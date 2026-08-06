"""Qt-free orchestration for the browser fire-mission calculator."""

from __future__ import annotations

from io import BytesIO
from dataclasses import dataclass
from functools import lru_cache
from math import atan2, degrees, isfinite
from pathlib import Path

from PIL import Image

from ..domain.ballistic_solution import BallisticSolutionEngine
from ..domain.calibration import Point
from ..domain.projectile import ARTILLERY_PHYSICS, artillery_time_of_flight
from ..domain.ranging import RangeMeasurement
from ..maps.catalog import MapRecord, load_map_catalog
from ..maps.elevation import ElevationField, elevation_field_for_map
from ..maps.entities import MapLocation, locations_for_map


class MapNotFoundError(LookupError):
    """Raised when an API map identifier is unknown."""


@dataclass(frozen=True)
class MapInfo:
    identifier: str
    name: str
    battlefield: str
    mode: str
    gameplay_area: int
    width_pixels: int
    height_pixels: int


@dataclass(frozen=True)
class FireSolution:
    map_id: str
    cannon: str
    projectile: str
    method: str
    horizontal_range_yards: float
    slant_range_yards: float
    gun_elevation_metres: float | None
    target_elevation_metres: float | None
    height_difference_metres: float | None
    bearing_degrees: float
    bearing_direction: str
    elevation_degrees: float | None
    fuze_seconds: float | None


