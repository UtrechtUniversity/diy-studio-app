# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

import logging
import threading
from modules.states import (
    Action,
    State,
    StateTutorial,
    StateLogin1,
    StateLogin2,
    StateVideotype1,
    StateVideotype2,
    StatePowerpoint,
    StateCalibration1,
    StateCalibration2,
    StateCalibrationHelp,
    StateControls1,
    StateControls2,
    StateControls3,
    StateRecordOverview,
    StateRecordActive,
    StateRecordReview,
    StateEnd,
    StateShutdown
)
from modules.gui import Navigate
from collections import deque

logger = logging.getLogger(__name__)


class StateManager:
    """Switches states and as a result switches pages in the GUI.
    
    Every state corresponds to a Page, but StateManager also handles
    non-GUI tasks that need to be performed when switching pages.
    """
    managers: dict = {}
    
    def __init__(self):
        self.action = Action.IDLE
        self.event_queue = deque([])
        self.prev = None
        self.state = None
        self.state_login1 = StateLogin1()
        self.state_login2 = StateLogin2()
        self.state_tutorial = StateTutorial()
        self.state_videotype_1 = StateVideotype1()
        self.state_videotype_2 = StateVideotype2()
        self.state_powerpoint = StatePowerpoint()
        self.state_calibration_1 = StateCalibration1()
        self.state_calibration_2 = StateCalibration2()
        self.state_calibration_help = StateCalibrationHelp() 
        self.state_controls_1 = StateControls1()
        self.state_controls_2 = StateControls2()
        self.state_controls_3 = StateControls3()
        self.state_record_overview = StateRecordOverview()
        self.state_record_active = StateRecordActive()
        self.state_record_review = StateRecordReview()
        self.state_end = StateEnd()
        self.state_shutdown = StateShutdown()
        self.starting_state = self.state_login1
        
        State.manager = self

    # =============================
    # Public methods
    # =============================
    def on_gui_loaded(self):
        # Set first state (called by GuiManager)
        StateManager.managers["cloud_manager"].setup()
        self.change_state(self.starting_state)

    def change_state(self, newstate: State):
        """Change state and lock this process using Action.TRANSITIONING
        
        State changes need to happen on MainThread, as we don't want
        GUI-calls in enter() and leave() functions to be scheduled and
        processed after the state change has already ended - as a new
        state change might happen immediately while not all function
        calls of the previous one had finished.
        """
        if threading.current_thread() is not threading.main_thread():
            # Schedule it on MainThread via GuiManager
            self.route_call(
                "gui_manager", "queue_task", lambda: self.change_state(newstate)
            )
            return

        if newstate != self.state and self.action == Action.IDLE:
            old = self.state.__class__.__name__ if self.state else "None"
            new = newstate.__class__.__name__
            logger.info(
                f"StateManager : changing state : {old} -> {new}"
            )

            self.action = Action.TRANSITIONING
            
            try:
                if self.state:
                    self.state.leave()

                self.prev = self.state
                self.state = newstate
                self.state.enter()
            except Exception:
                logger.exception(
                    "StateManager : exception during state transition"
                )
            finally:
                self.action = Action.IDLE
            return

        if newstate != self.state and self.action == Action.TRANSITIONING:
            logger.critical("StateManager : blocking state change "
                             "because action = Action.TRANSITIONING")
            return

    def get_state(self):
        return self.state
    
    def get_state_str(self):
        # Return state as string
        return self.state.__class__.__name__
  
    def goto(self, whereto):
        match (whereto, self.state):
            case (Navigate.HOME, _):
                self.change_state(self.state_login1)
                
            case (Navigate.NEXT, StateLogin1()):
                self.change_state(self.state_login2)
                
            case (Navigate.NEXT, StateLogin2()):
                self.change_state(self.state_tutorial)
                
            case (Navigate.NEXT, StateTutorial()):
                self.change_state(self.state_videotype_1)
        
            case (Navigate.NEXT, StateVideotype1()):
                self.change_state(self.state_powerpoint)
        
            case (Navigate.NEXT, StateVideotype2()):
                self.change_state(self.state_powerpoint)

            case (Navigate.NEXT, StatePowerpoint()):
                self.change_state(self.state_calibration_1)

            case (Navigate.NEXT, StateCalibration1()):
                self.change_state(self.state_calibration_2)

            case (Navigate.NEXT, StateCalibration2()):
                self.change_state(self.state_controls_1)

            case (Navigate.NEXT, StateControls1()):
                self.change_state(self.state_controls_2)

            case (Navigate.NEXT, StateControls2()):
                self.change_state(self.state_controls_3)

            case (Navigate.NEXT, StateControls3()):
                self.change_state(self.state_record_overview)

            case (Navigate.NEXT, StateRecordOverview()):
                self.change_state(self.state_record_active)

            case (Navigate.NEXT, StateRecordActive()):
                self.change_state(self.state_record_review)

            case (Navigate.NEXT, StateRecordReview()):
                self.change_state(self.state_end)

            # PREV
            case (Navigate.PREV, StateLogin2()):
                self.change_state(self.state_login1)
                
            case (Navigate.PREV, StateTutorial()):
                self.change_state(self.state_login1)

            case (Navigate.PREV, StateVideotype1()):
                self.change_state(self.state_tutorial)

            case (Navigate.PREV, StateVideotype2()):
                self.change_state(self.state_videotype_1)

            case (Navigate.PREV, StatePowerpoint()):
                self.change_state(self.state_videotype_1)

            case (Navigate.PREV, StateCalibration1()):
                self.change_state(self.state_powerpoint)

            case (Navigate.PREV, StateCalibration2()):
                self.change_state(self.state_calibration_1)

            case (Navigate.PREV, StateControls1()):
                self.change_state(self.state_calibration_1)

            case (Navigate.PREV, StateControls2()):
                self.change_state(self.state_controls_1)

            case (Navigate.PREV, StateControls3()):
                self.change_state(self.state_controls_2)

            case (Navigate.PREV, StateRecordOverview()):
                self.change_state(self.state_controls_1)

            case (Navigate.PREV, StateRecordActive()):
                self.change_state(self.state_record_overview)

            case (Navigate.PREV, StateRecordReview()):
                self.change_state(self.state_record_overview)

            case (Navigate.PREV, StateEnd()):
                self.change_state(self.state_record_overview)
   
    def set_action(self, action: Action):
        self.action = action

    # =============================
    # Outbound communication
    # =============================
    def route_call(self, manager, method, *args, **kwargs):
        audio_manager = StateManager.managers.get("audio_manager")
        streamdeck_manager = StateManager.managers.get("streamdeck_manager")
        cloud_manager = StateManager.managers.get("cloud_manager")
        presentation_manager = StateManager.managers.get("presentation_manager")
        recorder_manager = StateManager.managers.get("recorder_manager") 
        system_manager = StateManager.managers.get("system_manager")
        gui_manager = StateManager.managers.get("gui_manager")

        if not audio_manager:
            logger.error("StateManager : audio_manager not registered")
            return
        
        if not streamdeck_manager:
            logger.error("StateManager : streamdeck_manager not registered")
            return
        
        if not cloud_manager:
            logger.error("StateManager : cloud_manager not registered")
            return
        
        if not presentation_manager:
            logger.error("StateManager : presentation_manager not registered")
            return
        
        if not recorder_manager:
            logger.error("StateManager : recorder_manager not registered")
            return
        
        if not system_manager:
            logger.error("StateManager : system_manager not registered")
            return

        if not gui_manager:
            logger.error("StateManager : gui_manager not registered")
            return

        match (manager, method):
            case ("audio_manager", "start_mic_check"):
                audio_manager.start_mic_check()

            case ("audio_manager", "stop_mic_check"):
                audio_manager.stop_mic_check()

            case ("streamdeck_manager", "stop_server"):
                streamdeck_manager.stop_server()
                
            case ("cloud_manager", "is_internet_available"):
                cloud_manager.is_internet_available()

            case ("cloud_manager", "set_dir_id"):
                cloud_manager.set_dir_id(args[0])
                
            case ("cloud_manager", "set_action"):
                cloud_manager.set_action(args[0])
            
            case ("presentation_manager", "quit_presentation_app"):
                presentation_manager.quit_presentation_app()

            case ("recorder_manager", "disconnect"):
                recorder_manager.disconnect()

            case("recorder_manager", "disable_decklink_input"):
                recorder_manager.disable_decklink_input()

            case("recorder_manager", "enable_decklink_input"):
                recorder_manager.enable_decklink_input()

            case ("recorder_manager", "open_projector"):
                recorder_manager.open_projector(kwargs)
                
            case ("recorder_manager", "set_action"):
                recorder_manager.set_action(args[0])
                
            case ("recorder_manager", "switch_scenes"):
                recorder_manager.switch_scenes(
                    *args, **kwargs
                )
                
            case ("recorder_manager", "switch_scene_to_videotype"):
                recorder_manager.switch_scene_to_videotype()
                
            case ("system_manager", "start_auto_shutdown"):
                system_manager.start_auto_shutdown()

            case ("gui_manager", "close_browser"):
                gui_manager.call_on_ui_thread(method)
                
            case ("gui_manager", "close_obs_projector"):
                gui_manager.call_on_ui_thread(method, **kwargs)
                
            case ("gui_manager", "display_tutorial_video"):
                gui_manager.call_on_ui_thread(method)

            case ("gui_manager", "hide_streamdeck_windows"):
                gui_manager.call_on_ui_thread(method)
                
            case ("gui_manager", "leave_page"):
                gui_manager.call_on_ui_thread(method, args[0])
                
            case ("gui_manager", "menu.set_btn_active"):
                gui_manager.call_on_ui_thread(method, *args, **kwargs)
                
            case ("gui_manager", "menu.set_unlock_index"):
                gui_manager.call_on_ui_thread(method, args[0])
                
            case ("gui_manager", "stop_checking_uploads"):
                gui_manager.call_on_ui_thread(method)

            case ("gui_manager", "view_page"):
                gui_manager.call_on_ui_thread(method, args[0])

            case ("gui_manager", "queue_task"):
                gui_manager.queue_task(*args, **kwargs)
