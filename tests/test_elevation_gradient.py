import unittest

from worcalc.maps.elevation import ElevationField, ElevationSample
from worcalc.ui.map_view import (
    elevation_gradient_anchors,
    elevation_gradient_position,
)


class ElevationGradientTests(unittest.TestCase):
    def test_median_is_gradient_midpoint_despite_extreme_maximum(self):
        self.assertEqual(elevation_gradient_position(20, 0, 20, 1_000), 0.5)

    def test_each_side_of_median_uses_half_the_gradient(self):
        self.assertEqual(elevation_gradient_position(10, 0, 20, 1_000), 0.25)
        self.assertEqual(elevation_gradient_position(510, 0, 20, 1_000), 0.75)

    def test_values_outside_sampled_range_are_clamped(self):
        self.assertEqual(elevation_gradient_position(-10, 0, 20, 1_000), 0.0)
        self.assertEqual(elevation_gradient_position(1_100, 0, 20, 1_000), 1.0)

    def test_sparse_extreme_hill_does_not_set_red_anchor(self):
        field = ElevationField(
            tuple(
                ElevationSample(index, 0, elevation, str(index))
                for index, elevation in enumerate((*range(11), 1_000))
            )
        )

        minimum, midpoint, maximum = elevation_gradient_anchors(field)

        self.assertAlmostEqual(minimum, 1.1)
        self.assertEqual(midpoint, 5.5)
        self.assertAlmostEqual(maximum, 9.9)
        self.assertEqual(
            elevation_gradient_position(1_000, minimum, midpoint, maximum),
            1.0,
        )


if __name__ == "__main__":
    unittest.main()
