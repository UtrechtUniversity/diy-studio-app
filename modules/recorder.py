# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

"""
Module for interacting with recording software

When recording, RecorderManager goes through a series of Actions via
RecorderManager.set_action().

START RECORDING
===============
User presses the Record button on the Stream Deck:
* RecorderManager.pre_rec_check() verifies if we're allowed to record and if
  so, state is changed to StateRecordActive. This triggers:
                                                -> Action.STARTING_COUNTDOWN
                            -> when timer ends  -> Action.REQUESTING_RECORDING
* We either receive a recording event from OBS  -> Action.RECORDING
* ...or we hit a timeout                        -> Action.FINISHED

STOP RECORDING
==============
User presses the Stop button on the Stream Deck:
*          StreamDeckManager._receive_from_sd() -> Action.REQUESTING_OUTRO
                     -> obs.request_outro()
* We receive a scene change event from OBS      -> Action.RECORDING_OUTRO
    -> 4 second timer                           -> Action.REQUESTING_STOP
* ...or we hit a timeout                        -> Action.REQUESTING_STOP
* We either receive a stop event from OBS       -> Action.FINISHING
                                                -> Action.STARTING_USER_REVIEW
                                                -> Action.CREATING_UPLOAD_JOB
                                                -> Action.FINISHED
* ...or we hit a timeout                        -> Action.FINISHED
"""

import logging
import os
import shutil
import subprocess
import threading
from functools import partial
from modules.backends.recorder import Action
from modules.backends.recorder.obs import ObsRecorder

logger = logging.getLogger(__name__)

RECORDER_CLASSES = {
    "obs": ObsRecorder
}


