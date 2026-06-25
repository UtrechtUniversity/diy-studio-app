# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

import customtkinter as ctk
from PIL import Image
from modules.gui_pages.base import PageBase

class PageVideotype1(PageBase):
    IMAGE_NAMES = ["videotype1", "videotype2"]

    def __init__(self, parent, ui_elements):
        super().__init__(parent, ui_elements)
        
        self.setup_btn_forward()
        self.setup_btn_back()

        # CUSTOM CODE FOR THIS PAGE
        self.setup_title_by_pagename("videotype_1")

        self.btns = []
        self.texts = []
        self.btns_normal = []
        self.btns_hover = []
        self.btns_active = []
        self.prev = -1
        self.show_gs_btn = False
        
        # LOAD IMAGES
        i = 0

        for n in self.IMAGE_NAMES:

            self.btns_normal.append(ctk.CTkImage(Image.open(
                "assets/buttons/btn_" + n + "_normal.png"
                ), size=(648, 418)))
            self.btns_hover.append(ctk.CTkImage(Image.open(
                "assets/buttons/btn_" + n + "_hover.png"
                ), size=(648, 418)))
            self.btns_active.append(ctk.CTkImage(Image.open(
                "assets/buttons/btn_" + n + "_active.png"
                ), size=(648, 418)))

            b = ctk.CTkButton(
                    self,
                    text="",
                    fg_color=self.colors["bg_content"],
                    hover=self.colors["bg_content"],
                    image=self.btns_normal[i],
                    border_width=0,
                    corner_radius=0,
                    command=lambda i=i:PageVideotype1.manager.set_videotype(i))
            
            b.place(
                    # 480 - 324
                    x=216+(i*840),
                    y=200
                    )
            
            label = ctk.CTkLabel(
                self,
                text=self.text["pagetext"]["videotype_1"]["option_"+str(i+1)][
                        self.language
                ],
                cursor="hand2",
                width=648
            )

            label.configure(**self.text_style)

            label.configure(
                justify="center", compound="center", anchor="center"
            )

            label.bind(
                "<Button-1>",
                lambda event,
                i=i:PageVideotype1.manager.set_videotype(i)
            )

            self.set_binding(label, i, True)

            label.place(
                    x=216+(i*840),
                    y=640
            )
            
            self.texts.append(label)
            self.set_binding(b, i, True)
            self.btns.append(b)
            i += 1

        # Green screen button
        self.btn_greenscreen = ctk.CTkButton(
            self, 
            text = self.text["pagetext"]["videotype_1"]["option_gs"][
                self.language
            ],
            command = lambda: PageVideotype1.manager.set_videotype(2))
        
        self.btn_greenscreen.configure(**self.btn_style_normal)
        self.btn_greenscreen.bind("<Enter>", lambda event:
            self.hover(self.btn_greenscreen))
        self.btn_greenscreen.bind("<Leave>", lambda event:
            self.unhover(self.btn_greenscreen))

    def set_binding(self, btn, index, bind):
        if bind == True:
            btn.bind(
                "<Enter>", lambda event, index=index:self.hover_image(index)
            )

            btn.bind(
                "<Leave>", lambda event, index=index:self.unhover_image(index)
            )
        else:
            btn.unbind("<Enter>")
            btn.unbind("<Leave>")

    def set_active_videotype(self, index):
        self.set_unlock_forward()

        if index == 2:
            index = 0

        if self.prev != -1:
            self.btns[self.prev].configure(image=self.btns_normal[self.prev])
            self.set_binding(
                self.btns[self.prev],
                self.prev,
                True
            )
            self.set_binding(
                self.texts[self.prev],
                self.prev,
                True
            )

        self.btns[index].configure(image=self.btns_active[index])
        self.set_binding(
            self.btns[index],
            index,
            False
        )
        self.set_binding(
            self.texts[index],
            index,
            False
        )

        self.prev = index

    def hover_image(self, index):
        self.btns[index].configure(image=self.btns_hover[index])

    def unhover_image(self, index):
        self.btns[index].configure(image=self.btns_normal[index])

    def change_language(self,lang):
        super().change_language(lang)

        self.language = lang

        self.texts[0].configure(
            text=self.text["pagetext"]["videotype_1"]["option_1"][
                self.language
            ]
        )
        self.texts[1].configure(
            text=self.text["pagetext"]["videotype_1"]["option_2"][
                self.language
            ]
        )
        self.btn_greenscreen.configure(
            text=self.text["pagetext"]["videotype_1"]["option_gs"][
                self.language
            ]
        )

    def toggle_greenscreen_btn(self):
        if self.show_gs_btn:
            self.btn_greenscreen.place_forget()
            self.show_gs_btn = False
        else:
            self.btn_greenscreen.place(
                x = (960 - (self.btn_style_normal["width"] / 2)),
                y = (824)
            )
            self.show_gs_btn = True
