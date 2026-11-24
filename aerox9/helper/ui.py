"""Small GTK builders shared by the pages."""

import os
from importlib import resources

from gi.repository import Adw, Gdk, Gtk

_icons_registered = False


def register_icons():
    """Make the bundled aerox9-*-symbolic icons findable, independent of the system icon theme.

    Running from source: the package's icons/ folder is added to the search path.
    Installed zipapp: `make install` puts them in ~/.local/share/icons/hicolor, which GTK always searches.
    """
    global _icons_registered
    if _icons_registered:
        return
    _icons_registered = True
    icons = resources.files("aerox9") / "icons"
    if isinstance(icons, os.PathLike) and os.path.isdir(icons):
        Gtk.IconTheme.get_for_display(Gdk.Display.get_default()).add_search_path(os.fspath(icons))


def label(text, *classes, **kw):
    kw.setdefault("xalign", 0)
    return Gtk.Label(label=text, css_classes=list(classes), **kw)


def panel(title=None, spacing=12):
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing, css_classes=["panel"])
    if title:
        box.append(label(title.upper(), "section-title"))
    return box


def segmented(options, active, on_toggle):
    """Linked toggle buttons; on_toggle(value) fires when one becomes active."""
    box = Gtk.Box(css_classes=["linked", "segmented"])
    buttons = {}
    first = None
    for value, text in options:
        btn = Gtk.ToggleButton(label=text, group=first)
        first = first or btn
        btn.set_active(value == active)
        btn.connect("toggled", lambda b, v=value: b.get_active() and on_toggle(v))
        box.append(btn)
        buttons[value] = btn
    return box, buttons


def page(child):
    clamp = Adw.Clamp(maximum_size=1100, child=child, margin_top=24, margin_bottom=24,
                      margin_start=24, margin_end=24)
    return Gtk.ScrolledWindow(child=clamp, hscrollbar_policy=Gtk.PolicyType.NEVER)


def dialog(parent, heading, body, responses, default, on_response, extra=None, destructive=False):
    """Adw.AlertDialog (libadwaita 1.5+) or Adw.MessageDialog; on_response(id) gets the chosen id."""
    if hasattr(Adw, "AlertDialog"):
        dlg = Adw.AlertDialog(heading=heading, body=body or "")
    else:
        dlg = Adw.MessageDialog(transient_for=parent, modal=True, heading=heading, body=body or "")
    for rid, text in responses:
        dlg.add_response(rid, text)
    dlg.set_default_response(default)
    dlg.set_close_response(responses[0][0])
    dlg.set_response_appearance(default, Adw.ResponseAppearance.DESTRUCTIVE if destructive
                                else Adw.ResponseAppearance.SUGGESTED)
    if extra:
        dlg.set_extra_child(extra)
    dlg.connect("response", lambda _d, rid: on_response(rid))
    if hasattr(Adw, "AlertDialog"):
        dlg.present(parent)
    else:
        dlg.present()
    return dlg
