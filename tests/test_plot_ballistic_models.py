import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from matplotlib.axes import Axes

from scripts import plot_ballistic_models
from worcalc.domain.ballistics import (
    LinearDragTrajectoryModel,
    LinearModel,
    PchipModel,
    PolynomialModel,
    boresight_angle_offset,
    load_reference_points,
)
from worcalc.domain.projectile import (
    ARTILLERY_GRAVITY_METRES_PER_SECOND_SQUARED,
    ARTILLERY_MUZZLE_HEIGHT_METRES,
    ARTILLERY_PHYSICS,
)


CSV_PATH = Path(__file__).resolve().parent.parent / "war_of_rights_ballistic_ranges.csv"


class PlotBallisticModelsTests(unittest.TestCase):
    def test_every_displayed_model_curve_reaches_zero_yards(self) -> None:
        points = load_reference_points(CSV_PATH)
        minimum = points[0].elevation_deg
        maximum = points[-1].elevation_deg
        speed, drag = ARTILLERY_PHYSICS["3-inch Ordnance"]["Shell"]
        gravity = ARTILLERY_GRAVITY_METRES_PER_SECOND_SQUARED
        offset = boresight_angle_offset(
            speed,
            drag,
            gravity,
            ARTILLERY_MUZZLE_HEIGHT_METRES,
            points[0].elevation_deg,
            points[0].range_yards,
        )
        models = [
            LinearModel(points),
            PchipModel(points),
            PolynomialModel(points, 2),
            PolynomialModel(points, 3),
            LinearDragTrajectoryModel(
                speed,
                drag,
                gravity_metres_per_second_squared=gravity,
                angle_offset_deg=offset,
                muzzle_height_metres=ARTILLERY_MUZZLE_HEIGHT_METRES,
            ),
        ]

        for model in models:
            with self.subTest(model=model.name):
                elevations, ranges = plot_ballistic_models.curve_samples_to_zero(
                    model,
                    minimum,
                    maximum,
                    800,
                )

                self.assertLess(elevations[0], minimum)
                self.assertAlmostEqual(ranges[0], 0.0, places=6)
                self.assertGreater(ranges[-1], 0.0)

    def test_range_axis_starts_at_zero_yards(self) -> None:
        original_set_ylim = Axes.set_ylim
        lower_bounds: list[float | None] = []

        def record_set_ylim(axis, *args, **kwargs):
            lower_bounds.append(kwargs.get("bottom"))
            return original_set_ylim(axis, *args, **kwargs)

        with (
            patch.object(sys, "argv", ["plot_ballistic_models.py", "--no-show"]),
            patch.object(Axes, "set_ylim", record_set_ylim),
        ):
            self.assertEqual(plot_ballistic_models.main(), 0)

        self.assertIn(0, lower_bounds)


if __name__ == "__main__":
    unittest.main()
