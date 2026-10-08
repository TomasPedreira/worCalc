//! Port of the unified physics model used by the mobile workflow.
use crate::{Result, METRES_TO_YARDS};
use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, Deserialize, Serialize)]
pub struct Launch {
    pub height_metres: f64,
    pub forward_metres: f64,
    pub angle_offset_deg: f64,
    pub minimum_display_deg: f64,
    pub maximum_display_deg: f64,
}
impl Default for Launch {
    fn default() -> Self {
        Self {
            height_metres: 1.2,
            forward_metres: 0.,
            angle_offset_deg: 0.48,
            minimum_display_deg: -8.,
            maximum_display_deg: 13.7,
        }
    }
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize)]
pub struct Physics {
    pub speed: f64,
    pub drag: f64,
    pub gravity: f64,
    pub launch: Launch,
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize)]
pub struct Point {
    pub x: f64,
    pub y: f64,
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize)]
pub struct ProfilePoint {
    pub distance_yards: f64,
    pub elevation_metres: f64,
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize)]
pub struct Aim {
    pub elevation_degrees: f64,
    pub flight_time_seconds: f64,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct Clearance {
    pub obstructed: bool,
    pub first_obstruction_yards: Option<f64>,
    pub clearing_elevation_deg: Option<f64>,
    pub height_above_target_metres: Option<f64>,
}
impl Physics {
    pub fn validate(&self) -> Result<()> {
        let l = self.launch;
        if ![
            self.speed,
            self.drag,
            self.gravity,
            l.height_metres,
            l.forward_metres,
            l.angle_offset_deg,
            l.minimum_display_deg,
            l.maximum_display_deg,
        ]
        .iter()
        .all(|v| v.is_finite())
            || self.speed <= 0.
            || self.drag < 0.
            || self.gravity <= 0.
            || l.height_metres < 0.
            || l.forward_metres < 0.
            || l.minimum_display_deg + l.angle_offset_deg <= -89.
            || l.maximum_display_deg + l.angle_offset_deg >= 89.
            || l.minimum_display_deg >= l.maximum_display_deg
        {
            return Err("Invalid projectile physics or launch geometry".into());
        }
        Ok(())
    }
    pub fn at_distance(&self, yards: f64, display_deg: f64) -> Option<(f64, f64)> {
        if !yards.is_finite() || !display_deg.is_finite() || yards < 0. {
            return None;
        }
        let theta = (display_deg + self.launch.angle_offset_deg).to_radians();
        let (sine, cosine) = theta.sin_cos();
        let vx = self.speed * cosine;
        let vz = self.speed * sine;
        let distance = yards / METRES_TO_YARDS - self.launch.forward_metres * cosine;
        if vx <= 0. || distance < 0. {
            return None;
        }
        let height = self.launch.height_metres + self.launch.forward_metres * sine;
        if self.drag == 0. {
            let time = distance / vx;
            return Some((height + vz * time - self.gravity * time * time / 2., time));
        }
        let ratio = self.drag * distance / vx;
        if ratio >= 1. {
            return None;
        }
        let time = -(-ratio).ln_1p() / self.drag;
        let q = self.drag * time;
        let travel = -(-q).exp_m1() / self.drag;
        let fall = if q.abs() < 1e-3 {
            time * time / 2. * (1. - q / 3. + q * q / 12. - q.powi(3) / 60.)
        } else {
            (time - travel) / self.drag
        };
        Some((height + vz * travel - self.gravity * fall, time))
    }
    pub fn solve(&self, yards: f64, height: f64, limited: bool) -> Result<Option<Aim>> {
        self.validate()?;
        if !yards.is_finite() || yards <= 0. || !height.is_finite() {
            return Err("Target range must be positive and target height finite".into());
        }
        if yards / METRES_TO_YARDS <= self.launch.forward_metres {
            return Ok(None);
        }
        let mut lo = if limited {
            self.launch.minimum_display_deg
        } else {
            -89. - self.launch.angle_offset_deg + 1e-8
        };
        let mut hi = if limited {
            self.launch.maximum_display_deg
        } else {
            89. - self.launch.angle_offset_deg - 1e-8
        };
        if self.drag != 0. {
            let ratio =
                yards / METRES_TO_YARDS / (self.launch.forward_metres + self.speed / self.drag);
            if ratio >= 1. {
                return Ok(None);
            }
            let limit = ratio.acos().to_degrees() - 1e-8;
            lo = lo.max(-limit - self.launch.angle_offset_deg);
            hi = hi.min(limit - self.launch.angle_offset_deg);
        }
        if lo >= hi {
            return Ok(None);
        }
        let residual = |angle| {
            self.at_distance(yards, angle)
                .map_or(f64::NEG_INFINITY, |s| s.0 - height)
        };
        let mut left = lo;
        let mut right = hi;
        for _ in 0..80 {
            let a = left + (right - left) / 3.;
            let b = right - (right - left) / 3.;
            if residual(a) < residual(b) {
                left = a;
            } else {
                right = b;
            }
        }
        let mut peak = lo;
        for candidate in [hi, (left + right) / 2.] {
            if residual(candidate) > residual(peak) {
                peak = candidate;
            }
        }
        if residual(lo) > 1e-7 || residual(peak) < -1e-7 {
            return Ok(None);
        }
        right = peak;
        for _ in 0..65 {
            let middle = (lo + right) / 2.;
            if residual(middle) < 0. {
                lo = middle;
            } else {
                right = middle;
            }
        }
        let angle = (lo + right) / 2.;
        Ok(self.at_distance(yards, angle).map(|s| Aim {
            elevation_degrees: angle,
            flight_time_seconds: s.1,
        }))
    }
    pub fn impact_range(&self, profile: &[ProfilePoint], angle: f64) -> Option<f64> {
        if profile.len() < 2 {
            return None;
        }
        let ground = profile[0].elevation_metres;
        let mut previous = profile[0];
        for sample in &profile[1..] {
            let state = self.at_distance(sample.distance_yards, angle)?;
            if ground + state.0 - sample.elevation_metres > 0. {
                previous = *sample;
                continue;
            }
            return self.crossing(previous, *sample, ground, angle);
        }
        None
    }
    fn crossing(&self, a: ProfilePoint, b: ProfilePoint, ground: f64, angle: f64) -> Option<f64> {
        let mut left = a.distance_yards;
        let mut right = b.distance_yards;
        for _ in 0..45 {
            let middle = (left + right) / 2.;
            let fraction = (middle - a.distance_yards) / (b.distance_yards - a.distance_yards);
            let terrain = a.elevation_metres + fraction * (b.elevation_metres - a.elevation_metres);
            if ground + self.at_distance(middle, angle)?.0 > terrain {
                left = middle;
            } else {
                right = middle;
            }
        }
        Some((left + right) / 2.)
    }
    pub fn clearance(
        &self,
        yards: f64,
        height: f64,
        profile: &[ProfilePoint],
        limited: bool,
    ) -> Result<Option<Clearance>> {
        let Some(aim) = self.solve(yards, height, limited)? else {
            return Ok(None);
        };
        if profile.len() < 2
            || profile[0].distance_yards != 0.
            || profile.last().unwrap().distance_yards < yards
            || profile
                .iter()
                .any(|p| !p.distance_yards.is_finite() || !p.elevation_metres.is_finite())
            || profile
                .windows(2)
                .any(|p| p[0].distance_yards >= p[1].distance_yards)
        {
            return Err(
                "Terrain profile must be finite, ordered and extend from gun to target".into(),
            );
        }
        let ground = profile[0].elevation_metres;
        let mut points = profile.to_vec();
        let spawn = self.launch.forward_metres
            * (aim.elevation_degrees + self.launch.angle_offset_deg)
                .to_radians()
                .cos()
            * METRES_TO_YARDS;
        for distance in [spawn, yards] {
            if points.iter().any(|p| p.distance_yards == distance) {
                continue;
            }
            if let Some(pair) = profile
                .windows(2)
                .find(|p| p[0].distance_yards < distance && distance < p[1].distance_yards)
            {
                let f = (distance - pair[0].distance_yards)
                    / (pair[1].distance_yards - pair[0].distance_yards);
                points.push(ProfilePoint {
                    distance_yards: distance,
                    elevation_metres: pair[0].elevation_metres
                        + f * (pair[1].elevation_metres - pair[0].elevation_metres),
                });
            }
            points.sort_by(|a, b| a.distance_yards.total_cmp(&b.distance_yards));
        }
        let mut first = None;
        let mut previous: Option<(ProfilePoint, f64)> = None;
        for p in points.iter().filter(|p| p.distance_yards <= yards) {
            let Some(state) = self.at_distance(p.distance_yards, aim.elevation_degrees) else {
                continue;
            };
            let clearance = ground + state.0 - p.elevation_metres;
            if clearance < -1e-6
                || (spawn + 1e-6 < p.distance_yards
                    && p.distance_yards < yards - 1e-6
                    && clearance <= 1e-6)
            {
                first = match previous {
                    Some((prev, c)) if c > 0. => {
                        self.crossing(prev, *p, ground, aim.elevation_degrees)
                    }
                    _ => Some(p.distance_yards),
                };
                break;
            }
            previous = Some((*p, clearance));
        }
        let mut clearing = Some(aim.elevation_degrees);
        if first.is_some() {
            let is_clear = |angle| {
                points
                    .iter()
                    .filter(|p| spawn + 1e-6 < p.distance_yards && p.distance_yards < yards - 1e-6)
                    .all(|p| {
                        self.at_distance(p.distance_yards, angle)
                            .is_some_and(|s| s.0 - (p.elevation_metres - ground) >= 0.01)
                    })
            };
            let mut low = aim.elevation_degrees;
            let mut high = self.launch.maximum_display_deg;
            if !limited {
                high = if self.drag != 0. {
                    (yards
                        / METRES_TO_YARDS
                        / (self.launch.forward_metres + self.speed / self.drag))
                        .acos()
                        .to_degrees()
                        - self.launch.angle_offset_deg
                        - 1e-8
                } else {
                    89. - self.launch.angle_offset_deg - 1e-8
                };
                let mut left = low;
                let mut right = high;
                for _ in 0..80 {
                    let a = left + (right - left) / 3.;
                    let b = right - (right - left) / 3.;
                    match (self.at_distance(yards, a), self.at_distance(yards, b)) {
                        (Some(sa), Some(sb)) if sa.0 < sb.0 => left = a,
                        _ => right = b,
                    }
                }
                high = (left + right) / 2.;
            }
            if is_clear(high) {
                for _ in 0..60 {
                    let middle = (low + high) / 2.;
                    if is_clear(middle) {
                        high = middle;
                    } else {
                        low = middle;
                    }
                }
                clearing = Some(high);
            } else {
                clearing = None;
            }
        }
        let end = points
            .iter()
            .rev()
            .find(|p| p.distance_yards <= yards)
            .unwrap();
        let target_height = clearing
            .and_then(|a| self.at_distance(end.distance_yards, a))
            .map(|s| ground + s.0 - end.elevation_metres);
        Ok(Some(Clearance {
            obstructed: first.is_some(),
            first_obstruction_yards: first,
            clearing_elevation_deg: clearing,
            height_above_target_metres: target_height,
        }))
    }
}
