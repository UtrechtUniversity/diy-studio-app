# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

from enum import Enum


class Action(Enum):
    START_SLIDESHOW = "start slide show"
    RESTART_SLIDESHOW = "restart slide show"
    OPEN_PRESENTATION = "open presentation"
    SLIDE_NEXT = "navigate to next slide"
    SLIDE_ONE = "navigate to first slide"
    SLIDE_PREV = "navigate to previous slide"
