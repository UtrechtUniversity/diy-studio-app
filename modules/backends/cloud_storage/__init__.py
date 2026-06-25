# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

from enum import Enum


class Action(Enum):
    IDLE = "idle"
    AUTHENTICATING = "authenticating"
    REQUESTING_FOLDER = "requesting folder"
    DOWNLOADING_FILE = "downloading presentation"
