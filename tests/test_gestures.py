import unittest

from gestures import DepthHoldDetector, DepthTapDetector, FourFingerScrollDetector


class GestureTests(unittest.TestCase):
    def test_tap_fires_on_return_to_rest(self):
        d = DepthTapDetector(trigger=0.10, release=0.03, cooldown=0.2)
        self.assertFalse(d.update(0.00, 0.0))
        self.assertFalse(d.update(0.12, 0.1))
        self.assertFalse(d.update(0.08, 0.15))
        self.assertTrue(d.update(0.02, 0.2))
        self.assertFalse(d.update(0.00, 0.21))

    def test_tap_is_direction_independent(self):
        d = DepthTapDetector(trigger=0.10, release=0.03, cooldown=0.0)
        d.update(0.20, 0.0)
        self.assertFalse(d.update(0.08, 0.1))
        self.assertTrue(d.update(0.19, 0.2))

    def test_hold_starts_and_stops(self):
        d = DepthHoldDetector(trigger=0.10, release=0.03)
        self.assertEqual(d.update(0.0), (False, False))
        self.assertEqual(d.update(0.12), (True, True))
        self.assertEqual(d.update(0.10), (True, False))
        self.assertEqual(d.update(0.02), (False, True))

    def test_four_finger_vertical_motion_scrolls(self):
        d = FourFingerScrollDetector(
            rest_threshold=0.05, start_delta=0.005, speed=300.0,
            release_timeout=0.2, coherence=0.004, settle_frames=2)
        depths = (0.0, 0.0, 0.0, 0.0)
        p0 = ((0.2, 0.5), (0.4, 0.5), (0.6, 0.5), (0.8, 0.5))
        self.assertEqual(d.update(p0, depths, 0.00), (False, 0))
        p1 = tuple((x, y - 0.002) for x, y in p0)
        self.assertEqual(d.update(p1, depths, 0.03), (False, 0))
        p2 = tuple((x, y - 0.012) for x, y in p1)
        active, steps = d.update(p2, depths, 0.06)
        self.assertTrue(active)
        self.assertGreater(steps, 0)

    def test_four_finger_horizontal_motion_does_not_scroll(self):
        d = FourFingerScrollDetector(
            rest_threshold=0.05, start_delta=0.005, speed=300.0,
            coherence=0.004, settle_frames=2)
        depths = (0.0, 0.0, 0.0, 0.0)
        p0 = ((0.2, 0.5), (0.4, 0.5), (0.6, 0.5), (0.8, 0.5))
        d.update(p0, depths, 0.00)
        p1 = tuple((x + 0.002, y) for x, y in p0)
        d.update(p1, depths, 0.03)
        p2 = tuple((x + 0.015, y) for x, y in p1)
        self.assertEqual(d.update(p2, depths, 0.06), (False, 0))

    def test_single_finger_motion_does_not_scroll(self):
        d = FourFingerScrollDetector(
            rest_threshold=0.05, start_delta=0.005, speed=300.0,
            coherence=0.004, settle_frames=2)
        depths = (0.0, 0.0, 0.0, 0.0)
        p0 = ((0.2, 0.5), (0.4, 0.5), (0.6, 0.5), (0.8, 0.5))
        d.update(p0, depths, 0.00)
        d.update(p0, depths, 0.03)
        p1 = ((0.2, 0.48), p0[1], p0[2], p0[3])
        self.assertEqual(d.update(p1, depths, 0.06), (False, 0))

    def test_lifted_finger_blocks_scroll(self):
        d = FourFingerScrollDetector(
            rest_threshold=0.05, start_delta=0.005, speed=300.0,
            coherence=0.004, settle_frames=2)
        p0 = ((0.2, 0.5), (0.4, 0.5), (0.6, 0.5), (0.8, 0.5))
        d.update(p0, (0.0, 0.0, 0.0, 0.0), 0.00)
        d.update(p0, (0.0, 0.0, 0.0, 0.0), 0.03)
        p1 = tuple((x, y - 0.02) for x, y in p0)
        self.assertEqual(
            d.update(p1, (0.0, 0.0, 0.12, 0.0), 0.06), (False, 0))


if __name__ == "__main__":
    unittest.main()
