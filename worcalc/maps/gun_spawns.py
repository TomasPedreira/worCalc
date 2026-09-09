"""Read placed playable guns from the compiled level's layer hierarchy."""

from __future__ import annotations

import struct
import zipfile
import zlib
from dataclasses import dataclass
from functools import lru_cache
from math import isfinite
from pathlib import Path

from .catalog import MapRecord


# GameData.pak / Generated/archetype_database_migration.xml. Match archetypes,
# not entity names: most current guns are named Entity-<number>; scenery also
# contains cannon-shaped models. Limber archetypes are intentionally excluded.
GUN_ARCHETYPES = {
    3437346673: "3-inch Ordnance",
    2197219489: "10-pounder Parrott",
    797844681: "12-pounder Napoleon (USA)",
    4007736817: "12-pounder Napoleon (CSA)",
}


@dataclass(frozen=True)
class GunSpawn:
    name: str
    cannon: str
    layers: tuple[str, ...]
    world_x: float
    world_y: float
    elevation: float


class _CompiledLevel:
    """Bounded reader for the CGB object/array subset used by level layers.

    Object headers hold a field count and a forward word offset to a table.
    Table entries use lowercase CRC32 keys; pointer values are backward byte
    offsets from the key. Arrays encode their count above bit 9 and contain
    forward word offsets relative to each element slot.
    """

    def __init__(self, data: bytes):
        self.data = data
        if data[:4] != b"CGB " or self.uint(4) != len(data) - 8:
            raise ValueError("Invalid compiled level header")

    def uint(self, offset: int) -> int:
        if offset < 0 or offset + 4 > len(self.data):
            raise ValueError("Compiled level offset outside file")
        return struct.unpack_from("<I", self.data, offset)[0]

    def fields(self, offset: int) -> dict[int, int]:
        count = self.uint(offset)
        start = offset + 4 + self.uint(offset + 4) * 4
        if count > 1024 or start + count * 8 > len(self.data):
            raise ValueError("Invalid compiled object table")
        return {self.uint(p): p for p in range(start, start + count * 8, 8)}

    def field(self, fields: dict[int, int], name: str) -> int:
        return fields[zlib.crc32(name.encode("ascii"))]

    def pointer(self, slot: int) -> int:
        offset = slot - self.uint(slot + 4)
        self.uint(offset)
        return offset

    def array(self, offset: int) -> list[int]:
        count = self.uint(offset) >> 10
        if offset + 8 + count * 4 > len(self.data):
            raise ValueError("Invalid compiled array")
        return [p + self.uint(p) * 4
                for p in range(offset + 8, offset + 8 + count * 4, 4)]

    def members(self, fields: dict[int, int], name: str) -> list[int]:
        key = zlib.crc32(name.encode("ascii"))
        return self.array(self.pointer(fields[key])) if key in fields else []

    def name(self, fields: dict[int, int]) -> str:
        offset = self.pointer(self.field(fields, "name"))
        end = self.data.index(b"\0", offset, min(offset + 1024, len(self.data)))
        return self.data[offset:end].decode("utf-8")


def parse_gun_spawns(data: bytes) -> tuple[GunSpawn, ...]:
    reader = _CompiledLevel(data)
    result: list[GunSpawn] = []
    visited: set[int] = set()

    def visit(offset: int, ancestors: tuple[str, ...]) -> None:
        if offset in visited or len(ancestors) > 64:
            raise ValueError("Invalid compiled layer hierarchy")
        visited.add(offset)
        layer = reader.fields(offset)
        path = (*ancestors, reader.name(layer))
        for entity_offset in reader.members(layer, "entities"):
            fields = reader.fields(entity_offset)
            archetype_slot = fields.get(zlib.crc32(b"archetype_id"))
            if archetype_slot is None:
                continue
            cannon = GUN_ARCHETYPES.get(reader.uint(archetype_slot + 4))
            if cannon is None:
                continue
            position = reader.fields(reader.pointer(reader.field(fields, "position")))
            xyz = tuple(struct.unpack_from("<f", data, reader.field(position, axis) + 4)[0]
                        for axis in ("x", "y", "z"))
            if not all(isfinite(value) for value in xyz):
                raise ValueError("Non-finite gun position")
            result.append(GunSpawn(reader.name(fields), cannon, path, *xyz))
        for child in reader.members(layer, "children"):
            visit(child, path)

    for layer in reader.members(reader.fields(8), "layers"):
        visit(layer, ())
    return tuple(result)


@lru_cache(maxsize=8)
def load_gun_spawns(level_pak: Path) -> tuple[GunSpawn, ...]:
    try:
        with zipfile.ZipFile(level_pak) as archive:
            return parse_gun_spawns(archive.read("objects.cgb"))
    except (OSError, KeyError, ValueError, struct.error, zipfile.BadZipFile):
        # Unsupported/missing data must not become guessed spawn locations.
        return ()


def gun_spawns_for_map(record: MapRecord, paks_root: Path) -> tuple[GunSpawn, ...]:
    selected = record.layer.casefold()
    return tuple(
        gun for gun in load_gun_spawns((paks_root / record.battlefield / "level.pak").resolve())
        if (selected and selected in (layer.casefold() for layer in gun.layers))
        or (record.battlefield == "DrillCamp" and record.mode == "DrillCamp"
            and gun.layers == ("Artillery",))
    )
