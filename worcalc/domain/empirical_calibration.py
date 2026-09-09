"""Small, conservative fits for repeated shots along one local firing lane."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ImpactSample:
    elevation_degrees: float
    range_yards: float


@dataclass(frozen=True)
class EmpiricalAim:
    elevation_degrees: float
    distinct_settings: int
    sample_count: int


def estimate_elevation(
    samples: list[ImpactSample],
    target_range_yards: float,
) -> EmpiricalAim | None:
    """Extrapolate a local angle/range trend after rejecting an earlier terrain branch."""

    far_samples = [
        sample for sample in samples
        if sample.range_yards >= target_range_yards * 0.75
    ]
    grouped: dict[float, list[float]] = {}
    for sample in far_samples:
        setting = round(sample.elevation_degrees, 2)
        grouped.setdefault(setting, []).append(sample.range_yards)
    points = [
        (setting, sum(ranges) / len(ranges))
        for setting, ranges in sorted(grouped.items())
    ]
    if len(points) < 3:
        return None

    angles = [point[0] for point in points]
    ranges = [point[1] for point in points]
    if max(angles) - min(angles) < 0.02 or max(ranges) - min(ranges) < 5.0:
        return None

    below = [point for point in points if point[1] <= target_range_yards]
    above = [point for point in points if point[1] >= target_range_yards]
    if below and above:
        low_angle, low_range = max(below, key=lambda point: point[1])
        high_angle, high_range = min(above, key=lambda point: point[1])
        if high_range > low_range and high_angle > low_angle:
            # A ridge can cause a discontinuous jump from impact on its near
            # face to landing well beyond it. Test each available 0.01-degree
            # setting instead of interpolating through that unknown interval.
            estimate = min(low_angle + 0.01, high_angle)
            return EmpiricalAim(estimate, len(points), len(far_samples))

    mean_angle = sum(angles) / len(angles)
    mean_range = sum(ranges) / len(ranges)
    denominator = sum((angle - mean_angle) ** 2 for angle in angles)
    slope = sum(
        (angle - mean_angle) * (shot_range - mean_range)
        for angle, shot_range in points
    ) / denominator
    if slope <= 25.0:
        return None
    intercept = mean_range - slope * mean_angle
    estimate = (target_range_yards - intercept) / slope
    remaining = target_range_yards - max(ranges)
    if remaining > max(75.0, target_range_yards * 0.25):
        return None
    # Close to the target, terrain contact makes a long extrapolation unstable:
    # advance only one setting increment and observe the next collision.
    if 0 < remaining <= 25.0:
        estimate = min(estimate, max(angles) + 0.01)
    if estimate < min(angles) - 0.25 or estimate > max(angles) + 0.25:
        return None
    return EmpiricalAim(estimate, len(points), len(far_samples))
