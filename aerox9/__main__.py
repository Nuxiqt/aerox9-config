"""aerox9 [gui|apply|battery|save]"""

import argparse
import sys

from . import settings
from .device import DeviceError, Mouse


def main():
    p = argparse.ArgumentParser(prog="aerox9")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("gui", help="open the GUI (default)")
    a = sub.add_parser("apply", help="send stored settings to the mouse")
    a.add_argument("--buttons", action="store_true", help="also send the (experimental) button mapping")
    sub.add_parser("battery", help="print battery level")
    sub.add_parser("save", help="persist current settings to onboard memory")
    args = p.parse_args()

    if args.cmd in (None, "gui"):
        from . import gui
        return gui.run()
    try:
        with Mouse.open() as m:
            if args.cmd == "apply":
                m.send_all(settings.all_commands(settings.load(), include_buttons=args.buttons))
            elif args.cmd == "battery":
                b = m.battery()
                print("unavailable" if b is None else f"{b[0]}%{' (charging)' if b[1] else ''}")
            elif args.cmd == "save":
                m.save()
    except DeviceError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
