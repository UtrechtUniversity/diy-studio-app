# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

import customtkinter as ctk
from copy import copy
from modules.gui_popups.base import PopupBase

class PopupError(PopupBase):
    def __init__(self, parent, ui_elements, popup_style):
        super().__init__(parent, ui_elements, popup_style)

        # CUSTOM CODE FOR THIS PAGE
        self.type = 101 # default 101

        # copy style for button with grey background
        self.btn_style_normal_custom = copy(ui_elements[3])
        self.btn_style_hover_custom = copy(ui_elements[4])
        self.btn_style_locked_custom = copy(ui_elements[3])

        self.btn_style_normal_custom["bg_color"] = self.colors["bg_content"]
        self.btn_style_hover_custom["bg_color"] = self.colors["bg_content"]
        self.btn_style_locked_custom["bg_color"] = self.colors["bg_content"]
        self.btn_style_locked_custom["state"] = ctk.DISABLED

        self.setup_title_by_popupname("error_" + str(self.type))

        self.label_text1 = ctk.CTkLabel(
            self,
            text=self.text["popuptext"]["error_" + str(self.type)]["text_1"][self.language],
            width=500,
            wraplength=500,
            height=140,
            justify="center",
            anchor="center"
        )
        self.label_text1.configure(**self.popup_style)
        self.label_text1.place(x=430, y=168)

        self.btn_accept = ctk.CTkButton(
            self, 
            text=self.text["popupbuttons"]["accept"][self.language],
            command=self._on_popup_accept
        )
        
        self.btn_accept.configure(**self.btn_style_normal_custom) 
        self.btn_accept.bind("<Enter>", lambda event:self.hover(self.btn_accept))
        self.btn_accept.bind("<Leave>", lambda event:self.unhover(self.btn_accept))
        self.btn_accept.place(
            x = (640 - (self.btn_style_normal["width"] / 2)),
            y = 580
        )

        self.btn_reboot_exists = False
        self.btn_reboot = ctk.CTkButton(
            self, 
            text=self.text["popupbuttons"]["reboot"][self.language],
            command=PopupError.manager.on_popup_reboot
        )
        self.btn_reboot.configure(**self.btn_style_locked_custom)

    def _on_popup_accept(self):
        """User clicked 'Accept' button and popup disappears"""
        # Stop any running timers
        self._stop_unlock_timer()
        PopupError.manager.on_popup_accept()

    def change_language(self,lang):
        super().change_language(lang)
        self.btn_accept.configure(text=self.text["popupbuttons"]["accept"][self.language])
        self.btn_reboot.configure(text=self.text["popupbuttons"]["reboot"][self.language])
        self.update_info(PopupError.manager.cur_errors)

    def hover(self, btn):
        btn.configure(**self.btn_style_hover_custom)

    def set_type(self, t):
        self.btn_reboot_exists = False # happens once per popup
        self.type = t
        self.popupname = "error_" + str(self.type)
        self.change_language(self.language) # easiest way to refresh content

    def unhover(self, btn):
        btn.configure(**self.btn_style_normal_custom)

    def update_info(self, error_list):
        """Display one or more errors"""
        header = self.text["popuptext"]["error_header"][self.language]
        content = ""
        num = len(error_list)
        i = 0

        for error in error_list:
            header += str(error)
            content += (
                self.text["popuptext"][
                    "error_" + str(error)
                ]["text_1"][self.language]
            )

            if i < (num - 1):
                header += ", "
                content += "\n"

            i += 1

        if self.btn_reboot_exists:
            content += "\n\n"
            content += (
                self.text["popuptext"]["error_reboot_info"][self.language]
            )

        content += "\n\n"
        content += self.text["popuptext"]["error_support_info"][self.language]

        self.label_title.configure(text=header)
        self.label_text1.configure(text=content, justify="center")

    # =============================
    # Shutdown button methods
    # =============================
    def _start_unlock_timer(self):
        if getattr(self, "_unlock_after_id", None) is not None:
            # There's already a timer
            return
        
        self._unlock_after_id = PopupError.manager.schedule_task(
            1000, self._tick
        )

    def _stop_unlock_timer(self):
        after_id = getattr(self, "_unlock_after_id", None)
        if after_id is not None:
            try:
                PopupError.manager.cancel_task(after_id)
            except Exception:
                pass
        self._unlock_after_id = None

    def _tick(self):
        self.btn_reboot_unlock_timer = self.btn_reboot_unlock_timer - 1
        self.btn_reboot.configure(
            text = self.text["popupbuttons"]["reboot"][self.language] + self._get_unlock_timer()
        )

        if self.btn_reboot_unlock_timer > 0:
            PopupError.manager.schedule_task(1000, self._tick)
        else:
            self._unlock_after_id = None
            self._set_unlock_shutdown()

    def _set_unlock_shutdown(self):
        self.btn_reboot.configure(**self.btn_style_normal_custom)
        self.btn_reboot.bind("<Enter>", lambda event:self.hover(self.btn_reboot))
        self.btn_reboot.bind("<Leave>", lambda event:self.unhover(self.btn_reboot))

    def _get_unlock_timer(self):
        if self.btn_reboot_unlock_timer > 0:
            return " (" + str(self.btn_reboot_unlock_timer) + "..)"
        else:
            return ""
        
    def setup_btn_reboot(self, show):
        if self.btn_reboot_exists==True:
            return

        if(show):
            self.btn_reboot_exists = True
            self.btn_reboot.configure(**self.btn_style_locked_custom)
            self.btn_reboot.unbind("<Enter>")
            self.btn_reboot.unbind("<Leave>")
            self.btn_reboot.place(
                x=(640 - (self.btn_style_normal["width"] / 2)),
                y=480
            )
            self.btn_reboot_unlock_timer = 5
            self._start_unlock_timer()
        else:
            self.btn_reboot_exists = False
            self.btn_reboot.place_forget()

        self.update_info(PopupError.manager.cur_errors)
