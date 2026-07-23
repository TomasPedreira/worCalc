"""Diagnostic elevation sampling from positioned level objects.

The compiled CryEngine terrain is not a flat heightmap file. Until its sector
serialization is decoded, positioned level objects provide a dense, useful set
of elevation anchors for debugging map transforms and estimating local height.
"""

from __future__ import annotations

from dataclasses import dataclass
from heapq import nsmallest
from math import ceil, isfinite
from pathlib import Path

from ..domain.calibration import Point
from ..domain.trajectory import TerrainProfilePoint
from .catalog import MapRecord
from .entities import load_battlefield_position_samples


MAX_TERRAIN_HEIGHT_METRES = {
    "Antietam": 209.0,
    "DrillCamp": 300.0,
    "HarpersFerry": 336.0,
    "SouthMountain": 411.0,
}

UNRELIABLE_ELEVATION_NAME_PARTS = (
    "audio",
    "camera",
    "ctz_",
    "fog",
    "probe",
    "rope",
    "spectator",
    "stagingarea",
    "trigger",
    "volume",
)


@dataclass(frozen=True)
class ElevationSample:
    pixel_x: float
    pixel_y: float
    elevation_metres: float
    name: str


@dataclass(frozen=True)
class ElevationField:
    samples: tuple[ElevationSample, ...]

    @property
    def minimum_metres(self) -> float | None:
        return min((sample.elevation_metres for sample in self.samples), default=None)

    @property
    def maximum_metres(self) -> float | None:
        return max((sample.elevation_metres for sample in self.samples), default=None)

    def gradient_range_metres(self) -> tuple[float, float] | None:
        """Return the exact sampled elevation range for this map."""
        minimum = self.minimum_metres
        maximum = self.maximum_metres
        if minimum is None or maximum is None:
            return None
        if maximum - minimum < 1.0:
            midpoint = (minimum + maximum) / 2.0
            return midpoint - 0.5, midpoint + 0.5
        return minimum, maximum

    def percentile_metres(self, percentile: float) -> float | None:
        if not self.samples:
            return None
        values = sorted(sample.elevation_metres for sample in self.samples)
        position = min(max(percentile, 0.0), 1.0) * (len(values) - 1)
        lower_index = int(position)
        upper_index = min(lower_index + 1, len(values) - 1)
        fraction = position - lower_index
        return values[lower_index] + (
            values[upper_index] - values[lower_index]
        ) * fraction

    def contrast_range_metres(self) -> tuple[float, float] | None:
        """Clip sparse outliers so small battlefield height changes stay visible."""
        lower = self.percentile_metres(0.10)
        upper = self.percentile_metres(0.90)
        if lower is None or upper is None:
            return None
        if upper - lower < 1.0:
            midpoint = (lower + upper) / 2.0
            return midpoint - 0.5, midpoint + 0.5
        return lower, upper

    def elevation_at(self, point: Point, neighbours: int = 8) -> float | None:
        """Estimate elevation with inverse-distance weighting of nearby anchors."""
        if not self.samples:
            return None
        nearest = nsmallest(
            max(1, neighbours),
            self.samples,
            key=lambda sample: (
                (sample.pixel_x - point.x) ** 2 + (sample.pixel_y - point.y) ** 2
            ),
        )
        weighted_height = 0.0
        total_weight = 0.0
        for sample in nearest:
            distance_squared = (
                (sample.pixel_x - point.x) ** 2
                + (sample.pixel_y - point.y) ** 2
            )
            if distance_squared < 1e-6:
                return sample.elevation_metres
            # A small floor avoids a single nearly coincident object dominating
            # an otherwise useful local terrain estimate.
            weight = 1.0 / max(distance_squared, 25.0)
            weighted_height += sample.elevation_metres * weight
            total_weight += weight
        return weighted_height / total_weight if total_weight else None

    def profile_along_line(
        self,
        start: Point,
        end: Point,
        total_distance_yards: float,
        spacing_yards: float = 5.0,
    ) -> tuple[TerrainProfilePoint, ...]:
        """Sample the estimated elevation field along a straight map-space route."""

        if total_distance_yards <= 0:
            raise ValueError("Profile distance must be positive.")
        if spacing_yards <= 0:
            raise ValueError("Profile spacing must be positive.")
        count = max(1, ceil(total_distance_yards / spacing_yards))
        profile: list[TerrainProfilePoint] = []
        for index in range(count + 1):
            fraction = index / count
            point = Point(
                start.x + (end.x - start.x) * fraction,
                start.y + (end.y - start.y) * fraction,
            )
            elevation = self.elevation_at(point)
            if elevation is None:
                return ()
            profile.append(
                TerrainProfilePoint(
                    total_distance_yards * fraction,
                    elevation,
                )
            )
        return tuple(profile)


def elevation_field_for_map(
    record: MapRecord,
    image_width: int,
    image_height: int,
    paks_root: Path,
) -> ElevationField:
    """Project plausible object elevation anchors into the selected minimap."""
    maximum = MAX_TERRAIN_HEIGHT_METRES.get(record.battlefield, 1_000.0)
    level_pak = paks_root / record.battlefield / "level.pak"
    samples: list[ElevationSample] = []
    for sample in load_battlefield_position_samples(level_pak.resolve()):
        folded_name = sample.name.casefold()
        if (
            not all(
                isfinite(value)
                for value in (sample.elevation, sample.world_x, sample.world_y)
            )
            or not 1.0 <= sample.elevation <= maximum
            or any(part in folded_name for part in UNRELIABLE_ELEVATION_NAME_PARTS)
        ):
            continue
        delta = record.calibration.pixel_delta_for_world_units(
            sample.world_x - record.top_left_x_metres,
            sample.world_y - record.top_left_y_metres,
        )
        if not (0 <= delta.x <= image_width and 0 <= delta.y <= image_height):
            continue
        samples.append(
            ElevationSample(delta.x, delta.y, sample.elevation, sample.name)
        )
    return ElevationField(tuple(samples))
