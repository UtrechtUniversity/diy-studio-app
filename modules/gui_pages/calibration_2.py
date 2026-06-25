# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

import customtkinter as ctk
from PIL import Image
from modules.gui_pages.base import PageBase

class PageCalibration2(PageBase):
    def __init__(self, parent, ui_elements):
        super().__init__(parent, ui_elements)
        
        self.setup_btn_forward()
        self.setup_btn_back()

        # CUSTOM CODE FOR THIS PAGE
        self.setup_title_by_pagename("calibration_2")

        self.img1 = ctk.CTkImage(Image.open(
            "assets/static/studio_3d_positioning.png"
            ), size=(600, 600))
        self.label_img1 = ctk.CTkLabel(
            self,
            text="",
            image=self.img1,
            width=600,
            height=600
        )
        self.label_img1.place(x=100, y=150)

        self.label_text1 = ctk.CTkLabel(
            self,
            text=self.text["pagetext"][self.pagename]["text_1"][self.language],
            width=400,
            wraplength=400,
            height=140
        )
        self.label_text1.configure(**self.text_style)
        self.label_text1.configure(justify="center")
        self.label_text1.place(x=750,y=260)

        self.label_feedback = ctk.CTkLabel(
            self,
            text="",
            width=350,
            height=350,
            corner_radius=20,
            bg_color=self.colors["bg_content"],
            fg_color="#666666"
        )
        self.label_feedback.place(x=1280, y=240)
        
    def set_passed_soundcheck(self):
        self.set_unlock_forward()
        self.label_feedback.configure(fg_color=self.colors["good"])

    def change_language(self,lang):
        super().change_language(lang)

        self.label_text1.configure(
            text=self.text["pagetext"][self.pagename]["text_1"][self.language]
        )
