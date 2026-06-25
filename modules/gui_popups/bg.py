# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

import customtkinter as ctk
import pywinstyles

class PopupBg(ctk.CTkFrame):
    def __init__(self, parent):
        ctk.CTkFrame.__init__(
            self, 
            parent, 
            corner_radius=0, 
            width=1920, 
            height=1080,
            fg_color="black"
            )
        
        pywinstyles.set_opacity(self, value=0.5)
        