"""GTK4 / libadwaita GUI."""

import copy
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from . import protocol, settings, themes  # noqa: E402
from .helper import rgbf_to_hex, ui  # noqa: E402
from .helper.actions import CATEGORIES, KIND_CATEGORY, action_label, action_short  # noqa: E402
from .helper.theme_controller import controller as theme, theme_preview  # noqa: E402
from .helper.worker import DeviceWorker  # noqa: E402
from .widgets import ColorPicker, MouseDiagram  # noqa: E402

APP_ID = "io.github.aerox9"
DEBOUNCE_MS = 300
POLL_S = 5  # battery / charging poll interval
HOTPLUG_SETTLE_MS = 1000


class Window(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Aerox 9", default_width=1240, default_height=800)
        ui.register_icons()
        self.store = settings.load_store()
        self.data = self.store["profiles"][self.store["active"]]
        self._pending = {}
        self._batt_stamp = ""
        self.worker = DeviceWorker(self._on_device_status)
        self._install_profile_actions()

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, transition_duration=150)
        pages = [
            ("buttons", "Buttons", "aerox9-buttons-symbolic"),
            ("dpi", "DPI", "aerox9-dpi-symbolic"),
            ("lighting", "Illumination", "aerox9-lighting-symbolic"),
            ("power", "Power", "aerox9-power-symbolic"),
        ]
        self.stack.add_named(self._settings_page(), "settings")
        theme.listeners.append(self._redraw_diagrams)
        self._build_pages()

        self.page_title = ui.label("", "panel-title")
        header = Adw.HeaderBar(title_widget=self.page_title, css_classes=["flat"])
        self.banner = Adw.Banner(title="Looking for mouse…", button_label="Retry", revealed=True)
        self.banner.connect("button-clicked", lambda *_: self._probe())
        content = Adw.ToolbarView(content=self.stack)
        content.add_top_bar(header)
        content.add_top_bar(self.banner)

        split = Adw.OverlaySplitView(sidebar=self._sidebar(pages), content=content,
                                     min_sidebar_width=230, max_sidebar_width=260)
        self.toasts = Adw.ToastOverlay(child=split)
        self.set_content(self.toasts)

        self.nav["buttons"].set_active(True)
        self._watch_hotplug()
        self._probe()
        GLib.timeout_add_seconds(POLL_S, self._probe)

    # --- sidebar ------------------------------------------------------------

    def _sidebar(self, pages):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_start=14,
                      margin_end=14, margin_bottom=16)
        box.append(ui.label("AEROX 9", "brand", margin_top=4))
        box.append(ui.label("WIRELESS", "brand-sub"))
        conn_row = Gtk.Box(spacing=8, margin_top=10)
        self.conn_icon = Gtk.Image(icon_name="aerox9-offline-symbolic", css_classes=["status"])
        self.status_lbl = ui.label("Searching…", "status")
        conn_row.append(self.conn_icon)
        conn_row.append(self.status_lbl)
        box.append(conn_row)
        batt_row = Gtk.Box(spacing=8, margin_bottom=18)
        self.side_batt_bar = Gtk.LevelBar(min_value=0, max_value=100, hexpand=True,
                                          valign=Gtk.Align.CENTER, css_classes=["battery"])
        self.side_batt_bar.remove_offset_value("low")
        self.side_batt_bar.remove_offset_value("high")
        self.side_batt_bar.remove_offset_value("full")
        self.side_batt_lbl = ui.label("—", "status")
        batt_row.append(self.side_batt_bar)
        batt_row.append(self.side_batt_lbl)
        box.append(batt_row)

        box.append(ui.label("PROFILE", "section-title"))
        prof_row = Gtk.Box(spacing=6, margin_bottom=18)
        self.profile_model = Gtk.StringList()
        self.profile_dd = Gtk.DropDown(model=self.profile_model, hexpand=True,
                                       tooltip_text="Active profile")
        self._syncing_profiles = False
        self.profile_dd.connect("notify::selected", self._on_profile_selected)
        prof_row.append(self.profile_dd)
        menu = Gio.Menu()
        menu.append("New profile…", "win.profile-new")
        menu.append("Duplicate…", "win.profile-duplicate")
        menu.append("Rename…", "win.profile-rename")
        menu.append("Delete", "win.profile-delete")
        prof_row.append(Gtk.MenuButton(icon_name="aerox9-menu-symbolic", menu_model=menu,
                                       css_classes=["flat"], tooltip_text="Manage profiles"))
        box.append(prof_row)
        self._refresh_profiles()

        self.nav = {}
        group = None
        for name, title, icon in pages:
            inner = Gtk.Box(spacing=12)
            inner.append(Gtk.Image(icon_name=icon))
            inner.append(Gtk.Label(label=title.upper()))
            btn = Gtk.ToggleButton(child=inner, group=group, css_classes=["flat", "nav-button"])
            group = group or btn
            btn.connect("toggled", self._on_nav, name, title)
            box.append(btn)
            self.nav[name] = btn

        box.append(Gtk.Box(vexpand=True))
        inner = Gtk.Box(spacing=12)
        inner.append(Gtk.Image(icon_name="aerox9-settings-symbolic"))
        inner.append(Gtk.Label(label="SETTINGS"))
        btn = Gtk.ToggleButton(child=inner, group=group, css_classes=["flat", "nav-button"],
                               tooltip_text="App settings (shared by all profiles)")
        btn.connect("toggled", self._on_nav, "settings", "Settings")
        box.append(btn)
        self.nav["settings"] = btn
        reapply = Gtk.Button(label="Re-apply settings", css_classes=["flat"],
                             tooltip_text="Re-send all stored settings except buttons")
        reapply.connect("clicked", self._on_apply_all)
        box.append(reapply)
        save = Gtk.Button(label="Save to mouse", css_classes=["suggested-action", "pill"],
                          tooltip_text="Write current settings to onboard memory")
        save.connect("clicked", self._on_save)
        box.append(save)

        view = Adw.ToolbarView(content=box, css_classes=["sidebar-pane"])
        view.add_top_bar(Adw.HeaderBar(show_title=False, show_end_title_buttons=False, css_classes=["flat"]))
        return view

    def _on_nav(self, btn, name, title):
        if btn.get_active():
            self.stack.set_visible_child_name(name)
            self.page_title.set_label(title)

    # --- profiles -----------------------------------------------------------

    def _build_pages(self):
        """(Re)build every page from self.data, keeping the visible one."""
        visible = self.stack.get_visible_child_name()
        for name in ("buttons", "dpi", "lighting", "power"):
            if child := self.stack.get_child_by_name(name):
                self.stack.remove(child)
        for name, widget in (
            ("buttons", self._buttons_page()),
            ("dpi", self._performance_page()),
            ("lighting", self._lighting_page()),
            ("power", self._power_page()),
        ):
            self.stack.add_named(widget, name)
        if visible:
            self.stack.set_visible_child_name(visible)
        self.batt_updated.set_label(self._batt_stamp)
        if hasattr(self, "status_lbl"):
            self._render_status()

    def _refresh_profiles(self):
        names = list(self.store["profiles"])
        self._syncing_profiles = True
        self.profile_model.splice(0, self.profile_model.get_n_items(), names)
        self.profile_dd.set_selected(names.index(self.store["active"]))
        self._syncing_profiles = False
        self.lookup_action("profile-delete").set_enabled(len(names) > 1)

    def _on_profile_selected(self, dd, _p):
        if self._syncing_profiles:
            return
        item = dd.get_selected_item()
        if item and item.get_string() != self.store["active"]:
            self._switch_profile(item.get_string())

    def _switch_profile(self, name):
        for src in self._pending.values():
            GLib.source_remove(src)
        self._pending.clear()
        old = self.data
        self.store["active"] = name
        self.data = self.store["profiles"][name]
        self._save()
        self._refresh_profiles()
        self._build_pages()
        cmds = settings.switch_commands(old, self.data)
        self.worker.submit(lambda m: m.send_all(cmds), lambda _: self._toast(f"Profile “{name}” applied"))

    def _install_profile_actions(self):
        for name, handler in (
            ("profile-new", lambda: self._ask_name("New profile", "Create",
                                                   settings.unique_name(self.store, "Profile"),
                                                   lambda n: self._add_profile(n, settings.DEFAULTS))),
            ("profile-duplicate", lambda: self._ask_name("Duplicate profile", "Duplicate",
                                                         settings.unique_name(self.store, self.store["active"]),
                                                         lambda n: self._add_profile(n, self.data))),
            ("profile-rename", lambda: self._ask_name("Rename profile", "Rename", self.store["active"],
                                                      self._rename_profile)),
            ("profile-delete", self._confirm_delete),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda _a, _p, h=handler: h())
            self.add_action(action)

    def _add_profile(self, name, source):
        self.store["profiles"][name] = copy.deepcopy(source)
        self._switch_profile(name)

    def _rename_profile(self, name):
        old = self.store["active"]
        # rebuild the dict so the profile keeps its position in the list
        self.store["profiles"] = {name if k == old else k: v for k, v in self.store["profiles"].items()}
        self.store["active"] = name
        self._save()
        self._refresh_profiles()

    def _confirm_delete(self):
        name = self.store["active"]

        def on_response(resp):
            if resp != "delete":
                return
            names = list(self.store["profiles"])
            nxt = names[names.index(name) - 1] if names.index(name) else names[1]
            del self.store["profiles"][name]
            self._switch_profile(nxt)

        ui.dialog(self, f"Delete “{name}”?", "This can't be undone.",
                [("cancel", "Cancel"), ("delete", "Delete")], "delete", on_response, destructive=True)

    def _ask_name(self, heading, verb, initial, on_ok):
        entry = Gtk.Entry(text=initial, activates_default=True)
        current = self.store["active"] if verb == "Rename" else None

        def valid():
            n = entry.get_text().strip()
            return bool(n) and (n == current or n not in self.store["profiles"])

        def on_response(resp):
            n = entry.get_text().strip()
            if resp == "ok" and valid() and n != current:
                on_ok(n)

        dlg = ui.dialog(self, heading, None, [("cancel", "Cancel"), ("ok", verb)], "ok", on_response, extra=entry)
        entry.connect("changed", lambda *_: dlg.set_response_enabled("ok", valid()))
        dlg.set_response_enabled("ok", valid())
        entry.grab_focus()
        entry.select_region(0, -1)

    # --- settings page (global) ---------------------------------------------

    def _settings_page(self):
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        panel = ui.panel("Appearance · color scheme")
        cards = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
                            max_children_per_line=4, column_spacing=12, row_spacing=12)
        group = None
        for name in themes.CHOICES:
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            if name == themes.SYSTEM:
                preview = theme_preview(lambda: theme.system_palette())
                theme.listeners.append(preview.queue_draw)
            else:
                preview = theme_preview(lambda t=themes.THEMES[name]: t)
            card.append(preview)
            card.append(ui.label(themes.LABELS[name], "theme-name"))
            btn = Gtk.ToggleButton(child=card, group=group, css_classes=["theme-card"])
            group = group or btn
            btn.set_active(name == self.store["app"]["theme"])
            btn.connect("toggled", lambda b, n=name: b.get_active() and self._set_theme(n))
            cards.append(btn)
        panel.append(cards)
        panel.append(ui.label("System follows your desktop's light/dark setting and accent color. "
                            "Applies to the app only; nothing is sent to the mouse. "
                            "Shared by all profiles.", "binding", wrap=True))
        col.append(panel)
        return ui.page(col)

    def _set_theme(self, name):
        self.store["app"]["theme"] = name
        self._save()
        theme.apply(name)

    def _redraw_diagrams(self):
        for diagram in (self.btn_diagram, self.light_diagram):
            diagram.queue_draw()

    # --- device plumbing ----------------------------------------------------

    def _watch_hotplug(self):
        """Re-detect the mouse when hidraw nodes appear/disappear (cable or dongle plugged/unplugged)."""
        self._conn = None
        self._batt = None
        self._error = None
        self._hotplug_src = None
        self._dev_monitor = Gio.File.new_for_path("/dev").monitor_directory(Gio.FileMonitorFlags.NONE, None)

        def fire():
            self._hotplug_src = None
            self.worker.reset()
            self._probe()
            return False

        def on_changed(_m, file, _other, event):
            if not file.get_basename().startswith("hidraw"):
                return
            if event not in (Gio.FileMonitorEvent.CREATED, Gio.FileMonitorEvent.DELETED):
                return
            if self._hotplug_src:
                GLib.source_remove(self._hotplug_src)
            # udev needs a moment to apply permissions to new nodes
            self._hotplug_src = GLib.timeout_add(HOTPLUG_SETTLE_MS, fire)

        self._dev_monitor.connect("changed", on_changed)

    def _on_device_status(self, conn, error):
        if conn != self._conn:
            if conn and self._conn:
                self._toast("Switched to " + ("2.4 GHz wireless" if conn[1] else "wired"))
            elif self._conn and not conn:
                self._toast("Mouse disconnected")
        self._conn = conn
        self._error = error
        if conn is None:
            self._batt = None
        self._render_status()

    def _probe(self):
        self.worker.submit(lambda m: m.battery(), self._show_battery)
        return True

    def _show_battery(self, batt):
        if batt and self._batt and batt[1] != self._batt[1]:
            self._toast("Charging" if batt[1] else "Unplugged · on battery")
        self._batt = batt
        stamp = time.strftime("%H:%M:%S")
        self._batt_stamp = f"Updated {stamp}" if batt else f"Checked {stamp} · no reply"
        self.batt_updated.set_label(self._batt_stamp)
        self._render_status()

    def _render_status(self):
        conn, batt = self._conn, self._batt
        wireless = bool(conn and conn[1])
        asleep = wireless and batt is None
        charging = bool(batt and batt[1])

        # connection line
        if conn is None:
            icon, text, state = "aerox9-offline-symbolic", "Not connected", "offline"
        elif wireless:
            icon = "aerox9-wireless-asleep-symbolic" if asleep else "aerox9-wireless-symbolic"
            text = "2.4 GHz · mouse asleep / off" if asleep else "2.4 GHz wireless"
            state = "idle" if asleep else "online"
        else:
            icon, text, state = "aerox9-wired-symbolic", "Wired", "online"
        self.conn_icon.set_from_icon_name(icon)
        self.status_lbl.set_label(text)
        for w in (self.conn_icon, self.status_lbl):
            w.set_css_classes(["status", state])
        self.banner.set_title(self._error or "Mouse not connected")
        self.banner.set_revealed(conn is None)

        # battery
        if batt is None:
            self.side_batt_lbl.set_label("—")
            self.batt_big.set_label("—")
            self.batt_state.set_label("Mouse asleep or off" if asleep else "Unavailable")
            for bar in (self.side_batt_bar, self.batt_bar):
                bar.set_value(0)
            return
        level = batt[0]
        cls = "charging" if charging else ("low" if level <= 15 else None)
        for w in (self.side_batt_lbl, self.batt_big):
            w.set_css_classes([c for c in ("status" if w is not self.batt_big else "big-number", cls) if c])
        for bar in (self.side_batt_bar, self.batt_bar):
            bar.set_value(level)
            (bar.add_css_class if level <= 15 and not charging else bar.remove_css_class)("low")
        self.side_batt_lbl.set_label(f"{level}%" + (" ⚡" if charging else ""))
        self.batt_big.set_label(f"{level}%")
        if charging:
            state = "Charging via cable" if not wireless else "Charging"
        else:
            state = "On battery"
        self.batt_state.set_label(state)

    def _changed(self, section, debounce=False):
        """Persist settings and push `section` to the mouse."""
        self._save()
        if section in self._pending:
            GLib.source_remove(self._pending.pop(section))
        if not debounce:
            self._send(section)
            return

        def fire():
            self._pending.pop(section, None)
            self._send(section)
            return False

        self._pending[section] = GLib.timeout_add(DEBOUNCE_MS, fire)

    def _save(self):
        settings.save_store(self.store)

    def _send(self, section):
        cmds = settings.section_commands(self.data, section)
        self.worker.submit(lambda m: m.send_all(cmds))

    def _toast(self, text):
        self.toasts.add_toast(Adw.Toast(title=text, timeout=3))

    def _on_save(self, _btn):
        self.worker.submit(lambda m: m.save(), lambda _: self._toast("Saved to onboard memory"))

    def _on_apply_all(self, _btn):
        cmds = settings.all_commands(self.data, include_buttons=False)
        self.worker.submit(lambda m: m.send_all(cmds), lambda _: self._toast("Settings re-applied"))

    # --- buttons page -------------------------------------------------------

    def _buttons_page(self):
        self.pending_buttons = {k: tuple(v) for k, v in self.data["buttons"].items()}
        self.sel_button = "button1"
        self._syncing_list = False

        # left: list of all buttons
        self.btn_list = Gtk.ListBox(css_classes=["bind-list"], selection_mode=Gtk.SelectionMode.SINGLE)
        self.btn_list.connect("row-selected", self._on_btn_row)
        self.btn_rows = {}
        main = [b for b in protocol.BUTTONS if not b[0].startswith("side")]
        side = sorted((b for b in protocol.BUTTONS if b[0].startswith("side")), key=lambda b: int(b[0][4:]))
        for title, buttons in (("Main", main), ("Side keypad", side)):
            self.btn_list.append(Gtk.ListBoxRow(
                selectable=False, activatable=False,
                child=ui.label(title.upper(), "section-title", margin_top=10)))
            for bid, name, _d in buttons:
                vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
                vbox.append(ui.label(name, "bind-name"))
                binding = ui.label("", "binding")
                vbox.append(binding)
                row = Gtk.ListBoxRow(child=vbox)
                row.bid = bid
                self.btn_list.append(row)
                self.btn_rows[bid] = (row, binding)
        left = ui.panel(spacing=0)
        left.set_size_request(240, -1)
        left.append(Gtk.ScrolledWindow(child=self.btn_list, vexpand=True,
                                       hscrollbar_policy=Gtk.PolicyType.NEVER))

        # centre: diagram
        self.btn_diagram = MouseDiagram("buttons")
        self.btn_diagram.on_select = self._select_button

        # right: binding editor
        right = ui.panel()
        right.set_size_request(320, -1)
        self.bind_title = ui.label("", "panel-title")
        self.bind_current = ui.label("", "binding")
        right.append(self.bind_title)
        right.append(self.bind_current)
        self.category = "Mouse"
        seg, self.cat_buttons = ui.segmented([(c, c) for c in CATEGORIES], self.category, self._on_category)
        right.append(seg)
        self.opt_search = Gtk.SearchEntry(placeholder_text="Search keys", visible=False)
        self.opt_search.connect("search-changed", lambda *_: self.opt_list.invalidate_filter())
        right.append(self.opt_search)
        self.opt_list = Gtk.ListBox(css_classes=["option-list"], selection_mode=Gtk.SelectionMode.NONE)
        self.opt_list.set_filter_func(self._filter_option)
        self.opt_list.connect("row-activated", lambda _l, row: self._assign(row.action))
        right.append(Gtk.ScrolledWindow(child=self.opt_list, vexpand=True,
                                        hscrollbar_policy=Gtk.PolicyType.NEVER))
        reset_one = Gtk.Button(label="Restore default", css_classes=["flat"])
        reset_one.connect("clicked", lambda *_: self._assign(protocol.DEFAULT_BUTTONS[self.sel_button]))
        right.append(reset_one)

        body = Gtk.Box(spacing=16, margin_top=8, margin_bottom=16, margin_start=16, margin_end=16, vexpand=True)
        body.append(left)
        body.append(self.btn_diagram)
        body.append(right)

        # bottom: apply bar
        bar = Gtk.Box(spacing=12, css_classes=["apply-bar"])
        bar.append(ui.label("Button changes are not applied yet (experimental)", hexpand=True))
        reset_all = Gtk.Button(label="Reset all", css_classes=["flat"])
        reset_all.connect("clicked", lambda *_: self._set_pending(dict(protocol.DEFAULT_BUTTONS)))
        revert = Gtk.Button(label="Revert")
        revert.connect("clicked", lambda *_: self._set_pending(
            {k: tuple(v) for k, v in self.data["buttons"].items()}))
        apply_btn = Gtk.Button(label="Apply to mouse", css_classes=["suggested-action"])
        apply_btn.connect("clicked", self._apply_buttons)
        for b in (reset_all, revert, apply_btn):
            bar.append(b)
        self.apply_bar = Gtk.Revealer(child=bar, transition_type=Gtk.RevealerTransitionType.SLIDE_UP)

        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        page.append(body)
        page.append(self.apply_bar)
        self._refresh_bindings()
        self._select_button("button1")
        return page

    def _refresh_bindings(self):
        stored = {k: tuple(v) for k, v in self.data["buttons"].items()}
        for bid, (_row, lbl) in self.btn_rows.items():
            action = self.pending_buttons[bid]
            lbl.set_label(action_label(action))
            (lbl.add_css_class if action != stored[bid] else lbl.remove_css_class)("changed")
        self.btn_diagram.labels = {b: action_short(a) for b, a in self.pending_buttons.items()}
        self.btn_diagram.queue_draw()
        self.apply_bar.set_reveal_child(self.pending_buttons != stored)

    def _select_button(self, bid):
        self.sel_button = bid
        self.btn_diagram.set_selected([bid])
        row, _ = self.btn_rows[bid]
        if self.btn_list.get_selected_row() is not row:
            self._syncing_list = True
            self.btn_list.select_row(row)
            self._syncing_list = False
        name = dict((b[0], b[1]) for b in protocol.BUTTONS)[bid]
        self.bind_title.set_label(name)
        action = self.pending_buttons[bid]
        self.bind_current.set_label("Assigned: " + action_label(action))
        cat = KIND_CATEGORY[action[0]]
        if cat != self.category:
            self.cat_buttons[cat].set_active(True)  # triggers _on_category
        else:
            self._rebuild_options()

    def _on_btn_row(self, _list, row):
        if row is not None and not self._syncing_list:
            self._select_button(row.bid)

    def _on_category(self, cat):
        self.category = cat
        self.opt_search.set_visible(cat == "Keyboard")
        self.opt_search.set_text("")
        self._rebuild_options()

    def _rebuild_options(self):
        self.opt_list.remove_all()
        current = self.pending_buttons[self.sel_button]
        for action in CATEGORIES[self.category]:
            box = Gtk.Box(spacing=8)
            box.append(ui.label(action_label(action), hexpand=True))
            if action == current:
                box.append(Gtk.Image(icon_name="aerox9-check-symbolic", css_classes=["accent"]))
            row = Gtk.ListBoxRow(child=box)
            row.action = action
            self.opt_list.append(row)

    def _filter_option(self, row):
        text = self.opt_search.get_text().strip().lower()
        return not text or text in action_label(row.action).lower()

    def _assign(self, action):
        self.pending_buttons[self.sel_button] = tuple(action)
        self._refresh_bindings()
        self._select_button(self.sel_button)

    def _set_pending(self, mapping):
        self.pending_buttons = {k: tuple(v) for k, v in mapping.items()}
        self._refresh_bindings()
        self._select_button(self.sel_button)

    def _apply_buttons(self, _btn):
        if ("mouse", "left") not in self.pending_buttons.values():
            self._toast("Refusing: at least one button must be Left click")
            return
        self.data["buttons"] = {k: list(v) for k, v in self.pending_buttons.items()}
        self._save()
        self._refresh_bindings()
        cmds = settings.section_commands(self.data, "buttons")
        self.worker.submit(lambda m: m.send_all(cmds), lambda _: self._toast("Button mapping applied"))

    # --- performance page ---------------------------------------------------

    def _performance_page(self):
        self.sel_stage = self.data["dpi_active"]
        self._syncing_dpi = False
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)

        sens = ui.panel("Sensitivity · DPI stages")
        top = Gtk.Box(spacing=10)
        self.stage_box = Gtk.Box(spacing=10, hexpand=True)
        top.append(self.stage_box)
        self.add_stage = Gtk.Button(icon_name="aerox9-add-symbolic", valign=Gtk.Align.CENTER,
                                    css_classes=["circular"], tooltip_text="Add stage")
        self.add_stage.connect("clicked", self._on_add_stage)
        self.del_stage = Gtk.Button(icon_name="aerox9-remove-symbolic", valign=Gtk.Align.CENTER,
                                    css_classes=["circular"], tooltip_text="Remove selected stage")
        self.del_stage.connect("clicked", self._on_del_stage)
        top.append(self.del_stage)
        top.append(self.add_stage)
        sens.append(top)

        value_row = Gtk.Box(spacing=8, margin_top=12)
        self.dpi_big = ui.label("", "big-number")
        value_row.append(self.dpi_big)
        value_row.append(ui.label("DPI", "unit", valign=Gtk.Align.BASELINE_CENTER, hexpand=True))
        self.dpi_spin = Gtk.SpinButton.new_with_range(protocol.DPI_MIN, protocol.DPI_MAX, protocol.DPI_STEP)
        self.dpi_spin.set_valign(Gtk.Align.CENTER)
        value_row.append(self.dpi_spin)
        sens.append(value_row)

        self.dpi_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, protocol.DPI_MIN,
                                                  protocol.DPI_MAX, protocol.DPI_STEP)
        self.dpi_scale.set_draw_value(False)
        for mark in (100, 3600, 7200, 10800, 14400, 18000):
            self.dpi_scale.add_mark(mark, Gtk.PositionType.BOTTOM, str(mark))
        sens.append(self.dpi_scale)
        self.dpi_scale.connect("value-changed", self._on_dpi_value, "scale")
        self.dpi_spin.connect("value-changed", self._on_dpi_value, "spin")

        self.set_active_btn = Gtk.Button(label="Set as active stage", halign=Gtk.Align.START)
        self.set_active_btn.connect("clicked", self._on_set_active_stage)
        sens.append(self.set_active_btn)
        col.append(sens)

        poll = ui.panel("Polling rate")
        rates = sorted(protocol.POLLING_RATES)

        def on_rate(rate):
            self.data["polling_rate"] = rate
            self._changed("polling_rate")

        seg, _ = ui.segmented([(r, f"{r} Hz") for r in rates], self.data["polling_rate"], on_rate)
        seg.set_halign(Gtk.Align.START)
        poll.append(seg)
        col.append(poll)

        self._rebuild_stages()
        return ui.page(col)

    def _rebuild_stages(self):
        while child := self.stage_box.get_first_child():
            self.stage_box.remove(child)
        self.stage_values = []
        group = None
        for i, dpi in enumerate(self.data["dpi"]):
            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            vbox.append(ui.label(f"STAGE {i + 1}", "section-title", xalign=0.5))
            value = ui.label(str(dpi), "stage-value", xalign=0.5)
            vbox.append(value)
            vbox.append(ui.label("ACTIVE" if i == self.data["dpi_active"] else " ", "stage-tag", xalign=0.5))
            btn = Gtk.ToggleButton(child=vbox, group=group, css_classes=["dpi-stage"])
            group = group or btn
            btn.set_active(i == self.sel_stage)
            btn.connect("toggled", lambda b, i=i: b.get_active() and self._select_stage(i))
            self.stage_box.append(btn)
            self.stage_values.append(value)
        n = len(self.data["dpi"])
        self.add_stage.set_sensitive(n < protocol.MAX_DPI_PRESETS)
        self.del_stage.set_sensitive(n > 1)
        self._select_stage(self.sel_stage)

    def _select_stage(self, i):
        self.sel_stage = i
        dpi = self.data["dpi"][i]
        self._syncing_dpi = True
        self.dpi_scale.set_value(dpi)
        self.dpi_spin.set_value(dpi)
        self._syncing_dpi = False
        self.dpi_big.set_label(str(dpi))
        self.set_active_btn.set_sensitive(i != self.data["dpi_active"])

    def _on_dpi_value(self, widget, source):
        if self._syncing_dpi:
            return
        dpi = int(round(widget.get_value() / protocol.DPI_STEP) * protocol.DPI_STEP)
        self.data["dpi"][self.sel_stage] = dpi
        self._syncing_dpi = True
        (self.dpi_spin if source == "scale" else self.dpi_scale).set_value(dpi)
        self._syncing_dpi = False
        self.dpi_big.set_label(str(dpi))
        self.stage_values[self.sel_stage].set_label(str(dpi))
        self._changed("dpi", debounce=True)

    def _on_add_stage(self, _b):
        self.data["dpi"].append(min(self.data["dpi"][-1] * 2, protocol.DPI_MAX))
        self.sel_stage = len(self.data["dpi"]) - 1
        self._rebuild_stages()
        self._changed("dpi")

    def _on_del_stage(self, _b):
        dpis = self.data["dpi"]
        dpis.pop(self.sel_stage)
        if self.data["dpi_active"] >= len(dpis) or self.data["dpi_active"] > self.sel_stage:
            self.data["dpi_active"] = max(self.data["dpi_active"] - 1, 0)
        self.sel_stage = min(self.sel_stage, len(dpis) - 1)
        self._rebuild_stages()
        self._changed("dpi")

    def _on_set_active_stage(self, _b):
        self.data["dpi_active"] = self.sel_stage
        self._rebuild_stages()
        self._changed("dpi")

    # --- lighting page ------------------------------------------------------

    def _lighting_page(self):
        self.sel_zones = list(protocol.ZONES)
        self.light_diagram = MouseDiagram("lighting")
        self.light_diagram.colors = dict(self.data["colors"])
        self.light_diagram.set_rainbow(self.data["rainbow"])
        self.light_diagram.on_select = lambda z: self.zone_buttons[z].set_active(True)

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        right.set_size_request(360, -1)

        effect = ui.panel("Effect")
        seg, _ = ui.segmented([(False, "Static"), (True, "Rainbow")], self.data["rainbow"], self._on_effect)
        effect.append(seg)
        right.append(effect)

        self.color_panel = ui.panel("Color")
        seg, self.zone_buttons = ui.segmented(
            [("all", "All")] + [(z, z.capitalize()) for z in protocol.ZONES], "all", self._on_zone)
        self.color_panel.append(seg)
        self.picker = ColorPicker()
        self.picker.set_hex(self.data["colors"]["top"])
        self.picker.on_change = self._on_zone_color
        self.color_panel.append(self.picker)
        self.color_panel.set_sensitive(not self.data["rainbow"])
        right.append(self.color_panel)

        reactive = ui.panel("Reactive · flash on click")
        row = Gtk.Box(spacing=12)
        sw = Gtk.Switch(active=self.data["reactive"] is not None, valign=Gtk.Align.CENTER)
        row.append(sw)
        row.append(ui.label("Enabled", hexpand=True))
        color_btn = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(with_alpha=False), valign=Gtk.Align.CENTER)
        rgba = Gdk.RGBA()
        rgba.parse(self.data["reactive"] or "#ffffff")
        color_btn.set_rgba(rgba)
        color_btn.set_sensitive(sw.get_active())
        row.append(color_btn)
        reactive.append(row)

        def reactive_hex():
            c = color_btn.get_rgba()
            return rgbf_to_hex(c.red, c.green, c.blue)

        def on_switch(s, _p):
            color_btn.set_sensitive(s.get_active())
            self.data["reactive"] = reactive_hex() if s.get_active() else None
            self._changed("reactive")

        def on_color(_b, _p):
            if sw.get_active():
                self.data["reactive"] = reactive_hex()
                self._changed("reactive", debounce=True)

        sw.connect("notify::active", on_switch)
        color_btn.connect("notify::rgba", on_color)
        right.append(reactive)

        startup = ui.panel("Power-on lighting")
        modes = list(protocol.DEFAULT_LIGHTING)
        dd = Gtk.DropDown.new_from_strings([m.replace("-", " + ").capitalize() for m in modes])
        dd.set_selected(modes.index(self.data["default_lighting"]))

        def on_mode(d, _p):
            self.data["default_lighting"] = modes[d.get_selected()]
            self._changed("default_lighting")

        dd.connect("notify::selected", on_mode)
        startup.append(dd)
        right.append(startup)

        self._on_zone("all")
        body = Gtk.Box(spacing=16)
        body.append(self.light_diagram)
        body.append(right)
        return ui.page(body)

    def _on_effect(self, rainbow):
        self.data["rainbow"] = rainbow
        self.color_panel.set_sensitive(not rainbow)
        self.light_diagram.set_rainbow(rainbow)
        self._changed("lighting")

    def _on_zone(self, zone):
        self.sel_zones = list(protocol.ZONES) if zone == "all" else [zone]
        self.light_diagram.set_selected(self.sel_zones)
        self.picker.set_hex(self.data["colors"][self.sel_zones[0]])

    def _on_zone_color(self, hexcolor):
        for z in self.sel_zones:
            self.data["colors"][z] = hexcolor
        self.light_diagram.colors = dict(self.data["colors"])
        self.light_diagram.queue_draw()
        self._changed("lighting", debounce=True)

    # --- power page ---------------------------------------------------------

    def _power_page(self):
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)

        batt = ui.panel("Battery")
        row = Gtk.Box(spacing=16)
        self.batt_big = ui.label("—", "big-number")
        row.append(self.batt_big)
        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, valign=Gtk.Align.CENTER)
        self.batt_state = ui.label("", "binding")
        self.batt_updated = ui.label("", "binding")
        info.append(self.batt_state)
        info.append(self.batt_updated)
        row.append(info)
        refresh = Gtk.Button(icon_name="aerox9-refresh-symbolic", valign=Gtk.Align.CENTER,
                             css_classes=["circular"], tooltip_text="Refresh")
        refresh.connect("clicked", lambda *_: self._probe())
        row.append(refresh)
        batt.append(row)
        self.batt_bar = Gtk.LevelBar(min_value=0, max_value=100, css_classes=["battery"])
        for name in ("low", "high", "full"):
            self.batt_bar.remove_offset_value(name)
        batt.append(self.batt_bar)
        col.append(batt)

        def fmt_min(v):
            return "Never" if v == 0 else f"{v} min"

        def fmt_sec(v):
            return "Never" if v == 0 else (f"{v} s" if v < 60 else f"{v // 60} min {v % 60:02d} s")

        for key, title, maximum, fmt, step in (
            ("sleep_timer", "Sleep after idle", protocol.SLEEP_MAX_MIN, fmt_min, 1),
            ("dim_timer", "Dim lighting after idle", protocol.DIM_MAX_S, fmt_sec, 5),
        ):
            panel = ui.panel(title)
            value = ui.label(fmt(self.data[key]), "panel-title")
            panel.append(value)
            scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, maximum, step)
            scale.set_draw_value(False)
            scale.set_value(self.data[key])

            def on_value(s, key=key, value=value, fmt=fmt, step=step):
                v = int(round(s.get_value() / step) * step)
                value.set_label(fmt(v))
                self.data[key] = v
                self._changed(key, debounce=True)

            scale.connect("value-changed", on_value)
            panel.append(scale)
            col.append(panel)
        return ui.page(col)


def run():
    app = Adw.Application(application_id=APP_ID)

    def on_startup(a):
        theme.apply(settings.load_store()["app"]["theme"])
        ui.register_icons()
        Gtk.Window.set_default_icon_name(APP_ID)  # X11 / windows without a matching .desktop file

    app.connect("startup", on_startup)
    app.connect("activate", lambda a: (a.get_active_window() or Window(a)).present())
    return app.run(None)
