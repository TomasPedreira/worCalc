use serde_json::{json, Value};
use std::{path::PathBuf, sync::Arc};
use worcalc_core::{
    alignment::{align_catalog, ImageTransform, PixelTransform},
    engine::{Map, Observation},
    physics::Point,
    AssetStore, Engine, Result,
};

fn directory() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../assets")
}
fn original() -> Value {
    serde_json::from_slice(&std::fs::read(directory().join("catalog.json")).unwrap()).unwrap()
}
fn corrected() -> Value {
    let mut c = original();
    align_catalog(&mut c).unwrap();
    c
}
fn map(value: &Value) -> Map {
    serde_json::from_value(value.clone()).unwrap()
}
fn world(m: &Map, p: Point) -> Point {
    let c = &m.calibration;
    Point {
        x: m.top_left_x_metres + c.pixel_x_world_x * p.x + c.pixel_y_world_x * p.y,
        y: m.top_left_y_metres + c.pixel_x_world_y * p.x + c.pixel_y_world_y * p.y,
    }
}
fn pixel(m: &Map, p: Point) -> Point {
    let c = &m.calibration;
    let det = c.pixel_x_world_x * c.pixel_y_world_y - c.pixel_y_world_x * c.pixel_x_world_y;
    let x = p.x - m.top_left_x_metres;
    let y = p.y - m.top_left_y_metres;
    Point {
        x: (c.pixel_y_world_y * x - c.pixel_y_world_x * y) / det,
        y: (c.pixel_x_world_x * y - c.pixel_x_world_y * x) / det,
    }
}
fn close(a: f64, b: f64) {
    assert!((a - b).abs() < 1e-6, "{a} != {b}");
}
fn point(value: &Value) -> Point {
    serde_json::from_value(value.clone()).unwrap()
}
struct Files {
    catalog: Value,
}
impl AssetStore for Files {
    fn read(&self, path: &str) -> Result<Vec<u8>> {
        if path == "catalog.json" {
            return serde_json::to_vec(&self.catalog).map_err(|e| e.to_string());
        }
        std::fs::read(directory().join(path)).map_err(|e| e.to_string())
    }
}
fn engine(mut catalog: Value, legacy: bool) -> Engine {
    if legacy {
        catalog.as_object_mut().unwrap().remove("map_alignments");
    }
    Engine::new(Arc::new(Files { catalog })).unwrap()
}

#[test]
fn every_map_is_covered_neutral_maps_are_exactly_unchanged_and_locations_keep_world_positions() {
    let before = original();
    let after = corrected();
    let mut changed = 0;
    let mut guns = 0;
    for (a, b) in before["maps"]
        .as_array()
        .unwrap()
        .iter()
        .zip(after["maps"].as_array().unwrap())
    {
        let old = map(a);
        let new = map(b);
        let spec = &before["map_alignments"]["maps"][&old.identifier];
        assert!(spec.is_object());
        if new.coordinate_revision == 0 {
            assert_eq!(a, b);
        } else {
            changed += 1;
            if spec.get("image_transform").is_none() {
                close(
                    new.calibration
                        .pixel_x_world_y
                        .atan2(new.calibration.pixel_x_world_x)
                        .to_degrees(),
                    spec["heading_degrees"].as_f64().unwrap(),
                );
                let centre = Point {
                    x: old.width_pixels as f64 / 2.,
                    y: old.height_pixels as f64 / 2.,
                };
                let p = world(&old, centre);
                let q = world(&new, centre);
                close(p.x, q.x);
                close(p.y, q.y);
            }
        }
        for (p, q) in a["locations"]
            .as_array()
            .unwrap()
            .iter()
            .zip(b["locations"].as_array().unwrap())
        {
            assert_eq!(p["world_x"], q["world_x"]);
            assert_eq!(p["world_y"], q["world_y"]);
            assert_eq!(p["elevation_metres"], q["elevation_metres"]);
            let w = world(
                &new,
                Point {
                    x: q["pixel_x"].as_f64().unwrap(),
                    y: q["pixel_y"].as_f64().unwrap(),
                },
            );
            close(w.x, q["world_x"].as_f64().unwrap());
            close(w.y, q["world_y"].as_f64().unwrap());
            if p["kind"] == "gun_spawn" {
                guns += 1;
            }
        }
    }
    assert_eq!(changed, 60);
    assert_eq!(guns, 850);
    assert_eq!(before["maps"][40], after["maps"][40]); // independently verified CSA Drill Camp
    assert_eq!(before["launches"], after["launches"]);
    assert_eq!(before["options"], after["options"]);
}