class RecorderManager:
    managers: dict = {}

    def __init__(self, config, paths):
        logger.info("RecorderManager : init")

        try:
            self.recorder_class = RECORDER_CLASSES[config.app.lower()]
        except KeyError:
            raise ValueError(
                "RecorderManager : unknown recorder: "
                f"{config.app}"
            )

        self._timeout_gen = {}
        self.action = None
        self.connect_lock = threading.Lock()
        self.ffmpeg_path = paths.ffmpeg_path
        self.language = "nl"
        self.mp4file = ""
        self.projector_enabled = config.enable_projector
        self.projector_monitor = config.projector_monitor
        self.rec_dir_good = os.path.join(paths.record_dir, "good")
        self.rec_dir_temp = os.path.join(paths.record_dir, "temp")
        self.rec_dir_bad = os.path.join(paths.record_dir, "bad")
        self.recorder = self.recorder_class(manager=self, config=config)
        self.reached_status = set()
        self.skip_remux = True # When True, input needs to be .mp4
        self.static_bg_index = 0
        self.timeout_ids = {}
        self.toggle_decklink = True
        self.videopath = ""
        self.videotype_index = 0

    # =============================
    # Internal methods
    # =============================
    def _filecheck(self):
        """Checks if file exists and size is larger than 1000 bytes"""
        logger.info(f"RecorderManager : filesize check : {self.videopath}")

        if os.path.exists(self.videopath):
            this_size = os.path.getsize(self.videopath)
            if this_size > 1000:
                self.route_call("gui_manager", "stats_update_size", this_size)
                logger.info("RecorderManager : filesize check : success")
            else:
                logger.error("RecorderManager : filesize check : failed")
                # Need to show error
            self.start_remux()
            self.set_action(Action.STARTING_USER_REVIEW)
        else:
            self.route_call("gui_manager", "show_error", 302)
            self.set_action(Action.FINISHED)

    def _on_receive_timer_id(self, expected_status, gen, after_id):
        if after_id is None:
            return

        if self._timeout_gen.get(expected_status) != gen:
            # Received id for older timer, cancel
            self.route_call("gui_manager", "cancel_task_threadsafe", after_id)
            return

        self.timeout_ids[expected_status] = after_id

    def _set_action_timeout(self, error_type, reboot_btn,
                            timeout, expected_status):
        """Display error when certain states stay active for too long"""
        # Increase generation
        gen = self._timeout_gen.get(expected_status, 0) + 1
        self._timeout_gen[expected_status] = gen

        if expected_status in self.reached_status:
            # Clean-up entry in reached_status;
            # we need to reach it again
            logger.info("RecorderManager : removing " + str(expected_status))
            self.reached_status.remove(expected_status)

        old_id = self.timeout_ids.get(expected_status)
        if old_id is not None:
            self.route_call("gui_manager", "cancel_task_threadsafe", old_id)
            self.timeout_ids.pop(expected_status, None)

        def _on_timeout_gen_check():
            if self._timeout_gen.get(expected_status) != gen:
                return
            self.on_timeout(expected_status, error_type, reboot_btn)

        # Schedule the timeout via GuiManager's schedule_task
        self.route_call(
            "gui_manager",
            "schedule_task_threadsafe",
            timeout,
            _on_timeout_gen_check,
            on_id=partial(self._on_receive_timer_id, expected_status, gen)
        )

    # =============================
    # Public methods
    # =============================
    def on_force_stop_recording(self, output_path):
        self.videopath = output_path

        # Remux will create self.mp4file from self.videopath
        self.start_remux()

        # Move file to /good
        src = output_path
        dest = os.path.join(self.rec_dir_good, self.mp4file)

        try:
            shutil.move(src, dest)
            logger.info("RecorderManager : moved file to 'good' folder")
        except Exception as e:
            logger.error(
                f"RecorderManager : Moving file to 'good' folder failed: {e}"
            )

        self.route_call(
            "cloud_manager", "start_upload", self.mp4file
        )

    def on_timeout(self, expected_status, error_type, reboot_btn):
        if expected_status not in self.reached_status:
            # Display error popup
            self.route_call("gui_manager", "show_error", error_type, reboot_btn)

            if (
                self.action == Action.REQUESTING_RECORDING
                or self.action == Action.REQUESTING_STOP
            ):
                # Go back to record_overview
                self.set_action(Action.FINISHED)
            elif self.action == Action.REQUESTING_OUTRO:
                # If request for the outro failed, stop the recording,
                # because the user has pressed the stop button
                self.set_action(Action.REQUESTING_STOP)

    def set_language(self, lan):
        if self.recorder:
            self.language = lan
            self.recorder.set_language(lan)

    def set_action(self, s):
        if self.action == s:
            # No need to set same action twice
            return

        logger.info("RecorderManager : set_action : " + str(s))

        self.action = s

        # For timed errors
        self.reached_status.add(self.action)

        match self.action:
            case Action.IDLE:
                logger.info("RecorderManager : idle")
                self.route_call(
                    "gui_manager",
                    "update_debug_text",
                    0, True
                )

            case Action.CONNECTING:
                self.route_call(
                    "gui_manager",
                    "update_debug_text",
                    0, False
                )
                self._set_action_timeout(
                    208, False, 10000, Action.IDLE
                )
                if not self.recorder.connected:
                    self.connect()

            case Action.RECONNECTING:
                self._set_action_timeout(
                    208, False, 10000, Action.IDLE
                )

            case Action.DISCONNECTING:
                self.recorder.disconnect()
                self.set_action(Action.IDLE)

            case Action.STARTING_COUNTDOWN:
                self.route_call("gui_manager", "start_countdown")
                self.route_call(
                    "gui_manager",
                    "log_record_activity",
                    "Showing countdown")
                self.recorder.ensure_no_active_recordings()

            case Action.REQUESTING_RECORDING:
                self.route_call(
                    "gui_manager",
                    "log_record_activity",
                    "Recording requested"
                )

                self._set_action_timeout(
                    205, True, 10000, Action.RECORDING
                )

                self.recorder.request_record()

            case Action.RECORDING:
                self.route_call("gui_manager", "on_start_recording")
                self.route_call("gui_manager", "log_record_activity", "Recording..")
                self.route_call("gui_manager", "set_unlock_stop", True)
                self.route_call("streamdeck_manager", "on_recording_started")

            case Action.REQUESTING_OUTRO:
                self.route_call(
                    "gui_manager",
                    "log_record_activity",
                    "User pressed stop, requesting outro"
                )
                self.route_call("gui_manager", "set_unlock_stop", False)

                self._set_action_timeout(
                    207, True, 10000, Action.RECORDING_OUTRO
                )

                self.recorder.request_outro()

            case Action.RECORDING_OUTRO:
                self.route_call("gui_manager", "on_start_processing")
                self.route_call(
                    "gui_manager",
                    "log_record_activity",
                    "Recording outro.."
                )

                self.recorder.start_outro_timer()

            case Action.REQUESTING_STOP:
                self.route_call(
                    "gui_manager",
                    "log_record_activity",
                    "Stop requested"
                )
                self._set_action_timeout(
                    206, True, 10000, Action.FINISHING
                )
                self.recorder.request_stop()

            case Action.FINISHING:
                self.route_call("gui_manager", "log_record_activity", "Finishing..")
                self._filecheck()

            case Action.STARTING_USER_REVIEW:
                self.route_call(
                    "gui_manager",
                    "log_record_activity",
                    "Go to user review"
                )

                self.route_call(
                    "gui_manager",
                    "play_latest_recording",
                    os.path.join(self.rec_dir_temp, self.mp4file)
                )

                self.route_call(
                    "state_manager",
                    "change_state",
                    "state_record_review"
                )

            case Action.CREATING_UPLOAD_JOB:
                self.route_call("cloud_manager", "start_upload", self.mp4file)
                self.set_action(Action.FINISHED)

            case Action.FINISHED:
                self.route_call("gui_manager", "log_record_activity", "Finished")
                self.route_call(
                    "state_manager",
                    "change_state",
                    "state_record_overview"
                )

    def connect(self):
        if not self.connect_lock.acquire(blocking=False):
            return

        self.recorder.connect()

    def disconnect(self):
        self.set_action(Action.DISCONNECTING)

    def disable_decklink_input(self):
        if self.toggle_decklink:
            self.recorder.toggle_decklink(False)

    def enable_decklink_input(self):
        if self.toggle_decklink:
            self.recorder.toggle_decklink(True)

    def reconnect(self):
        if not self.recorder.connected:
            self.recorder.connect()

    def pre_rec_check(self):
        # Check if there's enough disk space to record
        # This call displays an error message upon failure
        passed_diskspace_check = self.route_call(
            "system_manager", "check_available_hdd_space"
        )

        # Check if we're connected to a recorder
        passed_recorder_check = self.recorder.connected
        if not passed_recorder_check:
            self.route_call("gui_manager", "show_error", 208)

        # Check if we're authenticated with a cloud storage provider
        passed_auth_check = self.route_call("cloud_manager", "is_authenticated")
        if not passed_auth_check:
            self.route_call("gui_manager", "show_error", 404)

        # Check if there's an active internet connection
        passed_internet_check = self.route_call(
            "cloud_manager", "is_internet_available"
        )

        if (
            passed_diskspace_check
            and passed_recorder_check
            and passed_auth_check
            and passed_internet_check
        ):
            return True
        else:
            return False

    def stop_record(self):
        self.set_action(Action.REQUESTING_OUTRO)

    def start_remux(self):
        """Remux a MKV file to an MP4 file"""
        logger.info("RecorderManager : remux : start")

        self.mp4file = os.path.basename(self.videopath)[:-3] + "mp4"
        destination = os.path.join(self.rec_dir_temp, self.mp4file)

        if self.skip_remux:
            # In case we're recording directly to the new hybrid mp4 codec:
            logger.info("RecorderManager : skipping remux")

            self.route_call(
                "system_manager",
                "backup_file",
                self.mp4file
            )

            return

        commands = [
            self.ffmpeg_path,
            "-i",
            self.videopath,
            "-c",
            "copy",
            destination
        ]

        if subprocess.run(commands,
                          stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL).returncode == 0:

            logger.info("RecorderManager : remux : success")

            self.route_call(
                "system_manager",
                "backup_file",
                os.path.basename(self.videopath)
            )

        else:
            logger.info("RecorderManager : remux : fail")
            self.route_call("gui_manager", "show_error", 303)

    def accept_recording(self, name_input):
        old_mp4file = self.mp4file

        if name_input != "default":
            # Custom name chosen
            self.mp4file = name_input + ".mp4"

        # Move file to /good
        src = os.path.join(self.rec_dir_temp, old_mp4file)
        dest = os.path.join(self.rec_dir_good, self.mp4file)

        i = 0
        basename = self.mp4file[:-4]
        while True:
            try:
                if os.path.exists(dest):
                    # File with this name already exists
                    i += 1
                    # Insert number after filename and check again
                    self.mp4file = basename + "-" + str(i) + ".mp4"
                    dest = os.path.join(
                        self.rec_dir_good, self.mp4file
                    )
                else:
                    break
            except Exception:
                logger.exception(
                    "RecorderManager : can't check if file exists. Proceeding."
                )
                break

        try:
            shutil.move(src, dest)
            logger.info("RecorderManager : moved file to 'good' folder")
        except Exception as e:
            logger.error(
                f"RecorderManager : Moving file to 'good' folder failed: {e}"
            )
            self.route_call("gui_manager", "show_error", 306)

        self.set_action(Action.CREATING_UPLOAD_JOB)

    def delete_recording(self):
        # Move file to /bad
        src = os.path.join(self.rec_dir_temp, self.mp4file)
        dest = os.path.join(self.rec_dir_bad, self.mp4file)

        try:
            shutil.move(src, dest)
            logger.info("RecorderManager : moved file to 'bad' folder")
        except Exception as e:
            logger.error(
                f"RecorderManager : Moving file to 'bad' folder failed: {e}"
            )
            self.route_call("gui_manager", "show_error", 306)

        self.route_call("state_manager", "change_state", "state_record_overview")
        self.set_action(Action.IDLE)

    def open_projector(self, preview = False):
        if self.projector_enabled:
            self.recorder.open_projector(preview)

    def set_mode_static_bg(self):
        self.videotype_index = 0
        self.recorder.set_mode_static_bg()
        self.recorder.set_index_static_bg(self.static_bg_index)

    def set_mode_powerpoint(self):
        self.videotype_index = 1
        self.recorder.set_mode_powerpoint()

    def set_index_static_bg(self, index):
        self.static_bg_index = index
        self.recorder.set_index_static_bg(self.static_bg_index)

    def switch_scenes(self, preview_scene = None, program_scene = None):
        self.recorder.switch_scenes(preview_scene, program_scene)

    def switch_scene_to_videotype(self):
        match self.videotype_index:
            case 0:
                # This sets the chosen background as scene for
                # the Preview monitor
                self.recorder.set_index_static_bg(self.static_bg_index)
                # This sets the scene for the Program monitor
                self.recorder.switch_scenes(program_scene="Record-StaticBG")
            case 1:
                self.recorder.switch_scenes(program_scene="Record-PP")

    # =============================
    # Outbound communication
    # =============================
    def route_call(self, manager, method, *args, **kwargs):
        streamdeck_manager = RecorderManager.managers.get("streamdeck_manager")
        cloud_manager = RecorderManager.managers.get("cloud_manager")
        state_manager = RecorderManager.managers.get("state_manager")
        system_manager = RecorderManager.managers.get("system_manager")
        gui_manager = RecorderManager.managers.get("gui_manager")

        if not streamdeck_manager:
            logger.error("RecorderManager : streamdeck_manager not registered")
            return

        if not cloud_manager:
            logger.error("RecorderManager : cloud_manager not registered")
            return

        if not state_manager:
            logger.error("RecorderManager : state_manager not registered")
            return

        if not system_manager:
            logger.error("RecorderManager : system_manager not registered")
            return

        if not gui_manager:
            logger.error("RecorderManager : gui_manager not registered")
            return

        match (manager, method):
            case ("streamdeck_manager", "on_recording_started"):
                streamdeck_manager.on_recording_started()

            case ("streamdeck_manager", "on_recording_stopped"):
                streamdeck_manager.on_recording_stopped()

            case ("cloud_manager", "is_authenticated"):
                return cloud_manager.is_authenticated()

            case ("cloud_manager", "is_internet_available"):
                return cloud_manager.is_internet_available()

            case ("cloud_manager", "start_upload"):
                cloud_manager.start_upload(args[0])

            case ("state_manager", "change_state"):
                state = getattr(state_manager, args[0])
                state_manager.change_state(state)

            case ("system_manager", "backup_file"):
                system_manager.backup_file(args[0])

            case ("system_manager", "check_available_hdd_space"):
                return system_manager.check_available_hdd_space()

            case ("gui_manager", "cancel_task_threadsafe"):
                gui_manager.cancel_task_threadsafe(*args, **kwargs)

            case ("gui_manager", "log_record_activity"):
                gui_manager.call_on_ui_thread(method, args[0])

            case ("gui_manager", "on_start_processing"):
                gui_manager.call_on_ui_thread(method)

            case ("gui_manager", "on_start_recording"):
                gui_manager.call_on_ui_thread(method)

            case ("gui_manager", "play_latest_recording"):
                gui_manager.call_on_ui_thread(method, args[0])

            case ("gui_manager", "remove_error"):
                gui_manager.call_on_ui_thread(method, args[0])

            case ("gui_manager", "schedule_task_threadsafe"):
                return gui_manager.schedule_task_threadsafe(*args, **kwargs)

            case ("gui_manager", "set_unlock_stop"):
                gui_manager.call_on_ui_thread(method, args[0])

            case ("gui_manager", "set_videobg"):
                gui_manager.call_on_ui_thread(method, args[0])

            case ("gui_manager", "show_error"):
                gui_manager.call_on_ui_thread(method, *args, **kwargs)

            case ("gui_manager", "start_countdown"):
                gui_manager.call_on_ui_thread(method)

            case("gui_manager", "start_recorder"):
                gui_manager.call_on_ui_thread(method)

            case ("gui_manager", "stats_update_size"):
                gui_manager.call_on_ui_thread(
                    "stats.update", "avg_filesize", args[0]
                )

            case ("gui_manager", "update_debug_text"):
                gui_manager.call_on_ui_thread(method, args[0], args[1])
