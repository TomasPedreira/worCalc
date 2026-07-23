import unittest

from worcalc.ui.bearing_compass import compass_direction, map_bearing_degrees


class BearingCompassTests(unittest.TestCase):
    def test_cardinal_and_intercardinal_labels(self):
        self.assertEqual(compass_direction(0), "N")
        self.assertEqual(compass_direction(45), "NE")
        self.assertEqual(compass_direction(90), "E")
        self.assertEqual(compass_direction(225), "SW")

    def test_bearing_wraps_around_north(self):
        self.assertEqual(compass_direction(359), "N")
        self.assertEqual(compass_direction(360), "N")

    def test_north_up_map_axes(self):
        self.assertEqual(map_bearing_degrees(0, -100), 0)
        self.assertEqual(map_bearing_degrees(100, 0), 90)
        self.assertEqual(map_bearing_degrees(0, 100), 180)
        self.assertEqual(map_bearing_degrees(-100, 0), 270)


if __name__ == "__main__":
    unittest.main()
