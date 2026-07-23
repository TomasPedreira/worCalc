from __future__ import annotations

from math import cos, isfinite, log, radians

from .calibration import METRES_TO_YARDS


THREE_INCH_SPEED_METRES_PER_SECOND = {
    "Shell": 370.0,
    "Case": 375.0,
}
THREE_INCH_SHELL_DRAG_PER_SECOND = 0.1
ARTILLERY_GRAVITY_METRES_PER_SECOND_SQUARED = 9.1

ARTILLERY_PHYSICS = {
    "3-inch Ordnance": {
        "Shell": (370.0, 0.1),
        "Case": (375.0, 0.1),
    },
    "10-pounder Parrott": {
        "Shell": (370.0, 0.1),
        "Case": (375.0, 0.1),
    },
    "12-pounder Napoleon": {
        "Shell": (439.0, 0.31),
        "Case": (439.0, 0.31),
    },
}


def artillery_time_of_flight(
    distance_yards: float,
    cannon_type: str,
    projectile_type: str,
    elevation_degrees: float = 0.0,
) -> float:
    """Estimate horizontal flight time using a cannon/ammunition physics profile."""
    if not isfinite(distance_yards) or distance_yards < 0:
        raise ValueError("Distance must be a finite non-negative value")
    try:
        speed_metres_per_second, drag_per_second = ARTILLERY_PHYSICS[cannon_type][
            projectile_type
        ]
    except KeyError as error:
        raise ValueError(
            f"Unsupported artillery profile: {cannon_type} / {projectile_type}"
        ) from error
    horizontal_speed = speed_metres_per_second * METRES_TO_YARDS * cos(
        radians(elevation_degrees)
    )
    if horizontal_speed <= 0:
        raise ValueError("Elevation must leave a positive horizontal velocity")
    ratio = drag_per_second * distance_yards / horizontal_speed
    if ratio >= 1:
        raise ValueError("Distance is beyond the model's horizontal range")
    return -log(1 - ratio) / drag_per_second


def three_inch_time_of_flight(
    distance_yards: float,
    elevation_degrees: float = 0.0,
    projectile_type: str = "Shell",
) -> float:
    """Estimate seconds to a horizontal range using the installed shell physics.

    CryEngine's linear air-resistance model gives
    x(t) = v_x / k * (1 - exp(-k*t)); this is its inverse.
    """
    return artillery_time_of_flight(
        distance_yards,
        "3-inch Ordnance",
        projectile_type,
        elevation_degrees,
    )
