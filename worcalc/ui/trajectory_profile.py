"""Compact side-profile rendering for terrain and shell trajectories."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from ..domain.trajectory import TrajectoryClearanceResult, TrajectorySample


class TrajectoryProfilePlot(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.result: TrajectoryClearanceResult | None = None
        self.setMinimumHeight(190)
        self.setToolTip(
            "Estimated terrain side profile with the original and clearing shell arcs"
        )

    def set_result(self, result: TrajectoryClearanceResult | None) -> None:
        self.result = result
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#121811"))
        plot = QRectF(40, 18, max(1, self.width() - 52), max(1, self.height() - 48))
        painter.setPen(QPen(QColor("#394235"), 1))
        painter.drawRect(plot)
        result = self.result
        if result is None or not result.original_trajectory:
            painter.setPen(QColor("#8f9888"))
            painter.drawText(
                plot,
                Qt.AlignmentFlag.AlignCenter,
                "PLACE GUN AND TARGET\nFOR CLEARANCE PROFILE",
            )
            painter.end()
            return

        impact = result.impact_range_yards or result.target_range_yards
        maximum_distance = max(
            result.target_range_yards * 1.15,
            impact * 1.05,
        )
        available_distance = result.original_trajectory[-1].distance_yards
        maximum_distance = min(maximum_distance, available_distance)
        trajectories = [result.original_trajectory]
        if result.clearing_trajectory:
            trajectories.append(result.clearing_trajectory)
        visible = [
            sample
            for samples in trajectories
            for sample in samples
            if sample.distance_yards <= maximum_distance
        ]
        terrain = [
            sample
            for sample in result.original_trajectory
            if sample.distance_yards <= maximum_distance
        ]
        minimum_height = min(sample.terrain_elevation_metres for sample in terrain)
        maximum_height = max(
            max(sample.shell_elevation_metres for sample in visible),
            max(sample.terrain_elevation_metres for sample in terrain),
        )
        span = max(maximum_height - minimum_height, 1.0)
        minimum_height -= span * 0.08
        maximum_height += span * 0.08

        def location(distance: float, elevation: float) -> QPointF:
            return QPointF(
                plot.left() + distance / maximum_distance * plot.width(),
                plot.bottom()
                - (elevation - minimum_height)
                / (maximum_height - minimum_height)
                * plot.height(),
            )

        terrain_path = QPainterPath()
        terrain_path.moveTo(plot.left(), plot.bottom())
        for sample in terrain:
            terrain_path.lineTo(
                location(sample.distance_yards, sample.terrain_elevation_metres)
            )
        terrain_path.lineTo(location(terrain[-1].distance_yards, minimum_height))
        terrain_path.closeSubpath()
        painter.fillPath(terrain_path, QColor("#394735"))
        painter.setPen(QPen(QColor("#8fa278"), 1.5))
        terrain_line = QPainterPath()
        for index, sample in enumerate(terrain):
            point = location(sample.distance_yards, sample.terrain_elevation_metres)
            terrain_line.moveTo(point) if index == 0 else terrain_line.lineTo(point)
        painter.drawPath(terrain_line)

        original_color = QColor("#e34f4f" if result.obstructed else "#35c46a")
        self._draw_trajectory(
            painter,
            result.original_trajectory,
            maximum_distance,
            location,
            QPen(original_color, 2),
        )
        if (
            result.obstructed
            and result.clearing_trajectory
            and result.clearing_elevation_deg is not None
        ):
            self._draw_trajectory(
                painter,
                result.clearing_trajectory,
                maximum_distance,
                location,
                QPen(QColor("#e2c85d"), 2, Qt.PenStyle.DashLine),
            )

        target_x = location(result.target_range_yards, minimum_height).x()
        painter.setPen(QPen(QColor("#d8d3bd"), 1, Qt.PenStyle.DotLine))
        painter.drawLine(
            QPointF(target_x, plot.top()),
            QPointF(target_x, plot.bottom()),
        )
        if result.impact_range_yards is not None:
            impact_x = location(result.impact_range_yards, minimum_height).x()
            painter.setPen(QPen(QColor("#e2c85d"), 1))
            painter.drawLine(
                QPointF(impact_x, plot.bottom() - 7),
                QPointF(impact_x, plot.bottom() + 2),
            )

        painter.setFont(QFont("Consolas", 8))
        painter.setPen(QColor("#c9b86c"))
        painter.drawText(
            QRectF(plot.left(), plot.bottom() + 5, plot.width(), 18),
            Qt.AlignmentFlag.AlignLeft,
            "GUN",
        )
        painter.drawText(
            QRectF(target_x - 35, plot.bottom() + 5, 70, 18),
            Qt.AlignmentFlag.AlignCenter,
            "TARGET",
        )
        painter.setPen(QColor("#9ba392"))
        painter.drawText(
            QRectF(2, plot.top(), 34, 18),
            Qt.AlignmentFlag.AlignRight,
            f"{maximum_height:.0f}m",
        )
        painter.drawText(
            QRectF(2, plot.bottom() - 16, 34, 18),
            Qt.AlignmentFlag.AlignRight,
            f"{minimum_height:.0f}m",
        )
        painter.end()

    @staticmethod
    def _draw_trajectory(
        painter: QPainter,
        samples: tuple[TrajectorySample, ...],
        maximum_distance: float,
        location,
        pen: QPen,
    ) -> None:
        path = QPainterPath()
        drawn = 0
        for sample in samples:
            if sample.distance_yards > maximum_distance:
                break
            point = location(sample.distance_yards, sample.shell_elevation_metres)
            path.moveTo(point) if drawn == 0 else path.lineTo(point)
            drawn += 1
        if drawn > 1:
            painter.setPen(pen)
            painter.drawPath(path)
