import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from worcalc.domain.calibration import AffineCalibration, Point
from worcalc.ui.map_view import (
    MapView,
    circle_intersections,
    common_circle_intersections,
)


class CircleIntersectionTests(unittest.TestCase):
    def test_two_intersections_are_returned(self) -> None:
        points = circle_intersections(Point(0, 0), 5, Point(6, 0), 5)

        self.assertEqual(len(points), 2)
        self.assertAlmostEqual(points[0].x, 3)
        self.assertAlmostEqual(abs(points[0].y), 4)
        self.assertAlmostEqual(points[1].x, 3)
        self.assertAlmostEqual(abs(points[1].y), 4)

    def test_tangent_and_disjoint_circles(self) -> None:
        tangent = circle_intersections(Point(0, 0), 5, Point(10, 0), 5)

        self.assertEqual(tangent, [Point(5, 0)])
        self.assertEqual(
            circle_intersections(Point(0, 0), 5, Point(11, 0), 5),
            [],
        )

    def test_third_circle_disambiguates_two_initial_candidates(self) -> None:
        points = common_circle_intersections(
            [
                (Point(0, 0), 5),
                (Point(6, 0), 5),
                (Point(3, 8), 4),
            ]
        )

        self.assertEqual(len(points), 1)
        self.assertAlmostEqual(points[0].x, 3)
        self.assertAlmostEqual(points[0].y, 4)


class PositionEstimationViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.range_requests: list[float | None] = []

        def request_range(suggested: float | None) -> float:
            self.range_requests.append(suggested)
            return 175.0

        self.view = MapView(
            lambda _point: None,
            estimation_range_requested=request_range,
        )
        self.view.resize(500, 500)
        self.view.set_map(QPixmap(500, 500))
        self.view.set_range_transform(AffineCalibration(1, 0, 0, 1))
        self.view.show()
        self.app.processEvents()

    def tearDown(self) -> None:
        self.view.close()

    def test_independent_ranges_create_candidates_without_gun_marker(self) -> None:
        radius_yards = 100 * 1.0936132983377078
        self.assertTrue(
            self.view.add_estimation_hit(QPointF(200, 250), radius_yards)
        )
        self.assertTrue(
            self.view.add_estimation_hit(QPointF(300, 250), radius_yards)
        )

        self.assertEqual(len(self.view._estimation_hits), 2)
        self.assertAlmostEqual(self.view._estimation_hits[0][1], radius_yards)
        self.assertAlmostEqual(self.view._estimation_hits[1][1], radius_yards)
        self.assertEqual(len(self.view._estimation_candidates), 2)

    def test_all_hits_are_retained_and_clear_removes_estimates(self) -> None:
        for x in (150, 200, 250):
            self.assertTrue(self.view.add_estimation_hit(QPointF(x, 250), 100))

        self.assertEqual(
            [hit[0] for hit in self.view._estimation_hits],
            [QPointF(150, 250), QPointF(200, 250), QPointF(250, 250)],
        )

        self.view.clear_points()

        self.assertEqual(self.view._estimation_hits, [])
        self.assertEqual(self.view._estimation_items, [])

    def test_hit_rejects_invalid_independent_range(self) -> None:
        self.assertFalse(self.view.add_estimation_hit(QPointF(200, 250), 0))
        self.assertFalse(
            self.view.add_estimation_hit(QPointF(200, 250), float("nan"))
        )

    def test_middle_click_records_hit_at_clicked_map_position(self) -> None:
        self.view.set_points([QPointF(100, 100), QPointF(200, 100)])
        viewport_point = self.view.mapFromScene(QPointF(250, 250))

        QTest.mouseClick(
            self.view.viewport(),
            Qt.MouseButton.MiddleButton,
            Qt.KeyboardModifier.NoModifier,
            viewport_point,
        )

        self.assertEqual(len(self.view._estimation_hits), 1)
        self.assertAlmostEqual(self.view._estimation_hits[0][0].x(), 250, delta=1)
        self.assertAlmostEqual(self.view._estimation_hits[0][0].y(), 250, delta=1)
        self.assertEqual(self.view._estimation_hits[0][1], 175)
        self.assertEqual(len(self.range_requests), 1)
        self.assertAlmostEqual(
            self.range_requests[0],
            100 * 1.0936132983377078,
        )

    def test_middle_click_without_markers_requests_an_independent_range(self) -> None:
        viewport_point = self.view.mapFromScene(QPointF(250, 250))

        QTest.mouseClick(
            self.view.viewport(),
            Qt.MouseButton.MiddleButton,
            Qt.KeyboardModifier.NoModifier,
            viewport_point,
        )

        self.assertEqual(self.range_requests, [None])
        self.assertEqual(self.view._estimation_hits[0][1], 175)

    def test_cancelled_range_request_does_not_record_hit(self) -> None:
        self.view._estimation_range_requested = lambda _suggested: None
        viewport_point = self.view.mapFromScene(QPointF(250, 250))

        QTest.mouseClick(
            self.view.viewport(),
            Qt.MouseButton.MiddleButton,
            Qt.KeyboardModifier.NoModifier,
            viewport_point,
        )

        self.assertEqual(self.view._estimation_hits, [])

    def test_right_click_on_hit_marker_removes_its_circle(self) -> None:
        self.view.add_estimation_hit(QPointF(200, 250), 100)
        self.view.add_estimation_hit(QPointF(300, 250), 100)
        viewport_point = self.view.mapFromScene(QPointF(200, 250))

        QTest.mouseClick(
            self.view.viewport(),
            Qt.MouseButton.RightButton,
            Qt.KeyboardModifier.NoModifier,
            viewport_point,
        )

        self.assertEqual(len(self.view._estimation_hits), 1)
        self.assertEqual(self.view._estimation_hits[0][0], QPointF(300, 250))
        self.assertEqual(self.view._estimation_candidates, [])


if __name__ == "__main__":
    unittest.main()
