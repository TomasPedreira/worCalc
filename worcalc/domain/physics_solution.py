"""One linear-drag trajectory for targeting, time and sampled terrain collision."""

from dataclasses import dataclass
from math import acos, cos, degrees, expm1, isfinite, log1p, radians, sin

from .calibration import METRES_TO_YARDS
from .trajectory import TerrainProfilePoint, TrajectoryClearanceResult, TrajectorySample


@dataclass(frozen=True)
class LaunchGeometry:
    # Provisional runtime assumptions; model measurements alone do not prove them.
    height_metres: float = 1.2
    forward_metres: float = 0.0
    angle_offset_deg: float = 0.48
    minimum_display_deg: float = -8.0
    maximum_display_deg: float = 13.7

    def __post_init__(self):
        if not all(isfinite(v) for v in vars(self).values()):
            raise ValueError("Launch settings must be finite")
        if self.height_metres < 0 or self.forward_metres < 0:
            raise ValueError("Launch height and forward offset cannot be negative")
        if not -89 < self.minimum_display_deg + self.angle_offset_deg < self.maximum_display_deg + self.angle_offset_deg < 89:
            raise ValueError("Launch angle limits must be ordered within -89 to 89 degrees")


@dataclass(frozen=True)
class PhysicalAim:
    elevation_degrees: float
    flight_time_seconds: float


