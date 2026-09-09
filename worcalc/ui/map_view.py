from __future__ import annotations

from collections.abc import Callable
from math import cos, hypot, isclose, isfinite, radians, sin, sqrt
from typing import Any

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetricsF,
    QImage,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSceneMouseEvent,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QInputDialog,
)

from ..domain.calibration import AffineCalibration, METRES_TO_YARDS, Point
from ..domain.shot_history import FireTarget, correction_summary, observed_impact_point
from ..maps.elevation import ElevationField
from ..maps.entities import MapLocation


PARCHMENT_PAPER = (222, 205, 151)
PARCHMENT_INK = (45, 36, 22)
LOCATION_COLORS = {
    "gun_spawn": QColor("#40d6a0"),
    "battery": QColor("#f2ad3d"),
    "usa_spawn": QColor("#3f8cff"),
    "csa_spawn": QColor("#e34f4f"),
    "spawn": QColor("#9aa0a6"),
    "objective": QColor("#b75cff"),
}


def parchment_color(mask_value: int) -> tuple[int, int, int]:
    """Map an alpha-mask value to the game's ink-on-paper visual language."""
    amount = min(max(mask_value, 0), 255) / 255.0
    return tuple(
        round(paper + (ink - paper) * amount)
        for paper, ink in zip(PARCHMENT_PAPER, PARCHMENT_INK)
    )


def styled_map_pixmap(source: QPixmap, style: str) -> QPixmap:
    if style.casefold() != "parchment":
        return source
    mask = source.toImage().convertToFormat(QImage.Format.Format_Grayscale8)
    ink = QImage(source.size(), QImage.Format.Format_ARGB32_Premultiplied)
    ink.fill(QColor(*PARCHMENT_INK))
    ink.setAlphaChannel(mask)
    parchment = QImage(source.size(), QImage.Format.Format_RGB32)
    parchment.fill(QColor(*PARCHMENT_PAPER))
    painter = QPainter(parchment)
    painter.drawImage(0, 0, ink)
    painter.end()
    return QPixmap.fromImage(parchment)


def ruler_distance(yards_per_pixel: float, view_scale: float, screen_pixels: float = 140) -> float:
    """Return the yard distance represented by a fixed screen-space ruler."""
    if yards_per_pixel <= 0 or view_scale <= 0 or screen_pixels <= 0:
        return 0
    return yards_per_pixel * screen_pixels / view_scale


def compass_tick_angles(ticks_between_cardinals: int = 5) -> list[float]:
    """Return clockwise angles with north at -90°, including cardinal ticks."""
    sectors_per_quarter = ticks_between_cardinals + 1
    step = 90 / sectors_per_quarter
    return [-90 + index * step for index in range(sectors_per_quarter * 4)]


def compass_direction_angles() -> dict[str, float]:
    return {
        "N": -90,
        "NE": -45,
        "E": 0,
        "SE": 45,
        "S": 90,
        "SW": 135,
        "W": 180,
        "NW": 225,
    }


def circle_intersections(
    first_center: Point,
    first_radius: float,
    second_center: Point,
    second_radius: float,
) -> list[Point]:
    """Return the zero, one, or two intersections of two circles."""
    values = (
        first_center.x,
        first_center.y,
        first_radius,
        second_center.x,
        second_center.y,
        second_radius,
    )
    if not all(isfinite(value) for value in values):
        return []
    if first_radius <= 0 or second_radius <= 0:
        return []
    dx = second_center.x - first_center.x
    dy = second_center.y - first_center.y
    distance = hypot(dx, dy)
    tolerance = 1e-9 * max(first_radius, second_radius, distance, 1.0)
    if (
        distance <= tolerance
        or distance > first_radius + second_radius + tolerance
        or distance < abs(first_radius - second_radius) - tolerance
    ):
        return []

    along = (
        first_radius * first_radius
        - second_radius * second_radius
        + distance * distance
    ) / (2 * distance)
    height_squared = max(first_radius * first_radius - along * along, 0.0)
    base_x = first_center.x + along * dx / distance
    base_y = first_center.y + along * dy / distance
    if height_squared <= tolerance * tolerance:
        return [Point(base_x, base_y)]

    height = sqrt(height_squared)
    offset_x = -dy * height / distance
    offset_y = dx * height / distance
    return [
        Point(base_x + offset_x, base_y + offset_y),
        Point(base_x - offset_x, base_y - offset_y),
    ]


def common_circle_intersections(
    circles: list[tuple[Point, float]],
    tolerance_ratio: float = 0.01,
) -> list[Point]:
    """Return distinct pairwise intersections that agree with every circle."""
    if len(circles) < 2:
        return []
    candidates: list[Point] = []
    for first_index, first in enumerate(circles):
        for second in circles[first_index + 1 :]:
            for candidate in circle_intersections(
                first[0], first[1], second[0], second[1]
            ):
                agrees = all(
                    abs(
                        hypot(
                            candidate.x - center.x,
                            candidate.y - center.y,
                        )
                        - radius
                    )
                    <= max(radius * tolerance_ratio, 1e-6)
                    for center, radius in circles
                )
                if not agrees:
                    continue
                duplicate_tolerance = max(
                    max(radius for _center, radius in circles) * 1e-6,
                    1e-6,
                )
                if any(
                    hypot(candidate.x - existing.x, candidate.y - existing.y)
                    <= duplicate_tolerance
                    for existing in candidates
                ):
                    continue
                candidates.append(candidate)
    return candidates


def elevation_color(
    elevation_metres: float,
    minimum_metres: float,
    maximum_metres: float,
    midpoint_metres: float | None = None,
) -> QColor:
    """Blue-cyan-yellow-red diagnostic ramp with a configurable midpoint."""
    value = elevation_gradient_position(
        elevation_metres,
        minimum_metres,
        (
            (minimum_metres + maximum_metres) / 2.0
            if midpoint_metres is None
            else midpoint_metres
        ),
        maximum_metres,
    )
    stops = (
        (0.0, (40, 76, 190)),
        (0.35, (31, 190, 210)),
        (0.68, (239, 220, 73)),
        (1.0, (207, 54, 54)),
    )
    for (left_at, left), (right_at, right) in zip(stops, stops[1:]):
        if value <= right_at:
            fraction = (value - left_at) / (right_at - left_at)
            color = tuple(
                round(a + (b - a) * fraction) for a, b in zip(left, right)
            )
            return QColor(*color, 180)
    return QColor(*stops[-1][1], 180)


