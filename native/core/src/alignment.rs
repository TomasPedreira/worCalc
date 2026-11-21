//! Map artwork alignment. The image stays fixed; every world-backed feature and
//! terrain query uses the same rebased projection. No terrain heights are edited.
use crate::{engine::Map, physics::Point, Result};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

#[derive(Clone, Copy, Debug, Deserialize, Serialize)]
pub struct ImageTransform {
    pub a: f64,
    pub z: f64,
    pub tx: f64,
    pub ty: f64,
}
#[derive(Clone, Copy, Debug)]
pub struct PixelTransform {
    xx: f64,
    xy: f64,
    yx: f64,
    yy: f64,
    tx: f64,
    ty: f64,
}
impl From<ImageTransform> for PixelTransform {
    fn from(t: ImageTransform) -> Self {
        Self {
            xx: t.a,
            xy: -t.z,
            yx: t.z,
            yy: t.a,
            tx: t.tx,
            ty: t.ty,
        }
    }
}
impl PixelTransform {
    pub fn apply(self, p: Point) -> Point {
        Point {
            x: self.xx * p.x + self.xy * p.y + self.tx,
            y: self.yx * p.x + self.yy * p.y + self.ty,
        }
    }
    /// Some nominally unrotated crops contain staggered corners, not a rigid
    /// rotation. Remove their cross-axis terms while preserving projected X/Y
    /// scale and the world position of the image centre.
    pub fn neutral_axes(map: &Map) -> Result<Self> {
        let c = &map.calibration;
        if c.pixel_x_world_x <= 0. || c.pixel_y_world_y >= 0. {
            return Err("Invalid neutral map axes".into());
        }
        let xy = c.pixel_y_world_x / c.pixel_x_world_x;
        let yx = c.pixel_x_world_y / c.pixel_y_world_y;
        let t = Self {
            xx: 1.,
            xy,
            yx,
            yy: 1.,
            tx: -xy * map.height_pixels as f64 / 2.,
            ty: -yx * map.width_pixels as f64 / 2.,
        };
        t.validate()?;
        Ok(t)
    }
    fn validate(self) -> Result<()> {
        if ![self.xx, self.xy, self.yx, self.yy, self.tx, self.ty]
            .iter()
            .all(|v| v.is_finite())
            || (self.xx * self.yy - self.xy * self.yx).abs() < 1e-12
        {
            return Err("Invalid map alignment transform".into());
        }
        Ok(())
    }
    pub fn reframe(self, map: &mut Map) -> Result<()> {
        self.validate()?;
        // A' = A B^-1, O' = O - A' t. Thus A'(B p+t)+O'=A p+O.
        let c = &mut map.calibration;
        let (a, b, cx, d) = (
            c.pixel_x_world_x,
            c.pixel_y_world_x,
            c.pixel_x_world_y,
            c.pixel_y_world_y,
        );
        let det = self.xx * self.yy - self.xy * self.yx;
        c.pixel_x_world_x = (a * self.yy - b * self.yx) / det;
        c.pixel_x_world_y = (cx * self.yy - d * self.yx) / det;
        c.pixel_y_world_x = (b * self.xx - a * self.xy) / det;
        c.pixel_y_world_y = (d * self.xx - cx * self.xy) / det;
        map.top_left_x_metres -= c.pixel_x_world_x * self.tx + c.pixel_y_world_x * self.ty;
        map.top_left_y_metres -= c.pixel_x_world_y * self.tx + c.pixel_y_world_y * self.ty;
        Ok(())
    }
    fn is_identity(self) -> bool {
        (self.xx - 1.).abs() < 1e-12
            && (self.yy - 1.).abs() < 1e-12
            && self.xy.abs() < 1e-12
            && self.yx.abs() < 1e-12
            && self.tx.abs() < 1e-9
            && self.ty.abs() < 1e-9
    }
}
impl ImageTransform {
    pub fn apply(self, p: Point) -> Point {
        Point {
            x: self.a * p.x - self.z * p.y + self.tx,
            y: self.z * p.x + self.a * p.y + self.ty,
        }
    }
    fn validate(self) -> Result<()> {
        if ![self.a, self.z, self.tx, self.ty]
            .iter()
            .all(|v| v.is_finite())
            || !(0.9..=1.1).contains(&self.a.hypot(self.z))
        {
            return Err("Invalid map alignment transform".into());
        }
        Ok(())
    }
    pub fn rotation_to_heading(map: &Map, heading_degrees: f64) -> Result<Self> {
        if !heading_degrees.is_finite() {
            return Err("Invalid map heading".into());
        }
        let c = &map.calibration;
        let det = c.pixel_x_world_x * c.pixel_y_world_y - c.pixel_y_world_x * c.pixel_x_world_y;
        if !det.is_finite() || det.abs() < 1e-12 {
            return Err("Invalid map calibration".into());
        }
        let (s, coss) = heading_degrees.to_radians().sin_cos();
        let dx = (c.pixel_y_world_y * coss - c.pixel_y_world_x * s) / det;
        let dy = (c.pixel_x_world_x * s - c.pixel_x_world_y * coss) / det;
        let angle = -dy.atan2(dx);
        let (z, a) = angle.sin_cos();
        let x = map.width_pixels as f64 / 2.;
        let y = map.height_pixels as f64 / 2.;
        Ok(Self {
            a,
            z,
            tx: x - a * x + z * y,
            ty: y - z * x - a * y,
        })
    }
    pub fn reframe(self, map: &mut Map) -> Result<()> {
        self.validate()?;
        PixelTransform::from(self).reframe(map)
    }
}

