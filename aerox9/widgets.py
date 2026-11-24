"""Custom-drawn widgets: mouse diagram and color picker."""

import colorsys
import math

import cairo
from gi.repository import GLib, Gtk

from . import protocol
from .settings import hex_to_rgb

# Drawing palette (RGB floats); replaced by set_palette() when the color scheme changes.
ACCENT = (1.0, 0.353, 0.122)
BODY = (0.13, 0.145, 0.165)
PART = (0.165, 0.18, 0.205)
EDGE = (0.26, 0.28, 0.31)
TEXT = (0.85, 0.87, 0.9)
DIM = (0.54, 0.56, 0.6)
HEX_FILL = (0.09, 0.1, 0.115)


def set_palette(theme):
    """Switch the diagram colors to a themes.THEMES entry; redraw widgets afterwards."""
    global ACCENT, BODY, PART, EDGE, TEXT, DIM, HEX_FILL
    ACCENT, BODY, PART, EDGE, TEXT, DIM, HEX_FILL = (
        hex_to_rgbf(theme[k]) for k in ("accent", "d_body", "d_part", "d_edge", "d_text", "d_dim", "d_hex"))

# Logical canvas; scaled to fit the widget.
CW, CH = 560, 590
CX = 180  # mouse centre line
SPLIT_Y = 235  # end of L/R buttons
ZONE_BANDS = {"top": (245, 345), "middle": (345, 445), "bottom": (445, 550)}
SIDE_GRID = [[1, 2, 3], [4, 5, 6], [7, 8, 9], [10, 11, 12]]
KEY, GAP, GX, GY = 54, 10, 348, 190


def hex_to_rgbf(color):
    return tuple(c / 255 for c in hex_to_rgb(color))


def rgbf_to_hex(r, g, b):
    return "#%02x%02x%02x" % tuple(round(min(max(c, 0), 1) * 255) for c in (r, g, b))


def _round_rect(cr, x, y, w, h, r):
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


def _body_path(cr):
    c = CX
    cr.new_path()
    cr.move_to(c, 40)
    cr.curve_to(c + 70, 40, c + 95, 90, c + 98, 200)
    cr.curve_to(c + 102, 320, c + 112, 420, c + 100, 480)
    cr.curve_to(c + 88, 540, c + 40, 550, c, 550)
    cr.curve_to(c - 40, 550, c - 88, 540, c - 100, 480)
    cr.curve_to(c - 112, 420, c - 102, 320, c - 98, 200)
    cr.curve_to(c - 95, 90, c - 70, 40, c, 40)
    cr.close_path()


def _text(cr, s, x, y, size, color, bold=True, align="center"):
    cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL,
                        cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
    cr.set_font_size(size)
    ext = cr.text_extents(s)
    dx = {"center": ext.width / 2 + ext.x_bearing, "left": 0, "right": ext.width}[align]
    cr.move_to(x - dx, y + ext.height / 2)
    cr.set_source_rgb(*color)
    cr.show_text(s)


def _hex(cr, x, y, r):
    for i in range(6):
        a = math.pi / 3 * i + math.pi / 6
        (cr.move_to if i == 0 else cr.line_to)(x + r * math.cos(a), y + r * math.sin(a))
    cr.close_path()


