from __future__ import annotations

import csv
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from math import atan2, cos, degrees, exp, radians, sin, sqrt
from pathlib import Path
from typing import Protocol

from .calibration import METRES_TO_YARDS


@dataclass(frozen=True)
class ReferencePoint:
    elevation_deg: float
    range_yards: float


def load_reference_points(path: Path) -> list[ReferencePoint]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    try:
        points = [
            ReferencePoint(float(row["elevation_deg"]), float(row["range_yards"]))
            for row in rows
        ]
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("CSV must contain numeric elevation_deg and range_yards columns.") from error
    if len(points) < 2:
        raise ValueError("At least two reference points are required.")
    if any(a.elevation_deg >= b.elevation_deg for a, b in zip(points, points[1:])):
        raise ValueError("Elevations must be strictly increasing.")
    if any(a.range_yards >= b.range_yards for a, b in zip(points, points[1:])):
        raise ValueError("Ranges must be strictly increasing.")
    return points


class CurveModel(Protocol):
    name: str

    def evaluate(self, elevation_deg: float) -> float: ...


class LinearModel:
    name = "Linear interpolation"

    def __init__(self, points: list[ReferencePoint]) -> None:
        self.points = points
        self.x = [point.elevation_deg for point in points]

    def evaluate(self, elevation_deg: float) -> float:
        index = max(0, min(bisect_right(self.x, elevation_deg) - 1, len(self.x) - 2))
        left, right = self.points[index], self.points[index + 1]
        fraction = (elevation_deg - left.elevation_deg) / (right.elevation_deg - left.elevation_deg)
        return left.range_yards + fraction * (right.range_yards - left.range_yards)


class PchipModel:
    name = "PCHIP interpolation"

    def __init__(self, points: list[ReferencePoint]) -> None:
        self.points = points
        self.x = [point.elevation_deg for point in points]
        self.y = [point.range_yards for point in points]
        self.derivatives = self._derivatives()

    def _derivatives(self) -> list[float]:
        count = len(self.x)
        steps = [self.x[i + 1] - self.x[i] for i in range(count - 1)]
        slopes = [(self.y[i + 1] - self.y[i]) / steps[i] for i in range(count - 1)]
        if count == 2:
            return [slopes[0], slopes[0]]
        derivatives = [0.0] * count
        for index in range(1, count - 1):
            before, after = slopes[index - 1], slopes[index]
            if before * after <= 0:
                derivatives[index] = 0.0
            else:
                weight_1 = 2 * steps[index] + steps[index - 1]
                weight_2 = steps[index] + 2 * steps[index - 1]
                derivatives[index] = (weight_1 + weight_2) / (
                    weight_1 / before + weight_2 / after
                )
        derivatives[0] = self._endpoint_slope(steps[0], steps[1], slopes[0], slopes[1])
        derivatives[-1] = self._endpoint_slope(
            steps[-1], steps[-2], slopes[-1], slopes[-2]
        )
        return derivatives

    @staticmethod
    def _endpoint_slope(here: float, adjacent: float, slope: float, adjacent_slope: float) -> float:
        derivative = ((2 * here + adjacent) * slope - here * adjacent_slope) / (here + adjacent)
        if derivative * slope <= 0:
            return 0.0
        if slope * adjacent_slope < 0 and abs(derivative) > abs(3 * slope):
            return 3 * slope
        return derivative

    def evaluate(self, elevation_deg: float) -> float:
        index = max(0, min(bisect_right(self.x, elevation_deg) - 1, len(self.x) - 2))
        step = self.x[index + 1] - self.x[index]
        t = (elevation_deg - self.x[index]) / step
        h00 = 2 * t**3 - 3 * t**2 + 1
        h10 = t**3 - 2 * t**2 + t
        h01 = -2 * t**3 + 3 * t**2
        h11 = t**3 - t**2
        return (
            h00 * self.y[index]
            + h10 * step * self.derivatives[index]
            + h01 * self.y[index + 1]
            + h11 * step * self.derivatives[index + 1]
        )


