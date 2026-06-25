# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

import logging
import socket
import threading
from modules.backends.recorder import Action as RecAction
from websockets.exceptions import ConnectionClosedOK, ConnectionClosedError
from websockets.sync.server import serve

logger = logging.getLogger(__name__)


class StreamDeckManager:
    """Sets up a Websocket server for the Stream Deck plugin"""
    enabled = True
    managers: dict = {}

    def __init__(self, root_window, config):
        logger.info('StreamDeckManager : init')

        if not config.enable:
            StreamDeckManager.enabled = False

        self.connected = False
        self.websocket = None
        self.server = None
        self.local_host = config.ip
        self.esd_port = config.port
        self.root_window = root_window
        self.stop_event = threading.Event()
        self.thread = None
        self.websocket_lock = threading.Lock()

        if not self._port_available(self.esd_port):
            logger.warning(f"StreamDeckManager : port {self.esd_port} "
                            + "unavailable, falling back to 4469")
            self.esd_port = 4469

    # =============================
    # Internal methods
    # =============================
    def _port_available(self, port):
        """Check if the requested port is available."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((self.local_host, port))
            except socket.error:
                # Port is in use
                return False
            # Port is available
            return True

    def _safe_send(self, msg: str):
        if not StreamDeckManager.enabled:
            return

        with self.websocket_lock:
            ws = self.websocket if self.connected else None

        if ws is None:
            logger.info(f"StreamDeckManager : send error '{msg}' (no client)")
            self.route_call("gui_manager", "show_error", 105, True)
            return

        try:
            ws.send(str(msg))
        except Exception as e:
            logger.warning(f"StreamDeckManager : send error '{msg}' : {e}")
            self.route_call("gui_manager", "show_error", 105, True)

    def _start_server(self):
        """Start the websocket server to which the SD plugin can connect."""
        try:
            host = self.local_host
            port = self.esd_port

            logger.info(
                "StreamDeckManager : starting Websocket server "
                f"on {host}:{port}"
            )

            with serve(
                self._receive_from_sd,
                self.local_host,
                self.esd_port
            ) as server:
                logger.info("StreamDeckManager : Websocket server running "
                            + f"on port {self.esd_port}")
                self.route_call("gui_manager", "update_debug_text", 1, True)
                self.server = server
                server.serve_forever()
                logger.info(
                    "StreamDeckManager : server loop stopped normally"
                )
        except OSError as e:
            logger.exception(
                "StreamDeckManager : server failed to start : "
                f"OSError : {e}"
            )
            self.route_call("gui_manager", "update_debug_text", 1, False)
            self.route_call("gui_manager", "show_error", 105, True)

        except Exception:
            logger.exception("StreamDeckManager : server stopped unexpectedly")
            self.route_call("gui_manager", "update_debug_text", 1, False)
            self.route_call("gui_manager", "show_error", 105, True)

        finally:
            with self.websocket_lock:
                self.connected = False
                ws = self.websocket
                self.websocket = None

            try:
                if ws is not None:
                    ws.close()
            except Exception:
                logger.exception(
                    "StreamDeckManager : error while closing server"
                )

    def _receive_from_sd(self, websocket):
        id = threading.current_thread().name

        # If we're already shutting down, immediately close this connection
        if self.stop_event.is_set():
            try:
                websocket.close()
            except Exception:
                pass
            return

        # ---- ENFORCE SINGLE ACTIVE CONNECTION ----
        with self.websocket_lock:
            if self.connected:
                # Another client is already connected – reject this one
                logger.info(
                    "StreamDeckManager : rejecting Stream Deck connection "
                    "because a client is already connected"
                )
                try:
                    # Close this websocket; don't take over self.websocket
                    websocket.close()
                except Exception:
                    pass
                return

            # Claim the "active client" slot
            self.connected = True
            self.websocket = websocket

        logger.info("StreamDeckManager : listening to messages from "
                + f"SD plugin (from thread {id})")

        # Reset record button when starting server
        self._safe_send("stop-confirm")

        while not self.stop_event.is_set():
            try:
                msg = websocket.recv()
            except ConnectionClosedOK as e:
                logger.info("StreamDeckManager : websocket closed cleanly")
                break
            except ConnectionClosedError as e:
                logger.warning("StreamDeckManager : "
                             + f"connection closed with error : {e}")
                if not self.stop_event.is_set():
                    self.route_call("gui_manager", "update_debug_text", 1, False)
                    self.route_call("gui_manager", "show_error", 105, True)
                break
            except Exception as e:
                logger.warning("StreamDeckManager : "
                             + f"exception in event loop : {e}")
                if not self.stop_event.is_set():
                    self.route_call("gui_manager", "update_debug_text", 1, False)
                    self.route_call("gui_manager", "show_error", 105, True)
                break

            logger.info("StreamDeckManager : Stream Deck button pressed: "
                            + f"{msg}")
            current_state = self.route_call("state_manager", "get_state_str")
            rec_action = self.route_call("recorder_manager", "action")

            match msg:
                case "record":
                    match current_state:
                        case "StateRecordOverview" if (
                            (
                                rec_action == RecAction.IDLE
                                or rec_action == RecAction.CREATING_UPLOAD_JOB
                                or rec_action == RecAction.FINISHED
                            )
                            and self.route_call("recorder_manager", "pre_rec_check")
                        ):
                            # We need to schedule this for
                            # the main thread:
                            logger.info("StreamDeckManager : "
                                            + "allowing to record")

                            self.route_call(
                                "state_manager",
                                "change_state",
                                "state_record_active"
                            )

                        case "StateControls3":
                            self.route_call(
                                "state_manager",
                                "change_state",
                                "state_record_overview"
                            )

                        case _:
                            logger.info("StreamDeckManager : "
                                + "not allowing recording, "
                                + f"state: {current_state}, rec_action: "
                                + f"{rec_action}")

                case "stop":
                    if current_state == "StateRecordActive":
                        match rec_action:
                            case RecAction.RECORDING:
                                self.route_call("recorder_manager", "stop_record")
                            case RecAction.STARTING_COUNTDOWN:
                                self.route_call(
                                    "gui_manager", "interrupt_countdown"
                                )

                case "pp-rewind":
                    self.route_call("presentation_manager", "pp_rewind")

                case "pp-prev":
                    self.route_call("presentation_manager", "pp_prev")

                case "pp-next":
                    self.route_call("presentation_manager", "pp_next")

        # Always release the active client slot when this connection ends
        with self.websocket_lock:
            if self.websocket is websocket:
                self.websocket = None
            self.connected = False

        logger.info("StreamDeckManager : connection on thread "
                        + f"{id} closed")

    # =============================
    # Public methods
    # =============================
    def on_gui_loaded(self):
        if not StreamDeckManager.enabled:
            return

        self.stop_event.clear()

        if self.thread is None or not self.thread.is_alive():
            self.thread = threading.Thread(
                name="StreamDeckServer",
                target=self._start_server,
                daemon=True
            )
            self.thread.start()

    def on_recording_started(self):
        if StreamDeckManager.enabled:
            self._safe_send("rec-confirm")

    def on_recording_stopped(self):
        if StreamDeckManager.enabled:
            self._safe_send("stop-confirm")

    def stop_server(self):
        """Stops Websocket server by sending a stop event."""
        if not StreamDeckManager.enabled:
            return

        self.stop_event.set()

        # Close active client
        with self.websocket_lock:
            self.connected = False
            try:
                if self.websocket:
                    self.websocket.close()
            except Exception:
                pass

            self.websocket = None

        # Stop the listening server
        try:
            if self.server is not None:
                self.server.shutdown()
        except Exception:
            pass

        # Join the thread
        if self.thread is not None and self.thread.is_alive():
            if threading.current_thread() is not self.thread:
                self.thread.join(timeout=2.0)

        self.route_call("gui_manager", "update_debug_text", 1, False)
        logger.info("StreamDeckManager : stopped Websocket server")

    # =============================
    # Outbound communication
    # =============================
    def route_call(self, manager, method, *args, **kwargs):
        presentation_manager = StreamDeckManager.managers.get("presentation_manager")
        recorder_manager = StreamDeckManager.managers.get("recorder_manager")
        state_manager = StreamDeckManager.managers.get("state_manager")
        gui_manager = StreamDeckManager.managers.get("gui_manager")

        if not presentation_manager:
            logger.error("StreamDeckManager : presentation_manager not registered")
            return

        if not recorder_manager:
            logger.error("StreamDeckManager : recorder_manager not registered")
            return

        if not state_manager:
            logger.error("StreamDeckManager : state_manager not registered")
            return

        if not gui_manager:
            logger.error("StreamDeckManager : gui_manager not registered")
            return

        match (manager, method):
            case ("presentation_manager", "pp_rewind"):
                presentation_manager.pp_rewind()

            case ("presentation_manager", "pp_prev"):
                presentation_manager.pp_prev()

            case ("presentation_manager", "pp_next"):
                presentation_manager.pp_next()

            case ("recorder_manager", "pre_rec_check"):
                return recorder_manager.pre_rec_check()

            case ("recorder_manager", "action"):
                return recorder_manager.action

            case ("recorder_manager", "stop_record"):
                recorder_manager.stop_record()

            case ("state_manager", "change_state"):
                state = getattr(state_manager, args[0])
                state_manager.change_state(state)

            case ("state_manager", "get_state_str"):
                return state_manager.get_state_str()

            case ("gui_manager", "interrupt_countdown"):
                gui_manager.call_on_ui_thread(method)

            case ("gui_manager", "show_error"):
                gui_manager.call_on_ui_thread(method, *args)

            case ("gui_manager", "update_debug_text"):
                gui_manager.call_on_ui_thread(method, args[0], args[1])
