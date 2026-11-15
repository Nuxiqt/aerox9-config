"""SteelSeries Aerox 9 Wireless HID protocol: pure encoders, no I/O.

Command bytes come from rivalcfg (https://github.com/flozz/rivalcfg, WTFPL).
Button mapping comes from the unmerged rivalcfg PR #243 and is EXPERIMENTAL.

Every function returns the command payload (without the HID report ID).
In 2.4 GHz wireless mode the first byte is OR'd with WIRELESS_FLAG
(see device.py).
"""

WIRELESS_FLAG = 0x40

# --- DPI ---------------------------------------------------------------------

DPI_MIN, DPI_MAX, DPI_STEP = 100, 18000, 100
MAX_DPI_PRESETS = 5
# TrueMove Air sensor codes for 100, 200, ... 18000 DPI.
_DPI_CODES = bytes.fromhex(
    "00020304050607090a0b0c0d0e1011121314161718191a1b1d1e1f20212325262728292a"
    "2c2d2e2f30323334353638393a3b3c3e3f40414244454647484a4b4c4d4e505152535456"
    "5758595a5c5d5e5f60626364656668696a6b6c6e6f70717274757677787a7b7c7d7e8081"
    "828384868788898a8c8d8e8f90929394959698999a9b9c9e9fa0a1a2a4a5a6a7a8aaabac"
    "adaeb0b1b2b3b4b5b6b7b8b9babbbcbdbfc0c2c3c4c5c6c7c9cacbcccdcfd0d1d2d3d5d6"
)


