"""Terrain-aware projectile trajectory and clearance calculations."""

from __future__ import annotations

from dataclasses import dataclass
from math import cos, exp, isfinite, log, radians, sin

from .calibration import METRES_TO_YARDS


YARDS_TO_METRES = 1.0 / METRES_TO_YARDS


@dataclass(frozen=True)
class TerrainProfilePoint:
    distance_yards: float
    elevation_metres: float


@dataclass(frozen=True)
class TrajectorySample:
    distance_yards: float
    terrain_elevation_metres: float
    shell_elevation_metres: float

    @property
    def clearance_metres(self) -> float:
        return self.shell_elevation_metres - self.terrain_elevation_metres


@dataclass(frozen=True)
class TrajectoryClearanceResult:
    confidence: str
    target_range_yards: float
    original_elevation_deg: float
    obstructed: bool
    first_obstruction_yards: float | None
    minimum_clearance_metres: float | None
    clearing_elevation_deg: float | None
    impact_range_yards: float | None
    overshoot_yards: float | None
    height_above_target_metres: float | None
    original_trajectory: tuple[TrajectorySample, ...]
    clearing_trajectory: tuple[TrajectorySample, ...]


def shell_height_at_distance(
    distance_yards: float,
    elevation_degrees: float,
    speed_metres_per_second: float,
    drag_per_second: float,
    gravity_metres_per_second_squared: float,
    muzzle_height_metres: float,
) -> float | None:
    """Return shell height above the gun's ground plane at horizontal distance."""

    if distance_yards < 0:
        raise ValueError("Distance cannot be negative.")
    if speed_metres_per_second <= 0:
        raise ValueError("Muzzle velocity must be positive.")
    if drag_per_second < 0:
        raise ValueError("Drag cannot be negative.")
    if gravity_metres_per_second_squared <= 0:
        raise ValueError("Gravity must be positive.")
    theta = radians(elevation_degrees)
    horizontal_speed = speed_metres_per_second * cos(theta)
    if horizontal_speed <= 0:
        return None
    distance_metres = distance_yards * YARDS_TO_METRES
    if drag_per_second == 0:
        time = distance_metres / horizontal_speed
        return (
            muzzle_height_metres
            + speed_metres_per_second * sin(theta) * time
            - 0.5 * gravity_metres_per_second_squared * time**2
        )
    ratio = drag_per_second * distance_metres / horizontal_speed
    if ratio >= 1:
        return None
    time = -log(1 - ratio) / drag_per_second
    vertical_speed = speed_metres_per_second * sin(theta)
    return (
        muzzle_height_metres
        + (
            vertical_speed
            + gravity_metres_per_second_squared / drag_per_second
        )
        * (1 - exp(-drag_per_second * time))
        / drag_per_second
        - gravity_metres_per_second_squared * time / drag_per_second
    )


def analyze_trajectory_clearance(
    terrain_profile: tuple[TerrainProfilePoint, ...],
    target_range_yards: float,
    original_elevation_deg: float,
    speed_metres_per_second: float,
    drag_per_second: float,
    gravity_metres_per_second_squared: float = 9.1,
    muzzle_height_metres: float = 0.762,
    safety_margin_metres: float = 0.01,
    maximum_elevation_deg: float = 75.0,
    confidence: str = "estimated",
) -> TrajectoryClearanceResult:
    """Check a calibrated physical arc and find the lowest terrain-clearing angle."""

    profile = _validated_profile(terrain_profile)
    if target_range_yards <= 0:
        raise ValueError("Target range must be positive.")
    if profile[-1].distance_yards < target_range_yards:
        raise ValueError("Terrain profile must extend at least to the target.")
    gun_ground = profile[0].elevation_metres
    target_ground = _terrain_elevation_at(profile, target_range_yards)
    raw_target_height = shell_height_at_distance(
        target_range_yards,
        original_elevation_deg,
        speed_metres_per_second,
        drag_per_second,
        gravity_metres_per_second_squared,
        muzzle_height_metres,
    )
    if raw_target_height is None:
        return TrajectoryClearanceResult(
            confidence,
            target_range_yards,
            original_elevation_deg,
            True,
            None,
            None,
            None,
            None,
            None,
            None,
            (),
            (),
        )

    # The selected empirical curve supplies the firing solution but not a vertical
    # path. Calibrate the physical arc so that this selected solution intersects
    # the sampled target elevation, then preserve that correction for raised arcs.
    vertical_bias_per_yard = (
        target_ground - gun_ground - raw_target_height
    ) / target_range_yards

    def trajectory(angle: float) -> tuple[TrajectorySample, ...]:
        samples: list[TrajectorySample] = []
        for point in profile:
            relative_height = shell_height_at_distance(
                point.distance_yards,
                angle,
                speed_metres_per_second,
                drag_per_second,
                gravity_metres_per_second_squared,
                muzzle_height_metres,
            )
            if relative_height is None:
                break
            samples.append(
                TrajectorySample(
                    point.distance_yards,
                    point.elevation_metres,
                    gun_ground
                    + relative_height
                    + vertical_bias_per_yard * point.distance_yards,
                )
            )
        return tuple(samples)

    original = trajectory(original_elevation_deg)
    route_samples = _samples_before_target(original, target_range_yards)
    minimum = min(
        (sample.clearance_metres for sample in route_samples),
        default=None,
    )
    first_obstruction = next(
        (
            sample.distance_yards
            for sample in route_samples
            if sample.clearance_metres < safety_margin_metres
        ),
        None,
    )
    obstructed = first_obstruction is not None
    clearing_angle = original_elevation_deg
    clearing = original

    if obstructed:
        blocked_angle = original_elevation_deg
        clear_angle: float | None = None
        candidate = original_elevation_deg
        while candidate < maximum_elevation_deg:
            candidate = min(candidate + 1.0, maximum_elevation_deg)
            candidate_samples = trajectory(candidate)
            if _route_is_clear(
                candidate_samples,
                target_range_yards,
                safety_margin_metres,
            ):
                clear_angle = candidate
                break
            blocked_angle = candidate
        if clear_angle is None:
            clearing_angle = None
            clearing = ()
        else:
            for _ in range(50):
                middle = (blocked_angle + clear_angle) / 2
                middle_samples = trajectory(middle)
                if _route_is_clear(
                    middle_samples,
                    target_range_yards,
                    safety_margin_metres,
                ):
                    clear_angle = middle
                else:
                    blocked_angle = middle
            clearing_angle = clear_angle
            clearing = trajectory(clear_angle)

    impact = _impact_range(clearing) if clearing else None
    overshoot = impact - target_range_yards if impact is not None else None
    height_above_target = (
        _clearance_at_distance(clearing, target_range_yards)
        if clearing
        else None
    )
    return TrajectoryClearanceResult(
        confidence,
        target_range_yards,
        original_elevation_deg,
        obstructed,
        first_obstruction,
        minimum,
        clearing_angle,
        impact,
        overshoot,
        height_above_target,
        original,
        clearing,
    )


