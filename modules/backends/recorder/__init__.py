# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

from enum import Enum


class Action(Enum):
    IDLE = "idle"
    CONNECTING = "connecting"
    RECONNECTING = "reconnecting"
    DISCONNECTING = "disconnecting"
    STARTING_COUNTDOWN = "countdown"
    REQUESTING_RECORDING = "record message sent"
    RECORDING = "recording confirmed"
    REQUESTING_OUTRO = "requested outro scene playback"
    RECORDING_OUTRO = "recording outro"
    REQUESTING_STOP = "stop message sent"
    FINISHING = "stop confirmed, finishing video"
    STARTING_USER_REVIEW = "user review"
    REMUXING = "remuxing"
    CREATING_UPLOAD_JOB = "upload"
    FINISHED = "finished recording"
    ERROR = "error"
