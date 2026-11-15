"""Persisted settings. The mouse can't report its config, so this file is the source of truth."""

import copy
import json
import os

from . import protocol

PATH = os.path.join(
    os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
    "aerox9",
    "settings.json",
)

DEFAULTS = {
    "dpi": [400, 800, 1200, 2400, 3200],
    "dpi_active": 0,
    "polling_rate": 1000,
    "rainbow": False,
    "colors": {"top": "#ff0000", "middle": "#00ff00", "bottom": "#0000ff"},
    "reactive": None,
    "default_lighting": "rainbow",
    "dim_timer": 30,
    "sleep_timer": 5,
    "buttons": {k: list(v) for k, v in protocol.DEFAULT_BUTTONS.items()},
}


def load(path=PATH):
    data = copy.deepcopy(DEFAULTS)
    try:
        with open(path) as f:
            stored = json.load(f)
    except (OSError, ValueError):
        return data
    for key, value in stored.items():
        if key in ("colors", "buttons") and isinstance(value, dict):
            data[key].update(value)
        elif key in data:
            data[key] = value
    return data


def save(data, path=PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def hex_to_rgb(color):
    color = color.lstrip("#")
    return [int(color[i:i + 2], 16) for i in (0, 2, 4)]


# Each section maps to the commands that apply it, so the GUI can send only what changed.
def section_commands(data, section):
    if section == "dpi":
        return [protocol.sensitivity(data["dpi"], data["dpi_active"])]
    if section == "polling_rate":
        return [protocol.polling_rate(data["polling_rate"])]
    if section == "lighting":
        if data["rainbow"]:
            return [protocol.rainbow()]
        return [protocol.zone_color(z, hex_to_rgb(data["colors"][z])) for z in protocol.ZONES]
    if section == "reactive":
        rgb = hex_to_rgb(data["reactive"]) if data["reactive"] else None
        return [protocol.reactive_color(rgb)]
    if section == "default_lighting":
        return [protocol.default_lighting(data["default_lighting"])]
    if section == "dim_timer":
        return [protocol.dim_timer(data["dim_timer"])]
    if section == "sleep_timer":
        return [protocol.sleep_timer(data["sleep_timer"])]
    if section == "buttons":
        return protocol.buttons({k: tuple(v) for k, v in data["buttons"].items()})
    raise KeyError(section)


SECTIONS = (
    "dpi", "polling_rate", "lighting", "reactive", "default_lighting",
    "dim_timer", "sleep_timer", "buttons",
)


def all_commands(data, include_buttons=True):
    cmds = []
    for s in SECTIONS:
        if s == "buttons" and not include_buttons:
            continue
        cmds += section_commands(data, s)
    return cmds
