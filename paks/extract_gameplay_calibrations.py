"""Extract authoritative gameplay-area map bounds from War of Rights assets."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ASSETS = ROOT / "Assets"
PAK_MAPS = ROOT / "paks" / "converted_minimaps"
OUTPUT_CSV = ROOT / "paks" / "gameplay_area_calibrations.csv"
OUTPUT_JSON = ROOT / "paks" / "gameplay_area_calibrations.json"
METRES_TO_YARDS = 1.0936132983377078
PAK_IMAGE_SIZE = 2048


def relaxed_json(text: str) -> object:
    """Parse the game's JSON-like files, which permit trailing commas."""
    return json.loads(re.sub(r",\s*([}\]])", r"\1", text))


def open_cryengine_entry(
    archive: zipfile.ZipFile, info: zipfile.ZipInfo
):
    try:
        return archive.open(info)
    except zipfile.BadZipFile as error:
        if "File name in directory" not in str(error) or "/" not in info.orig_filename:
            raise
        original_name = info.orig_filename
        info.orig_filename = original_name.replace("/", "\\")
        try:
            return archive.open(info)
        finally:
            info.orig_filename = original_name


def display_name(battlefield: str, mode: str, name: str, index: int) -> str:
    if mode in {"Conquest", "Contention", "Skirmish", "DrillCamp"}:
        return name
    if mode == "PicketPatrol":
        return f"Picket Patrol {index + 1:02d}"
    if mode == "LTMOnslaught":
        return {
            "Antietam": "Antietam (Onslaught)",
            "DrillCamp": "Drill Camp (Onslaught)",
            "HarpersFerry": "Harpers Ferry (Onslaught)",
            "SouthMountain": "South Mountain (Onslaught)",
        }[battlefield]
    raise ValueError(f"unsupported mode: {battlefield}/{mode}")


def map_descriptor(area: dict[str, object]) -> dict[str, float]:
    for descriptor in area.get("Descriptors", []):
        if descriptor.get("Type") == "UserInterfaceDescriptor" and "Map" in descriptor:
            return descriptor["Map"]
    raise ValueError(f"no UserInterfaceDescriptor.Map for {area.get('Name')!r}")


