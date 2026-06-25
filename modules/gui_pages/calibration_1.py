# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

import customtkinter as ctk
from PIL import Image
from modules.gui_pages.base import PageBase

class PageCalibration1(PageBase):
    def __init__(self, parent, ui_elements):
        super().__init__(parent, ui_elements)

        self.setup_btn_forward()
        self.set_unlock_forward()
        self.setup_btn_back()

        # CUSTOM CODE FOR THIS PAGE
        self.setup_title_by_pagename("calibration_1")

        col1_x = 452
        col2_x = 750
        col3_x = 1240

        # 1e COLUMN - 2x IMAGE

        self.img1 = ctk.CTkImage(Image.open(
            "assets/static/calibration_1_img_1.png"
            ), size=(452, 183))
        self.label_img1 = ctk.CTkLabel(
            self,
            text="",
            image=self.img1,
            width=col1_x,
            height=183
        )
        self.label_img1.place(x=184, y=150)

        self.img2 = ctk.CTkImage(Image.open(
            "assets/static/calibration_1_img_2.png"
            ), size=(452, 255))
        self.label_img2 = ctk.CTkLabel(
            self,
            text="",
            image=self.img2,
            width=col1_x,
            height=255
        )
        self.label_img2.place(x=184, y=400)

        # 2e COLUMN - 3x TITLE/TEXT

        self.label_title1 = ctk.CTkLabel(
            self,
            text=self.text["pagetext"]["calibration_1"]["texttitle_1"][self.language],
            width=400,
            height=30,
        )
        self.label_title1.configure(**self.texttitle_style)
        self.label_title1.place(x=col2_x,y=150)

        self.label_text1 = ctk.CTkLabel(
            self,
            text=self.text["pagetext"]["calibration_1"]["text_1"][self.language],
            width=388,
            wraplength=388,
            height=94
        )
        self.label_text1.configure(**self.text_style)
        self.label_text1.place(x=col2_x,y=184)



        self.label_title2 = ctk.CTkLabel(
            self,
            text=self.text["pagetext"]["calibration_1"]["texttitle_2"][self.language],
            width=400,
            height=30,

        )
        self.label_title2.configure(**self.texttitle_style)
        self.label_title2.place(x=col2_x,y=350)

        self.label_text2 = ctk.CTkLabel(
            self,
            text=self.text["pagetext"]["calibration_1"]["text_2"][self.language],
            width=388,
            wraplength=388,
            height=120
        )
        self.label_text2.configure(**self.text_style)
        self.label_text2.place(x=col2_x, y=384)


        self.label_title3 = ctk.CTkLabel(
            self,
            text=self.text["pagetext"]["calibration_1"]["texttitle_3"][self.language],
            width=400,
            height=30,

        )
        self.label_title3.configure(**self.texttitle_style)
        self.label_title3.place(x=col2_x,y=570)


        self.label_text3 = ctk.CTkLabel(
            self,
            text=self.text["pagetext"]["calibration_1"]["text_3"][self.language],
            width=388,
            wraplength=388,
            height=96
        )
        self.label_text3.configure(**self.text_style)
        self.label_text3.place(x=col2_x, y=604)

        # 3e COLUMN - 1x IMAGE

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
        self.label_img1.place(x=col3_x, y=150)


    def change_language(self,lang):
        super().change_language(lang)

        self.label_text1.configure(
            text=self.text["pagetext"][self.pagename]["text_1"][self.language]
        )
        self.label_text2.configure(
            text=self.text["pagetext"][self.pagename]["text_2"][self.language]
        )
        self.label_text3.configure(
            text=self.text["pagetext"][self.pagename]["text_3"][self.language]
        )

        self.label_title1.configure(
            text=self.text["pagetext"][self.pagename]["texttitle_1"][self.language]
        )
        self.label_title2.configure(
            text=self.text["pagetext"][self.pagename]["texttitle_2"][self.language]
        )
        self.label_title3.configure(
            text=self.text["pagetext"][self.pagename]["texttitle_3"][self.language]
        )