def elevation_gradient_position(
    elevation_metres: float,
    minimum_metres: float,
    midpoint_metres: float,
    maximum_metres: float,
) -> float:
    """Normalize elevation while pinning the sampled median to the ramp midpoint."""
    midpoint = min(max(midpoint_metres, minimum_metres), maximum_metres)
    if elevation_metres < midpoint:
        span = midpoint - minimum_metres
        value = 0.0 if span <= 0 else 0.5 * (
            elevation_metres - minimum_metres
        ) / span
    elif elevation_metres > midpoint:
        span = maximum_metres - midpoint
        value = 1.0 if span <= 0 else 0.5 + 0.5 * (
            elevation_metres - midpoint
        ) / span
    else:
        value = 0.5
    return min(max(value, 0.0), 1.0)


def elevation_gradient_anchors(
    field: ElevationField,
) -> tuple[float, float, float] | None:
    """Return outlier-resistant low, median, and high anchors for the ramp."""
    contrast_range = field.contrast_range_metres()
    midpoint = field.percentile_metres(0.5)
    if contrast_range is None or midpoint is None:
        return None
    minimum, maximum = contrast_range
    return minimum, midpoint, maximum


def elevation_overlay_pixmap(
    field: ElevationField,
    width: int,
    height: int,
    grid_size: int = 80,
) -> QPixmap:
    """Render an outlier-resistant gradient centered on the map's median."""
    anchors = elevation_gradient_anchors(field)
    if anchors is None or width <= 0 or height <= 0:
        return QPixmap()
    minimum, midpoint, maximum = anchors
    grid_width = max(2, grid_size)
    grid_height = max(2, round(grid_size * height / width))
    image = QImage(grid_width, grid_height, QImage.Format.Format_ARGB32)
    for y in range(grid_height):
        pixel_y = y * height / max(grid_height - 1, 1)
        for x in range(grid_width):
            pixel_x = x * width / max(grid_width - 1, 1)
            elevation = field.elevation_at(Point(pixel_x, pixel_y))
            color = (
                elevation_color(elevation, minimum, maximum, midpoint)
                if elevation is not None
                else QColor(0, 0, 0, 0)
            )
            image.setPixelColor(x, y, color)
    return QPixmap.fromImage(image).scaled(
        width,
        height,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


class CircleEntity(QGraphicsEllipseItem):
    """A fire-mission endpoint with explicit movement/removal policy."""

    def __init__(
        self,
        position: QPointF,
        changed: Callable[["CircleEntity", Any, Any], Any],
        remove: Callable[["CircleEntity"], None],
        color: QColor,
        label: str,
        role: str,
        *,
        movable: bool,
        removable: bool,
    ) -> None:
        radius = 10
        super().__init__(-radius, -radius, radius * 2, radius * 2)
        self._ready = False
        self._changed = changed
        self._remove = remove
        self._movable = movable
        self._removable = removable
        self.label = label
        self.role = role
        self.label_color = (
            QColor("#fff0e5") if role == "target" else QColor("#211b0e")
        )
        pen = QPen(QColor("#2b2412"), 2)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setBrush(QColor(color))
        self.setCursor(
            Qt.CursorShape.OpenHandCursor if movable else Qt.CursorShape.ArrowCursor
        )
        self.setZValue(2)
        flags = (
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
            | QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations
        )
        if movable:
            flags |= (
                QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            )
        self.setFlags(flags)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton)
        self.setToolTip(
            "Cannon position — use CLEAR to replace"
            if not movable
            else "Position marker — drag to adjust"
        )
        self.setPos(position)
        self._ready = True

    def paint(self, painter: QPainter, option: Any, widget: Any = None) -> None:
        super().paint(painter, option, widget)
        font = QFont("Arial", 9)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(self.label_color)
        bounds = QFontMetricsF(font).tightBoundingRect(self.label)
        center = self.rect().center()
        origin = QPointF(
            center.x() - bounds.center().x(),
            center.y() - bounds.center().y(),
        )
        painter.drawText(origin, self.label)

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
        if self._ready:
            return self._changed(self, change, value)
        return super().itemChange(change, value)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            if self._removable:
                self._remove(self)
            event.accept()
            return
        if self._movable:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._movable:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)


class EstimationHitMarker(QGraphicsEllipseItem):
    """A recorded shot marker that can remove its associated range circle."""

    def __init__(
        self,
        position: QPointF,
        color: QColor,
        remove: Callable[[], None],
    ) -> None:
        super().__init__(QRectF(-6, -6, 12, 12))
        self._remove = remove
        self.setPen(QPen(QColor("#101820"), 2))
        self.setBrush(QBrush(color))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self.setAcceptedMouseButtons(Qt.MouseButton.RightButton)
        self.setPos(position)
        self.setZValue(5)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            self._remove()
            event.accept()
            return
        super().mousePressEvent(event)


class SavedTargetMarker(QGraphicsEllipseItem):
    """A compact selectable marker for a user-saved fire target."""

    def __init__(
        self,
        target: FireTarget,
        selected: bool,
        select: Callable[[int], None],
        move: Callable[[int, QPointF], None],
        remove: Callable[[int], None],
    ) -> None:
        radius = 12 if selected else 10
        super().__init__(-radius, -radius, radius * 2, radius * 2)
        self.target_id = target.identifier
        self.label = f"T{target.identifier}"
        self._select = select
        self._move = move
        self._remove = remove
        self._press_position: QPointF | None = None
        pen = QPen(QColor("#fff0d2") if selected else QColor("#74474a"), 2)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setBrush(
            QBrush(
                QColor(159, 47, 56, 235)
                if selected
                else QColor(72, 74, 68, 225)
            )
        )
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations
            | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        )
        self.setAcceptedMouseButtons(
            Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton
        )
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setPos(target.target.x, target.target.y)
        self.setZValue(7.0)
        self.setToolTip(
            f"{self.label} — drag to move; left-click to "
            f"{'collapse' if selected else 'select'}; right-click to remove"
        )

    def paint(self, painter: QPainter, option: Any, widget: Any = None) -> None:
        super().paint(painter, option, widget)
        font = QFont("Arial", 7)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#fff4db"))
        bounds = QFontMetricsF(font).tightBoundingRect(self.label)
        center = self.rect().center()
        painter.drawText(
            QPointF(
                center.x() - bounds.center().x(),
                center.y() - bounds.center().y(),
            ),
            self.label,
        )

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            self._remove(self.target_id)
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_position = QPointF(self.scenePos())
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        press_position = self._press_position
        self._press_position = None
        if press_position is None:
            return
        current_position = QPointF(self.scenePos())
        if (current_position - press_position).manhattanLength() > 1:
            self._move(self.target_id, current_position)
        else:
            self._select(self.target_id)


