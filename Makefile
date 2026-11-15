PREFIX ?= $(HOME)/.local
BIN := build/aerox9

$(BIN): $(wildcard aerox9/*.py aerox9/*.css)
	mkdir -p build/src
	rm -rf build/src/aerox9
	cp -r aerox9 build/src/
	find build/src -name __pycache__ -prune -exec rm -rf {} +
	python3 -m zipapp build/src -o $@ -p "/usr/bin/env python3" -m "aerox9.__main__:main"

install: $(BIN)
	install -Dm755 $(BIN) $(PREFIX)/bin/aerox9
	sed "s|^Exec=.*|Exec=$(PREFIX)/bin/aerox9|" aerox9.desktop > build/aerox9.desktop
	install -Dm644 build/aerox9.desktop $(PREFIX)/share/applications/aerox9.desktop

uninstall:
	rm -f $(PREFIX)/bin/aerox9 $(PREFIX)/share/applications/aerox9.desktop

test:
	python3 -m unittest tests/test_protocol.py

clean:
	rm -rf build

.PHONY: install uninstall test clean

screenshots:
	mkdir -p docs/screenshots build/shot-config
	XDG_CONFIG_HOME=$(CURDIR)/build/shot-config python3 tools/screenshots.py $(CURDIR) $(CURDIR)/docs/screenshots
	rm -rf build/shot-config

.PHONY: screenshots
