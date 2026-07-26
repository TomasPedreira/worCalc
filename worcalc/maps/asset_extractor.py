"""Build worCalc's runtime map data directly from a game Assets directory."""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
import shutil
import zipfile
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from PIL import Image


METRES_TO_YARDS = 1.0936132983377078
PAK_IMAGE_SIZE = 2048


def resolve_assets_directory(path: Path) -> Path:
    """Accept either Assets itself or its parent game directory."""
    candidate = path.expanduser().resolve()
    if (candidate / "LevelsLooseFiles.pak").is_file():
        return candidate
    nested = candidate / "Assets"
    if (nested / "LevelsLooseFiles.pak").is_file():
        return nested
    raise FileNotFoundError(
        f"Assets directory not found at {candidate} or {nested}"
    )


def open_cryengine_entry(
    archive: zipfile.ZipFile, info: zipfile.ZipInfo
) -> BinaryIO:
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


def safe_output_path(root: Path, archive_name: str) -> Path:
    relative = PurePosixPath(archive_name)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"unsafe archive path: {archive_name!r}")
    destination = root.joinpath(*relative.parts)
    destination.resolve().relative_to(root.resolve())
    return destination


def relaxed_json(text: str) -> object:
    return json.loads(re.sub(r",\s*([}\]])", r"\1", text))


def definition_areas(document: dict[str, object]) -> list[dict[str, object]]:
    for component in document.get("Components", []):
        if component.get("Type") == "GameplayAreaManager":
            return component.get("GameplayAreas", [])
    raise ValueError("no GameplayAreaManager component")


def map_descriptor(area: dict[str, object]) -> dict[str, float]:
    for descriptor in area.get("Descriptors", []):
        if descriptor.get("Type") == "UserInterfaceDescriptor" and "Map" in descriptor:
            return descriptor["Map"]
    raise ValueError(f"no UserInterfaceDescriptor.Map for {area.get('Name')!r}")


def display_name(battlefield: str, mode: str, name: str, index: int) -> str:
    if mode in {"Conquest", "Contention", "Skirmish", "DrillCamp"}:
        return name
    if mode == "PicketPatrol":
        return f"Picket Patrol {index + 1:02d}"
    if mode == "LTMOnslaught":
        names = {
            "Antietam": "Antietam (Onslaught)",
            "DrillCamp": "Drill Camp (Onslaught)",
            "HarpersFerry": "Harpers Ferry (Onslaught)",
            "SouthMountain": "South Mountain (Onslaught)",
        }
        return names[battlefield]
    raise ValueError(f"unsupported mode: {battlefield}/{mode}")


def _extract_minimaps(assets: Path, maps_output: Path) -> list[Path]:
    outputs: list[Path] = []
    archives = sorted(assets.glob("Minimaps_*.pak"))
    if not archives:
        raise FileNotFoundError(f"No Minimaps_*.pak archives found in {assets}")
    for archive_path in archives:
        battlefield = archive_path.stem.removeprefix("Minimaps_")
        with zipfile.ZipFile(archive_path) as archive:
            for info in archive.infolist():
                name = info.filename.replace("\\", "/")
                if (
                    info.is_dir()
                    or not name.lower().endswith(".dds")
                    or "gameplayarea_" not in name.lower()
                ):
                    continue
                destination = safe_output_path(
                    maps_output / battlefield,
                    str(PurePosixPath(name).with_suffix(".png")),
                )
                destination.parent.mkdir(parents=True, exist_ok=True)
                with open_cryengine_entry(archive, info) as source:
                    payload = source.read()
                with Image.open(io.BytesIO(payload)) as texture:
                    texture.getchannel("A").save(destination, format="PNG")
                outputs.append(destination)
    if not outputs:
        raise ValueError("No GameplayArea_*.dds textures found in minimap archives")
    return outputs


def _copy_level_paks(assets: Path, output_root: Path, battlefields: set[str]) -> None:
    for battlefield in sorted(battlefields):
        source = assets / "Levels" / battlefield / "level.pak"
        if not source.is_file():
            raise FileNotFoundError(f"Missing level archive: {source}")
        destination = output_root / battlefield / "level.pak"
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.is_file() or destination.stat().st_size != source.stat().st_size:
            shutil.copy2(source, destination)


def _map_corners(coordinates: dict[str, object]) -> tuple[
    tuple[float, float], tuple[float, float], tuple[float, float]
]:
    required = {
        "TopLeftX",
        "TopLeftY",
        "TopRightX",
        "TopRightY",
        "BottomRightX",
        "BottomRightY",
    }
    if required.issubset(coordinates):
        return (
            (float(coordinates["TopLeftX"]), float(coordinates["TopLeftY"])),
            (float(coordinates["TopRightX"]), float(coordinates["TopRightY"])),
            (
                float(coordinates["BottomRightX"]),
                float(coordinates["BottomRightY"]),
            ),
        )
    if "Center" in coordinates and "Size" in coordinates:
        center_x, center_y = (float(value) for value in coordinates["Center"])
        half_size = float(coordinates["Size"]) / 2.0
        return (
            (center_x - half_size, center_y + half_size),
            (center_x + half_size, center_y + half_size),
            (center_x + half_size, center_y - half_size),
        )
    raise ValueError(f"incomplete map coordinates: {coordinates}")


