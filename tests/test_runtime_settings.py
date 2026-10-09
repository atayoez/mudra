import unittest
from types import SimpleNamespace

from runtime_settings import SETTING_SPECS, normalize_updates, values_from_args


DEFAULTS = {
    "tap_lift": 0.14,
    "tap_return": 0.055,
    "tap_cooldown": 0.22,
    "thumb_lift": 0.16,
    "thumb_return": 0.065,
    "four_finger_scroll": True,
    "scroll_rest": 0.085,
    "scroll_start": 0.006,
    "scroll_speed": 95.0,
    "scroll_release": 0.16,
    "invert_scroll": False,
    "smart_pinky": True,
    "median": 3,
    "mincutoff": 1.0,
    "beta": 0.05,
    "conf": 0.8,
}


class RuntimeSettingsTests(unittest.TestCase):
    def test_defaults_cover_every_supported_setting(self):
        self.assertEqual(set(DEFAULTS), set(SETTING_SPECS))
        self.assertEqual(values_from_args(SimpleNamespace(**DEFAULTS)), DEFAULTS)

    def test_numeric_update_is_normalized(self):
        out = normalize_updates(DEFAULTS, {"scroll_speed": 120})
        self.assertEqual(out, {"scroll_speed": 120.0})

    def test_unknown_setting_is_rejected(self):
        with self.assertRaises(KeyError):
            normalize_updates(DEFAULTS, {"shell_command": "rm -rf /"})

    def test_boolean_must_be_boolean(self):
        with self.assertRaises(TypeError):
            normalize_updates(DEFAULTS, {"smart_pinky": 1})

    def test_out_of_range_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_updates(DEFAULTS, {"conf": 1.0})

    def test_tap_return_must_stay_below_lift(self):
        with self.assertRaises(ValueError):
            normalize_updates(DEFAULTS, {"tap_return": 0.20})

    def test_thumb_return_must_stay_below_lift(self):
        with self.assertRaises(ValueError):
            normalize_updates(DEFAULTS, {"thumb_return": 0.20})


if __name__ == "__main__":
    unittest.main()
