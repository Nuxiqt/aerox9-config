"""Small shared helpers: color conversions and cairo shapes. Pure Python, so the CLI can import it without GTK."""

import math


def hex_to_rgb(color):
    """"#rrggbb" -> (r, g, b) ints 0..255."""
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def hex_to_rgbf(color):
    """"#rrggbb" -> (r, g, b) floats 0..1, as cairo wants them."""
    return tuple(c / 255 for c in hex_to_rgb(color))


def rgb_to_hex(r, g, b):
    return "#%02x%02x%02x" % (round(r), round(g), round(b))


def rgbf_to_hex(r, g, b):
    """Floats 0..1 (clamped) -> "#rrggbb"."""
    return rgb_to_hex(*(min(max(c, 0), 1) * 255 for c in (r, g, b)))


def mix(a, b, t):
    """Blend two "#rrggbb" colors; t=0 gives a, t=1 gives b."""
    return rgb_to_hex(*(x + (y - x) * t for x, y in zip(hex_to_rgb(a), hex_to_rgb(b))))


def accent_hex(rgb):
    """A desktop-portal accent (floats 0..1; out of range means unset) -> "#rrggbb", or None."""
    try:
        if len(rgb) == 3 and all(0 <= c <= 1 for c in rgb):
            return rgbf_to_hex(*rgb)
    except TypeError:
        pass
    return None


def round_rect(cr, x, y, w, h, r):
    """Add a rounded-rectangle sub-path to cairo context `cr`."""
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()