@dataclass(frozen=True)
class PhysicsSolver:
    speed: float
    drag: float
    gravity: float = 9.1
    launch: LaunchGeometry = LaunchGeometry()

    def __post_init__(self):
        if not all(isfinite(v) for v in (self.speed, self.drag, self.gravity)) or self.speed <= 0 or self.drag < 0 or self.gravity <= 0:
            raise ValueError("Invalid projectile physics")

    def at_distance(self, yards: float, display_deg: float) -> tuple[float, float] | None:
        """Return (height above gun ground, time) at a horizontal range."""
        if not all(isfinite(v) for v in (yards, display_deg)) or yards < 0:
            raise ValueError("Range and angle must be finite; range cannot be negative")
        theta = radians(display_deg + self.launch.angle_offset_deg)
        vx, vz = self.speed * cos(theta), self.speed * sin(theta)
        distance = yards / METRES_TO_YARDS - self.launch.forward_metres * cos(theta)
        if vx <= 0 or distance < 0:
            return None
        height = self.launch.height_metres + self.launch.forward_metres * sin(theta)
        if self.drag == 0:
            time = distance / vx
            return height + vz * time - self.gravity * time * time / 2, time
        ratio = self.drag * distance / vx
        if ratio >= 1:
            return None
        time = -log1p(-ratio) / self.drag
        # Stable displacement integral, including the zero-drag limit.
        q = self.drag * time
        travel = -expm1(-q) / self.drag
        fall = (time*time/2 * (1-q/3+q*q/12-q**3/60)
                if abs(q) < 1e-3 else (time-travel)/self.drag)
        return height + vz * travel - self.gravity * fall, time

    def solve(self, yards: float, target_height: float) -> PhysicalAim | None:
        if not isfinite(yards) or yards <= 0 or not isfinite(target_height):
            raise ValueError("Target range must be positive and target height finite")
        lo, hi = self.launch.minimum_display_deg, self.launch.maximum_display_deg
        if yards / METRES_TO_YARDS <= self.launch.forward_metres:
            return None
        if self.drag:
            ratio = yards / METRES_TO_YARDS / (self.launch.forward_metres + self.speed/self.drag)
            if ratio >= 1:
                return None
            limit = degrees(acos(ratio)) - 1e-8
            lo = max(lo, -limit-self.launch.angle_offset_deg)
            hi = min(hi, limit-self.launch.angle_offset_deg)
        if lo >= hi:
            return None

        def residual(angle):
            state = self.at_distance(yards, angle)
            return state[0]-target_height if state is not None else float('-inf')

        # Find the reachable height maximum, then the lower-angle target root.
        left, right = lo, hi
        for _ in range(80):
            a, b = left+(right-left)/3, right-(right-left)/3
            if residual(a) < residual(b):
                left = a
            else:
                right = b
        peak = max((lo, hi, (left+right)/2), key=residual)
        if residual(lo) > 1e-7 or residual(peak) < -1e-7:
            return None
        right = peak
        for _ in range(65):
            middle = (lo+right)/2
            if residual(middle) < 0:
                lo = middle
            else:
                right = middle
        angle = (lo+right)/2
        state = self.at_distance(yards, angle)
        return PhysicalAim(angle, state[1]) if state else None

    def clearance(self, yards: float, target_height: float,
                  profile: tuple[TerrainProfilePoint, ...],
                  safety_margin_metres: float = 0.01) -> TrajectoryClearanceResult | None:
        aim = self.solve(yards, target_height)
        if aim is None:
            return None
        if (len(profile) < 2 or profile[0].distance_yards != 0 or profile[-1].distance_yards < yards
                or any(not isfinite(p.distance_yards) or not isfinite(p.elevation_metres) for p in profile)
                or any(a.distance_yards >= b.distance_yards for a,b in zip(profile,profile[1:]))):
            raise ValueError("Terrain profile must be finite, ordered and extend from gun to target")
        ground = profile[0].elevation_metres
        samples = []
        # Include target explicitly even when a desktop profile extends past it.
        points = list(profile)
        spawn_yards = self.launch.forward_metres*cos(radians(aim.elevation_degrees+self.launch.angle_offset_deg))*METRES_TO_YARDS
        for distance in (spawn_yards, yards):
            if any(p.distance_yards == distance for p in points):
                continue
            for a,b in zip(profile,profile[1:]):
                if a.distance_yards < distance < b.distance_yards:
                    f = (distance-a.distance_yards)/(b.distance_yards-a.distance_yards)
                    points.append(TerrainProfilePoint(distance,a.elevation_metres+f*(b.elevation_metres-a.elevation_metres)))
                    break
            points.sort(key=lambda p:p.distance_yards)
        for p in points:
            if p.distance_yards > yards:
                break
            state = self.at_distance(p.distance_yards, aim.elevation_degrees)
            if state is not None:
                samples.append(TrajectorySample(p.distance_yards,p.elevation_metres,ground+state[0]))
        first = None
        # The linear-drag arc is concave in horizontal distance. Against each
        # linear terrain segment, positive endpoints rule out an interior dip.
        # Find first crossing with the same physical arc, not a warped curve.
        previous = None
        for sample in samples:
            if (sample.clearance_metres < -1e-6 or
                    spawn_yards+1e-6 < sample.distance_yards < yards-1e-6 and sample.clearance_metres <= 1e-6):
                if previous is None or previous.clearance_metres <= 0:
                    first = sample.distance_yards
                else:
                    left,right = previous.distance_yards,sample.distance_yards
                    for _ in range(45):
                        middle=(left+right)/2
                        f=(middle-previous.distance_yards)/(sample.distance_yards-previous.distance_yards)
                        terrain=previous.terrain_elevation_metres+f*(sample.terrain_elevation_metres-previous.terrain_elevation_metres)
                        if ground+self.at_distance(middle,aim.elevation_degrees)[0] > terrain:
                            left=middle
                        else:
                            right=middle
                    first=(left+right)/2
                break
            previous=sample
        obstructed = first is not None
        target_sample = samples[-1]
        impact = first if obstructed else (yards if abs(target_sample.clearance_metres) < 1e-5 else None)
        clearing_angle = aim.elevation_degrees
        clearing_samples = tuple(samples)
        if obstructed:
            def trajectory(angle: float) -> tuple[TrajectorySample, ...]:
                result = []
                for point in points:
                    if point.distance_yards > yards:
                        break
                    state = self.at_distance(point.distance_yards, angle)
                    if state is not None:
                        result.append(TrajectorySample(
                            point.distance_yards,
                            point.elevation_metres,
                            ground + state[0],
                        ))
                return tuple(result)

            def is_clear(angle: float) -> bool:
                candidate = trajectory(angle)
                return bool(candidate) and all(
                    sample.clearance_metres >= safety_margin_metres
                    for sample in candidate
                    if spawn_yards + 1e-6 < sample.distance_yards < yards - 1e-6
                )

            low = aim.elevation_degrees
            high = self.launch.maximum_display_deg
            if is_clear(high):
                for _ in range(60):
                    middle = (low + high) / 2
                    if is_clear(middle):
                        high = middle
                    else:
                        low = middle
                clearing_angle = high
                clearing_samples = trajectory(high)
            else:
                clearing_angle = None
                clearing_samples = ()
        height_above_target = (
            clearing_samples[-1].clearance_metres if clearing_samples else None
        )
        return TrajectoryClearanceResult(
            'provisional physics',yards,aim.elevation_degrees,obstructed,first,
            min((s.clearance_metres for s in samples),default=None),
            clearing_angle,
            impact,impact-yards if impact is not None else None,
            height_above_target,
            tuple(samples),clearing_samples,
        )
