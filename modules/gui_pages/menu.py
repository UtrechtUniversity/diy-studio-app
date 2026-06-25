# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

import customtkinter as ctk
from enum import Enum
from PIL import Image
import pywinstyles
from typing import ClassVar, TYPE_CHECKING

if TYPE_CHECKING:
    from modules.gui import GuiManager


class ButtonsMenu(Enum):
    LOGIN = "login"
    TUTORIAL = "tutorial"
    VIDEOTYPE = "videotype"
    POWERPOINT = "powerpoint"
    CALIBRATION = "calibration"
    CONTROLS = "controls"
    RECORD = "record"
    END = "end"


class PageMenu(ctk.CTkFrame):
    buttons = {}
    manager: ClassVar["GuiManager"]
    unlockIndex = 0
    unlocked = {
        ButtonsMenu.LOGIN.value: True,
        ButtonsMenu.TUTORIAL.value: False,
        ButtonsMenu.VIDEOTYPE.value: False,
        ButtonsMenu.POWERPOINT.value: False,
        ButtonsMenu.CALIBRATION.value: False,
        ButtonsMenu.CONTROLS.value: False,
        ButtonsMenu.RECORD.value: False,
        ButtonsMenu.END.value: True
    }

    def __init__(self, parent, ui_elements):
        self.language = ui_elements[0]
        self.padding = ui_elements[1]
        self.colors = ui_elements[2]
        self.btn_style_normal = ui_elements[3]
        self.btn_style_active = ui_elements[4]
        self.btn_style_locked = ui_elements[5]
        self.btn_style_hover = ui_elements[6]
        self.debug_style = ui_elements[7]

        ctk.CTkFrame.__init__(
            self, 
            parent, 
            corner_radius=0, 
            width=1920, 
            height=self.padding["page_padding_content_y"], 
            fg_color=self.colors["primary"])
        
        self.text = PageMenu.manager.dataText

        # MENU BUTTONS
        i = 0

        for n in ButtonsMenu:
            self.buttons[n.value] = ctk.CTkButton(
                self, 
                text=self.text["menubuttons"][n.value][self.language],
                command=lambda n=n:PageMenu.manager.on_menu_click(n.value))
            
            self.buttons[n.value].configure(**self.btn_style_normal)
            
            self.buttons[n.value].place(
                x = self.padding["all_padding_x"] + (i * (
                    self.btn_style_normal["width"]
                    + self.padding["menu_padding_buttons_x"])),
                y = self.padding["menu_padding_buttons_y"])

            i = i + 1

        # LANGUAGE BUTTONS
        self.img_lang_en_normal = ctk.CTkImage(Image.open(
            "assets/buttons/btn_flag_gb.png"), size=(73, 73))
        self.img_lang_en_hover = ctk.CTkImage(Image.open(
            "assets/buttons/btn_flag_gb_hover.png"), size=(73, 73))

        self.img_lang_nl_normal = ctk.CTkImage(Image.open(
            "assets/buttons/btn_flag_nl.png"), size=(73, 73))
        self.img_lang_nl_hover = ctk.CTkImage(Image.open(
            "assets/buttons/btn_flag_nl_hover.png"), size=(73, 73))

        self.dict_lang_imgs = {
            "nl_normal":self.img_lang_nl_normal,
            "nl_hover":self.img_lang_nl_hover,
            "en_normal":self.img_lang_en_normal,
            "en_hover":self.img_lang_en_hover,
        }

        self.btn_lang = ctk.CTkButton(
            self, 
            text="",
            fg_color="transparent",
            hover="transparent",
            border_spacing=0,
            width=73,
            height=73,
            image=self.img_lang_nl_normal,
            command=self.on_change_language)
    
        self.btn_lang.bind("<Enter>", self.hover_img)
        self.btn_lang.bind("<Leave>", self.unhover_img)
        self.btn_lang.place(x = 1780, y = 33)

        # DEBUG TEXT
        self.showing_debug = False
        self.label_debug = ctk.CTkLabel(
            self,
            text='Versienummer app   -   OBS: (not) connected   -   StreamDeck: (not) connected   -   OneDrive: (not) authenticated   -   Internet: (not) connected',
            width=1920,
            height=20
        )
        self.label_debug.configure(**self.debug_style)
        
    def toggle_debug(self):
        if self.showing_debug == False:
            self.showing_debug = True
            self.label_debug.place(x=0,y=0)
        else:
            self.showing_debug = False
            self.label_debug.place_forget()

    def update_debug(self,txt):
        self.label_debug.configure(text=txt)

    def on_change_language(self):
        PageMenu.manager.change_language()
        self.btn_lang.configure(
            image = self.dict_lang_imgs[PageMenu.manager.language + "_hover"])

    def set_binding(self, name, bind):
        if bind == True:
            self.buttons[name].bind("<Enter>", lambda event,
                                    name = name: self.hover(name))
            self.buttons[name].bind("<Leave>", lambda event,
                                    name = name: self.unhover(name))
        else:
            self.buttons[name].unbind("<Enter>")
            self.buttons[name].unbind("<Leave>")

    def hover(self, name):
        self.buttons[name].configure(**self.btn_style_hover)

    def unhover(self, name):
        self.buttons[name].configure(**self.btn_style_normal)

    def hover_img(self, e):
        self.btn_lang.configure(
            image = self.dict_lang_imgs[PageMenu.manager.language + "_hover"])

    def unhover_img(self, e):
        self.btn_lang.configure(
            image = self.dict_lang_imgs[PageMenu.manager.language + "_normal"])
        
    def refresh_buttons(self, lang):
        authenticated: bool
        self.language = lang

        for n in ButtonsMenu:
            btn_text: str
            authenticated = PageMenu.manager.get_auth_status()
            btn_text = "logout" if (
                n.value == "login" and authenticated
            ) else n.value
            self.buttons[n.value].configure(
                text = self.text["menubuttons"][btn_text][self.language])
    
    def reset_unlock_index(self):
        PageMenu.unlocked[ButtonsMenu.LOGIN.value] = True
        PageMenu.unlocked[ButtonsMenu.TUTORIAL.value] = False
        PageMenu.unlocked[ButtonsMenu.VIDEOTYPE.value] = False
        PageMenu.unlocked[ButtonsMenu.POWERPOINT.value] = False
        PageMenu.unlocked[ButtonsMenu.CALIBRATION.value] = False
        PageMenu.unlocked[ButtonsMenu.CONTROLS.value] = False
        PageMenu.unlocked[ButtonsMenu.RECORD.value] = False
        PageMenu.unlocked[ButtonsMenu.END.value] = True
        
        self.set_btn_active(ButtonsMenu.LOGIN.value)
        self.refresh_buttons(self.language)
     
    def set_unlock_index(self, index, force = False):
        if force == True:
            PageMenu.unlockIndex = index
        else:
            PageMenu.unlockIndex = max(index, PageMenu.unlockIndex)
        
        match index:
            case 0:
                PageMenu.unlocked[ButtonsMenu.LOGIN.value] = True
            case 1:
                PageMenu.unlocked[ButtonsMenu.TUTORIAL.value] = True
            case 2:
                PageMenu.unlocked[ButtonsMenu.VIDEOTYPE.value] = True
            case 3:
                PageMenu.unlocked[ButtonsMenu.POWERPOINT.value] = True
            case 4:
                PageMenu.unlocked[ButtonsMenu.CALIBRATION.value] = True
            case 5:
                PageMenu.unlocked[ButtonsMenu.CONTROLS.value] = True
            case 6:
                PageMenu.unlocked[ButtonsMenu.RECORD.value] = True
            case 7:
                PageMenu.unlocked[ButtonsMenu.END.value] = True

    def set_btn_active(self, name, lock_rest = False):
        """Highlight the button of the active page in the menu bar
        (dark blue) and set bindings to the rest, depending on
        unlockIndex"""
        for n in ButtonsMenu:
            self.buttons[n.value].configure(**self.btn_style_normal)
            
            if (PageMenu.unlocked[n.value] and lock_rest == False):
                self.set_binding(n.value, True)
                self.buttons[n.value].configure(**self.btn_style_normal)
                pywinstyles.set_opacity(self.buttons[n.value], value=1)
            else:
                self.set_binding(n.value, False)
                self.buttons[n.value].configure(**self.btn_style_locked)
                pywinstyles.set_opacity(self.buttons[n.value], value=0.5)

        self.set_binding(name, False)
        self.buttons[name].configure(**self.btn_style_active)
        pywinstyles.set_opacity(self.buttons[name],value=1)