#[test]
fn affine_reframing_preserves_world_points_even_for_skewed_non_square_maps() {
    let mut m = map(&original()["maps"][67]);
    m.width_pixels = 1300;
    m.height_pixels = 700;
    let before = m.clone();
    let transform = ImageTransform::rotation_to_heading(&m, 0.).unwrap();
    transform.reframe(&mut m).unwrap();
    for p in [
        Point { x: 0., y: 0. },
        Point { x: 1300., y: 700. },
        Point { x: 650., y: 350. },
        Point { x: 39.2, y: 602.3 },
    ] {
        let a = world(&before, p);
        let b = world(&m, transform.apply(p));
        close(a.x, b.x);
        close(a.y, b.y);
    }
    assert!(ImageTransform {
        a: 0.,
        z: 0.,
        tx: 0.,
        ty: 0.
    }
    .reframe(&mut m)
    .is_err());
    assert!(ImageTransform::rotation_to_heading(&m, f64::NAN).is_err());
    m.calibration.pixel_x_world_x = 0.;
    m.calibration.pixel_x_world_y = 0.;
    assert!(ImageTransform::rotation_to_heading(&m, 0.).is_err());
}

#[test]
fn neutral_corner_skew_is_removed_without_rotating_the_entire_map() {
    let mut m = map(&original()["maps"][67]);
    let before = m.clone();
    let correction = PixelTransform::neutral_axes(&m).unwrap();
    correction.reframe(&mut m).unwrap();
    close(
        m.calibration.pixel_x_world_x,
        before.calibration.pixel_x_world_x,
    );
    close(
        m.calibration.pixel_y_world_y,
        before.calibration.pixel_y_world_y,
    );
    close(m.calibration.pixel_x_world_y, 0.);
    close(m.calibration.pixel_y_world_x, 0.);
    for p in [
        Point { x: 0., y: 0. },
        Point { x: 2048., y: 2048. },
        Point {
            x: 1591.62,
            y: 867.9,
        },
    ] {
        let a = world(&before, p);
        let b = world(&m, correction.apply(p));
        close(a.x, b.x);
        close(a.y, b.y);
    }
    // Two independently identified roofs on Outskirts. A rigid 5.38-degree
    // image rotation moves their X coordinates unnecessarily.
    let roofs = [
        (
            Point {
                x: 1591.6214467850266,
                y: 867.8993468798375,
            },
            Point {
                x: 1589.408961593172,
                y: 815.6394025604552,
            },
        ),
        (
            Point {
                x: 776.9565897690267,
                y: 1729.866732751286,
            },
            Point {
                x: 778.2139784946237,
                y: 1749.5666666666666,
            },
        ),
    ];
    for (p, q) in roofs {
        let corrected = correction.apply(p);
        let rotated = ImageTransform::rotation_to_heading(&before, 0.)
            .unwrap()
            .apply(p);
        assert!((corrected.x - q.x).hypot(corrected.y - q.y) < 4.5);
        assert!((rotated.x - q.x).hypot(rotated.y - q.y) > 10.);
    }
}

#[test]
fn alignment_pack_rejects_missing_unknown_and_unsupported_entries() {
    assert!(align_catalog(&mut corrected())
        .unwrap_err()
        .contains("already been resolved"));
    for edit in 0..4 {
        let mut c = original();
        match edit {
            0 => c["map_alignments"]["revision"] = json!(2),
            1 => {
                c["map_alignments"]["maps"]
                    .as_object_mut()
                    .unwrap()
                    .remove("map-1");
            }
            2 => {
                let entry = c["map_alignments"]["maps"]
                    .as_object_mut()
                    .unwrap()
                    .remove("map-1")
                    .unwrap();
                c["map_alignments"]["maps"]["unknown"] = entry;
            }
            _ => c["map_alignments"]["maps"]["map-17"]["image_transform"]["a"] = json!(20),
        }
        assert!(align_catalog(&mut c).is_err());
    }
}

