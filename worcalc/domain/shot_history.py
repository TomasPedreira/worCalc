"""Fire-target history and observed-impact correction geometry."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import hypot, isfinite

from .calibration import AffineCalibration, METRES_TO_YARDS, Point


@dataclass(frozen=True)
class ObservedShot:
    """A spotted impact relative to its intended target.

    Positive longitudinal values are over; negative values are short. Positive
    lateral values are right of the gun-to-target line; negative values are left.
    """

    over_short_yards: float
    left_right_yards: float
    fired_elevation_deg: float | None = None
    fuze_seconds: float | None = None
    note: str = ""


@dataclass
class FireTarget:
    """A saved target position with its observed shots."""

    identifier: int
    target: Point
    shots: list[ObservedShot] = field(default_factory=list)


def observed_impact_point(
    calibration: AffineCalibration,
    gun: Point,
    target: Point,
    shot: ObservedShot,
) -> Point:
    """Place a spotted impact using target-relative yard corrections."""

    values = (shot.over_short_yards, shot.left_right_yards)
    if not all(isfinite(value) for value in values):
        raise ValueError("Shot corrections must be finite")

    pixel_dx = target.x - gun.x
    pixel_dy = target.y - gun.y
    world_route = calibration.world_delta(pixel_dx, pixel_dy)
    route_length = hypot(world_route.x, world_route.y)
    if route_length <= 0:
        raise ValueError("Gun and target positions must be different")

    forward_x = world_route.x / route_length
    forward_y = world_route.y / route_length
    right_candidates = ((-forward_y, forward_x), (forward_y, -forward_x))
    desired_pixel_right = (-pixel_dy, pixel_dx)

    def screen_alignment(world_right: tuple[float, float]) -> float:
        pixel_right = calibration.pixel_delta_for_world_units(*world_right)
        return (
            pixel_right.x * desired_pixel_right[0]
            + pixel_right.y * desired_pixel_right[1]
        )

    right_x, right_y = max(right_candidates, key=screen_alignment)
    over_metres = shot.over_short_yards / METRES_TO_YARDS
    right_metres = shot.left_right_yards / METRES_TO_YARDS
    world_offset_x = forward_x * over_metres + right_x * right_metres
    world_offset_y = forward_y * over_metres + right_y * right_metres
    pixel_offset = calibration.pixel_delta_for_world_units(
        world_offset_x,
        world_offset_y,
    )
    return Point(target.x + pixel_offset.x, target.y + pixel_offset.y)


def correction_summary(shot: ObservedShot) -> str:
    """Return a compact field-readable correction summary."""

    longitudinal = (
        f"{abs(shot.over_short_yards):,.0f} over"
        if shot.over_short_yards > 0
        else f"{abs(shot.over_short_yards):,.0f} short"
        if shot.over_short_yards < 0
        else "range correct"
    )
    lateral = (
        f"{abs(shot.left_right_yards):,.0f} right"
        if shot.left_right_yards > 0
        else f"{abs(shot.left_right_yards):,.0f} left"
        if shot.left_right_yards < 0
        else "line correct"
    )
    return f"{longitudinal}, {lateral}"