class PolynomialModel:
    def __init__(self, points: list[ReferencePoint], degree: int) -> None:
        self.points = points
        self.degree = degree
        self.name = f"Polynomial degree {degree}"
        x = [point.elevation_deg for point in points]
        y = [point.range_yards for point in points]
        matrix = [
            [sum(value ** (row + column) for value in x) for column in range(degree + 1)]
            for row in range(degree + 1)
        ]
        vector = [sum(target * value**power for value, target in zip(x, y)) for power in range(degree + 1)]
        self.coefficients = _solve(matrix, vector)

    def evaluate(self, elevation_deg: float) -> float:
        return sum(coefficient * elevation_deg**power for power, coefficient in enumerate(self.coefficients))

    @property
    def equation(self) -> str:
        terms = [f"{self.coefficients[0]:.3f}"]
        for power, coefficient in enumerate(self.coefficients[1:], start=1):
            terms.append(f"{coefficient:+.3f}θ" + (f"^{power}" if power > 1 else ""))
        return "R(θ) = " + " ".join(terms)


class LinearDragTrajectoryModel:
    """Projectile range from an elevated muzzle with gravity and linear drag."""

    METRES_TO_YARDS = 1.0936132983377078

    def __init__(
        self,
        speed_metres_per_second: float,
        drag_per_second: float,
        gravity_metres_per_second_squared: float = 9.81,
        angle_offset_deg: float = 0.0,
        muzzle_height_metres: float = 0.0,
    ) -> None:
        if speed_metres_per_second <= 0:
            raise ValueError("Muzzle velocity must be positive.")
        if drag_per_second < 0:
            raise ValueError("Drag cannot be negative.")
        if gravity_metres_per_second_squared <= 0:
            raise ValueError("Gravity must be positive.")
        if muzzle_height_metres < 0:
            raise ValueError("Muzzle height cannot be negative.")
        self.speed = speed_metres_per_second
        self.drag = drag_per_second
        self.gravity = gravity_metres_per_second_squared
        self.angle_offset_deg = angle_offset_deg
        self.muzzle_height = muzzle_height_metres
        self.name = (
            f"Theoretical ({self.speed:g} m/s, drag {self.drag:g} 1/s"
            f", muzzle {self.muzzle_height / 0.3048:.2f} ft"
            + (f", offset {self.angle_offset_deg:+g}°" if self.angle_offset_deg else "")
            + ")"
        )

    def evaluate(self, elevation_deg: float) -> float:
        theta = radians(elevation_deg + self.angle_offset_deg)
        vertical_speed = self.speed * sin(theta)
        horizontal_speed = self.speed * cos(theta)
        if self.muzzle_height == 0 and vertical_speed <= 0:
            return 0.0
        if horizontal_speed <= 0:
            return 0.0
        if self.drag == 0:
            flight_time = (
                vertical_speed
                + sqrt(
                    vertical_speed**2
                    + 2 * self.gravity * self.muzzle_height
                )
            ) / self.gravity
            return horizontal_speed * flight_time * self.METRES_TO_YARDS

        drag = self.drag
        gravity = self.gravity

        def height(time: float) -> float:
            return (
                self.muzzle_height
                + (vertical_speed + gravity / drag)
                * (1 - exp(-drag * time))
                / drag
                - gravity * time / drag
            )

        low = 0.0
        high = max(1.0, 2 * max(vertical_speed, 0.0) / gravity + 1.0)
        while height(high) > 0:
            high *= 2
        for _ in range(80):
            middle = (low + high) / 2
            if height(middle) > 0:
                low = middle
            else:
                high = middle
        flight_time = (low + high) / 2
        horizontal_metres = horizontal_speed * (1 - exp(-drag * flight_time)) / drag
        return horizontal_metres * self.METRES_TO_YARDS


