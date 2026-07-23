import tempfile
import unittest
from pathlib import Path

from worcalc.domain.calibration import (
    METRES_TO_YARDS,
    AffineCalibration,
    Calibration,
    Point,
    read_resolution,
    write_calibration,
)


class CalibrationTests(unittest.TestCase):
    def test_scale_uses_euclidean_pixel_distance(self):
        calibration = Calibration(Point(0, 0), Point(3, 4), 10)
        self.assertEqual(calibration.pixel_distance, 5)
        self.assertEqual(calibration.yards_per_pixel, 2)

    def test_same_point_is_invalid(self):
        with self.assertRaises(ValueError):
            _ = Calibration(Point(2, 2), Point(2, 2), 10).yards_per_pixel

    def test_config_round_trip(self):
        calibration = Calibration(Point(1, 2), Point(4, 6), 10)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "res.config"
            write_calibration(path, calibration, 1920, 1080)
            self.assertEqual(read_resolution(path), 2)
            text = path.read_text(encoding="utf-8")
            self.assertIn("image_width=1920", text)
            self.assertIn("image_height=1080", text)
            self.assertIn("unit=yard", text)

    def test_affine_distance_uses_both_world_axes(self):
        transform = AffineCalibration(0.4, -0.5, -0.5, -0.4)
        world = transform.world_delta_metres(30, 40)
        expected = (world.x**2 + world.y**2) ** 0.5 * METRES_TO_YARDS
        self.assertAlmostEqual(transform.distance_yards(Point(10, 20), Point(40, 60)), expected)

    def test_affine_world_to_pixel_round_trip(self):
        transform = AffineCalibration(0.4, -0.5, -0.5, -0.4)
        pixel = transform.pixel_delta_for_world_metres(125, -75)
        world = transform.world_delta(pixel.x, pixel.y)
        self.assertAlmostEqual(world.x, 125)
        self.assertAlmostEqual(world.y, -75)


if __name__ == "__main__":
    unittest.main()
