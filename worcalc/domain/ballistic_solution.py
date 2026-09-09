"""Application-facing ballistic elevation solver without UI dependencies."""

from __future__ import annotations

from pathlib import Path
import json
from .physics_solution import LaunchGeometry, PhysicsSolver

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
    ARTILLERY_PHYSICS,
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
        self.set_weapon("3-inch Ordnance", "Shell")
        self.method_index = len(self.models)

    @property
    def is_unified(self) -> bool:
        return self.method_index == len(self.models)

    def set_weapon(self, cannon: str, projectile: str) -> None:
        speed, drag = ARTILLERY_PHYSICS[cannon][projectile]
        self.set_physics_profile(speed, drag)
        settings = json.loads(Path(__file__).with_name("launch_profiles.json").read_text(encoding="utf-8"))
        self.physics = PhysicsSolver(speed, drag, launch=LaunchGeometry(**settings[cannon]))

    def flight_time(self, yards: float, height: float) -> float | None:
        if yards == 0:
            return None
        aim = self.physics.solve(yards, height)
        return aim.flight_time_seconds if aim is not None else None

    def set_physics_profile(
        self,
        speed_metres_per_second: float,
        drag_per_second: float,
    ) -> None:
        """Update the selectable theoretical curve for the active weapon."""
        self.physics = PhysicsSolver(speed_metres_per_second, drag_per_second,
                                     launch=getattr(getattr(self, "physics", None), "launch", LaunchGeometry()))

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
        return [model.name for model in self.models] + ["Unified physics (provisional)"]

    @property
    def method_name(self) -> str:
        return self.method_names[self.method_index]

    def set_method(self, index: int) -> None:
        if not 0 <= index < len(self.method_names):
            raise ValueError(f"Unknown ballistic method index: {index}")
        self.method_index = index

    def solve(
        self,
        horizontal_range_yards: float,
        target_height_change_metres: float,
    ) -> float | None:
        if self.is_unified:
            if horizontal_range_yards == 0:
                return None
            aim = self.physics.solve(horizontal_range_yards, target_height_change_metres)
            return aim.elevation_degrees if aim else None
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
        if self.is_unified:
            return self.physics.clearance(horizontal_range_yards, target_height_change_metres, terrain_profile)
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