def boresight_angle_offset(
    speed_metres_per_second: float,
    drag_per_second: float,
    gravity_metres_per_second_squared: float,
    muzzle_height_metres: float,
    displayed_elevation_deg: float,
    target_range_yards: float,
) -> float:
    """Find the low-angle bore offset that hits a boresight reference range."""

    low, high = -10.0 - displayed_elevation_deg, 45.0 - displayed_elevation_deg

    def range_with_offset(offset: float) -> float:
        return LinearDragTrajectoryModel(
            speed_metres_per_second,
            drag_per_second,
            gravity_metres_per_second_squared,
            angle_offset_deg=offset,
            muzzle_height_metres=muzzle_height_metres,
        ).evaluate(displayed_elevation_deg)

    if not range_with_offset(low) <= target_range_yards <= range_with_offset(high):
        raise ValueError("Boresight range has no low-angle trajectory solution.")
    for _ in range(80):
        middle = (low + high) / 2
        if range_with_offset(middle) < target_range_yards:
            low = middle
        else:
            high = middle
    return (low + high) / 2


def _solve(matrix: list[list[float]], vector: list[float]) -> list[float]:
    size = len(vector)
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(matrix[row][column]))
        matrix[column], matrix[pivot] = matrix[pivot], matrix[column]
        vector[column], vector[pivot] = vector[pivot], vector[column]
        divisor = matrix[column][column]
        for index in range(column, size):
            matrix[column][index] /= divisor
        vector[column] /= divisor
        for row in range(size):
            if row == column:
                continue
            factor = matrix[row][column]
            for index in range(column, size):
                matrix[row][index] -= factor * matrix[column][index]
            vector[row] -= factor * vector[column]
    return vector


def elevation_for_range(
    model: CurveModel,
    target_yards: float,
    minimum_elevation: float,
    maximum_elevation: float,
) -> float | None:
    low, high = minimum_elevation, maximum_elevation
    low_residual = model.evaluate(low) - target_yards
    high_residual = model.evaluate(high) - target_yards
    if low_residual == 0:
        return low
    if high_residual == 0:
        return high

    span = max(maximum_elevation - minimum_elevation, 1.0)
    if low_residual > 0 and high_residual > 0:
        high, high_residual = low, low_residual
        step = span
        for _ in range(60):
            low = high - step
            low_residual = model.evaluate(low) - target_yards
            if low_residual * high_residual <= 0:
                break
            high, high_residual = low, low_residual
            step *= 1.5
        else:
            return None
    elif low_residual < 0 and high_residual < 0:
        low, low_residual = high, high_residual
        step = span
        for _ in range(60):
            high = low + step
            high_residual = model.evaluate(high) - target_yards
            if low_residual * high_residual <= 0:
                break
            low, low_residual = high, high_residual
            step *= 1.5
        else:
            return None

    for _ in range(70):
        middle = (low + high) / 2
        middle_residual = model.evaluate(middle) - target_yards
        if low_residual * middle_residual <= 0:
            high = middle
            high_residual = middle_residual
        else:
            low = middle
            low_residual = middle_residual
    return (low + high) / 2


def height_adjusted_elevation(
    level_ground_elevation_deg: float,
    horizontal_range_yards: float,
    target_height_change_metres: float,
) -> float:
    """Add the signed gun-to-target sight angle to a level-ground solution."""

    if horizontal_range_yards < 0:
        raise ValueError("Horizontal range cannot be negative.")
    sight_angle = degrees(
        atan2(
            target_height_change_metres * METRES_TO_YARDS,
            horizontal_range_yards,
        )
    )
    return level_ground_elevation_deg + sight_angle


def reference_bracket(
    points: list[ReferencePoint], target_yards: float
) -> tuple[ReferencePoint, ReferencePoint]:
    ranges = [point.range_yards for point in points]
    index = bisect_left(ranges, target_yards)
    if index <= 0:
        return points[0], points[0]
    if index >= len(points):
        return points[-1], points[-1]
    if ranges[index] == target_yards:
        return points[index], points[index]
    return points[index - 1], points[index]


def rmse(model: CurveModel, points: list[ReferencePoint]) -> float:
    return sqrt(
        sum((model.evaluate(point.elevation_deg) - point.range_yards) ** 2 for point in points)
        / len(points)
    )
