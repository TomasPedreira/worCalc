from __future__ import annotations

from dataclasses import dataclass
from math import hypot, isfinite
from pathlib import Path


METRES_TO_YARDS = 1.0936132983377078


@dataclass(frozen=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True)
class Calibration:
    first: Point
    second: Point
    known_distance_yards: float

    @property
    def pixel_distance(self) -> float:
        return hypot(self.second.x - self.first.x, self.second.y - self.first.y)

    @property
    def yards_per_pixel(self) -> float:
        if not isfinite(self.known_distance_yards) or self.known_distance_yards <= 0:
            raise ValueError("Known distance must be greater than zero.")
        if self.pixel_distance <= 0:
            raise ValueError("The two calibration points must be different.")
        return self.known_distance_yards / self.pixel_distance


@dataclass(frozen=True)
class AffineCalibration:
    """Convert minimap pixel deltas to CryEngine world-space metre deltas."""

    pixel_x_world_x: float
    pixel_x_world_y: float
    pixel_y_world_x: float
    pixel_y_world_y: float

    @property
    def determinant(self) -> float:
        return (
            self.pixel_x_world_x * self.pixel_y_world_y
            - self.pixel_y_world_x * self.pixel_x_world_y
        )

    @property
    def x_yards_per_pixel(self) -> float:
        return hypot(self.pixel_x_world_x, self.pixel_x_world_y) * METRES_TO_YARDS

    @property
    def y_yards_per_pixel(self) -> float:
        return hypot(self.pixel_y_world_x, self.pixel_y_world_y) * METRES_TO_YARDS

    @property
    def mean_yards_per_pixel(self) -> float:
        return (self.x_yards_per_pixel + self.y_yards_per_pixel) / 2.0

    def world_delta(self, pixel_dx: float, pixel_dy: float) -> Point:
        return Point(
            pixel_dx * self.pixel_x_world_x + pixel_dy * self.pixel_y_world_x,
            pixel_dx * self.pixel_x_world_y + pixel_dy * self.pixel_y_world_y,
        )

    def pixel_delta_for_world_units(self, world_x: float, world_y: float) -> Point:
        determinant = self.determinant
        if not isfinite(determinant) or abs(determinant) < 1e-12:
            raise ValueError("Affine calibration matrix is singular")
        return Point(
            (self.pixel_y_world_y * world_x - self.pixel_y_world_x * world_y)
            / determinant,
            (-self.pixel_x_world_y * world_x + self.pixel_x_world_x * world_y)
            / determinant,
        )

    def distance_yards(self, first: Point, second: Point) -> float:
        world_delta = self.world_delta(second.x - first.x, second.y - first.y)
        return hypot(world_delta.x, world_delta.y) * METRES_TO_YARDS

    # Compatibility aliases for callers created before the UI descriptor's units
    # were validated against the game's yard-range display.
    def world_delta_metres(self, pixel_dx: float, pixel_dy: float) -> Point:
        return self.world_delta(pixel_dx, pixel_dy)

    def pixel_delta_for_world_metres(self, world_x: float, world_y: float) -> Point:
        return self.pixel_delta_for_world_units(world_x, world_y)


def read_resolution(config_path: Path) -> float | None:
    if not config_path.exists():
        return None
    for raw_line in config_path.read_text(encoding="utf-8").splitlines():
        key, separator, value = raw_line.partition("=")
        if separator and key.strip().lower() == "resolution":
            try:
                resolution = float(value.strip())
            except ValueError:
                return None
            return resolution if isfinite(resolution) and resolution > 0 else None
    return None


def write_calibration(config_path: Path, calibration: Calibration, image_width: int, image_height: int) -> None:
    lines = [
        f"resolution={calibration.yards_per_pixel:.12g}",
        "unit=yard",
        f"image_width={image_width}",
        f"image_height={image_height}",
        f"point_1={calibration.first.x:.6f},{calibration.first.y:.6f}",
        f"point_2={calibration.second.x:.6f},{calibration.second.y:.6f}",
        f"known_distance={calibration.known_distance_yards:.12g}",
    ]
    config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
