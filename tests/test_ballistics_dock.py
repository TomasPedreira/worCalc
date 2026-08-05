import os
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QGraphicsItem, QLabel, QPushButton

from worcalc.app import MainWindow, discover_maps
from worcalc.domain.calibration import METRES_TO_YARDS, Point
from worcalc.domain.shot_history import ObservedShot
from worcalc.domain.trajectory import TrajectoryClearanceResult


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
        overlay_background = self.window.view._target_solution_background
        self.assertIsNotNone(overlay_background)
        assert overlay_background is not None
        self.assertEqual(overlay_background.brush().color().alpha(), 160)
        self.assertIn("SLANT", overlay.text())
        self.assertIn("FUZE", overlay.text())
        self.assertIn("ELEV", overlay.text())
        clearance = self.window.current_clearance_result
        self.assertIsNotNone(clearance)
        assert clearance is not None
        self.assertIs(self.window.trajectory_profile.result, clearance)
        self.assertIn("ESTIMATED", self.window.clearance_status.text())
        self.assertTrue(self.window.clearance_details.isVisible())
        self.assertIn(
            "Predicted height over target", self.window.clearance_details.text()
        )
        self.assertIn("yd (", self.window.clearance_details.text())
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

    def test_fuze_uses_slant_range_without_ballistic_elevation(self) -> None:
        record = discover_maps(self.maps_dir)[0]
        self.window._select_map(record)
        delta = record.calibration.pixel_delta_for_world_units(
            2500 / METRES_TO_YARDS, 0
        )
        self.window.points = [
            QPointF(100, 100),
            QPointF(100 + delta.x, 100 + delta.y),
        ]
        solver = self.window.ballistic_solver
        self.assertIsNotNone(solver)
        assert solver is not None

        with (
            patch(
                "worcalc.ui.main_window.artillery_time_of_flight",
                return_value=1.234,
            ) as time_of_flight,
            patch.object(solver, "solve", return_value=35.0),
            patch.object(self.window, "_analyze_route_clearance"),
        ):
            self.window._refresh_measurement()

        measurement = self.window.current_range_measurement
        self.assertIsNotNone(measurement)
        assert measurement is not None
        time_of_flight.assert_called_once_with(
            measurement.slant_yards,
            self.window.cannon_type.currentText(),
            self.window.projectile_type.currentText(),
        )
        self.assertEqual(self.window.solution_tof.text(), "1.234 s")
        self.assertEqual(self.window.solution_elevation.text(), "35.000°")

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
        self.assertEqual(
            self.window.ballistic_method.itemText(
                self.window.ballistic_method.count() - 1
            ),
            "Theoretical physics",
        )

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

    def test_each_click_after_gun_autosaves_a_new_target(self) -> None:
        self.window._select_map(discover_maps(self.maps_dir)[0])
        cannon = QPointF(100, 120)
        first_target = QPointF(300, 320)
        second_target = QPointF(500, 520)

        self.window._add_measurement_point(cannon)
        self.window._add_measurement_point(first_target)
        self.window._add_measurement_point(second_target)

        self.assertEqual(self.window.points[0], cannon)
        self.assertEqual(self.window.points[1], second_target)
        self.assertEqual(self.window.selected_target_id, 2)
        self.assertEqual(len(self.window._current_targets()), 2)
        self.assertEqual(
            self.window._current_targets()[0].target,
            Point(first_target.x(), first_target.y()),
        )
        self.assertEqual(
            self.window._current_targets()[1].target,
            Point(second_target.x(), second_target.y()),
        )
        movable = QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        self.assertTrue(self.window.view._markers[0].flags() & movable)
        self.assertTrue(self.window.view._markers[1].flags() & movable)
        self.assertIn(1, self.window.view._saved_target_markers)
        self.assertIn(2, self.window.view._saved_target_markers)

    def test_markers_are_labeled_yellow_gun_and_red_target(self) -> None:
        self.window._select_map(discover_maps(self.maps_dir)[0])
        self.window._add_measurement_point(QPointF(100, 120))
        self.window._add_measurement_point(QPointF(300, 320))

        gun, target = self.window.view._markers
        self.assertEqual((gun.label, gun.role), ("G", "gun"))
        self.assertEqual((target.label, target.role), ("T", "target"))
        self.assertEqual(gun.brush().color(), QColor("#f2c94c"))
        self.assertEqual(target.brush().color(), QColor("#9f2f38"))
        self.assertEqual(target.label_color, QColor("#fff0e5"))

    def test_saves_numbered_target_and_records_spotted_impact(self) -> None:
        self.window._select_map(discover_maps(self.maps_dir)[0])
        self.window._add_measurement_point(QPointF(100, 120))
        self.window._add_measurement_point(QPointF(300, 320))

        recorded = self.window._record_impact(
            ObservedShot(-75, 20, fired_elevation_deg=4.5, fuze_seconds=3.2)
        )

        self.assertTrue(recorded)
        self.assertEqual(self.window.selected_target_id, 1)
        self.assertEqual(len(self.window._current_targets()), 1)
        self.assertEqual(len(self.window._current_targets()[0].shots), 1)
        target_item = self.window.target_history_tree.topLevelItem(0)
        self.assertTrue(target_item.text(0).startswith("T1 ·"))
        self.assertIn("ELEV", target_item.text(0))
        self.assertIn("CLEARANCE", target_item.text(0))
        self.assertIn("FUZE", target_item.text(0))
        self.assertNotIn("yd", target_item.text(0))
        self.assertRegex(
            target_item.text(0),
            r"CLEARANCE [+-]\d+\.\d m",
        )
        self.assertNotIn("OBSTRUCTED", target_item.text(0))
        self.assertNotIn("CLEAR ·", target_item.text(0))
        self.assertEqual(target_item.text(0).count("°"), 1)
        self.assertIn("75 SHORT, 20 RIGHT", target_item.child(0).text(0))
        self.assertIn(1, self.window.view._saved_target_markers)
        self.assertEqual(len(self.window.view._target_history_items), 3)

    def test_tapping_selected_target_collapses_overlay_and_impacts(self) -> None:
        self.window._select_map(discover_maps(self.maps_dir)[0])
        self.window._add_measurement_point(QPointF(100, 120))
        self.window._add_measurement_point(QPointF(300, 320))
        self.window._record_impact(ObservedShot(-50, -10))

        self.window._select_saved_target(1)

        self.assertIsNone(self.window.selected_target_id)
        self.assertIsNone(self.window.view._target_solution_label)
        self.assertEqual(len(self.window.view._target_history_items), 1)

        self.window._select_saved_target(1)

        self.assertEqual(self.window.selected_target_id, 1)
        self.assertIsNotNone(self.window.view._target_solution_label)
        self.assertEqual(len(self.window.view._target_history_items), 3)

    def test_dragging_any_saved_target_moves_it_without_creating_another(self) -> None:
        self.window._select_map(discover_maps(self.maps_dir)[0])
        gun = QPointF(100, 120)
        self.window._add_measurement_point(gun)
        self.window._add_measurement_point(QPointF(300, 320))
        self.window._add_measurement_point(QPointF(500, 520))
        moved_target = QPointF(360, 390)

        first_marker = self.window.view._saved_target_markers[1]
        self.assertTrue(
            first_marker.flags()
            & QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        )
        self.window._move_saved_target(1, moved_target)

        self.assertEqual(self.window.points, [gun, moved_target])
        self.assertEqual(len(self.window._current_targets()), 2)
        self.assertEqual(self.window.selected_target_id, 1)
        self.assertEqual(
            self.window._current_targets()[0].target,
            Point(moved_target.x(), moved_target.y()),
        )
        self.assertEqual(
            self.window._current_targets()[1].target,
            Point(500, 520),
        )

    def test_saved_target_right_click_removal_path_deletes_immediately(self) -> None:
        self.window._select_map(discover_maps(self.maps_dir)[0])
        self.window._add_measurement_point(QPointF(100, 120))
        self.window._add_measurement_point(QPointF(300, 320))
        marker = self.window.view._saved_target_markers[1]
        self.assertTrue(
            marker.acceptedMouseButtons() & Qt.MouseButton.RightButton
        )

        self.window._remove_saved_target(1)

        self.assertEqual(self.window._current_targets(), [])
        self.assertNotIn(1, self.window.view._saved_target_markers)

    def test_removing_gun_retains_target_until_replacement_gun_is_placed(self) -> None:
        self.window._select_map(discover_maps(self.maps_dir)[0])
        original_gun = QPointF(100, 120)
        target_point = QPointF(300, 320)
        replacement_gun = QPointF(180, 220)
        self.window._add_measurement_point(original_gun)
        self.window._add_measurement_point(target_point)
        target_marker = self.window.view._markers[1]

        self.window.view._remove_entity(self.window.view._markers[0])

        self.assertEqual(self.window.points, [])
        self.assertEqual(self.window.view._markers, [target_marker])
        self.assertEqual(target_marker.role, "target")
        self.assertEqual(target_marker.scenePos(), target_point)

        self.window._add_measurement_point(replacement_gun)

        self.assertEqual(self.window.points, [replacement_gun, target_point])
        self.assertEqual(
            [marker.role for marker in self.window.view._markers],
            ["gun", "target"],
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
        solid, _collision, skipped, _impact = self.window.view._trajectory_items
        self.assertEqual(solid.pen().style(), Qt.PenStyle.SolidLine)
        self.assertEqual(skipped.pen().style(), Qt.PenStyle.DashLine)
        self.assertEqual(solid.pen().color(), QColor("#d94149"))
        self.assertEqual(skipped.pen().color(), QColor("#d94149"))
        self.assertFalse(self.window.view._line.isVisible())
        self.assertTrue(
            all(
                item.zValue() < self.window.view._markers[1].zValue()
                for item in self.window.view._trajectory_items
            )
        )
        self.window.view.clear_trajectory_overlay()
        self.assertEqual(self.window.view._trajectory_items, [])
        self.assertTrue(self.window.view._line.isVisible())

    def test_control_column_scrolls_in_short_window(self) -> None:
        self.window.resize(1100, 560)
        self.app.processEvents()
        self.assertGreater(
            self.window.control_scroll.verticalScrollBar().maximum(),
            0,
        )

    def test_solution_options_are_in_header_and_map_toggles_are_at_bottom(self) -> None:
        self.window._select_map(discover_maps(self.maps_dir)[0])
        self.window.resize(1100, 560)
        self.app.processEvents()

        header_options = (
            self.window.cannon_type,
            self.window.projectile_type,
            self.window.ballistic_method,
        )
        for option in header_options:
            self.assertTrue(self.window.toolbar.isAncestorOf(option))
            self.assertFalse(self.window.control_scroll.isAncestorOf(option))
            self.assertTrue(option.isVisible())
        header_button_texts = {
            button.text() for button in self.window.toolbar.findChildren(QPushButton)
        }
        self.assertNotIn("FIT MAP", header_button_texts)
        self.assertNotIn("CLEAR", header_button_texts)
        bottom_toggles = (
            self.window.grayscale_map,
            self.window.elevation_overlay,
        )
        for toggle in bottom_toggles:
            self.assertTrue(self.window.display_options_bar.isAncestorOf(toggle))
            self.assertFalse(self.window.control_scroll.isAncestorOf(toggle))
            self.assertTrue(toggle.isVisible())
        self.assertFalse(hasattr(self.window, "measurement"))
        self.assertTrue(
            self.window.control_scroll.isAncestorOf(self.window.muzzle_velocity)
        )
        self.assertTrue(
            self.window.control_scroll.isAncestorOf(self.window.drag_factor)
        )
        self.window.grayscale_map.setChecked(True)
        self.assertEqual(self.window.view._map_style, "Grayscale")

    def test_map_rows_use_muted_gold_selection_and_outlined_hover(self) -> None:
        item_rule = self.window.styleSheet().split(
            "QTreeWidget::item {", 1
        )[1].split("}", 1)[0]
        hover_rule = self.window.styleSheet().split(
            "QTreeWidget::item:hover", 1
        )[1].split("}", 1)[0]
        selected_rule = self.window.styleSheet().split(
            "QTreeWidget::item:selected", 1
        )[1].split("}", 1)[0]
        self.assertIn("font-weight: 700", item_rule)
        self.assertIn("background: #1d261d", hover_rule)
        self.assertIn("border-color: #465442", hover_rule)
        self.assertIn("background: #cdb36b", selected_rule)
        self.assertIn("border-color: #cdb36b", selected_rule)
        self.assertIn("color: #15160f", selected_rule)
        self.assertIn(
            "QTreeWidget::branch:hover, QTreeWidget::branch:selected "
            "{ background: #121811; }",
            self.window.styleSheet(),
        )

    def test_map_groups_toggle_on_single_click_and_cannot_be_selected(self) -> None:
        battlefield = self.window.map_tree.topLevelItem(0)
        mode = battlefield.child(0)
        map_item = mode.child(0)

        self.assertFalse(
            battlefield.flags() & Qt.ItemFlag.ItemIsSelectable
        )
        self.assertFalse(mode.flags() & Qt.ItemFlag.ItemIsSelectable)
        self.assertTrue(map_item.flags() & Qt.ItemFlag.ItemIsSelectable)
        self.assertTrue(battlefield.font(0).bold())
        self.assertTrue(mode.font(0).bold())
        self.assertTrue(map_item.font(0).bold())
        self.assertFalse(self.window.map_tree.expandsOnDoubleClick())
        self.assertIn(
            "QTreeWidget::branch { image: none; background: #121811; }",
            self.window.styleSheet(),
        )

        self.assertFalse(battlefield.isExpanded())
        self.window._tree_item_clicked(battlefield, 0)
        self.assertTrue(battlefield.isExpanded())
        self.window._tree_item_clicked(battlefield, 0)
        self.assertFalse(battlefield.isExpanded())

    def test_target_solution_box_does_not_overlap_target_marker(self) -> None:
        self.window._select_map(discover_maps(self.maps_dir)[0])
        self.window._add_measurement_point(QPointF(100, 120))
        self.window._add_measurement_point(QPointF(300, 320))
        self.app.processEvents()

        target = self.window.view._markers[1]
        background = self.window.view._target_solution_background
        self.assertIsNotNone(background)
        assert background is not None
        self.assertFalse(
            target.sceneBoundingRect().intersects(background.sceneBoundingRect())
        )

    def test_sidebar_keeps_thumbnails_without_collapse_strip(self) -> None:
        battlefield = self.window.map_tree.topLevelItem(0)
        map_item = battlefield.child(0).child(0)

        self.assertFalse(map_item.icon(0).isNull())
        self.assertTrue(map_item.font(0).bold())
        self.assertFalse(hasattr(self.window, "sidebar_toggle"))

    def test_sidebar_owns_scrollable_target_tools_and_map_data(self) -> None:
        self.assertIs(
            self.window.sidebar_pages.currentWidget(),
            self.window.sidebar_library_page,
        )
        record = discover_maps(self.maps_dir)[0]

        self.window._select_map(record)

        self.assertIs(
            self.window.sidebar_pages.currentWidget(),
            self.window.sidebar_map_data_page,
        )
        self.assertTrue(self.window.sidebar.isAncestorOf(self.window.map_info))
        self.assertFalse(self.window.control_scroll.isAncestorOf(self.window.map_info))
        for control in (
            self.window.target_history_tree,
            self.window.record_impact_button,
        ):
            self.assertTrue(self.window.sidebar_tool_scroll.isAncestorOf(control))
            self.assertFalse(self.window.control_scroll.isAncestorOf(control))
        self.assertIn("SOURCE    GAME PAK", self.window.map_info.text())
        self.assertIn("AREA", self.window.map_info.text())
        self.assertIn("SCALE", self.window.map_info.text())
        self.assertEqual(
            sum(
                label.text() == "MAP DATA"
                for label in self.window.findChildren(QLabel)
            ),
            1,
        )

        self.window._show_map_library()
        self.assertIs(
            self.window.sidebar_pages.currentWidget(),
            self.window.sidebar_library_page,
        )

    def test_left_tools_are_flat_while_solution_cards_remain_outlined(self) -> None:
        style = self.window.styleSheet()
        self.assertIn("QWidget#sidebar { border-right: 1px solid #465442; }", style)
        self.assertIn("QFrame#sidebarSection", style)
        self.assertIn("background: #121811", style)
        self.assertIn(
            "QTreeWidget#targetHistoryTree::item:selected",
            style,
        )
        self.assertIn("QFrame#panelCard", style)
        self.assertIn("QFrame#readout", style)
        self.assertIn("border: 1px solid #465442", style)
        self.assertIn("border-bottom: 1px solid #465442", style)
        self.assertIn("background:#121811", self.window.map_info.styleSheet())
        self.assertIn("border:0", self.window.map_info.styleSheet())
        self.assertEqual(self.window.history_toggle.objectName(), "sidebarSectionTitle")
        self.assertEqual(
            self.window.record_impact_button.objectName(),
            "sidebarActionButton",
        )
        self.assertIn("background: #121811", style)
        self.assertIn("background:#121811", self.window.view.styleSheet())
        self.assertIn("background:#121811", self.window.clearance_details.styleSheet())
        self.assertEqual(
            self.window.view.backgroundBrush().color(),
            QColor("#121811"),
        )
        self.assertIn(
            "border:1px solid #465442",
            self.window.solution_bearing.styleSheet(),
        )

    def test_target_history_height_tracks_content_without_large_empty_card(self) -> None:
        self.window._select_map(discover_maps(self.maps_dir)[0])
        self.window._add_measurement_point(QPointF(100, 120))
        empty_height = 220
        self.assertEqual(self.window.target_history_tree.height(), empty_height)

        for point in (QPointF(200, 220), QPointF(300, 320)):
            self.window._add_measurement_point(point)
        self.app.processEvents()

        self.assertEqual(
            self.window.target_history_tree.verticalScrollBar().maximum(),
            0,
        )

        for point in (QPointF(400, 420), QPointF(500, 520), QPointF(600, 620)):
            self.window._add_measurement_point(point)

        self.assertGreater(self.window.target_history_tree.height(), empty_height)
        self.assertLessEqual(self.window.target_history_tree.height(), 420)

    def test_obstructed_route_status_is_one_line_with_only_outcome_red(self) -> None:
        result = TrajectoryClearanceResult(
            confidence="estimated",
            target_range_yards=1000,
            original_elevation_deg=5,
            obstructed=True,
            first_obstruction_yards=400,
            minimum_clearance_metres=-2,
            clearing_elevation_deg=6,
            impact_range_yards=1100,
            overshoot_yards=100,
            height_above_target_metres=0,
            original_trajectory=(),
            clearing_trajectory=(),
        )

        self.window._set_clearance_result(result)

        self.assertEqual(
            self.window.clearance_status.text(),
            'ESTIMATED ROUTE: <span style="color:#ff7a70; '
            'font-weight:700;">OBSTRUCTED</span>',
        )
        labels = {
            label.text() for label in self.window.findChildren(QLabel)
        }
        self.assertNotIn("ROUTE CLEARANCE · ESTIMATED", labels)


if __name__ == "__main__":
    unittest.main()
