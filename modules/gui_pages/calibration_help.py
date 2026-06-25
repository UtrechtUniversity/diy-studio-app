# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

from modules.gui_pages.base import PageBase


class PageCalibrationHelp(PageBase):
    def __init__(self, parent, ui_elements):
        super().__init__(parent, ui_elements)
        
        self.setup_btn_forward()
        # because first bg is selected, this button is always unlocked
        self.btn_forward.configure(**self.btn_style_normal)

        self.setup_btn_back()

        # CUSTOM CODE FOR THIS PAGE
        self.setup_title_by_pagename('calibration_help')