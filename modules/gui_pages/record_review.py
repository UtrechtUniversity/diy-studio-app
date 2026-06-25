# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

import customtkinter as ctk
import pywinstyles
import re
from copy import copy
from modules.gui_pages.base import PageBase


class PageRecordReview(PageBase):
    scrubbing = False
    video_playhead = 0.0 # range 0 - 1

    def __init__(self, parent, ui_elements):
        super().__init__(parent, ui_elements)
        
        # CUSTOM CODE FOR THIS PAGE
        self.setup_title_by_pagename("record_review")

        # Copy style for button with grey background
        self.btn_style_normal_custom = copy(ui_elements[3])
        self.btn_style_hover_custom = copy(ui_elements[4])
        self.btn_style_locked_custom = copy(ui_elements[5])

        self.btn_style_normal_custom["bg_color"] = self.colors["bg_content"]
        self.btn_style_hover_custom["bg_color"] = self.colors["bg_content"]
        self.btn_style_locked_custom["bg_color"] = self.colors["bg_content"]

        # TRANSPARENT
        self.label_transparent = ctk.CTkLabel(
            self,
            width=938,
            height=570,
            text="",
            fg_color="red"
        )
        self.label_transparent.place(x=491,y=164)

        # Get placement of basic buttons
        h = 1080-self.padding["page_padding_content_y"]

        self.placeholder_text = self.text["pagetext"]["record_review"]["entry_videoname"][self.language]
        self.btn_accept_unlocked = False # to stop double binding

        # REJECT BUTTON
        self.btn_reject = ctk.CTkButton(
            self, 
            text=self.text["pagetext"]["record_review"]["button_reject"][self.language])
        
        self.btn_reject.configure(**self.btn_style_normal) 
        
        self.btn_reject.bind("<Enter>",   
            lambda event: self.hover(self.btn_reject))
        self.btn_reject.bind("<Leave>",
            lambda event: self.unhover(self.btn_reject))
        self.btn_reject.bind("<1>",
            lambda event: PageRecordReview.manager.on_video_reviewed(False))

        self.btn_reject.place(
            x=self.padding["all_padding_x"],
            y=h-self.padding["page_padding_buttons_y"]
            -self.btn_style_normal["height"]
            )

        # ACCEPT BUTTON
        self.btn_accept = ctk.CTkButton(
            self, 
            text=self.text["pagetext"]["record_review"]["button_accept"][self.language])
        
        self.btn_accept.configure(**self.btn_style_normal) 

        self.btn_accept.bind("<Enter>",
            lambda event: self.hover(self.btn_accept))
        self.btn_accept.bind("<Leave>",
            lambda event: self.unhover(self.btn_accept))
        self.btn_accept.bind("<1>", command=self.on_accept)

        self.btn_accept.place(
            x=1920-self.padding["all_padding_x"]
            -self.btn_style_normal["width"],
            y=h-self.padding["page_padding_buttons_y"]
            -self.btn_style_normal["height"]
            )
        
        # ENTRY
        self.entry_var = ctk.StringVar(value=self.placeholder_text)

        self.entry_filename = ctk.CTkEntry(self, 
            state=ctk.NORMAL,
            width=370,
            height=76,
            border_width=0,
            corner_radius=38,
            border_color="black",
            placeholder_text=self.placeholder_text, # doesnt work cause of stringvar
            placeholder_text_color="black",
            textvariable=self.entry_var,
            font=self.btn_style_normal["font"]
        )

        self.entry_filename.bind("<Enter>", lambda event:self.hover_entry(self.entry_filename))
        self.entry_filename.bind("<Leave>", lambda event:self.unhover_entry(self.entry_filename))
        self.entry_filename.bind("<1>", self.on_entry_focus)

        self.entry_filename.place(
            x=750,
            y=h-self.padding["page_padding_buttons_y"]-self.btn_style_normal["height"]
            )
        
        # HITBOX FOR UNFOCUS OF TEXTBOX
        # when Entry is focused, the hitbox is set transparency 0.01 to make it clickable
        self.hitbox = ctk.CTkFrame(
            self,
            width=1920,
            height=800,
            )
        
        pywinstyles.set_opacity(self.hitbox,0)
        self.hitbox.place(x=0,y=0)
        self.hitbox.bind("<1>", lambda event:self.unfocus_entry())

    def on_accept(self, *args):
        filename_entry = self.entry_var.get()
        if filename_entry == self.placeholder_text or filename_entry == "":
            PageRecordReview.manager.on_video_reviewed(True)
        else:
            # Filter anything that is not a-z, A-Z, 0-9,
            # a space, dash or parentheses
            filtered_filename_entry = re.sub(
                r"[^a-zA-Z0-9 _\-()]", "", filename_entry
            )
            # Limit filename to 251 chars + extension = 255 characters
            PageRecordReview.manager.on_video_reviewed(
                True, filtered_filename_entry[:251])

    def unfocus_entry(self):
        self.hitbox.focus_set()
        pywinstyles.set_opacity(self.hitbox,0)

        if self.entry_var.get() == "":
            self.entry_var.set(self.placeholder_text)

    def on_entry_focus(self, *args):
        pywinstyles.set_opacity(self.hitbox,0.01)

        if self.entry_var.get() == self.placeholder_text:
            self.entry_var.set("")

    def hover_custom(self, btn):
        btn.configure(**self.btn_style_hover_custom)

    def unhover_custom(self, btn):
        btn.configure(**self.btn_style_normal_custom)

    def hover_entry(self, btn):
        btn.configure(border_width=self.btn_style_hover["border_width"]) 

    def unhover_entry(self, btn):
        btn.configure(border_width=0)

    def change_language(self,lang):
        super().change_language(lang)

        if self.entry_var.get() == self.placeholder_text:
            self.entry_var.set(
                self.text["pagetext"]["record_review"]["entry_videoname"][self.language]
            )

        self.placeholder_text = self.text["pagetext"]["record_review"]["entry_videoname"][self.language]

        self.btn_reject.configure(
            text=self.text["pagetext"]["record_review"]["button_reject"][self.language]
        )
        self.btn_accept.configure(
            text=self.text["pagetext"]["record_review"]["button_accept"][self.language]
        )
 
    def refresh(self):
        self.entry_var.set("")
        self.entry_var.set(self.placeholder_text)
