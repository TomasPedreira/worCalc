"""Application-facing ballistic elevation solver without UI dependencies."""

from __future__ import annotations

from pathlib import Path

from .ballistics import (
    CurveModel,
    LinearDragTrajectoryModel,
    LinearModel,
    PchipModel,
    PolynomialModel,
    boresight_angle_offset,
    elevation_for_range,
    height_adjusted_elevation,
    load_reference_points,
)
from .projectile import (
    ARTILLERY_GRAVITY_METRES_PER_SECOND_SQUARED,
    ARTILLERY_MUZZLE_HEIGHT_METRES,
    THREE_INCH_SHELL_DRAG_PER_SECOND,
    THREE_INCH_SPEED_METRES_PER_SECOND,
)
from .trajectory import (
    TerrainProfilePoint,
    TrajectoryClearanceResult,
    analyze_trajectory_clearance,
)


class BallisticSolutionEngine:
    def __init__(self, reference_path: Path) -> None:
        self.points = load_reference_points(reference_path)
        self.models: list[CurveModel] = [
            LinearModel(self.points),
            PchipModel(self.points),
            PolynomialModel(self.points, 2),
            PolynomialModel(self.points, 3),
        ]
        self._theoretical_model_index = len(self.models)
        self.set_physics_profile(
            THREE_INCH_SPEED_METRES_PER_SECOND["Shell"],
            THREE_INCH_SHELL_DRAG_PER_SECOND,
        )
        self.method_index = 3

    def set_physics_profile(
        self,
        speed_metres_per_second: float,
        drag_per_second: float,
    ) -> None:
        """Update the selectable theoretical curve for the active weapon."""

        muzzle_height_metres = ARTILLERY_MUZZLE_HEIGHT_METRES
        gravity = ARTILLERY_GRAVITY_METRES_PER_SECOND_SQUARED
        first_point = self.points[0]
        angle_offset = boresight_angle_offset(
            speed_metres_per_second,
            drag_per_second,
            gravity,
            muzzle_height_metres,
            first_point.elevation_deg,
            first_point.range_yards,
        )
        model = LinearDragTrajectoryModel(
            speed_metres_per_second,
            drag_per_second,
            gravity_metres_per_second_squared=gravity,
            angle_offset_deg=angle_offset,
            muzzle_height_metres=muzzle_height_metres,
        )
        model.name = "Theoretical physics"
        if len(self.models) == self._theoretical_model_index:
            self.models.append(model)
        else:
            self.models[self._theoretical_model_index] = model

    @property
    def method_names(self) -> list[str]:
        return [model.name for model in self.models]

    @property
    def method_name(self) -> str:
        return self.models[self.method_index].name

    def set_method(self, index: int) -> None:
        if not 0 <= index < len(self.models):
            raise ValueError(f"Unknown ballistic method index: {index}")
        self.method_index = index

    def solve(
        self,
        horizontal_range_yards: float,
        target_height_change_metres: float,
    ) -> float | None:
        minimum = self.points[0].elevation_deg
        maximum = self.points[-1].elevation_deg
        base_elevation = elevation_for_range(
            self.models[self.method_index],
            horizontal_range_yards,
            minimum,
            maximum,
        )
        if base_elevation is None:
            return None
        return height_adjusted_elevation(
            base_elevation,
            horizontal_range_yards,
            target_height_change_metres,
        )

    def analyze_clearance(
        self,
        horizontal_range_yards: float,
        target_height_change_metres: float,
        terrain_profile: tuple[TerrainProfilePoint, ...],
        speed_metres_per_second: float,
        drag_per_second: float,
        safety_margin_metres: float = 0.01,
    ) -> TrajectoryClearanceResult | None:
        angle = self.solve(
            horizontal_range_yards,
            target_height_change_metres,
        )
        if angle is None:
            return None
        return analyze_trajectory_clearance(
            terrain_profile,
            horizontal_range_yards,
            angle,
            speed_metres_per_second,
            drag_per_second,
            gravity_metres_per_second_squared=(
                ARTILLERY_GRAVITY_METRES_PER_SECOND_SQUARED
            ),
            muzzle_height_metres=ARTILLERY_MUZZLE_HEIGHT_METRES,
            safety_margin_metres=safety_margin_metres,
            confidence="estimated",
        )
