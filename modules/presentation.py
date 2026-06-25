# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

"""
This module manages all things related to presentations.

It handles opening files, starting slide shows and navigating slides.

As of now, it's hardwired to be used in conjunction with Microsoft PowerPoint
on Windows through the win32 COM interface.
"""

import logging
from modules.backends.presentation import Action
from modules.backends.presentation.powerpoint import PowerPointApp
from os.path import join

logger = logging.getLogger(__name__)

APP_CLASSES = {
    "powerpoint": PowerPointApp
}


class PresentationManager:
    enabled = True
    managers: dict = {}

    def __init__(self, root_window, config, assets_dir):
        logger.info("PresentationManager : init")

        try:
            app_class = APP_CLASSES[config.app_name.lower()]
        except KeyError:
            raise ValueError(
                "PresentationManager : unknown presentations app: "
                f"{config.app_name}"
            )

        self._app = app_class(self, assets_dir)
        self.presentation_name = "none"
        self.root_window = root_window
        self.teleprompter_x = self._pixels_to_points(config.teleprompter_x)
        self.teleprompter_y = self._pixels_to_points(config.teleprompter_y)
        
        if not config.enable:
            PresentationManager.enabled = False

    # =============================
    # Post-UI-initialization setup
    # =============================
    def on_gui_loaded(self):
        if PresentationManager.enabled:
            self._app.queue_task(self._app.task, Action.START_SLIDESHOW)
        else:
            logger.info("PresentationManager : module not enabled")

    # =============================
    # Private methods
    # =============================
    def _pixels_to_points(self, px, dpi=96):
        return px * 72.0 / dpi

    # =============================
    # Other public methods
    # =============================
    # Important to know is that
    # PowerPoint can only be called
    # from the same thread that
    # initiated it.
    def open_presentation(self, name):
        if PresentationManager.enabled:
            self.presentation_name = name
            self._app.queue_task(self._app.task, Action.OPEN_PRESENTATION, name)
            
    def pp_next(self):
        if PresentationManager.enabled:
            self._app.queue_task(self._app.task, Action.SLIDE_NEXT)

    def pp_prev(self):
        if PresentationManager.enabled:
            self._app.queue_task(self._app.task, Action.SLIDE_PREV)

    def pp_rewind(self):
        if PresentationManager.enabled:
            self._app.queue_task(self._app.task, Action.SLIDE_ONE)

    def quit_presentation_app(self):
        if PresentationManager.enabled:
            self._app.stop_thread()

    def set_presenter_view(self, view):
        logger.info('PresentationManager : set_presenter_view : ' + str(view))
        self._app.show_presenter_view = view
        self.open_presentation(self.presentation_name)
        
    # =============================
    # Outbound communication
    # =============================
    def route_call(self, manager, method, *args, **kwargs):
        gui_manager = PresentationManager.managers["gui_manager"]

        match (manager, method):      
            case ("gui_manager", "show_error"):
                gui_manager.call_on_ui_thread(method, *args, **kwargs)

