# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

from enum import Enum
from modules.backends.cloud_storage import Action as CloudStorageAction
from modules.gui import Pages
from modules.recorder import Action as RecAction
from modules.gui_pages.menu import ButtonsMenu
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from modules.state_manager import StateManager


class Action(Enum):
    IDLE = "idle"
    TRANSITIONING = "transitioning"
    UPDATING = "updating"
    PROCESSING_EVENT = "processing event"


class State:
    manager: "StateManager"

    def enter(self):
        pass

    def while_active(self):
        State.manager.set_action(Action.UPDATING)

    def leave(self):
        pass


class StateLogin1(State):
    def enter(self):
        State.manager.route_call("gui_manager", "hide_streamdeck_windows")
        State.manager.route_call(
            "gui_manager", "menu.set_btn_active", ButtonsMenu.LOGIN.value
        )
        State.manager.route_call("gui_manager", "view_page", Pages.LOGIN1)

    def leave(self):
        State.manager.route_call("gui_manager", "leave_page", Pages.LOGIN1)


class StateLogin2(State):
    def enter(self):
        State.manager.route_call(
            "gui_manager", "menu.set_btn_active", ButtonsMenu.LOGIN.value
        )
        State.manager.route_call("gui_manager", "menu.set_unlock_index", 0)
        State.manager.route_call(
            "cloud_manager", "set_action", CloudStorageAction.AUTHENTICATING
        )
        State.manager.route_call("gui_manager", "view_page", Pages.LOGIN2)

    def leave(self):
        State.manager.route_call("gui_manager", "leave_page", Pages.LOGIN2)


class StateTutorial(State):
    def enter(self):
        State.manager.route_call(
            "gui_manager", "menu.set_btn_active", ButtonsMenu.TUTORIAL.value
        )
        State.manager.route_call("gui_manager", "menu.set_unlock_index", 1)
        State.manager.route_call("gui_manager", "view_page", Pages.TUTORIAL)

    def leave(self):
        State.manager.route_call("gui_manager", "close_browser")
        State.manager.route_call("gui_manager", "leave_page", Pages.TUTORIAL)


class StateVideotype1(State):
    def enter(self):
        State.manager.route_call(
            "gui_manager", "menu.set_btn_active", ButtonsMenu.VIDEOTYPE.value
        )
        State.manager.route_call("gui_manager", "menu.set_unlock_index", 2)
        State.manager.route_call("gui_manager", "view_page", Pages.VIDEOTYPE_1)

    def leave(self):
        State.manager.route_call("gui_manager", "leave_page", Pages.VIDEOTYPE_1)


class StateVideotype2(State):
    def enter(self):
        State.manager.route_call("recorder_manager", "open_projector")
        State.manager.route_call("gui_manager", "menu.set_btn_active",
                                 ButtonsMenu.VIDEOTYPE.value)
        State.manager.route_call("gui_manager", "view_page", Pages.VIDEOTYPE_2)

    def leave(self):
        State.manager.route_call("gui_manager", "close_obs_projector")
        State.manager.route_call("gui_manager", "leave_page", Pages.VIDEOTYPE_2)


class StatePowerpoint(State):
    def enter(self):
        State.manager.route_call("cloud_manager", "set_dir_id", "current")
        State.manager.route_call("gui_manager", "menu.set_btn_active",
                                 ButtonsMenu.POWERPOINT.value)
        State.manager.route_call("gui_manager", "menu.set_unlock_index", 3)
        State.manager.route_call("gui_manager", "view_page", Pages.POWERPOINT)

    def leave(self):
        State.manager.route_call("gui_manager", "leave_page", Pages.POWERPOINT)


class StateCalibration1(State):
    def enter(self):
        State.manager.route_call("recorder_manager",
                                 "switch_scenes",
                                 preview_scene = "NoPreview",
                                 program_scene = "Program-DeskHeight")
        State.manager.route_call("recorder_manager", "open_projector")
        State.manager.route_call("gui_manager", "menu.set_btn_active",
                                 ButtonsMenu.CALIBRATION.value)
        State.manager.route_call("gui_manager", "menu.set_unlock_index", 4)
        State.manager.route_call("gui_manager", "view_page", Pages.CALIBRATION_1)

    def leave(self):
        State.manager.route_call("gui_manager", "close_obs_projector")
        State.manager.route_call("gui_manager", "leave_page", Pages.CALIBRATION_1)


