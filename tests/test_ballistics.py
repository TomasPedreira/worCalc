import unittest
from pathlib import Path

from worcalc.domain.ballistics import (
    LinearDragTrajectoryModel,
    LinearModel,
    PchipModel,
    PolynomialModel,
    boresight_angle_offset,
    elevation_for_range,
    height_adjusted_elevation,
    load_reference_points,
    rmse,
)


CSV_PATH = Path(__file__).resolve().parent.parent / "war_of_rights_ballistic_ranges.csv"


class BallisticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.points = load_reference_points(CSV_PATH)

    def test_loads_official_reference_range(self):
        self.assertEqual(len(self.points), 17)
        self.assertEqual(self.points[0].range_yards, 380)
        self.assertEqual(self.points[-1].range_yards, 4180)

    def test_linear_inverse_example(self):
        model = LinearModel(self.points)
        angle = elevation_for_range(model, 3500, 0, 16)
        self.assertAlmostEqual(angle, 13.3, places=6)

    def test_inverse_extrapolates_beyond_reference_range(self):
        model = PolynomialModel(self.points, 3)
        angle = elevation_for_range(model, 5000, 0, 16)
        self.assertIsNotNone(angle)
        assert angle is not None
        self.assertGreater(angle, 16)
        self.assertAlmostEqual(model.evaluate(angle), 5000, places=6)

    def test_height_adjustment_has_the_correct_sign(self):
        level_solution = 2.0
        uphill = height_adjusted_elevation(level_solution, 100, 10)
        downhill = height_adjusted_elevation(level_solution, 100, -10)
        self.assertGreater(uphill, level_solution)
        self.assertLess(downhill, level_solution)

    def test_pchip_preserves_every_reference(self):
        model = PchipModel(self.points)
        for point in self.points:
            self.assertAlmostEqual(model.evaluate(point.elevation_deg), point.range_yards)

    def test_pchip_remains_monotonic(self):
        model = PchipModel(self.points)
        values = [model.evaluate(index / 20) for index in range(321)]
        self.assertTrue(all(a <= b for a, b in zip(values, values[1:])))

    def test_polynomial_fit_errors_match_diagnostics(self):
        self.assertAlmostEqual(rmse(PolynomialModel(self.points, 2), self.points), 66.77, places=2)
        self.assertAlmostEqual(rmse(PolynomialModel(self.points, 3), self.points), 50.01, places=2)

    def test_theoretical_model_uses_linear_drag(self):
        model = LinearDragTrajectoryModel(370, 0.1)
        self.assertAlmostEqual(model.evaluate(8), 2398.65, places=2)
        self.assertEqual(model.evaluate(0), 0)

    def test_theoretical_model_without_drag_matches_vacuum_range(self):
        model = LinearDragTrajectoryModel(100, 0)
        self.assertAlmostEqual(model.evaluate(45), 1114.79, places=2)

    def test_elevated_muzzle_has_nonzero_range_at_zero_degrees(self):
        model = LinearDragTrajectoryModel(370, 0.1, 9.1, muzzle_height_metres=0.762)
        self.assertGreater(model.evaluate(0), 0)

    def test_boresight_offset_hits_reference_range(self):
        offset = boresight_angle_offset(370, 0.1, 9.1, 0.762, 0, 380)
        model = LinearDragTrajectoryModel(
            370,
            0.1,
            9.1,
            angle_offset_deg=offset,
            muzzle_height_metres=0.762,
        )
        self.assertAlmostEqual(model.evaluate(0), 380, places=6)


if __name__ == "__main__":
    unittest.main()