def definition_areas(document: dict[str, object]) -> list[dict[str, object]]:
    for component in document.get("Components", []):
        if component.get("Type") == "GameplayAreaManager":
            return component.get("GameplayAreas", [])
    raise ValueError("no GameplayAreaManager component")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, default=DEFAULT_ASSETS)
    args = parser.parse_args()

    archive_path = args.assets / "LevelsLooseFiles.pak"
    if not archive_path.is_file():
        raise SystemExit(f"Missing archive: {archive_path}")
    pak_paths = sorted(PAK_MAPS.rglob("GameplayArea_*.png"))
    grouped_paths: dict[tuple[str, str], list[Path]] = {}
    for path in pak_paths:
        relative = path.relative_to(PAK_MAPS)
        grouped_paths.setdefault((relative.parts[0], relative.parts[-2]), []).append(path)

    rows: list[dict[str, object]] = []
    with zipfile.ZipFile(archive_path) as archive:
        entries = {entry.filename: entry for entry in archive.infolist()}
        for (battlefield, mode), paths in sorted(grouped_paths.items()):
            entry_name = f"Levels/{battlefield}/Definitions/{mode}.json"
            entry = entries.get(entry_name)
            if entry is None:
                raise ValueError(f"definition missing from archive: {entry_name}")
            with open_cryengine_entry(archive, entry) as handle:
                document = relaxed_json(handle.read().decode("utf-8-sig"))
            areas = definition_areas(document)
            paths.sort(key=lambda path: int(path.stem.rsplit("_", 1)[1]))
            if len(areas) != len(paths):
                raise ValueError(
                    f"area/texture count mismatch for {battlefield}/{mode}: "
                    f"{len(areas)} vs {len(paths)}"
                )

            for index, (area, pak_path) in enumerate(zip(areas, paths, strict=True)):
                coordinates = map_descriptor(area)
                required_coordinates = {
                    "TopLeftX",
                    "TopLeftY",
                    "TopRightX",
                    "TopRightY",
                    "BottomRightX",
                    "BottomRightY",
                }
                if required_coordinates.issubset(coordinates):
                    tl = (float(coordinates["TopLeftX"]), float(coordinates["TopLeftY"]))
                    tr = (float(coordinates["TopRightX"]), float(coordinates["TopRightY"]))
                    br = (
                        float(coordinates["BottomRightX"]),
                        float(coordinates["BottomRightY"]),
                    )
                elif "Center" in coordinates and "Size" in coordinates:
                    center_x, center_y = (float(value) for value in coordinates["Center"])
                    half_size = float(coordinates["Size"]) / 2.0
                    tl = (center_x - half_size, center_y + half_size)
                    tr = (center_x + half_size, center_y + half_size)
                    br = (center_x + half_size, center_y - half_size)
                else:
                    raise ValueError(
                        f"incomplete map coordinates for {battlefield}/{mode}/"
                        f"GameplayArea_{index}: {coordinates}"
                    )
                width_m = math.dist(tl, tr)
                height_m = math.dist(tr, br)
                name = display_name(battlefield, mode, str(area["Name"]), index)
                world_dx = (tr[0] - tl[0], tr[1] - tl[1])
                world_dy = (br[0] - tr[0], br[1] - tr[1])
                dot = world_dx[0] * world_dy[0] + world_dx[1] * world_dy[1]
                axis_angle = math.degrees(
                    math.acos(max(-1.0, min(1.0, dot / (width_m * height_m))))
                )
                row = {
                    "battlefield": battlefield,
                    "mode": mode,
                    "gameplay_area": index,
                    "name": name,
                    "layer": area.get("Layer", ""),
                    "top_left_x_m": tl[0],
                    "top_left_y_m": tl[1],
                    "top_right_x_m": tr[0],
                    "top_right_y_m": tr[1],
                    "bottom_right_x_m": br[0],
                    "bottom_right_y_m": br[1],
                    "width_m": round(width_m, 6),
                    "height_m": round(height_m, 6),
                    "rotation_degrees": round(math.degrees(math.atan2(tr[1] - tl[1], tr[0] - tl[0])), 6),
                    "axis_angle_degrees": round(axis_angle, 6),
                    "pak_width_px": PAK_IMAGE_SIZE,
                    "pak_height_px": PAK_IMAGE_SIZE,
                    "pak_x_metres_per_pixel": round(width_m / PAK_IMAGE_SIZE, 9),
                    "pak_y_metres_per_pixel": round(height_m / PAK_IMAGE_SIZE, 9),
                    "pak_x_yards_per_pixel": round(width_m / PAK_IMAGE_SIZE * METRES_TO_YARDS, 9),
                    "pak_y_yards_per_pixel": round(height_m / PAK_IMAGE_SIZE * METRES_TO_YARDS, 9),
                    "pak_pixel_x_to_world_x_m": round(world_dx[0] / PAK_IMAGE_SIZE, 9),
                    "pak_pixel_x_to_world_y_m": round(world_dx[1] / PAK_IMAGE_SIZE, 9),
                    "pak_pixel_y_to_world_x_m": round(world_dy[0] / PAK_IMAGE_SIZE, 9),
                    "pak_pixel_y_to_world_y_m": round(world_dy[1] / PAK_IMAGE_SIZE, 9),
                    "pak_path": str(pak_path.relative_to(ROOT)).replace("\\", "/"),
                    "definition": entry_name,
                }
                rows.append(row)

    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    OUTPUT_JSON.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"Extracted {len(rows)} authoritative gameplay-area calibrations")
    print(f"CSV: {OUTPUT_CSV}")
    print(f"JSON: {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
