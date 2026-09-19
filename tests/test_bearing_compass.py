import unittest

from worcalc.ui.bearing_compass import (
    COMPASS_DIAL_LABELS,
    compass_direction,
    game_compass_aim,
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

    def test_game_compass_uses_two_ticks_between_named_directions(self):
        first = game_compass_aim(14.0)
        second = game_compass_aim(31.0)

        self.assertEqual((first.mark_degrees, first.instruction), (15.0, "N +1 TICK"))
        self.assertEqual((second.mark_degrees, second.instruction), (30.0, "N +2 TICKS"))

    def test_game_compass_named_direction_needs_no_tick_instruction(self):
        aim = game_compass_aim(44.0)

        self.assertEqual(aim.mark_degrees, 45.0)
        self.assertEqual(aim.instruction, "NE")
        self.assertEqual(aim.error_degrees, -1.0)

    def test_game_compass_wraps_to_north(self):
        aim = game_compass_aim(359.0)

        self.assertEqual(aim.mark_degrees, 0.0)
        self.assertEqual(aim.instruction, "N")
        self.assertEqual(aim.error_degrees, -1.0)

    def test_game_compass_half_step_resolves_clockwise(self):
        self.assertEqual(game_compass_aim(7.5).mark_degrees, 15.0)


if __name__ == "__main__":
    unittest.main()
