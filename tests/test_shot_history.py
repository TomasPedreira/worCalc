import unittest

from worcalc.domain.calibration import AffineCalibration, METRES_TO_YARDS, Point
from worcalc.domain.shot_history import (
    ObservedShot,
    correction_summary,
    observed_impact_point,
)


class ShotHistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        metres_per_pixel = 1 / METRES_TO_YARDS
        self.calibration = AffineCalibration(
            metres_per_pixel,
            0,
            0,
            metres_per_pixel,
        )

    def test_places_over_and_right_relative_to_horizontal_route(self) -> None:
        impact = observed_impact_point(
            self.calibration,
            Point(10, 20),
            Point(110, 20),
            ObservedShot(25, 10),
        )

        self.assertAlmostEqual(impact.x, 135)
        self.assertAlmostEqual(impact.y, 30)

    def test_right_is_screen_right_for_upward_route(self) -> None:
        impact = observed_impact_point(
            self.calibration,
            Point(100, 100),
            Point(100, 50),
            ObservedShot(-20, 15),
        )

        self.assertAlmostEqual(impact.x, 115)
        self.assertAlmostEqual(impact.y, 70)

    def test_rejects_coincident_gun_and_target(self) -> None:
        with self.assertRaises(ValueError):
            observed_impact_point(
                self.calibration,
                Point(10, 10),
                Point(10, 10),
                ObservedShot(5, 0),
            )

    def test_formats_field_correction(self) -> None:
        self.assertEqual(
            correction_summary(ObservedShot(-75, 20)),
            "75 short, 20 right",
        )


if __name__ == "__main__":
    unittest.main()
