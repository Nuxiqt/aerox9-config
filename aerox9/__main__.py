"""aerox9 [gui|apply|battery|save|profile]"""

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
    a.add_argument("--profile", metavar="NAME", help="send this profile instead of the active one")
    sub.add_parser("battery", help="print battery level")
    sub.add_parser("save", help="persist current settings to onboard memory")
    pr = sub.add_parser("profile", help="list profiles, or switch with `profile use NAME`")
    psub = pr.add_subparsers(dest="profile_cmd")
    psub.add_parser("list", help="list profiles (default); * marks the active one")
    u = psub.add_parser("use", help="make NAME the active profile and send it to the mouse")
    u.add_argument("name")
    u.add_argument("--no-apply", action="store_true", help="only switch; don't send anything")
    args = p.parse_args()

    if args.cmd in (None, "gui"):
        from . import gui
        return gui.run()

    cmds = []
    if args.cmd == "profile":
        store = settings.load_store()
        if args.profile_cmd in (None, "list"):
            for name in store["profiles"]:
                print(("* " if name == store["active"] else "  ") + name)
            return 0
        if args.name not in store["profiles"]:
            print(f"error: no profile named {args.name!r}", file=sys.stderr)
            return 1
        old = store["profiles"][store["active"]]
        store["active"] = args.name
        settings.save_store(store)
        if args.no_apply:
            return 0
        cmds = settings.switch_commands(old, store["profiles"][args.name])
    elif args.cmd == "apply":
        try:
            data = settings.load(profile=args.profile)
        except KeyError:
            print(f"error: no profile named {args.profile!r}", file=sys.stderr)
            return 1
        cmds = settings.all_commands(data, include_buttons=args.buttons)

    try:
        with Mouse.open() as m:
            if args.cmd == "battery":
                b = m.battery()
                print("unavailable" if b is None else f"{b[0]}%{' (charging)' if b[1] else ''}")
            elif args.cmd == "save":
                m.save()
            else:
                m.send_all(cmds)
    except DeviceError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
