"""Color schemes. Each fills the $tokens in style.css and the palette of the custom-drawn widgets."""

from string import Template

from .helper import hex_to_rgb, mix

DEFAULT = "dark"
SYSTEM = "system"  # follows the desktop's light/dark preference and accent color

THEMES = {
    "dark": {
        "label": "Dark",
        "scheme": "dark",
        "accent": "#ff5a1f",       # buttons, selection
        "accent_text": "#ff7a45",  # accent used as text color
        "bg": "#0d0e10",
        "sidebar": "#15171a",
        "card": "#17191c",
        "border": "#23262b",
        "popover": "#1d2024",
        "raised": "#1f2226",
        "trough": "#2a2e33",
        "fg": "#ffffff",
        "nav_fg": "#b8bcc4",
        "muted": "#8a8f98",
        "ok": "#4cd964",
        "warn": "#ffcc00",
        "bad": "#ff6b5f",
        "low": "#ff3b30",
        # mouse diagram
        "d_body": "#21252a",
        "d_part": "#2a2e34",
        "d_edge": "#42474f",
        "d_text": "#d9dee6",
        "d_dim": "#8a8f99",
        "d_hex": "#171a1d",
    },
    "light": {
        "label": "Light",
        "scheme": "light",
        "accent": "#f0541a",
        "accent_text": "#c8400c",
        "bg": "#f3f4f6",
        "sidebar": "#e8eaed",
        "card": "#ffffff",
        "border": "#d8dbe0",
        "popover": "#ffffff",
        "raised": "#eef0f3",
        "trough": "#d8dbe0",
        "fg": "#1b1d21",
        "nav_fg": "#454a52",
        "muted": "#6a6f78",
        "ok": "#1e9e3e",
        "warn": "#b07d00",
        "bad": "#d33a2c",
        "low": "#d93025",
        "d_body": "#e1e4e8",
        "d_part": "#d0d4da",
        "d_edge": "#a7adb6",
        "d_text": "#2a2e34",
        "d_dim": "#6a6f78",
        "d_hex": "#c3c8cf",
    },
    "teal": {
        "label": "Dark teal",
        "scheme": "dark",
        "accent": "#14a898",
        "accent_text": "#3dd6c3",
        "bg": "#0a1213",
        "sidebar": "#0f1a1b",
        "card": "#122022",
        "border": "#1c2f31",
        "popover": "#162628",
        "raised": "#18292b",
        "trough": "#233739",
        "fg": "#ffffff",
        "nav_fg": "#b0c4c5",
        "muted": "#7f9799",
        "ok": "#4cd964",
        "warn": "#ffcc00",
        "bad": "#ff6b5f",
        "low": "#ff3b30",
        "d_body": "#1a2a2c",
        "d_part": "#213436",
        "d_edge": "#36504f",
        "d_text": "#d6e6e6",
        "d_dim": "#80999a",
        "d_hex": "#111d1e",
    },
}


# Order of the cards on the Settings page.
CHOICES = (SYSTEM, "dark", "light", "teal")
LABELS = {SYSTEM: "System", **{k: t["label"] for k, t in THEMES.items()}}


def get(name):
    return THEMES.get(name, THEMES[DEFAULT])


def resolve(name, dark=True, accent=None):
    """The palette for `name`. For SYSTEM: Dark or Light per `dark`, with `accent` ("#rrggbb") if given."""
    if name != SYSTEM:
        return get(name)
    theme = dict(THEMES["dark" if dark else "light"], label=LABELS[SYSTEM])
    if accent:
        theme["accent"] = accent
        # accent as text: lighter on dark backgrounds, darker on light ones, for contrast
        theme["accent_text"] = mix(accent, "#ffffff" if dark else "#000000", 0.25)
    return theme


def css(template, t):
    """Fill style.css's placeholders from palette `t` (a THEMES entry or resolve() result)."""
    tokens = {k: v for k, v in t.items() if isinstance(v, str)}
    tokens["accent_rgb"] = "%d, %d, %d" % hex_to_rgb(t["accent"])
    return Template(template).substitute(tokens)
