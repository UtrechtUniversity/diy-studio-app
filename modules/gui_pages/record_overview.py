# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

import customtkinter as ctk
import logging
from copy import copy
from CTkListbox import CTkListbox
from modules.gui_pages.base import PageBase
from PIL import Image

logger = logging.getLogger(__name__)


class PageRecordOverview(PageBase):
    dir_good = "good/"
    dir_bad = "bad/"
    has_recorded = False

    def __init__(self, parent, ui_elements):
        super().__init__(parent, ui_elements)
        
        self.data = []
        if PageRecordOverview.manager.gui_rec_buttons_enabled:
            self.setup_btn_forward()
            self.set_unlock_forward()
        self.setup_btn_back()

        # CUSTOM CODE FOR THIS PAGE
        self._check_after_id = None
        self.setup_title_by_pagename("record_overview")

        # Copy style for button with grey background
        self.btn_style_normal_custom = copy(ui_elements[3])
        self.btn_style_hover_custom = copy(ui_elements[4])
        self.btn_style_locked_custom = copy(ui_elements[5])

        self.btn_style_normal_custom["bg_color"] = self.colors["bg_content"]
        self.btn_style_hover_custom["bg_color"] = self.colors["bg_content"]
        self.btn_style_locked_custom["bg_color"] = self.colors["bg_content"]

        col_x = 200

        if PageRecordOverview.has_recorded:
            which_text = "b"
        else:
            which_text = "a"

        # TEXTTITLE 1 - DYNAMIC
        self.label_title1 = ctk.CTkLabel(
            self,
            text=self.text["pagetext"]["record_overview"]["texttitle_1"+which_text][self.language],
            width=400,
            height=34,
        )
        self.label_title1.configure(**self.texttitle_style)
        self.label_title1.place(x=col_x,y=200)

        # TEXT 1 - DYNAMIC
        self.label_text1 = ctk.CTkLabel(
            self,
            text=self.text["pagetext"]["record_overview"]["text_1"+which_text][self.language],
            width=400,
            height=140,
            wraplength=400
        )
        self.label_text1.configure(**self.text_style)
        self.label_text1.place(x=col_x, y=234)
        
        # TEXTTITLE 2 - DYNAMIC
        self.label_title2 = ctk.CTkLabel(
            self,
            text=self.text["pagetext"]["record_overview"]["texttitle_2"+which_text][self.language],
            width=400,
            height=34,
        )
        self.label_title2.configure(**self.texttitle_style)
        self.label_title2.place(x=col_x,y=370)

        # TEXT 2 - DYNAMIC
        self.label_text2 = ctk.CTkLabel(
            self,
            text=self.text["pagetext"]["record_overview"]["text_2"+which_text][self.language],
            width=400,
            height=140,
            wraplength=400
        )
        self.label_text2.configure(**self.text_style)
        self.label_text2.place(x=col_x, y=404)
        
        # TEXTTITLE 3 - STATIC
        self.label_title3 = ctk.CTkLabel(
            self,
            text=self.text["pagetext"]["record_overview"]["texttitle_3"][self.language],
            width=400,
            height=34,
        )
        self.label_title3.configure(**self.texttitle_style)
        self.label_title3.place(x=col_x,y=530)

        # TEXT 3 - STATIC
        self.label_text3 = ctk.CTkLabel(
            self,
            text=self.text["pagetext"]["record_overview"]["text_3"][self.language],
            width=400,
            wraplength=400
        )
        self.label_text3.configure(**self.text_style)
        self.label_text3.place(x=col_x, y=564)

        # LISTBOX
        self.listbox = CTkListbox(
            self,
            width=800,
            height=400,)
        self.listbox.configure(**self.listbox_style)
        self.listbox.configure(bg_color = self.colors["bg_content"],
                               fg_color = self.colors["bg_content"],
                               hover_color = self.colors["primary"])
        self.listbox.place(x=850, y=200)

        # TEXT ABOVE LISTBOX
        self.label_text4 = ctk.CTkLabel(
            self,
            text=self.text["pagetext"]["record_overview"]["text_4"][self.language],
            width=400,
            height=140,
            wraplength=400
        )
        self.label_text4.configure(**self.text_style)
        self.label_text4.configure(justify="center",compound="center", anchor="center")
        
        # Only place this text before any recordings have happened
        if not PageRecordOverview.has_recorded:
            self.label_text4.place(x=1050, y=330)
        
        # Record icon
        self.img_rec_icon = ctk.CTkImage(Image.open(
            "assets/static/record_button.png"), size=(141, 141))
        self.label_img_rec_icon = ctk.CTkLabel(
            self,
            text="",
            image=self.img_rec_icon,
            width=141,
            height=141
        )
        self.label_img_rec_icon.place(x=650, y=360)

    def _start_checking_uploads(self):
        manager = PageRecordOverview.manager

        if self._check_after_id is not None:
            # Check is happening already
            return
        
        self.data = manager.route_call("cloud_manager", "uploads")

        self._check_after_id = manager.schedule_task(
            0, self._update_upload_data
        )

    def stop_checking_uploads(self):
        after_id = self._check_after_id
        if after_id is not None:
            logger.info(
                f"PageRecordOverview : stop checking uploads : {after_id}"
            )
            try:
                PageRecordOverview.manager.cancel_task(after_id)
            except Exception:
                pass
            self._check_after_id = None

    def _update_upload_data(self):
        manager = PageRecordOverview.manager
        self.data = manager.route_call("cloud_manager", "uploads")

        if len(self.data) > 0:

            self.clear_listbox()

            for i in range(len(self.data)-1):
                self.listbox.insert(
                    i,
                    self.data[i].file_name
                    + " - "
                    + self.data[i].get_status()
                )

            self.listbox.insert(
                "END",
                self.data[-1].file_name
                + " - "
                + self.data[-1].get_status()
            )

        if (
            not manager.route_call("cloud_manager", "all_uploads_done")
            and self._check_after_id is not None
        ):
            self._check_after_id = manager.schedule_task(
                1000, self._update_upload_data
            )
        else:
            self._check_after_id = None

    def change_language(self,lang):
        super().change_language(lang)

        if PageRecordOverview.has_recorded:
            which_text = "b"
        else:
            which_text = "a"

        self.label_title1.configure(
            text=self.text["pagetext"][self.pagename]["texttitle_1"+which_text][self.language]
        )  
        self.label_text1.configure(
            text=self.text["pagetext"][self.pagename]["text_1"+which_text][self.language]
        )  

        self.label_title2.configure(
            text=self.text["pagetext"][self.pagename]["texttitle_2"+which_text][self.language]
        )  
        self.label_text2.configure(
            text=self.text["pagetext"][self.pagename]["text_2"+which_text][self.language]
        )  

        self.label_title3.configure(
            text=self.text["pagetext"][self.pagename]["texttitle_3"][self.language]
        )  
        self.label_text3.configure(
            text=self.text["pagetext"][self.pagename]["text_3"][self.language]
        )  

        self.label_text4.configure(
            text=self.text["pagetext"][self.pagename]["text_4"][self.language]
        )  
        
        if PageRecordOverview.has_recorded:
            self.label_text4.place_forget()

    def clear_listbox(self):
        self.listbox.delete("all")

    def refresh(self):
        self._start_checking_uploads()
        
        # Simplest way to refresh
        self.change_language(self.language)