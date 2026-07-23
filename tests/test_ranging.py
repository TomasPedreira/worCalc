import unittest

from worcalc.domain.ranging import RangeMeasurement


class RangeMeasurementTests(unittest.TestCase):
    def test_horizontal_debug_mode_ignores_elevation(self):
        measurement = RangeMeasurement(100.0, 20.0)
        self.assertEqual(measurement.distance_yards(include_elevation=False), 100.0)

    def test_terrain_mode_uses_three_dimensional_distance(self):
        measurement = RangeMeasurement(100.0, 20.0)
        self.assertGreater(measurement.distance_yards(include_elevation=True), 100.0)

    def test_missing_elevation_safely_falls_back_to_horizontal(self):
        measurement = RangeMeasurement(100.0)
        self.assertEqual(measurement.distance_yards(include_elevation=True), 100.0)


if __name__ == "__main__":
    unittest.main()
