import unittest
from pathlib import Path

from worcalc.domain.ballistic_solution import BallisticSolutionEngine
from worcalc.domain.ballistics import LinearDragTrajectoryModel
from worcalc.domain.projectile import ARTILLERY_MUZZLE_HEIGHT_METRES


CSV_PATH = Path(__file__).resolve().parent.parent / "war_of_rights_ballistic_ranges.csv"


class BallisticSolutionEngineTests(unittest.TestCase):
    def test_weapon_uses_its_configured_launch_calibration(self) -> None:
        engine = BallisticSolutionEngine(CSV_PATH)
        engine.set_weapon("3-inch Ordnance", "Shell")
        self.assertEqual(engine.physics.launch.angle_offset_deg, 0.48)
        engine.set_weapon("10-pounder Parrott", "Shell")
        self.assertEqual(engine.physics.launch.angle_offset_deg, 0.48)

    def setUp(self) -> None:
        self.solver = BallisticSolutionEngine(CSV_PATH)

    def test_theoretical_physics_is_an_estimation_curve_option(self) -> None:
        self.assertIn("Theoretical physics", self.solver.method_names)

        index = self.solver.method_names.index("Theoretical physics")
        self.solver.set_method(index)
        angle = self.solver.solve(2500, 0)

        self.assertIsNotNone(angle)
        assert angle is not None
        model = self.solver.models[index]
        self.assertIsInstance(model, LinearDragTrajectoryModel)
        assert isinstance(model, LinearDragTrajectoryModel)
        self.assertEqual(model.muzzle_height, ARTILLERY_MUZZLE_HEIGHT_METRES)
        self.assertAlmostEqual(model.evaluate(angle), 2500, places=6)

    def test_theoretical_curve_uses_the_active_physics_profile(self) -> None:
        index = self.solver.method_names.index("Theoretical physics")
        self.solver.set_method(index)
        original_angle = self.solver.solve(2500, 0)

        self.solver.set_physics_profile(439, 0.31)

        model = self.solver.models[index]
        self.assertIsInstance(model, LinearDragTrajectoryModel)
        assert isinstance(model, LinearDragTrajectoryModel)
        self.assertEqual(model.speed, 439)
        self.assertEqual(model.drag, 0.31)
        self.assertNotEqual(self.solver.solve(2500, 0), original_angle)


if __name__ == "__main__":
    unittest.main()
