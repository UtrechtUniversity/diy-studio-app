# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

import argparse
import csv
import customtkinter as ctk
import json
import logging
import os
import psutil
import pywinctl as window_manager
import queue
import requests
import shutil
import subprocess
import sys
import threading
import traceback
from datetime import datetime, timedelta
from enum import Enum
from typing import ClassVar
from modules.http_session import session
from modules.backends.recorder import Action as RecAction
from modules.gui_pages.base import PageBase
from modules.gui_pages.calibration_1 import PageCalibration1
from modules.gui_pages.calibration_2 import PageCalibration2
from modules.gui_pages.calibration_help import PageCalibrationHelp
from modules.gui_pages.controls_1 import PageControls1
from modules.gui_pages.controls_2 import PageControls2
from modules.gui_pages.controls_3 import PageControls3
from modules.gui_pages.countdown import PageCountdown
from modules.gui_pages.end import PageEnd
from modules.gui_pages.login_1 import PageLogin1
from modules.gui_pages.login_2 import PageLogin2
from modules.gui_pages.menu import PageMenu
from modules.gui_pages.powerpoint import PagePowerPoint
from modules.gui_pages.record_overview import PageRecordOverview
from modules.gui_pages.record_active import PageRecordActive
from modules.gui_pages.record_review import PageRecordReview
from modules.gui_pages.videotype_1 import PageVideotype1
from modules.gui_pages.videotype_2 import PageVideotype2
from modules.gui_pages.tutorial import PageTutorial
from modules.gui_popups.base import PopupBase
from modules.gui_popups.bg import PopupBg
from modules.gui_popups.confirmation import PopupConfirmation
from modules.gui_popups.error import PopupError
from time import time
from modules.ultimatte import Ultimatte

logger = logging.getLogger(__name__)
ctk.set_appearance_mode("system")  # Modes: system, light, dark
ctk.set_default_color_theme("blue")  # Themes: blue, dark-blue, green


class Navigate(Enum):
    NEXT = "next"
    PREV = "prev"
    HELP = "help"
    MAIN = "main"
    HOME = "home"
    UP = "up"
    DOWN = "down"


class Popups(Enum):
    ERROR = "error"
    CONFIRMATION = "confirmation"


class Pages(Enum):
    LOGIN1 = "login1"
    LOGIN2 = "login2"
    TUTORIAL = "tutorial"
    VIDEOTYPE_1 = "videotype_1"
    VIDEOTYPE_2 = "videotype_2"
    POWERPOINT = "powerpoint"
    CALIBRATION_1 = "calibration_1"
    CALIBRATION_2 = "calibration_2"
    CALIBRATION_HELP = "calibratie_help"
    CONTROLS_1 = "controls_1"
    CONTROLS_2 = "controls_2"
    CONTROLS_3 = "controls_3"
    RECORD_OVERVIEW = "record_overview"
    RECORD_ACTIVE = "record_active"
    RECORD_REVIEW = "record_review"
    END = "end"

