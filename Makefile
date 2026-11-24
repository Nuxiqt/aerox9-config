PREFIX ?= $(HOME)/.local
BIN := build/aerox9
APP_ID := io.github.aerox9
APP_ICON := aerox9/icons/$(APP_ID).svg
ICONS := $(wildcard aerox9/icons/*-symbolic.svg)
ICON_THEME := $(PREFIX)/share/icons/hicolor
ICON_DIR := $(ICON_THEME)/scalable/actions
APP_ICON_DIR := $(ICON_THEME)/scalable/apps
# KDE/GNOME on Wayland match a window to its launcher by app_id, so the .desktop file must be named $(APP_ID).desktop.
DESKTOP := $(PREFIX)/share/applications/$(APP_ID).desktop
# A stale icon-theme.cache hides newly installed icons from GTK, so refresh it if one exists.
UPDATE_ICON_CACHE = if [ -f $(ICON_THEME)/icon-theme.cache ]; then gtk-update-icon-cache -f -t -q $(ICON_THEME) || true; fi

$(BIN): $(wildcard aerox9/*.py aerox9/*.css)
	mkdir -p build/src
	rm -rf build/src/aerox9
	cp -r aerox9 build/src/
	find build/src -name __pycache__ -prune -exec rm -rf {} +
	rm -rf build/src/aerox9/icons  # installed into the icon theme instead
	python3 -m zipapp build/src -o $@ -p "/usr/bin/env python3" -m "aerox9.__main__:main"

install: $(BIN)
	install -Dm755 $(BIN) $(PREFIX)/bin/aerox9
	sed "s|^Exec=.*|Exec=$(PREFIX)/bin/aerox9|" $(APP_ID).desktop > build/$(APP_ID).desktop
	install -Dm644 build/$(APP_ID).desktop $(DESKTOP)
	rm -f $(PREFIX)/share/applications/aerox9.desktop  # old name, before it matched the app_id
	install -Dm644 -t $(ICON_DIR) $(ICONS)
	install -Dm644 -t $(APP_ICON_DIR) $(APP_ICON)
	$(UPDATE_ICON_CACHE)
	command -v update-desktop-database >/dev/null && update-desktop-database -q $(PREFIX)/share/applications || true

uninstall:
	rm -f $(PREFIX)/bin/aerox9 $(DESKTOP) $(PREFIX)/share/applications/aerox9.desktop
	rm -f $(addprefix $(ICON_DIR)/,$(notdir $(ICONS))) $(APP_ICON_DIR)/$(notdir $(APP_ICON))
	$(UPDATE_ICON_CACHE)

test:
	python3 -m unittest tests/test_protocol.py

clean:
	rm -rf build

.PHONY: install uninstall test clean
