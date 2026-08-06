from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QSize, Qt, Signal
from PySide6.QtGui import QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QComboBox,
    QFrame,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..domain.calibration import (
    AffineCalibration,
    Calibration,
    METRES_TO_YARDS,
    Point,
    read_resolution,
    write_calibration,
)
from ..domain.ballistic_solution import BallisticSolutionEngine
from ..domain.projectile import (
    ARTILLERY_PHYSICS,
    artillery_range_for_flight_time,
    artillery_time_of_flight,
)
from ..domain.ranging import RangeMeasurement
from ..domain.shot_history import FireTarget, ObservedShot, correction_summary
from ..domain.trajectory import TrajectoryClearanceResult
from ..maps.catalog import MapRecord, load_map_catalog
from ..maps.elevation import ElevationField, elevation_field_for_map
from ..maps.entities import locations_for_map
from ..paths import BALLISTICS_CSV, MAPS_DIR
from .bearing_compass import BearingCompass, map_bearing_degrees
from .map_view import MapView
from .trajectory_profile import TrajectoryProfilePlot


APP_STYLESHEET = """
QMainWindow, QWidget {
    background: #121811;
    color: #eee9d5;
    font-family: "Segoe UI";
    font-size: 13px;
}
QWidget#sidebar, QWidget#controlPanel { background: #121811; }
QWidget#sidebar { border-right: 1px solid #465442; }
QWidget#sidebarPages, QWidget#sidebarSelectedTools, QWidget#historyBody {
    background: #121811;
}
QFrame#sidebarSection {
    background: #121811;
    border: 1px solid #465442;
    border-radius: 3px;
}
QPushButton#sidebarSectionTitle {
    background: #121811;
    border: 0;
    border-bottom: 1px solid #465442;
    border-radius: 0;
    color: #e8d77e;
    padding: 8px 0;
    text-align: left;
}
QPushButton#sidebarSectionTitle:hover {
    background: #121811;
    border-bottom-color: #c6b35e;
}
QPushButton#sidebarActionButton {
    background: #121811;
    border: 1px solid #596044;
    color: #eee9d5;
}
QPushButton#sidebarActionButton:hover {
    background: #121811;
    border-color: #c6b35e;
    color: #fff5cd;
}
QPushButton#sidebarActionButton:pressed { background: #121811; }
QTreeWidget#targetHistoryTree {
    background: #121811;
    border: 0;
}
QTreeWidget#targetHistoryTree::item:hover {
    background: #121811;
    border-color: #465442;
}
QTreeWidget#targetHistoryTree::item:selected {
    background: #121811;
    border-color: #cdb36b;
    color: #e8d77e;
}
QFrame#mapWorkspace {
    background: #121811;
    border: 1px solid #465442;
    border-radius: 2px;
}
QFrame#toolbar, QFrame#panelCard, QFrame#instructionCard {
    background: #121811;
    border: 1px solid #465442;
    border-radius: 3px;
}
QFrame#toolbar { border-width: 0 0 1px 0; border-radius: 0; }
QFrame#readout {
    background: #121811;
    border: 1px solid #465442;
    border-radius: 2px;
}
QLabel#brand { font-size: 18px; font-weight: 700; color: #f2edda; }
QLabel#eyebrow, QLabel#fieldLabel, QLabel#readoutLabel {
    color: #c9b86c;
    font-family: Consolas;
    font-size: 10px;
}
QLabel#sectionTitle {
    color: #e8d77e;
    font-family: Consolas;
    font-size: 12px;
    font-weight: 700;
    border-bottom: 1px solid #465442;
    padding-bottom: 6px;
}
QLabel#mapTitle { font-size: 20px; font-weight: 700; }
QLabel#mapSubtitle { color: #9ea890; font-family: Consolas; font-size: 10px; }
QLabel#readoutValue { color: #fff5cd; font-family: Consolas; font-size: 19px; font-weight: 700; }
QLabel#muted { color: #9ba392; }
QPushButton {
    background: #121811;
    border: 1px solid #3e4939;
    border-radius: 3px;
    color: #eee9d5;
    padding: 7px 12px;
    font-family: Consolas;
    font-weight: 700;
}
QPushButton:hover { background: #2a3327; border-color: #c6b35e; }
QPushButton:pressed { background: #151b14; }
QPushButton#primaryButton { background: #c6b35e; color: #15160f; border-color: #d9c977; }
QPushButton#primaryButton:hover { background: #d3c36d; }
QLineEdit, QComboBox, QDoubleSpinBox {
    background: #121811;
    border: 1px solid #394335;
    border-radius: 3px;
    color: #fff7dc;
    padding: 8px 10px;
    min-height: 20px;
}
QLineEdit:focus, QComboBox:focus { border-color: #c6b35e; }
QComboBox QAbstractItemView { background: #121811; color: #fff7dc; selection-background-color: #3b4433; }
QTreeWidget {
    background: transparent;
    border: 0;
    outline: 0;
    color: #e7e2cf;
}
QTreeWidget::item {
    padding: 8px 9px;
    margin: 2px 4px;
    border: 1px solid transparent;
    border-radius: 3px;
    font-weight: 700;
}
QTreeWidget::item:hover {
    background: #1d261d;
    border-color: #465442;
}
QTreeWidget::item:selected {
    background: #cdb36b;
    border-color: #cdb36b;
    color: #15160f;
    font-weight: 700;
}
QTreeWidget::branch { image: none; background: #121811; }
QTreeWidget::branch:hover, QTreeWidget::branch:selected { background: #121811; }
QScrollBar:vertical { background: #121811; width: 8px; }
QScrollBar::handle:vertical { background: #3c4538; min-height: 30px; border-radius: 4px; }
QToolTip { background: #121811; color: #fff3c6; border: 1px solid #c6b35e; padding: 5px; }
"""


def discover_maps(maps_dir: Path) -> list[MapRecord]:
    """Load PAK-derived minimaps and their authoritative gameplay transforms."""
    return load_map_catalog(maps_dir.parent / "gameplay_area_calibrations.json")


def fit_window_to_screen(window: QWidget, preferred_width: int, preferred_height: int) -> None:
    """Keep a new window centered and entirely inside the usable desktop area."""
    screen = window.screen() or QApplication.primaryScreen()
    if screen is None:
        window.resize(preferred_width, preferred_height)
        return
    available = screen.availableGeometry()
    width = max(1, min(preferred_width, int(available.width() * 0.92)))
    height = max(1, min(preferred_height, int(available.height() * 0.92)))
    window.resize(width, height)
    frame = window.frameGeometry()
    frame.moveCenter(available.center())
    window.move(frame.topLeft())


