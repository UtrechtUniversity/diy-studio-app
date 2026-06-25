# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

import logging
import os
import threading
from . import Action
from dataclasses import dataclass
from enum import Enum
from obswebsocket import obsws, requests, events
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from modules.recorder import RecorderManager


class ObsCommand(Enum):
    """All OBS requests that this app needs and supports.

    The actions are implemented in OBS._translate_request()

    For the full list, see: https://github.com/obsproject/obs-websocket/blob/master/docs/generated/protocol.md#requests
    """
    GET_RECORD_STATUS = "GetRecordStatus"
    GET_SCENE_COLLECTIONS = "GetSceneCollections"
    GET_SCENE_ITEM_ID = "GetSceneItemId"
    OPEN_PROJECTOR = "OpenVideoMixProjector"
    SET_PREVIEW_SCENE = "SetPreviewScene"
    SET_PROFILE = "SetCurrentProfile"
    SET_PROGRAM_SCENE = "SetProgramScene"
    SET_RECORD_DIRECTORY = "SetRecordDirectory"
    SET_SCENE_COLLECTION = "SetCurrentSceneCollection"
    SET_SCENE_ITEM_ENABLED = "SetSceneItemEnabled"
    SET_SOURCE_FILTER = "SetSourceFilter"
    START_RECORD = "StartRecord"
    STOP_RECORD = "StopRecord"


@dataclass(frozen=True)
class ObsRequest:
    name: ObsCommand
    params: dict


@dataclass
class ObsResult:
    status: bool
    data: dict
    error: str | None = None


