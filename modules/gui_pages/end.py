# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

import customtkinter as ctk
from PIL import Image
from modules.gui_pages.base import PageBase
from os.path import join, exists

class PageEnd(PageBase):
    def __init__(
            self, parent, ui_elements,
            logo_path: str, logo_width: int, logo_height: int
        ):
        super().__init__(parent, ui_elements)
        
        # CUSTOM CODE FOR THIS PAGE
        # get placement of basic buttons
        h = 1080 - self.padding["page_padding_content_y"]

        self.setup_title_by_pagename("end")

        if not exists(logo_path):
            logo_path = join("assets", "static", "logo_placeholder.png")

        self.img1 = ctk.CTkImage(
            Image.open(logo_path), size=(logo_width, logo_height)
        )
        
        self.label_img1 = ctk.CTkLabel(
            self,
            text="",
            image=self.img1,
            width=595,
            height=240,
            bg_color=self.colors["bg_content"]
        )
        self.label_img1.place(x=1100,y=250)


        self.label_text1 = ctk.CTkLabel(
            self,
            text=self.text["pagetext"][self.pagename]["text_1"][self.language],
            width=600,
            wraplength=800,
            height=140
        )
        self.label_text1.configure(**self.text_style)
        self.label_text1.place(x=250, y=260)

        
        self.btn_exit = ctk.CTkButton(
            self, 
            text=self.text["pagetext"]["end"]["button_exit"][self.language],
            command=PageEnd.manager.on_shutdown)
        
        self.btn_exit.bind("<Enter>",lambda event:self.hover(self.btn_exit))
        self.btn_exit.bind("<Leave>",lambda event:self.unhover(self.btn_exit))
        self.btn_exit.configure(**self.btn_style_normal)

        self.btn_exit.place(
            x=800,
            y=h - self.padding["page_padding_buttons_y"]
            - self.btn_style_normal["height"]
        )

    def change_language(self,lang):
        super().change_language(lang)

        self.btn_exit.configure(
            text=self.text["pagetext"]["end"]["button_exit"][self.language]
        )
        
        self.label_text1.configure(
            text=self.text["pagetext"]["end"]["text_1"][self.language]
        )