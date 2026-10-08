use crate::{
    empirical::{estimate, Sample},
    physics::{Launch, Physics, Point, ProfilePoint},
    terrain::Terrain,
    Result, METRES_TO_YARDS,
};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{collections::VecDeque, sync::Arc};
pub trait AssetStore: Send + Sync {
    fn read(&self, path: &str) -> Result<Vec<u8>>;
}
#[derive(Clone, Deserialize)]
pub struct Calibration {
    pub pixel_x_world_x: f64,
    pub pixel_x_world_y: f64,
    pub pixel_y_world_x: f64,
    pub pixel_y_world_y: f64,
}
impl Calibration {
    fn delta(&self, x: f64, y: f64) -> Point {
        Point {
            x: self.pixel_x_world_x * x + self.pixel_y_world_x * y,
            y: self.pixel_x_world_y * x + self.pixel_y_world_y * y,
        }
    }
    fn distance(&self, a: Point, b: Point) -> f64 {
        let p = self.delta(b.x - a.x, b.y - a.y);
        p.x.hypot(p.y) * METRES_TO_YARDS
    }
}
#[derive(Clone, Deserialize)]
pub struct Map {
    pub identifier: String,
    pub name: String,
    pub battlefield: String,
    pub mode: String,
    pub layer: String,
    pub width_pixels: u32,
    pub height_pixels: u32,
    pub calibration: Calibration,
    pub top_left_x_metres: f64,
    pub top_left_y_metres: f64,
}
impl Map {
    fn validate(&self, p: Point) -> Result<()> {
        if !p.x.is_finite()
            || !p.y.is_finite()
            || p.x < 0.
            || p.y < 0.
            || p.x > self.width_pixels as f64
            || p.y > self.height_pixels as f64
        {
            Err("Coordinates are outside the map image".into())
        } else {
            Ok(())
        }
    }
    fn elevation(&self, t: &Terrain, p: Point) -> Option<f64> {
        let w = self.calibration.delta(p.x, p.y);
        t.elevation(w.x + self.top_left_x_metres, w.y + self.top_left_y_metres)
    }
}
#[derive(Clone, Deserialize, Serialize)]
pub struct Observation {
    pub map_id: String,
    pub gun: Point,
    pub bearing: f64,
    pub cannon: String,
    pub projectile: String,
    pub actual_elevation_degrees: f64,
    pub observed_range_yards: f64,
}
struct Shot {
    id: String,
    map: Map,
    gun: Point,
    target: Point,
    physics: Physics,
    profile: Vec<ProfilePoint>,
    range: f64,
    bearing: f64,
    cannon: String,
    projectile: String,
}
#[derive(Deserialize)]
pub struct Mission {
    pub map_id: String,
    pub gun: Point,
    pub target: Point,
    pub cannon: String,
    pub projectile: String,
    #[serde(default)]
    pub calibration_mode: bool,
    #[serde(default)]
    pub airburst_mode: bool,
}
pub struct Engine {
    store: Arc<dyn AssetStore>,
    catalog: Value,
    maps: Vec<Map>,
    terrain: Option<(String, Terrain)>,
    shots: VecDeque<Shot>,
    pub observations: Vec<Observation>,
}
impl Engine {
    pub fn new(store: Arc<dyn AssetStore>) -> Result<Self> {
        let catalog: Value =
            serde_json::from_slice(&store.read("catalog.json")?).map_err(|e| e.to_string())?;
        if catalog["version"] != 1 {
            return Err("Unsupported map catalog".into());
        }
        let maps: Vec<Map> =
            serde_json::from_value(catalog["maps"].clone()).map_err(|e| e.to_string())?;
        if maps.is_empty() {
            return Err("No bundled maps".into());
        }
        for map in &maps {
            if map.width_pixels == 0
                || map.height_pixels == 0
                || map.width_pixels > 16384
                || map.height_pixels > 16384
                || !map.battlefield.chars().all(|c| c.is_ascii_alphanumeric())
            {
                return Err("Invalid map catalog".into());
            }
            let c = &map.calibration;
            if ![
                c.pixel_x_world_x,
                c.pixel_x_world_y,
                c.pixel_y_world_x,
                c.pixel_y_world_y,
                map.top_left_x_metres,
                map.top_left_y_metres,
            ]
            .iter()
            .all(|v| v.is_finite())
                || (c.pixel_x_world_x * c.pixel_y_world_y - c.pixel_y_world_x * c.pixel_x_world_y)
                    .abs()
                    < 1e-12
            {
                return Err("Invalid map calibration".into());
            }
        }
        Ok(Self {
            store,
            catalog,
            maps,
            terrain: None,
            shots: VecDeque::new(),
            observations: vec![],
        })
    }
    fn map(&self, id: &str) -> Result<Map> {
        self.maps
            .iter()
            .find(|m| m.identifier == id)
            .cloned()
            .ok_or("Unknown map".into())
    }
    fn load_terrain(&mut self, battlefield: &str) -> Result<()> {
        if self.terrain.as_ref().is_some_and(|t| t.0 == battlefield) {
            return Ok(());
        }
        // Evict before decoding to keep only one battlefield in memory.
        self.terrain = None;
        let bytes = self.store.read(&format!("terrain/{battlefield}.wrtz"))?;
        self.terrain = Some((battlefield.into(), Terrain::decode(&bytes)?));
        Ok(())
    }
    fn physics(&self, cannon: &str, projectile: &str) -> Result<Physics> {
        let p = &self.catalog["options"]["physics"][cannon][projectile];
        let physics = Physics {
            speed: p["speed"].as_f64().ok_or("Unsupported artillery profile")?,
            drag: p["drag"].as_f64().ok_or("Unsupported artillery profile")?,
            gravity: 9.1,
            launch: serde_json::from_value::<Launch>(self.catalog["launches"][cannon].clone())
                .map_err(|e| e.to_string())?,
        };
        physics.validate()?;
        Ok(physics)
    }
    fn empirical(
        &self,
        map: &Map,
        gun: Point,
        bearing: f64,
        cannon: &str,
        projectile: &str,
        range: f64,
    ) -> Option<crate::empirical::EmpiricalAim> {
        let samples: Vec<_> = self
            .observations
            .iter()
            .filter(|o| {
                let Ok(m) = self.map(&o.map_id) else {
                    return false;
                };
                m.battlefield == map.battlefield
                    && m.mode == map.mode
                    && m.layer == map.layer
                    && o.cannon == cannon
                    && o.projectile == projectile
                    && map.calibration.distance(gun, o.gun) <= 15.
                    && ((o.bearing - bearing + 180.).rem_euclid(360.) - 180.).abs() <= 2.
            })
            .map(|o| Sample {
                elevation_degrees: o.actual_elevation_degrees,
                range_yards: o.observed_range_yards,
            })
            .collect();
        estimate(&samples, range)
    }
    pub fn calculate(&mut self, mission: Mission) -> Result<Value> {
        let map = self.map(&mission.map_id)?;
        map.validate(mission.gun)?;
        map.validate(mission.target)?;
        if mission.gun.x == mission.target.x && mission.gun.y == mission.target.y {
            return Err("Gun and target must be different points".into());
        }
        let physics = self.physics(&mission.cannon, &mission.projectile)?;
        let range = map.calibration.distance(mission.gun, mission.target);
        self.load_terrain(&map.battlefield)?;
        let terrain = &self.terrain.as_ref().unwrap().1;
        let gun_elevation = map.elevation(terrain, mission.gun);
        let target_elevation = map.elevation(terrain, mission.target);
        let difference = gun_elevation.zip(target_elevation).map(|(g, t)| t - g);
        let aim_height = difference.unwrap_or(0.) + if mission.airburst_mode { 1. } else { 0. };
        let aim = physics.solve(range, aim_height, false)?;
        let elevation = aim.map(|a| a.elevation_degrees);
        let profile = if elevation.is_some() {
            terrain.profile(mission.gun, mission.target, range, |p| {
                map.elevation(terrain, p)
            })
        } else {
            vec![]
        };
        let clearance = if profile.is_empty() {
            None
        } else {
            physics.clearance(range, aim_height, &profile, false)?
        };
        let mut operational = clearance
            .as_ref()
            .and_then(|c| c.clearing_elevation_deg)
            .or(elevation);
        let obstructed = clearance.as_ref().is_some_and(|c| c.obstructed);
        if obstructed {
            operational = operational.map(|a| ((a - 1e-10) * 100.).ceil() / 100.);
        }
        let displayed = if mission.calibration_mode {
            elevation
        } else {
            operational
        };
        let state = displayed.and_then(|a| physics.at_distance(range, a));
        let height = if let Some((g, t)) = gun_elevation.zip(target_elevation) {
            state.map(|s| g + s.0 - t)
        } else {
            clearance
                .as_ref()
                .and_then(|c| c.height_above_target_metres)
        };
        let bearing = (mission.target.x - mission.gun.x)
            .atan2(-(mission.target.y - mission.gun.y))
            .to_degrees()
            .rem_euclid(360.);
        let direction = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
            [(bearing / 45.).round_ties_even() as usize % 8];
        let empirical = self.empirical(
            &map,
            mission.gun,
            bearing,
            &mission.cannon,
            &mission.projectile,
            range,
        );
        let id = uuid::Uuid::new_v4().to_string();
        let result = json!({"calculation_id":id,"map_id":mission.map_id,"cannon":mission.cannon,"projectile":mission.projectile,
            "method":self.catalog["options"]["defaults"]["method"],"horizontal_range_yards":range,
            "slant_range_yards":range.hypot(aim_height*METRES_TO_YARDS),"gun_elevation_metres":gun_elevation,
            "target_elevation_metres":target_elevation,"height_difference_metres":difference,"bearing_degrees":bearing,
            "bearing_direction":direction,"elevation_degrees":displayed,"fuze_seconds":state.map(|s|s.1),
            "clearance_status":clearance.as_ref().map(|c|if c.obstructed {"obstructed"} else {"clear"}),
            "height_above_target_metres":height,"elevation_source":if mission.calibration_mode {"calibration_test"} else if obstructed {"terrain_clearance"} else {"physics"},
            "physics_elevation_degrees":elevation,"calibration_sample_count":empirical.map_or(0,|e|e.sample_count),
            "calibration_mode":mission.calibration_mode,"airburst_mode":mission.airburst_mode});
        self.shots.push_back(Shot {
            id,
            map,
            gun: mission.gun,
            target: mission.target,
            physics,
            profile,
            range,
            bearing,
            cannon: mission.cannon,
            projectile: mission.projectile,
        });
        while self.shots.len() > 200 {
            self.shots.pop_front();
        }
        Ok(result)
    }
    pub fn record_impact(&mut self, body: Value) -> Result<Value> {
        let id = body["calculation_id"]
            .as_str()
            .ok_or("Missing calculation id")?;
        let shot = self
            .shots
            .iter()
            .find(|s| s.id == id)
            .ok_or("Shot expired. Recalculate before marking its impact.")?;
        let angle = body["actual_elevation_degrees"]
            .as_f64()
            .filter(|a| a.is_finite() && *a > -89. && *a < 89.)
            .ok_or("Actual elevation must be between -89 and 89 degrees")?;
        let impact: Point =
            serde_json::from_value(body["impact"].clone()).map_err(|e| e.to_string())?;
        shot.map.validate(impact)?;
        let predicted_range = shot.physics.impact_range(&shot.profile, angle);
        let predicted = predicted_range.map(|r| {
            let f = r / shot.range;
            Point {
                x: shot.gun.x + (shot.target.x - shot.gun.x) * f,
                y: shot.gun.y + (shot.target.y - shot.gun.y) * f,
            }
        });
        let observed = shot.map.calibration.distance(shot.gun, impact);
        self.observations.push(Observation {
            map_id: shot.map.identifier.clone(),
            gun: shot.gun,
            bearing: shot.bearing,
            cannon: shot.cannon.clone(),
            projectile: shot.projectile.clone(),
            actual_elevation_degrees: angle,
            observed_range_yards: observed,
        });
        if self.observations.len() > 2000 {
            self.observations.remove(0);
        }
        let empirical = self.empirical(
            &shot.map,
            shot.gun,
            shot.bearing,
            &shot.cannon,
            &shot.projectile,
            shot.range,
        );
        Ok(
            json!({"event":"observed_impact","source":"native","calculation_id":id,"impact_id":uuid::Uuid::new_v4().to_string(),
            "actual_elevation_degrees":angle,"angle_resolution_degrees":0.01,"impact_pixel":impact,"observed_range_yards":observed,
            "distance_from_target_yards":shot.map.calibration.distance(shot.target,impact),"predicted_impact_pixel":predicted,
            "predicted_impact_yards_at_actual_angle":predicted_range,"prediction_error_yards":predicted.map(|p|shot.map.calibration.distance(p,impact)),
            "recommended_elevation_degrees":empirical.map(|e|e.elevation_degrees),"calibration_sample_count":empirical.map_or(0,|e|e.sample_count)}),
        )
    }
    pub fn request(&mut self, operation: &str, data: Value) -> Result<Value> {
        match operation {
            "options" => Ok(self.catalog["options"].clone()),
            "maps" => Ok(Value::Array(
                self.catalog["maps"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .map(|m| {
                        let mut m = m.clone();
                        let o = m.as_object_mut().unwrap();
                        for key in [
                            "calibration",
                            "locations",
                            "layer",
                            "top_left_x_metres",
                            "top_left_y_metres",
                        ] {
                            o.remove(key);
                        }
                        m
                    })
                    .collect(),
            )),
            "calculate" => self.calculate(serde_json::from_value(data).map_err(|e| e.to_string())?),
            "impact" => self.record_impact(data),
            "locations" => {
                let id = data["map_id"].as_str().ok_or("Missing map_id")?;
                self.map(id)?;
                Ok(self.catalog["maps"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .find(|m| m["identifier"] == id)
                    .unwrap()["locations"]
                    .clone())
            }
            _ => Err("Unknown native operation".into()),
        }
    }
}