def _validated_profile(
    terrain_profile: tuple[TerrainProfilePoint, ...],
) -> tuple[TerrainProfilePoint, ...]:
    if len(terrain_profile) < 2:
        raise ValueError("At least two terrain profile points are required.")
    if terrain_profile[0].distance_yards != 0:
        raise ValueError("Terrain profile must start at the gun.")
    if any(
        not isfinite(point.distance_yards)
        or not isfinite(point.elevation_metres)
        for point in terrain_profile
    ):
        raise ValueError("Terrain profile values must be finite.")
    if any(
        left.distance_yards >= right.distance_yards
        for left, right in zip(terrain_profile, terrain_profile[1:])
    ):
        raise ValueError("Terrain profile distances must be strictly increasing.")
    return terrain_profile


def _terrain_elevation_at(
    profile: tuple[TerrainProfilePoint, ...],
    distance_yards: float,
) -> float:
    for left, right in zip(profile, profile[1:]):
        if left.distance_yards <= distance_yards <= right.distance_yards:
            span = right.distance_yards - left.distance_yards
            fraction = (distance_yards - left.distance_yards) / span
            return left.elevation_metres + fraction * (
                right.elevation_metres - left.elevation_metres
            )
    return profile[-1].elevation_metres


def _samples_before_target(
    samples: tuple[TrajectorySample, ...],
    target_range_yards: float,
) -> tuple[TrajectorySample, ...]:
    # The shell is intentionally descending into the selected target. Do not
    # treat the final few yards of that approach as a terrain obstruction.
    terminal_exclusion = max(10.0, min(25.0, target_range_yards * 0.05))
    return tuple(
        sample
        for sample in samples
        if 5.0
        <= sample.distance_yards
        <= max(5.0, target_range_yards - terminal_exclusion)
    )


def _route_is_clear(
    samples: tuple[TrajectorySample, ...],
    target_range_yards: float,
    safety_margin_metres: float,
) -> bool:
    route = _samples_before_target(samples, target_range_yards)
    return bool(route) and all(
        sample.clearance_metres >= safety_margin_metres for sample in route
    )


def _impact_range(samples: tuple[TrajectorySample, ...]) -> float | None:
    previous: TrajectorySample | None = None
    for sample in samples:
        if sample.distance_yards < 5.0:
            previous = sample
            continue
        if sample.clearance_metres <= 0:
            if previous is None or previous.clearance_metres <= 0:
                return sample.distance_yards
            clearance_span = previous.clearance_metres - sample.clearance_metres
            if clearance_span <= 0:
                return sample.distance_yards
            fraction = previous.clearance_metres / clearance_span
            return previous.distance_yards + fraction * (
                sample.distance_yards - previous.distance_yards
            )
        previous = sample
    return None


def _clearance_at_distance(
    samples: tuple[TrajectorySample, ...],
    distance_yards: float,
) -> float | None:
    for left, right in zip(samples, samples[1:]):
        if left.distance_yards <= distance_yards <= right.distance_yards:
            span = right.distance_yards - left.distance_yards
            fraction = (distance_yards - left.distance_yards) / span
            shell = left.shell_elevation_metres + fraction * (
                right.shell_elevation_metres - left.shell_elevation_metres
            )
            terrain = left.terrain_elevation_metres + fraction * (
                right.terrain_elevation_metres - left.terrain_elevation_metres
            )
            return shell - terrain
    return None
