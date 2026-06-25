# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

import customtkinter as ctk
from PIL import Image
from typing import ClassVar, TYPE_CHECKING

if TYPE_CHECKING:
    from modules.gui import GuiManager

class PageBase(ctk.CTkFrame):
    btn_forward_unlock_timer = -1
    manager: ClassVar["GuiManager"]
    
    def __init__(self, parent, ui_elements):
        self.window = parent
        self.language = ui_elements[0]
        self.padding = ui_elements[1]
        self.colors = ui_elements[2]
        self.btn_style_normal = ui_elements[3]
        self.btn_style_hover = ui_elements[4]
        self.btn_style_locked = ui_elements[5]
        self.text_style = ui_elements[6]
        self.title_style = ui_elements[7]
        self.texttitle_style = ui_elements[8]
        self.listbox_style = ui_elements[9]
        self.text = PageBase.manager.dataText

        # weird hack cause checking if a basic button exists
        # gives an error
        self.btn_forward_exists = False
        self.btn_back_exists = False
        self.title_exists = False

        ctk.CTkFrame.__init__(
            self, 
            parent, 
            corner_radius=0, 
            width=1920, 
            height=1080-self.padding["page_padding_content_y"], 
            fg_color=self.colors["primary"]
            )
        
        self.box_bg = ctk.CTkImage(Image.open("assets/static/page_bg.png"),
                                   size=(1800, 790))
        self.label_bg = ctk.CTkLabel(self, image=self.box_bg, text="")
        self.label_bg.place(x=self.padding["all_padding_x"], y=0)

    def setup_title_by_pagename(self, pagename):
        self.title_exists = True
        self.pagename = pagename

        self.label_title = ctk.CTkLabel(
            self,
            text = self.text["pagetext"][pagename]["title"][self.language],
            width = 1920 - (2 * self.padding["all_padding_x"])
        )
        self.label_title.configure(**self.title_style)
        self.label_title.place(x = self.padding["all_padding_x"], y=40)

    def setup_btn_forward(self, timer = False):
        self.btn_forward_exists = True

        self.btn_forward = ctk.CTkButton(
            self, 
            text = self.text["pagebuttons"]["forward"][self.language],
            command = PageBase.manager.on_forward)
        
        # first load normal as default to get all settings
        self.btn_forward.configure(**self.btn_style_normal)
        self.btn_forward.configure(**self.btn_style_locked)

        h = 1080-self.padding["page_padding_content_y"]

        self.btn_forward.place(
            x = (1920 - self.padding["all_padding_x"]
                 - self.btn_style_normal["width"]),
            y = (h - self.padding["page_padding_buttons_y"]
                 - self.btn_style_normal["height"])
            )

        if timer == True:
            self.btn_forward_unlock_timer = 5

    def setup_btn_back(self):
        self.btn_back_exists = True

        self.btn_back = ctk.CTkButton(
            self, 
            text = self.text["pagebuttons"]["back"][self.language],
            command = PageBase.manager.on_back)
        
        self.btn_back.configure(**self.btn_style_normal)

        self.btn_back.bind("<Enter>", lambda event: self.hover(self.btn_back))
        self.btn_back.bind("<Leave>", lambda event:
            self.unhover(self.btn_back))

        h = 1080 - self.padding["page_padding_content_y"]

        self.btn_back.place(
            x = self.padding["all_padding_x"],
            y = (h - self.padding["page_padding_buttons_y"]
                 - self.btn_style_normal["height"])
            )
        
    def set_unlock_forward(self):
        self.btn_forward.configure(**self.btn_style_normal)
        self.btn_forward.bind("<Enter>", lambda event:
            self.hover(self.btn_forward))
        self.btn_forward.bind("<Leave>", lambda event:
            self.unhover(self.btn_forward))

    def set_relock_forward(self):
        self.btn_forward.configure(**self.btn_style_locked)
        self.btn_forward.unbind("<Enter>")
        self.btn_forward.unbind("<Leave>")

    def hover(self, btn):
        btn.configure(**self.btn_style_hover)

    def unhover(self, btn):
        btn.configure(**self.btn_style_normal)

    def change_language(self,lang):
        self.language = lang

        if self.btn_back_exists == True:
            self.btn_back.configure(
                text = self.text["pagebuttons"]["back"][self.language]
            )

        if self.btn_forward_exists == True:
            self.btn_forward.configure(
                text = self.text["pagebuttons"]["forward"][self.language]
            )

        if self.title_exists == True:
            self.label_title.configure(
                text = self.text["pagetext"][self.pagename]["title"][self.language]
            )

    def refresh(self):
        return
