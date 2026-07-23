import unittest

from worcalc.domain.calibration import Point
from worcalc.maps.elevation import ElevationField, ElevationSample


class ElevationFieldTests(unittest.TestCase):
    def test_exact_anchor_uses_its_elevation(self):
        field = ElevationField(
            (
                ElevationSample(10, 20, 42.5, "anchor"),
                ElevationSample(100, 100, 90, "other"),
            )
        )
        self.assertEqual(field.elevation_at(Point(10, 20)), 42.5)

    def test_interpolation_stays_inside_local_range(self):
        field = ElevationField(
            (
                ElevationSample(0, 0, 10, "low"),
                ElevationSample(10, 0, 30, "high"),
            )
        )
        value = field.elevation_at(Point(5, 0), neighbours=2)
        self.assertAlmostEqual(value, 20)

    def test_empty_field_has_no_estimate(self):
        self.assertIsNone(ElevationField(()).elevation_at(Point(0, 0)))

    def test_contrast_range_clips_sparse_outliers(self):
        field = ElevationField(
            tuple(
                ElevationSample(index, 0, elevation, str(index))
                for index, elevation in enumerate(
                    [0, 10, 10, 11, 12, 13, 14, 15, 16, 17, 18, 100]
                )
            )
        )
        lower, upper = field.contrast_range_metres()
        self.assertGreater(lower, 0)
        self.assertLess(upper, 100)


if __name__ == "__main__":
    unittest.main()
