# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

import customtkinter as ctk
from modules.gui_pages.base import PageBase
from CTkListbox import CTkListbox
import pywinstyles
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from modules.backends.cloud_storage.storage_base import CloudStorageDirContent


class PagePowerPoint(PageBase):
    def __init__(self, parent, ui_elements):
        super().__init__(parent, ui_elements)

        self.setup_btn_forward()
        self.set_unlock_forward()
        self.setup_btn_back()

        self.data: Optional["CloudStorageDirContent"] = None
        # path_ids contains all directories we've entered, starting from root.
        self.path_ids: list[str] = []
        self._lock_selecting = False
        self._pending_path_ids: Optional[list[str]] = None

        # CUSTOM CODE FOR THIS PAGE
        listbox_w = 800
        listbox_h = 550
        listbox_x = 550
        listbox_y = 150
        self.pagename = "powerpoint_staticbg"
        self.PPT_LOAD_WAIT_TIME = 3000
        self.setup_title_by_pagename(self.pagename)

        self.label_text1 = ctk.CTkLabel(
            self,
            text=self.text["pagetext"][self.pagename]["text_1"][self.language],
            width=200,
            wraplength=200,
            height=94
        )
        self.label_text1.configure(**self.text_style)
        self.label_text1.place(x=210, y=350)

        self.listbox = CTkListbox(
            self,
            width=listbox_w,
            height=listbox_h
            )
        self.listbox.configure(**self.listbox_style)
        self.listbox.configure(bg_color=self.colors["bg_content"],
                               fg_color=self.colors["bg_content"],
                               hover_color=self.colors["primary"])
        self.listbox.place(x=listbox_x, y=listbox_y)
        self.listbox.bind("<<ListboxSelect>>", self.on_select_item)

        self.checkbox = ctk.CTkCheckBox(
            self,
            text="Presenter View",
            height=40,
            font=self.text_style["font"]
        )

        self.checkbox.configure(
            border_color="black",
            bg_color=self.colors["bg_content"],
            fg_color="#333333",
            hover_color=self.colors["primary"],
            command=self.set_presenter_view
            )
        self.checkbox.place(x=listbox_x, y=listbox_y+listbox_h+20)

        self.listbox_blocker = ctk.CTkLabel(
            self,
            text="",
            width=listbox_w+40,
            height=listbox_h+70,
            fg_color=self.colors["bg_content"]
        )
        self.listbox_blocker.place(x=listbox_x, y=listbox_y)
        pywinstyles.set_opacity(self.listbox_blocker, value=0)

    def _refresh_folder(self):
        data = self.data
        if data is None:
            return

        self._lock_selecting = True
        try:
            self.clear_listbox()

            count = 0

            if len(self.path_ids) > 1:
                self.listbox.insert(0, "< Back")
                count = 1

            for dir in data.dirs:
                self.listbox.insert(count, "> " + dir.name)
                count += 1

            for i in range(len(data.files)):
                file = data.files[i]
                if i != len(data.files)-1:
                    self.listbox.insert(count, file.name)
                else:
                    self.listbox.insert("END", file.name)
                count += 1
        finally:
            self._lock_selecting = False

    def change_language(self, lang):
        super().change_language(lang)

        self.label_text1.configure(
            text=self.text["pagetext"][self.pagename]["text_1"][self.language]
        )

    def change_videotype(self, type):
        if type == "staticbg":
            self.pagename = "powerpoint_staticbg"
        elif type == "ppt":
            self.pagename = "powerpoint_ppt"
        self.setup_title_by_pagename(self.pagename)

    def clear_listbox(self):
        self.listbox.delete("all")

    def on_select_item(self, e):
        """User clicked an item in the listbox"""
        if self._lock_selecting:
            return

        data = self.data
        if data is None:
            return

        clicked_index = self.listbox.curselection()

        self.listbox.selection_clear()

        if len(self.path_ids) > 1:
            if clicked_index == 0:
                # The first item that's displayed in the listbox
                # when we're not in the root directory is the
                # '< Back' button, so let's go up one folder.
                self._pending_path_ids = self.path_ids[:-1]
                self.show_blocker()

                PagePowerPoint.manager.route_call(
                    "cloud_manager",
                    "set_dir_id",
                    self._pending_path_ids[-1]
                )
                return
            else:
                # User clicked any item other than '< Back',
                # so we need to subtract 1 so it will match
                # the index in self.data.dirs or self.data.files
                clicked_index -= 1

        if clicked_index < len(data.dirs):
            # Open folder
            self._pending_path_ids = (
                self.path_ids + [data.dirs[clicked_index].id]
            )
            self.show_blocker()

            PagePowerPoint.manager.route_call(
                "cloud_manager",
                "set_dir_id",
                self._pending_path_ids[-1]
            )
        else:
            # Open file
            self.show_timer_blocker(self.PPT_LOAD_WAIT_TIME)

            PagePowerPoint.manager.route_call(
                "cloud_manager",
                "set_presentation",
                (clicked_index - len(data.dirs))
            )

    def refresh(self):
        self.clear_listbox()

    def set_folder_data(self, data: "CloudStorageDirContent"):
        """Received a CloudStorageDirContent object: refresh folder contents

        CloudStorageManager -> GuiManager -> here
        """
        self.data = data

        if self._pending_path_ids is not None:
            self.path_ids = self._pending_path_ids
            self._pending_path_ids = None

        self._refresh_folder()
        self.hide_blocker()

    def set_presenter_view(self, *args):
        self.show_timer_blocker(self.PPT_LOAD_WAIT_TIME)

        PagePowerPoint.manager.route_call(
            "presentation_manager",
            "set_presenter_view",
            self.checkbox.get()
        )

    def set_root_id(self, id):
        # Root should always be path_ids[0]
        self.path_ids = [id]
        self._pending_path_ids = None

    def hide_blocker(self):
        pywinstyles.set_opacity(self.listbox_blocker, value=0)
        self._lock_selecting = False

    def show_blocker(self):
        self._lock_selecting = True
        pywinstyles.set_opacity(self.listbox_blocker, value=0.6)

    def show_timer_blocker(self, duration):
        self.show_blocker()
        PagePowerPoint.manager.schedule_task(duration, self.hide_blocker)
