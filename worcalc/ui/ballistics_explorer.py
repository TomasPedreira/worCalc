from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)

from ..domain.ballistics import (
    LinearModel,
    PchipModel,
    PolynomialModel,
    ReferencePoint,
    elevation_for_range,
    height_adjusted_elevation,
    load_reference_points,
    reference_bracket,
    rmse,
)
from ..paths import BALLISTICS_CSV


class CurvePlot(QWidget):
    def __init__(self, points: list[ReferencePoint]) -> None:
        super().__init__()
        self.points = points
        self.model = None
        self.target_range = points[len(points) // 2].range_yards
        self.target_elevation: float | None = None
        self.setMinimumSize(420, 320)

    def set_selection(self, model, target_range: float, target_elevation: float | None) -> None:
        self.model = model
        self.target_range = target_range
        self.target_elevation = target_elevation
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#121811"))
        plot = QRectF(76, 28, self.width() - 105, self.height() - 88)
        min_x, max_x = self.points[0].elevation_deg, self.points[-1].elevation_deg
        max_y = 4500.0

        def location(x: float, y: float) -> QPointF:
            return QPointF(
                plot.left() + (x - min_x) / (max_x - min_x) * plot.width(),
                plot.bottom() - y / max_y * plot.height(),
            )

        grid_pen = QPen(QColor("#42464d"), 1)
        painter.setPen(grid_pen)
        for angle in range(int(min_x), int(max_x) + 1, 2):
            point = location(angle, 0)
            painter.drawLine(QPointF(point.x(), plot.top()), QPointF(point.x(), plot.bottom()))
        for yards in range(0, 4501, 500):
            point = location(min_x, yards)
            painter.drawLine(QPointF(plot.left(), point.y()), QPointF(plot.right(), point.y()))

        painter.setPen(QPen(QColor("#e5e7eb"), 1.5))
        painter.drawRect(plot)
        font = QFont("Segoe UI", 9)
        painter.setFont(font)
        for angle in range(int(min_x), int(max_x) + 1, 2):
            point = location(angle, 0)
            painter.drawText(QRectF(point.x() - 18, plot.bottom() + 8, 36, 18), Qt.AlignmentFlag.AlignCenter, str(angle))
        for yards in range(0, 4501, 500):
            point = location(min_x, yards)
            painter.drawText(QRectF(4, point.y() - 9, 64, 18), Qt.AlignmentFlag.AlignRight, f"{yards:,}")
        painter.drawText(QRectF(plot.left(), self.height() - 34, plot.width(), 20), Qt.AlignmentFlag.AlignCenter, "Elevation (degrees)")
        painter.save()
        painter.translate(18, plot.center().y())
        painter.rotate(-90)
        painter.drawText(QRectF(-plot.height() / 2, -10, plot.height(), 20), Qt.AlignmentFlag.AlignCenter, "Range (yards)")
        painter.restore()

        if self.model is not None:
            curve = QPainterPath()
            for index in range(401):
                angle = min_x + (max_x - min_x) * index / 400
                point = location(angle, self.model.evaluate(angle))
                curve.moveTo(point) if index == 0 else curve.lineTo(point)
            painter.setPen(QPen(QColor("#ff3d9e"), 3))
            painter.drawPath(curve)

        painter.setPen(QPen(QColor("#111318"), 1.5))
        painter.setBrush(QColor("#7cff4f"))
        for point in self.points:
            screen = location(point.elevation_deg, point.range_yards)
            painter.drawEllipse(screen, 5, 5)

        if self.target_elevation is not None:
            target = location(self.target_elevation, self.target_range)
            dashed = QPen(QColor("#f7f4ea"), 1.5, Qt.PenStyle.DashLine)
            painter.setPen(dashed)
            painter.drawLine(QPointF(plot.left(), target.y()), target)
            painter.drawLine(QPointF(target.x(), plot.bottom()), target)
            painter.setPen(QPen(QColor("#ffffff"), 2))
            painter.setBrush(QColor("#ff3d9e"))
            painter.drawEllipse(target, 6, 6)
        painter.end()


class ExplorerWindow(QMainWindow):
    def __init__(self, csv_path: Path) -> None:
        super().__init__()
        self.points = load_reference_points(csv_path)
        self.models = [
            LinearModel(self.points),
            PchipModel(self.points),
            PolynomialModel(self.points, 2),
            PolynomialModel(self.points, 3),
        ]
        self.target_height_change_metres = 0.0
        self.base_elevation_deg: float | None = None
        self.height_correction_deg = 0.0
        self.solution_elevation_deg: float | None = None
        self.setWindowTitle("War of Rights — 3-inch Rifle Curve Explorer")

        self.method = QComboBox()
        self.method.addItems([model.name for model in self.models])
        self.method.setCurrentIndex(3)
        self.method.currentIndexChanged.connect(self._refresh)
        self.target = QDoubleSpinBox()
        self.target.setRange(0, sys.float_info.max)
        self.target.setDecimals(0)
        self.target.setSingleStep(10)
        self.target.setSuffix(" yd")
        self.target.setValue(2500)
        self.target.valueChanged.connect(self._refresh)

        form = QFormLayout()
        form.addRow("Curve method", self.method)
        form.addRow("Target range", self.target)
        controls = QVBoxLayout()
        controls.addLayout(form)
        self.elevation = QLabel()
        self.elevation.setStyleSheet("font-size: 30px; font-weight: 600; color: #ff3d9e;")
        controls.addWidget(self.elevation)
        self.details = QLabel()
        self.details.setWordWrap(True)
        self.details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        controls.addWidget(self.details)
        self.comparison = QLabel()
        self.comparison.setWordWrap(True)
        self.comparison.setStyleSheet("background: #121811; padding: 10px; border-radius: 5px;")
        controls.addWidget(self.comparison)
        controls.addStretch()
        control_widget = QWidget()
        control_widget.setLayout(controls)
        control_widget.setFixedWidth(290)

        self.plot = CurvePlot(self.points)
        layout = QHBoxLayout()
        layout.addWidget(control_widget)
        layout.addWidget(self.plot, 1)
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            self.resize(1100, 650)
        else:
            available = screen.availableGeometry()
            self.resize(min(1100, int(available.width() * 0.92)), min(650, int(available.height() * 0.92)))
            frame = self.frameGeometry()
            frame.moveCenter(available.center())
            self.move(frame.topLeft())
        self._refresh()

    def set_target_range(self, yards: float) -> None:
        """Update a level-ground requested range."""
        self.target_height_change_metres = 0.0
        self.target.setValue(max(0.0, yards))
        self._refresh()

    def set_target_geometry(
        self,
        horizontal_range_yards: float,
        target_height_change_metres: float,
    ) -> None:
        """Update horizontal range and signed target height relative to the gun."""
        self.target_height_change_metres = target_height_change_metres
        self.target.setValue(max(0.0, horizontal_range_yards))
        self._refresh()

    def _refresh(self) -> None:
        selected = self.models[self.method.currentIndex()]
        target = self.target.value()
        minimum, maximum = self.points[0].elevation_deg, self.points[-1].elevation_deg
        range_minimum = self.points[0].range_yards
        range_maximum = self.points[-1].range_yards
        in_reference_range = range_minimum <= target <= range_maximum
        base_angle = elevation_for_range(selected, target, minimum, maximum)
        self.base_elevation_deg = base_angle
        if base_angle is None:
            angle = None
            self.height_correction_deg = 0.0
        else:
            angle = height_adjusted_elevation(
                base_angle,
                target,
                self.target_height_change_metres,
            )
            self.height_correction_deg = angle - base_angle
        self.solution_elevation_deg = angle
        if angle is None:
            self.elevation.setText("No solution")
        else:
            self.elevation.setText(f"{angle:.3f}° elevation")
        if not in_reference_range:
            bracket = (
                f"Extrapolating beyond official reference range "
                f"({range_minimum:,.0f}–{range_maximum:,.0f} yd)."
            )
        else:
            left, right = reference_bracket(self.points, target)
            if left == right:
                bracket = f"Exact official point: {left.elevation_deg:g}° → {left.range_yards:,.0f} yd"
            else:
                bracket = (
                    f"Official bracket: {left.elevation_deg:g}° → {left.range_yards:,.0f} yd  |  "
                    f"{right.elevation_deg:g}° → {right.range_yards:,.0f} yd"
                )
        description = selected.equation if isinstance(selected, PolynomialModel) else "Passes through every official reference point."
        geometry = (
            f"Level-ground solution: {base_angle:.3f}°  |  "
            f"Target height: {self.target_height_change_metres:+.2f} m  |  "
            f"Sight-angle correction: {self.height_correction_deg:+.3f}°"
            if base_angle is not None
            else "No mathematical level-ground solution."
        )
        self.details.setText(
            f"{bracket}\n{description}\n{geometry}\n"
            f"Reference-point RMSE: {rmse(selected, self.points):.2f} yd"
        )
        lines = []
        for model in self.models:
            base_result = elevation_for_range(model, target, minimum, maximum)
            result = (
                height_adjusted_elevation(
                    base_result,
                    target,
                    self.target_height_change_metres,
                )
                if base_result is not None
                else None
            )
            value = f"{result:.3f}°" if result is not None else "no mathematical solution"
            lines.append(f"{model.name}: {value}")
        self.comparison.setText("Method comparison\n" + "\n".join(lines))
        self.plot.set_selection(selected, target, base_angle)


def main() -> int:
    csv_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else BALLISTICS_CSV
    app = QApplication(sys.argv)
    window = ExplorerWindow(csv_path)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
