# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

import customtkinter as ctk
from PIL import Image
from modules.gui_pages.base import PageBase

class PageVideotype2(PageBase):
    IMAGE_NAMES = ["blue", "cream", "green", "yellow",
                   "photo1", "photo2", "photo3", "photo4"]

    def __init__(self, parent, ui_elements):
        super().__init__(parent, ui_elements)
        
        self.setup_btn_forward()
        
        # Because first bg is selected, this button is always unlocked
        self.set_unlock_forward()

        self.setup_btn_back()

        # CUSTOM CODE FOR THIS PAGE
        self.setup_title_by_pagename("videotype_2")

        self.btns = []
        self.btns_normal = []
        self.btns_hover = []
        self.btns_active = []
        self.prev = -1

        # LOAD IMAGES
        for n in self.IMAGE_NAMES:
            self.btns_normal.append(ctk.CTkImage(Image.open(
                "assets/buttons/btn_static_" + n + "_normal.png"
            ), size=(400, 226)))
            
            self.btns_hover.append(ctk.CTkImage(Image.open(
                "assets/buttons/btn_static_" + n + "_hover.png"
            ), size=(400, 226)))
            
            self.btns_active.append(ctk.CTkImage(Image.open(
                "assets/buttons/btn_static_" + n + "_selected.png"
            ), size=(400, 226)))

        # BUTTONS
        image_width = 400
        image_padding_x = 40
        image_height = 200
        image_padding_y = 80

        for y in range(0, 2):
            for x in range(0, 4):
                i = y * 4 + x

                b = ctk.CTkButton(
                    self,
                    text="",
                    fg_color=self.colors["bg_content"],
                    hover=self.colors["bg_content"],
                    image=self.btns_normal[i],
                    border_width=0,
                    corner_radius=0,
                    command=lambda i=i:PageVideotype2.manager.set_videobg(i))

                b.place(
                    x=30+self.padding["all_padding_x"]
                    +(x*(image_width+image_padding_x)),
                    y=40+self.padding["page_padding_title_height"]
                    +(y*(image_height+image_padding_y))
                )
                                
                self.set_binding(b, i, True)
                self.btns.append(b)


    def set_binding(self, btn, index, bind):
        #logger.info("set_binding " + str(btn))
        if bind == True:
            btn.bind("<Enter>",
                     lambda event,index=index:self.hover_image(index))
            btn.bind("<Leave>",
                     lambda event,index=index:self.unhover_image(index))
        else:
            btn.unbind("<Enter>")
            btn.unbind("<Leave>")

    def set_active_videobg(self, index):
        if self.prev != -1:
            self.btns[self.prev].configure(image=self.btns_normal[self.prev])
            self.set_binding(
                self.btns[self.prev],
                self.prev,
                True
            )

        self.btns[index].configure(image=self.btns_active[index])
        self.set_binding(
            self.btns[index],
            index,
            False
        )

        self.prev = index

    def set_active_bg(self, index):
        self.btns[index].configure(image=self.btns_active[index])

    def hover_image(self, index):
        self.btns[index].configure(image=self.btns_hover[index])

    def unhover_image(self, index):
        self.btns[index].configure(image=self.btns_normal[index])