class ObsRecorder:
    """
    This class communicates with OBS through the obs-websocket-py
    library. It's of utmost importance that obs commands cannot be
    given from the same thread on which obs-websocket-py is running.
    This might happen when an incoming event triggers app logic.
    """

    def __init__(self, manager: "RecorderManager", config):

        self._PROFILE_NAME = config.profile
        self._SCENE_COLLECTION_NAME = config.scene_collection
        self.port = 4455
        self.pwd = config.password
        self.host = config.ip
        self.client = obsws(self.host,
                            self.port,
                            self.pwd,
                            authreconnect=1,
                            on_connect=self._on_connect,
                            on_disconnect=self._on_disconnect)
        self.connected = False
        self.id_decklink_static = 0
        self.id_decklink_pp = 0
        self.id_outro_en = 0
        self.id_outro_nl = 0
        self.manager = manager
        self.thread = None

        self.client.register(self._on_switch,
                             events.CurrentProgramSceneChanged)

        self.client.register(self._on_recording_state_change,
                             events.RecordStateChanged)

        # We're using a timer, because this event does not
        # trigger reliably:
        # self.client.register(self.on_outro_end,
        #                      events.MediaInputPlaybackEnded)

    # =============================
    # Internal methods
    # =============================
    def _check_scene_collection(self):
        scene_col = None
        response = self._safe_call(
            ObsRequest(ObsCommand.GET_SCENE_COLLECTIONS, {})
        )

        if response.data.get("currentSceneCollectionName") is not None:
            scene_col = response.data.get("currentSceneCollectionName")
        else:
            scene_col = "no valid scene collection"

        logger.info(
                "OBS : scene collection received"
                + f" : {scene_col}"
        )

        if (response.data.get("currentSceneCollectionName")
            != self._SCENE_COLLECTION_NAME):
            self.manager.route_call("gui_manager", "show_error", 201)
            self._safe_call(
                ObsRequest(
                    ObsCommand.SET_SCENE_COLLECTION,
                    {"sceneCollection": self._SCENE_COLLECTION_NAME}
                )
            )

    def _on_connect(self, obj):
        self.connected = True

        try:
            self.thread = self.client.thread_recv.ident
            logger.info(f"OBS : running on thread {self.thread}")
        except Exception:
            self.thread = 0

        # We release the connect lock here,
        # because a sudden crash of OBS will not
        # trigger on_disconnect()
        try:
            self.manager.connect_lock.release()
        except RuntimeError:
            pass

        logger.info("OBS : "
                    f"connected to OBS on port {self.port}")

        # If there was a connection error displayed, remove it
        self.manager.route_call("gui_manager", "remove_error", 203)
        self.manager.route_call("gui_manager", "remove_error", 208)

        # Can't continue immediately as it might result in errors
        self.manager.route_call(
            "gui_manager",
            "schedule_task_threadsafe",
            3000,
            self._post_connect_setup
        )

    def _on_disconnect(self, obj):
        self.manager.route_call("gui_manager", "log_record_activity", "Disconnected")
        self.connected = False
        logger.info("OBS : disconnected from OBS.")

        try:
            self.manager.connect_lock.release()
        except RuntimeError:
            pass

        if self.manager.action != Action.DISCONNECTING:
            self.manager.route_call("gui_manager", "show_error", 203, True)
            # Try to restart OBS
            self.manager.route_call("gui_manager", "start_recorder")
            # The obsws module will automatically try to reconnect
            self.manager.set_action(Action.RECONNECTING)

    def _on_event(self, evt):
        logger.info(evt)

    def _on_recording_state_change(self, evt):
        s = evt.datain.get("outputState")

        logger.info(f"OBS : record state changed : {s}")

        match s, self.manager.action:
            case "OBS_WEBSOCKET_OUTPUT_STARTED", Action.REQUESTING_RECORDING:
                self.manager.videopath = evt.datain.get("outputPath")
                self.manager.route_call(
                    "gui_manager",
                    "log_record_activity",
                    "Record confirmed"
                )
                self.manager.set_action(Action.RECORDING)

            case "OBS_WEBSOCKET_OUTPUT_STOPPED", Action.REQUESTING_STOP:
                # Normal stop
                self.manager.route_call(
                    "gui_manager",
                    "log_record_activity",
                    "Stop confirmed"
                )
                self.manager.set_action(Action.FINISHING)
                self.manager.route_call("streamdeck_manager", "on_recording_stopped")

            case "OBS_WEBSOCKET_OUTPUT_STOPPED", status if (
                    status in (Action.RECORDING, Action.RECORDING_OUTRO)
                ):
                # OBS stopped the recording unexpectedly
                logger.error(
                    "RecorderManager : OBS stopped recording unexpectedly"
                )
                self.manager.route_call(
                    "gui_manager",
                    "log_record_activity",
                    "Stop confirmed"
                )
                self.manager.set_action(Action.FINISHING)
                self.manager.route_call("streamdeck_manager", "on_recording_stopped")
                self.manager.route_call("gui_manager", "show_error", 209)

            case "OBS_WEBSOCKET_OUTPUT_STOPPED", Action.STARTING_COUNTDOWN:
                # A previous recording was not stopped when it
                # should have and is instead stopped during countdown
                # to a new recording. We want to silently upload
                # the file. First we need to retrieve the path of the
                # recording.
                logger.warning(
                    "RecorderManager : stopped a still ongoing recording "
                    "during countdown"
                )
                self.manager.on_force_stop_recording(
                    evt.datain.get("outputPath")
                )
                self.manager.route_call("streamdeck_manager", "on_recording_stopped")

            case "OBS_WEBSOCKET_OUTPUT_STOPPED", _:
                self.manager.route_call("streamdeck_manager", "on_recording_stopped")

    def _on_switch(self, evt):
        s = evt.datain.get("sceneName")

        match s, self.manager.action:
            case "Record-Outro", Action.REQUESTING_OUTRO:
                self.manager.route_call(
                    "gui_manager",
                    "log_record_activity",
                    "Scene changed to outro"
                )
                self.manager.set_action(Action.RECORDING_OUTRO)

    def _post_connect_setup(self):
        """Runs after OBS has connected"""
        self._set_profile()
        self._set_record_directory()
        self._check_scene_collection()

        if self.manager.videotype_index == 0:
            self.set_mode_static_bg()
            self.set_index_static_bg(self.manager.static_bg_index)
        else:
            self.set_mode_powerpoint()

        # Retrieve ID's of Decklink sources
        try:
            response = self._safe_call(
                ObsRequest(
                    ObsCommand.GET_SCENE_ITEM_ID,
                    {"scene": "Record-StaticBG", "source": "Decklink"}
                )
            )
            self.id_decklink_static = response.data.get("sceneItemId")
        except Exception:
            logger.warning("OBS : can't get Decklink scene item ID")

        try:
            response = self._safe_call(
                ObsRequest(
                    ObsCommand.GET_SCENE_ITEM_ID,
                    {"scene": "Record-PP", "source": "Decklink"}
                )
            )
            self.id_decklink_pp = response.data.get("sceneItemId")
        except Exception:
            logger.warning("OBS : can't get Decklink scene item ID")

        # Retrieve ID's of Outro sources and set language
        try:
            response = self._safe_call(
                ObsRequest(
                    ObsCommand.GET_SCENE_ITEM_ID,
                    {"scene": "Record-Outro", "source": "Outro-EN"}
                )
            )
            self.id_outro_en = response.data.get("sceneItemId")
        except Exception:
            logger.warning("OBS : can't get Outro-EN scene item ID")

        try:
            response = self._safe_call(
                ObsRequest(
                    ObsCommand.GET_SCENE_ITEM_ID,
                    {"scene": "Record-Outro", "source": "Outro-NL"}
                )
            )
            self.id_outro_nl = response.data.get("sceneItemId")
        except Exception:
            logger.warning("OBS : can't get Outro-NL scene item ID")

        self.set_language(self.manager.language)

        self.manager.set_action(Action.IDLE)

    def _safe_call(self, our_request: ObsRequest) -> ObsResult:
        """This function will check if there is a connection to OBS
        before sending a client.call.

        Always returns an object of type ObsResult with attributes:
        - status: bool
        - data: dict
        - error: str
        """

        if not self.connected:
            logger.warning(
                "Not connected to OBS. Not sending message: "
                f"{our_request.name}"
            )
            return ObsResult(False, {}, "disconnected")

        if threading.get_ident() == self.thread:
            logger.critical(
                "OBS : request made from same thread as "
                f"OBS library : {threading.current_thread().name}. "
                f"Request: {our_request.name}"
            )
            return ObsResult(False, {}, "wrong_thread")

        try:
            lib_request = self._translate_request(our_request)
            resp = self.client.call(lib_request)
            ok = bool(getattr(resp, "status", False))
            datain = getattr(resp, "datain", {}) or {}
            logger.info(
                f"OBS : {our_request.name} : {our_request.params} : "
                f"Result: {ok}")
            return ObsResult(ok, datain, None if ok else "obs_error")
        except ConnectionResetError as e:
            logger.exception("OBS: connection reset. Trying to restart OBS.")
            self.manager.route_call("gui_manager", "start_recorder")
            # Retry _safe_call() instead of returning a false result?
            # Might throw us in a loop though, so we would need a lock
            # as well.
            return ObsResult(False, {}, str(e))
        except Exception as e:
            logger.exception("OBS : couldn't send message to OBS for "
                              "%s", our_request.name)
            return ObsResult(False, {}, str(e))

    def _set_record_directory(self):
        rec_dir = self.manager.rec_dir_temp
        response = self._safe_call(
            ObsRequest(ObsCommand.SET_RECORD_DIRECTORY, {"recDir": rec_dir})
        )

        if response.status:
            logger.info(
                "OBS : record directory set to"
                + f" : {rec_dir}"
            )
        else:
            self.manager.route_call("gui_manager", "show_error", 204, True)

    def _set_profile(self):
        response = self._safe_call(
            ObsRequest(
                ObsCommand.SET_PROFILE, {"profile": self._PROFILE_NAME}
            )
        )

        if response.status:
            logger.info(
                "OBS : profile set to"
                + f" : {self._PROFILE_NAME}"
            )
        else:
            self.manager.route_call("gui_manager", "show_error", 202)

    def _translate_request(self, cmd: ObsRequest):
        """This function will translate our own ObsCommand object
        into the object our obs-websocket library needs as input for
        a websocket call to obs.

        Object "requests" is imported from obswebsocket
        """

        n, p = cmd.name, cmd.params
        match(n):
            case ObsCommand.GET_RECORD_STATUS:
                return requests.GetRecordStatus()
            case ObsCommand.GET_SCENE_COLLECTIONS:
                return requests.GetSceneCollectionList()
            case ObsCommand.GET_SCENE_ITEM_ID:
                return requests.GetSceneItemId(
                    sceneName=p["scene"],
                    sourceName=p["source"]
                )
            case ObsCommand.OPEN_PROJECTOR:
                return requests.OpenVideoMixProjector(
                    videoMixType=p["videoMixType"],
                    monitorIndex=p["monitorIndex"]
                )
            case ObsCommand.SET_PREVIEW_SCENE:
                return requests.SetCurrentPreviewScene(sceneName=p["scene"])
            case ObsCommand.SET_PROFILE:
                return requests.SetCurrentProfile(profileName=p["profile"])
            case ObsCommand.SET_PROGRAM_SCENE:
                return requests.SetCurrentProgramScene(sceneName=p["scene"])
            case ObsCommand.SET_RECORD_DIRECTORY:
                return requests.SetRecordDirectory(recordDirectory=p["recDir"])
            case ObsCommand.SET_SCENE_COLLECTION:
                return requests.SetCurrentSceneCollection(
                    sceneCollectionName=p["sceneCollection"]
                )
            case ObsCommand.SET_SCENE_ITEM_ENABLED:
                return requests.SetSceneItemEnabled(
                    sceneName=p["scene"],
                    sceneItemId=p["sceneItemId"],
                    sceneItemEnabled=p["enabled"]
                )
            case ObsCommand.SET_SOURCE_FILTER:
                return requests.SetSourceFilterEnabled(
                    sourceName=p["source"],
                    filterName=p["filter"],
                    filterEnabled=p["enabled"]
                )
            case ObsCommand.START_RECORD:
                return requests.StartRecord()
            case ObsCommand.STOP_RECORD:
                return requests.StopRecord()

        raise ValueError(f"Unsupported OBS command: {n}")

    # =============================
    # Public methods
    # =============================
    def connect(self):
        self.client.connect()

    def disconnect(self):
        self.client.disconnect()

    def toggle_decklink(self, toggle):
        if toggle:
            logger.info(
                "OBS : enabling Decklink source from "
                f"{threading.current_thread().name}"
            )
            self._safe_call(
                ObsRequest(
                    ObsCommand.SET_SCENE_ITEM_ENABLED,
                    {
                        "sceneItemId": self.id_decklink_static,
                        "scene": "Record-StaticBG",
                        "enabled": True
                    }
                )
            )
            self._safe_call(
                ObsRequest(
                    ObsCommand.SET_SCENE_ITEM_ENABLED,
                    {
                        "sceneItemId": self.id_decklink_pp,
                        "scene": "Record-PP",
                        "enabled": True
                    }
                )
            )

        else:
            logger.info(
                "OBS : disabling Decklink source from "
                f"{threading.current_thread().name}"
            )
            self._safe_call(
                ObsRequest(
                    ObsCommand.SET_SCENE_ITEM_ENABLED,
                    {
                        "sceneItemId": self.id_decklink_static,
                        "scene": "Record-StaticBG",
                        "enabled": False
                    }
                )
            )
            self._safe_call(
                ObsRequest(
                    ObsCommand.SET_SCENE_ITEM_ENABLED,
                    {
                        "sceneItemId": self.id_decklink_pp,
                        "scene": "Record-PP",
                        "enabled": False
                    }
                )
            )

    def request_record(self):
        self._safe_call(ObsRequest(ObsCommand.START_RECORD, {}))

    def request_stop(self):
        self._safe_call(ObsRequest(ObsCommand.STOP_RECORD, {}))

    def ensure_no_active_recordings(self):
        """Check if a recording is unexpectedly happening already
        and stop this recording if that's the case."""
        response = self._safe_call(
            ObsRequest(ObsCommand.GET_RECORD_STATUS, {})
        )
        if (
            response.data.get("outputActive")
            or response.data.get("outputPaused")
        ):
            # Stop current recording - file will be uploaded
            # in self._on_recording_state_change()
            self.request_stop()

    def request_outro(self):
        self._safe_call(
            ObsRequest(
                ObsCommand.SET_PROGRAM_SCENE,
                {"scene": "Record-Outro"}
            )
        )

    def open_projector(self, preview):
        if preview:
            self._safe_call(
                ObsRequest(
                    ObsCommand.OPEN_PROJECTOR,
                    {
                        "videoMixType": "OBS_WEBSOCKET_VIDEO_MIX_TYPE_PREVIEW",
                        "monitorIndex": self.manager.projector_monitor
                    }
                )
            )
        else:
            self._safe_call(
                ObsRequest(
                    ObsCommand.OPEN_PROJECTOR,
                    {
                        "videoMixType": "OBS_WEBSOCKET_VIDEO_MIX_TYPE_PROGRAM",
                        "monitorIndex": self.manager.projector_monitor
                    }
                )
            )

    def set_language(self, lan):
        nl_enabled = False
        en_enabled = False

        logger.info(f"OBS : enabling outro for language: {lan}")

        match lan:
            case 'nl':
                nl_enabled = True
            case 'en':
                en_enabled = True

        self._safe_call(
            ObsRequest(
                ObsCommand.SET_SCENE_ITEM_ENABLED,
                {
                    "sceneItemId": self.id_outro_nl,
                    "scene": "Record-Outro",
                    "enabled": nl_enabled
                }
            )
        )
        self._safe_call(
            ObsRequest(
                ObsCommand.SET_SCENE_ITEM_ENABLED,
                {
                    "sceneItemId": self.id_outro_en,
                    "scene": "Record-Outro",
                    "enabled": en_enabled
                }
            )
        )

    def set_mode_powerpoint(self):
        logger.info("OBS : PowerPoint mode: enabling filters in OBS")
        self._safe_call(
            ObsRequest(
                ObsCommand.SET_SOURCE_FILTER,
                {
                    "source": "Decklink",
                    "filter": "ChromaKey",
                    "enabled": True
                }
            )
        )
        self._safe_call(
            ObsRequest(
                ObsCommand.SET_SOURCE_FILTER,
                {
                    "source": "Decklink",
                    "filter": "Crop",
                    "enabled": True
                }
            )
        )
        self._safe_call(
            ObsRequest(
                ObsCommand.SET_SOURCE_FILTER,
                {
                    "source": "Decklink",
                    "filter": "ColorCorrection",
                    "enabled": True
                }
            )
        )
        self._safe_call(
            ObsRequest(
                ObsCommand.SET_PROGRAM_SCENE,
                {"scene": "Record-PP"}
            )
        )

    def set_mode_static_bg(self):
        logger.info("OBS : Static BG mode: disabling filters in OBS")
        self._safe_call(
            ObsRequest(
                ObsCommand.SET_SOURCE_FILTER,
                {
                    "source": "Decklink",
                    "filter": "ChromaKey",
                    "enabled": False
                }
            )
        )
        self._safe_call(
            ObsRequest(
                ObsCommand.SET_SOURCE_FILTER,
                {
                    "source": "Decklink",
                    "filter": "Crop",
                    "enabled": False
                }
            )
        )
        self._safe_call(
            ObsRequest(
                ObsCommand.SET_SOURCE_FILTER,
                {
                    "source": "Decklink",
                    "filter": "ColorCorrection",
                    "enabled": False
                }
            )
        )
        self._safe_call(
            ObsRequest(
                ObsCommand.SET_PROGRAM_SCENE,
                {"scene": "Record-StaticBG"}
            )
        )

    def set_index_static_bg(self, index):
        match index:
            case 0:
                self._safe_call(
                    ObsRequest(
                        ObsCommand.SET_PREVIEW_SCENE,
                        {"scene": "Ultimatte-BG-Blue"}
                    )
                )
            case 1:
                self._safe_call(
                    ObsRequest(
                        ObsCommand.SET_PREVIEW_SCENE,
                        {"scene": "Ultimatte-BG-Cream"}
                    )
                )
            case 2:
                self._safe_call(
                    ObsRequest(
                        ObsCommand.SET_PREVIEW_SCENE,
                        {"scene": "Ultimatte-BG-Green"}
                    )
                )
            case 3:
                self._safe_call(
                    ObsRequest(
                        ObsCommand.SET_PREVIEW_SCENE,
                        {"scene": "Ultimatte-BG-Yellow"}
                    )
                )
            case 4:
                self._safe_call(
                    ObsRequest(
                        ObsCommand.SET_PREVIEW_SCENE,
                        {"scene": "Ultimatte-BG-Photo1"}
                    )
                )
            case 5:
                self._safe_call(
                    ObsRequest(
                        ObsCommand.SET_PREVIEW_SCENE,
                        {"scene": "Ultimatte-BG-Photo2"}
                    )
                )
            case 6:
                self._safe_call(
                    ObsRequest(
                        ObsCommand.SET_PREVIEW_SCENE,
                        {"scene": "Ultimatte-BG-Photo3"}
                    )
                )
            case 7:
                self._safe_call(
                    ObsRequest(
                        ObsCommand.SET_PREVIEW_SCENE,
                        {"scene": "Ultimatte-BG-Photo4"}
                    )
                )

    def switch_scenes(self, preview_scene=None, program_scene=None):
        if preview_scene is not None:
            self._safe_call(
                ObsRequest(
                    ObsCommand.SET_PREVIEW_SCENE,
                    {"scene": preview_scene}
                )
            )

        if program_scene is not None:
            self._safe_call(
                ObsRequest(
                    ObsCommand.SET_PROGRAM_SCENE,
                    {"scene": program_scene}
                )
            )

    def start_outro_timer(self):
        def on_outro_end():
            if self.manager.action == Action.RECORDING_OUTRO:
                logger.info("RecorderManager : outro has ended")
                self.manager.route_call(
                    "gui_manager",
                    "log_record_activity",
                    "Outro completed"
                )
                self.manager.set_action(Action.REQUESTING_STOP)

        self.manager.route_call(
            "gui_manager", "schedule_task_threadsafe", 4000, on_outro_end
        )
