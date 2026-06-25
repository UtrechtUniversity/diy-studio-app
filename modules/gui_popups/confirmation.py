# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

import customtkinter as ctk
from modules.gui_popups.base import PopupBase
from copy import copy


class PopupConfirmation(PopupBase):
    def __init__(self, parent, ui_elements, popup_style):
        super().__init__(parent, ui_elements, popup_style)

        # CUSTOM CODE FOR THIS PAGE
        self.type = 1 # default 1

        # Copy style for button with grey background
        self.btn_style_normal_custom = copy(ui_elements[3])
        self.btn_style_hover_custom = copy(ui_elements[4])

        self.btn_style_normal_custom["bg_color"] = self.colors["bg_content"]
        self.btn_style_hover_custom["bg_color"] = self.colors["bg_content"]

        self.setup_title_by_popupname("confirmation_" + str(self.type))

        self.label_text1 = ctk.CTkLabel(
            self,
            text=self.text["popuptext"]["confirmation_" + str(self.type)]["text_1"][self.language],
            width=400,
            wraplength=400,
            height=140
        )
        self.label_text1.configure(**self.popup_style)
        self.label_text1.place(x=440,y=168)

        self.btn_confirm = ctk.CTkButton(
            self, 
            text=self.text["popupbuttons"]["confirm"][self.language],
            command=PopupConfirmation.manager.on_popup_confirm
        )
        
        self.btn_confirm.configure(**self.btn_style_normal_custom) 
        self.btn_confirm.bind("<Enter>", lambda event: self.hover(self.btn_confirm))
        self.btn_confirm.bind("<Leave>", lambda event: self.unhover(self.btn_confirm))
        self.btn_confirm.place(x=830,y=580)

        self.btn_cancel = ctk.CTkButton(
            self, 
            text=self.text["popupbuttons"]["cancel"][self.language],
            command=PopupConfirmation.manager.on_popup_cancel
        )
        
        self.btn_cancel.configure(**self.btn_style_normal_custom) 
        self.btn_cancel.bind("<Enter>", lambda event: self.hover(self.btn_cancel))
        self.btn_cancel.bind("<Leave>", lambda event: self.unhover(self.btn_cancel))
        self.btn_cancel.place(x=70,y=580)
        
    def set_type(self, t):
        self.type = t
        self.popupname = "confirmation_" + str(self.type)
        self.change_language(self.language) # easiest way to refresh content

    def hover(self, btn):
        btn.configure(**self.btn_style_hover_custom)

    def unhover(self, btn):
        btn.configure(**self.btn_style_normal_custom)

    def change_language(self,lang):

        super().change_language(lang)

        self.label_text1.configure(text=self.text["popuptext"][self.popupname]["text_1"][self.language])
        self.btn_confirm.configure(text=self.text["popupbuttons"]["confirm"][self.language])
        self.btn_cancel.configure(text=self.text["popupbuttons"]["cancel"][self.language])