#[test]
fn registered_buildings_match_the_measured_artwork_without_using_gun_positions() {
    let catalog = corrected();
    let references: Value = serde_json::from_str(include_str!("fixtures/alignment.json")).unwrap();
    assert_eq!(references["landmarks"].as_array().unwrap().len(), 17);
    for landmark in references["landmarks"].as_array().unwrap() {
        let m = map(catalog["maps"]
            .as_array()
            .unwrap()
            .iter()
            .find(|m| m["identifier"] == landmark["map_id"])
            .unwrap());
        let p = pixel(&m, point(&landmark["world"]));
        let q = point(&landmark["picture"]);
        let error = (p.x - q.x).hypot(p.y - q.y);
        assert!(
            error < landmark["max_error_pixels"].as_f64().unwrap(),
            "{} {}: {error}",
            landmark["map_id"],
            landmark["name"]
        );
    }
}

#[test]
fn miller_guns_match_the_held_out_wortool_reference_after_correction() {
    let mut current = engine(original(), false);
    let references: Value = serde_json::from_str(include_str!("fixtures/alignment.json")).unwrap();
    let reference = &references["held_out_guns"];
    let locations = current
        .request("locations", json!({"map_id":reference["map_id"]}))
        .unwrap();
    let x = &reference["reference_transform"]["x"];
    let y = &reference["reference_transform"]["y"];
    let projected = |location: &Value| Point {
        x: x[0].as_f64().unwrap() * location["pixel_x"].as_f64().unwrap()
            + x[1].as_f64().unwrap() * location["pixel_y"].as_f64().unwrap()
            + x[2].as_f64().unwrap(),
        y: y[0].as_f64().unwrap() * location["pixel_x"].as_f64().unwrap()
            + y[1].as_f64().unwrap() * location["pixel_y"].as_f64().unwrap()
            + y[2].as_f64().unwrap(),
    };
    for gun in reference["measurements"].as_array().unwrap() {
        let location = locations
            .as_array()
            .unwrap()
            .iter()
            .find(|p| p["name"] == gun["name"])
            .unwrap();
        let p = projected(location);
        let q = point(&gun["picture"]);
        assert!(
            (p.x - q.x).hypot(p.y - q.y) < gun["max_error_pixels"].as_f64().unwrap(),
            "{}",
            gun["name"]
        );
    }
    let group = &reference["other_group"];
    let names = group["names"].as_array().unwrap();
    assert_eq!(names.len(), 4);
    let positions: Vec<_> = locations
        .as_array()
        .unwrap()
        .iter()
        .filter(|p| names.contains(&p["name"]))
        .map(projected)
        .collect();
    assert_eq!(positions.len(), 4);
    let p = Point {
        x: positions.iter().map(|p| p.x).sum::<f64>() / 4.,
        y: positions.iter().map(|p| p.y).sum::<f64>() / 4.,
    };
    let q = point(&group["picture"]);
    assert!((p.x - q.x).hypot(p.y - q.y) < group["max_error_pixels"].as_f64().unwrap());
}

#[test]
fn engine_samples_true_ground_at_corrected_guns_and_preserves_drill_camp_heights() {
    let catalog = original();
    let aligned = corrected();
    let mut current = engine(catalog.clone(), false);
    let mut legacy = engine(catalog, true);
    let references: Value = serde_json::from_str(include_str!("fixtures/alignment.json")).unwrap();
    let mut max_old_error: f64 = 0.;
    for sample in references["ground"].as_array().unwrap() {
        let m = map(aligned["maps"]
            .as_array()
            .unwrap()
            .iter()
            .find(|m| m["identifier"] == sample["map_id"])
            .unwrap());
        let p = pixel(&m, point(&sample["world"]));
        let mission = json!({"map_id":m.identifier,"gun":p,"target":{"x":1024,"y":1100},"cannon":"3-inch Ordnance","projectile":"Shell"});
        let result = current.request("calculate", mission.clone()).unwrap();
        close(
            result["gun_elevation_metres"].as_f64().unwrap(),
            sample["height_metres"].as_f64().unwrap(),
        );
        let previous = legacy.request("calculate", mission).unwrap();
        let error = (previous["gun_elevation_metres"].as_f64().unwrap()
            - sample["height_metres"].as_f64().unwrap())
        .abs();
        if m.identifier == "map-41" {
            close(error, 0.);
        } else {
            max_old_error = max_old_error.max(error);
        }
    }
    assert!(max_old_error > 1.5); // catches correcting markers without terrain lookup
}

