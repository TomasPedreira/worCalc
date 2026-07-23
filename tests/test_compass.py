import unittest

from worcalc.ui.map_view import compass_direction_angles, compass_tick_angles


class CompassTests(unittest.TestCase):
    def test_has_five_minor_ticks_between_cardinals(self):
        angles = compass_tick_angles(5)
        self.assertEqual(len(angles), 24)
        self.assertEqual(angles[0], -90)
        self.assertEqual(angles[3], -45)
        self.assertEqual(angles[6], 0)
        self.assertEqual(angles[12], 90)
        self.assertEqual(angles[18], 180)

    def test_intercardinal_directions_are_exact_diagonals(self):
        directions = compass_direction_angles()
        self.assertEqual(directions["NE"], -45)
        self.assertEqual(directions["SE"], 45)
        self.assertEqual(directions["SW"], 135)
        self.assertEqual(directions["NW"], 225)


if __name__ == "__main__":
    unittest.main()
