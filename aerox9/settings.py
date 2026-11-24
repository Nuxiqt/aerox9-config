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


DEFAULT_PROFILE = "Default"

# Global, not per-profile.
APP_DEFAULTS = {
    "theme": "dark",
}


def _merge(stored):
    """One profile's settings, with anything missing or unknown filled from DEFAULTS."""
    data = copy.deepcopy(DEFAULTS)
    if not isinstance(stored, dict):
        return data
    for key, value in stored.items():
        if key in ("colors", "buttons") and isinstance(value, dict):
            data[key].update(value)
        elif key in data:
            data[key] = value
    return data


def load_store(path=PATH):
    """Returns {"app": global settings, "active": name, "profiles": {name: settings}}.

    There is always at least one profile.
    """
    try:
        with open(path) as f:
            raw = json.load(f)
    except (OSError, ValueError):
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    if isinstance(raw.get("profiles"), dict) and raw["profiles"]:
        profiles = {str(name): _merge(p) for name, p in raw["profiles"].items()}
        active = raw.get("active")
        if active not in profiles:
            active = next(iter(profiles))
    else:  # file from before profiles existed: a flat settings dict
        profiles = {DEFAULT_PROFILE: _merge(raw)}
        active = DEFAULT_PROFILE
    app = dict(APP_DEFAULTS)
    if isinstance(raw.get("app"), dict):
        app.update((k, v) for k, v in raw["app"].items() if k in APP_DEFAULTS)
    return {"app": app, "active": active, "profiles": profiles}


def save_store(store, path=PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(store, f, indent=2)
    os.replace(tmp, path)


def load(path=PATH, profile=None):
    """Settings of `profile` (default: the active one). Raises KeyError for an unknown profile."""
    store = load_store(path)
    return store["profiles"][store["active"] if profile is None else profile]


def unique_name(store, base):
    """`base`, or `base 2`, `base 3`… if that name is taken."""
    name, n = base, 2
    while name in store["profiles"]:
        name, n = f"{base} {n}", n + 1
    return name


def switch_commands(old, new):
    """Commands to go from profile `old` to `new`. Buttons are sent only when the mapping differs."""
    return all_commands(new, include_buttons=new["buttons"] != old["buttons"])


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
