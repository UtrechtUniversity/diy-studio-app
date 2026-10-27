import logging
import psutil
import pywinctl as window_manager
import pywintypes
import subprocess
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from time import monotonic

logger = logging.getLogger(__name__)


class Browser:
    """Manage all webbrowser related things.

    The browser is used for several things:
        - The login procedure (InteractiveBrowserCredential)
        - To display a loading screen until TkInter GUI is loaded
        - Video player for the tutorial video and user recordings

    Upon launching the browser, we create a local HTTP server which
    servers loading.html: this will send a reply so we know that
    the browser has actually loaded and displayed this page.
    """
    def __init__(self, manager, name, path, args, close):
        """Initialize browser process, readiness, and notification state."""
        logger.info("Initializing browser")
        self.args = args
        self.close = close
        self.deadline = None
        self.force_terminate_sent = False
        self.manager = manager
        self.name = name
        self.on_shutdown_complete = None
        self.on_state_changed: Callable[[], None] | None = None
        self.path = path
        self.pending_url = None
        self.poll_id = None
        self.process = None
        self.ready_event = threading.Event()
        self.ready_server = None
        self.ready_server_thread = None
        self.shutting_down = False
        self.state = "stopped"
        self.stopping_processes: set[psutil.Process] = set()

    def _set_state(self, state: str) -> None:
        """Store a changed browser state and notify the GUI."""
        if self.state == state:
            return

        self.state = state
        if self.on_state_changed is not None:
            self.on_state_changed()

    def _begin_stop(self):
        """Begin browser closure and poll for process exit"""
        if not self.close or self.state == "stopping":
            return

        if self.poll_id is not None:
            self.manager.cancel_task(self.poll_id)
            self.poll_id = None

        self._set_state("stopping")
        self.ready_event.clear()
        self.deadline = monotonic() + 15
        self.force_terminate_sent = False
        self.stopping_processes = set(self._get_browser_processes())

        # First try to simply close all browser windows
        for window in self.get_visible_browser_windows():
            try:
                window.close()
            except (OSError, pywintypes.error) as e:
                logger.warning(
                    "Browser : could not request window closure (%s)",
                    type(e).__name__
                )

        # Stop any remaining processes
        self._poll_shutdown()

    def _finish_app_shutdown(self):
        """Stop ready-check server and complete application shutdown."""
        def finish():
            self._set_state("closed")
            callback = self.on_shutdown_complete
            self.on_shutdown_complete = None
            if callback is not None:
                callback()

        self._stop_ready_server(finish)

    def _get_browser_processes(self):
        """Return all active browser processes."""
        browser_path = Path(self.path).resolve()
        processes = []

        for process in psutil.process_iter():
            try:
                executable = process.exe()
                if executable and Path(executable).resolve() == browser_path:
                    processes.append(process)
            except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                continue

        return processes

    def _poll_shutdown(self):
        """Wait for browser exit with forced-stop fallback."""
        self.poll_id = None
        if self.state != "stopping":
            return

        self.stopping_processes.update(self._get_browser_processes())
        self.stopping_processes = {
            process for process in self.stopping_processes
            if process.is_running()
        }

        # Check if we already have a launch process and if poll()
        # doesn't return an exit-code for that process.
        launcher_running = (
            self.process is not None and self.process.poll() is None
        )

        # If no processes need to be stopped and no launcher is running,
        # we are finished already.
        if not self.stopping_processes and not launcher_running:
            self.process = None
            self.deadline = None
            self._set_state("stopped")

            if self.shutting_down:
                self._finish_app_shutdown()
            else:
                destination = self.pending_url
                self.pending_url = None
                self.launch(destination)
            return

        now = monotonic()
        if self.deadline is not None and now >= self.deadline:
            # Deadline has been passed. If there has been an attempt
            # to terminate the browser already, there's nothing more
            # to try.
            if self.force_terminate_sent:
                self._set_state("failed")
                self.deadline = None
                logger.error("Browser : could not confirm shutdown")

                if self.shutting_down:
                    self._finish_app_shutdown()
                return

            self.force_terminate_sent = True
            logger.warning(
                "Browser : forcing remaining browser processes to stop"
            )

            for process in self.stopping_processes:
                try:
                    process.kill()
                except psutil.NoSuchProcess:
                    continue
                except (psutil.AccessDenied, OSError) as e:
                    logger.error(
                        "Browser : could not stop a process (%s)",
                        type(e).__name__
                    )

            if self.process is not None and self.process.poll() is None:
                try:
                    self.process.kill()
                except OSError as e:
                    logger.error(
                        "Browser : could not stop launcher (%s)",
                        type(e).__name__
                    )

            self.deadline = now + 5

        self.poll_id = self.manager.window.after(
            100, self._poll_shutdown
        )

    def _poll_startup(self):
        """Check page readiness without blocking GUI thread."""
        self.poll_id = None

        if self.state != "starting":
            return

        if self.ready_event.is_set():
            self._set_state("ready")
            self.deadline = None
            logger.info("Browser : loading page is ready")

            if self.pending_url is not None:
                self.navigate(self.pending_url)
            return

        if self.deadline is not None and monotonic() >= self.deadline:
            self._set_state("failed")
            self.deadline = None
            logger.error("Browser : startup timed out")
            return

        self.poll_id = self.manager.window.after(
            100, self._poll_startup
        )

    def _start_process(self, url):
        """Start browser and return its process."""
        url = url.replace("\\", "/").replace(" ", "%20")
        command = [self.path, *self.args, url]

        try:
            process = subprocess.Popen(command)
        except OSError as e:
            logger.error(
                "Browser : could not start %s (%s)",
                self.name,
                type(e).__name__
            )
            return None

        logger.info(f"Browser : started {self.name}")
        return process

    def _start_ready_server(self):
        """Start a local HTTP ready-check server and return the loading URL."""
        if self.ready_server is not None:
            port = self.ready_server.server_port
            return f"http://127.0.0.1:{port}/loading.html"

        loading_path = Path(self.manager.html_dir) / "loading.html"
        loading_html = loading_path.read_bytes()
        ready_event = self.ready_event

        class ReadyHandler(BaseHTTPRequestHandler):
            """Serve the loading page and receive its ready notification."""

            def do_GET(self):
                """Serve loading page."""
                if self.path != "/loading.html":
                    self.send_error(404)
                    return

                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(loading_html)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(loading_html)

            def do_POST(self):
                """Receive ready notification from loading page."""
                if self.path != "/ready":
                    self.send_error(404)
                    return

                expected_origin = (
                    f"http://127.0.0.1:{server.server_port}"
                )

                if self.headers.get("Origin") != expected_origin:
                    self.send_error(403)
                    return

                self.send_response(204)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                ready_event.set()

            def log_message(self, format, *args):
                """Disable default HTTP request logging."""
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), ReadyHandler)
        thread = threading.Thread(
            target=server.serve_forever,
            name="BrowserReadyServer",
            daemon=True
        )

        try:
            thread.start()
        except RuntimeError:
            server.server_close()
            raise

        self.ready_server = server
        self.ready_server_thread = thread

        return f"http://127.0.0.1:{server.server_port}/loading.html"

    def _stop_ready_server(self, on_complete=None):
        """Stop HTTP listener."""
        server = self.ready_server
        server_thread = self.ready_server_thread

        def finish():
            self.ready_server = None
            self.ready_server_thread = None
            self.ready_event.clear()
            if on_complete is not None:
                on_complete()

        if server is None:
            finish()
            return

        def stop_server():
            try:
                try:
                    server.shutdown()
                finally:
                    server.server_close()

                if server_thread is not None:
                    server_thread.join()
            except (OSError, RuntimeError) as e:
                logger.error(
                    "Browser : could not stop ready-check server (%s)",
                    type(e).__name__
                )
            finally:
                self.manager.queue_task(finish)

        threading.Thread(
            target=stop_server,
            name="BrowserReadyShutdown",
            daemon=True
        ).start()

    def get_visible_browser_windows(self):
        """Return visible windows belonging to the configured browser."""
        process_ids = {
            process.pid for process in self._get_browser_processes()
        }
        if not process_ids:
            return []

        windows = []
        for window in window_manager.getAllWindows():
            try:
                if window.getPID() in process_ids and window.isVisible:
                    windows.append(window)
            except (OSError, pywintypes.error):
                continue

        return windows

    def launch(self, url=None):
        """Start the loading page, optionally followed by a url."""
        if self.shutting_down:
            return

        if self.state in ("starting", "stopping"):
            if url is not None:
                self.pending_url = url
            return

        if self.state == "ready":
            if url is not None:
                self.navigate(url)
            return

        self.pending_url = url
        self.ready_event.clear()

        # Start the server that will load loading.html and
        # receives the ready message.
        try:
            loading_url = self._start_ready_server()
        except (OSError, RuntimeError) as e:
            self._set_state("failed")
            logger.error(
                "Browser : could not start readiness listener (%s)",
                type(e).__name__
            )
            return

        # Launch the browser and navigate to the loading url
        self.process = self._start_process(loading_url)
        if self.process is None:
            self._set_state("failed")
            return

        self._set_state("starting")
        self.deadline = monotonic() + 120
        self._poll_startup()

    def navigate(self, url):
        """Navigate to a url when ready or remember URL.

        If self.state is anything other than 'stopped' or 'ready',
        pending_url is kept.
        """
        if self.shutting_down:
            return

        self.pending_url = url

        if self.state == "stopped":
            self.launch(url)
        elif (
            self.state == "ready"
            and self._start_process(url) is not None):
            self.pending_url = None

    def quit_and_restart(self):
        """Close and restart the browser when config allows."""
        if self.shutting_down or not self.close or self.state == "stopping":
            return
        self.pending_url = "about:blank"
        self._begin_stop()

    def shutdown(self, on_complete=None):
        """Quit browser on shutdown, before application exit."""
        if self.shutting_down:
            return

        self.shutting_down = True
        self.on_shutdown_complete = on_complete
        self.pending_url = None

        if self.on_state_changed is not None:
            self.on_state_changed()

        if self.close:
            self._begin_stop()
            return

        if self.poll_id is not None:
            self.manager.cancel_task(self.poll_id)
            self.poll_id = None

        self.deadline = None
        self._set_state("stopped")
        self._finish_app_shutdown()
