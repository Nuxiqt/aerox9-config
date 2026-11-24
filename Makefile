PREFIX ?= $(HOME)/.local
BIN := build/aerox9
ICONS := $(wildcard aerox9/icons/*.svg)
ICON_THEME := $(PREFIX)/share/icons/hicolor
ICON_DIR := $(ICON_THEME)/scalable/actions
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
	sed "s|^Exec=.*|Exec=$(PREFIX)/bin/aerox9|" aerox9.desktop > build/aerox9.desktop
	install -Dm644 build/aerox9.desktop $(PREFIX)/share/applications/aerox9.desktop
	install -Dm644 -t $(ICON_DIR) $(ICONS)
	$(UPDATE_ICON_CACHE)

uninstall:
	rm -f $(PREFIX)/bin/aerox9 $(PREFIX)/share/applications/aerox9.desktop
	rm -f $(addprefix $(ICON_DIR)/,$(notdir $(ICONS)))
	$(UPDATE_ICON_CACHE)

test:
	python3 -m unittest tests/test_protocol.py

clean:
	rm -rf build

.PHONY: install uninstall test clean