class FireMissionCalculator:
    """Load map data and calculate one gun-to-target solution at a time."""

    def __init__(
        self,
        maps_dir: Path,
        ballistics_csv: Path,
        paks_root: Path | None = None,
    ) -> None:
        self.maps_dir = maps_dir
        self.ballistics_csv = ballistics_csv
        self.paks_root = paks_root or maps_dir.parent
        records = load_map_catalog(maps_dir.parent / "gameplay_area_calibrations.json")
        self._records = {
            f"map-{index + 1}": record for index, record in enumerate(records)
        }
        self._dimensions: dict[str, tuple[int, int]] = {}
        self._elevation_fields: dict[str, ElevationField] = {}

        solver = BallisticSolutionEngine(self.ballistics_csv)
        self.methods = tuple(solver.method_names)
        self.default_method = solver.method_name

    @property
    def weapons(self) -> dict[str, tuple[str, ...]]:
        return {
            cannon: tuple(projectiles)
            for cannon, projectiles in ARTILLERY_PHYSICS.items()
        }

    @property
    def physics_profiles(self) -> dict[str, dict[str, dict[str, float]]]:
        return {
            cannon: {
                projectile: {"speed": speed, "drag": drag}
                for projectile, (speed, drag) in projectiles.items()
            }
            for cannon, projectiles in ARTILLERY_PHYSICS.items()
        }

    def list_maps(self) -> list[MapInfo]:
        return [
            self.map_info(identifier)
            for identifier in self._records
        ]

    def map_info(self, map_id: str) -> MapInfo:
        record = self.map_record(map_id)
        width, height = self.image_dimensions(map_id)
        return MapInfo(
            identifier=map_id,
            name=record.name,
            battlefield=record.battlefield,
            mode=record.mode_name,
            gameplay_area=record.gameplay_area,
            width_pixels=width,
            height_pixels=height,
        )

    def map_record(self, map_id: str) -> MapRecord:
        try:
            return self._records[map_id]
        except KeyError as error:
            raise MapNotFoundError(f"Unknown map: {map_id}") from error

    def image_path(self, map_id: str) -> Path:
        return self.map_record(map_id).image_path

    def image_dimensions(self, map_id: str) -> tuple[int, int]:
        if map_id not in self._dimensions:
            with Image.open(self.image_path(map_id)) as image:
                self._dimensions[map_id] = image.size
        return self._dimensions[map_id]

    @lru_cache(maxsize=4)
    def parchment_image_bytes(self, map_id: str) -> bytes:
        """Render the grayscale map mask with the desktop parchment palette."""

        with Image.open(self.image_path(map_id)) as source:
            mask = source.convert("L")
            paper = Image.new("RGB", mask.size, (222, 205, 151))
            ink = Image.new("RGB", mask.size, (45, 36, 22))
            styled = Image.composite(ink, paper, mask)
            output = BytesIO()
            styled.save(output, format="PNG")
        return output.getvalue()

    @lru_cache(maxsize=8)
    def map_locations(self, map_id: str) -> tuple[MapLocation, ...]:
        """Return projected game-file reference locations for one map."""

        width, height = self.image_dimensions(map_id)
        return tuple(
            locations_for_map(
                self.map_record(map_id),
                width,
                height,
                self.paks_root,
            )
        )

    def calculate(
        self,
        map_id: str,
        gun: Point,
        target: Point,
        cannon: str,
        projectile: str,
        method: str,
    ) -> FireSolution:
        record = self.map_record(map_id)
        self._validate_point(map_id, gun, "Gun")
        self._validate_point(map_id, target, "Target")
        if gun == target:
            raise ValueError("Gun and target must be different points")

        try:
            speed, drag = ARTILLERY_PHYSICS[cannon][projectile]
        except KeyError as error:
            raise ValueError(
                f"Unsupported artillery profile: {cannon} / {projectile}"
            ) from error

        solver = BallisticSolutionEngine(self.ballistics_csv)
        try:
            method_index = solver.method_names.index(method)
        except ValueError as error:
            raise ValueError(f"Unknown ballistic method: {method}") from error
        solver.set_physics_profile(speed, drag)
        solver.set_method(method_index)

        horizontal_range = record.calibration.distance_yards(gun, target)
        field = self._elevation_field(map_id)
        gun_elevation = field.elevation_at(gun)
        target_elevation = field.elevation_at(target)
        height_difference = (
            target_elevation - gun_elevation
            if gun_elevation is not None and target_elevation is not None
            else None
        )
        measurement = RangeMeasurement(horizontal_range, height_difference)
        elevation = solver.solve(horizontal_range, height_difference or 0.0)
        try:
            fuze = artillery_time_of_flight(
                measurement.slant_yards,
                cannon,
                projectile,
            )
        except ValueError:
            fuze = None

        bearing = self._bearing_degrees(target.x - gun.x, target.y - gun.y)
        return FireSolution(
            map_id=map_id,
            cannon=cannon,
            projectile=projectile,
            method=method,
            horizontal_range_yards=horizontal_range,
            slant_range_yards=measurement.slant_yards,
            gun_elevation_metres=gun_elevation,
            target_elevation_metres=target_elevation,
            height_difference_metres=height_difference,
            bearing_degrees=bearing,
            bearing_direction=self._bearing_direction(bearing),
            elevation_degrees=elevation,
            fuze_seconds=fuze,
        )

    def _elevation_field(self, map_id: str) -> ElevationField:
        if map_id not in self._elevation_fields:
            width, height = self.image_dimensions(map_id)
            self._elevation_fields[map_id] = elevation_field_for_map(
                self.map_record(map_id),
                width,
                height,
                self.paks_root,
            )
        return self._elevation_fields[map_id]

    def _validate_point(self, map_id: str, point: Point, label: str) -> None:
        if not isfinite(point.x) or not isfinite(point.y):
            raise ValueError(f"{label} coordinates must be finite")
        width, height = self.image_dimensions(map_id)
        if not 0 <= point.x <= width or not 0 <= point.y <= height:
            raise ValueError(f"{label} coordinates are outside the map image")

    @staticmethod
    def _bearing_degrees(pixel_dx: float, pixel_dy: float) -> float:
        return (degrees(atan2(pixel_dx, -pixel_dy)) + 360.0) % 360.0

    @staticmethod
    def _bearing_direction(bearing: float) -> str:
        directions = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
        return directions[round((bearing % 360.0) / 45.0) % 8]