class MouseDiagram(Gtk.DrawingArea):
    """Top view of the mouse plus the side keypad.

    mode "buttons": hotspots are button ids, `labels` maps id -> short binding text.
    mode "lighting": hotspots are zones, `colors` maps zone -> hex.
    """

    def __init__(self, mode):
        super().__init__(hexpand=True, vexpand=True, content_width=420, content_height=440)
        self.mode = mode
        self.selected = set()
        self.hover = None
        self.labels = {}
        self.names = {b[0]: b[1] for b in protocol.BUTTONS}
        self.colors = {z: "#808080" for z in protocol.ZONES}
        self.rainbow = False
        self.on_select = None
        self._xf = (1, 0, 0)
        self._tick = None
        self._phase = 0.0
        self.set_draw_func(self._draw)
        click = Gtk.GestureClick()
        click.connect("pressed", self._on_click)
        self.add_controller(click)
        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self._on_motion)
        motion.connect("leave", lambda *_: self._set_hover(None))
        self.add_controller(motion)

    # --- public -------------------------------------------------------------

    def set_selected(self, ids):
        self.selected = set(ids)
        self.queue_draw()

    def set_rainbow(self, on):
        self.rainbow = on
        if on and self._tick is None:
            self._tick = self.add_tick_callback(self._animate)
        elif not on and self._tick is not None:
            self.remove_tick_callback(self._tick)
            self._tick = None
        self.queue_draw()

    # --- geometry -----------------------------------------------------------

    def _hotspots(self):
        if self.mode == "lighting":
            return [(z, (CX - 115, y0, 230 + 150, y1 - y0)) for z, (y0, y1) in ZONE_BANDS.items()]
        spots = [
            ("scroll_up", (CX - 16, 58, 32, 30)),
            ("button3", (CX - 14, 92, 28, 66)),
            ("scroll_down", (CX - 16, 162, 32, 26)),
            ("button6", (CX - 12, 196, 24, 30)),
            ("button1", (CX - 110, 40, 108, SPLIT_Y - 40)),
            ("button2", (CX + 2, 40, 108, SPLIT_Y - 40)),
        ]
        for r, row in enumerate(SIDE_GRID):
            for c, n in enumerate(row):
                spots.append((f"side{n}", (GX + c * (KEY + GAP), GY + r * (KEY + GAP), KEY, KEY)))
        return spots

    def _hit(self, x, y):
        s, ox, oy = self._xf
        lx, ly = (x - ox) / s, (y - oy) / s
        for sid, (hx, hy, hw, hh) in self._hotspots():
            if hx <= lx <= hx + hw and hy <= ly <= hy + hh:
                return sid
        return None

    def _on_click(self, _g, _n, x, y):
        sid = self._hit(x, y)
        if sid and self.on_select:
            self.on_select(sid)

    def _on_motion(self, _c, x, y):
        self._set_hover(self._hit(x, y))

    def _set_hover(self, sid):
        if sid != self.hover:
            self.hover = sid
            self.set_cursor_from_name("pointer" if sid else None)
            self.queue_draw()

    def _animate(self, _w, clock):
        self._phase = (clock.get_frame_time() / 4e6) % 1.0
        self.queue_draw()
        return GLib.SOURCE_CONTINUE

    # --- drawing ------------------------------------------------------------

    def _part_fill(self, cr, sid):
        if sid in self.selected:
            cr.set_source_rgba(*ACCENT, 0.9)
        elif sid == self.hover:
            cr.set_source_rgba(*ACCENT, 0.35)
        else:
            cr.set_source_rgb(*PART)

    def _zone_rgb(self, zone, y):
        if self.rainbow:
            return colorsys.hsv_to_rgb((self._phase + y / 700) % 1.0, 1, 1)
        return hex_to_rgbf(self.colors[zone])

    def _draw(self, _area, cr, w, h):
        s = min(w / CW, h / CH)
        ox, oy = (w - CW * s) / 2, (h - CH * s) / 2
        self._xf = (s, ox, oy)
        cr.translate(ox, oy)
        cr.scale(s, s)
        lighting = self.mode == "lighting"

        # glow under the mouse in lighting mode
        if lighting:
            for zone, (y0, y1) in ZONE_BANDS.items():
                r, g, b = self._zone_rgb(zone, (y0 + y1) / 2)
                grad = cairo.RadialGradient(CX, (y0 + y1) / 2, 10, CX, (y0 + y1) / 2, 170)
                grad.add_color_stop_rgba(0, r, g, b, 0.28)
                grad.add_color_stop_rgba(1, r, g, b, 0)
                cr.set_source(grad)
                cr.paint()

        # body
        _body_path(cr)
        cr.set_source_rgb(*BODY)
        cr.fill_preserve()
        cr.set_source_rgb(*EDGE)
        cr.set_line_width(2)
        cr.stroke()

        # L/R buttons
        for sid, x0 in (("button1", 0), ("button2", CX + 2)):
            cr.save()
            _body_path(cr)
            cr.clip()
            cr.rectangle(x0, 0, CX - 2 if x0 == 0 else CW, SPLIT_Y)
            if lighting:
                cr.set_source_rgb(*PART)
            else:
                self._part_fill(cr, sid)
            cr.fill()
            cr.restore()

        # honeycomb shell (LED zones)
        cr.save()
        _body_path(cr)
        cr.clip()
        r = 8
        dx, dy = math.sqrt(3) * r + 2.5, 1.5 * r + 2.5
        row = 0
        y = ZONE_BANDS["top"][0] + r
        while y < 560:
            x = CX - 120 + (dx / 2 if row % 2 else 0)
            zone = next(z for z, (y0, y1) in ZONE_BANDS.items() if y < y1 or z == "bottom")
            while x < CX + 120:
                _hex(cr, x, y, r)
                if lighting:
                    cr_r, cr_g, cr_b = self._zone_rgb(zone, y)
                    sel = zone in self.selected or zone == self.hover
                    cr.set_source_rgba(cr_r, cr_g, cr_b, 0.95 if sel or not self.selected else 0.55)
                else:
                    cr.set_source_rgb(*HEX_FILL)
                cr.fill()
                x += dx
            y += dy
            row += 1
        cr.restore()

        if lighting:
            self._draw_zone_labels(cr)
        else:
            self._draw_buttons(cr)

    def _draw_zone_labels(self, cr):
        for zone, (y0, y1) in ZONE_BANDS.items():
            ym = (y0 + y1) / 2
            active = zone in self.selected or zone == self.hover
            col = ACCENT if active else DIM
            cr.set_source_rgb(*col)
            cr.set_line_width(1.5)
            cr.move_to(CX + 115, ym)
            cr.line_to(CX + 175, ym)
            cr.stroke()
            cr.arc(CX + 185, ym, 7, 0, 2 * math.pi)
            r, g, b = self._zone_rgb(zone, ym)
            cr.set_source_rgb(r, g, b)
            cr.fill()
            _text(cr, zone.upper(), CX + 200, ym, 14, ACCENT if active else TEXT, align="left")

    def _draw_buttons(self, cr):
        # wheel, scroll arrows, dpi
        x, y, w, h = CX - 14, 92, 28, 66
        _round_rect(cr, x, y, w, h, 12)
        self._part_fill(cr, "button3")
        cr.fill_preserve()
        cr.set_source_rgb(*EDGE)
        cr.set_line_width(1.5)
        cr.stroke()
        for i in range(6):
            cr.move_to(x + 6, y + 12 + i * 8.5)
            cr.line_to(x + w - 6, y + 12 + i * 8.5)
        cr.set_source_rgba(0, 0, 0, 0.35)
        cr.stroke()
        for sid, ty, up in (("scroll_up", 73, True), ("scroll_down", 175, False)):
            cr.arc(CX, ty, 11, 0, 2 * math.pi)
            self._part_fill(cr, sid)
            cr.fill()
            d = -1 if up else 1
            cr.move_to(CX - 5, ty - 2.5 * d)
            cr.line_to(CX + 5, ty - 2.5 * d)
            cr.line_to(CX, ty + 3.5 * d)
            cr.close_path()
            cr.set_source_rgb(*TEXT)
            cr.fill()
        _round_rect(cr, CX - 10, 198, 20, 26, 6)
        self._part_fill(cr, "button6")
        cr.fill()
        _text(cr, "DPI", CX, 211, 7, TEXT)

        for sid, lx in (("button1", CX - 58), ("button2", CX + 58)):
            col = (1, 1, 1) if sid in self.selected else TEXT
            _text(cr, "L" if sid == "button1" else "R", lx, 140, 22, col)
            _text(cr, self.labels.get(sid, ""), lx, 166, 10, col, bold=False)

        # side keypad
        pw = 3 * KEY + 2 * GAP
        ph = 4 * KEY + 3 * GAP
        _round_rect(cr, GX - 14, GY - 44, pw + 28, ph + 58, 16)
        cr.set_source_rgb(*BODY)
        cr.fill_preserve()
        cr.set_source_rgb(*EDGE)
        cr.set_line_width(1.5)
        cr.stroke()
        _text(cr, "SIDE KEYPAD", GX + pw / 2, GY - 24, 11, DIM)
        for r, row in enumerate(SIDE_GRID):
            for c, n in enumerate(row):
                sid = f"side{n}"
                kx, ky = GX + c * (KEY + GAP), GY + r * (KEY + GAP)
                _round_rect(cr, kx, ky, KEY, KEY, 10)
                self._part_fill(cr, sid)
                cr.fill()
                col = (1, 1, 1) if sid in self.selected else TEXT
                _text(cr, str(n), kx + KEY / 2, ky + 20, 17, col)
                label = self.labels.get(sid, "")
                _text(cr, label[:7], kx + KEY / 2, ky + 41, 9, col if sid in self.selected else DIM, bold=False)

        # status line for hovered/selected button
        sid = self.hover or next(iter(self.selected), None)
        if sid:
            _text(cr, f"{self.names[sid]}:  {self.labels.get(sid, '')}", CW / 2, CH - 18, 14, TEXT)


