"""Qt-free orchestration for the browser fire-mission calculator."""

from __future__ import annotations

from io import BytesIO
from dataclasses import asdict, dataclass
from functools import lru_cache
from math import atan2, ceil, degrees, isfinite
from pathlib import Path
from uuid import uuid4
from collections import OrderedDict
from threading import Lock

from PIL import Image

from ..domain.ballistic_solution import BallisticSolutionEngine
from ..domain.calibration import Point
from ..domain.physics_solution import LaunchGeometry, PhysicsSolver
from ..domain.projectile import ARTILLERY_PHYSICS, artillery_time_of_flight
from ..domain.ranging import RangeMeasurement
from ..maps.catalog import MapRecord, load_map_catalog
from ..maps.elevation import ElevationField, elevation_field_for_map
from ..maps.entities import MapLocation, locations_for_map
from ..diagnostics import read_observed_impacts, record_calculation
from ..domain.empirical_calibration import ImpactSample, estimate_elevation


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
    clearance_status: str | None
    height_above_target_metres: float | None
    calculation_id: str = ""
    elevation_source: str = "physics"
    physics_elevation_degrees: float | None = None
    calibration_sample_count: int = 0
    calibration_mode: bool = False


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
        self._shot_traces = OrderedDict()
        self._shot_lock = Lock()

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

        styled = self._parchment_image(map_id)
        output = BytesIO()
        styled.save(output, format="PNG")
        return output.getvalue()

    @lru_cache(maxsize=32)
    def parchment_thumbnail_bytes(
        self,
        map_id: str,
        max_size: int = 320,
    ) -> bytes:
        """Render a compact selector thumbnail without transferring the full map."""

        if max_size <= 0:
            raise ValueError("Thumbnail size must be positive")
        styled = self._parchment_image(map_id)
        styled.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        output = BytesIO()
        styled.save(output, format="WEBP", quality=72, method=4)
        return output.getvalue()

    @lru_cache(maxsize=4)
    def parchment_webp_image_bytes(self, map_id: str) -> bytes:
        """Render the full map in a phone-friendly format with its dimensions intact."""

        styled = self._parchment_image(map_id)
        output = BytesIO()
        styled.save(output, format="WEBP", quality=85, method=4)
        return output.getvalue()

    def _parchment_image(self, map_id: str) -> Image.Image:
        with Image.open(self.image_path(map_id)) as source:
            mask = source.convert("L")
        paper = Image.new("RGB", mask.size, (222, 205, 151))
        ink = Image.new("RGB", mask.size, (45, 36, 22))
        return Image.composite(ink, paper, mask)

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
        calibration_mode: bool = False,
    ) -> FireSolution:
        record = self.map_record(map_id)
        # Older clients still send a method name, but the web firing workflow
        # always uses the preferred unified model.
        method = self.default_method
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
        solver.set_weapon(cannon, projectile)
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
        clearance = None
        terrain_profile = ()
        clearance_error = None
        if elevation is not None and field.samples:
            try:
                terrain_profile = field.profile_along_line(
                    gun,
                    target,
                    horizontal_range,
                    spacing_yards=5.0,
                )
                clearance = solver.analyze_clearance(
                    horizontal_range,
                    height_difference or 0.0,
                    terrain_profile,
                    speed,
                    drag,
                )
            except ValueError as error:
                clearance_error = str(error)
                clearance = None
        solution_elevation = (
            clearance.clearing_elevation_deg
            if clearance is not None
            else elevation
        )
        if clearance is not None and clearance.obstructed and solution_elevation is not None:
            solution_elevation = ceil((solution_elevation - 1e-10) * 100.0) / 100.0
        try:
            fuze = artillery_time_of_flight(
                measurement.slant_yards,
                cannon,
                projectile,
            )
        except ValueError:
            fuze = None

        if solver.is_unified:
            fuze = solver.flight_time(horizontal_range, height_difference or 0.0)

        bearing = self._bearing_degrees(target.x - gun.x, target.y - gun.y)
        empirical = self._empirical_aim(
            record, gun, bearing, cannon, projectile, horizontal_range
        )
        displayed_elevation = elevation if calibration_mode else solution_elevation
        if solver.is_unified and displayed_elevation is not None:
            state = solver.physics.at_distance(horizontal_range, displayed_elevation)
            fuze = state[1] if state is not None else None
        displayed_height = clearance.height_above_target_metres if clearance is not None else None
        if (solver.is_unified and displayed_elevation is not None
                and gun_elevation is not None and target_elevation is not None):
            state = solver.physics.at_distance(horizontal_range, displayed_elevation)
            displayed_height = (
                gun_elevation + state[0] - target_elevation if state is not None else None
            )
        result = FireSolution(
            calculation_id=str(uuid4()),
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
            elevation_degrees=displayed_elevation,
            fuze_seconds=fuze,
            clearance_status=(
                "obstructed" if clearance is not None and clearance.obstructed
                else "clear" if clearance is not None
                else None
            ),
            height_above_target_metres=displayed_height,
            elevation_source=(
                "calibration_test"
                if calibration_mode
                else "terrain_clearance"
                if clearance is not None and clearance.obstructed
                else "physics"
            ),
            physics_elevation_degrees=elevation,
            calibration_sample_count=empirical.sample_count if empirical is not None else 0,
            calibration_mode=calibration_mode,
        )
        trace = {
            "source": "web",
            "map": {"id": map_id, "name": record.name, "battlefield": record.battlefield,
                    "mode": record.mode, "layer": record.layer,
                    "calibration": asdict(record.calibration),
                    "top_left_world_metres": [record.top_left_x_metres, record.top_left_y_metres]},
            "gun_pixel": asdict(gun), "target_pixel": asdict(target),
            "physics": asdict(solver.physics),
            "terrain_source": type(field).__name__,
            "used_level_ground_fallback": height_difference is None,
            "aim_elevation_before_terrain_deg": elevation,
            "empirical_aim": asdict(empirical) if empirical is not None else None,
            "calibration_mode": calibration_mode,
            "reason": ("no_ballistic_solution" if elevation is None
                       else "terrain_obstruction" if clearance is not None and clearance.obstructed
                       else "clear" if clearance is not None
                       else "terrain_check_unavailable"),
            "clearance_error": clearance_error,
            "clearance": asdict(clearance) if clearance is not None else None,
            "terrain_profile": [asdict(point) for point in terrain_profile],
            "result": asdict(result),
        }
        with self._shot_lock:
            self._shot_traces[result.calculation_id] = trace
            while len(self._shot_traces) > 200:
                self._shot_traces.popitem(last=False)
        record_calculation(trace)
        return result

    def _empirical_aim(self, record: MapRecord, gun: Point, bearing: float,
                       cannon: str, projectile: str, target_range: float):
        samples = []
        for event in read_observed_impacts():
            try:
                shot = event["shot"]
                result = shot["result"]
                logged_map = shot["map"]
                logged_gun = Point(**shot["gun_pixel"])
                logged_bearing = float(result["bearing_degrees"])
                angle = float(event["actual_elevation_degrees"])
                shot_range = float(event["observed_range_yards"])
            except (KeyError, TypeError, ValueError):
                continue
            if (logged_map.get("battlefield"), logged_map.get("mode"), logged_map.get("layer")) != (
                record.battlefield, record.mode, record.layer
            ):
                continue
            if result.get("cannon") != cannon or result.get("projectile") != projectile:
                continue
            if record.calibration.distance_yards(gun, logged_gun) > 15.0:
                continue
            bearing_delta = abs((logged_bearing - bearing + 180.0) % 360.0 - 180.0)
            if bearing_delta > 2.0:
                continue
            samples.append(ImpactSample(angle, shot_range))
        return estimate_elevation(samples, target_range)

    @staticmethod
    def _impact_range_at_angle(trace: dict, angle: float) -> float | None:
        physics = dict(trace['physics'])
        physics['launch'] = LaunchGeometry(**physics['launch'])
        solver = PhysicsSolver(**physics)
        profile = trace['terrain_profile']
        if len(profile) < 2:
            return None
        ground = profile[0]['elevation_metres']
        previous = profile[0]
        for sample in profile[1:]:
            state = solver.at_distance(sample['distance_yards'], angle)
            if state is None:
                return None
            clearance = ground + state[0] - sample['elevation_metres']
            if clearance > 0:
                previous = sample
                continue
            left, right = previous['distance_yards'], sample['distance_yards']
            for _ in range(45):
                middle = (left + right) / 2
                fraction = ((middle - previous['distance_yards']) /
                            (sample['distance_yards'] - previous['distance_yards']))
                terrain = (previous['elevation_metres'] + fraction *
                           (sample['elevation_metres'] - previous['elevation_metres']))
                shell = ground + solver.at_distance(middle, angle)[0]
                if shell > terrain:
                    left = middle
                else:
                    right = middle
            return (left + right) / 2
        return None

    def record_impact(self, calculation_id: str, impact: Point,
                      actual_elevation_degrees: float) -> dict:
        with self._shot_lock:
            trace = self._shot_traces.get(calculation_id)
        if trace is None:
            raise ValueError("Shot expired. Recalculate before marking its impact.")
        if not isfinite(actual_elevation_degrees) or not -89 < actual_elevation_degrees < 89:
            raise ValueError("Actual elevation must be a finite angle between -89 and 89 degrees.")
        self._validate_point(trace['result']['map_id'], impact, "Impact")
        record = self.map_record(trace['result']['map_id'])
        gun = Point(**trace['gun_pixel'])
        target = Point(**trace['target_pixel'])
        predicted_range = self._impact_range_at_angle(trace, actual_elevation_degrees)
        predicted = None
        if predicted_range is not None:
            fraction = predicted_range / trace['result']['horizontal_range_yards']
            predicted = Point(gun.x + (target.x-gun.x)*fraction,
                              gun.y + (target.y-gun.y)*fraction)
        observation = {
            'event': 'observed_impact', 'source': 'web',
            'calculation_id': calculation_id, 'impact_id': str(uuid4()),
            'actual_elevation_degrees': actual_elevation_degrees,
            'angle_resolution_degrees': 0.01,
            'impact_pixel': asdict(impact), 'shot': trace,
            'observed_range_yards': record.calibration.distance_yards(gun, impact),
            'distance_from_target_yards': record.calibration.distance_yards(target, impact),
            'predicted_impact_pixel': asdict(predicted) if predicted else None,
            'predicted_impact_yards_at_actual_angle': predicted_range,
            'prediction_error_yards': record.calibration.distance_yards(predicted, impact) if predicted else None,
        }
        record_calculation(observation)
        empirical = self._empirical_aim(
            record,
            gun,
            float(trace['result']['bearing_degrees']),
            trace['result']['cannon'],
            trace['result']['projectile'],
            float(trace['result']['horizontal_range_yards']),
        )
        response = {key: value for key, value in observation.items() if key != 'shot'}
        response['recommended_elevation_degrees'] = (
            empirical.elevation_degrees if empirical is not None else None
        )
        response['calibration_sample_count'] = (
            empirical.sample_count if empirical is not None else 0
        )
        return response

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
