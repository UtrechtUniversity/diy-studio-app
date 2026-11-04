# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

import logging
import socket
import threading
from typing import TYPE_CHECKING
from modules.backends.control_panel.control_panel_base import ControlPanel
from modules.backends.recorder import Action as RecAction
from websockets.exceptions import ConnectionClosedOK, ConnectionClosedError
from websockets.sync.server import serve

if TYPE_CHECKING:
    from modules.control_panel import ControlPanelManager

logger = logging.getLogger(__name__)


class StreamDeck(ControlPanel):
    def __init__(self, manager: "ControlPanelManager", config):
        super().__init__(manager, config)
        self.server = None
        self.stop_event = threading.Event()
        self.thread = None
        self.websocket = None
        self.websocket_lock = threading.Lock()

        if not self._port_available(self.port):
            logger.warning(f"StreamDeck : port {self.port} "
                            + "unavailable, falling back to 4469")
            self.port = 4469

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

    def _start_server(self):
        """Start the websocket server to which the SD plugin can connect."""
        try:
            host = self.local_host
            port = self.port

            logger.info(
                "StreamDeck : starting Websocket server "
                f"on {host}:{port}"
            )

            with serve(
                self._receive_from_sd,
                self.local_host,
                self.port
            ) as server:
                logger.info("StreamDeck : Websocket server running "
                            + f"on port {self.port}")
                self.manager.route_call("gui_manager", "update_debug_text", 1, True)
                self.server = server
                server.serve_forever()
                logger.info(
                    "StreamDeck : server loop stopped normally"
                )
        except OSError as e:
            logger.exception(
                "StreamDeck : server failed to start : "
                f"OSError : {e}"
            )
            self.manager.route_call("gui_manager", "update_debug_text", 1, False)
            self.manager.route_call("gui_manager", "show_error", 105, True)

        except Exception:
            logger.exception("StreamDeck : server stopped unexpectedly")
            self.manager.route_call("gui_manager", "update_debug_text", 1, False)
            self.manager.route_call("gui_manager", "show_error", 105, True)

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
                    "StreamDeck : error while closing server"
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
                    "StreamDeck : rejecting Stream Deck connection "
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

        logger.info("StreamDeck : listening to messages from "
                + f"SD plugin (from thread {id})")

        # Reset record button when starting server
        self._safe_send("stop-confirm")

        while not self.stop_event.is_set():
            try:
                msg = websocket.recv()
            except ConnectionClosedOK as e:
                logger.info("StreamDeck : websocket closed cleanly")
                break
            except ConnectionClosedError as e:
                logger.warning("StreamDeck : "
                             + f"connection closed with error : {e}")
                if not self.stop_event.is_set():
                    self.manager.route_call("gui_manager", "update_debug_text", 1, False)
                    self.manager.route_call("gui_manager", "show_error", 105, True)
                break
            except Exception as e:
                logger.warning("StreamDeck : "
                             + f"exception in event loop : {e}")
                if not self.stop_event.is_set():
                    self.manager.route_call("gui_manager", "update_debug_text", 1, False)
                    self.manager.route_call("gui_manager", "show_error", 105, True)
                break

            logger.info("StreamDeck : Stream Deck button pressed: "
                            + f"{msg}")
            current_state = self.manager.route_call("state_manager", "get_state_str")
            rec_action = self.manager.route_call("recorder_manager", "action")

            match msg:
                case "record":
                    match current_state:
                        case "StateRecordOverview" if (
                            (
                                rec_action == RecAction.IDLE
                                or rec_action == RecAction.CREATING_UPLOAD_JOB
                                or rec_action == RecAction.FINISHED
                            )
                            and self.manager.route_call("recorder_manager", "pre_rec_check")
                        ):
                            # We need to schedule this for
                            # the main thread:
                            logger.info("StreamDeck : "
                                            + "allowing to record")

                            self.manager.route_call(
                                "state_manager",
                                "change_state",
                                "state_record_active"
                            )

                        case "StateControls3":
                            self.manager.route_call(
                                "state_manager",
                                "change_state",
                                "state_record_overview"
                            )

                        case _:
                            logger.info("StreamDeck : "
                                + "not allowing recording, "
                                + f"state: {current_state}, rec_action: "
                                + f"{rec_action}")

                case "stop":
                    if current_state == "StateRecordActive":
                        match rec_action:
                            case RecAction.RECORDING:
                                self.manager.route_call("recorder_manager", "stop_record")
                            case RecAction.STARTING_COUNTDOWN:
                                self.manager.route_call(
                                    "gui_manager", "interrupt_countdown"
                                )

                case "pp-rewind":
                    self.manager.route_call("presentation_manager", "pp_rewind")

                case "pp-prev":
                    self.manager.route_call("presentation_manager", "pp_prev")

                case "pp-next":
                    self.manager.route_call("presentation_manager", "pp_next")

        # Always release the active client slot when this connection ends
        with self.websocket_lock:
            if self.websocket is websocket:
                self.websocket = None
            self.connected = False

        logger.info("StreamDeck : connection on thread "
                        + f"{id} closed")

    def _safe_send(self, msg: str):
        with self.websocket_lock:
            ws = self.websocket if self.connected else None

        if ws is None:
            logger.info(f"StreamDeck : send error '{msg}' (no client)")
            self.manager.route_call("gui_manager", "show_error", 105, True)
            return

        try:
            ws.send(str(msg))
        except Exception as e:
            logger.warning(f"StreamDeck : send error '{msg}' : {e}")
            self.manager.route_call("gui_manager", "show_error", 105, True)

    # =============================
    # Public methods
    # =============================
    def on_recording_started(self):
        self._safe_send("rec-confirm")

    def on_recording_stopped(self):
        self._safe_send("stop-confirm")

    def start(self):
        self.stop_event.clear()

        if self.thread is None or not self.thread.is_alive():
            self.thread = threading.Thread(
                name="StreamDeckServer",
                target=self._start_server,
                daemon=True
            )
            self.thread.start()

    def shutdown(self):
        """Stops Websocket server by sending a stop event."""
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

        self.manager.route_call("gui_manager", "update_debug_text", 1, False)
        logger.info("StreamDeck : stopped Websocket server")