class CalibrationEditor(QWidget):
    back_requested = Signal()
    calibration_saved = Signal(object, float)

    def __init__(self) -> None:
        super().__init__()
        self.record: MapRecord | None = None
        self.pixmap = QPixmap()
        self.points: list[QPointF] = []

        self.back_button = QPushButton("Close")
        self.back_button.clicked.connect(self.back_requested.emit)
        self.title = QLabel()
        self.title.setStyleSheet("font-size: 18px; font-weight: 600;")
        header = QHBoxLayout()
        header.addWidget(self.back_button)
        header.addWidget(self.title)
        header.addStretch()

        self.distance = QDoubleSpinBox()
        self.distance.setRange(0.001, 1_000_000_000)
        self.distance.setDecimals(3)
        self.distance.setSuffix(" yd")
        self.distance.setValue(100.0)
        self.distance.valueChanged.connect(self._refresh)
        self.instructions = QLabel("Enter the known distance in yards, then click its two endpoints.")
        self.instructions.setWordWrap(True)
        self.point_status = QLabel("Points: 0 / 2")
        self.result = QLabel("Scale: —")
        self.result.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.existing = QLabel("Saved scale: —")
        reset = QPushButton("Reset points")
        reset.clicked.connect(self._reset)
        self.save_button = QPushButton("Save calibration")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self._save)

        controls = QVBoxLayout()
        controls.addWidget(QLabel("Known distance"))
        controls.addWidget(self.distance)
        controls.addSpacing(12)
        controls.addWidget(self.instructions)
        controls.addWidget(self.point_status)
        controls.addWidget(self.result)
        controls.addWidget(self.existing)
        controls.addStretch()
        controls.addWidget(reset)
        controls.addWidget(self.save_button)
        control_widget = QWidget()
        control_widget.setLayout(controls)
        control_widget.setFixedWidth(290)

        self.view = MapView(self._add_point, self._calibration_points_changed)
        body = QHBoxLayout()
        body.addWidget(self.view, 1)
        body.addWidget(control_widget)
        layout = QVBoxLayout(self)
        layout.addLayout(header)
        layout.addLayout(body, 1)

    def set_map(self, record: MapRecord) -> None:
        self.record = record
        self.title.setText(f"Calibrate: {record.name}")
        self.pixmap = QPixmap(str(record.image_path))
        self.points.clear()
        if self.pixmap.isNull():
            self.view.clear_map()
            self.instructions.setText(f"Could not load {record.image_path}")
            return
        self.view.set_map(self.pixmap)
        saved = read_resolution(record.config_path)
        self.existing.setText(
            f"Saved scale: {saved:.8g} yd/pixel" if saved else "Saved scale: not calibrated"
        )
        self._refresh()

    def _add_point(self, point: QPointF) -> None:
        if len(self.points) == 2:
            self.points.clear()
        self.points.append(point)
        self.view.set_points(self.points)
        self._refresh()

    def _calibration_points_changed(self, points: list[QPointF]) -> None:
        self.points = points
        self._refresh()

    def _reset(self) -> None:
        self.points.clear()
        self.view.clear_points()
        self._refresh()

    def _calibration(self) -> Calibration | None:
        if len(self.points) != 2:
            return None
        return Calibration(
            Point(self.points[0].x(), self.points[0].y()),
            Point(self.points[1].x(), self.points[1].y()),
            self.distance.value(),
        )

    def _refresh(self) -> None:
        self.point_status.setText(f"Points: {len(self.points)} / 2")
        calibration = self._calibration()
        if calibration is None:
            self.result.setText("Scale: —")
            self.save_button.setEnabled(False)
            return
        try:
            scale = calibration.yards_per_pixel
        except ValueError as error:
            self.result.setText(str(error))
            self.save_button.setEnabled(False)
            return
        self.result.setText(
            f"Pixel distance: {calibration.pixel_distance:.3f} px\n"
            f"Scale: {scale:.10g} yd/pixel\n"
            f"Equivalent: {1 / scale:.6g} pixels/yard"
        )
        self.save_button.setEnabled(self.record is not None)

    def _save(self) -> None:
        calibration = self._calibration()
        if calibration is None or self.record is None:
            return
        try:
            write_calibration(
                self.record.config_path,
                calibration,
                self.pixmap.width(),
                self.pixmap.height(),
            )
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "Save failed", str(error))
            return
        scale = calibration.yards_per_pixel
        self.existing.setText(f"Saved scale: {scale:.8g} yd/pixel")
        self.calibration_saved.emit(self.record.image_path, scale)
        QMessageBox.information(self, "Calibration saved", f"Saved {self.record.name}.")


class CalibrationDialog(QDialog):
    calibration_saved = Signal(object, float)

    def __init__(self, record: MapRecord, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Calibrate {record.name}")
        self.editor = CalibrationEditor()
        self.editor.back_requested.connect(self.reject)
        self.editor.calibration_saved.connect(self._saved)
        self.editor.set_map(record)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.editor)
        fit_window_to_screen(self, 1100, 760)

    def _saved(self, path: Path, scale: float) -> None:
        self.calibration_saved.emit(path, scale)


