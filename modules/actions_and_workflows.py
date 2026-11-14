# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

from dataclasses import dataclass


@dataclass (frozen=True)
class ActionProperties:
    conds: list
    params: list


ACTION_CATALOGUE = {
    "audio.mic_check.start": ActionProperties(
        conds=[],
        params=[]
    ),
    "gui.hide_streamdeck_update_window": ActionProperties(
        conds=[],
        params=[]
    ),
    "gui.menu.set_button_active": ActionProperties(
        conds=[],
        params=["name"]
    ),
    "gui.page.enter": ActionProperties(
        conds=[],
        params=["page"]
    ),
    "gui.page.leave": ActionProperties(
        conds=[],
        params=["page"]
    )
}

WORKFLOW_CATALOGUE = {
    "record": [
        {"key": "rec.start", "params": {}}
    ]
}
