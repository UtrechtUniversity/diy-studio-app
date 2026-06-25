# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

import customtkinter as ctk
from PIL import Image
from modules.gui_pages.base import PageBase
from copy import copy

class PageRecordActive(PageBase):
    SHOW_LOG = False

    logged_text = "Start log"

    def __init__(self, parent, ui_elements, text_big_style):

        super().__init__(parent, ui_elements)
        
        self.text_big_style = text_big_style
        self.arrow_pos = [250, 200]

        # CUSTOM CODE FOR THIS PAGE

        self.setup_title_by_pagename("record_active")

        self.current_state_index = 0

        # Copy style for button with grey background
        self.btn_style_normal_custom = copy(ui_elements[3])
        self.btn_style_hover_custom = copy(ui_elements[4])
        self.btn_style_locked_custom = copy(ui_elements[5])

        self.btn_style_normal_custom["bg_color"] = self.colors[
            "bg_content"
        ]

        self.btn_style_hover_custom["bg_color"] = self.colors[
            "bg_content"
        ]

        self.btn_style_locked_custom["bg_color"] = self.colors[
            "bg_content"
        ]

        # ARROW
        self.img_arrow = ctk.CTkImage(Image.open(
            "assets/static/arrow-left-small.png"), size=(121, 122))
        
        self.label_img_arrow = ctk.CTkLabel(
            self,
            text="",
            image=self.img_arrow,
            width=121,
            height=122,
            bg_color=self.colors["bg_content"]
        )
        
        if self.SHOW_LOG is False:
            self.label_img_arrow.place(
                x=self.arrow_pos[0],
                y=self.arrow_pos[1]
            )
        
        # FEEDBACK TEXT
        self.label_text1 = ctk.CTkLabel(
            self,
            text=self.text["pagetext"]["record_active"]["text_1_countdown"][
                self.language
            ],
            width=1000,
            wraplength=1000
        )

        self.label_text1.configure(**self.text_big_style)

        self.label_text2 = ctk.CTkLabel(
            self,
            text=self.text["pagetext"]["record_active"]["text_2"][
                self.language
            ],
            width=500,
            wraplength=500
        )

        self.label_text2.configure(**self.text_style)

        self.label_text2.configure(
            justify="center", compound="center", anchor="center"
        )

        if self.SHOW_LOG is False:
            self.label_text1.place(x=480, y=350)

        # LOG
        self.label_log = ctk.CTkLabel(
            self,
            text=self.logged_text,
            width=400,
            justify="left",
            wraplength=400
        )
        self.label_log.configure(**self.text_style)
        
        if self.SHOW_LOG is True:
            self.label_log.place(x=750, y=150)

        # STOP
        self.btn_stop = ctk.CTkButton(
            self, 
            text="Stop",
            command=lambda: PageRecordActive.manager.route_call(
                "recorder_manager", "stop_record")
        )
        
        # First load normal as default to get all settings
        self.btn_stop.configure(**self.btn_style_normal)
        self.set_unlock_stop(False)

        if PageRecordActive.manager.gui_rec_buttons_enabled:
            self.btn_stop.place(
                x=800,
                y=820
            )

        # self.log("Init done")

    def log(self, txt):
        self.logged_text = self.logged_text + "\n" + txt
        self.label_log.configure(text=self.logged_text)

    def update_text(self, index):
        # 0 countdown
        # 1 recording
        # 2 processing
        self.current_state_index = index

        if self.SHOW_LOG is False:
            match index:
                case 0:
                    self.label_img_arrow.place(
                        x=self.arrow_pos[0],
                        y=self.arrow_pos[1]
                    )
                    
                    self.label_text1.configure(
                        text=self.text["pagetext"]["record_active"][
                            "text_1_countdown"
                        ][self.language]
                    )
                    self.label_text1.place(x=480, y=330)
                case 1:
                    self.label_img_arrow.place_forget()
                    self.label_text1.configure(
                        text=self.text["pagetext"]["record_active"][
                            "text_1_recording"
                        ][self.language]
                    )
                    self.label_text1.place(x=480, y=350)
                    self.label_text2.place(x=730, y=600)
                case 2:
                    self.label_text1.configure(
                        text=self.text["pagetext"]["record_active"][
                            "text_1_processing"
                        ][self.language]
                    )
                    self.label_text1.place(x=480, y=350)
                    self.label_text2.place_forget()
        
    def set_unlock_stop(self, unlock):
        if unlock == True:
            self.btn_stop.configure(**self.btn_style_normal)
            self.btn_stop.bind(
                "<Enter>",lambda event: self.hover(self.btn_stop))
            self.btn_stop.bind(
                "<Leave>",lambda event: self.unhover(self.btn_stop))
        
        else:
            self.btn_stop.configure(**self.btn_style_locked)
            self.btn_stop.unbind("<Enter>")
            self.btn_stop.unbind("<Leave>")

    def hover_custom(self, btn):
        btn.configure(**self.btn_style_hover)

    def unhover_custom(self, btn):
        btn.configure(**self.btn_style_normal)
        
    def refresh(self):
        self.logged_text = ""
        self.label_log.configure(text=self.logged_text)

    def change_language(self, lang):
        super().change_language(lang)
        
        self.label_text2.configure(
            text=self.text["pagetext"][self.pagename]["text_2"][self.language]
        )  

        self.update_text(self.current_state_index)