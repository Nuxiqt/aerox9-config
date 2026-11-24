"""Names for button actions, and how the picker groups them."""

from .. import protocol

MOUSE_LABELS = {
    "left": "Left click", "right": "Right click", "middle": "Middle click",
    "back": "Back", "forward": "Forward", "scroll_up": "Scroll up", "scroll_down": "Scroll down",
}
MOUSE_SHORT = {
    "left": "L-Click", "right": "R-Click", "middle": "M-Click", "back": "Back",
    "forward": "Fwd", "scroll_up": "Scr Up", "scroll_down": "Scr Dn",
}
MEDIA_LABELS = {
    "PlayPause": "Play / Pause", "Next": "Next track", "Previous": "Previous track",
    "Mute": "Mute", "VolumeUp": "Volume up", "VolumeDown": "Volume down",
}
MEDIA_SHORT = {
    "PlayPause": "Play", "Next": "Next", "Previous": "Prev",
    "Mute": "Mute", "VolumeUp": "Vol +", "VolumeDown": "Vol -",
}
KEY_SYMBOLS = {
    "Minus": "-", "Equal": "=", "LeftBracket": "[", "RightBracket": "]", "Backslash": "\\",
    "Semicolon": ";", "Quote": "'", "Grave": "`", "Comma": ",", "Period": ".", "Slash": "/",
}
CATEGORIES = {
    "Mouse": [("mouse", m) for m in protocol.MOUSE_TARGETS],
    "Keyboard": [("key", k) for k in protocol.KEYS],
    "Media": [("media", k) for k in protocol.MEDIA_KEYS],
    "Other": [("dpi", None), ("disabled", None)],
}
KIND_CATEGORY = {"mouse": "Mouse", "key": "Keyboard", "media": "Media", "dpi": "Other", "disabled": "Other"}


def action_label(action):
    kind, value = action
    if kind == "mouse":
        return MOUSE_LABELS[value]
    if kind == "key":
        return f"Key  {KEY_SYMBOLS.get(value, value)}"
    if kind == "media":
        return MEDIA_LABELS[value]
    return "DPI cycle" if kind == "dpi" else "Disabled"


def action_short(action):
    kind, value = action
    if kind == "mouse":
        return MOUSE_SHORT[value]
    if kind == "key":
        return KEY_SYMBOLS.get(value, value)
    if kind == "media":
        return MEDIA_SHORT[value]
    return "DPI" if kind == "dpi" else "—"
