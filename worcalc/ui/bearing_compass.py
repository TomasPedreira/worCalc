"""Compact world-bearing compass for the fire-mission panel."""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, degrees, floor, radians, sin

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

GAME_COMPASS_STEP_DEGREES = 15.0


@dataclass(frozen=True)
class GameCompassAim:
    """The closest mark that can be read on the in-game compass."""

    bearing_degrees: float
    mark_degrees: float
    direction: str
    ticks_after_direction: int
    error_degrees: float

    @property
    def instruction(self) -> str:
        if self.ticks_after_direction == 0:
            return self.direction
        suffix = "TICK" if self.ticks_after_direction == 1 else "TICKS"
        return f"{self.direction} +{self.ticks_after_direction} {suffix}"


def game_compass_aim(bearing_degrees: float) -> GameCompassAim:
    """Snap a north-up bearing to the game's 24 compass marks.

    The game labels every third mark (N, NE, E, ...), with two small marks
    clockwise between labels.  Half steps resolve clockwise so the result is
    deterministic at exactly 7.5 degrees.
    """
    bearing = bearing_degrees % 360.0
    mark_index = int(floor(bearing / GAME_COMPASS_STEP_DEGREES + 0.5)) % 24
    mark = mark_index * GAME_COMPASS_STEP_DEGREES
    direction_index, ticks_after_direction = divmod(mark_index, 3)
    direction = COMPASS_DIAL_LABELS[direction_index][1]
    error = (bearing - mark + 180.0) % 360.0 - 180.0
    return GameCompassAim(
        bearing_degrees=bearing,
        mark_degrees=mark,
        direction=direction,
        ticks_after_direction=ticks_after_direction,
        error_degrees=error,
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
        self.setMinimumHeight(112)
        self.setToolTip(
            "North-up bearing from cannon to target. The highlighted mark is "
            "the closest mark on the in-game compass."
        )

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
        return QSize(290, 118)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        diameter = min(96.0, self.width() * 0.38, self.height() - 16.0)
        dial = QRectF(
            10,
            (self.height() - diameter) / 2,
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

        painter.setFont(QFont("Consolas", 7, QFont.Weight.Bold))
        painter.setPen(QColor("#eee9d5"))
        label_radius = radius - 14
        for bearing, text in COMPASS_DIAL_LABELS:
            angle = radians(bearing - 90)
            point = QPointF(
                center.x() + cos(angle) * label_radius,
                center.y() + sin(angle) * label_radius,
            )
            painter.drawText(
                QRectF(point.x() - 10, point.y() - 7, 20, 14),
                Qt.AlignmentFlag.AlignCenter,
                text,
            )

        aim: GameCompassAim | None = None
        if self._bearing is not None:
            aim = game_compass_aim(self._bearing)
            mark_angle = radians(aim.mark_degrees - 90)
            mark = QPointF(
                center.x() + cos(mark_angle) * (radius - 4),
                center.y() + sin(mark_angle) * (radius - 4),
            )
            painter.setPen(QPen(QColor("#fff5cd"), 3.5))
            painter.drawPoint(mark)

            angle = radians(self._bearing - 90)
            tip = QPointF(
                center.x() + cos(angle) * (radius - 19),
                center.y() + sin(angle) * (radius - 19),
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
        readout_left = dial.right() + 12
        readout = QRectF(
            readout_left,
            8,
            max(0.0, self.width() - readout_left - 8),
            self.height() - 16,
        )
        painter.setPen(QColor("#8f987f"))
        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold))
        painter.drawText(readout, Qt.AlignmentFlag.AlignTop, "IN-GAME COMPASS")

        if aim is not None:
            painter.setPen(QColor("#fff5cd"))
            painter.setFont(QFont("Consolas", 13, QFont.Weight.Bold))
            painter.drawText(
                readout.adjusted(0, 20, 0, 0),
                Qt.AlignmentFlag.AlignTop,
                aim.instruction,
            )
            painter.setPen(QColor("#e2c85d"))
            painter.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
            painter.drawText(
                readout.adjusted(0, 48, 0, 0),
                Qt.AlignmentFlag.AlignTop,
                f"MARK {aim.mark_degrees:03.0f}°",
            )
            painter.setPen(QColor("#b9c0b1"))
            painter.setFont(QFont("Consolas", 8))
            painter.drawText(
                readout.adjusted(0, 68, 0, 0),
                Qt.AlignmentFlag.AlignTop,
                f"EXACT {self._bearing:06.2f}°",
            )
        else:
            painter.setPen(QColor("#fff5cd"))
            painter.setFont(QFont("Consolas", 13, QFont.Weight.Bold))
            painter.drawText(
                readout.adjusted(0, 25, 0, 0),
                Qt.AlignmentFlag.AlignTop,
                "—",
            )
        painter.end()
