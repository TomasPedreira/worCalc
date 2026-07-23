import unittest

from worcalc.domain.projectile import artillery_time_of_flight, three_inch_time_of_flight


class ProjectileTests(unittest.TestCase):
    def test_three_inch_tof_includes_drag(self):
        self.assertAlmostEqual(three_inch_time_of_flight(321), 0.8265, places=4)

    def test_tof_increases_with_elevation(self):
        self.assertGreater(
            three_inch_time_of_flight(300, 10),
            three_inch_time_of_flight(300, 0),
        )

    def test_case_arrives_before_shell(self):
        self.assertLess(
            three_inch_time_of_flight(300, projectile_type="Case"),
            three_inch_time_of_flight(300, projectile_type="Shell"),
        )

    def test_unknown_projectile_is_rejected(self):
        with self.assertRaises(ValueError):
            three_inch_time_of_flight(300, projectile_type="Canister")

    def test_napoleon_uses_its_installed_shell_physics(self):
        self.assertAlmostEqual(
            artillery_time_of_flight(300, "12-pounder Napoleon", "Shell"),
            0.6946,
            places=4,
        )

    def test_napoleon_shell_and_case_share_speed(self):
        self.assertEqual(
            artillery_time_of_flight(300, "12-pounder Napoleon", "Shell"),
            artillery_time_of_flight(300, "12-pounder Napoleon", "Case"),
        )

    def test_parrott_uses_shared_rifled_artillery_profile(self):
        for projectile_type in ("Shell", "Case"):
            self.assertEqual(
                artillery_time_of_flight(
                    340, "10-pounder Parrott", projectile_type
                ),
                artillery_time_of_flight(
                    340, "3-inch Ordnance", projectile_type
                ),
            )

    def test_invalid_distance_is_rejected(self):
        with self.assertRaises(ValueError):
            three_inch_time_of_flight(-1)


if __name__ == "__main__":
    unittest.main()
