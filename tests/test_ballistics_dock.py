import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication, QGraphicsItem

from worcalc.app import MainWindow, discover_maps
from worcalc.domain.calibration import METRES_TO_YARDS


class FireMissionUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.root = Path(__file__).resolve().parents[1]

    def setUp(self) -> None:
        self.maps_dir = self.root / "paks" / "converted_minimaps"
        self.window = MainWindow(self.maps_dir)
        self.window.show()
        self.app.processEvents()

    def tearDown(self) -> None:
        self.window.close()
        self.app.processEvents()

    def test_measurement_updates_inline_solution_without_analysis_dock(self) -> None:
        self.assertFalse(hasattr(self.window, "ballistics_dock"))
        self.assertFalse(hasattr(self.window, "ballistic_estimate"))
        record = discover_maps(self.maps_dir)[0]
        self.window._select_map(record)
        delta = record.calibration.pixel_delta_for_world_units(2500 / METRES_TO_YARDS, 0)
        self.window.points = [
            QPointF(100, 100),
            QPointF(100 + delta.x, 100 + delta.y),
        ]
        self.window.view.set_points(self.window.points)
        self.window._refresh_measurement()
        self.app.processEvents()

        self.assertIn("yd", self.window.solution_range.text())
        self.assertIn("H ", self.window.solution_range.text())
        self.assertIn("S ", self.window.solution_range.text())
        self.assertIn("°", self.window.solution_elevation.text())
        self.assertTrue(self.window.solution_tof.text().endswith(" s"))
        self.assertIsNotNone(self.window.solution_bearing.bearing)
        self.assertFalse(self.window.elevation_overlay.isChecked())
        overlay = self.window.view._target_solution_label
        self.assertIsNotNone(overlay)
        assert overlay is not None
        self.assertIn("SLANT", overlay.text())
        self.assertIn("FUZE", overlay.text())
        self.assertIn("ELEV", overlay.text())
        clearance = self.window.current_clearance_result
        self.assertIsNotNone(clearance)
        assert clearance is not None
        self.assertIs(self.window.trajectory_profile.result, clearance)
        self.assertIn("ESTIMATED", self.window.clearance_status.text())
        self.assertTrue(self.window.clearance_details.isVisible())
        self.assertIn("Height above target", self.window.clearance_details.text())
        solution_before_gradient = (
            self.window.solution_range.text(),
            self.window.solution_tof.text(),
            self.window.solution_elevation.text(),
        )
        self.window.elevation_overlay.setChecked(True)
        self.assertEqual(
            (
                self.window.solution_range.text(),
                self.window.solution_tof.text(),
                self.window.solution_elevation.text(),
            ),
            solution_before_gradient,
        )

    def test_outside_official_range_is_extrapolated(self) -> None:
        solver = self.window.ballistic_solver
        self.assertIsNotNone(solver)
        assert solver is not None
        self.assertIsNotNone(solver.solve(100, 0))

    def test_uphill_target_adds_positive_sight_angle(self) -> None:
        solver = self.window.ballistic_solver
        self.assertIsNotNone(solver)
        assert solver is not None
        level = solver.solve(100, 0)
        uphill = solver.solve(100, 10)
        self.assertIsNotNone(level)
        self.assertIsNotNone(uphill)
        assert level is not None and uphill is not None
        self.assertGreater(uphill, level)

    def test_inline_method_selector_defaults_to_cubic_and_updates_solver(self) -> None:
        solver = self.window.ballistic_solver
        self.assertIsNotNone(solver)
        assert solver is not None
        self.assertEqual(self.window.ballistic_method.currentText(), "Polynomial degree 3")
        self.assertEqual(solver.method_name, "Polynomial degree 3")

        self.window._select_map(discover_maps(self.maps_dir)[0])
        record = self.window.current_map
        assert record is not None
        delta = record.calibration.pixel_delta_for_world_units(
            2500 / METRES_TO_YARDS, 0
        )
        self.window.points = [
            QPointF(100, 100),
            QPointF(100 + delta.x, 100 + delta.y),
        ]
        self.window._refresh_measurement()
        cubic_result = self.window.solution_elevation.text()

        self.window.ballistic_method.setCurrentIndex(0)
        self.app.processEvents()

        self.assertEqual(solver.method_name, "Linear interpolation")
        self.assertNotEqual(self.window.solution_elevation.text(), cubic_result)

    def test_later_clicks_relocate_only_the_target(self) -> None:
        self.window._select_map(discover_maps(self.maps_dir)[0])
        cannon = QPointF(100, 120)
        first_target = QPointF(300, 320)
        relocated_target = QPointF(500, 520)

        self.window._add_measurement_point(cannon)
        self.window._add_measurement_point(first_target)
        first_overlay_position = self.window.view._target_solution_label.pos()
        self.window._add_measurement_point(relocated_target)

        self.assertEqual(self.window.points[0], cannon)
        self.assertEqual(self.window.points[1], relocated_target)
        movable = QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        self.assertTrue(self.window.view._markers[0].flags() & movable)
        self.assertTrue(self.window.view._markers[1].flags() & movable)
        self.assertTrue(
            self.window.view._markers[0].acceptedMouseButtons()
        )
        self.assertNotEqual(
            self.window.view._target_solution_label.pos(),
            first_overlay_position,
        )

    def test_hover_readout_reports_pixel_world_and_elevation(self) -> None:
        self.window._select_map(discover_maps(self.maps_dir)[0])
        self.window._map_position_hovered(QPointF(100, 200))
        text = self.window.cursor_readout.text()
        self.assertIn("PIXEL 100.0, 200.0", text)
        self.assertIn("WORLD X", text)
        self.assertIn("Y", text)
        self.assertIn("ELEV", text)

    def test_straight_right_is_east_bearing(self) -> None:
        self.window._select_map(discover_maps(self.maps_dir)[0])
        self.window._add_measurement_point(QPointF(200, 300))
        self.window._add_measurement_point(QPointF(500, 300))
        self.assertAlmostEqual(self.window.solution_bearing.bearing, 90.0)

    def test_trajectory_overlay_marks_obstruction_and_impact(self) -> None:
        self.window._select_map(discover_maps(self.maps_dir)[0])
        self.window.view.set_points([QPointF(100, 100), QPointF(500, 100)])
        self.window.view.set_trajectory_overlay(1000, 500, 1250)
        self.assertEqual(len(self.window.view._trajectory_items), 4)
        self.window.view.clear_trajectory_overlay()
        self.assertEqual(self.window.view._trajectory_items, [])

    def test_control_column_scrolls_in_short_window(self) -> None:
        self.window.resize(1100, 560)
        self.app.processEvents()
        self.assertGreater(
            self.window.control_scroll.verticalScrollBar().maximum(),
            0,
        )


if __name__ == "__main__":
    unittest.main()
