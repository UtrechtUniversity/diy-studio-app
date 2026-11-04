# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

import logging
from modules.backends.control_panel.stream_deck import StreamDeck

logger = logging.getLogger(__name__)

PANEL_CLASSES = {
    "stream_deck": StreamDeck
}

class ControlPanelManager:
    """Management of control panel implementations."""
    enabled = True
    managers: dict = {}

    def __init__(self, root_window, config):
        logger.info("ControlPanelManager : init")

        try:
            panel_class = PANEL_CLASSES[config.panel.lower()]
        except KeyError:
            raise ValueError(
                "ControlPanelManager : unknown control panel: "
                f"{config.panel}"
            )

        self._panel = panel_class(
            self, config)

        if not config.enable:
            ControlPanelManager.enabled = False

        self.root_window = root_window

    # =============================
    # Internal methods
    # =============================

    # =============================
    # Public methods
    # =============================
    def on_gui_loaded(self):
        if ControlPanelManager.enabled:
            self._panel.start()

    def on_recording_started(self):
        if ControlPanelManager.enabled:
            self._panel.on_recording_started()

    def on_recording_stopped(self):
        if ControlPanelManager.enabled:
            self._panel.on_recording_stopped()

    def shutdown(self):
        if ControlPanelManager.enabled:
            self._panel.shutdown()

    # =============================
    # Outbound communication
    # =============================
    def route_call(self, manager, method, *args, **kwargs):
        presentation_manager = ControlPanelManager.managers.get("presentation_manager")
        recorder_manager = ControlPanelManager.managers.get("recorder_manager")
        state_manager = ControlPanelManager.managers.get("state_manager")
        gui_manager = ControlPanelManager.managers.get("gui_manager")

        if not presentation_manager:
            logger.error("ControlPanelManager : presentation_manager not registered")
            return

        if not recorder_manager:
            logger.error("ControlPanelManager : recorder_manager not registered")
            return

        if not state_manager:
            logger.error("ControlPanelManager : state_manager not registered")
            return

        if not gui_manager:
            logger.error("ControlPanelManager : gui_manager not registered")
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