def _build_catalog(
    assets: Path, output_root: Path, map_paths: list[Path]
) -> list[dict[str, object]]:
    maps_root = output_root / "converted_minimaps"
    grouped: dict[tuple[str, str], list[Path]] = {}
    for path in map_paths:
        relative = path.relative_to(maps_root)
        grouped.setdefault((relative.parts[0], relative.parts[-2]), []).append(path)

    rows: list[dict[str, object]] = []
    with zipfile.ZipFile(assets / "LevelsLooseFiles.pak") as archive:
        entries = {entry.filename.replace("\\", "/"): entry for entry in archive.infolist()}
        for (battlefield, mode), paths in sorted(grouped.items()):
            if (battlefield, mode) == ("HarpersFerry", "DrillCamp"):
                continue
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
            for index, (area, image_path) in enumerate(zip(areas, paths, strict=True)):
                tl, tr, br = _map_corners(map_descriptor(area))
                width_m = math.dist(tl, tr)
                height_m = math.dist(tr, br)
                world_dx = (tr[0] - tl[0], tr[1] - tl[1])
                world_dy = (br[0] - tr[0], br[1] - tr[1])
                dot = world_dx[0] * world_dy[0] + world_dx[1] * world_dy[1]
                axis_angle = math.degrees(
                    math.acos(max(-1.0, min(1.0, dot / (width_m * height_m))))
                )
                rows.append(
                    {
                        "battlefield": battlefield,
                        "mode": mode,
                        "gameplay_area": index,
                        "name": display_name(
                            battlefield, mode, str(area["Name"]), index
                        ),
                        "layer": area.get("Layer", ""),
                        "top_left_x_m": tl[0],
                        "top_left_y_m": tl[1],
                        "top_right_x_m": tr[0],
                        "top_right_y_m": tr[1],
                        "bottom_right_x_m": br[0],
                        "bottom_right_y_m": br[1],
                        "width_m": round(width_m, 6),
                        "height_m": round(height_m, 6),
                        "rotation_degrees": round(
                            math.degrees(math.atan2(world_dx[1], world_dx[0])), 6
                        ),
                        "axis_angle_degrees": round(axis_angle, 6),
                        "pak_width_px": PAK_IMAGE_SIZE,
                        "pak_height_px": PAK_IMAGE_SIZE,
                        "pak_x_metres_per_pixel": round(width_m / PAK_IMAGE_SIZE, 9),
                        "pak_y_metres_per_pixel": round(height_m / PAK_IMAGE_SIZE, 9),
                        "pak_x_yards_per_pixel": round(
                            width_m / PAK_IMAGE_SIZE * METRES_TO_YARDS, 9
                        ),
                        "pak_y_yards_per_pixel": round(
                            height_m / PAK_IMAGE_SIZE * METRES_TO_YARDS, 9
                        ),
                        "pak_pixel_x_to_world_x_m": round(
                            world_dx[0] / PAK_IMAGE_SIZE, 9
                        ),
                        "pak_pixel_x_to_world_y_m": round(
                            world_dx[1] / PAK_IMAGE_SIZE, 9
                        ),
                        "pak_pixel_y_to_world_x_m": round(
                            world_dy[0] / PAK_IMAGE_SIZE, 9
                        ),
                        "pak_pixel_y_to_world_y_m": round(
                            world_dy[1] / PAK_IMAGE_SIZE, 9
                        ),
                        "pak_path": str(
                            image_path.relative_to(output_root.parent)
                        ).replace("\\", "/"),
                        "definition": entry_name,
                    }
                )
    return rows


def extract_assets(assets_path: Path, output_root: Path) -> int:
    assets = resolve_assets_directory(assets_path)
    output = output_root.expanduser().resolve()
    maps_output = output / "converted_minimaps"
    map_paths = _extract_minimaps(assets, maps_output)
    battlefields = {path.relative_to(maps_output).parts[0] for path in map_paths}
    _copy_level_paks(assets, output, battlefields)
    rows = _build_catalog(assets, output, map_paths)
    if not rows:
        raise ValueError("No gameplay-area calibrations were generated")
    output.mkdir(parents=True, exist_ok=True)
    csv_path = output / "gameplay_area_calibrations.csv"
    json_path = output / "gameplay_area_calibrations.json"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    json_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "assets",
        type=Path,
        help="path to the game's Assets directory (or its parent game directory)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "paks",
        help="runtime map-data output directory (default: <project>/paks)",
    )
    args = parser.parse_args()
    count = extract_assets(args.assets, args.output)
    print(f"Extracted {count} gameplay-area maps to {args.output.resolve()}")


if __name__ == "__main__":
    main()