class ShotRecordDialog(QDialog):
    """Compact form for a target-relative observed impact."""

    def __init__(
        self,
        fired_elevation_deg: float | None,
        fuze_seconds: float | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Record observed impact")
        form = QFormLayout(self)

        self.over_short = QDoubleSpinBox()
        self.over_short.setRange(-10_000, 10_000)
        self.over_short.setDecimals(1)
        self.over_short.setSuffix(" yd")
        self.over_short.setToolTip("Positive is over; negative is short")
        form.addRow("Over (+) / short (-)", self.over_short)

        self.left_right = QDoubleSpinBox()
        self.left_right.setRange(-10_000, 10_000)
        self.left_right.setDecimals(1)
        self.left_right.setSuffix(" yd")
        self.left_right.setToolTip("Positive is right; negative is left")
        form.addRow("Right (+) / left (-)", self.left_right)

        self.fired_elevation = QDoubleSpinBox()
        self.fired_elevation.setRange(-10, 75)
        self.fired_elevation.setDecimals(3)
        self.fired_elevation.setSuffix("°")
        self.fired_elevation.setValue(fired_elevation_deg or 0.0)
        form.addRow("Elevation fired", self.fired_elevation)

        self.fuze = QDoubleSpinBox()
        self.fuze.setRange(0, 3_600)
        self.fuze.setDecimals(3)
        self.fuze.setSuffix(" s")
        self.fuze.setSpecialValueText("Not recorded")
        self.fuze.setValue(fuze_seconds or 0.0)
        form.addRow("Fuze / flight time", self.fuze)

        self.note = QLineEdit()
        self.note.setPlaceholderText("Optional note")
        form.addRow("Note", self.note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def record(self) -> ObservedShot:
        return ObservedShot(
            self.over_short.value(),
            self.left_right.value(),
            self.fired_elevation.value(),
            self.fuze.value() or None,
            self.note.text().strip(),
        )


class MainWindow(QMainWindow):
    def __init__(self, maps_dir: Path) -> None:
        super().__init__()
        self.maps_dir = maps_dir
        self.maps = discover_maps(maps_dir)
        self.current_map: MapRecord | None = None
        self.transform: AffineCalibration | None = None
        self.resolution: float | None = None
        self.points: list[QPointF] = []
        self.current_image_size = (0, 0)
        self.elevation_field: ElevationField | None = None
        self.current_range_measurement: RangeMeasurement | None = None
        self.current_flight_time_text = "—"
        self.current_clearance_result: TrajectoryClearanceResult | None = None
        self.map_items: dict[Path, QTreeWidgetItem] = {}
        self.ballistic_solver: BallisticSolutionEngine | None = None
        self.target_histories: dict[Path, list[FireTarget]] = {}
        self.active_guns: dict[Path, Point] = {}
        self._target_summary_cache: dict[tuple[object, ...], str] = {}
        self.selected_target_id: int | None = None
        self._target_overlay_suppressed = False
        self._updating_target_history = False
        self.setWindowTitle("worCalc — Artillery Fire Direction")
        self.setStyleSheet(APP_STYLESHEET)

        self.sidebar = self._create_sidebar()

        self.pages = QStackedWidget()
        empty = QLabel("Choose a map from the map selector")
        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.setWordWrap(True)
        empty.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        empty.setStyleSheet("font-size: 24px; color: #8b8f94; background: #121811;")
        self.empty_page = empty
        self.map_page = self._create_map_page()
        self.pages.addWidget(self.empty_page)
        self.pages.addWidget(self.map_page)
        self.pages.setCurrentWidget(self.empty_page)

        root = QHBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.sidebar)
        root.addWidget(self.pages, 1)
        container = QWidget()
        container.setLayout(root)
        self.setCentralWidget(container)
        self._create_ballistic_solver()
        fit_window_to_screen(self, 1480, 880)

    def _create_ballistic_solver(self) -> None:
        if not BALLISTICS_CSV.is_file():
            return
        self.ballistic_solver = BallisticSolutionEngine(BALLISTICS_CSV)
        self.ballistic_method.clear()
        self.ballistic_method.addItems(self.ballistic_solver.method_names)
        self.ballistic_method.setCurrentIndex(self.ballistic_solver.method_index)
        self.ballistic_method.setEnabled(True)
        self.ballistic_method.currentIndexChanged.connect(
            self._ballistic_method_changed
        )

    def _ballistic_method_changed(self, index: int) -> None:
        if self.ballistic_solver is None:
            return
        self.ballistic_solver.set_method(index)
        self._refresh_measurement()
        self._refresh_target_history()

    def _create_sidebar(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("sidebar")
        panel.setFixedWidth(312)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        badge = QLabel("FDC\n01")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFixedSize(54, 46)
        badge.setStyleSheet(
            "background:#121811; color:#e2c85d; border:1px solid #596044; "
            "border-radius:3px; font-family:Consolas; font-weight:700; font-size:15px;"
        )
        brand = QLabel("FIRE CONTROL")
        brand.setObjectName("brand")
        subtitle = QLabel("TACTICAL OPERATIONS SYSTEM")
        subtitle.setObjectName("eyebrow")
        brand_text = QVBoxLayout()
        brand_text.setSpacing(1)
        brand_text.addWidget(brand)
        brand_text.addWidget(subtitle)
        brand_row = QHBoxLayout()
        brand_row.addWidget(badge)
        brand_row.addLayout(brand_text)
        brand_row.addStretch()
        layout.addLayout(brand_row)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("color:#394235;")
        layout.addWidget(divider)

        self.sidebar_pages = QStackedWidget()
        self.sidebar_pages.setObjectName("sidebarPages")
        layout.addWidget(self.sidebar_pages, 1)

        library_page = QWidget()
        library_layout = QVBoxLayout(library_page)
        library_layout.setContentsMargins(0, 0, 0, 0)
        library_layout.setSpacing(12)
        library_card = QFrame()
        library_card.setObjectName("sidebarSection")
        library_card_layout = QVBoxLayout(library_card)
        library_card_layout.setContentsMargins(12, 10, 12, 12)
        library_card_layout.setSpacing(10)
        self.map_library_card = library_card
        library_layout.addWidget(library_card, 1)
        library_label = QLabel("MAP LIBRARY")
        library_label.setObjectName("sectionTitle")
        library_card_layout.addWidget(library_label)

        self.map_search = QLineEdit()
        self.map_search.setPlaceholderText("SEARCH OPERATION AREA")
        self.map_search.setClearButtonEnabled(True)
        self.map_search.textChanged.connect(self._filter_map_tree)
        library_card_layout.addWidget(self.map_search)

        self.map_tree = QTreeWidget()
        self.map_tree.setHeaderHidden(True)
        self.map_tree.setIconSize(QSize(34, 34))
        self.map_tree.setIndentation(18)
        self.map_tree.setExpandsOnDoubleClick(False)
        self.map_tree.itemClicked.connect(self._tree_item_clicked)
        nodes: dict[tuple[str, ...], QTreeWidgetItem] = {}
        if not self.maps:
            empty_item = QTreeWidgetItem(["No maps found"])
            empty_item.setFlags(
                empty_item.flags() & ~Qt.ItemFlag.ItemIsSelectable
            )
            self.map_tree.addTopLevelItem(empty_item)
        for record in self.maps:
            parts = record.tree_parts
            parent: QTreeWidgetItem | None = None
            for depth, part in enumerate(parts, start=1):
                key = parts[:depth]
                item = nodes.get(key)
                if item is None:
                    item = QTreeWidgetItem([part])
                    item_font = item.font(0)
                    item_font.setWeight(QFont.Weight.Bold)
                    item.setFont(0, item_font)
                    if depth < len(parts):
                        item.setFlags(
                            item.flags() & ~Qt.ItemFlag.ItemIsSelectable
                        )
                    nodes[key] = item
                    if parent is None:
                        self.map_tree.addTopLevelItem(item)
                    else:
                        parent.addChild(item)
                parent = item
            if parent is not None:
                parent.setData(0, Qt.ItemDataRole.UserRole, record)
                parent.setIcon(0, QIcon(str(record.image_path)))
                parent.setToolTip(
                    0,
                    f"{record.name}\n{record.battlefield} · {record.mode_name}\n"
                    "Authoritative game calibration",
                )
                self.map_items[record.image_path] = parent
        self.map_tree.collapseAll()
        library_card_layout.addWidget(self.map_tree, 1)

        instructions = QFrame()
        instructions.setObjectName("instructionCard")
        instruction_layout = QVBoxLayout(instructions)
        instruction_layout.setContentsMargins(13, 11, 13, 11)
        instruction_layout.setSpacing(4)
        heading = QLabel("POINT SEQUENCE")
        heading.setObjectName("sectionTitle")
        steps = QLabel("01 / PLACE GUN POSITION\n02 / PLACE TARGET POSITION\n03 / DRAG MARKERS TO ADJUST")
        steps.setObjectName("eyebrow")
        steps.setStyleSheet("line-height: 1.5;")
        instruction_layout.addWidget(heading)
        instruction_layout.addWidget(steps)
        library_layout.addWidget(instructions)
        self.sidebar_pages.addWidget(library_page)
        self.sidebar_library_page = library_page

        map_data_page = QWidget()
        map_data_layout = QVBoxLayout(map_data_page)
        map_data_layout.setContentsMargins(0, 0, 0, 0)
        map_data_layout.setSpacing(10)

        selected_tools = QWidget()
        selected_tools.setObjectName("sidebarSelectedTools")
        self.sidebar_selected_layout = QVBoxLayout(selected_tools)
        self.sidebar_selected_layout.setContentsMargins(0, 0, 0, 0)
        self.sidebar_selected_layout.setSpacing(10)

        map_data_title = QLabel("MAP DATA")
        map_data_title.setObjectName("sectionTitle")
        self.map_data_title = map_data_title
        self.sidebar_selected_layout.addStretch()
        self.sidebar_selected_layout.addWidget(map_data_title)

        self.map_info = QLabel()
        self.map_info.setObjectName("muted")
        self.map_info.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        self.map_info.setWordWrap(True)
        self.map_info.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        self.map_info.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.map_info.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Maximum,
        )
        self.map_info.setStyleSheet(
            "background:#121811; border:0; padding:8px 0;"
        )
        self.sidebar_selected_layout.addWidget(self.map_info)

        selected_scroll = QScrollArea()
        selected_scroll.setObjectName("sidebarToolScroll")
        selected_scroll.setWidgetResizable(True)
        selected_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        selected_scroll.setFrameShape(QFrame.Shape.NoFrame)
        selected_scroll.setStyleSheet(
            "QScrollArea#sidebarToolScroll {"
            "border:0; background:#121811;"
            "} QScrollArea#sidebarToolScroll > QWidget > QWidget {"
            "background:#121811;"
            "}"
        )
        selected_scroll.setWidget(selected_tools)
        self.sidebar_tool_scroll = selected_scroll
        map_data_layout.addWidget(selected_scroll, 1)

        change_map = QPushButton("← CHANGE OPERATION AREA")
        change_map.clicked.connect(self._show_map_library)
        map_data_layout.addWidget(change_map)
        self.sidebar_pages.addWidget(map_data_page)
        self.sidebar_map_data_page = map_data_page
        self.sidebar_pages.setCurrentWidget(self.sidebar_library_page)

        return panel

    def _show_map_library(self) -> None:
        self.sidebar_pages.setCurrentWidget(self.sidebar_library_page)
        self.map_search.setFocus()

    def _show_map_data(self) -> None:
        self.sidebar_pages.setCurrentWidget(self.sidebar_map_data_page)

    def _tree_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        record = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(record, MapRecord):
            self._select_map(record)
        elif item.childCount():
            item.setExpanded(not item.isExpanded())

    def _filter_map_tree(self, text: str) -> None:
        query = text.strip().casefold()

        def filter_item(item: QTreeWidgetItem, ancestor_matches: bool = False) -> bool:
            own_match = query in item.text(0).casefold()
            branch_matches = ancestor_matches or own_match
            child_visible = False
            for index in range(item.childCount()):
                if filter_item(item.child(index), branch_matches):
                    child_visible = True
            visible = not query or branch_matches or child_visible
            item.setHidden(not visible)
            if query and visible and item.childCount():
                item.setExpanded(True)
            return visible

        for index in range(self.map_tree.topLevelItemCount()):
            filter_item(self.map_tree.topLevelItem(index))
        if not query:
            self.map_tree.collapseAll()

    def _create_map_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("mapPage")
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        workspace = QFrame()
        workspace.setObjectName("mapWorkspace")
        workspace_layout = QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(1, 1, 1, 1)
        workspace_layout.setSpacing(0)
        toolbar = QFrame()
        toolbar.setObjectName("toolbar")
        self.toolbar = toolbar
        header = QHBoxLayout(toolbar)
        header.setContentsMargins(16, 9, 14, 9)
        header.setSpacing(8)
        self.map_title = QLabel()
        self.map_title.setObjectName("mapTitle")
        self.map_subtitle = QLabel("SELECT A MAP")
        self.map_subtitle.setObjectName("mapSubtitle")
        self.map_subtitle.setMaximumWidth(290)
        title_block = QVBoxLayout()
        title_block.setSpacing(0)
        title_block.addWidget(self.map_title)
        title_block.addWidget(self.map_subtitle)
        self.calibrate_button = QPushButton("Calibrate map…")
        self.calibrate_button.setToolTip("Calibrate the currently selected map")
        self.calibrate_button.clicked.connect(self._open_calibration)
        self.calibrate_button.hide()
        self.projectile_type = QComboBox()
        self.projectile_type.addItems(["Shell", "Case"])
        self.projectile_type.setFixedWidth(88)
        self.projectile_type.setToolTip("Select the ammunition for the fuze estimate")
        self.projectile_type.currentTextChanged.connect(
            lambda _text: self._weapon_changed()
        )
        self.cannon_type = QComboBox()
        self.cannon_type.addItems(
            ["3-inch Ordnance", "10-pounder Parrott", "12-pounder Napoleon"]
        )
        self.cannon_type.setFixedWidth(178)
        self.cannon_type.setToolTip("Select the cannon for the fuze estimate")
        self.cannon_type.currentTextChanged.connect(
            lambda _text: self._weapon_changed()
        )
        self.ballistic_method = QComboBox()
        self.ballistic_method.setFixedWidth(168)
        self.ballistic_method.setEnabled(False)
        self.ballistic_method.setToolTip(
            "Choose the curve used to calculate the required gun elevation"
        )

        def add_header_option(title: str, control: QWidget) -> None:
            option_layout = QVBoxLayout()
            option_layout.setSpacing(2)
            option_label = QLabel(title)
            option_label.setObjectName("fieldLabel")
            option_layout.addWidget(option_label)
            option_layout.addWidget(control)
            header.addLayout(option_layout)

        header.addLayout(title_block)
        header.addStretch()
        add_header_option("CANNON", self.cannon_type)
        add_header_option("AMMUNITION", self.projectile_type)
        add_header_option("ESTIMATION CURVE", self.ballistic_method)
        self.warning_banner = QLabel()
        self.warning_banner.setWordWrap(True)
        self.warning_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.warning_banner.setMinimumHeight(44)
        self.warning_banner.setStyleSheet(
            "background: #704b00; color: #fff3cd; border: 1px solid #c78b12; "
            "border-radius: 5px; padding: 8px; font-weight: 600;"
        )
        self.warning_banner.hide()
        self.view = MapView(
            self._add_measurement_point,
            self._measurement_points_changed,
            self._map_position_hovered,
            estimation_range_for_fuze=self._estimation_range_for_fuze,
            saved_target_selected=self._select_saved_target,
            saved_target_moved=self._move_saved_target,
            saved_target_removed=self._remove_saved_target,
        )
        self.view.setStyleSheet("border:0; background:#121811;")
        self.marker_legend = QLabel(
            '<span style="color:#f2ad3d;">●</span> Game-file reference&nbsp;&nbsp; '
            '<span style="color:#3f8cff;">●</span> USA spawn&nbsp;&nbsp; '
            '<span style="color:#e34f4f;">●</span> CSA spawn&nbsp;&nbsp; '
            '<span style="color:#b75cff;">●</span> Objective / contention point&nbsp;&nbsp; '
            '<span style="color:#f2c94c;">G</span> User-placed gun'
        )
        self.marker_legend.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.marker_legend.setStyleSheet(
            "font-family:Consolas; font-size:11px; color:#d8d3bd; background:#121811; "
            "border-top:1px solid #343d31; padding:7px 8px;"
        )
        self.marker_legend.hide()
        self.cursor_readout = QLabel("CURSOR —")
        self.cursor_readout.setObjectName("eyebrow")
        self.cursor_readout.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.cursor_readout.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.cursor_readout.setMinimumHeight(30)
        self.cursor_readout.setStyleSheet(
            "background:#121811; border-top:1px solid #343d31; "
            "padding:4px 14px; color:#d8c96d;"
        )
        self.elevation_overlay = QCheckBox("Show elevation gradient")
        self.elevation_overlay.setToolTip(
            "Show or hide gradient colors only; altitude calculations remain active"
        )
        self.elevation_overlay.toggled.connect(
            self.view.set_elevation_overlay_visible
        )
        self.grayscale_map = QCheckBox("Grayscale map")
        self.grayscale_map.setToolTip("Show the PAK minimap mask in grayscale")
        self.grayscale_map.toggled.connect(
            lambda checked: self._set_map_style(
                "Grayscale" if checked else "Parchment"
            )
        )
        display_options_bar = QFrame()
        display_options_bar.setObjectName("toolbar")
        self.display_options_bar = display_options_bar
        display_options_layout = QHBoxLayout(display_options_bar)
        display_options_layout.setContentsMargins(14, 5, 14, 5)
        display_options_layout.setSpacing(18)
        display_options_layout.addStretch()
        display_options_layout.addWidget(self.grayscale_map)
        display_options_layout.addWidget(self.elevation_overlay)
        workspace_layout.addWidget(toolbar)
        workspace_layout.addWidget(self.warning_banner)
        workspace_layout.addWidget(self.view, 1)
        workspace_layout.addWidget(self.marker_legend)
        workspace_layout.addWidget(self.cursor_readout)
        workspace_layout.addWidget(display_options_bar)

        control_panel = QWidget()
        control_panel.setObjectName("controlPanel")
        control_panel.setMinimumWidth(320)
        controls = QVBoxLayout(control_panel)
        controls.setContentsMargins(12, 12, 12, 12)
        controls.setSpacing(10)
        mission_card = QFrame()
        mission_card.setObjectName("panelCard")
        mission_layout = QVBoxLayout(mission_card)
        mission_layout.setContentsMargins(13, 12, 13, 13)
        mission_layout.setSpacing(9)
        mission_title = QLabel("FIRE MISSION")
        mission_title.setObjectName("sectionTitle")
        mission_layout.addWidget(mission_title)
        primary_solution_grid = QGridLayout()
        primary_solution_grid.setSpacing(8)
        range_frame, self.solution_range = self._make_readout("DISTANCE", "—")
        elevation_frame, self.solution_elevation = self._make_readout("ELEVATION", "—")
        tof_frame, self.solution_tof = self._make_readout("FUZE / FLIGHT TIME", "—")
        primary_solution_grid.addWidget(range_frame, 0, 0, 1, 2)
        mission_layout.addLayout(primary_solution_grid)
        profile_grid = QGridLayout()
        profile_grid.setSpacing(8)
        velocity_frame, self.muzzle_velocity = self._make_readout("MUZZLE VELOCITY", "—")
        drag_frame, self.drag_factor = self._make_readout("DRAG FACTOR", "—")
        profile_grid.addWidget(velocity_frame, 0, 0)
        profile_grid.addWidget(drag_frame, 0, 1)
        mission_layout.addLayout(profile_grid)
        bearing_label = QLabel("BEARING")
        bearing_label.setObjectName("fieldLabel")
        self.solution_bearing = BearingCompass()
        mission_layout.addWidget(bearing_label)
        mission_layout.addWidget(self.solution_bearing)
        secondary_solution_grid = QGridLayout()
        secondary_solution_grid.setSpacing(8)
        secondary_solution_grid.addWidget(elevation_frame, 0, 0)
        secondary_solution_grid.addWidget(tof_frame, 0, 1)
        mission_layout.addLayout(secondary_solution_grid)
        self.clearance_status = QLabel("ESTIMATED ROUTE: —")
        self.clearance_status.setWordWrap(True)
        self.clearance_status.setTextFormat(Qt.TextFormat.RichText)
        self.clearance_status.setStyleSheet(
            "color:#eee9d5; font-family:Consolas;"
        )
        self.clearance_details = QLabel()
        self.clearance_details.setWordWrap(True)
        self.clearance_details.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.clearance_details.setStyleSheet(
            "background:#121811; border:1px solid #465442; "
            "border-radius:2px; padding:8px;"
        )
        self.clearance_details.hide()
        self.trajectory_profile = TrajectoryProfilePlot()
        self.solution_bearing.setStyleSheet(
            "background:#121811; border:1px solid #465442; border-radius:2px;"
        )
        mission_layout.addWidget(self.clearance_status)
        mission_layout.addWidget(self.clearance_details)
        mission_layout.addWidget(self.trajectory_profile)

        history_card = QFrame()
        history_card.setObjectName("sidebarSection")
        history_card.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Maximum,
        )
        history_layout = QVBoxLayout(history_card)
        history_layout.setContentsMargins(12, 10, 12, 12)
        history_layout.setSpacing(8)
        self.history_toggle = QPushButton("TARGET HISTORY · 0")
        self.history_toggle.setObjectName("sidebarSectionTitle")
        self.history_toggle.setCheckable(True)
        self.history_toggle.setChecked(True)
        history_layout.addWidget(self.history_toggle)
        self.history_body = QWidget()
        self.history_body.setObjectName("historyBody")
        history_body_layout = QVBoxLayout(self.history_body)
        history_body_layout.setContentsMargins(0, 2, 0, 0)
        history_body_layout.setSpacing(8)
        self.target_history_tree = QTreeWidget()
        self.target_history_tree.setObjectName("targetHistoryTree")
        self.target_history_tree.setHeaderHidden(True)
        self.target_history_tree.setRootIsDecorated(False)
        self.target_history_tree.setIndentation(0)
        self.target_history_tree.setFixedHeight(220)
        self.target_history_tree.itemClicked.connect(self._history_item_clicked)
        history_body_layout.addWidget(self.target_history_tree)
        interaction_hint = QLabel("DRAG TO MOVE  ·  RIGHT-CLICK TO REMOVE")
        interaction_hint.setObjectName("eyebrow")
        interaction_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        history_body_layout.addWidget(interaction_hint)
        history_actions = QGridLayout()
        history_actions.setSpacing(6)
        self.record_impact_button = QPushButton("RECORD IMPACT…")
        self.record_impact_button.setObjectName("sidebarActionButton")
        self.record_impact_button.clicked.connect(self._record_impact_clicked)
        history_actions.addWidget(self.record_impact_button, 0, 0)
        history_body_layout.addLayout(history_actions)
        history_layout.addWidget(self.history_body)
        self.history_toggle.toggled.connect(self.history_body.setVisible)
        self.sidebar_selected_layout.insertWidget(0, history_card)

        controls.addWidget(mission_card)
        controls.addStretch()
        control_panel.setMinimumHeight(control_panel.sizeHint().height())
        control_scroll = QScrollArea()
        control_scroll.setObjectName("controlPanelScroll")
        control_scroll.setWidgetResizable(True)
        control_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        control_scroll.setFrameShape(QFrame.Shape.NoFrame)
        control_scroll.setFixedWidth(358)
        control_scroll.setStyleSheet(
            "QScrollArea#controlPanelScroll {"
            "border:0; background:#121811;"
            "}"
        )
        control_scroll.setWidget(control_panel)
        self.control_scroll = control_scroll

        layout.addWidget(workspace, 1)
        layout.addWidget(control_scroll)
        self._update_history_controls()
        self._weapon_changed()
        return page

    def _make_readout(self, title: str, value: str) -> tuple[QFrame, QLabel]:
        frame = QFrame()
        frame.setObjectName("readout")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(9, 7, 9, 8)
        layout.setSpacing(2)
        label = QLabel(title)
        label.setObjectName("readoutLabel")
        result = QLabel(value)
        result.setObjectName("readoutValue")
        layout.addWidget(label)
        layout.addWidget(result)
        return frame, result

    def _set_map_style(self, style: str) -> None:
        self.view.set_map_style(style)

    def _select_map(self, record: MapRecord) -> None:
        pixmap = QPixmap(str(record.image_path))
        if pixmap.isNull():
            QMessageBox.critical(self, "Map error", f"Could not load {record.image_path}")
            return
        self.current_map = record
        self.transform = record.calibration
        self.resolution = record.calibration.mean_yards_per_pixel
        self.current_image_size = (pixmap.width(), pixmap.height())
        active_gun = self.active_guns.get(record.image_path)
        self.points = (
            [QPointF(active_gun.x, active_gun.y)]
            if active_gun is not None
            else []
        )
        self._target_summary_cache.clear()
        self.selected_target_id = None
        self._target_overlay_suppressed = False
        self.map_title.setText(record.name)
        battlefield_name = {
            "DrillCamp": "Drill Camp",
            "HarpersFerry": "Harpers Ferry",
            "SouthMountain": "South Mountain",
        }.get(record.battlefield, record.battlefield)
        self.map_subtitle.setText(
            f"{battlefield_name.upper()} / {record.mode_name.upper()} / "
            f"AREA {record.gameplay_area + 1:02d}"
        )
        self.view.set_map(pixmap)
        self.view.set_range_transform(self.transform)
        self.elevation_field = elevation_field_for_map(
            record, pixmap.width(), pixmap.height(), self.maps_dir.parent
        )
        self.view.set_elevation_field(self.elevation_field)
        self.view.set_elevation_overlay_visible(self.elevation_overlay.isChecked())
        locations = locations_for_map(
            record, pixmap.width(), pixmap.height(), self.maps_dir.parent
        )
        self.view.set_location_markers(locations)
        if locations:
            self.marker_legend.setToolTip(f"{len(locations)} game-file locations on this map")
            self.marker_legend.show()
        else:
            self.marker_legend.hide()
        self._refresh_target_history()
        self._update_map_info()
        self._show_map_data()
        self.pages.setCurrentWidget(self.map_page)
        selected_item = self.map_items.get(record.image_path)
        if selected_item is not None:
            self.map_tree.setCurrentItem(selected_item)
            parent = selected_item.parent()
            while parent is not None:
                parent.setExpanded(True)
                parent = parent.parent()
        self.view.set_interaction_enabled(True)
        self.view.set_points(self.points)
        self.warning_banner.hide()
        self._refresh_measurement()

    def _add_measurement_point(self, point: QPointF) -> None:
        if self.transform is None:
            return
        if not self.points:
            retained_target = self.view.retained_target_point()
            self._set_active_gun(point)
            if retained_target is None:
                self.points = [point]
            else:
                self.points = [point, retained_target]
                self._sync_selected_target_from_points()
            self.view.set_points(self.points)
            self._refresh_measurement()
            return

        active_gun = self._active_gun()
        gun = (
            QPointF(active_gun.x, active_gun.y)
            if active_gun is not None
            else QPointF(self.points[0])
        )
        self.selected_target_id = None
        self._target_overlay_suppressed = False
        self.points = [gun, point]
        self.view.set_points(self.points)
        self._refresh_measurement()
        self._autosave_current_target()

    def _measurement_points_changed(self, points: list[QPointF]) -> None:
        self.points = points
        self._set_active_gun(points[0] if points else None)
        self._sync_selected_target_from_points()
        self._refresh_target_history()
        self._refresh_measurement()

    def _current_targets(self) -> list[FireTarget]:
        if self.current_map is None:
            return []
        return self.target_histories.setdefault(self.current_map.image_path, [])

    def _active_gun(self) -> Point | None:
        if self.current_map is None:
            return None
        return self.active_guns.get(self.current_map.image_path)

    def _set_active_gun(self, point: QPointF | Point | None) -> None:
        if self.current_map is None:
            return
        if point is None:
            self.active_guns.pop(self.current_map.image_path, None)
        else:
            self.active_guns[self.current_map.image_path] = Point(
                point.x() if isinstance(point, QPointF) else point.x,
                point.y() if isinstance(point, QPointF) else point.y,
            )
        self._target_summary_cache.clear()

    def _target_by_id(self, target_id: int | None) -> FireTarget | None:
        if target_id is None:
            return None
        return next(
            (
                target
                for target in self._current_targets()
                if target.identifier == target_id
            ),
            None,
        )

    def _sync_selected_target_from_points(self) -> None:
        target = self._target_by_id(self.selected_target_id)
        if target is None or len(self.points) != 2:
            return
        target.target = Point(self.points[1].x(), self.points[1].y())

    def _autosave_current_target(self) -> None:
        if len(self.points) != 2:
            return
        target = self._target_by_id(self.selected_target_id)
        if target is None:
            targets = self._current_targets()
            target = FireTarget(
                max((item.identifier for item in targets), default=0) + 1,
                Point(self.points[1].x(), self.points[1].y()),
            )
            targets.append(target)
            self.selected_target_id = target.identifier
        else:
            target.target = Point(self.points[1].x(), self.points[1].y())
        self._target_overlay_suppressed = False
        self._refresh_target_history()
        self._update_target_overlay()

    def _select_saved_target(self, target_id: int) -> None:
        if self.selected_target_id == target_id:
            self.selected_target_id = None
            self._target_overlay_suppressed = True
            self._refresh_target_history()
            self._update_target_overlay()
            return
        target = self._target_by_id(target_id)
        if target is None:
            return
        self.selected_target_id = target_id
        self._target_overlay_suppressed = False
        active_gun = self._active_gun()
        self.points = (
            [
                QPointF(active_gun.x, active_gun.y),
                QPointF(target.target.x, target.target.y),
            ]
            if active_gun is not None
            else []
        )
        self.view.set_points(self.points)
        self._refresh_measurement()
        self._refresh_target_history()

    def _remove_saved_target(self, target_id: int) -> None:
        targets = self._current_targets()
        target = self._target_by_id(target_id)
        if target is None:
            return
        targets.remove(target)
        if self.selected_target_id == target_id:
            self.selected_target_id = None
            self._target_overlay_suppressed = False
            active_gun = self._active_gun()
            self.points = (
                [QPointF(active_gun.x, active_gun.y)]
                if active_gun is not None
                else []
            )
            self.view.set_points(self.points)
            self._refresh_measurement()
        self._refresh_target_history()

    def _move_saved_target(self, target_id: int, point: QPointF) -> None:
        target = self._target_by_id(target_id)
        if target is None:
            return
        width, height = self.current_image_size
        clamped = QPointF(
            min(max(point.x(), 0.0), float(width)),
            min(max(point.y(), 0.0), float(height)),
        )
        target.target = Point(clamped.x(), clamped.y())
        self.selected_target_id = target_id
        self._target_overlay_suppressed = False
        active_gun = self._active_gun()
        self.points = (
            [QPointF(active_gun.x, active_gun.y), clamped]
            if active_gun is not None
            else []
        )
        self.view.set_points(self.points)
        self._refresh_measurement()
        self._refresh_target_history()

    def _history_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        if self._updating_target_history:
            return
        target_id = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(target_id, int):
            self._select_saved_target(target_id)

    def _target_history_summary(self, target: FireTarget) -> str:
        active_gun = self._active_gun()
        if self.transform is None or active_gun is None:
            return f"T{target.identifier} · — · —"
        method_index = (
            self.ballistic_solver.method_index
            if self.ballistic_solver is not None
            else None
        )
        cache_key = (
            self.current_map.image_path if self.current_map is not None else None,
            target.identifier,
            active_gun.x,
            active_gun.y,
            target.target.x,
            target.target.y,
            self.cannon_type.currentText(),
            self.projectile_type.currentText(),
            method_index,
        )
        cached = self._target_summary_cache.get(cache_key)
        if cached is not None:
            return cached
        horizontal_range = self.transform.distance_yards(active_gun, target.target)
        gun_elevation = (
            self.elevation_field.elevation_at(active_gun)
            if self.elevation_field is not None
            else None
        )
        target_elevation = (
            self.elevation_field.elevation_at(target.target)
            if self.elevation_field is not None
            else None
        )
        elevation_change = (
            target_elevation - gun_elevation
            if gun_elevation is not None and target_elevation is not None
            else None
        )
        measurement = RangeMeasurement(horizontal_range, elevation_change)
        angle = (
            self.ballistic_solver.solve(
                horizontal_range,
                elevation_change if elevation_change is not None else 0.0,
            )
            if self.ballistic_solver is not None
            else None
        )
        elevation_text = f"{angle:.2f}°" if angle is not None else "—"
        try:
            fuze_seconds = artillery_time_of_flight(
                measurement.slant_yards,
                self.cannon_type.currentText(),
                self.projectile_type.currentText(),
            )
            fuze_text = f"{fuze_seconds:.2f} s"
        except ValueError:
            fuze_text = "—"
        summary = f"T{target.identifier} · {elevation_text} · {fuze_text}"
        self._target_summary_cache[cache_key] = summary
        return summary

    def _refresh_target_history(self) -> None:
        if not hasattr(self, "target_history_tree"):
            return
        targets = self._current_targets()
        self._updating_target_history = True
        self.target_history_tree.clear()
        selected_item: QTreeWidgetItem | None = None
        for target in targets:
            summary = self._target_history_summary(target)
            target_item = QTreeWidgetItem([summary])
            target_item.setSizeHint(0, QSize(0, 38))
            target_item.setData(
                0,
                Qt.ItemDataRole.UserRole,
                target.identifier,
            )
            self.target_history_tree.addTopLevelItem(target_item)
            for index, shot in enumerate(target.shots, start=1):
                details = f"S{index} · {correction_summary(shot).upper()}"
                if shot.fired_elevation_deg is not None:
                    details += f" · {shot.fired_elevation_deg:.3f}°"
                shot_item = QTreeWidgetItem([details])
                shot_item.setData(
                    0,
                    Qt.ItemDataRole.UserRole,
                    target.identifier,
                )
                target_item.addChild(shot_item)
            target_item.setExpanded(target.identifier == self.selected_target_id)
            if target.identifier == self.selected_target_id:
                selected_item = target_item
        self.target_history_tree.setCurrentItem(selected_item)
        self._updating_target_history = False
        target_height = len(targets) * 44
        shot_height = sum(len(target.shots) for target in targets) * 36
        self.target_history_tree.setFixedHeight(
            min(420, max(220, target_height + shot_height + 16))
        )
        self.history_toggle.setText(f"TARGET HISTORY · {len(targets)}")
        self.view.set_target_history(
            targets,
            self.selected_target_id,
            self._active_gun(),
        )
        self._update_history_controls()

    def _update_history_controls(self) -> None:
        if not hasattr(self, "record_impact_button"):
            return
        self.record_impact_button.setEnabled(
            self._target_by_id(self.selected_target_id) is not None
            and len(self.points) == 2
        )

    @staticmethod
    def _readout_number(text: str) -> float | None:
        try:
            return float(text.split()[0].rstrip("°"))
        except (ValueError, IndexError):
            return None

    def _record_impact_clicked(self) -> None:
        if self._target_by_id(self.selected_target_id) is None:
            return
        dialog = ShotRecordDialog(
            self._readout_number(self.solution_elevation.text()),
            self._readout_number(self.solution_tof.text()),
            self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._record_impact(dialog.record())

    def _record_impact(self, shot: ObservedShot) -> bool:
        target = self._target_by_id(self.selected_target_id)
        if target is None:
            return False
        target.shots.append(shot)
        self._target_overlay_suppressed = False
        self._refresh_target_history()
        self._update_target_overlay()
        return True

    def _map_position_hovered(self, point: QPointF | None) -> None:
        if point is None or self.current_map is None or self.transform is None:
            if hasattr(self, "cursor_readout"):
                self.cursor_readout.setText("CURSOR —")
            return
        world_delta = self.transform.world_delta(point.x(), point.y())
        world_x = self.current_map.top_left_x_metres + world_delta.x
        world_y = self.current_map.top_left_y_metres + world_delta.y
        elevation = (
            self.elevation_field.elevation_at(Point(point.x(), point.y()))
            if self.elevation_field is not None
            else None
        )
        elevation_text = (
            f"{elevation:.2f} m" if elevation is not None else "unavailable"
        )
        self.cursor_readout.setText(
            f"PIXEL {point.x():.1f}, {point.y():.1f} px   |   "
            f"WORLD X {world_x:.2f} m  Y {world_y:.2f} m   |   "
            f"ELEV {elevation_text}"
        )

    def _refresh_measurement(self) -> None:
        if self.transform is None:
            return
        if not self.points:
            self.current_range_measurement = None
            self.current_flight_time_text = "—"
            self.view.clear_target_solution()
            self._set_clearance_result(None)
            self.solution_range.setText("—")
            self.solution_bearing.clear_bearing()
            self.solution_elevation.setText("—")
            self.solution_tof.setText("—")
        elif len(self.points) == 1:
            self.current_range_measurement = None
            self.current_flight_time_text = "—"
            self.view.clear_target_solution()
            self._set_clearance_result(None)
            self.solution_range.setText("—")
            self.solution_bearing.clear_bearing()
            self.solution_elevation.setText("—")
            self.solution_tof.setText("—")
        else:
            horizontal_range = self.transform.distance_yards(
                Point(self.points[0].x(), self.points[0].y()),
                Point(self.points[1].x(), self.points[1].y()),
            )
            first_elevation = (
                self.elevation_field.elevation_at(
                    Point(self.points[0].x(), self.points[0].y())
                )
                if self.elevation_field is not None
                else None
            )
            second_elevation = (
                self.elevation_field.elevation_at(
                    Point(self.points[1].x(), self.points[1].y())
                )
                if self.elevation_field is not None
                else None
            )
            elevation_change = (
                second_elevation - first_elevation
                if first_elevation is not None and second_elevation is not None
                else None
            )
            range_measurement = RangeMeasurement(horizontal_range, elevation_change)
            self.current_range_measurement = range_measurement
            target_range = range_measurement.slant_yards
            try:
                cannon_type = self.cannon_type.currentText()
                projectile_type = self.projectile_type.currentText()
                flight_time_text = (
                    f"{artillery_time_of_flight(target_range, cannon_type, projectile_type):.3f} s"
                )
            except ValueError:
                flight_time_text = "unavailable"
            self.current_flight_time_text = flight_time_text
            pixel_dx = self.points[1].x() - self.points[0].x()
            pixel_dy = self.points[1].y() - self.points[0].y()
            bearing = map_bearing_degrees(pixel_dx, pixel_dy)
            slant_text = (
                f"{range_measurement.slant_yards:,.2f} yd"
                if elevation_change is not None
                else "unavailable"
            )
            height_text = (
                f"{elevation_change:+.2f} m"
                if elevation_change is not None
                else "unavailable"
            )
            self.solution_range.setText(
                f"H {horizontal_range:,.2f} yd\n"
                f"S {slant_text}\n"
                f"ΔH {height_text}"
            )
            if elevation_change is None:
                self.solution_range.setToolTip(
                    f"Horizontal: {horizontal_range:,.1f} yd\n"
                    "Elevation estimate unavailable"
                )
            else:
                self.solution_range.setToolTip(
                    "Mode: altitude-aware 3D slant\n"
                    f"Horizontal: {horizontal_range:,.1f} yd\n"
                    f"Slant: {range_measurement.slant_yards:,.1f} yd\n"
                    f"Gun elevation: {first_elevation:.2f} m\n"
                    f"Target elevation: {second_elevation:.2f} m\n"
                    f"Height change: {elevation_change:+.2f} m"
                )
            self.solution_bearing.set_bearing(bearing)
            self.solution_tof.setText(flight_time_text)
            self._update_ballistic_solution(
                horizontal_range,
                elevation_change if elevation_change is not None else 0.0,
            )
        self._update_history_controls()

    def _weapon_changed(self) -> None:
        if not hasattr(self, "muzzle_velocity"):
            return
        cannon = self.cannon_type.currentText()
        projectile = self.projectile_type.currentText()
        try:
            velocity, drag = ARTILLERY_PHYSICS[cannon][projectile]
            self.muzzle_velocity.setText(f"{velocity:g} m/s")
            self.drag_factor.setText(f"{drag:g} s⁻¹")
            if self.ballistic_solver is not None:
                self.ballistic_solver.set_physics_profile(velocity, drag)
        except KeyError:
            self.muzzle_velocity.setText("—")
            self.drag_factor.setText("—")
        self._refresh_measurement()
        self._refresh_target_history()

    def _estimation_range_for_fuze(self, fuze_seconds: float) -> float:
        return artillery_range_for_flight_time(
            fuze_seconds,
            self.cannon_type.currentText(),
            self.projectile_type.currentText(),
        )

    def _update_ballistic_solution(
        self,
        horizontal_range_yards: float,
        target_height_change_metres: float,
    ) -> None:
        if len(self.points) != 2 or self.ballistic_solver is None:
            self.solution_elevation.setText("—")
            self._set_clearance_result(None)
            self._update_target_overlay()
            return
        angle = self.ballistic_solver.solve(
            horizontal_range_yards,
            target_height_change_metres,
        )
        if angle is None:
            self.solution_elevation.setText("Unavailable")
            self._set_clearance_result(None)
            self._update_target_overlay()
            return
        self.solution_elevation.setText(f"{angle:.3f}°")
        self._analyze_route_clearance(
            horizontal_range_yards,
            target_height_change_metres,
        )
        self._update_target_overlay()

    def _analyze_route_clearance(
        self,
        horizontal_range_yards: float,
        target_height_change_metres: float,
    ) -> None:
        if (
            self.ballistic_solver is None
            or self.elevation_field is None
            or not self.elevation_field.samples
            or len(self.points) != 2
        ):
            self._set_clearance_result(None)
            return
        profile = self._terrain_profile_to_map_edge(horizontal_range_yards)
        if not profile:
            self._set_clearance_result(None)
            return
        try:
            speed, drag = ARTILLERY_PHYSICS[self.cannon_type.currentText()][
                self.projectile_type.currentText()
            ]
            result = self.ballistic_solver.analyze_clearance(
                horizontal_range_yards,
                target_height_change_metres,
                profile,
                speed,
                drag,
            )
        except (KeyError, ValueError):
            result = None
        self._set_clearance_result(result)

    def _terrain_profile_to_map_edge(self, target_range_yards: float):
        assert self.elevation_field is not None
        start = Point(self.points[0].x(), self.points[0].y())
        target = Point(self.points[1].x(), self.points[1].y())
        return self._terrain_profile_for_route(
            start,
            target,
            target_range_yards,
        )

    def _terrain_profile_for_route(
        self,
        start: Point,
        target: Point,
        target_range_yards: float,
    ):
        assert self.elevation_field is not None
        dx = target.x - start.x
        dy = target.y - start.y
        if dx == 0 and dy == 0:
            return ()
        width, height = self.current_image_size
        factors: list[float] = []
        if dx > 0:
            factors.append((width - start.x) / dx)
        elif dx < 0:
            factors.append((0 - start.x) / dx)
        if dy > 0:
            factors.append((height - start.y) / dy)
        elif dy < 0:
            factors.append((0 - start.y) / dy)
        positive_factors = [factor for factor in factors if factor >= 1.0]
        extension = min(positive_factors) if positive_factors else 1.0
        end = Point(
            start.x + dx * extension,
            start.y + dy * extension,
        )
        return self.elevation_field.profile_along_line(
            start,
            end,
            target_range_yards * extension,
            spacing_yards=5.0,
        )

    def _set_clearance_result(
        self,
        result: TrajectoryClearanceResult | None,
    ) -> None:
        self.current_clearance_result = result
        self.trajectory_profile.set_result(result)
        if result is None:
            self.clearance_status.setText(
                'ESTIMATED ROUTE: <span style="color:#9ba392;">UNAVAILABLE</span>'
            )
            self.clearance_details.clear()
            self.clearance_details.hide()
            self.view.clear_trajectory_overlay()
            return
        if result.obstructed:
            self.clearance_status.setText(
                'ESTIMATED ROUTE: <span style="color:#ff7a70; '
                'font-weight:700;">OBSTRUCTED</span>'
            )
            obstruction = (
                f"{result.first_obstruction_yards:,.0f} yd"
                if result.first_obstruction_yards is not None
                else "unknown"
            )
            clearing = (
                f"{result.clearing_elevation_deg:.3f}°"
                if result.clearing_elevation_deg is not None
                else "no clearing solution"
            )
            impact = (
                f"{result.impact_range_yards:,.0f} yd"
                if result.impact_range_yards is not None
                else "outside sampled map"
            )
            target_height = (
                f"{result.height_above_target_metres * METRES_TO_YARDS:+.1f} yd "
                f"({result.height_above_target_metres:+.1f} m)"
                if result.height_above_target_metres is not None
                else "unavailable"
            )
            self.clearance_details.setText(
                f"First obstruction: {obstruction}\n"
                f"Minimum clearance: {result.minimum_clearance_metres:+.1f} m\n"
                f"Current elevation: {result.original_elevation_deg:.3f}°\n"
                f"Clearance elevation: {clearing}\n"
                f"Predicted height over target: {target_height}\n"
                f"Downrange impact: {impact}"
            )
        else:
            self.clearance_status.setText(
                'ESTIMATED ROUTE: <span style="color:#63d785; '
                'font-weight:700;">CLEAR</span>'
            )
            minimum = (
                f"{result.minimum_clearance_metres:+.1f} m"
                if result.minimum_clearance_metres is not None
                else "unavailable"
            )
            target_height = (
                f"{result.height_above_target_metres * METRES_TO_YARDS:+.1f} yd "
                f"({result.height_above_target_metres:+.1f} m)"
                if result.height_above_target_metres is not None
                else "unavailable"
            )
            self.clearance_details.setText(
                f"Minimum clearance: {minimum}\n"
                f"Elevation: {result.original_elevation_deg:.3f}°\n"
                f"Predicted height over target: {target_height}"
            )
        self.clearance_details.show()
        impact_for_overlay = (
            result.impact_range_yards
            if result.overshoot_yards is not None
            and abs(result.overshoot_yards) >= 1.0
            else None
        )
        self.view.set_trajectory_overlay(
            result.target_range_yards,
            result.first_obstruction_yards,
            impact_for_overlay,
        )

    def _update_target_overlay(self) -> None:
        if (
            self._target_overlay_suppressed
            or len(self.points) != 2
            or self.current_range_measurement is None
        ):
            self.view.clear_target_solution()
            return
        self.view.set_target_solution(
            self.current_range_measurement.slant_yards,
            self.current_flight_time_text,
            self.solution_elevation.text(),
        )

    def _reset_measurement(self) -> None:
        self.points.clear()
        self._set_active_gun(None)
        self.selected_target_id = None
        self._target_overlay_suppressed = False
        self.current_range_measurement = None
        self.current_flight_time_text = "—"
        self.view.clear_points()
        self._set_clearance_result(None)
        self.solution_range.setText("—")
        self.solution_bearing.clear_bearing()
        self.solution_elevation.setText("—")
        self.solution_tof.setText("—")
        self._refresh_target_history()

    def _update_map_info(self) -> None:
        width, height = self.current_image_size
        pixel_size = f"{width:,} × {height:,} px"
        if self.current_map is None or self.transform is None:
            self.map_info.setText(
                f"Map size: {pixel_size}   •   Game calibration unavailable"
            )
            return
        yard_width = self.current_map.width_metres * 1.0936132983377078
        yard_height = self.current_map.height_metres * 1.0936132983377078
        elevation_text = "unavailable"
        if self.elevation_field is not None and self.elevation_field.samples:
            contrast = self.elevation_field.contrast_range_metres()
            contrast_text = (
                f" / contrast {contrast[0]:.1f}–{contrast[1]:.1f} m"
                if contrast is not None
                else ""
            )
            elevation_text = (
                f"{len(self.elevation_field.samples):,} anchors / "
                f"{self.elevation_field.minimum_metres:.1f}–"
                f"{self.elevation_field.maximum_metres:.1f} m"
                f"{contrast_text}"
            )
        self.map_info.setText(
            f"SOURCE    GAME PAK\n"
            f"IMAGE     {pixel_size}\n"
            f"AREA      {yard_width:,.0f} × {yard_height:,.0f} yd\n"
            f"SCALE     {self.transform.mean_yards_per_pixel:.4f} yd/px\n"
            f"ROTATION  {self.current_map.rotation_degrees:.2f}°\n"
            f"ELEVATION {elevation_text} (sampled)"
        )

    def _open_calibration(self) -> None:
        if self.current_map is None:
            return
        dialog = CalibrationDialog(self.current_map, self)
        dialog.calibration_saved.connect(self._calibration_saved)
        dialog.exec()

    def _calibration_saved(self, image_path: Path, scale: float) -> None:
        if self.current_map and self.current_map.image_path == image_path:
            self.resolution = scale
            self.points.clear()
            self._set_active_gun(None)
            self.view.set_interaction_enabled(True)
            self.view.set_range_scale(scale)
            self._update_map_info()
            self.calibrate_button.setText("Recalibrate…")
            self.calibrate_button.setStyleSheet("")
            self.warning_banner.hide()


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("worCalc")
    window = MainWindow(MAPS_DIR)
    window.show()
    return app.exec()