class GuiManager:
    """
    Manager for all GUI-related tasks.

    As Tkinter is not threadsafe, we need to make sure that any
    external calls to public functions of this class happen through
    GuiManager.call_on_ui_thread(), which in turn will call
    queue_task(). _tick() wil continuously check for events and if
    set, call _process_queue().

    Tldr;
    call_on_ui_thread -> queue_task -> tick -> process_queue

    Pages and popups can use direct calls, as they will always run
    on the GUI-thread.

    For timers and direct scheduling using tkinter's after(),
    schedule_task() and cancel_task() can be used.

    """
    managers: dict = {}

    def __init__(
            self, window, app_version, config, cloud_config, log_filename, paths
        ):
        logger.info('GuiManager : init')

        assets_dir = paths.assets_dir
        logo_filename = config.logo_file_name

        self._last_tick = time()
        self.always_on_top = config.gui_always_on_top
        self.app_version = app_version
        self.app_window = None
        self.browser_name = config.browser_name
        self.browser_path = paths.browser_path
        self.browser_args = config.browser_args
        self.browser_close = config.browser_quit
        self.client_id = cloud_config.client_id
        self.countdown_window = None
        self.countdown_window_x = 0
        self.countdown_window_y = 0
        self.cur_errors = []
        self.debug_components = [False,False,False,False]
        self.email_logs = config.email_logs
        self.gui_rec_buttons_enabled = config.gui_rec_buttons_enabled
        self.gui_thread_id = threading.get_ident()
        self.html_dir = os.path.join(os.getcwd(), "assets", "html")
        self.kb_send_log = config.key_send_log
        self.kb_toggle_greenscreen = config.key_toggle_greenscreen
        self.kb_restart_recorder = config.key_restart_recorder
        self.kb_toggle_debug = config.key_toggle_debug
        self.language = "nl"
        self.last_log_sent: datetime | None = None
        self.log_filename = log_filename
        self.logo_filepath = os.path.join(assets_dir, logo_filename)
        self.logo_height = config.logo_height
        self.logo_width = config.logo_width
        self.queue = queue.Queue()
        self.queue_event = threading.Event()
        self.queue_scheduled = False
        self.recorder_args = config.recorder_args
        self.recorder_path = paths.recorder_path
        self.record_dir = paths.record_dir
        self.stats = SessionStats(
            paths.stats_file_path,
            config.studio_location,
            config.telemetry
            )
        self.teleprompter_x = config.teleprompter_x
        self.teleprompter_y = config.teleprompter_y
        self.tenant_id = cloud_config.tenant_id
        self.tick_active = False
        self.ultimatte = Ultimatte(
            enable=config.ultimatte_enabled,
            host=config.ultimatte_ip,
            port=config.ultimatte_port
        )
        self.videotype = "staticbg"
        self.videobg = 0
        self.webhost = config.webhost_url
        self.window = window
        self.x = config.gui_offset_x
        self.y = config.gui_offset_y

        # Launch browser and hide console
        allTitles = window_manager.getAllTitles()
        browser_window_found = False

        for title in allTitles:
            if self.browser_name in title:
                # Show web browser
                browser_window_found = True
                windows = window_manager.getWindowsWithTitle(title)
                if windows:
                    window = windows[0]
                    window.maximize()
            if title == "python" or title == "DIY Studio App Console":
                # Hide DIY Studio App console window
                windows = window_manager.getWindowsWithTitle(title)
                if windows:
                    window = windows[0]
                    window.minimize()

        if not browser_window_found:
            # Launch web browser
            url = "file://" + os.path.join(self.html_dir, "loading.html")
            self._launch_browser(url)

        # LANGUAGE
        self.dataText = self.load_ext_text()

        # STYLE ALL
        FONT_PRIMARY = "Open Sans"
        FONT_PRIMARY_BOLD = "Open Sans bold"
        FONT_SECONDARY = "Merriweather bold"

        # STYLE COLOR
        COLOR_PRIMARY = config.color_primary
        COLOR_SECONDARY = config.color_secondary
        COLOR_BG_CONTENT = config.color_bg_content
        COLOR_GOOD = config.color_good

        COLORS = {
            "primary": COLOR_PRIMARY,
            "secondary": COLOR_SECONDARY,
            "bg_content": COLOR_BG_CONTENT,
            "good": COLOR_GOOD,
        }

        # STYLE PADDING
        ALL_PADDING_X = 60
        MENU_PADDING_BUTTONS_Y = 45
        MENU_PADDING_BUTTONS_X = 15
        PAGE_PADDING_CONTENT_Y = 145 # also influences placing of frame
        PAGE_PADDING_BUTTONS_Y = 35
        PAGE_PADDING_TITLE_HEIGHT = 120

        PADDING = {
            "all_padding_x": ALL_PADDING_X,
            "menu_padding_buttons_x": MENU_PADDING_BUTTONS_X,
            "menu_padding_buttons_y": MENU_PADDING_BUTTONS_Y,
            "page_padding_content_y": PAGE_PADDING_CONTENT_Y,
            "page_padding_buttons_y": PAGE_PADDING_BUTTONS_Y,
            "page_padding_title_height": PAGE_PADDING_TITLE_HEIGHT
        }

        # STYLE ALL BUTTONS
        BTN_BORDER_COLOR = "black"
        BTN_BORDER_WIDTH = 5

        # STYLE MENU BUTTON
        MENU_BTN_FG_COLOR_NORMAL = config.color_menu_btn_fg_normal
        MENU_BTN_FG_COLOR_ACTIVE = COLOR_SECONDARY
        MENU_BTN_TXT_COLOR_NORMAL = config.color_menu_btn_txt_normal
        MENU_BTN_TXT_COLOR_ACTIVE = config.color_menu_btn_txt_active
        MENU_BTN_TXT_COLOR_LOCKED = config.color_menu_btn_txt_locked

        MENU_BTN_STYLE_NORMAL = {
            "state": ctk.NORMAL,
            "width": 200,
            "height": 60,
            "border_width": 0,
            "border_color": BTN_BORDER_COLOR,
            "corner_radius": 30,
            "fg_color": MENU_BTN_FG_COLOR_NORMAL,
            "text_color": MENU_BTN_TXT_COLOR_NORMAL,
            "font": (FONT_PRIMARY, 22)
        }

        MENU_BTN_STYLE_ACTIVE = {
            "state": ctk.DISABLED,
            "border_width": 0,
            "fg_color": MENU_BTN_FG_COLOR_ACTIVE,
            "text_color_disabled": MENU_BTN_TXT_COLOR_ACTIVE,
        }

        MENU_BTN_STYLE_HOVER = {
            "state": ctk.NORMAL,
            "border_width": BTN_BORDER_WIDTH,
            "fg_color": MENU_BTN_FG_COLOR_NORMAL
        }

        MENU_BTN_STYLE_LOCKED = {
            "state": ctk.DISABLED,
            "border_width": 0,
            "fg_color": MENU_BTN_FG_COLOR_NORMAL,
            "text_color": MENU_BTN_TXT_COLOR_NORMAL,
            "text_color_disabled": MENU_BTN_TXT_COLOR_LOCKED,
        }

        MENU_DEBUG_STYLE = {
            "fg_color":"black",
            "text_color":"white",
            "font":(FONT_PRIMARY, 16),
            "justify":"left"
        }

        # STYLE PAGE BUTTON
        PAGE_BTN_FG_COLOR_NORMAL = config.color_page_btn_fg_normal
        PAGE_BTN_FG_COLOR_LOCKED = config.color_page_btn_fg_locked
        PAGE_BTN_TXT_COLOR_NORMAL = config.color_page_btn_txt_normal
        PAGE_BTN_TXT_COLOR_LOCKED = config.color_page_btn_txt_locked

        PAGE_BTN_STYLE_NORMAL = {
            "state": ctk.NORMAL,
            "width": 370,
            "height": 76,
            "border_width": 0,
            "border_color": BTN_BORDER_COLOR,
            "corner_radius": 38,
            "fg_color": PAGE_BTN_FG_COLOR_NORMAL,
            "text_color": PAGE_BTN_TXT_COLOR_NORMAL,
            "hover_color": PAGE_BTN_FG_COLOR_NORMAL,
            "font": (FONT_PRIMARY, 22)
        }

        PAGE_BTN_STYLE_LOCKED = {
            "state": ctk.DISABLED,
            "border_width": 0,
            "fg_color": PAGE_BTN_FG_COLOR_LOCKED,
            "text_color_disabled": PAGE_BTN_TXT_COLOR_LOCKED,
        }

        PAGE_BTN_STYLE_HOVER = {
            "state": ctk.NORMAL,
            "border_width": BTN_BORDER_WIDTH,
            "hover_color": PAGE_BTN_FG_COLOR_NORMAL,
        }

        # STYLE PAGE TEXT & TITLE
        PAGE_TXT_COLOR = config.color_page_txt_1
        PAGE_TXT_FG_COLOR = config.color_page_txt_2

        PAGE_TXT_STYLE = {
            "fg_color": COLOR_BG_CONTENT,
            "text_color": PAGE_TXT_COLOR,
            "font": (FONT_PRIMARY, 22),
            "justify": "left",
            "compound": "left",
            "anchor": "nw",
        }

        PAGE_TEXTTITLE_STYLE = {
            "fg_color": COLOR_BG_CONTENT,
            "text_color": PAGE_TXT_COLOR,
            "font": (FONT_PRIMARY_BOLD, 23),
            "justify": "left",
            "compound": "left",
            "anchor": "w"
        }

        PAGE_LISTBOX_STYLE = {
            "fg_color": COLOR_BG_CONTENT,
            "text_color": PAGE_TXT_COLOR,
            "font": (FONT_PRIMARY, 22),
            "justify": "left",
        }

        # Used only in record active to show recording/processing state
        PAGE_TXT_BIG_STYLE = {
            "fg_color":COLOR_BG_CONTENT,
            "text_color":PAGE_TXT_COLOR,
            "font":(FONT_PRIMARY, 56),
            "justify":"center"
        }

        PAGE_TITLE_STYLE = {
            "fg_color":PAGE_TXT_FG_COLOR,
            "text_color":PAGE_TXT_COLOR,
            "justify":"center",
            "font":(FONT_SECONDARY, 28)
        }

        # STYLE POPUP TEXT
        POPUP_TXT_STYLE = PAGE_TXT_STYLE.copy()
        POPUP_TXT_STYLE['justify'] = 'left'

        # WINDOW PROPERTIES
        self.window.geometry(f"1920x1080+{self.x}+{self.y}")
        self.window.title("DIY Studio App")
        self.window.resizable(False, False)
        self.window.overrideredirect(True)
        self.window.wm_attributes("-transparentcolor", "red")
        self.window.bind("<Visibility>", self._register_main_window)
        self.window.wm_attributes("-topmost", self.always_on_top)

        # SET MANAGERS
        PageBase.manager = self
        PageCountdown.manager = self
        PageMenu.manager = self
        PopupBase.manager = self
        SessionStats.manager = self

        # MENU
        self.menu = PageMenu(
            self.window,
            (self.language,
            PADDING,
            COLORS,
            MENU_BTN_STYLE_NORMAL,
            MENU_BTN_STYLE_ACTIVE,
            MENU_BTN_STYLE_LOCKED,
            MENU_BTN_STYLE_HOVER,
            MENU_DEBUG_STYLE))
        self.menu.place(x=0, y=0)

        # PAGES
        self.pages = {}
        page_elements = (
            self.language, PADDING, COLORS,
            PAGE_BTN_STYLE_NORMAL,
            PAGE_BTN_STYLE_HOVER,
            PAGE_BTN_STYLE_LOCKED,
            PAGE_TXT_STYLE,
            PAGE_TITLE_STYLE,
            PAGE_TEXTTITLE_STYLE,
            PAGE_LISTBOX_STYLE
        )

        self.pages[Pages.TUTORIAL] = PageTutorial(
            self.window, page_elements)

        self.pages[Pages.LOGIN1] = PageLogin1(
            self.window, page_elements)

        self.pages[Pages.LOGIN2] = PageLogin2(
            self.window, page_elements)

        self.pages[Pages.VIDEOTYPE_1] = PageVideotype1(
            self.window, page_elements)

        self.pages[Pages.VIDEOTYPE_2] = PageVideotype2(
            self.window, page_elements)

        self.pages[Pages.POWERPOINT] = PagePowerPoint(
            self.window, page_elements)

        self.pages[Pages.CALIBRATION_1] = PageCalibration1(
            self.window, page_elements)

        self.pages[Pages.CALIBRATION_2] = PageCalibration2(
            self.window, page_elements)

        self.pages[Pages.CALIBRATION_HELP] = PageCalibrationHelp(
            self.window, page_elements)

        self.pages[Pages.CONTROLS_1] = PageControls1(
            self.window, page_elements)

        self.pages[Pages.CONTROLS_2] = PageControls2(
            self.window, page_elements)

        self.pages[Pages.CONTROLS_3] = PageControls3(
            self.window, page_elements)

        self.pages[Pages.RECORD_OVERVIEW] = PageRecordOverview(
            self.window, page_elements)

        self.pages[Pages.RECORD_ACTIVE] = PageRecordActive(
            self.window, page_elements, PAGE_TXT_BIG_STYLE)

        self.pages[Pages.RECORD_REVIEW] = PageRecordReview(
            self.window, page_elements)

        self.pages[Pages.END] = PageEnd(
            self.window, page_elements,
            self.logo_filepath, self.logo_width, self.logo_height
        )

        for p in Pages:
            # -1 is necessary otherwise it displays a line
            self.pages[p].place(x=0, y=PAGE_PADDING_CONTENT_Y - 1)

        # POPUPS
        self.popup_cur = None
        self.popup_bg = PopupBg(self.window)
        self.popups = {}

        self.popups[Popups.ERROR] = PopupError(
            self.window, page_elements, POPUP_TXT_STYLE)

        self.popups[Popups.CONFIRMATION] = PopupConfirmation(
            self.window, page_elements, POPUP_TXT_STYLE)

        # SHUTDOWN INFO SCREEN
        self.shutdown_frame = ctk.CTkFrame(
            self.window, corner_radius=0,
            width=1920, height=1080,
            fg_color=COLOR_SECONDARY
        )

        self.label_shutdown_header = ctk.CTkLabel(
            self.shutdown_frame,
            text=(self.dataText['pagetext']['black']['title'][self.language]
                  + "\n\n"),
            text_color=PAGE_TXT_FG_COLOR,
            justify="center",
            anchor="center",
            width=500
        )

        self.label_shutdown_header.place(x=710, rely=0.45)

        self.label_shutdown_uploads = ctk.CTkLabel(
            self.shutdown_frame,
            text_color=PAGE_TXT_FG_COLOR,
            justify="center",
            anchor="center",
            width=500,
            wraplength=480
        )

        self.label_shutdown_encrypted = ctk.CTkLabel(
            self.shutdown_frame,
            text_color=PAGE_TXT_FG_COLOR,
            justify="center",
            anchor="center",
            width=500,
            wraplength=480
        )

        self.update_shutdown_info(num_uploads=0, num_encrypt=0)

        self.label_shutdown_uploads.place(x=710, rely=0.5)
        self.label_shutdown_encrypted.place(x=710, rely=0.55)

    # =============================
    # Internal methods
    # =============================
    def _launch_browser(self, url):
        url = url.replace("\\", "/")
        url = url.replace(" ", "%20")

        command = [self.browser_path] + self.browser_args + [url]

        try:
            subprocess.Popen(command)
            logger.info(f"GuiManager : launching {self.browser_name} "
                         + f"with url {url}")
        except subprocess.CalledProcessError as e:
            logger.error("GuiManager : error while launching "
                          + f"{self.browser_name}: {e}")
        except FileNotFoundError:
            logger.error("GuiManager : error while launching "
                          +  f"{self.browser_name}: {self.browser_path} "
                          + "not found")
        except Exception as e:
            logger.error("GuiManager : error while launching "
                          + f"{self.browser_name}: {e}")

    def _process_queue(self, max_per_tick=1):
        """Process events set by queued tasks"""
        self.queue_scheduled = False
        self.queue_event.clear()

        processed = 0
        func = None

        while processed < max_per_tick:
            try:
                func, args, kwargs = self.queue.get_nowait()
                # Call
                logger.info(
                    "GuiManager : external call from queue : "
                    f"{func.__name__}"
                )
                func(*args, **kwargs)
            except queue.Empty:
                break
            except Exception as e:
                func_name = ""
                if not func or not func.__name__:
                    func_name = "unknown function"
                else:
                    func_name = func.__name__
                logger.warning(
                    "GuiManager : could not process "
                    f"queued function {func_name} : {e}"
                )
            processed += 1

        if not self.queue.empty():
            self.queue_scheduled = True
            self.window.after(0, self._process_queue)

    def _tick(self):
        """Schedules processing of queue when needed"""
        if not self.tick_active:
            return

        self._last_tick = time()

        if self.queue_event.is_set() and not self.queue_scheduled:
            self.queue_scheduled = True
            self.window.after(0, self._process_queue)
        self.window.after(10, self._tick)

    def _start_tick(self):
        # Happens when main window has been created
        # and at self.start_processing()
        if self.tick_active:
            # No need to start if it's active already
            return

        self.tick_active = True
        logger.info("GuiManager : starting tick")
        self._last_tick = time()
        self.window.after(100, self._tick)
        self.window.after(5000, self._watchdog)

    def _pause_tick(self):
        # Tick is paused in self.start_countdown()
        logger.info("GuiManager : pausing tick")
        self.tick_active = False

    def _watchdog(self):
        if time() - self._last_tick > 5.0:
            logger.critical(
                "GuiManager : watchdog : MainThread stalled > 5 seconds"
            )
            for tid, frame in sys._current_frames().items():
                logger.critical(
                    "Thread %s\n%s", tid, "".join(
                        traceback.format_stack(frame)
                    )
                )
        self.window.after(5000, self._watchdog)

    def _register_main_window(self, e):
        self.window.unbind("<Visibility>")
        self.window.bind(self.kb_send_log, lambda event: self._send_log())
        self.window.bind(self.kb_toggle_greenscreen,
                         lambda event: self._toggle_greenscreen_btn())
        self.window.bind(self.kb_restart_recorder,
                         lambda event: self._restart_recorder())
        self.window.bind(self.kb_toggle_debug,
                         lambda event: self.menu.toggle_debug())

        app_windows = window_manager.getWindowsWithTitle("DIY Studio App")
        if app_windows:
            logger.info("GuiManager : GUI loaded")
            self.app_window = app_windows[0]
            self.app_window.raiseWindow()
            self.route_call("streamdeck_manager", "on_gui_loaded")
            self.route_call("state_manager", "on_gui_loaded")
            self.route_call("presentation_manager", "on_gui_loaded")
            self.set_videobg(0)
            self._start_tick()

        else:
            #No application window. Log error
            logger.critical("GuiManager : no application window found")

        # Show error if app has restarted after a crash
        parser = argparse.ArgumentParser(description="crash_info")
        parser.add_argument(
            "--restart",
            action="store_true",
            help="show an error message if app was restarted after a crash"
        )
        args = parser.parse_args()

        if args.restart:
            # Show an error message
            self.show_error(108)

    def _restart_recorder(self):
        """This will try to restart the recorder"""
        # Try to disconnect WebSocket first
        self.route_call("recorder_manager", "disconnect")

        def quit_recorder():
            # Try to terminate the recorder
            logger.info("GuiManager : trying to terminate recorder")
            recorder_file_name = os.path.basename(self.recorder_path)
            for p in psutil.process_iter(["name", "pid"]):
                if p.info["name"] == recorder_file_name:
                    p.terminate()
                    p.wait(timeout=3)
                    if p.is_running():
                        p.kill()
                        p.wait(timeout=3)

        self.window.after(2000, quit_recorder)
        self.window.after(3000, self.start_recorder)

    def _send_log(self):
        """Send log file via HTTP request to PHP script"""

        if not self.email_logs:
            return

        COOLDOWN = timedelta(seconds=30)
        current_time = datetime.now()
        temp_log_file = "logs/temp_log_file.log"
        log_file = getattr(self, "log_filename", "")

        if not log_file or not os.path.exists(log_file):
            logger.error("GuiManager : no log file received")
            return

        if (
            self.last_log_sent is not None
            and current_time - self.last_log_sent < COOLDOWN
        ):
            # We don't want the logs to be send more often than
            # once every 30 seconds
            return

        try:
            shutil.copy(log_file, temp_log_file)
        except PermissionError:
            logger.error(
                "GuiManager : no permission to copy log file"
            )

        try:
            with open(temp_log_file, "r") as file:
                log_content = file.read()

            response = session.post(
                self.webhost + "email_log.php",
                data={"log": log_content},
                timeout=(3, 5)
            )

            if response.status_code == 200:
                logger.info("GuiManager : log file sent successfully")
            else:
                logger.error("GuiManager : failed to send log: "
                              + str(response.status_code))

        except requests.Timeout as e:
            logger.error(f"GuiManager : timeout sending log file : {e}")
        except requests.RequestException as e:
            logger.error(f"GuiManager : request failed : {e}")
        except Exception as e:
            logger.error("GuiManager : could not send log file: "
                          + log_file + f" - error: {e}")

        self.last_log_sent = current_time

    def _toggle_greenscreen_btn(self):
        """Show button for green screen recording on videotype_1 page"""
        self.pages[Pages.VIDEOTYPE_1].toggle_greenscreen_btn()

    # =============================
    # Public methods
    # =============================

    # SCHEDULING FUNCTIONS
    def call_on_ui_thread(self, func_name, *args, **kwargs):
        """Run directly when on GUI thread or schedule for next tick"""
        target = self
        # The following resolves dotted paths,
        # like: self.menu.set_btn_active
        for part in func_name.split("."):
            target = getattr(target, part, None)
            if target is None:
                logger.error(
                    "GuiManager : no function with name "
                    f"{func_name} found")
                return

        if threading.get_ident() == self.gui_thread_id:
            # Run now
            logger.info(
                f"GuiManager : direct external call : {func_name}"
            )
            return target(*args, **kwargs)

        # Schedule - no return value possible
        self.queue_task(target, *args, **kwargs)
        return

    def queue_task(self, func, *args, **kwargs):
        """Put a task in the queue to be processed on the next tick

        Threadsafe function for calling UI-related functions from anywhere
        in the app.
        """
        self.queue.put((func, args, kwargs))
        thread_name = threading.current_thread().name
        if thread_name.startswith("Thread"):
            # All other threads have names - except worker threads
            thread_name = "RecorderWebSocket"
        logger.info(
            f"GuiManager : putting task in queue : {func.__name__} "
            f"(from thread: {thread_name})"
        )
        self.queue_event.set()

    def schedule_task(self, delay_ms, func, *args, **kwargs):
        """Schedule a function call directly and return its after_id

        Use for timers or instant scheduling.

        Not entirely threadsafe: only call from the main/GUI thread.
        """
        try:
            after_id = self.window.after(
                delay_ms, lambda: func(*args, **kwargs)
            )
            logger.info(
                f"GuiManager : scheduling task : {func.__name__} with "
                f"args : {args} : kwargs : {kwargs} : after_id : {after_id}"
            )
            return after_id
        except Exception as e:
            logger.exception(
                f"GuiManager : failed to schedule task : "
                f"{func.__name__}  : {e}"
            )
            return None

    def schedule_task_threadsafe(
            self, delay_ms, func, *args, on_id=None, **kwargs
        ):
        """Threadsafe scheduler"""
        if threading.current_thread() is threading.main_thread():
            # Skip queue
            after_id = self.schedule_task(delay_ms, func, *args, **kwargs)
            if on_id is not None:
                try:
                    on_id(after_id)
                except Exception:
                    logger.exception(
                        "GuiManager : on_id callback failed"
                    )
            return

        def _schedule_for_ui_thread():
            after_id = self.schedule_task(delay_ms, func, *args, **kwargs)
            if on_id is not None:
                try:
                    on_id(after_id)
                except Exception:
                    logger.exception(
                        "GuiManager : on_id callback failed"
                    )

        self.queue_task(_schedule_for_ui_thread)

    def cancel_task(self, after_id):
        """Cancel task that was scheduled with schedule_task"""
        try:
            self.window.after_cancel(after_id)
            logger.info(
                f"GuiManager : cancelled task with id {after_id}"
            )
        except Exception as e:
            logger.exception(
                "GuiManager : failed to cancel task "
                f"with id {after_id}: {e}"
            )

    def cancel_task_threadsafe(self, after_id):
        """Threadsafe version to cancel task"""
        if not after_id:
            return

        if threading.current_thread() is threading.main_thread():
            self.cancel_task(after_id)
            return

        def _do_cancel():
            try:
                self.window.after_cancel(after_id)
                logger.info(
                    f"GuiManager : cancelled task with id {after_id}"
                )
            except Exception as e:
                logger.exception(
                    "GuiManager : failed to cancel task "
                    f"with id {after_id}: {e}"
                )

        self.queue_task(_do_cancel)

    # GENERAL (UI) FUNCTIONS
    def change_language(self):
        lan_full: str = ""

        match self.language:
            case 'nl':
                self.language = 'en'
                lan_full = "English"
            case 'en':
                self.language = 'nl'
                lan_full = "Dutch"

        self.menu.refresh_buttons(self.language)

        logger.info(f"Language changed to {lan_full}")

        for p in Pages:
            self.pages[p].change_language(self.language)

        for p in Popups:
            self.popups[p].change_language(self.language)

        self.update_shutdown_info(
            self.managers["cloud_manager"].get_remaining_uploads()
        )

        self.route_call("recorder_manager", "set_language", self.language)

    def close_window(self):
        """Close main tkinter window during shutdown procedure"""
        try:
            self.window.withdraw()
            logger.info("GuiManager : closed app window")
        except Exception:
            logger.exception("GuiManager : could not close main window")

    def on_back(self):
        self.route_call("state_manager", "goto", Navigate.PREV)

    def on_forward(self):
        self.route_call("state_manager", "goto", Navigate.NEXT)

    def leave_page(self, page):
        #logger.info(f"Leaving page {page}")
        pass

    def view_page(self, page):
        logger.info(f"GuiManager : refreshing page {page}")
        self.pages[page].refresh()
        logger.info(f"GuiManager : raising page {page}")
        self.pages[page].tkraise()
        # if there is an active error, raise it to the front
        if len(self.cur_errors) > 0:
            logger.info("GuiManager : raising popup_bg")
            self.popup_bg.tkraise()
            logger.info("GuiManager : raising error popup")
            self.popups[Popups.ERROR].tkraise()

    def show_shutdown_screen(self, show):
        if show:
            self.shutdown_frame.place(x=0, y=0)
            self.shutdown_frame.tkraise()
            self.shutdown_frame.focus_set()
        else:
            self.shutdown_frame.place_forget()

    def start_recorder(self):
        cwd = os.getcwd()
        # Somehow, OBS only works when started from its own path
        os.chdir(os.path.dirname(self.recorder_path))

        command = [self.recorder_path] + self.recorder_args

        try:
            subprocess.Popen(command)
            logger.info("GuiManager : launching recorder")
            # Try to reconnect
            self.route_call("recorder_manager", "reconnect")
        except subprocess.CalledProcessError as e:
            logger.error(f"GuiManager : error while launching recorder: {e}")
        except FileNotFoundError:
            logger.error("GuiManager : error while launching recorder: "
                          ".exe not found")
        except Exception as e:
            logger.error(f"GuiManager : error while launching recorder: {e}")
        finally:
            os.chdir(cwd)

    def hide_streamdeck_windows(self):
        allTitles = window_manager.getAllTitles()
        for title in allTitles:
            if "Software Update - Stream Deck" in title:
                windows = window_manager.getWindowsWithTitle(title)
                if windows:
                    windows[0].move(3840, 0)
            elif "Stream Deck" in title:
                windows = window_manager.getWindowsWithTitle(title)
                if windows:
                    windows[0].minimize()

    def update_debug_text(self, index, value):
        # index - component
        # 0 - recorder
        # 1 - Stream Deck
        # 2 - cloud storage
        # 3 - internet
        # example str: 'App version: 0.0.1, Recorder: (not) connected,
        # StreamDeck: (not) connected, Cloud Storage: (not) authenticated,
        # Internet: (not) connected'

        self.debug_components[index] = value

        s = "App version: " + self.app_version + "   -   Recorder: "
        if not self.debug_components[0]:
            s = s + "not "
        s = s + "connected   -   StreamDeck: "
        if not self.debug_components[1]:
            s = s + "not "
        s = s + "connected   -   Cloud Storage: "
        if not self.debug_components[2]:
            s = s + "not "
        s = s + "connected   -   Internet: "
        if not self.debug_components[3]:
            s = s + "not "
        s = s + "connected"

        self.menu.update_debug(s)

    # HEADER
    def load_ext_text(self):
        FILE_NAME = "loc.json"
        file_path = os.path.join("config", FILE_NAME)

        # Check if there's a custom version in config folder.
        # If not, then use the file from the root folder
        if not os.path.exists(file_path):
            file_path = "loc.json"
            if not os.path.exists(file_path):
                logging.critical(f"GuiManager : can't find {file_path}")
                return

        with open(file_path, "r", encoding="utf-8") as loc_file:
            return json.load(loc_file)

    def on_menu_click(self, name):
        match name:
            case "tutorial":
                self.route_call("state_manager",
                                "change_state",
                                "state_tutorial"
                                )
            case "login":
                self.route_call("state_manager",
                                "change_state",
                                "state_login1"
                                )
            case "videotype":
                self.route_call("state_manager",
                                "change_state",
                                "state_videotype_1"
                                )
            case "powerpoint":
                self.route_call("state_manager",
                                "change_state",
                                "state_powerpoint"
                                )
            case "calibration":
                self.route_call("state_manager",
                                "change_state",
                                "state_calibration_1"
                                )
            case "controls":
                self.route_call("state_manager",
                                "change_state",
                                "state_controls_1"
                                )
            case "record":
                self.route_call("state_manager",
                                "change_state",
                                "state_record_overview"
                                )
            case "end":
                self.route_call("state_manager",
                                "change_state",
                                "state_end"
                                )

    # VIDEOPLAYER - WELCOME & REVIEW
    def close_browser(self):
        # Don't actually close it, but navigate to an empty page
        self._launch_browser("about:blank")

        # Bring focus back to application window
        try:
            if self.app_window:
                self.app_window.activate()
        except Exception:
            logger.info("GuiManager : can't bring focus back to app")

    def display_tutorial_video(self):
        url = (
            "file://"
            + os.path.join(self.record_dir, "videoplayer.html")
            + "?file=tutorial.mp4"
            + "&type=tutorial"
            + "&lang=" + self.language
        )
        self._launch_browser(url)

    def play_latest_recording(self, videopath):
        filename = os.path.basename(videopath)
        url = (
            "file://"
            + os.path.join(self.record_dir, "videoplayer.html")
            + "?file=" + filename
            + "&type=review"
            + "&lang=" + self.language
        )
        self._launch_browser(url)

    # CALIBRATION
    def on_passed_soundcheck(self):
        self.pages[Pages.CALIBRATION_2].set_passed_soundcheck()

    # OBS
    def close_obs_projector(self, preview=False):
        if preview:
            windows = window_manager.getWindowsWithTitle(
                "Projector - Preview")
        else:
            windows = window_manager.getWindowsWithTitle(
                "Projector - Program")

        for window in windows:
            window.close()

    # RECORD OVERVIEW
    def stop_checking_uploads(self):
        self.pages[Pages.RECORD_OVERVIEW].stop_checking_uploads()

    # RECORD
    def log_record_activity(self, log):
        self.window.after(0, lambda: self.pages[Pages.RECORD_ACTIVE].log(log))

    def set_unlock_stop(self, unlock):
        self.pages[Pages.RECORD_ACTIVE].set_unlock_stop(unlock)

    def start_countdown(self):
        self.pages[Pages.RECORD_ACTIVE].update_text(0)

        if self.countdown_window is None:
            self.create_countdown_window()
        else:
            self.countdown_page.setup_and_start_countdown_timer()
            window_countdown = window_manager.getWindowsWithTitle(
                "DIY Studio Countdown")

            if window_countdown:
                window = window_countdown[0]
                window.moveTo(self.countdown_window_x,self.countdown_window_y)

    def hide_countdown_window(self):
        window_countdown = window_manager.getWindowsWithTitle(
            "DIY Studio Countdown")
        if window_countdown:
                window = window_countdown[0]
                window.moveTo(self.countdown_window_x,
                              self.countdown_window_y-1080)

    def create_countdown_window(self):
        length = 680

        self.countdown_window_x = int(
            self.teleprompter_x + (1920 - length) / 2)

        self.countdown_window_y = int(
            self.teleprompter_y + (1080 - length) / 2)

        g = (f"{length}x{length}+"
             + f"{self.countdown_window_x}+{self.countdown_window_y}")

        self.countdown_window = ctk.CTkToplevel()
        self.countdown_window.geometry(g)
        self.countdown_window.overrideredirect(True)
        self.countdown_window.wm_attributes("-topmost", True)
        self.countdown_window.title("DIY Studio Countdown")
        self.countdown_window.resizable(False, False)

        self.countdown_page = PageCountdown(self.countdown_window, self)
        self.countdown_page.place(x=0,y=0)

    def on_countdown_complete(self):
        self.hide_countdown_window()
        # Right now we use the timer on the page
        # to trigger the recording
        self.route_call(
            "recorder_manager",
            "set_action",
            RecAction.REQUESTING_RECORDING
        )

    def on_start_recording(self):
        self.pages[Pages.RECORD_ACTIVE].update_text(1)

        # Switch focus to PowerPoint Slide Show so it can play animations
        allTitles = window_manager.getAllTitles()
        for title in allTitles:
            if "PowerPoint Slide Show" in title:
                windows = window_manager.getWindowsWithTitle(title)
                if windows:
                    windows[0].activate()
                    return

    def on_start_processing(self):
        self.pages[Pages.RECORD_ACTIVE].update_text(2)
        PageRecordOverview.has_recorded = True
        self.stats.update("recs_total")
        if self.videotype == "staticbg":
            self.stats.update("recs_static")
            bg_num = "bg" + str(self.videobg + 1)
            self.stats.update(bg_num)
        else:
            self.stats.update("recs_ppt")

    def interrupt_countdown(self):
        logger.info("GuiManager : interrupting countdown")
        self.countdown_page.stop_countdown()
        self.hide_countdown_window()
        self.route_call("recorder_manager", "set_action", RecAction.IDLE)
        self.route_call("state_manager", "goto", Navigate.PREV)

    def on_video_reviewed(self, good, name_input="default"):
        if good:
            self.stats.update("recs_good")
            if not name_input == "default":
                self.stats.update("custom_file_names")
            self.route_call("recorder_manager", "accept_recording", name_input)
        else:
            self.show_popup(
                Popups.CONFIRMATION, 1,
                lambda:self.route_call("recorder_manager", "delete_recording")
            )

    # VIDEOTYPE
    def set_videotype(self, index):
        """Change videotype to PowerPoint, Static Background or Green Screen.

        index can be:
        0 = Video with static background
        1 = PowerPoint video
        2 = Green screen mode: same as 0, but with the key turned off
        """
        ult_result: int = 0

        match index:
            case 0:
                self.videotype = "staticbg"
                self.route_call("recorder_manager", "set_mode_static_bg")
                self.pages[Pages.POWERPOINT].change_videotype("staticbg")
                ult_result = self.ultimatte.send("key-on")
            case 1:
                self.videotype = "ppt"
                self.route_call("recorder_manager", "set_mode_powerpoint")
                self.pages[Pages.POWERPOINT].change_videotype("ppt")
                ult_result = self.ultimatte.send("key-off")
            case 2:
                self.videotype = "staticbg"
                self.route_call("recorder_manager", "set_mode_static_bg")
                self.pages[Pages.POWERPOINT].change_videotype("staticbg")
                ult_result = self.ultimatte.send("key-off")

        self.pages[Pages.VIDEOTYPE_1].set_active_videotype(index)

        if ult_result == 0:
            # Message has not been delivered to Ultimatte.
            # We can not proceed...
            self.show_error(104, True)
            return

        # If the user clicked the "Static Background-video"-button,
        # we'll automatically switch to the page where a background
        # can be chosen
        if index == 0:
            self.route_call("state_manager", "change_state", "state_videotype_2")
        elif index == 2:
            self.route_call("state_manager", "change_state", "state_powerpoint")

    def set_videobg(self, index):
        """Register the chosen background for the static video option."""
        self.videobg = index
        self.route_call("recorder_manager", "set_index_static_bg", index)
        self.pages[Pages.VIDEOTYPE_2].set_active_videobg(index)

    # LOGIN
    def get_auth_status(self):
        return self.pages[Pages.LOGIN1].get_auth_status()

    def on_auth_failed(self, err):
        self.update_debug_text(2, False)
        self.pages[Pages.LOGIN1].set_auth_failed(err)
        self.route_call("state_manager", "change_state", "state_login1")

    def on_auth_lost(self):
        self.quit_browser()

        # Reset session
        self.route_call("cloud_manager", "logout")

        # Change PageLogin1 and PageLogin2
        self.pages[Pages.LOGIN1].logout()
        self.pages[Pages.LOGIN2].logout()

        # Reset unlockIndex to 0 (authentication can't be
        # interrupted by navigation to other urls in the browser
        # f.e. the video player html page)
        self.menu.reset_unlock_index()

        # Return to login page
        self.route_call("state_manager", "change_state", "state_login1")

    def on_authenticated(self, id):
        self.update_debug_text(2, True)
        self.pages[Pages.LOGIN1].set_authenticated()
        self.pages[Pages.LOGIN2].set_authenticated()
        self.pages[Pages.POWERPOINT].set_root_id(id)
        self.menu.refresh_buttons(self.language)

        if id:
            # Advance to tutorial page
            # (can't do this when OneDrive module is disabled
            # as the advance will happen while still in a
            # state transition)
            self.on_menu_click("tutorial")

    def on_logout(self):
        # Only log out if no uploads are busy or pending
        if (self.route_call("cloud_manager", "all_uploads_done")):
            self.stats.update("logout")
            self.quit_browser()

            # Reset session
            self.route_call("cloud_manager", "logout")

            # Change PageLogin1 and PageLogin2
            self.pages[Pages.LOGIN1].logout()
            self.pages[Pages.LOGIN2].logout()

            # Clear listboxes on PagePowerPoint and RecordOverview
            self.pages[Pages.POWERPOINT].clear_listbox()
            self.pages[Pages.RECORD_OVERVIEW].clear_listbox()

            # Reset unlockIndex to 0 (authentication can't be
            # interrupted by navigation to other urls in the browser
            # f.e. the video player html page)
            self.menu.reset_unlock_index()

            # Change PowerPoint back to default
            self.route_call("presentation_manager", "open_presentation", "DEFAULT")

        else:
            self.pages[Pages.LOGIN1].on_uploads_pending()

    def quit_browser(self):
        """Quit the web browser."""
        if self.browser_close:
            allTitles = window_manager.getAllTitles()
            for title in allTitles:
                if self.browser_name in title:
                    windows = window_manager.getWindowsWithTitle(title)
                    for window in windows:
                        window.close()
            # Wait a second and restart
            self.window.after(
                1000, lambda: self._launch_browser("about:blank")
            )

    def start_auth_timer(self, timeout):
        self.pages[Pages.LOGIN2].set_auth_start(timeout)

    # POWERPOINT
    def set_folder_data(self, data):
        self.pages[Pages.POWERPOINT].set_folder_data(data)

    # END
    def on_shutdown(self):
        """Show confirmation popup when a user clicks 'end session' button."""
        self.show_popup(Popups.CONFIRMATION, 2, self.start_shutdown)

    def start_shutdown(self):
        """Prepares GUI for shutdown and changes state to initiate shutdown."""
        self.stats.write()
        self.hide_popup()
        self.update_shutdown_info(
            num_uploads=self.route_call("cloud_manager", "get_remaining_uploads"),
            num_encrypt=self.stats.recs_good
        )
        self.show_shutdown_screen(True)
        self.route_call("state_manager", "change_state", "state_shutdown")

    def update_shutdown_info(self, num_uploads=-1, num_encrypt=-1):
        """Show information to the user about the status when shutting down.

        It will show how many uploads are remaining and how many files still
        need to be encrypted.

        This function will be called from either CloudStorageManager (when
        an upload is finished) or SystemManager (when a file has been encrypted).

        A value of -1 means: no change
        """
        if num_uploads >= 0:
            s = (
                str(num_uploads) +
                " " + self.dataText[
                    'pagetext'
                    ]['black']['text_1'][self.language]
            )
            self.label_shutdown_uploads.configure(text=s, justify="center")

        if num_encrypt >= 0:
            s = (
                str(num_encrypt) +
                " " + self.dataText[
                    'pagetext'
                    ]['black']['text_2'][self.language]
            )
            self.label_shutdown_encrypted.configure(text=s, justify="center")

    # POPUP
    def show_error(self, type, reboot_button=False):
        """Show an error in a pop-up and email the logfile."""
        logger.info("GuiManager : show error "
                     + str(type)
                     + ", reboot_button "
                     + str(reboot_button)
        )

        self.stats.update("errors")

        # E-mail log file, unless there's no internet (error 102)
        if type != 102:
            self._send_log()

        # Try to restart recorder if error is 208
        if type == 208:
            self._restart_recorder()

        # Return when GUI is not loaded yet
        if self.app_window is None:
            return

        # Show or add error to popup
        if len(self.cur_errors) == 0:
            self.cur_errors.append(type)
            self.window.after(
                0, lambda: self.show_popup(
                    Popups.ERROR, type, None, reboot_button
                )
            )
        else:
            self.add_to_error(type, reboot_button)

    def add_to_error(self, type, reboot_button):
        if type not in self.cur_errors:
            self.cur_errors.append(type)
            self.popups[Popups.ERROR].update_info(self.cur_errors)
            self.popups[Popups.ERROR].setup_btn_reboot(reboot_button)

    def remove_error(self, type):
        try:
            self.cur_errors.remove(type)
        except Exception:
            pass
        if len(self.cur_errors) == 0:
            self.hide_popup()
        else:
            self.popups[Popups.ERROR].update_info(self.cur_errors)

    def hide_error(self):
        self.cur_errors.clear()
        self.hide_popup()

    def show_popup(self, p, type=-1, continue_method=None,
                   reboot_button=False):
        """Show a popup. p = Popups.ERROR or Popups.CONFIRMATION"""
        if(p != Popups.ERROR and reboot_button):
            logger.error(
                "GuiManager : ERROR : you have selected a non-error "
                "popup with reboot_button True."
            )
        self.popup_continue_method = continue_method
        self.popup_bg.place(x=0, y=0)
        self.popup_bg.tkraise()
        self.popups[p].set_type(type)

        if(p==Popups.ERROR):
            self.popups[p].setup_btn_reboot(reboot_button)

        self.popup_cur = self.popups[p]
        self.popups[p].place(x=320, y=180)
        self.popups[p].tkraise()

    def hide_popup(self):
        if self.popup_cur is not None:
            self.popup_cur.place_forget()
        if self.popup_bg is not None:
            self.popup_bg.place_forget()

    def on_popup_cancel(self):
        self.hide_popup()

    def on_popup_confirm(self):
        self.hide_popup()
        if self.popup_continue_method is not None:
            self.popup_continue_method()

    def on_popup_accept(self):
        self.hide_error()

    def on_popup_reboot(self):
        self.route_call("system_manager", "set_shutdown_type_to_reboot")
        self.start_shutdown()

    # =============================
    # Outbound communication
    # =============================
    def route_call(self, manager, method, *args, **kwargs):
        streamdeck_manager = GuiManager.managers.get("streamdeck_manager")
        cloud_manager = GuiManager.managers.get("cloud_manager")
        presentation_manager = GuiManager.managers.get("presentation_manager")
        recorder_manager = GuiManager.managers.get("recorder_manager")
        state_manager = GuiManager.managers.get("state_manager")
        system_manager = GuiManager.managers.get("system_manager")

        if not streamdeck_manager:
            logger.error("GuiManager : streamdeck_manager not registered")
            return

        if not cloud_manager:
            logger.error("GuiManager : cloud_manager not registered")
            return

        if not presentation_manager:
            logger.error("GuiManager : presentation_manager not registered")
            return

        if not recorder_manager:
            logger.error("GuiManager : recorder_manager not registered")
            return

        if not state_manager:
            logger.error("GuiManager : state_manager not registered")
            return

        if not system_manager:
            logger.error("GuiManager : system_manager not registered")
            return

        match (manager, method):
            case ("streamdeck_manager", "on_gui_loaded"):
                streamdeck_manager.on_gui_loaded()

            case ("cloud_manager", "all_uploads_done"):
                return cloud_manager.all_uploads_done()

            case("cloud_manager", "get_remaining_uploads"):
                return cloud_manager.get_remaining_uploads()

            case ("cloud_manager", "logout"):
                cloud_manager.logout()

            case ("cloud_manager", "set_dir_id"):
                cloud_manager.set_dir_id(args[0])

            case ("cloud_manager", "set_presentation"):
                cloud_manager.set_presentation(args[0])

            case ("cloud_manager", "uploads"):
                return cloud_manager.uploads

            case ("presentation_manager", "on_gui_loaded"):
                presentation_manager.on_gui_loaded()

            case ("presentation_manager", "open_presentation"):
                presentation = args[0] if args else "DEFAULT"
                presentation_manager.open_presentation(presentation)

            case ("presentation_manager", "set_presenter_view"):
                presentation_manager.set_presenter_view(
                    args[0])

            case ("recorder_manager", "accept_recording"):
                recorder_manager.accept_recording(args[0])

            case ("recorder_manager", "set_language"):
                recorder_manager.set_language(args[0])

            case ("recorder_manager", "delete_recording"):
                recorder_manager.delete_recording()

            case ("recorder_manager", "disconnect"):
                recorder_manager.disconnect()

            case ("recorder_manager", "reconnect"):
                recorder_manager.reconnect()

            case ("recorder_manager", "set_index_static_bg"):
                recorder_manager.set_index_static_bg(
                    args[0])

            case ("recorder_manager", "set_mode_powerpoint"):
                recorder_manager.set_mode_powerpoint()

            case ("recorder_manager", "set_mode_static_bg"):
                recorder_manager.set_mode_static_bg()

            case ("recorder_manager", "set_action"):
                recorder_manager.set_action(args[0])

            case ("recorder_manager", "stop_record"):
                recorder_manager.stop_record()

            case ("state_manager", "change_state"):
                state = getattr(state_manager, args[0])
                state_manager.change_state(state)

            case ("state_manager", "get_state_str"):
                return state_manager.get_state_str()

            case ("state_manager", "goto"):
                state_manager.goto(args[0])

            case ("state_manager", "on_gui_loaded"):
                state_manager.on_gui_loaded()

            case ("system_manager", "set_shutdown_type_to_reboot"):
                system_manager.shutdown_type = "r"


