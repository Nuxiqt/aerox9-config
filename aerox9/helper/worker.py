"""Background thread that owns the HID device."""

import queue
import threading

from gi.repository import GLib

from ..device import DeviceError, Mouse


class DeviceWorker:
    """Serialises all HID I/O on one background thread."""

    def __init__(self, on_status):
        self._q = queue.Queue()
        self._mouse = None
        # called on the main loop: ((name, wireless) or None, error or None)
        self._on_status = on_status
        threading.Thread(target=self._run, daemon=True).start()

    def submit(self, job, on_done=None):
        """job(mouse) runs on the worker; on_done(result) runs on the main loop."""
        self._q.put((job, on_done))

    def reset(self):
        """Close the device so the next job re-discovers it (e.g. after a hotplug)."""
        self._q.put((None, None))

    def _close(self):
        if self._mouse:
            self._mouse.close()
        self._mouse = None

    def _run(self):
        while True:
            job, on_done = self._q.get()
            if job is None:
                self._close()
                continue
            try:
                if self._mouse is None:
                    self._mouse = Mouse.open()
                    GLib.idle_add(self._on_status, (self._mouse.name, self._mouse.wireless), None)
                result = job(self._mouse)
            except DeviceError as e:
                self._close()
                GLib.idle_add(self._on_status, None, str(e))
                continue
            if on_done:
                GLib.idle_add(on_done, result)
