"""hidraw transport for the Aerox 9 Wireless (wired cable or 2.4 GHz dongle)."""

import glob
import os
import select
import time

from . import protocol

VENDOR = 0x1038
# product id -> (name, wireless)
PRODUCTS = {
    0x185A: ("Aerox 9 Wireless (wired)", False),
    0x1858: ("Aerox 9 Wireless (2.4 GHz)", True),
    0x1876: ("Aerox 9 Wireless WOW (wired)", False),
    0x1874: ("Aerox 9 Wireless WOW (2.4 GHz)", True),
}
INTERFACE = 3
COMMAND_DELAY = 0.05  # the mouse drops commands sent back-to-back
READ_TIMEOUT = 0.2
REPORT_LEN = 64


class DeviceError(Exception):
    pass


def find_devices():
    """Yields (hidraw_path, product_id) for matching mice on the config interface."""
    for node in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        try:
            with open(os.path.join(node, "device/uevent")) as f:
                uevent = dict(l.strip().split("=", 1) for l in f if "=" in l)
            _, vid, pid = uevent["HID_ID"].split(":")
            vid, pid = int(vid, 16), int(pid, 16)
            iface = os.path.basename(os.path.realpath(os.path.join(node, "device/..")))
        except (OSError, KeyError, ValueError):
            continue
        if vid == VENDOR and pid in PRODUCTS and iface.endswith(f".{INTERFACE}"):
            yield "/dev/" + os.path.basename(node), pid


class Mouse:
    def __init__(self, path, pid):
        self.path = path
        self.name, self.wireless = PRODUCTS[pid]
        try:
            self._fd = os.open(path, os.O_RDWR)
        except OSError as e:
            raise DeviceError(f"cannot open {path}: {e.strerror}") from e

    @classmethod
    def open(cls):
        """Opens the mouse, preferring the cable over the dongle when both are present."""
        devices = sorted(find_devices(), key=lambda d: PRODUCTS[d[1]][1])
        if not devices:
            raise DeviceError("Aerox 9 Wireless not found")
        return cls(*devices[0])

    def close(self):
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _drain(self):
        while select.select([self._fd], [], [], 0)[0]:
            os.read(self._fd, REPORT_LEN)

    def _read(self):
        if select.select([self._fd], [], [], READ_TIMEOUT)[0]:
            return os.read(self._fd, REPORT_LEN)
        return None

    def send(self, cmd, expect_reply=False):
        cmd = list(cmd)
        if self.wireless:
            cmd[0] |= protocol.WIRELESS_FLAG
        try:
            self._drain()
            os.write(self._fd, bytes([0x00] + cmd))
            reply = self._read() if (expect_reply or self.wireless) else None
        except OSError as e:  # e.g. ENODEV after unplugging
            raise DeviceError(f"mouse disconnected ({e.strerror})") from e
        time.sleep(COMMAND_DELAY)
        return reply

    def send_all(self, cmds):
        for c in cmds:
            self.send(c)

    def battery(self):
        return protocol.parse_battery(self.send(protocol.BATTERY, expect_reply=True))

    def save(self):
        """Persist current settings to onboard memory (writes flash; don't spam)."""
        self.send(protocol.SAVE)
