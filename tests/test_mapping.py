import unittest

from mapping import camera_point_to_screen, transform_normalized, validate_area


class MappingTests(unittest.TestCase):
    def assertPointAlmostEqual(self, actual, expected):
        self.assertAlmostEqual(actual[0], expected[0], places=7)
        self.assertAlmostEqual(actual[1], expected[1], places=7)

    def test_rotations(self):
        p = (0.2, 0.3)
        self.assertPointAlmostEqual(transform_normalized(*p, 0), (0.2, 0.3))
        self.assertPointAlmostEqual(transform_normalized(*p, 90), (0.7, 0.2))
        self.assertPointAlmostEqual(transform_normalized(*p, 180), (0.8, 0.7))
        self.assertPointAlmostEqual(transform_normalized(*p, 270), (0.3, 0.8))

    def test_active_area_maps_to_screen(self):
        area = (0.1, 0.2, 0.9, 0.8)
        self.assertPointAlmostEqual(
            camera_point_to_screen(10, 20, 100, 100, area), (0.0, 0.0))
        self.assertPointAlmostEqual(
            camera_point_to_screen(90, 80, 100, 100, area), (1.0, 1.0))
        self.assertPointAlmostEqual(
            camera_point_to_screen(50, 50, 100, 100, area), (0.5, 0.5))

    def test_invalid_area(self):
        with self.assertRaises(ValueError):
            validate_area((0.9, 0.1, 0.2, 0.8))


if __name__ == "__main__":
    unittest.main()
