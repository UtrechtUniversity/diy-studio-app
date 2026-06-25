# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

import customtkinter as ctk
import time
from PIL import Image
from modules.gui_pages.base import PageBase

class PageLogin2(PageBase):
    TIMER_SHOW_TRANSPARENT_LABEL = 1

    # Simple state manager
    # phase 1 : not logged in
    # phase 2 : logging in
    # phase 3 : authenticated
    phase = 1

    def __init__(self, parent, ui_elements):
        super().__init__(parent, ui_elements)
        
        self.setup_btn_forward()
        self.setup_btn_back()

        # CUSTOM CODE FOR THIS PAGE
        self.showing = False
        self.timeout = 180
        self.start_time = time.time()
        self._width = 1784
        self._height = 772
        self._x = 68
        self._y = 8

        # TRANSPARENT RECT
        self.img1 = ctk.CTkImage(Image.open(
            "assets/static/page_bg_transparent_large.png"), size=(1784,772)
        )
        
        self.label_transparent = ctk.CTkLabel(
            self,
            bg_color=self.colors["bg_content"],
            fg_color=self.colors["bg_content"],
            width=self._width,
            height=self._height,
            corner_radius=0,
            image=self.img1,
            text=""
        )

        # Show a timer with login timeout
        self.label_timeout = ctk.CTkLabel(
            self,
            text_color=self.colors["secondary"],
            justify="center",
            anchor="center",
            width=500,
            wraplength=480
        )
        self.label_timeout.configure(
            text=self.text["pagetext"]["login"]["text_7"][self.language]
        )
        self.label_timeout.place(x=710, y=850)

    def change_language(self,lang):
        super().change_language(lang)

    def logout(self):
        self.phase = 1
        super().set_relock_forward()

    def refresh(self):
        if self.showing is False:
            PageLogin2.manager.schedule_task(1000, self.show_label_transparent)
            self.showing = True

    def set_auth_start(self, timeout):
        self.timeout = timeout
        self.start_time = time.time()
        self.update_timer()

    def set_authenticated(self):
        self.set_unlock_forward()
        self.phase = 3
        self.start_time = None

    def set_logging_in(self):
        self.label_transparent.place_forget()
        self.phase = 2

    def show_label_transparent(self):
        self.label_transparent.place(x=self._x, y=self._y)

    def update_timer(self):
        if not self.start_time:
            return
        
        elapsed = time.time() - self.start_time
        remaining = int(self.timeout - elapsed)

        if remaining < 0:
            remaining = 0

        self.label_timeout.configure(
            text=self.text["pagetext"]["login"]["text_7"][self.language]
            + " " + str(remaining),
            justify="center"
        )

        if remaining > 0:
            PageLogin2.manager.window.after(1000, self.update_timer)