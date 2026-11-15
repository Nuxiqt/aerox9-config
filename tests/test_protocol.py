import unittest

from aerox9 import protocol as p
from aerox9 import settings


class ProtocolTest(unittest.TestCase):
    # Expected bytes derived from rivalcfg's Aerox 9 profile and handlers.
    def test_sensitivity(self):
        self.assertEqual(p.sensitivity([400, 800, 1200, 2400, 3200]),
                         [0x2D, 5, 0, 0x04, 0x09, 0x0D, 0x1B, 0x26])
        self.assertEqual(p.sensitivity([100, 18000], 1), [0x2D, 2, 1, 0x00, 0xD6])
        self.assertEqual(p.dpi_code(1650), p.dpi_code(1600))  # rounds to step
        with self.assertRaises(ValueError):
            p.sensitivity([800] * 6)

    def test_simple(self):
        self.assertEqual(p.polling_rate(1000), [0x2B, 0x00])
        self.assertEqual(p.polling_rate(125), [0x2B, 0x03])
        self.assertEqual(p.zone_color("middle", [1, 2, 3]), [0x21, 0x01, 0x01, 1, 2, 3])
        self.assertEqual(p.reactive_color(None), [0x26, 0, 0, 0, 0, 0])
        self.assertEqual(p.reactive_color([9, 8, 7]), [0x26, 0x01, 0x00, 9, 8, 7])
        self.assertEqual(p.default_lighting("reactive-rainbow"), [0x27, 1, 1])
        self.assertEqual(p.sleep_timer(5), [0x29, 0xE0, 0x93, 0x04])   # 300000 ms
        self.assertEqual(p.dim_timer(30), [0x23, 0x0F, 0x01, 0, 0, 0x30, 0x75, 0x00])  # 30000 ms

    def test_battery(self):
        self.assertEqual(p.parse_battery(bytes([0x92, 0x8C])), (55, True))
        self.assertEqual(p.parse_battery(bytes([0x92, 0x15])), (100, False))
        self.assertIsNone(p.parse_battery(bytes([0x92, 0x00])))
        self.assertIsNone(p.parse_battery(None))

    def test_buttons_default(self):
        pkts = p.buttons({})
        self.assertEqual([len(x) for x in pkts], [32, 32, 42])
        self.assertEqual([x[:2] for x in pkts], [[0x2A, 0], [0x2A, 1], [0x2A, 2]])
        flat = pkts[0][2:] + pkts[1][2:] + pkts[2][2:]
        fields = [flat[i:i + 5] for i in range(0, 100, 5)]
        self.assertEqual(fields[0], [0x01, 0, 0, 0, 0])            # left
        self.assertEqual(fields[5], [0x30, 0, 0, 0, 0])            # dpi
        self.assertEqual(fields[6], [0x51, 0x20, 0, 0, 0])         # side3 -> "3"
        self.assertEqual(fields[9], [0x51, 0x2E, 0, 0, 0])         # side12 -> "="
        self.assertEqual(fields[18], [0x31, 0, 0, 0, 0])           # scroll up

    def test_buttons_custom(self):
        pkts = p.buttons({"side1": ("media", "PlayPause"), "button2": ("disabled", None)})
        self.assertEqual(pkts[0][2 + 5:2 + 10], [0, 0, 0, 0, 0])
        self.assertEqual(pkts[2][2 + 10:2 + 15], [0x61, 0xCD, 0, 0, 0])  # side1 at offset 70
        with self.assertRaises(ValueError):
            p.buttons({"nope": ("dpi", None)})

    def test_settings_commands(self):
        cmds = settings.all_commands(settings.DEFAULTS)
        self.assertEqual(len(cmds), 1 + 1 + 3 + 1 + 1 + 1 + 1 + 3)
        self.assertEqual(settings.section_commands(dict(settings.DEFAULTS, rainbow=True), "lighting"),
                         [[0x22, 0xFF]])


if __name__ == "__main__":
    unittest.main()
