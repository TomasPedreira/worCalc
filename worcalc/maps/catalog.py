from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..domain.calibration import AffineCalibration


MODE_DISPLAY_NAMES = {
    "DrillCamp": "Drill Camp",
    "LTMOnslaught": "Onslaught",
    "PicketPatrol": "Picket Patrol",
}


@dataclass(frozen=True)
class MapRecord:
    name: str
    image_path: Path
    battlefield: str
    mode: str
    gameplay_area: int
    width_metres: float
    height_metres: float
    rotation_degrees: float
    calibration: AffineCalibration
    layer: str = ""
    top_left_x_metres: float = 0.0
    top_left_y_metres: float = 0.0

    @property
    def tree_parts(self) -> tuple[str, str, str]:
        return self.battlefield, self.mode_name, self.name

    @property
    def mode_name(self) -> str:
        return MODE_DISPLAY_NAMES.get(self.mode, self.mode)

    @property
    def config_path(self) -> Path:
        """Legacy manual-calibration path, retained for editor compatibility."""
        return self.image_path.parent / "res.config"


def load_map_catalog(catalog_path: Path) -> list[MapRecord]:
    """Load the authoritative gameplay-area names and map transforms."""
    if not catalog_path.is_file():
        return []
    rows = json.loads(catalog_path.read_text(encoding="utf-8"))
    records: list[MapRecord] = []
    for row in rows:
        raw_path = Path(row["pak_path"])
        if raw_path.is_absolute():
            image_path = raw_path
        else:
            project_relative = catalog_path.parent.parent / raw_path
            catalog_relative = catalog_path.parent / raw_path
            image_path = project_relative if project_relative.is_file() else catalog_relative
        if not image_path.is_file():
            continue
        records.append(
            MapRecord(
                name=str(row["name"]),
                image_path=image_path.resolve(),
                battlefield=str(row["battlefield"]),
                mode=str(row["mode"]),
                gameplay_area=int(row["gameplay_area"]),
                width_metres=float(row["width_m"]),
                height_metres=float(row["height_m"]),
                rotation_degrees=float(row["rotation_degrees"]),
                calibration=AffineCalibration(
                    pixel_x_world_x=float(row["pak_pixel_x_to_world_x_m"]),
                    pixel_x_world_y=float(row["pak_pixel_x_to_world_y_m"]),
                    pixel_y_world_x=float(row["pak_pixel_y_to_world_x_m"]),
                    pixel_y_world_y=float(row["pak_pixel_y_to_world_y_m"]),
                ),
                layer=str(row.get("layer", "")),
                top_left_x_metres=float(row.get("top_left_x_m", 0.0)),
                top_left_y_metres=float(row.get("top_left_y_m", 0.0)),
            )
        )
    return sorted(
        records,
        key=lambda record: (
            record.battlefield.casefold(),
            record.mode.casefold(),
            record.gameplay_area,
        ),
    )
