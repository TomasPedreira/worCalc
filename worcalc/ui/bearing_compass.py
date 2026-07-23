"""Compact world-bearing compass for the fire-mission panel."""

from __future__ import annotations

from math import atan2, cos, degrees, radians, sin

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget


COMPASS_DIAL_LABELS = (
    (0, "N"),
    (45, "NE"),
    (90, "E"),
    (135, "SE"),
    (180, "S"),
    (225, "SW"),
    (270, "W"),
    (315, "NW"),
)


def compass_direction(bearing_degrees: float) -> str:
    directions = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
    return directions[round((bearing_degrees % 360.0) / 45.0) % 8]


def map_bearing_degrees(pixel_dx: float, pixel_dy: float) -> float:
    """North-up map bearing: up=0, right=90, down=180, left=270."""
    return (degrees(atan2(pixel_dx, -pixel_dy)) + 360.0) % 360.0


class BearingCompass(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._bearing: float | None = None
        self.setMinimumHeight(150)
        self.setToolTip("North-up map bearing from cannon to target")

    @property
    def bearing(self) -> float | None:
        return self._bearing

    def set_bearing(self, bearing_degrees: float) -> None:
        self._bearing = bearing_degrees % 360.0
        self.update()

    def clear_bearing(self) -> None:
        self._bearing = None
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(290, 170)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        diameter = min(self.width() - 24, self.height() - 34)
        dial = QRectF(
            (self.width() - diameter) / 2,
            5,
            diameter,
            diameter,
        )
        center = dial.center()
        radius = diameter / 2

        painter.setPen(QPen(QColor("#5b654f"), 1.5))
        painter.setBrush(QColor("#121811"))
        painter.drawEllipse(dial)

        for bearing in range(0, 360, 15):
            angle = radians(bearing - 90)
            outer = QPointF(
                center.x() + cos(angle) * (radius - 4),
                center.y() + sin(angle) * (radius - 4),
            )
            tick_length = 10 if bearing % 90 == 0 else 6 if bearing % 45 == 0 else 3
            inner = QPointF(
                center.x() + cos(angle) * (radius - 4 - tick_length),
                center.y() + sin(angle) * (radius - 4 - tick_length),
            )
            painter.setPen(
                QPen(QColor("#e2c85d") if bearing % 90 == 0 else QColor("#7d856f"), 1.5)
            )
            painter.drawLine(inner, outer)

        painter.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        painter.setPen(QColor("#eee9d5"))
        label_radius = radius - 17
        for bearing, text in COMPASS_DIAL_LABELS:
            angle = radians(bearing - 90)
            point = QPointF(
                center.x() + cos(angle) * label_radius,
                center.y() + sin(angle) * label_radius,
            )
            painter.drawText(
                QRectF(point.x() - 12, point.y() - 9, 24, 18),
                Qt.AlignmentFlag.AlignCenter,
                text,
            )

        if self._bearing is not None:
            angle = radians(self._bearing - 90)
            tip = QPointF(
                center.x() + cos(angle) * (radius - 24),
                center.y() + sin(angle) * (radius - 24),
            )
            left = QPointF(
                center.x() + cos(angle + 2.6) * 9,
                center.y() + sin(angle + 2.6) * 9,
            )
            right = QPointF(
                center.x() + cos(angle - 2.6) * 9,
                center.y() + sin(angle - 2.6) * 9,
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#ff5a4f"))
            painter.drawPolygon(QPolygonF((tip, left, right)))
            painter.setBrush(QColor("#e2c85d"))
            painter.drawEllipse(center, 4, 4)
            readout = (
                f"{self._bearing:06.2f}°  "
                f"{compass_direction(self._bearing)}"
            )
        else:
            readout = "—"

        painter.setFont(QFont("Consolas", 12, QFont.Weight.Bold))
        painter.setPen(QColor("#fff5cd"))
        painter.drawText(
            QRectF(0, dial.bottom() + 5, self.width(), 24),
            Qt.AlignmentFlag.AlignCenter,
            readout,
        )
        painter.end()
