"""Applies the chosen color scheme and, for "System", tracks the desktop's dark mode and accent live."""

from importlib import resources

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from .. import themes, widgets
from . import accent_hex, hex_to_rgbf, round_rect


class ThemeController:
    """Applies a color scheme to the CSS and the diagrams; for "system", follows the desktop live."""

    def __init__(self):
        self.name = None
        self.listeners = []  # called after every (re)apply, e.g. to redraw custom-drawn widgets
        self._provider = None
        self._template = None
        self._portal = None
        self._portal_accent = None
        self._watching = False

    def apply(self, name):
        self.name = name
        sm = Adw.StyleManager.get_default()
        if name == themes.SYSTEM:
            self._watch()
            sm.set_color_scheme(Adw.ColorScheme.DEFAULT)  # libadwaita follows the desktop setting
            theme = self.system_palette()
        else:
            theme = themes.get(name)
            sm.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT if theme["scheme"] == "light"
                                else Adw.ColorScheme.FORCE_DARK)
        widgets.set_palette(theme)
        if self._provider is None:
            self._template = resources.files("aerox9").joinpath("style.css").read_text()
            self._provider = Gtk.CssProvider()
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(), self._provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self._provider.load_from_string(themes.css(self._template, theme))
        for fn in self.listeners:
            fn()

    def system_palette(self):
        sm = Adw.StyleManager.get_default()
        return themes.resolve(themes.SYSTEM, dark=sm.get_system_supports_color_schemes() and self._system_dark(),
                              accent=self._system_accent())

    def _system_dark(self):
        sm = Adw.StyleManager.get_default()
        if self.name == themes.SYSTEM:
            return sm.get_dark()
        # while a fixed scheme is forced, get_dark() reports that instead of the desktop's choice
        pref = self._portal_read("color-scheme")
        return pref.unpack() == 1 if pref is not None else sm.get_dark()

    def _system_accent(self):
        """The desktop accent as "#rrggbb", or None (then the theme's own accent is used)."""
        if self._portal_accent is None:
            v = self._portal_read("accent-color")
            self._portal_accent = accent_hex(v.unpack()) if v is not None else ""
        if self._portal_accent:
            return self._portal_accent
        # no portal: libadwaita 1.6+ still knows the (rounded) system accent
        sm = Adw.StyleManager.get_default()
        if hasattr(sm, "get_system_supports_accent_colors") and sm.get_system_supports_accent_colors():
            c = sm.get_accent_color_rgba()
            return accent_hex((c.red, c.green, c.blue))
        return None

    # --- desktop settings portal (org.freedesktop.appearance) --------------

    def _proxy(self):
        if self._portal is None:
            try:
                self._portal = Gio.DBusProxy.new_for_bus_sync(
                    Gio.BusType.SESSION, Gio.DBusProxyFlags.DO_NOT_AUTO_START_AT_CONSTRUCTION, None,
                    "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
                    "org.freedesktop.portal.Settings", None)
            except GLib.Error:
                self._portal = False
        return self._portal or None

    def _portal_read(self, key):
        proxy = self._proxy()
        if proxy is None:
            return None
        args = GLib.Variant("(ss)", ("org.freedesktop.appearance", key))
        try:
            return proxy.call_sync("ReadOne", args, Gio.DBusCallFlags.NONE, 1000, None).get_child_value(0) \
                .get_variant()
        except GLib.Error:
            pass
        try:  # portals before ReadOne existed wrap the value twice
            v = proxy.call_sync("Read", args, Gio.DBusCallFlags.NONE, 1000, None).get_child_value(0).get_variant()
            return v.get_variant() if v.get_type_string() == "v" else v
        except GLib.Error:
            return None

    def _watch(self):
        if self._watching:
            return
        self._watching = True

        def on_change(*_):
            if self.name == themes.SYSTEM:
                self.apply(self.name)

        Adw.StyleManager.get_default().connect("notify::dark", on_change)
        proxy = self._proxy()
        if proxy is not None:
            def on_signal(_p, _sender, signal, params):
                ns, key, value = params.unpack()
                if signal == "SettingChanged" and ns == "org.freedesktop.appearance" and key == "accent-color":
                    self._portal_accent = accent_hex(value) or ""
                    on_change()
            proxy.connect("g-signal", on_signal)


controller = ThemeController()


def theme_preview(get_theme):
    """A small mock of the app in get_theme()'s colors: sidebar with a selected item, a card, a button."""
    def draw(_a, cr, w, h):
        theme = get_theme()

        def rect(x, y, rw, rh, color, r=4):
            round_rect(cr, x, y, rw, rh, r)
            cr.set_source_rgb(*hex_to_rgbf(color))
            cr.fill()

        rect(0, 0, w, h, theme["bg"], 8)
        rect(0, 0, w * 0.32, h, theme["sidebar"], 8)
        for i in range(3):
            rect(8, 14 + i * 16, w * 0.32 - 16, 9, theme["accent"] if i == 0 else theme["raised"], 3)
        rect(w * 0.32 + 10, 12, w * 0.68 - 20, h - 24, theme["card"], 6)
        rect(w * 0.32 + 20, 22, w * 0.3, 7, theme["muted"], 3)
        rect(w * 0.32 + 20, 36, w * 0.45, 7, theme["trough"], 3)
        rect(w - 58, h - 34, 38, 12, theme["accent"], 6)
    area = Gtk.DrawingArea(content_width=150, content_height=90)
    area.set_draw_func(draw)
    return area
