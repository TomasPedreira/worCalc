import unittest

from worcalc.domain.projectile import ARTILLERY_MUZZLE_HEIGHT_METRES
from worcalc.domain.trajectory import (
    TerrainProfilePoint,
    analyze_trajectory_clearance,
    shell_height_at_distance,
)


def flat_profile(length_yards: int, spacing_yards: int = 10):
    return tuple(
        TerrainProfilePoint(distance, 0.0)
        for distance in range(0, length_yards + 1, spacing_yards)
    )


class TrajectoryTests(unittest.TestCase):
    def test_shell_starts_at_muzzle_height(self):
        self.assertAlmostEqual(
            shell_height_at_distance(
                0,
                5,
                370,
                0.1,
                9.1,
                ARTILLERY_MUZZLE_HEIGHT_METRES,
            ),
            1.4,
        )

    def test_clearance_uses_artillery_muzzle_height_by_default(self):
        result = analyze_trajectory_clearance(
            flat_profile(100),
            target_range_yards=100,
            original_elevation_deg=3,
            speed_metres_per_second=370,
            drag_per_second=0.1,
        )

        self.assertAlmostEqual(
            result.original_trajectory[0].shell_elevation_metres,
            1.4,
        )

    def test_flat_route_is_clear_and_impacts_at_calibrated_target(self):
        result = analyze_trajectory_clearance(
            flat_profile(2000),
            target_range_yards=1000,
            original_elevation_deg=3,
            speed_metres_per_second=370,
            drag_per_second=0.1,
        )
        self.assertFalse(result.obstructed)
        self.assertAlmostEqual(result.clearing_elevation_deg, 3)
        self.assertAlmostEqual(result.impact_range_yards, 1000, delta=10)
        self.assertAlmostEqual(result.overshoot_yards, 0, delta=10)
        self.assertAlmostEqual(result.height_above_target_metres, 0, places=6)

    def test_gentle_uphill_does_not_treat_muzzle_clearance_as_obstruction(self):
        profile = tuple(
            TerrainProfilePoint(distance, distance / 100)
            for distance in range(0, 2001, 10)
        )

        result = analyze_trajectory_clearance(
            profile,
            target_range_yards=1000,
            original_elevation_deg=0,
            speed_metres_per_second=370,
            drag_per_second=0.1,
        )

        self.assertFalse(result.obstructed)
        self.assertEqual(result.clearing_elevation_deg, 0)

    def test_hill_requires_more_elevation_and_reports_overshoot(self):
        profile = list(flat_profile(3000))
        for index, point in enumerate(profile):
            distance_from_hill = abs(point.distance_yards - 500)
            if distance_from_hill <= 100:
                profile[index] = TerrainProfilePoint(
                    point.distance_yards,
                    45 * (1 - distance_from_hill / 100),
                )
        result = analyze_trajectory_clearance(
            tuple(profile),
            target_range_yards=1000,
            original_elevation_deg=3,
            speed_metres_per_second=370,
            drag_per_second=0.1,
        )
        self.assertTrue(result.obstructed)
        self.assertIsNotNone(result.first_obstruction_yards)
        self.assertIsNotNone(result.clearing_elevation_deg)
        self.assertIsNotNone(result.impact_range_yards)
        self.assertIsNotNone(result.overshoot_yards)
        self.assertIsNotNone(result.height_above_target_metres)
        assert result.clearing_elevation_deg is not None
        assert result.overshoot_yards is not None
        assert result.height_above_target_metres is not None
        self.assertGreater(result.clearing_elevation_deg, 3)
        self.assertGreater(result.overshoot_yards, 0)
        self.assertGreater(result.height_above_target_metres, 0)

    def test_profile_must_reach_target(self):
        with self.assertRaises(ValueError):
            analyze_trajectory_clearance(
                flat_profile(500),
                target_range_yards=1000,
                original_elevation_deg=3,
                speed_metres_per_second=370,
                drag_per_second=0.1,
            )


if __name__ == "__main__":
    unittest.main()
