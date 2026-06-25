# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

"""
Module for interacting with a cloud storage provider.
Currently OneDrive is supported.
"""

import asyncio
import logging
import re
import socket
import threading
from concurrent.futures import CancelledError as FutureCancelledError, TimeoutError as FutureTimeoutError
from modules.backends.cloud_storage import Action
from modules.backends.cloud_storage.storage_base import CloudStorageDirContent
from modules.backends.cloud_storage.onedrive import OneDriveStorage
from os.path import join

logger = logging.getLogger(__name__)

PROVIDER_CLASSES = {
    "onedrive": OneDriveStorage
}


class CloudStorageManager:
    enabled = True
    managers: dict = {}

    def __init__(self, enable, config, paths):
        logger.info("CloudStorageManager : init")

        try:
            provider_class = PROVIDER_CLASSES[config.provider.lower()]
        except KeyError:
            raise ValueError(
                "CloudStorageManager : unknown cloud storage provider: "
                f"{config.provider}"
            )

        self._auth_future = None
        self._auth_in_progress = threading.Event()
        self.action = Action.IDLE
        self.dir_content = None
        self.dir_id = None
        self.done = False
        self.download_dir = paths.download_dir
        self.loop = None
        self.loop_started = threading.Event()
        self.online = False
        self.provider = provider_class(manager=self, config=config)
        self.presentation = None
        self.rec_dir_good = join(paths.record_dir, "good")
        self.asyncio_thread = None
        self.upload_restart_timer = None
        self.uploads = []

        if not enable:
            CloudStorageManager.enabled = False
            self.provider.authenticated = True

    # =========================================
    # Post-UI-initialization setup and shutdown
    # =========================================
    def setup(self):
        self.loop = asyncio.new_event_loop()

        self.asyncio_thread = threading.Thread(
            name="CloudStorageAsyncioLoop",
            target=self.run_async_loop,
            args=(self.loop,)
        )
        self.asyncio_thread.start()

    def shutdown(self):
        """Stops the Asyncio event loop and joins the thread"""
        logger.info("CloudStorageManager : stopping Asyncio event loop and "
                    "joining thread")
        self.loop.call_soon_threadsafe(self.loop.stop)

        if self.asyncio_thread is not None and self.asyncio_thread.is_alive():
            if threading.current_thread() is not self.asyncio_thread:
                self.asyncio_thread.join(timeout=2.0)

    # =============================
    # Internal methods
    # =============================
    def _on_restart_timer_finished(self):
        if not CloudStorageManager.enabled:
            return

        if self.upload_restart_timer:
            self.restart_upload_queue()

    def _start_auth(self):
        if not CloudStorageManager.enabled:
            logger.info("CloudStorageManager : module not enabled")
            self.set_action(Action.IDLE)
            self.route_call("gui_manager", "on_authenticated", None)
            return

        if self._auth_in_progress.is_set():
            logger.warning("CloudStorageManager : can't start authentication, "
                            "auth_lock is True")
            self.set_action(Action.IDLE)
            return

        # There can only be a single auth process happening at any time.
        # This is a limitation of the Microsoft Graph Python SDK
        # in combination with the InteractiveBrowserCredential:
        # Multiple auth processes will interfere with one another and
        # result in "token mismatch" errors.
        self._auth_in_progress.set()

        self._auth_future = asyncio.run_coroutine_threadsafe(
            self.provider.authenticate(),
            self.loop
        )

        self._auth_future.add_done_callback(self.on_authenticated)
        self.route_call("gui_manager", "start_auth_timer")

    # =============================
    # Other public methods
    # =============================
    def add_to_uploads(self, item):
        logger.info(
            "CloudStorageManager : upload status : " + item.get_status()
        )
        self.uploads.append(item)

    def all_uploads_done(self):
        return len(self.provider.upload_queue) == 0

    def get_remaining_uploads(self):
        return len(self.provider.upload_queue)

    def is_authenticated(self):
        return self.provider.authenticated

    def is_internet_available(self) -> bool:
        """Checks internet connection via socket to Google public DNS server"""
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=2).close()
            self.route_call("gui_manager", "update_debug_text", 3, True)
            if self.online == False:
                # Back online
                self.restart_upload_queue()
            self.online = True
            return True
        except OSError:
            self.online = False
            self.route_call("gui_manager", "update_debug_text", 3, False)
            self.route_call("gui_manager", "show_error", 102)
            return False

    def logout(self):
        # Clear upload list
        self.uploads = []
        # Logout
        self.provider.logout()

    def restart_upload_queue(self):
        if not CloudStorageManager.enabled:
            return

        # Stop running timers from rescheduling
        self.upload_restart_timer = False

        try:
            if len(self.provider.upload_queue) >= 1:
                logger.info(
                    "CloudStorageManager : trying to restart upload queue"
                )

                fut = getattr(self, "_upload_future", None)
                if fut is not None and not fut.done():
                    logger.info(
                        "CloudStorageManager : not starting upload queue, "
                        "another session is already underway"
                    )
                    return

                self._upload_future = asyncio.run_coroutine_threadsafe(
                    self.provider.process_upload_queue(),
                    self.loop
                )
        except Exception:
            logger.exception(
                "CloudStorageManager : error while restarting file uploads"
            )

    def run_async_loop(self, loop):
        try:
            asyncio.set_event_loop(loop)
            loop.run_forever()
        except Exception:
            logger.exception("CloudStorageManager : asyncio event loop error")

    def set_action(self, s):
        if self.action == s:
            # Do nothing
            return

        if self.action == Action.AUTHENTICATING and s != Action.IDLE:
            logger.warning("CloudStorageManager : can't switch status to "
                            f"{s} - current status is Action.AUTHENTICATING")
            # self.route_call("gui_manager", "show_error", 404)
            return

        self.action = s

        match self.action:
            case Action.IDLE:
                logger.info("CloudStorageManager : IDLE")

            case Action.AUTHENTICATING:
                logger.info("CloudStorageManager : AUTHENTICATING")
                self._start_auth()

            case Action.REQUESTING_FOLDER:
                logger.info("CloudStorageManager : REQUESTING_FOLDER")
                if CloudStorageManager.enabled:
                    list_fut = asyncio.run_coroutine_threadsafe(
                        self.provider.list_files(self.dir_id),
                        self.loop
                    )
                    list_fut.add_done_callback(self.on_files_listed)
                else:
                    # Cloud storage not enabled, return empty
                    # CloudStorageDirContent object
                    self.dir_content = CloudStorageDirContent([], [])
                    self.route_call(
                        "gui_manager",
                        "set_folder_data",
                        self.dir_content
                    )
                    self.set_action(Action.IDLE)

            case Action.DOWNLOADING_FILE:
                logger.info("CloudStorageManager : DOWNLOADING_FILE")

                if not self.is_internet_available():
                    self.route_call("gui_manager", "show_error", 102)
                    self.set_action(Action.IDLE)
                    return

                future = asyncio.run_coroutine_threadsafe(
                    self.provider.download_file(self.presentation),
                    self.loop
                )

                try:
                    result = future.result(timeout=30)
                    if result.startswith("error"):
                        # Download failed. Display error.
                        # Not much else we can do?
                        logger.error("CloudStorageManager : download failed"
                                      "- will not attempt to open file")
                        self.route_call(
                            "gui_manager", "show_error", 405)
                        return
                    else:
                        self.on_download_complete(result)
                        return
                except FutureTimeoutError:
                    logger.error("CloudStorageManager : download timed out")
                    future.cancel()
                    self.route_call("gui_manager", "show_error", 405)
                    self.set_action(Action.IDLE)
                    return
                except Exception as e:
                    logger.error("CloudStorageManager : error while waiting "
                                  f"for download: {e}")
                    self.route_call("gui_manager", "show_error", 405)
                    self.set_action(Action.IDLE)
                    return

    def set_dir_id(self, id):
        """Change directory by directory id

        This function will be called by:
        * StateManager: StatePowerPoint.enter()
        * PagePowerPoint (user clicks on a directory) -> GuiManager
        """
        if id != "current":
            self.dir_id = id
        self.set_action(Action.REQUESTING_FOLDER)

    def set_presentation(self, index):
        """Register the chosen presentation, then download

        index belongs to CloudStorageDirContent.files[index],
        which contains the CloudStorageItem that needs to be downloaded.

        This function will be called by:
        * PagePowerPoint (user clicks on a file) -> GuiManager"""
        new_presentation = self.dir_content.files[index]

        if (self.presentation is None
            or self.presentation.id != new_presentation.id):
            self.presentation = new_presentation

        # Download file
        self.set_action(Action.DOWNLOADING_FILE)

    def on_authenticated(self, future):
        success = False

        try:
            result = future.result()
        except FutureCancelledError:
            logger.info("CloudStorageManager : authentication was cancelled")
        except Exception as e:
            logger.error("CloudStorageManager : error while waiting "
                          f"for authentication: {e}")

            err = 0

            if str(e).startswith("Timed out"):
                err = 1

            # Try again
            self.route_call("gui_manager", "on_auth_failed", err)
        else:
            if result:
                logger.info("CloudStorageManager : authentication successful")
                self.dir_id = self.provider.root_item_id
                self.route_call(
                    "gui_manager",
                    "on_authenticated",
                    self.provider.root_item_id
                )
                success = True
            else:
                logger.error("CloudStorageManager : authentication failed")
                self.route_call("gui_manager", "on_auth_failed", 1)
        finally:
            # Release authentication lock
            self._auth_in_progress.clear()
            self._auth_future = None
            self.set_action(Action.IDLE)

        if success:
            # There might be uploads waiting in the queue; start these
            self.restart_upload_queue()

    def on_files_listed(self, future):
        """Received CloudStorageDirContent object with contents of directory

        Store this directory content in self.dir_content and pass it on
        to PagePowerPoint via GuiManager.set_folder_data()"""
        try:
            self.dir_content = future.result(timeout=20)
            self.route_call(
                "gui_manager",
                "set_folder_data",
                self.dir_content
            )
        except FutureTimeoutError:
            logger.error("CloudStorageManager : list_files() timed out")
            future.cancel()
            self.route_call("gui_manager", "show_error", 408)
        except FutureCancelledError:
            logger.info("CloudStorageManager : list_files() was cancelled")
        except Exception as e:
            logger.error(
                f"CloudStorageManager : error while listing files: {e}"
            )
            self.route_call("gui_manager", "show_error", 408)

        self.set_action(Action.IDLE)

    def on_download_complete(self, path):
        self.set_action(Action.IDLE)
        logger.info("CloudStorageManager : received file, "
                     "opening file.")
        self.route_call("presentation_manager", "open_presentation", path)
        self.route_call("gui_manager", "stats_update_download_amnt")

    def schedule_queue_restart(self):
        if self.upload_restart_timer:
            return

        self.upload_restart_timer = True

        self.route_call(
            "gui_manager",
            "schedule_task_threadsafe",
            30000,
            self._on_restart_timer_finished
        )

    def start_upload(self, name):
        anon_name = re.sub(r'[a-zA-Z]', 'X', name)
        logger.info("CloudStorageManager : start_upload : " + anon_name)

        result = self.provider.create_upload_job(name)

        if not result:
            self.route_call("gui_manager", "show_error", 406)
            return

        if not CloudStorageManager.enabled:
            # Let's pretend the upload has finished
            result.set_status("finished")
            # Remove from upload_queue
            self.provider.upload_queue.popleft()
            self.provider.uploaded_files.append(result)
            return

        try:
            self.add_to_uploads(result)

            # Start queue if current job is the only job in there.
            # If another job is present in the queue than nothing
            # needs to happen right now.
            if len(self.provider.upload_queue) == 1:
                fut = getattr(self, "_upload_future", None)
                if fut is not None and not fut.done():
                    logger.info(
                        "CloudStorageManager : not starting upload queue, "
                        "another session is already underway."
                    )
                    return

                self._upload_future = asyncio.run_coroutine_threadsafe(
                    self.provider.process_upload_queue(),
                    self.loop
                )

        except Exception as e:
            logger.error(
                "CloudStorageManager : error while waiting "
                f"for file upload: {e}"
            )

    # =============================
    # Outbound communication
    # =============================
    def route_call(self, manager, method, *args, **kwargs):
        presentation_manager = CloudStorageManager.managers.get(
            "presentation_manager"
            )
        gui_manager = CloudStorageManager.managers.get("gui_manager")

        if not presentation_manager:
            logger.error(
                "CloudStorageManager : presentation_manager not registered"
            )
            return

        if not gui_manager:
            logger.error("CloudStorageManager : gui_manager not registered")
            return

        match (manager, method):
            case ("presentation_manager", "open_presentation"):
                presentation_manager.open_presentation(args[0])

            case ("gui_manager", "on_auth_failed"):
                gui_manager.call_on_ui_thread(method, args[0])

            case("gui_manager", "on_auth_lost"):
                gui_manager.call_on_ui_thread(method)

            case ("gui_manager", "on_authenticated"):
                gui_manager.call_on_ui_thread(method, args[0])

            case ("gui_manager", "schedule_task_threadsafe"):
                gui_manager.schedule_task_threadsafe(*args, **kwargs)

            case ("gui_manager", "show_error"):
                gui_manager.call_on_ui_thread(method, *args, **kwargs)

            case ("gui_manager", "set_folder_data"):
                gui_manager.call_on_ui_thread(method, args[0])

            case ("gui_manager", "start_auth_timer"):
                gui_manager.call_on_ui_thread(
                    method, self.provider.LOGIN_TIMEOUT
                )

            case ("gui_manager", "stats_update_download_amnt"):
                gui_manager.call_on_ui_thread(
                    "stats.update", "file_download_amnt"
                )

            case ("gui_manager", "update_debug_text"):
                gui_manager.call_on_ui_thread(method, args[0], args[1])

            case ("gui_manager", "update_shutdown_info"):
                gui_manager.call_on_ui_thread(method, num_uploads=args[0])
