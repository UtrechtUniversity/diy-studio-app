import logging
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from modules.control_panel import ControlPanelManager


class ControlPanel:
    def __init__(self, manager: "ControlPanelManager", config):
        self.connected = False
        self.local_host = config.ip
        self.manager = manager
        self.port = config.port

    def start(self):
        raise NotImplementedError

    def on_recording_started(self):
        raise NotImplementedError

    def on_recording_stopped(self):
        raise NotImplementedError

    def shutdown(self):
        raise NotImplementedError