#[test]
fn corrected_missions_retain_physics_and_terrain_results_for_the_same_world_points() {
    let catalog = original();
    let aligned = corrected();
    let mut current = engine(catalog.clone(), false);
    let cases: Vec<Value> = serde_json::from_str(include_str!("fixtures/missions.json")).unwrap();
    for case in cases {
        let mut mission = case["mission"].clone();
        let id = mission["map_id"].as_str().unwrap();
        let index = catalog["maps"]
            .as_array()
            .unwrap()
            .iter()
            .position(|m| m["identifier"] == id)
            .unwrap();
        let old = map(&catalog["maps"][index]);
        let new = map(&aligned["maps"][index]);
        for key in ["gun", "target"] {
            mission[key] = json!(pixel(&new, world(&old, point(&mission[key]))));
        }
        current.observations.clear();
        let result = current.request("calculate", mission).unwrap();
        for (key, expected) in case["expected"].as_object().unwrap() {
            if ["bearing_degrees", "bearing_direction"].contains(&key.as_str()) {
                continue;
            }
            if let Some(n) = expected.as_f64() {
                close(n, result[key].as_f64().unwrap());
            } else {
                assert_eq!(expected, &result[key], "{} {key}", old.identifier);
            }
        }
    }
}

#[test]
fn map_alignment_keeps_image_cardinals_and_recomputes_bearings_for_moved_world_points() {
    let catalog = original();
    let mut current = engine(catalog.clone(), false);
    let mut legacy = engine(catalog.clone(), true);
    for (x, y, degrees, direction) in [
        (1024., 900., 0., "N"),
        (1150., 1024., 90., "E"),
        (1024., 1150., 180., "S"),
        (900., 1024., 270., "W"),
    ] {
        let mission = json!({"map_id":"map-17","gun":{"x":1024,"y":1024},"target":{"x":x,"y":y},"cannon":"3-inch Ordnance","projectile":"Shell"});
        let a = legacy.request("calculate", mission.clone()).unwrap();
        let b = current.request("calculate", mission).unwrap();
        close(b["bearing_degrees"].as_f64().unwrap(), degrees);
        assert_eq!(b["bearing_degrees"], a["bearing_degrees"]);
        assert_eq!(b["bearing_direction"], direction);
    }
    let old = map(&catalog["maps"][16]);
    let aligned = corrected();
    let new = map(&aligned["maps"][16]);
    let gun = Point { x: 1000., y: 1000. };
    let target = Point { x: 1100., y: 900. };
    let mission = json!({"map_id":"map-17","gun":pixel(&new,world(&old,gun)),"target":pixel(&new,world(&old,target)),"cannon":"3-inch Ordnance","projectile":"Shell"});
    let result = current.request("calculate", mission).unwrap();
    close(
        result["bearing_degrees"].as_f64().unwrap(),
        45. + 3.6640287500086095,
    );
}

#[test]
fn old_observations_are_retained_but_only_current_alignment_is_used() {
    let catalog = original();
    let mut current = engine(catalog, false);
    for id in ["map-17", "map-41"] {
        let mission = json!({"map_id":id,"gun":{"x":1024,"y":1024},"target":{"x":1200,"y":1100},"cannon":"3-inch Ordnance","projectile":"Shell"});
        current.observations.clear();
        let result = current.request("calculate", mission.clone()).unwrap();
        let range = result["horizontal_range_yards"].as_f64().unwrap();
        for (i, scale) in [0.9, 1., 1.1].iter().enumerate() {
            current.observations.push(serde_json::from_value::<Observation>(json!({"map_id":id,"gun":mission["gun"],"bearing":result["bearing_degrees"],"cannon":mission["cannon"],"projectile":"Shell","actual_elevation_degrees":1. + i as f64 * 0.1,"observed_range_yards":range*scale})).unwrap());
        }
        let sampled = current.request("calculate", mission.clone()).unwrap();
        assert_eq!(
            sampled["calibration_sample_count"],
            if id == "map-41" { 3 } else { 0 }
        );
        assert_eq!(current.observations.len(), 3);
        let revision = sampled["coordinate_revision"].as_u64().unwrap() as u32;
        for o in &mut current.observations {
            o.coordinate_revision = revision;
        }
        assert_eq!(
            current.request("calculate", mission.clone()).unwrap()["calibration_sample_count"],
            3
        );
        current.request("impact",json!({"calculation_id":sampled["calculation_id"],"impact":mission["target"],"actual_elevation_degrees":1.})).unwrap();
        assert_eq!(
            current.observations.last().unwrap().coordinate_revision,
            revision
        );
    }
}
