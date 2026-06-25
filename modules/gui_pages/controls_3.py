# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

import customtkinter as ctk
from PIL import Image
from modules.gui_pages.base import PageBase

class PageControls3(PageBase):
    def __init__(self, parent, ui_elements):
        super().__init__(parent, ui_elements)
        
        self.setup_btn_forward()
        self.set_unlock_forward()
        self.setup_btn_back()

        # CUSTOM CODE FOR THIS PAGE
        self.setup_title_by_pagename("controls_3")
                
        self.img1 = ctk.CTkImage(Image.open(
            "assets/static/studio_3d_streamdeck.png"), size=(600, 600))
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
        self.label_text1.place(x=1100, y=600)

        self.img2 = ctk.CTkImage(Image.open(
            "assets/static/streamdeck_record.png"), size=(570, 400))
        self.label_img2 = ctk.CTkLabel(
            self,
            text="",
            image=self.img2,
            width=600,
            height=420,
            bg_color=self.colors["bg_content"]
        )
        self.label_img2.place(x=1000, y=140)

        
    def change_language(self,lang):
        super().change_language(lang)
        
        self.label_text1.configure(
            text=self.text["pagetext"][self.pagename]["text_1"][self.language]
        )