class SessionStats:
    enabled = False
    manager: ClassVar["GuiManager"]

    def __init__(self, csv: str, studio, enable):
        if enable:
            SessionStats.enabled = True

        current_date = datetime.now()
        folder = os.getcwd()
        path = os.path.join(folder, csv)

        if not os.path.isfile(path):
            # csv file not found, let's create it from the template
            template_path = os.path.join(folder, "stats_template.csv")
            new_stats_path = os.path.join(folder, "stats.csv")
            try:
                shutil.copy(template_path, new_stats_path)
                csv = "stats.csv"
                logger.info("SessionStats : created stats.csv from template")
            except Exception as e:
                logger.warning("SessionStats : "
                            + f"couldn't create stats.csv from template : {e}")

        self.csv = csv
        self.studio = studio
        self.date = current_date.strftime("%Y-%m-%d")
        self.recs_total: int = 0
        self.recs_good: int = 0
        self.custom_file_names: int = 0
        self.avg_filesize: float = 0.0
        self.file_download_amnt: int = 0
        self.recs_ppt: int = 0
        self.recs_static: int = 0
        self.bg1: int = 0
        self.bg2: int = 0
        self.bg3: int = 0
        self.bg4: int = 0
        self.bg5: int = 0
        self.bg6: int = 0
        self.bg7: int = 0
        self.bg8: int = 0
        self.errors: int = 0
        self.logout: int = 0

    def update(self, attr: str, value: int = 1):
        if not SessionStats.enabled:
            return

        if hasattr(self, attr):
            current_value = getattr(self, attr)
            if attr == "avg_filesize":
                # Calculate average filesize
                num = self.recs_total
                # This assumes that rec_totaal already includes the
                # latest recording that value refers to
                new_avg = (current_value * (num - 1) + value) / num
                self.avg_filesize = new_avg
            else:
                setattr(self, attr, current_value + value)
        else:
            raise AttributeError(f"'{self.__class__.__name__}' object has "
                                 f"no attribute '{attr}'")

    def write(self):
        if not SessionStats.enabled:
            return

        logger.info("SessionStats : trying to send stats to server")

        data = {
            "studio": self.studio,
            "date": self.date,
            "recs_total": self.recs_total,
            "recs_good": self.recs_good,
            "custom_file_names": self.custom_file_names,
            "avg_filesize": self.avg_filesize,
            "ppt_download_amnt": self.file_download_amnt,
            "recs_ppt": self.recs_ppt,
            "recs_static": self.recs_static,
            "bg1": self.bg1,
            "bg2": self.bg2,
            "bg3": self.bg3,
            "bg4": self.bg4,
            "bg5": self.bg5,
            "bg6": self.bg6,
            "bg7": self.bg7,
            "bg8": self.bg8,
            "errors": self.errors,
            "logout": self.logout
        }

        url = SessionStats.manager.webhost + "receive_stats.php"

        try:
            response = session.post(
                url,
                json=data,
                timeout=(3.0, 5.0)
            )

            if response.status_code == 200:
                logger.info("SessionStats : stats sent successfully")
            else:
                logger.error("SessionStats : failed to send stats to: "
                                + url + " "
                                + str(response.status_code))
        except requests.Timeout as e:
            logger.error(f"SessionStats : timeout sending stats : {e}")
        except requests.RequestException as e:
            logger.error(f"SessionStats : request failed : {e}")
        except Exception as e:
            logger.error(f"SessionStats : failed to send stats : {e}")

    def write_csv(self):
        # Not currently in use
        if not SessionStats.enabled:
            return

        new_row = [
            self.date, self.recs_total, self.recs_good,
            self.custom_file_names, self.avg_filesize, self.file_download_amnt,
            self.recs_ppt, self.recs_static, self.bg1, self.bg2,
            self.bg3, self.bg4, self.bg5, self.bg6, self.bg7, self.bg8,
            self.errors, self.logout
        ]

        with open(self.csv, mode="a", newline="") as file:
            writer = csv.writer(file, delimiter=";")
            writer.writerow(new_row)

        logger.info("SessionStats : added record to stats.csv")
