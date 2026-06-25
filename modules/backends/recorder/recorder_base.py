# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from modules.recorder import RecorderManager


class Recorder:
    def __init__(self, manager: "RecorderManager", config):
        self.connected = False
        self.manager = manager

    # =============================
    # Public methods
    # =============================
    def connect(self):
        raise NotImplementedError

    def disconnect(self):
        raise NotImplementedError

    def toggle_decklink(self, toggle):
        raise NotImplementedError

    def request_record(self):
        raise NotImplementedError

    def request_stop(self):
        raise NotImplementedError

    def ensure_no_active_recordings(self):
        raise NotImplementedError

    def request_outro(self):
        raise NotImplementedError

    def open_projector(self, preview):
        raise NotImplementedError

    def set_language(self, lan):
        raise NotImplementedError

    def set_mode_powerpoint(self):
        raise NotImplementedError

    def set_mode_static_bg(self):
        raise NotImplementedError

    def set_index_static_bg(self, index):
        raise NotImplementedError

    def switch_scenes(self, preview_scene=None, program_scene=None):
        raise NotImplementedError

    def start_outro_timer(self):
        raise NotImplementedError
