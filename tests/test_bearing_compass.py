import unittest

from worcalc.ui.bearing_compass import (
    COMPASS_DIAL_LABELS,
    compass_direction,
    map_bearing_degrees,
)


class BearingCompassTests(unittest.TestCase):
    def test_dial_labels_all_cardinal_and_intercardinal_directions(self):
        self.assertEqual(
            COMPASS_DIAL_LABELS,
            (
                (0, "N"),
                (45, "NE"),
                (90, "E"),
                (135, "SE"),
                (180, "S"),
                (225, "SW"),
                (270, "W"),
                (315, "NW"),
            ),
        )

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
