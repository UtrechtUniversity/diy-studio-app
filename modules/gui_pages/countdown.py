# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

import customtkinter as ctk
import logging
import winsound
from typing import ClassVar, TYPE_CHECKING

if TYPE_CHECKING:
    from modules.gui import GuiManager

logger = logging.getLogger(__name__)


class PageCountdown(ctk.CTkFrame):

    manager: ClassVar["GuiManager"]
    timer_value = 5

    def __init__(self, parent, gui_manager):
        self.gui_manager = gui_manager

        ctk.CTkFrame.__init__(
            self, 
            parent, 
            corner_radius=0,
            width=680,
            height=680,
            fg_color='#888888'
            )
        
        self.label_timer = ctk.CTkLabel(
            self,
            width=680,
            height=680,
            font=("Open Sans Bold", 376),
            text='5',
            fg_color='transparent',
            text_color='#ffcd00',
            justify='center',
            anchor='center'
        )
        
        self.label_timer.place(x=0,y=0)
        self.countdown_in_progress = False
        self.setup_and_start_countdown_timer()

    def _tick(self):
        if self.countdown_in_progress:
            self.timer_value -= 1
            logger.info(f"Countdown : {self.timer_value}")
            self.label_timer.configure(text=str(self.timer_value))

            if self.timer_value > 0:
                self.start_countdown_timer()
            else:
                self.stop_countdown()
                PageCountdown.manager.on_countdown_complete()

    def setup_and_start_countdown_timer(self):
        self.timer_value = 5
        self.label_timer.configure(text=str(self.timer_value))
        self.countdown_in_progress = True
        logger.info(f"Countdown : {self.timer_value}")
        self.start_countdown_timer()

    def start_countdown_timer(self):
        winsound.Beep(500, 200)
        PageCountdown.manager.schedule_task(1000, self._tick)

    def stop_countdown(self):
        self.countdown_in_progress = False
