# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

import logging
import pythoncom
import threading
import time
import win32com.client
from . import Action
from modules.backends.presentation.app_base import PresentationApp
from os.path import exists, join
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from modules.presentation import PresentationManager

logger = logging.getLogger(__name__)


class PowerPointApp(PresentationApp):
    def __init__(self, manager: "PresentationManager", assets_dir):
        super().__init__(manager, assets_dir)

    def _process_task(self):
        """Executes tasks that were put in
        the queue on PowerPoint thread"""
        pythoncom.CoInitialize()

        try:
            while True:
                # queue.get() blocks until something is there
                func, args, kwargs = self._queue.get()

                if func is self._STOP:
                    logger.info("PowerPoint : stopping thread")
                    break

                try:

                    func(*args, **kwargs)
                except Exception as e:
                    logger.exception(
                        "PowerPoint : task failed : "
                        f"{func.__name__} : {e}"
                    )
        finally:
            self.quit()
            pythoncom.CoUninitialize()

    def queue_task(self, func, *args, **kwargs):
        """Put a task in the queue to be
        processed on PowerPoint thread"""
        self._queue.put((func, args, kwargs))
        thread_name = threading.current_thread().name
        if thread_name.startswith("Thread"):
            thread_name = "ObsWebsocket"

        task = "unknown"
        if len(args) >= 1 and args[0] is not None:
            task = str(args[0])

        logger.info(
            f"PowerPoint : putting task in queue : {task} "
            f"(from thread: {thread_name})"
        )

    def quit(self):
        try:
            if self._app:
                self._app.Quit()
        except:
            logger.info(
                "PowerPoint : unable to quit PowerPoint. "
                + "Breaking reference instead."
            )
        finally:
            self._app = None

    def resolve_path(self, ppt):
        if ppt == "DEFAULT":
            path = join(self._default_presentation_path, "default_presentation.pptx")
        else:
            path = ppt
        return path

    def stop_thread(self):
        self._queue.put((self._STOP, (), {}))
        self._thread.join(timeout=5)

    def task(self, action, _file_to_open=None):
        self._file_to_open = _file_to_open

        if not self._app:
            # Initialize app
            self._app = win32com.client.Dispatch("PowerPoint.Application")
            logger.info("PowerPoint : initializing PowerPoint")

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
            f"PowerPoint : running task {action} (from thread "
            f"{threading.current_thread().name})")

        match action:
            case Action.OPEN_PRESENTATION:
                # Only open a file if the requested presentation
                # is different from the selected presentation, unless:
                # a) the 'show presenter view' checkbox has been toggled
                # b) we want to force a re-open after re-initialization
                open_ppt = self._force_open

                if self._file_to_open == self._file_currently_open:
                    # This presentation is already open
                    # Only open if the presenter view
                    # toggle has been switched.
                    if self._presenter_view_upon_opening != self.show_presenter_view:
                        open_ppt = True
                else:
                    # The chosen presentation is different
                    # from the one that is supposed to be open
                    open_ppt = True

                if open_ppt:
                    error = False

                    # Can't open a presentation when a slideshow
                    # is running, so let's end any running slideshows
                    try:
                        slideshow_amnt = self._app.SlideShowWindows.Count
                        if slideshow_amnt > 0:
                            for i in range(1, slideshow_amnt + 1):
                                self._app.SlideShowWindows(i).View.Exit()
                                # Give PP a bit of time to stop
                                # the slide show before continuing
                                time.sleep(0.5)
                                logger.info(f"PowerPoint : "
                                             f"stopped slideshow {i}")

                    except Exception as e:
                        logger.warning("PowerPoint : could not close active "
                                        + f"presentations: {e}")
                        error = True

                    if self._file_to_open:
                        path = self.resolve_path(self._file_to_open)
                        if not exists(path):
                            logger.error("PowerPoint : requested file "
                                          + "not found.")
                            return

                    if not error:
                        try:
                            logger.info(f"PowerPoint : opening presentation")
                            self._presentation = self._app.Presentations.Open(
                                FileName=path,
                                ReadOnly=1,
                                WithWindow=0
                            )
                            self._force_open = False
                            self._file_currently_open = self._file_to_open
                            self._presenter_view_upon_opening = self.show_presenter_view

                            # Try to run the slide show
                            self.task(Action.START_SLIDESHOW)

                        except Exception as e:
                            # We may have to show an error to the user
                            # as well. We also need to keep in mind that
                            # the user might have provided a file with
                            # .pptx extension that is not actually a
                            # PowerPoint file! So instead of restarting
                            # PowerPoint and trying again, we might want
                            # to stop here immediately...
                            logger.warning("PowerPoint : error: can't open "
                                         + f"PowerPoint-file: {e}")

                            error = True

                    if error:
                        # Try to quit and restart PowerPoint
                        self._start_app_attemps += 1
                        if self._start_app_attemps < 3:
                            logger.info("PowerPoint : quitting and re-opening ppt")
                            self.quit()
                            time.sleep(5)
                            self.task(Action.OPEN_PRESENTATION, self._file_to_open)
                        else:
                            logger.critical("Can't get PowerPoint to restart."
                                         + " Out of options.")

                            self._manager.route_call(
                                "gui_manager", "show_error", 501
                            )

            case Action.START_SLIDESHOW:
                try:
                    if self._presentation:
                        if self._app.SlideShowWindows.Count > 0:
                            # There's a slideshow already,
                            # we only need it to return to the start
                            self._app.SlideShowWindows(1).View.First()
                            logger.info("PowerPoint : returning to start "
                                        + "of slideshow")
                        else:
                            slideshow = self._presentation.SlideShowSettings
                            slideshow.ShowPresenterView = (
                                self.show_presenter_view
                            )
                            slideshow.ShowWithAnimation = True
                            # We need to loop the slide show or it
                            # will quit when advancing beyond the last
                            # slide - this will trigger a save prompt
                            # which we don't want.
                            slideshow.LoopUntilStopped = True
                            slideshow.Run()
                            self._app.SlideShowWindows(1).View.First()
                            ssw = self._app.ActivePresentation.SlideShowWindow
                            ssw.Left = self._manager.teleprompter_x
                            ssw.Top = self._manager.teleprompter_y
                            logger.info("PowerPoint : starting slideshow")
                            self._start_app_attemps = 0
                    else:
                        logger.info("PowerPoint : no presentation opened")

                except Exception as e:
                    logger.info(f"PowerPoint : error: can't run "
                                 + f"slideshow: {e}")

                    if "RPC server is unavailable" in str(e):
                        logger.info("PowerPoint : RPC server is unavailable. "
                                     + "Attempting to restart PowerPoint.")

                        # Try to quit and restart PowerPoint
                        self._start_app_attemps += 1
                        if self._start_app_attemps < 3:
                            try:
                                self._app.Quit()
                                self._app = None
                            except:
                                logger.info(
                                    "PowerPoint : unable to quit PowerPoint."
                                    + "Breaking reference and"
                                    + "trying to re-initialize"
                                )
                                self._app = None
                            time.sleep(5)
                            self.task(Action.START_SLIDESHOW)
                        else:
                            logger.info(
                                "PowerPoint : "
                                + "can't get PowerPoint to restart."
                                + "Out of options."
                            )

                    else:
                        # Lost Presentation object. Reload presentation.
                        # This will only work if we set
                        # presentation_selected to something else
                        _file_to_open = self._file_currently_open
                        self._file_currently_open = None
                        self.task(Action.OPEN_PRESENTATION, _file_to_open)
                        self._start_app_attemps += 1
                        if self._start_app_attemps < 2:
                            self.task(Action.START_SLIDESHOW)

            case Action.SLIDE_NEXT:
                try:
                    if self._presentation:
                        if self._app.SlideShowWindows.Count > 0:
                            slideshow = self._app.SlideShowWindows(1)
                            # Advance to next slide,
                            # unless it's the last -- we're explicitly
                            # not returning to the first slide at the end,
                            # as a comparison between the current slide index
                            # and the total number of slides might match while
                            # there are still next steps within the last slide
                            # that a user wishes to trigger.
                            # We can also not check for ppSlideShowBlackScreen,
                            # as this might occur in between slides.
                            # Hence the rewind button.
                            logger.info("PowerPoint : advancing to "
                                         "next slide (if possible)")
                            slideshow.View.Next()
                        else:
                            # No slideshow running
                            logger.info("PowerPoint : "
                                         "can't advance to next slide: "
                                         "no slideshow running")
                except Exception as e:
                    logger.warning("PowerPoint : "
                                   f"can't switch to next page: {e}")

            case Action.SLIDE_ONE:
                try:
                    logger.info(f"PowerPoint : "
                                  "returning to slide 1")
                    self._app.SlideShowWindows(1).View.GotoSlide(1)
                except Exception as e:
                    logger.warning("PowerPoint : "
                                   f"can't rewind to first slide: {e}")

            case Action.SLIDE_PREV:
                try:
                    self._app.SlideShowWindows(1).View.Previous()
                except Exception as e:
                    logger.warning("PowerPoint : "
                                   f"can't switch to previous slide: {e}")
