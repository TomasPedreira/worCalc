from __future__ import annotations

import re
import struct
import zipfile
from dataclasses import dataclass
from functools import lru_cache
from math import isfinite
from pathlib import Path

from .catalog import MapRecord
from .gun_spawns import gun_spawns_for_map


# CryEngine stores position fields under stable hashed names immediately before
# each printable entity name. War of Rights orders them elevation, world X, Y.
_POSITIONED_NAME = re.compile(
    rb"\xaf\x77\xd2\x62(.{4})\x83\x16\xdc\x8c(.{4})"
    rb"\x15\x26\xdb\xfb(.{4})([ -~]{3,120})\x00",
    re.DOTALL,
)


@dataclass(frozen=True)
class WorldEntity:
    name: str
    elevation: float
    world_x: float
    world_y: float
    kind: str
    faction: str | None


@dataclass(frozen=True)
class WorldPositionSample:
    name: str
    elevation: float
    world_x: float
    world_y: float


@dataclass(frozen=True)
class MapLocation:
    name: str
    pixel_x: float
    pixel_y: float
    kind: str
    faction: str | None
    elevation_metres: float | None = None
    world_x: float | None = None
    world_y: float | None = None


def _classify(name: str) -> tuple[str, str | None] | None:
    folded = name.casefold()
    faction = "USA" if "usa" in folded else "CSA" if "csa" in folded else None
    artillery = "artillery" in folded or "_arty" in folded or "arty_" in folded
    if "spawnpoint" in folded and artillery:
        return "battery", faction
    if "spawnpoint" in folded:
        return "spawn", faction
    if folded.startswith("victory_"):
        return "objective", None
    if folded.endswith("_victorysequence"):
        return "objective", None
    if folded.endswith("capturearea") and "target" not in folded and "icon" not in folded:
        return "objective", None
    return None


def parse_position_samples(data: bytes) -> tuple[WorldPositionSample, ...]:
    samples: list[WorldPositionSample] = []
    for match in _POSITIONED_NAME.finditer(data):
        elevation, world_x, world_y = (
            struct.unpack("<f", match.group(index))[0] for index in (1, 2, 3)
        )
        if not all(isfinite(value) for value in (elevation, world_x, world_y)):
            continue
        name = match.group(4).decode("ascii", errors="ignore")
        samples.append(WorldPositionSample(name, elevation, world_x, world_y))
    return tuple(samples)


def parse_world_entities(data: bytes) -> tuple[WorldEntity, ...]:
    entities: list[WorldEntity] = []
    for sample in parse_position_samples(data):
        name = sample.name
        classification = _classify(name)
        if classification is None:
            continue
        kind, faction = classification
        entities.append(
            WorldEntity(
                name,
                sample.elevation,
                sample.world_x,
                sample.world_y,
                kind,
                faction,
            )
        )
    return tuple(entities)


@lru_cache(maxsize=8)
def load_battlefield_entities(level_pak: Path) -> tuple[WorldEntity, ...]:
    if not level_pak.is_file():
        return ()
    try:
        with zipfile.ZipFile(level_pak) as archive:
            return parse_world_entities(archive.read("objects.cgb"))
    except (OSError, KeyError, zipfile.BadZipFile):
        return ()


@lru_cache(maxsize=8)
def load_battlefield_position_samples(
    level_pak: Path,
) -> tuple[WorldPositionSample, ...]:
    if not level_pak.is_file():
        return ()
    try:
        with zipfile.ZipFile(level_pak) as archive:
            return parse_position_samples(archive.read("objects.cgb"))
    except (OSError, KeyError, zipfile.BadZipFile):
        return ()


def _belongs_to_selected_layer(entity: WorldEntity, record: MapRecord) -> bool:
    conquest = re.fullmatch(r"Conquest_(\d+)", record.layer, re.IGNORECASE)
    if conquest:
        number = conquest.group(1)
        folded = entity.name.casefold()
        return folded.startswith(f"cq{number}_spawnpoint".casefold()) or (
            folded == f"victory_conquest_{number}".casefold()
        )

    if record.mode.casefold() == "drillcamp":
        faction = "USA" if "USA" in record.layer.upper() else "CSA"
        return entity.name.casefold().startswith(f"spawnpoint-{faction}-".casefold())

    if record.mode.casefold() == "skirmish":
        suffix = re.sub(r"^Skirmish_", "", record.layer, flags=re.IGNORECASE)
        numbered = re.match(r"(\d+)_(.+)", suffix)
        sequence = numbered.group(1) if numbered else None
        suffix = numbered.group(2) if numbered else suffix
        words = re.findall(r"[A-Za-z0-9]+", suffix)
        acronym = "".join(word[0] for word in words)
        acronym = {
            "Crossroads": "CR",
            "East_Woods_Hood_Push": "EW",
            "Pry_Ford": "PFord",
        }.get(suffix, acronym)
        folded = entity.name.casefold()
        victory_names = {f"victory_{suffix}".casefold()}
        if suffix.casefold() == "high_street":
            victory_names.add("victory_hight_street")
        return (
            folded.startswith(f"spawnpoint_{acronym}_".casefold())
            or folded in victory_names
            or (sequence is not None and folded == f"skirmish_{sequence}_victorysequence".casefold())
        )

    if record.mode.casefold() == "picketpatrol":
        return entity.name.casefold().startswith(
            f"spawnpoint_{record.layer}_".casefold()
        )

    if record.mode.casefold() == "ltmonslaught":
        return entity.name.casefold().startswith("ltmonslaught_")

    # The calibrated crop remains a final bounds check for any future modes.
    return True


def locations_for_map(
    record: MapRecord,
    image_width: int,
    image_height: int,
    paks_root: Path,
) -> list[MapLocation]:
    level_pak = paks_root / record.battlefield / "level.pak"
    locations: list[MapLocation] = []
    for entity in load_battlefield_entities(level_pak.resolve()):
        if not _belongs_to_selected_layer(entity, record):
            continue
        delta = record.calibration.pixel_delta_for_world_units(
            entity.world_x - record.top_left_x_metres,
            entity.world_y - record.top_left_y_metres,
        )
        if not (0 <= delta.x <= image_width and 0 <= delta.y <= image_height):
            continue
        locations.append(
            MapLocation(
                name=entity.name,
                pixel_x=delta.x,
                pixel_y=delta.y,
                kind=entity.kind,
                faction=entity.faction,
                elevation_metres=entity.elevation,
                world_x=entity.world_x,
                world_y=entity.world_y,
            )
        )
    for gun in gun_spawns_for_map(record, paks_root):
        delta = record.calibration.pixel_delta_for_world_units(
            gun.world_x - record.top_left_x_metres,
            gun.world_y - record.top_left_y_metres,
        )
        if 0 <= delta.x <= image_width and 0 <= delta.y <= image_height:
            locations.append(MapLocation(
                name=f"{gun.cannon} · {gun.name}",
                pixel_x=delta.x, pixel_y=delta.y, kind="gun_spawn", faction=None,
                elevation_metres=gun.elevation, world_x=gun.world_x, world_y=gun.world_y,
            ))
    return locations