class StateCalibration2(State):
    def enter(self):
        State.manager.route_call("audio_manager", "start_mic_check")
        State.manager.route_call("gui_manager", "view_page", Pages.CALIBRATION_2)

    def leave(self):
        State.manager.route_call("audio_manager", "stop_mic_check")
        State.manager.route_call("gui_manager", "leave_page", Pages.CALIBRATION_2)


class StateCalibrationHelp(State):
    def enter(self):
        State.manager.route_call("gui_manager", "view_page", Pages.CALIBRATION_HELP)

    def leave(self):
        State.manager.route_call("gui_manager", "leave_page",
                                 Pages.CALIBRATION_HELP)


class StateControls1(State):
    def enter(self):
        State.manager.route_call("gui_manager", "menu.set_btn_active",
                                 ButtonsMenu.CONTROLS.value)
        State.manager.route_call("gui_manager", "menu.set_unlock_index", 5)
        State.manager.route_call("gui_manager", "view_page", Pages.CONTROLS_1)

    def leave(self):
        State.manager.route_call("gui_manager", "leave_page", Pages.CONTROLS_1)


class StateControls2(State):
    def enter(self):
        State.manager.route_call("gui_manager", "view_page", Pages.CONTROLS_2)

    def leave(self):
        State.manager.route_call("gui_manager", "leave_page", Pages.CONTROLS_2)


class StateControls3(State):
    def enter(self):
        State.manager.route_call("gui_manager", "view_page", Pages.CONTROLS_3)

    def leave(self):
        State.manager.route_call("gui_manager", "leave_page", Pages.CONTROLS_3)


class StateRecordOverview(State):
    def enter(self):
        State.manager.route_call("recorder_manager", "enable_decklink_input")
        State.manager.route_call("recorder_manager", "switch_scene_to_videotype")
        State.manager.route_call("recorder_manager", "open_projector")
        State.manager.route_call("gui_manager", "menu.set_btn_active",
                                 ButtonsMenu.RECORD.value)
        State.manager.route_call("gui_manager", "menu.set_unlock_index", 6)
        State.manager.route_call("gui_manager", "view_page", Pages.RECORD_OVERVIEW)

    def leave(self):
        State.manager.route_call("gui_manager", "stop_checking_uploads")
        State.manager.route_call("gui_manager", "close_obs_projector")
        State.manager.route_call("gui_manager", "leave_page", Pages.RECORD_OVERVIEW)


class StateRecordActive(State):
    def enter(self):
        State.manager.route_call("gui_manager", "menu.set_btn_active",
            ButtonsMenu.RECORD.value, lock_rest = True)
        State.manager.route_call("recorder_manager", "set_action", RecAction.STARTING_COUNTDOWN)
        State.manager.route_call("gui_manager", "view_page", Pages.RECORD_ACTIVE)

    def leave(self):
        State.manager.route_call("gui_manager", "leave_page", Pages.RECORD_ACTIVE)


class StateRecordReview(State):
    def enter(self):
        State.manager.route_call("gui_manager", "menu.set_unlock_index", 7)
        State.manager.route_call("gui_manager", "menu.set_btn_active",
            ButtonsMenu.RECORD.value, lock_rest = True)
        State.manager.route_call("gui_manager", "view_page", Pages.RECORD_REVIEW)

    def leave(self):
        State.manager.route_call("recorder_manager", "disable_decklink_input")
        State.manager.route_call("gui_manager", "close_browser")
        State.manager.route_call("gui_manager", "leave_page", Pages.RECORD_REVIEW)


class StateEnd(State):
    def enter(self):
        State.manager.route_call("gui_manager", "menu.set_btn_active",
                                 ButtonsMenu.END.value)
        State.manager.route_call("gui_manager", "view_page", Pages.END)
        State.manager.route_call("cloud_manager", "is_internet_available")

    def leave(self):
        State.manager.route_call("gui_manager", "leave_page", Pages.END)


class StateShutdown(State):
    def enter(self):
        # Quit PowerPoint
        State.manager.route_call("presentation_manager", "quit_presentation_app")

        # Stop OBS Websocket server
        State.manager.route_call("recorder_manager", "disconnect")

        # Stop StreamDeck Websocket server
        State.manager.route_call("streamdeck_manager", "stop_server")

        # Initiate shutdown
        State.manager.route_call("system_manager", "start_auto_shutdown")

    def leave(self):
        pass