class ColorPicker(Gtk.Box):
    """Saturation/value square, hue strip, swatches and hex entry. Calls on_change(hex)."""

    SWATCHES = ["#ff0000", "#ff5a1f", "#ffd000", "#00ff40", "#00e5ff",
                "#0050ff", "#8a2be2", "#ff00c8", "#ffffff"]
    W = 300

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.h, self.s, self.v = 0.0, 1.0, 1.0
        self.on_change = None

        self.sv = Gtk.DrawingArea(content_width=self.W, content_height=180)
        self.sv.set_draw_func(self._draw_sv)
        self._drag(self.sv, self._pick_sv)
        self.hue = Gtk.DrawingArea(content_width=self.W, content_height=18)
        self.hue.set_draw_func(self._draw_hue)
        self._drag(self.hue, self._pick_hue)
        self.swatches = Gtk.DrawingArea(content_width=self.W, content_height=28)
        self.swatches.set_draw_func(self._draw_swatches)
        click = Gtk.GestureClick()
        click.connect("pressed", self._pick_swatch)
        self.swatches.add_controller(click)

        self.entry = Gtk.Entry(max_length=7, width_chars=8, hexpand=False)
        self.entry.connect("activate", self._on_entry)
        hex_row = Gtk.Box(spacing=8)
        hex_row.append(Gtk.Label(label="HEX", css_classes=["section-title"]))
        hex_row.append(self.entry)

        for wdg in (self.sv, self.hue, self.swatches, hex_row):
            self.append(wdg)

    def hex(self):
        return rgbf_to_hex(*colorsys.hsv_to_rgb(self.h, self.s, self.v))

    def set_hex(self, color):
        self.h, self.s, self.v = colorsys.rgb_to_hsv(*hex_to_rgbf(color))
        self._refresh()

    def _refresh(self):
        self.entry.set_text(self.hex())
        for wdg in (self.sv, self.hue):
            wdg.queue_draw()

    def _emit(self):
        self._refresh()
        if self.on_change:
            self.on_change(self.hex())

    @staticmethod
    def _drag(widget, fn):
        drag = Gtk.GestureDrag()
        start = [0, 0]

        def begin(_g, x, y):
            start[:] = [x, y]
            fn(widget, x, y)

        drag.connect("drag-begin", begin)
        drag.connect("drag-update", lambda _g, dx, dy: fn(widget, start[0] + dx, start[1] + dy))
        widget.add_controller(drag)

    def _pick_sv(self, w, x, y):
        self.s = min(max(x / w.get_width(), 0), 1)
        self.v = 1 - min(max(y / w.get_height(), 0), 1)
        self._emit()

    def _pick_hue(self, w, x, _y):
        self.h = min(max(x / w.get_width(), 0), 0.9999)
        self._emit()

    def _pick_swatch(self, _g, _n, x, _y):
        i = int(x // (self.swatches.get_width() / len(self.SWATCHES)))
        if 0 <= i < len(self.SWATCHES):
            self.set_hex(self.SWATCHES[i])
            self._emit()

    def _on_entry(self, entry):
        text = entry.get_text().strip().lstrip("#")
        if len(text) == 6 and all(c in "0123456789abcdefABCDEF" for c in text):
            self.set_hex("#" + text)
            self._emit()
        else:
            self._refresh()

    def _draw_sv(self, _a, cr, w, h):
        _round_rect(cr, 0, 0, w, h, 10)
        cr.clip()
        cr.set_source_rgb(*colorsys.hsv_to_rgb(self.h, 1, 1))
        cr.paint()
        g = cairo.LinearGradient(0, 0, w, 0)
        g.add_color_stop_rgba(0, 1, 1, 1, 1)
        g.add_color_stop_rgba(1, 1, 1, 1, 0)
        cr.set_source(g)
        cr.paint()
        g = cairo.LinearGradient(0, 0, 0, h)
        g.add_color_stop_rgba(0, 0, 0, 0, 0)
        g.add_color_stop_rgba(1, 0, 0, 0, 1)
        cr.set_source(g)
        cr.paint()
        self._marker(cr, self.s * w, (1 - self.v) * h)

    def _draw_hue(self, _a, cr, w, h):
        _round_rect(cr, 0, 0, w, h, h / 2)
        g = cairo.LinearGradient(0, 0, w, 0)
        for i in range(7):
            g.add_color_stop_rgb(i / 6, *colorsys.hsv_to_rgb(i / 6 % 1, 1, 1))
        cr.set_source(g)
        cr.fill()
        self._marker(cr, self.h * w, h / 2)

    def _draw_swatches(self, _a, cr, w, h):
        step = w / len(self.SWATCHES)
        for i, color in enumerate(self.SWATCHES):
            cr.arc(step * i + step / 2, h / 2, min(step, h) / 2 - 2, 0, 2 * math.pi)
            cr.set_source_rgb(*hex_to_rgbf(color))
            cr.fill()

    @staticmethod
    def _marker(cr, x, y):
        cr.arc(x, y, 7, 0, 2 * math.pi)
        cr.set_source_rgb(1, 1, 1)
        cr.set_line_width(3)
        cr.stroke_preserve()
        cr.set_source_rgba(0, 0, 0, 0.5)
        cr.set_line_width(1)
        cr.stroke()
