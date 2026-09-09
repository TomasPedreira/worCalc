import unittest

from worcalc.domain.empirical_calibration import ImpactSample, estimate_elevation


class EmpiricalCalibrationTests(unittest.TestCase):
    def test_uses_far_impact_branch_and_recommends_higher_setting(self):
        samples = [
            ImpactSample(-0.15, 172.2),
            ImpactSample(-0.15, 170.2),
            ImpactSample(-0.14, 178.0),
            ImpactSample(-0.14, 332.84),
            ImpactSample(-0.14, 331.88),
            ImpactSample(-0.13, 334.89),
            ImpactSample(-0.10, 340.80),
        ]

        aim = estimate_elevation(samples, 370.33)

        self.assertIsNotNone(aim)
        self.assertAlmostEqual(aim.elevation_degrees, 0.042, places=3)
        self.assertEqual(aim.distinct_settings, 3)
        self.assertEqual(aim.sample_count, 4)

    def test_requires_three_distinct_settings(self):
        samples = [ImpactSample(-0.14, 332), ImpactSample(-0.10, 341)]

        self.assertIsNone(estimate_elevation(samples, 370))

    def test_rejects_flat_or_reversed_relationship(self):
        samples = [
            ImpactSample(-0.14, 340),
            ImpactSample(-0.12, 336),
            ImpactSample(-0.10, 332),
        ]

        self.assertIsNone(estimate_elevation(samples, 370))

    def test_advances_one_click_when_a_nearby_ridge_stops_the_latest_shot(self):
        samples = [
            ImpactSample(-0.14, 332.36),
            ImpactSample(-0.13, 334.89),
            ImpactSample(-0.10, 340.80),
            ImpactSample(0.06, 354.59),
        ]

        aim = estimate_elevation(samples, 373.24)

        self.assertIsNotNone(aim)
        self.assertAlmostEqual(aim.elevation_degrees, 0.07)

    def test_steps_through_unobserved_settings_between_short_and_long_impacts(self):
        samples = [
            ImpactSample(-0.14, 332.36),
            ImpactSample(-0.13, 334.89),
            ImpactSample(-0.10, 340.80),
            ImpactSample(0.06, 354.59),
            ImpactSample(0.24, 477.34),
        ]

        aim = estimate_elevation(samples, 374.82)

        self.assertIsNotNone(aim)
        self.assertAlmostEqual(aim.elevation_degrees, 0.07)

    def test_uses_next_unobserved_click_after_a_round_clears_the_ridge(self):
        samples = [
            ImpactSample(-0.14, 332.36),
            ImpactSample(-0.13, 334.89),
            ImpactSample(-0.10, 340.80),
            ImpactSample(0.06, 354.59),
            ImpactSample(0.09, 432.09),
            ImpactSample(0.24, 477.34),
        ]

        aim = estimate_elevation(samples, 374.82)

        self.assertIsNotNone(aim)
        self.assertAlmostEqual(aim.elevation_degrees, 0.07)
