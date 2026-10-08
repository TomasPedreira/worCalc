//! Stable results captured from the retired implementation before migration.
use serde_json::{json, Value};
use std::{path::PathBuf, sync::Arc};
use worcalc_core::{
    empirical,
    physics::{Physics, ProfilePoint},
    AssetStore, Engine, Result,
};

struct Files(PathBuf);
impl AssetStore for Files {
    fn read(&self, path: &str) -> Result<Vec<u8>> {
        std::fs::read(self.0.join(path)).map_err(|e| e.to_string())
    }
}
fn engine() -> Engine {
    Engine::new(Arc::new(Files(
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../assets"),
    )))
    .unwrap()
}
fn compare(expected: &Value, actual: &Value, context: &str) {
    match expected {
        Value::Object(e) => {
            let a = actual
                .as_object()
                .unwrap_or_else(|| panic!("{context}: expected object, got {actual}"));
            assert_eq!(e.len(), a.len(), "{context}: object keys");
            for (key, value) in e {
                compare(
                    value,
                    a.get(key)
                        .unwrap_or_else(|| panic!("{context}: missing {key}")),
                    &format!("{context}/{key}"),
                );
            }
        }
        Value::Array(e) => {
            let a = actual.as_array().unwrap();
            assert_eq!(e.len(), a.len(), "{context}: array length");
            for (i, (x, y)) in e.iter().zip(a).enumerate() {
                compare(x, y, &format!("{context}/{i}"));
            }
        }
        Value::Number(e) => {
            let a = actual
                .as_f64()
                .unwrap_or_else(|| panic!("{context}: expected number, got {actual}"));
            assert!(
                (e.as_f64().unwrap() - a).abs() <= 1e-6,
                "{context}: expected {e}, got {a}"
            );
        }
        _ => assert_eq!(expected, actual, "{context}"),
    }
}
#[test]
fn physics_and_clearance_match_127_reference_cases() {
    let cases: Vec<Value> = serde_json::from_str(include_str!("fixtures/physics.json")).unwrap();
    for (i, case) in cases.iter().enumerate() {
        let p: Physics = serde_json::from_value(case["physics"].clone()).unwrap();
        let yards = case["yards"].as_f64().unwrap();
        let height = case["height"].as_f64().unwrap();
        let limited = case["limited"].as_bool().unwrap();
        let clearance = if let Some(profile) = case.get("profile") {
            let profile: Vec<ProfilePoint> = serde_json::from_value(profile.clone()).unwrap();
            p.clearance(yards, height, &profile, limited).unwrap()
        } else {
            None
        };
        let actual = json!({"aim":p.solve(yards,height,limited).unwrap(), "clearance":clearance,
            "state":case["angle"].as_f64().and_then(|a| p.at_distance(yards,a))});
        compare(&case["expected"], &actual, &format!("physics/{i}"));
    }
}
#[test]
fn empirical_calibration_matches_reference_branches() {
    let cases: Vec<Value> = serde_json::from_str(include_str!("fixtures/empirical.json")).unwrap();
    for (i, case) in cases.iter().enumerate() {
        let samples =
            serde_json::from_value::<Vec<empirical::Sample>>(case["samples"].clone()).unwrap();
        compare(
            &case["expected"],
            &json!(empirical::estimate(
                &samples,
                case["target"].as_f64().unwrap()
            )),
            &format!("empirical/{i}"),
        );
    }
}
#[test]
fn all_maps_weapons_modes_and_observed_impacts_match_reference() {
    let cases: Vec<Value> = serde_json::from_str(include_str!("fixtures/missions.json")).unwrap();
    let mut engine = engine();
    for (i, case) in cases.iter().enumerate() {
        engine.observations.clear();
        let mut actual = engine
            .request("calculate", case["mission"].clone())
            .unwrap();
        let id = actual
            .as_object_mut()
            .unwrap()
            .remove("calculation_id")
            .unwrap();
        compare(
            &case["expected"],
            &actual,
            &format!("mission/{i}/{}", case["mission"]["map_id"]),
        );
        if let Some(impact) = case.get("impact") {
            let mut actual = engine.request("impact", json!({"calculation_id":id,"impact":impact["point"],"actual_elevation_degrees":impact["angle"]})).unwrap();
            for key in ["calculation_id", "impact_id", "source"] {
                actual.as_object_mut().unwrap().remove(key);
            }
            compare(&impact["expected"], &actual, "impact");
        }
    }
    let locations: Vec<Value> =
        serde_json::from_str(include_str!("fixtures/locations.json")).unwrap();
    for case in locations {
        compare(
            &case["expected"],
            &engine
                .request("locations", json!({"map_id":case["map_id"]}))
                .unwrap(),
            "locations",
        );
    }
}
#[test]
fn native_commands_validate_input_and_expose_only_display_metadata() {
    let mut engine = engine();
    let maps = engine.request("maps", Value::Null).unwrap();
    assert_eq!(maps.as_array().unwrap().len(), 99);
    for map in maps.as_array().unwrap() {
        assert!(map.get("calibration").is_none());
        assert!(map.get("locations").is_none());
        assert!(map["image_path"].as_str().unwrap().starts_with("maps/"));
    }
    assert!(engine.request("options", Value::Null).unwrap()["weapons"].is_object());
    assert!(engine
        .request("unknown", Value::Null)
        .unwrap_err()
        .contains("Unknown native operation"));
    assert!(engine
        .request("locations", Value::Null)
        .unwrap_err()
        .contains("Missing map_id"));
    assert!(engine
        .request("locations", json!({"map_id":"missing"}))
        .is_err());
    let mut mission = serde_json::from_str::<Vec<Value>>(include_str!("fixtures/missions.json"))
        .unwrap()[0]["mission"]
        .clone();
    mission["gun"]["x"] = json!(-1);
    assert!(engine
        .request("calculate", mission.clone())
        .unwrap_err()
        .contains("outside the map"));
    mission["gun"]["x"] = json!(700);
    mission["cannon"] = json!("Unknown cannon");
    assert!(engine.request("calculate", mission).is_err());
    assert!(engine
        .request(
            "impact",
            json!({"calculation_id":"expired","impact":{"x":1,"y":1},"actual_elevation_degrees":1})
        )
        .is_err());
}