def dpi_code(dpi):
    dpi = min(max(int(round(dpi / DPI_STEP)) * DPI_STEP, DPI_MIN), DPI_MAX)
    return _DPI_CODES[dpi // DPI_STEP - 1]


def sensitivity(presets, active=0):
    if not 1 <= len(presets) <= MAX_DPI_PRESETS:
        raise ValueError(f"need 1..{MAX_DPI_PRESETS} DPI presets")
    if not 0 <= active < len(presets):
        raise ValueError("active preset out of range")
    return [0x2D, len(presets), active] + [dpi_code(d) for d in presets]


# --- Performance / power -----------------------------------------------------

POLLING_RATES = {125: 0x03, 250: 0x02, 500: 0x01, 1000: 0x00}


def polling_rate(hz):
    return [0x2B, POLLING_RATES[hz]]


def _le24(value):
    return [value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF]


SLEEP_MAX_MIN = 20
DIM_MAX_S = 1200


def sleep_timer(minutes):
    """Idle minutes before sleep (0 = never)."""
    minutes = min(max(int(minutes), 0), SLEEP_MAX_MIN)
    return [0x29] + _le24(minutes * 60000)


def dim_timer(seconds):
    """Idle seconds before LEDs dim (0 = never)."""
    seconds = min(max(int(seconds), 0), DIM_MAX_S)
    return [0x23, 0x0F, 0x01, 0x00, 0x00] + _le24(seconds * 1000)


# --- Lighting ----------------------------------------------------------------

ZONES = ("top", "middle", "bottom")


def zone_color(zone, rgb):
    return [0x21, 0x01, ZONES.index(zone)] + list(rgb)


def reactive_color(rgb):
    """Color flashed on click; None disables it."""
    if rgb is None:
        return [0x26, 0x00, 0x00, 0x00, 0x00, 0x00]
    return [0x26, 0x01, 0x00] + list(rgb)


def rainbow():
    """Rainbow effect; any zone_color call overrides it."""
    return [0x22, 0xFF]


DEFAULT_LIGHTING = {
    "off": [0x00, 0x00],
    "reactive": [0x00, 0x01],
    "rainbow": [0x01, 0x00],
    "reactive-rainbow": [0x01, 0x01],
}


def default_lighting(mode):
    """Lighting the mouse shows at power-on."""
    return [0x27] + DEFAULT_LIGHTING[mode]


# --- Device ------------------------------------------------------------------

SAVE = [0x11, 0x00]
BATTERY = [0x92]
_CHARGING = 0x80


def parse_battery(resp):
    """resp is the raw reply (echoed command byte first). Returns (level%, charging) or None."""
    if not resp or len(resp) < 2:
        return None
    level = ((resp[1] & ~_CHARGING) - 1) * 5
    if not 0 <= level <= 100:
        return None
    return level, bool(resp[1] & _CHARGING)


# --- Buttons (EXPERIMENTAL, rivalcfg PR #243) --------------------------------

ACT_DISABLED = 0x00
ACT_DPI = 0x30
ACT_KEY = 0x51
ACT_MEDIA = 0x61

# Mouse-button target ids.
MOUSE_TARGETS = {
    "left": 0x01,
    "right": 0x02,
    "middle": 0x03,
    "back": 0x04,
    "forward": 0x05,
    "scroll_up": 0x31,
    "scroll_down": 0x32,
}

MEDIA_KEYS = {
    "PlayPause": 0xCD,
    "Next": 0xB5,
    "Previous": 0xB6,
    "Mute": 0xE2,
    "VolumeUp": 0xE9,
    "VolumeDown": 0xEA,
}


def _build_keys():
    """USB HID keyboard usage IDs (US layout names)."""
    keys = {}
    for i, c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
        keys[c] = 0x04 + i
    for i, c in enumerate("1234567890"):
        keys[c] = 0x1E + i
    for i, name in enumerate(
        ["Enter", "Escape", "Backspace", "Tab", "Space", "Minus", "Equal",
         "LeftBracket", "RightBracket", "Backslash", None, "Semicolon",
         "Quote", "Grave", "Comma", "Period", "Slash", "CapsLock"]
    ):
        if name:
            keys[name] = 0x28 + i
    for i in range(12):
        keys[f"F{i + 1}"] = 0x3A + i
    for i, name in enumerate(
        ["PrintScreen", "ScrollLock", "Pause", "Insert", "Home", "PageUp",
         "Delete", "End", "PageDown", "Right", "Left", "Down", "Up", "NumLock",
         "KpSlash", "KpAsterisk", "KpMinus", "KpPlus", "KpEnter",
         "Kp1", "Kp2", "Kp3", "Kp4", "Kp5", "Kp6", "Kp7", "Kp8", "Kp9", "Kp0",
         "KpPeriod"]
    ):
        keys[name] = 0x46 + i
    keys["ContextMenu"] = 0x65
    for i in range(12):
        keys[f"F{i + 13}"] = 0x68 + i
    for i, name in enumerate(
        ["LeftCtrl", "LeftShift", "LeftAlt", "LeftSuper",
         "RightCtrl", "RightShift", "RightAlt", "RightSuper"]
    ):
        keys[name] = 0xE0 + i
    return keys


KEYS = _build_keys()

# (id, label, default action) in packet order; each field is 5 bytes.
BUTTONS = [
    ("button1", "Left click", ("mouse", "left")),
    ("button2", "Right click", ("mouse", "right")),
    ("button3", "Wheel click", ("mouse", "middle")),
    ("button4", "Button 4 (unverified)", ("mouse", "back")),
    ("button5", "Button 5 (unverified)", ("mouse", "forward")),
    ("button6", "DPI button", ("dpi", None)),
    ("side3", "Side 3", ("key", "3")),
    ("side6", "Side 6", ("key", "6")),
    ("side9", "Side 9", ("key", "9")),
    ("side12", "Side 12", ("key", "Equal")),
    ("side2", "Side 2", ("key", "2")),
    ("side5", "Side 5", ("key", "5")),
    ("side8", "Side 8", ("key", "8")),
    ("side11", "Side 11", ("key", "Minus")),
    ("side1", "Side 1", ("key", "1")),
    ("side4", "Side 4", ("key", "4")),
    ("side7", "Side 7", ("key", "7")),
    ("side10", "Side 10", ("key", "0")),
    ("scroll_up", "Scroll up", ("mouse", "scroll_up")),
    ("scroll_down", "Scroll down", ("mouse", "scroll_down")),
]
BUTTON_IDS = [b[0] for b in BUTTONS]
DEFAULT_BUTTONS = {b[0]: b[2] for b in BUTTONS}
_FIELD = 5
_SPLITS = (0, 30, 60, len(BUTTONS) * _FIELD)


def encode_action(action):
    kind, value = action
    if kind == "mouse":
        return [MOUSE_TARGETS[value]]
    if kind == "dpi":
        return [ACT_DPI]
    if kind == "disabled":
        return [ACT_DISABLED]
    if kind == "key":
        return [ACT_KEY, KEYS[value]]
    if kind == "media":
        return [ACT_MEDIA, MEDIA_KEYS[value]]
    raise ValueError(f"unknown action {action!r}")


def buttons(mapping):
    """mapping: {button_id: (kind, value)}; missing buttons get defaults.

    Returns a list of 3 commands (the mapping is split over 3 packets).
    """
    unknown = set(mapping) - set(BUTTON_IDS)
    if unknown:
        raise ValueError(f"unknown buttons: {sorted(unknown)}")
    packet = []
    for bid in BUTTON_IDS:
        field = encode_action(mapping.get(bid, DEFAULT_BUTTONS[bid]))
        packet += field + [0x00] * (_FIELD - len(field))
    return [
        [0x2A, part] + packet[_SPLITS[part]:_SPLITS[part + 1]]
        for part in range(len(_SPLITS) - 1)
    ]
