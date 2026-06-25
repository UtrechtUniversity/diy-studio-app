# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

import customtkinter as ctk
from modules.gui_pages.base import PageBase

class PageLogin1(PageBase):
    # simple state manager
    # phase 1 : not logged in
    # phase 2 : logging in
    # phase 3 : authenticated
    # phase 4 : authenticated and uploads pending
    phase = 1
    
    def __init__(self, parent, ui_elements):
        super().__init__(parent, ui_elements)
        
        # CUSTOM CODE FOR THIS PAGE
        self.setup_title_by_pagename("login")

        self.showing = False
        self._width = 1784
        self._height = 663
        self._x = 68
        self._y = 117
        self.h = 1080-self.padding["page_padding_content_y"]
        
        self.label_text = ctk.CTkLabel(
            self,
            text=self.text["pagetext"]["login"][(
                "text_"
                + str(PageLogin1.phase)
            )][self.language],
            width=800,
            wraplength=800,
            height=40,
        )
        self.label_text.configure(**self.text_style)
        self.label_text.configure(justify="center",compound="center", anchor="center")
        self.label_text.place(relx=0.5,y=350, anchor="c")
        
        # Start button
        self.btn_start = ctk.CTkButton(
            self, 
            text = self.text["pagebuttons"]["start"][self.language],
            command = PageLogin1.manager.on_forward)
        
        self.btn_start.configure(**self.btn_style_normal)
        self.btn_start.bind("<Enter>", lambda event:
            self.hover(self.btn_start))
        self.btn_start.bind("<Leave>", lambda event:
            self.unhover(self.btn_start))

        self.btn_start.place(
            x = (960 - (self.btn_style_normal["width"] / 2)),
            y = (self.h - self.padding["page_padding_buttons_y"]
                 - self.btn_style_normal["height"])
        )
        
        # Logout button
        self.btn_logout = ctk.CTkButton(
            self, 
            text = self.text["pagebuttons"]["logout"][self.language],
            command = PageLogin1.manager.on_logout)
        
        self.btn_logout.configure(**self.btn_style_normal)
        self.btn_logout.bind("<Enter>", lambda event:
            self.hover(self.btn_logout))
        self.btn_logout.bind("<Leave>", lambda event:
            self.unhover(self.btn_logout))

    def change_language(self, lang):
        super().change_language(lang)

        # Update the text
        self.label_text.configure(
            text=self.text["pagetext"]["login"][(
                "text_"
                + str(PageLogin1.phase)
            )][self.language]
        )

        # Update logout button text
        self.btn_logout.configure(
            text = self.text["pagebuttons"]["logout"][self.language]
        )

    def get_auth_status(self):
        return True if PageLogin1.phase >= 3 else False

    def set_auth_failed(self, err):
        if err == 1:
            # Timeout
            self.label_text.configure(
                text=self.text["pagetext"]["login"][("text_5")][self.language]
            )
        if err == 0:
            # Other error
            self.label_text.configure(
                text=self.text["pagetext"]["login"][("text_6")][self.language]
            )

    def set_authenticated(self):
        PageLogin1.phase = 3
        self.label_text.configure(
            text=self.text["pagetext"]["login"][(
                "text_"
                + str(PageLogin1.phase)
            )][self.language]
        )
        # Remove start button
        self.btn_start.place_forget()
        self.btn_logout.place(
            x = (960 - (self.btn_style_normal["width"] / 2)),
            y = (self.h - self.padding["page_padding_buttons_y"]
                 - self.btn_style_normal["height"])
        )

    def logout(self):
        PageLogin1.phase = 1
        self.label_text.configure(
            text=self.text["pagetext"]["login"][(
                "text_"
                + str(PageLogin1.phase)
            )][self.language]
        )
        self.btn_logout.place_forget()
        self.btn_start.place(
            x = (960 - (self.btn_style_normal["width"] / 2)),
            y = (self.h - self.padding["page_padding_buttons_y"]
                 - self.btn_style_normal["height"])
        )
        
    def on_uploads_pending(self):
        PageLogin1.phase = 4
        self.label_text.configure(
            text=self.text["pagetext"]["login"][(
                "text_"
                + str(PageLogin1.phase)
            )][self.language]
        )
        
    def refresh(self):
        pass