class MapView(QGraphicsView):
    """Zoomable map with fire-mission endpoints and live coordinate reporting."""

    def __init__(
        self,
        point_clicked: Callable[[QPointF], None],
        points_changed: Callable[[list[QPointF]], None] | None = None,
        position_hovered: Callable[[QPointF | None], None] | None = None,
        estimation_fuze_requested: Callable[[], float | None] | None = None,
        estimation_range_for_fuze: Callable[[float], float] | None = None,
        saved_target_selected: Callable[[int], None] | None = None,
        saved_target_moved: Callable[[int, QPointF], None] | None = None,
        saved_target_removed: Callable[[int], None] | None = None,
    ) -> None:
        super().__init__()
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._source_pixmap = QPixmap()
        self._map_style = "Parchment"
        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._elevation_item: QGraphicsPixmapItem | None = None
        self._elevation_field: ElevationField | None = None
        self._elevation_overlay_visible = False
        self._markers: list[CircleEntity] = []
        self._retained_target: CircleEntity | None = None
        self._location_items: list[QGraphicsEllipseItem | QGraphicsRectItem] = []
        self._line = None
        self._rings = []
        self._ring_halos = []
        self._ring_labels: list[QGraphicsSimpleTextItem] = []
        self._ring_label_backgrounds: list[QGraphicsRectItem] = []
        self._compass_items = []
        self._target_solution_label: QGraphicsSimpleTextItem | None = None
        self._target_solution_background: QGraphicsRectItem | None = None
        self._trajectory_items: list[QGraphicsItem] = []
        self._estimation_hits: list[tuple[QPointF, float]] = []
        self._estimation_fuzes: list[float | None] = []
        self._estimation_items: list[QGraphicsItem] = []
        self._estimation_candidates: list[QPointF] = []
        self._target_history_items: list[QGraphicsItem] = []
        self._saved_target_markers: dict[int, SavedTargetMarker] = {}
        self._range_transform: AffineCalibration | None = None
        self._yards_per_pixel: float | None = None
        self._point_clicked = point_clicked
        self._points_changed = points_changed
        self._position_hovered = position_hovered
        self._estimation_fuze_requested = (
            estimation_fuze_requested or self._prompt_for_estimation_fuze
        )
        self._estimation_range_for_fuze = estimation_range_for_fuze
        self._saved_target_selected = saved_target_selected or (lambda _target_id: None)
        self._saved_target_moved = saved_target_moved or (
            lambda _target_id, _point: None
        )
        self._saved_target_removed = saved_target_removed or (lambda _target_id: None)
        self._press_position: QPoint | None = None
        self._middle_press_position: QPoint | None = None
        self._press_on_marker = False
        self._interaction_enabled = True
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.setBackgroundBrush(QColor("#121811"))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setToolTip(
            "Left-click once to place the gun; each later click saves a new target. "
            "Middle-click a shot impact to record a position-estimate circle "
            "from its observed fuze time."
        )

    def set_map(self, pixmap: QPixmap) -> None:
        self._scene.clear()
        self._markers.clear()
        self._retained_target = None
        self._location_items.clear()
        self._line = None
        self._rings.clear()
        self._ring_halos.clear()
        self._ring_labels.clear()
        self._ring_label_backgrounds.clear()
        self._compass_items.clear()
        self._target_solution_label = None
        self._target_solution_background = None
        self._trajectory_items.clear()
        self._estimation_hits.clear()
        self._estimation_fuzes.clear()
        self._estimation_items.clear()
        self._estimation_candidates.clear()
        self._target_history_items.clear()
        self._saved_target_markers.clear()
        self._source_pixmap = pixmap
        self._pixmap_item = self._scene.addPixmap(styled_map_pixmap(pixmap, self._map_style))
        self._elevation_item = None
        self._scene.setSceneRect(self._pixmap_item.boundingRect())
        self.resetTransform()
        self.fitInView(self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

    def clear_map(self) -> None:
        self._scene.clear()
        self._markers.clear()
        self._retained_target = None
        self._location_items.clear()
        self._line = None
        self._rings.clear()
        self._ring_halos.clear()
        self._ring_labels.clear()
        self._ring_label_backgrounds.clear()
        self._compass_items.clear()
        self._target_solution_label = None
        self._target_solution_background = None
        self._trajectory_items.clear()
        self._estimation_hits.clear()
        self._estimation_fuzes.clear()
        self._estimation_items.clear()
        self._estimation_candidates.clear()
        self._target_history_items.clear()
        self._saved_target_markers.clear()
        self._pixmap_item = None
        self._elevation_item = None
        self._elevation_field = None
        self._source_pixmap = QPixmap()
        self.resetTransform()

    def set_map_style(self, style: str) -> None:
        self._map_style = style
        if self._pixmap_item is not None and not self._source_pixmap.isNull():
            self._pixmap_item.setPixmap(styled_map_pixmap(self._source_pixmap, style))
            self._scene.setSceneRect(self._pixmap_item.boundingRect())
            self.viewport().update()

    def fit_map(self) -> None:
        if self._pixmap_item is None:
            return
        self.resetTransform()
        self.fitInView(self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
        self._sync_geometry(notify=False)
        self.viewport().update()

    def set_location_markers(self, locations: list[MapLocation]) -> None:
        for item in self._location_items:
            self._scene.removeItem(item)
        self._location_items.clear()
        for location in locations:
            color_key = location.kind
            if location.kind == "spawn" and location.faction:
                color_key = f"{location.faction.casefold()}_spawn"
            color = LOCATION_COLORS.get(color_key, LOCATION_COLORS["spawn"])
            radius = 3.5 if location.kind == "objective" else 3 if location.kind == "battery" else 2.5
            shape = QGraphicsRectItem if location.kind == "gun_spawn" else QGraphicsEllipseItem
            item = shape(-radius, -radius, radius * 2, radius * 2)
            outline = QPen(QColor("#17191c"), 1)
            outline.setCosmetic(True)
            item.setPen(outline)
            item.setBrush(QBrush(color))
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
            item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            label = (
                "Artillery crew spawn reference"
                if location.kind == "battery"
                else "Gun starting position (before movement)"
                if location.kind == "gun_spawn"
                else location.kind.title()
            )
            if location.faction:
                label = f"{location.faction} {label}"
            details = [label, location.name]
            if location.elevation_metres is not None:
                elevation_label = "Entity origin elevation" if location.kind == "gun_spawn" else "Elevation"
                details.append(f"{elevation_label}: {location.elevation_metres:.2f} m")
            if location.world_x is not None and location.world_y is not None:
                details.append(
                    f"World: {location.world_x:.2f}, {location.world_y:.2f} m"
                )
            details.append(f"Pixel: {location.pixel_x:.1f}, {location.pixel_y:.1f}")
            item.setToolTip("\n".join(details))
            item.setPos(location.pixel_x, location.pixel_y)
            item.setZValue(6)
            self._scene.addItem(item)
            self._location_items.append(item)

    def set_target_history(
        self,
        targets: list[FireTarget],
        selected_target_id: int | None,
        active_gun: Point | None,
    ) -> None:
        """Render saved targets and only the selected target's spotted impacts."""

        for item in self._target_history_items:
            if item.scene() is self._scene:
                self._scene.removeItem(item)
        self._target_history_items.clear()
        self._saved_target_markers.clear()
        if self._pixmap_item is None:
            return

        selected_target: FireTarget | None = None
        for target in targets:
            selected = target.identifier == selected_target_id
            marker = SavedTargetMarker(
                target,
                selected,
                self._saved_target_selected,
                self._saved_target_moved,
                self._saved_target_removed,
            )
            self._scene.addItem(marker)
            self._target_history_items.append(marker)
            self._saved_target_markers[target.identifier] = marker
            if selected:
                selected_target = target

        if (
            selected_target is None
            or active_gun is None
            or self._range_transform is None
        ):
            return
        for index, shot in enumerate(selected_target.shots, start=1):
            try:
                impact = observed_impact_point(
                    self._range_transform,
                    active_gun,
                    selected_target.target,
                    shot,
                )
            except ValueError:
                continue
            marker = self._scene.addEllipse(
                QRectF(-6, -6, 12, 12),
                QPen(QColor("#27190d"), 2),
                QBrush(QColor("#ff9d3d")),
            )
            marker.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations
            )
            marker.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            marker.setPos(impact.x, impact.y)
            marker.setZValue(6.6)
            marker.setToolTip(
                f"T{selected_target.identifier} shot {index}: "
                f"{correction_summary(shot)}"
            )
            label = self._scene.addSimpleText(f"S{index}")
            font = QFont("Consolas", 9)
            font.setWeight(QFont.Weight.DemiBold)
            label.setFont(font)
            label.setBrush(QColor("#fff0d2"))
            label.setPen(QPen(QColor("#17100a"), 1))
            label.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations
            )
            label.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            label.setPos(impact.x + 8, impact.y - 10)
            label.setZValue(6.7)
            label.setToolTip(marker.toolTip())
            self._target_history_items.extend((marker, label))

    def set_elevation_field(self, field: ElevationField | None) -> None:
        self._elevation_field = field
        if self._elevation_item is not None:
            self._scene.removeItem(self._elevation_item)
            self._elevation_item = None
        if self._elevation_overlay_visible:
            self._ensure_elevation_item()

    def _ensure_elevation_item(self) -> None:
        if (
            self._elevation_item is not None
            or self._elevation_field is None
            or self._pixmap_item is None
            or self._source_pixmap.isNull()
        ):
            return
        overlay = elevation_overlay_pixmap(
            self._elevation_field,
            self._source_pixmap.width(),
            self._source_pixmap.height(),
        )
        if overlay.isNull():
            return
        self._elevation_item = self._scene.addPixmap(overlay)
        self._elevation_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self._elevation_item.setOpacity(0.78)
        self._elevation_item.setZValue(0.2)
        self._elevation_item.setVisible(self._elevation_overlay_visible)

    def set_elevation_overlay_visible(self, visible: bool) -> None:
        self._elevation_overlay_visible = visible
        if visible:
            self._ensure_elevation_item()
        if self._elevation_item is not None:
            self._elevation_item.setVisible(visible)

    def set_interaction_enabled(self, enabled: bool) -> None:
        self._interaction_enabled = enabled
        self.clear_points()

    def set_range_scale(self, yards_per_pixel: float | None) -> None:
        """Compatibility entry point for isotropically calibrated legacy maps."""
        self._yards_per_pixel = yards_per_pixel
        metres_per_pixel = yards_per_pixel / METRES_TO_YARDS if yards_per_pixel else None
        self._range_transform = (
            AffineCalibration(metres_per_pixel, 0, 0, metres_per_pixel)
            if metres_per_pixel and metres_per_pixel > 0
            else None
        )
        self._sync_geometry(notify=False)

    def set_range_transform(self, transform: AffineCalibration | None) -> None:
        self._range_transform = transform
        self._yards_per_pixel = transform.mean_yards_per_pixel if transform else None
        self._sync_geometry(notify=False)
        self._draw_estimation_overlay()

    def clear_points(self) -> None:
        self._clear_fire_mission_points()
        self.clear_estimation_hits()

    def _clear_fire_mission_points(self) -> None:
        for marker in self._markers:
            self._scene.removeItem(marker)
        self._markers.clear()
        self._retained_target = None
        if self._line is not None:
            self._scene.removeItem(self._line)
            self._line = None
        self.clear_target_solution()
        self.clear_trajectory_overlay()
        self._clear_range_rings()

    def clear_target_solution(self) -> None:
        if self._target_solution_label is not None:
            self._scene.removeItem(self._target_solution_label)
            self._target_solution_label = None
        if self._target_solution_background is not None:
            self._scene.removeItem(self._target_solution_background)
            self._target_solution_background = None

    def clear_trajectory_overlay(self) -> None:
        for item in self._trajectory_items:
            self._scene.removeItem(item)
        self._trajectory_items.clear()
        if self._line is not None:
            self._line.setVisible(True)

    def set_trajectory_overlay(
        self,
        target_range_yards: float,
        obstruction_range_yards: float | None,
        impact_range_yards: float | None,
    ) -> None:
        self.clear_trajectory_overlay()
        if len(self._markers) != 2 or target_range_yards <= 0:
            return
        gun = self._markers[0].scenePos()
        target = self._markers[1].scenePos()
        delta = target - gun

        def route_point(distance_yards: float) -> QPointF:
            fraction = distance_yards / target_range_yards
            return QPointF(
                gun.x() + delta.x() * fraction,
                gun.y() + delta.y() * fraction,
            )

        if obstruction_range_yards is not None:
            obstruction = route_point(obstruction_range_yards)
            if self._line is not None:
                self._line.setVisible(False)
            blocked_line = self._scene.addLine(
                gun.x(),
                gun.y(),
                obstruction.x(),
                obstruction.y(),
                QPen(QColor("#d94149"), 2.5, Qt.PenStyle.SolidLine),
            )
            obstruction_marker = self._scene.addEllipse(
                QRectF(-5, -5, 10, 10),
                QPen(QColor("#ffd0c8"), 1.5),
                QBrush(QColor("#d94149")),
            )
            obstruction_marker.setPos(obstruction)
            self._trajectory_items.extend((blocked_line, obstruction_marker))
            continuation_end = (
                route_point(impact_range_yards)
                if impact_range_yards is not None
                else target
            )
            skipped_line = self._scene.addLine(
                obstruction.x(),
                obstruction.y(),
                continuation_end.x(),
                continuation_end.y(),
                QPen(QColor("#d94149"), 2, Qt.PenStyle.DashLine),
            )
            self._trajectory_items.append(skipped_line)

        if impact_range_yards is not None:
            impact = route_point(impact_range_yards)
            if obstruction_range_yards is None:
                continuation = self._scene.addLine(
                    target.x(),
                    target.y(),
                    impact.x(),
                    impact.y(),
                    QPen(QColor("#d94149"), 2, Qt.PenStyle.DashLine),
                )
                self._trajectory_items.append(continuation)
            impact_marker = self._scene.addEllipse(
                QRectF(-5, -5, 10, 10),
                QPen(QColor("#ffc9c9"), 1.5),
                QBrush(QColor("#d94149")),
            )
            impact_marker.setPos(impact)
            self._trajectory_items.append(impact_marker)

        for item in self._trajectory_items:
            item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            item.setZValue(1.5)

    def set_target_solution(
        self,
        slant_yards: float | None,
        fuze_text: str,
        elevation_text: str,
    ) -> None:
        if len(self._markers) != 2 or slant_yards is None:
            self.clear_target_solution()
            return
        text = (
            f"SLANT  {slant_yards:,.2f} yd\n"
            f"FUZE   {fuze_text}\n"
            f"ELEV   {elevation_text}"
        )
        if self._target_solution_label is None:
            self._target_solution_label = self._scene.addSimpleText(text)
            font = QFont("Consolas", 11)
            font.setWeight(QFont.Weight.DemiBold)
            self._target_solution_label.setFont(font)
            self._target_solution_label.setBrush(QColor("#fff7dc"))
            self._target_solution_label.setPen(QPen(Qt.PenStyle.NoPen))
            self._target_solution_label.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations
            )
            self._target_solution_label.setAcceptedMouseButtons(
                Qt.MouseButton.NoButton
            )
            self._target_solution_label.setZValue(8.1)
            self._target_solution_background = self._scene.addRect(
                QRectF(),
                QPen(QColor("#e34f4f"), 1.4),
                QBrush(QColor(17, 22, 16, 160)),
            )
            self._target_solution_background.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations
            )
            self._target_solution_background.setAcceptedMouseButtons(
                Qt.MouseButton.NoButton
            )
            self._target_solution_background.setZValue(8.0)
        else:
            self._target_solution_label.setText(text)
        assert self._target_solution_background is not None
        self._target_solution_background.setRect(
            self._target_solution_label.boundingRect().adjusted(-7, -5, 7, 5)
        )
        self._position_target_solution()

    def _position_target_solution(self) -> None:
        if (
            len(self._markers) != 2
            or self._target_solution_label is None
            or self._target_solution_background is None
        ):
            return
        target = self._markers[1].scenePos()
        background = self._target_solution_background.rect()
        position = QPointF(
            target.x() + 26,
            target.y() - background.height() / 2,
        )
        self._target_solution_label.setPos(position)
        self._target_solution_background.setPos(position)

    def set_points(self, points: list[QPointF]) -> None:
        self._clear_fire_mission_points()
        if not self._pixmap_item:
            return
        colors = (QColor("#f2c94c"), QColor("#9f2f38"))
        labels = ("G", "T")
        roles = ("gun", "target")
        for index, point in enumerate(points):
            marker = CircleEntity(
                point,
                self._entity_changed,
                self._remove_entity,
                colors[min(index, len(colors) - 1)],
                labels[min(index, len(labels) - 1)],
                roles[min(index, len(roles) - 1)],
                movable=True,
                removable=True,
            )
            marker.setToolTip(
                "Cannon position — drag or right-click to remove"
                if index == 0
                else "Target position — drag to adjust or right-click to remove"
            )
            self._scene.addItem(marker)
            self._markers.append(marker)
        self._sync_geometry(notify=False)

    def add_estimation_hit(
        self,
        point: QPointF,
        radius_yards: float,
        fuze_seconds: float | None = None,
    ) -> bool:
        """Record a shot impact with its internally estimated range."""
        if self._range_transform is None:
            return False
        if not isfinite(radius_yards) or radius_yards <= 0:
            return False
        if fuze_seconds is not None and (
            not isfinite(fuze_seconds) or fuze_seconds <= 0
        ):
            return False
        self._estimation_hits.append((QPointF(point), radius_yards))
        self._estimation_fuzes.append(fuze_seconds)
        self._draw_estimation_overlay()
        return True

    def _prompt_for_estimation_fuze(self) -> float | None:
        value, accepted = QInputDialog.getDouble(
            self,
            "Record observed shot fuze",
            "Fuze / flight time (seconds; range estimated at 0°):",
            1.0,
            0.001,
            3_600.0,
            3,
        )
        return value if accepted else None

    def _request_estimation_hit(self, point: QPointF) -> bool:
        if (
            self._range_transform is None
            or self._estimation_range_for_fuze is None
        ):
            return False
        fuze_seconds = self._estimation_fuze_requested()
        if fuze_seconds is None:
            return False
        try:
            radius_yards = self._estimation_range_for_fuze(fuze_seconds)
        except ValueError:
            return False
        return self.add_estimation_hit(point, radius_yards, fuze_seconds)

    def clear_estimation_hits(self) -> None:
        self._estimation_hits.clear()
        self._estimation_fuzes.clear()
        self._draw_estimation_overlay()

    def _remove_estimation_hit(self, index: int) -> None:
        if 0 <= index < len(self._estimation_hits):
            del self._estimation_hits[index]
            del self._estimation_fuzes[index]
            self._draw_estimation_overlay()

    def _draw_estimation_overlay(self) -> None:
        for item in self._estimation_items:
            if item.scene() is self._scene:
                self._scene.removeItem(item)
        self._estimation_items.clear()
        self._estimation_candidates.clear()
        if self._range_transform is None:
            return

        colors = (
            QColor("#35c9ff"),
            QColor("#ff9d3d"),
            QColor("#d76bff"),
            QColor("#ffe14f"),
            QColor("#67e480"),
        )
        for index, (center, radius_yards) in enumerate(self._estimation_hits):
            fuze_seconds = self._estimation_fuzes[index]
            estimate_text = (
                f"{fuze_seconds:.3f} s fuze"
                if fuze_seconds is not None
                else "range-derived"
            )
            color = colors[index % len(colors)]
            halo_pen = QPen(QColor(10, 16, 20, 220), 5)
            halo_pen.setCosmetic(True)
            halo_pen.setStyle(Qt.PenStyle.DashLine)
            ring_pen = QPen(color, 2.4)
            ring_pen.setCosmetic(True)
            ring_pen.setStyle(Qt.PenStyle.DashLine)
            path = self._range_ring_path(center, radius_yards)
            for path_item in (
                self._scene.addPath(path, halo_pen),
                self._scene.addPath(path, ring_pen),
            ):
                path_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                path_item.setZValue(4.0)
                path_item.setToolTip(
                    f"Shot {index + 1}: {estimate_text} position estimate"
                )
                self._estimation_items.append(path_item)

            marker = EstimationHitMarker(
                center,
                color,
                lambda hit_index=index: self._remove_estimation_hit(hit_index),
            )
            self._scene.addItem(marker)
            marker.setToolTip(
                f"Recorded shot {index + 1} — {estimate_text} — "
                "right-click to remove"
            )
            self._estimation_items.append(marker)

        if len(self._estimation_hits) < 2:
            return
        world_circles: list[tuple[Point, float]] = []
        for center, radius_yards in self._estimation_hits:
            world_circles.append(
                (
                    self._range_transform.world_delta(center.x(), center.y()),
                    radius_yards / METRES_TO_YARDS,
                )
            )
        intersections = common_circle_intersections(world_circles)
        bounds = self._pixmap_item.sceneBoundingRect() if self._pixmap_item else QRectF()
        for intersection in intersections:
            pixel = self._range_transform.pixel_delta_for_world_units(
                intersection.x, intersection.y
            )
            candidate = QPointF(pixel.x, pixel.y)
            if not bounds.contains(candidate):
                continue
            self._estimation_candidates.append(candidate)
            candidate_item = self._scene.addEllipse(
                QRectF(-8, -8, 16, 16),
                QPen(QColor("#ffffff"), 2.5),
                QBrush(QColor("#2de2a6")),
            )
            candidate_item.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations
            )
            candidate_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            candidate_item.setPos(candidate)
            candidate_item.setZValue(6)
            candidate_item.setToolTip(
                f"Possible gun position matching all {len(self._estimation_hits)} "
                "recorded shots"
            )
            self._estimation_items.append(candidate_item)

    def entity_points(self) -> list[QPointF]:
        if self._retained_target is not None:
            return []
        return [marker.scenePos() for marker in self._markers]

    def retained_target_point(self) -> QPointF | None:
        if self._retained_target is None:
            return None
        return QPointF(self._retained_target.scenePos())

    def _entity_changed(self, marker: CircleEntity, change: Any, value: Any) -> Any:
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self._pixmap_item:
            bounds = self._pixmap_item.sceneBoundingRect()
            point = value
            return QPointF(
                min(max(point.x(), bounds.left()), bounds.right()),
                min(max(point.y(), bounds.top()), bounds.bottom()),
            )
        result = QGraphicsEllipseItem.itemChange(marker, change, value)
        if (
            change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged
            and marker in self._markers
        ):
            self._sync_geometry(notify=True)
        return result

    def _remove_entity(self, marker: CircleEntity) -> None:
        if marker not in self._markers:
            return
        if marker.role == "gun" and len(self._markers) == 2:
            self._retained_target = self._markers[1]
        self._markers.remove(marker)
        self._scene.removeItem(marker)
        if marker is self._retained_target:
            self._retained_target = None
        self.clear_target_solution()
        self.clear_trajectory_overlay()
        self._sync_geometry(notify=True)

    def _sync_geometry(self, notify: bool) -> None:
        points = self.entity_points()
        if len(points) == 2:
            if self._line is None:
                pen = QPen(QColor("#a83b42"), 2)
                pen.setCosmetic(True)
                self._line = self._scene.addLine(0, 0, 0, 0, pen)
                self._line.setZValue(1)
            self._line.setLine(
                points[0].x(), points[0].y(), points[1].x(), points[1].y()
            )
        elif self._line is not None:
            self._scene.removeItem(self._line)
            self._line = None
        # The fire mission uses a single uncluttered gun-to-target sight line.
        # Range, elevation and fuze are presented together in the control panel.
        self._clear_range_rings()
        self._position_target_solution()
        if notify and self._points_changed is not None:
            self._points_changed(points)

    def _clear_range_rings(self) -> None:
        for ring in self._rings:
            self._scene.removeItem(ring)
        for halo in self._ring_halos:
            self._scene.removeItem(halo)
        for label in self._ring_labels:
            self._scene.removeItem(label)
        for background in self._ring_label_backgrounds:
            self._scene.removeItem(background)
        for item in self._compass_items:
            self._scene.removeItem(item)
        self._rings.clear()
        self._ring_halos.clear()
        self._ring_labels.clear()
        self._ring_label_backgrounds.clear()
        self._compass_items.clear()

    def _draw_range_rings(self, points: list[QPointF]) -> None:
        self._clear_range_rings()
        if len(points) != 2 or self._range_transform is None:
            return
        dx = points[1].x() - points[0].x()
        dy = points[1].y() - points[0].y()
        pixel_distance = hypot(dx, dy)
        if pixel_distance <= 0:
            return
        target_yards = self._range_transform.distance_yards(
            Point(points[0].x(), points[0].y()),
            Point(points[1].x(), points[1].y()),
        )
        ranges = [float(value) for value in range(50, int(target_yards // 50) * 50 + 1, 50)]
        if not ranges or not isclose(ranges[-1], target_yards, abs_tol=0.01):
            ranges.append(target_yards)
        for yards in ranges:
            final_ring = isclose(yards, target_yards, abs_tol=0.01)
            hundred_yard_ring = not final_ring and isclose(yards % 100, 0, abs_tol=0.01)
            if final_ring:
                color = QColor("#ff3d9e")
                line_width = 3
            elif hundred_yard_ring:
                color = QColor("#7cff4f")
                line_width = 2.6
            else:
                color = QColor(245, 247, 255, 225)
                line_width = 1.8
            pen = QPen(color, line_width)
            pen.setCosmetic(True)
            halo_width = 5 if final_ring else 4.6 if hundred_yard_ring else 3.8
            halo_pen = QPen(QColor(16, 18, 22, 225), halo_width)
            halo_pen.setCosmetic(True)
            if not final_ring and not hundred_yard_ring:
                pen.setStyle(Qt.PenStyle.DashLine)
                halo_pen.setStyle(Qt.PenStyle.DashLine)
            path = self._range_ring_path(points[0], yards)
            halo = self._scene.addPath(path, halo_pen)
            halo.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            halo.setZValue(0.45)
            self._ring_halos.append(halo)
            ring = self._scene.addPath(path, pen)
            ring.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            ring.setZValue(0.5)
            self._rings.append(ring)

            if not final_ring:
                continue
            self._draw_compass(points[0], yards)
            label_text = f"{yards:,.1f} yd"
            label = self._scene.addSimpleText(label_text)
            font = QFont("Segoe UI", 18)
            font.setWeight(QFont.Weight.Medium)
            label.setFont(font)
            label.setBrush(QColor("#ffffff"))
            label.setPen(QPen(Qt.PenStyle.NoPen))
            label.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
            label.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            label.setZValue(3)
            label_x = points[1].x() + 12
            label_y = points[1].y() - 34
            label.setPos(label_x, label_y)
            background = self._scene.addRect(
                label.boundingRect().adjusted(-7, -4, 7, 4),
                QPen(QColor("#ffffff"), 1.4),
                QBrush(QColor("#b51669")),
            )
            background.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
            background.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            background.setPos(label_x, label_y)
            background.setZValue(2.9)
            self._ring_label_backgrounds.append(background)
            self._ring_labels.append(label)

    def _range_ring_path(self, center: QPointF, radius_yards: float) -> QPainterPath:
        path = QPainterPath()
        radius_world_units = radius_yards / METRES_TO_YARDS
        for index in range(121):
            angle = radians(index * 3)
            delta = self._range_transform.pixel_delta_for_world_units(
                cos(angle) * radius_world_units,
                sin(angle) * radius_world_units,
            )
            point = QPointF(center.x() + delta.x, center.y() + delta.y)
            if index == 0:
                path.moveTo(point)
            else:
                path.lineTo(point)
        path.closeSubpath()
        return path

    def _pixel_direction(self, bearing_degrees: float, radius_yards: float) -> Point:
        bearing = radians(bearing_degrees)
        radius_world_units = radius_yards / METRES_TO_YARDS
        return self._range_transform.pixel_delta_for_world_units(
            sin(bearing) * radius_world_units,
            cos(bearing) * radius_world_units,
        )

    def _draw_compass(self, center: QPointF, radius_yards: float) -> None:
        view_scale = max(abs(self.transform().m11()), 0.001)
        angles = compass_tick_angles(5)
        cardinals = {0: "N", 6: "E", 12: "S", 18: "W"}
        for index, angle_degrees in enumerate(angles):
            cardinal = index in cardinals
            direction = self._pixel_direction(angle_degrees, radius_yards)
            direction_length = max(hypot(direction.x, direction.y), 1e-12)
            direction_x = direction.x / direction_length
            direction_y = direction.y / direction_length
            tick_length = (14 if cardinal else 7) / view_scale
            outer_x = center.x() + direction.x
            outer_y = center.y() + direction.y
            inner_x = outer_x - direction_x * tick_length
            inner_y = outer_y - direction_y * tick_length

            halo_pen = QPen(QColor(16, 18, 22, 235), 5 if cardinal else 3.8)
            halo_pen.setCosmetic(True)
            halo = self._scene.addLine(inner_x, inner_y, outer_x, outer_y, halo_pen)
            halo.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            halo.setZValue(1.8)
            self._compass_items.append(halo)

            tick_pen = QPen(QColor("#ffffff") if cardinal else QColor("#ff3d9e"), 3 if cardinal else 2)
            tick_pen.setCosmetic(True)
            tick = self._scene.addLine(inner_x, inner_y, outer_x, outer_y, tick_pen)
            tick.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            tick.setZValue(1.9)
            self._compass_items.append(tick)

            if not cardinal:
                continue
            self._add_compass_label(
                center, radius_yards, angle_degrees, cardinals[index], 12, QFont.Weight.DemiBold
            )

        for direction in ("NE", "SE", "SW", "NW"):
            self._add_compass_label(
                center,
                radius_yards,
                compass_direction_angles()[direction],
                direction,
                10,
                QFont.Weight.Medium,
            )

    def _add_compass_label(
        self,
        center: QPointF,
        radius_yards: float,
        angle_degrees: float,
        text: str,
        font_size: int,
        weight: QFont.Weight,
    ) -> None:
        view_scale = max(abs(self.transform().m11()), 0.001)
        direction = self._pixel_direction(angle_degrees, radius_yards)
        direction_length = max(hypot(direction.x, direction.y), 1e-12)
        unit_x = direction.x / direction_length
        unit_y = direction.y / direction_length
        label = self._scene.addSimpleText(text)
        font = QFont("Segoe UI", font_size)
        font.setWeight(weight)
        label.setFont(font)
        label.setBrush(QColor("#b51669"))
        label.setPen(QPen(Qt.PenStyle.NoPen))
        label.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        label.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        label.setZValue(3)
        anchor_x = center.x() + direction.x + unit_x * 18 / view_scale
        anchor_y = center.y() + direction.y + unit_y * 18 / view_scale
        bounds = label.boundingRect()
        label_x = anchor_x - bounds.width() / (2 * view_scale)
        label_y = anchor_y - bounds.height() / (2 * view_scale)
        label.setPos(label_x, label_y)
        background = self._scene.addRect(
            bounds.adjusted(-4, -2, 4, 2),
            QPen(QColor("#b51669"), 1.2),
            QBrush(QColor("#f7f4ea")),
        )
        background.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        background.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        background.setPos(label_x, label_y)
        background.setZValue(2.9)
        self._compass_items.extend((background, label))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_position = event.position().toPoint()
            self._press_on_marker = isinstance(
                self.itemAt(self._press_position),
                (CircleEntity, SavedTargetMarker),
            )
        elif event.button() == Qt.MouseButton.MiddleButton:
            self._middle_press_position = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        super().mouseMoveEvent(event)
        if self._position_hovered is None:
            return
        scene_point = self.mapToScene(event.position().toPoint())
        if self._pixmap_item is None:
            self._position_hovered(None)
            return
        local_point = self._pixmap_item.mapFromScene(scene_point)
        self._position_hovered(
            scene_point if self._pixmap_item.contains(local_point) else None
        )

    def leaveEvent(self, event) -> None:
        if self._position_hovered is not None:
            self._position_hovered(None)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        release_position = event.position().toPoint()
        was_click = (
            event.button() == Qt.MouseButton.LeftButton
            and self._press_position is not None
            and not self._press_on_marker
            and (release_position - self._press_position).manhattanLength() <= 4
        )
        was_middle_click = (
            event.button() == Qt.MouseButton.MiddleButton
            and self._middle_press_position is not None
            and (release_position - self._middle_press_position).manhattanLength() <= 4
        )
        self._press_position = None
        self._middle_press_position = None
        self._press_on_marker = False
        super().mouseReleaseEvent(event)
        if (was_click or was_middle_click) and self._pixmap_item and self._interaction_enabled:
            scene_point = self.mapToScene(release_position)
            local_point = self._pixmap_item.mapFromScene(scene_point)
            if self._pixmap_item.contains(local_point):
                if was_middle_click:
                    self._request_estimation_hit(scene_point)
                else:
                    self._point_clicked(scene_point)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if not self._pixmap_item:
            return
        factor = 1.2 if event.angleDelta().y() > 0 else 1 / 1.2
        if 0.03 <= self.transform().m11() * factor <= 50:
            self.scale(factor, factor)
            self._sync_geometry(notify=False)
            self.viewport().update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        self._paint_ruler()

    def _paint_ruler(self) -> None:
        if not self._pixmap_item or self._range_transform is None:
            return
        view_scale = abs(self.transform().m11())
        if view_scale <= 0:
            return
        ruler_pixels = 140.0
        ruler_yards = ruler_distance(
            self._range_transform.x_yards_per_pixel,
            view_scale,
            ruler_pixels,
        )
        if ruler_yards <= 0:
            return

        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = QFont("Segoe UI", 12)
        font.setWeight(QFont.Weight.Medium)
        painter.setFont(font)
        if ruler_yards >= 100:
            label = f"{ruler_yards:,.0f} yd"
        elif ruler_yards >= 10:
            label = f"{ruler_yards:,.1f} yd"
        else:
            label = f"{ruler_yards:,.2f} yd"
        text_width = painter.fontMetrics().horizontalAdvance(label)
        panel_width = max(ruler_pixels + 30, text_width + 24)
        panel = QRectF(18, 18, panel_width, 50)
        painter.setPen(QPen(QColor("#7a7044"), 1.2))
        panel_color = QColor("#141a13")
        panel_color.setAlpha(235)
        painter.setBrush(QBrush(panel_color))
        painter.drawRoundedRect(panel, 3, 3)

        bar_left = panel.left() + 15
        bar_right = bar_left + ruler_pixels
        bar_y = panel.bottom() - 13
        bar_pen = QPen(QColor("#d6c468"), 2)
        bar_pen.setCosmetic(True)
        painter.setPen(bar_pen)
        painter.drawLine(QPointF(bar_left, bar_y), QPointF(bar_right, bar_y))
        painter.drawLine(QPointF(bar_left, bar_y - 6), QPointF(bar_left, bar_y + 6))
        painter.drawLine(QPointF(bar_right, bar_y - 6), QPointF(bar_right, bar_y + 6))
        painter.setPen(QColor("#f2e9c8"))
        painter.drawText(
            QRectF(panel.left() + 8, panel.top() + 3, panel.width() - 16, 22),
            Qt.AlignmentFlag.AlignCenter,
            label,
        )
        painter.end()
