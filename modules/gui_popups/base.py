# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

import customtkinter as ctk
from PIL import Image
from typing import ClassVar, TYPE_CHECKING

if TYPE_CHECKING:
    from modules.gui import GuiManager

class PopupBase(ctk.CTkFrame):
    manager: ClassVar["GuiManager"]
    btn_forward_unlock_timer = -1

    def __init__(self, parent, ui_elements, popup_style):
        self.language = ui_elements[0]
        self.padding = ui_elements[1]
        self.colors = ui_elements[2]
        self.btn_style_normal = ui_elements[3]
        self.btn_style_hover = ui_elements[4]
        self.btn_style_locked = ui_elements[5]
        self.text_style = ui_elements[6]
        self.title_style = ui_elements[7]
        self.popup_style = popup_style
        self.text = PopupBase.manager.dataText

        # weird hack cause checking if a basic button exists gives an error
        self.btn_forward_exists = False
        self.btn_back_exists = False
        self.title_exists = False

        ctk.CTkFrame.__init__(
            self,
            parent,
            corner_radius=0,
            width=1280,
            height=720
        )
        
        self.box_bg = ctk.CTkImage(
            Image.open("assets/static/popup_bg.png"),size=(1280,720)
        )
        self.label_bg = ctk.CTkLabel(self, image=self.box_bg, text="")
        self.label_bg.place(x=0, y=0)

    def setup_title_by_popupname(self, popupname):
        self.title_exists = True

        self.popupname = popupname

        self.label_title = ctk.CTkLabel(
            self,
            text=self.text["popuptext"][popupname]["title"][self.language],
            width=1280
        )
        self.label_title.configure(**self.title_style)
        self.label_title.place(x=0, y=40)

    def change_language(self,lang):
        self.language = lang

        if self.title_exists == True:
            self.label_title.configure(
                text=self.text[
                    "popuptext"
                ][self.popupname][
                    "title"
                ][self.language]
            )

    def refresh(self):
        return
