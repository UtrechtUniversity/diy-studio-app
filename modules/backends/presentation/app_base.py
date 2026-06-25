# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

import logging
import queue
import threading
from . import Action
from os.path import join
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from modules.presentation import PresentationManager

logger = logging.getLogger(__name__)


class PresentationApp():
    def __init__(self, manager: "PresentationManager", assets_dir):
        self._STOP = object()
        self._app = None
        self._default_presentation_path = assets_dir
        self._presentation = None
        self._start_app_attemps = 0
        self._force_open = False
        self._file_to_open = ""
        self._file_currently_open = "DEFAULT"
        self._manager = manager
        self._presenter_view_upon_opening = False
        self._queue = queue.Queue()
        self._thread = threading.Thread(
            name="PresentationApp", target=self._process_task
        )
        self.show_presenter_view = False

        self._thread.start()

    def _process_task(self):
        raise NotImplementedError

    def queue_task(self, func, *args, **kwargs):
        raise NotImplementedError

    def quit(self):
        raise NotImplementedError

    def resolve_path(self, presentation):
        if presentation == "DEFAULT":
            path = join(
                self._default_presentation_path, "default_presentation.pptx"
            )
        else:
            path = presentation
        return path

    def stop_thread(self):
        self._queue.put((self._STOP, (), {}))
        self._thread.join(timeout=5)

    def task(self, action, _file_to_open=None):
        self._file_to_open = _file_to_open

        if not self._app:
            # Initialize app

            # We don't have a _file_to_open value if
            # action was set to "START_SLIDESHOW"
            if action == Action.START_SLIDESHOW:
                # We need to open a presentation, so we'll override this
                # value, because "open" will also trigger
                # "START_SLIDESHOW" again
                action = Action.OPEN_PRESENTATION

                # Select previously opened presentation
                self._file_to_open = self._file_currently_open

            # The "open" action will not do anything if
            # _file_to_open is equal to _file_currently_open
            # and _presenter_view_upon_opening is also equal to
            # show_presenter_view, so we need to force
            # it to re-open the presentation
            self._force_open = True

        logger.info(
            f"PresentationApp : running task {action} (from thread "
            f"{threading.current_thread().name})")

        match action:
            case Action.OPEN_PRESENTATION:
                pass
            case Action.START_SLIDESHOW:
                pass
            case Action.SLIDE_NEXT:
                pass
            case Action.SLIDE_ONE:
                pass
            case Action.SLIDE_PREV:
                pass
