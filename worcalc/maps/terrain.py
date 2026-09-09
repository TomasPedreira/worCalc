"""Read WoR's compiled CryEngine terrain (chunk 28, terrain nodes 7).

The format and interpolation are described in docs/terrain-decoding.md.
No game assets are modified. Unsupported/corrupt formats fail explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from math import floor, isfinite
from pathlib import Path
from struct import Struct
from types import MappingProxyType
from typing import Mapping
import zipfile


HEADER = Struct("<4B5i2f")
NODE = Struct("<2h8f2i")
U16 = Struct("<H")
I32 = Struct("<i")
F32 = Struct("<f")


class TerrainFormatError(ValueError):
    """The terrain cannot be decoded reliably by this reader."""


def _float32(value: float) -> float:
    return F32.unpack(F32.pack(value))[0]


@dataclass(frozen=True)
class TerrainTile:
    size: int
    offset_steps: int
    height_step: int
    data: bytes

    def raw(self, x: int, y: int) -> int:
        return U16.unpack_from(self.data, 2 * (x * self.size + y))[0]

    def height(self, x: int, y: int) -> float:
        return (self.offset_steps + (self.raw(x, y) >> 4) * self.height_step) * 0.05

    def interpolated_vertex(self, x: float, y: float) -> float:
        # Coarser sectors are expanded bilinearly to the engine's unit grid.
        ix, iy = min(floor(x), self.size - 2), min(floor(y), self.size - 2)
        fx, fy = x - ix, y - iy
        return (
            self.height(ix, iy) * (1 - fx) * (1 - fy)
            + self.height(ix + 1, iy) * fx * (1 - fy)
            + self.height(ix, iy + 1) * (1 - fx) * fy
            + self.height(ix + 1, iy + 1) * fx * fy
        )


@dataclass(frozen=True)
class TerrainHeightmap:
    size_units: int
    unit_metres: int
    sector_metres: int
    tiles: Mapping[tuple[int, int], TerrainTile]

    @property
    def width_metres(self) -> int:
        return self.size_units * self.unit_metres

    def elevation_at(self, world_x: float, world_y: float) -> float | None:
        if not all(isfinite(v) for v in (world_x, world_y)):
            return None
        # Outside the terrain is unknown, never clamped onto a nearby hill.
        if not (0 <= world_x < self.width_metres and 0 <= world_y < self.width_metres):
            return None
        sx, sy = int(world_x // self.sector_metres), int(world_y // self.sector_metres)
        tile = self.tiles[(sx, sy)]
        x = (world_x - sx * self.sector_metres) / self.unit_metres
        y = (world_y - sy * self.sector_metres) / self.unit_metres
        ix, iy = floor(x), floor(y)
        scale = (tile.size - 1) * self.unit_metres / self.sector_metres
        if tile.raw(floor(ix * scale), floor(iy * scale)) & 15 == 15:
            return None  # Hole in terrain; a bridge/mesh is a separate collider.
        a = tile.interpolated_vertex(ix * scale, iy * scale)
        b = tile.interpolated_vertex((ix + 1) * scale, iy * scale)
        c = tile.interpolated_vertex(ix * scale, (iy + 1) * scale)
        d = tile.interpolated_vertex((ix + 1) * scale, (iy + 1) * scale)
        fx, fy = x - ix, y - iy
        # Match the two triangles used by CryEngine's GetZApr / ray trace.
        if fx + fy < 1:
            return a * (1 - fx - fy) + b * fx + c * fy
        return d * (fx + fy - 1) + c * (1 - fx) + b * (1 - fy)


def decode_terrain(data: bytes) -> TerrainHeightmap:
    """Decode a complete terrain.dat, validating its table and quadtree layout."""
    if len(data) < HEADER.size:
        raise TerrainFormatError("Truncated terrain header")
    version, _, flags, flags2, length, size, unit, sector, sectors, ratio, ocean = HEADER.unpack_from(data)
    if version != 28 or flags != 6 or flags2 != 0:
        raise TerrainFormatError(f"Unsupported terrain format: {version=}, {flags=}, {flags2=}")
    if length != len(data):
        raise TerrainFormatError("Terrain length does not match header")
    if (not 1 <= size <= 16384 or not 1 <= unit <= 32 or not 2 <= sector // unit <= 256
            or sector % unit or sectors * sector != size * unit
            or sectors < 1 or sectors & (sectors - 1)
            or (sector // unit) & (sector // unit - 1)
            or ratio != 1 or not isfinite(ocean)):
        raise TerrainFormatError("Unsupported terrain dimensions")
    cursor = HEADER.size

    def take(count: int) -> int:
        nonlocal cursor
        start = cursor
        if count < 0 or count > len(data) - cursor:
            raise TerrainFormatError("Truncated terrain payload")
        cursor += count
        return start

    def align() -> None:
        take((-cursor) % 4)

    # StatInstGroupChunk, brush SNameChunk, material SNameChunk.
    for record_size in (360, 256, 256):
        count = I32.unpack_from(data, take(4))[0]
        if count < 0:
            raise TerrainFormatError("Negative terrain table length")
        take(count * record_size)
    tiles: dict[tuple[int, int], TerrainTile] = {}
    lod_bytes = ((sector // unit).bit_length() - 1) * 4

    def node(x: int, y: int, width: int) -> None:
        values = NODE.unpack_from(data, take(NODE.size))
        node_version, holes, x0, y0, z0, x1, y1, z1, offset, span, n, surfaces = values
        if (node_version != 7 or holes not in (0, 1, 2)
                or not all(isfinite(v) for v in values[2:10])
                or (x0, y0, x1, y1) != (x, y, x + width, y + width)
                or z0 > z1 or span < 0 or not 0 <= surfaces <= 128):
            raise TerrainFormatError("Invalid terrain node header or bounds")
        leaf = width == sector
        if (not leaf and n != 0) or (leaf and (n < 2 or n > sector // unit + 1
                or (n - 1) & (n - 2))):
            raise TerrainFormatError("Unsupported terrain node sample size")
        start = take(n * n * 2)
        if leaf:
            # Node v7 stores 12-bit integer heights and 4-bit surface indices.
            # Reproduce float32 arithmetic before C++ truncation to integer steps.
            maximum = _float32(offset + _float32(0xFFF0 * span))
            range_steps = int(_float32(_float32(maximum - offset) * 20))
            step = (range_steps + 4094) // 4095 if range_steps else 1
            tiles[(x // sector, y // sector)] = TerrainTile(
                n, int(_float32(offset * 20)), step, data[start:cursor]
            )
        align()
        take(lod_bytes)
        take(surfaces)
        align()
        if not leaf:
            half = width // 2
            for dx, dy in ((0, 0), (half, 0), (0, half), (half, half)):
                node(x + dx, y + dy, half)

    node(0, 0, size * unit)
    if len(tiles) != sectors * sectors:
        raise TerrainFormatError("Incomplete terrain coverage")
    # Remaining bytes are the outdoor object octree, not additional heights.
    return TerrainHeightmap(size, unit, sector, MappingProxyType(tiles))


def terrain_for_battlefield(paks_root: Path, battlefield: str) -> TerrainHeightmap | None:
    path = paks_root / battlefield / "level.pak"
    if not path.is_file():
        return None
    stat = path.stat()
    return _load_archive(path.resolve(), stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=4)
def _load_archive(path: Path, modified_ns: int, size: int) -> TerrainHeightmap | None:
    with zipfile.ZipFile(path) as archive:
        info = next((i for i in archive.infolist()
                     if i.filename.replace("\\", "/").lower() == "terrain/terrain.dat"), None)
        if info is None:
            return None
        # CryEngine's local ZIP headers can use backslashes unlike the directory.
        try:
            data = archive.read(info)
        except zipfile.BadZipFile as error:
            if "File name in directory" not in str(error):
                raise
            info.orig_filename = info.orig_filename.replace("/", "\\")
            data = archive.read(info)
    return decode_terrain(data)