/// Resolve the versioned, declarative corrections once at engine creation.
/// The canonical catalog retains the original export for audit and regression.
pub fn align_catalog(catalog: &mut Value) -> Result<()> {
    let Some(pack) = catalog.get("map_alignments").cloned() else {
        return Ok(());
    };
    if pack["revision"] != 1 {
        return Err("Unsupported map alignment revision".into());
    }
    let entries = pack["maps"].as_object().ok_or("Missing map alignments")?;
    let maps = catalog["maps"].as_array_mut().ok_or("Missing maps")?;
    if entries.len() != maps.len() {
        return Err("Map alignment coverage does not match catalog".into());
    }
    for value in maps {
        let mut map: Map = serde_json::from_value(value.clone()).map_err(|e| e.to_string())?;
        if map.coordinate_revision != 0 {
            return Err("Map alignment has already been resolved".into());
        }
        let spec = entries
            .get(&map.identifier)
            .ok_or("Missing map alignment")?;
        let transform: PixelTransform = if let Some(fit) = spec.get("image_transform") {
            let t =
                serde_json::from_value::<ImageTransform>(fit.clone()).map_err(|e| e.to_string())?;
            t.validate()?;
            t.into()
        } else if spec["method"] == "neutral_axis_rectification" {
            if spec["heading_degrees"] != 0 {
                return Err("Invalid neutral map heading".into());
            }
            PixelTransform::neutral_axes(&map)?
        } else {
            ImageTransform::rotation_to_heading(
                &map,
                spec["heading_degrees"]
                    .as_f64()
                    .ok_or("Missing map heading")?,
            )?
            .into()
        };
        transform.validate()?;
        if transform.is_identity() {
            continue;
        }
        transform.reframe(&mut map)?;
        value["calibration"] = serde_json::to_value(&map.calibration).map_err(|e| e.to_string())?;
        value["top_left_x_metres"] = json!(map.top_left_x_metres);
        value["top_left_y_metres"] = json!(map.top_left_y_metres);
        value["coordinate_revision"] = json!(1);
        let mut gun_updates = vec![];
        for location in value["locations"]
            .as_array_mut()
            .ok_or("Missing map locations")?
        {
            let old = Point {
                x: location["pixel_x"].as_f64().ok_or("Invalid location")?,
                y: location["pixel_y"].as_f64().ok_or("Invalid location")?,
            };
            let p = transform.apply(old);
            if location["kind"] == "gun_spawn" {
                gun_updates.push(json!({"old_x":old.x,"old_y":old.y,"x":p.x,"y":p.y}));
            }
            location["pixel_x"] = json!(p.x);
            location["pixel_y"] = json!(p.y);
        }
        // Only exact old default positions are migrated. User-placed points stay
        // on their pictured landmarks; their cached firing solutions are retired.
        value["coordinate_migration"] = json!({"from_revision":0,"gun_positions":gun_updates});
    }
    Ok(())
}
