//! JSON-lines harness for native diagnostics.
use serde_json::{json, Value};
use std::{
    io::{self, BufRead},
    path::PathBuf,
    sync::Arc,
};
use worcalc_core::{
    physics::{Physics, ProfilePoint},
    AssetStore, Engine, Result,
};
struct Files(PathBuf);
impl AssetStore for Files {
    fn read(&self, path: &str) -> Result<Vec<u8>> {
        std::fs::read(self.0.join(path)).map_err(|e| e.to_string())
    }
}
fn main() {
    let path = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "native/assets".into());
    let mut engine: Option<Engine> = None;
    for line in io::stdin().lock().lines() {
        let result = (|| -> Result<Value> {
            let req: Value = serde_json::from_str(&line.map_err(|e| e.to_string())?)
                .map_err(|e| e.to_string())?;
            if req["operation"] == "physics" {
                let p: Physics =
                    serde_json::from_value(req["physics"].clone()).map_err(|e| e.to_string())?;
                let yards = req["yards"].as_f64().ok_or("Missing yards")?;
                let height = req["height"].as_f64().unwrap_or(0.);
                let limited = req["limited"].as_bool().unwrap_or(true);
                let aim = p.solve(yards, height, limited)?;
                let clearance = if let Some(profile) = req.get("profile") {
                    let points: Vec<ProfilePoint> =
                        serde_json::from_value(profile.clone()).map_err(|e| e.to_string())?;
                    p.clearance(yards, height, &points, limited)?
                } else {
                    None
                };
                return Ok(
                    json!({"aim":aim,"clearance":clearance,"state":req["angle"].as_f64().and_then(|a|p.at_distance(yards,a))}),
                );
            }
            if req["operation"] == "empirical" {
                let samples: Vec<worcalc_core::empirical::Sample> =
                    serde_json::from_value(req["samples"].clone()).map_err(|e| e.to_string())?;
                return Ok(json!(worcalc_core::empirical::estimate(
                    &samples,
                    req["target"].as_f64().ok_or("Missing target")?
                )));
            }
            if engine.is_none() {
                engine = Some(Engine::new(Arc::new(Files(PathBuf::from(&path))))?);
            }
            engine.as_mut().unwrap().request(
                req["operation"].as_str().ok_or("Missing operation")?,
                req["data"].clone(),
            )
        })();
        println!(
            "{}",
            match result {
                Ok(value) => json!({"ok":true,"value":value}),
                Err(error) => json!({"ok":false,"error":error}),
            }
        );
    }
}
