# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

import customtkinter as ctk
from copy import copy
from modules.gui_pages.base import PageBase

class PageTutorial(PageBase):
    def __init__(self, parent, ui_elements):
        super().__init__(parent, ui_elements)
        
        self.setup_btn_forward()
        self.set_unlock_forward()
        self.setup_btn_back()

        # CUSTOM CODE FOR THIS PAGE
        # Copy style for button with grey background
        self.btn_style_normal_custom = copy(ui_elements[3])
        self.btn_style_hover_custom = copy(ui_elements[4])

        self.btn_style_normal_custom["bg_color"] = self.colors["bg_content"]
        self.btn_style_hover_custom["bg_color"] = self.colors["bg_content"]

        self.setup_title_by_pagename("tutorial")

        self.label_transparent = ctk.CTkLabel(
            self,
            width=938,
            height=570,
            text="",
            fg_color="red"
        )
        self.label_transparent.place(x=491, y=164)

    def change_language(self, lang):
        super().change_language(lang)
        # Change language for tutorial video
        manager = PageTutorial.manager
        if manager.route_call("state_manager", "get_state_str") == "StateTutorial":
            manager.display_tutorial_video()

    def refresh(self):
        PageTutorial.manager.display_tutorial_video()
    