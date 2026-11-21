#[cfg(not(any(feature = "calculator", feature = "kill-tracker")))]
compile_error!("Select the calculator, sketcher or kill-tracker application feature.");

use serde_json::Value;
use std::sync::Mutex;
#[cfg(feature = "calculator")]
use std::{path::PathBuf, sync::Arc};
#[cfg(all(feature = "calculator", not(target_os = "android")))]
use tauri::path::BaseDirectory;
use tauri::{AppHandle, Manager};
#[cfg(feature = "calculator")]
use tauri::State;
#[cfg(all(feature = "calculator", not(target_os = "android")))]
use tauri_plugin_fs::FsExt;
#[cfg(feature = "calculator")]
use worcalc_core::{AssetStore, Engine};
type Result<T> = std::result::Result<T, String>;
#[cfg(feature = "kill-tracker")]
mod kill_tracker;
#[cfg(feature = "sketcher")]
mod sketch_store;
#[cfg(feature = "kill-tracker")]
#[derive(Default)]
struct KillTrackerState(Mutex<Option<kill_tracker::Session>>);

#[cfg(feature = "kill-tracker")]
#[tauri::command]
async fn native_kill_tracker(app: AppHandle, operation: String, authorized: bool) -> Result<Value> {
    tauri::async_runtime::spawn_blocking(move || {
        let state = app.state::<KillTrackerState>();
        let mut session = state.0.lock().map_err(|_| "Kill tracker lock failed")?;
        match operation.as_str() {
            "start" => {
                if !authorized {
                    return Err("Authorize read-only capture before starting".into());
                }
                if session.is_some() {
                    return Err("Capture is already running".into());
                }
                let root = app
                    .path()
                    .app_data_dir()
                    .map_err(|e| e.to_string())?
                    .join("kill-captures");
                let mut capture = kill_tracker::Session::start(root)?;
                let snapshot = capture.poll()?;
                *session = Some(capture);
                Ok(snapshot)
            }
            "poll" => {
                let Some(capture) = session.as_mut() else {
                    return Ok(serde_json::json!({"running":false,"deaths":[]}));
                };
                let result = capture.poll();
                if result.is_err() {
                    *session = None;
                }
                result
            }
            "stop" => {
                *session = None;
                Ok(serde_json::json!({"running":false,"deaths":[]}))
            }
            _ => Err("Unknown kill tracker operation".into()),
        }
    })
    .await
    .map_err(|e| e.to_string())?
}
#[cfg(feature = "sketcher")]
#[derive(Default)]
struct SketchState(Mutex<()>);

#[cfg(feature = "sketcher")]
#[tauri::command]
async fn native_sketch(app: AppHandle, operation: String, data: Value) -> Result<Value> {
    tauri::async_runtime::spawn_blocking(move || {
        let state = app.state::<SketchState>();
        let _guard = state.0.lock().map_err(|_| "Plan storage lock failed")?;
        let path = app
            .path()
            .app_data_dir()
            .map_err(|e| e.to_string())?
            .join("sketches.json");
        match operation.as_str() {
            "load" => {
                if app.config().identifier == "pt.tomaspedreira.worsketch" {
                    let legacy = path
                        .parent()
                        .and_then(|directory| directory.parent())
                        .ok_or("Missing application data directory")?
                        .join("pt.tomaspedreira.worcalc")
                        .join("sketches.json");
                    sketch_store::migrate_if_missing(&path, &legacy)?;
                }
                sketch_store::load(&path)
            }
            "save" => {
                sketch_store::save(&path, &data)?;
                Ok(Value::Null)
            }
            "export" => {
                let directory = app.path().download_dir().map_err(|e| e.to_string())?;
                Ok(Value::String(sketch_store::export(&directory, &data)?))
            }
            _ => Err("Unknown plan storage operation".into()),
        }
    })
    .await
    .map_err(|e| e.to_string())?
}

#[cfg(feature = "calculator")]
struct BundledAssets(#[cfg_attr(target_os = "android", allow(dead_code))] AppHandle);
#[cfg(feature = "calculator")]
impl AssetStore for BundledAssets {
    fn read(&self, path: &str) -> Result<Vec<u8>> {
        #[cfg(target_os = "android")]
        return android_asset(&format!("resources/{path}"));
        #[cfg(not(target_os = "android"))]
        {
            let resource = self
                .0
                .path()
                .resolve(format!("resources/{path}"), BaseDirectory::Resource)
                .map_err(|e| e.to_string())?;
            self.0.fs().read(resource).map_err(|e| e.to_string())
        }
    }
}

#[cfg(all(feature = "calculator", target_os = "android"))]
fn android_asset(path: &str) -> Result<Vec<u8>> {
    use std::{ffi::CString, io::Read, ptr::NonNull};
    let context = ndk_context::android_context();
    // Tao owns a global Activity reference and VM for the lifetime of the application.
    let vm = unsafe { jni::JavaVM::from_raw(context.vm().cast()) }.map_err(|e| e.to_string())?;
    let mut env = vm.attach_current_thread().map_err(|e| e.to_string())?;
    let activity = unsafe { jni::objects::JObject::from_raw(context.context().cast()) };
    let java_assets = env
        .call_method(
            &activity,
            "getAssets",
            "()Landroid/content/res/AssetManager;",
            &[],
        )
        .and_then(|v| v.l())
        .map_err(|e| e.to_string())?;
    let java_assets = env.auto_local(java_assets);
    // Keep java_assets alive until the native read completes. AAsset handles both
    // compressed entries and uncompressed entries with their proper offset/length.
    let pointer = unsafe {
        ndk_sys::AAssetManager_fromJava(env.get_native_interface(), java_assets.as_raw())
    };
    let pointer = NonNull::new(pointer).ok_or("Android asset manager is unavailable")?;
    let manager = unsafe { ndk::asset::AssetManager::from_ptr(pointer) };
    let name = CString::new(path).map_err(|e| e.to_string())?;
    let mut asset = manager
        .open(&name)
        .ok_or_else(|| format!("Missing bundled asset: {path}"))?;
    let mut bytes = Vec::new();
    asset.read_to_end(&mut bytes).map_err(|e| e.to_string())?;
    Ok(bytes)
}

#[cfg(feature = "calculator")]
#[tauri::command]
async fn native_resource(app: AppHandle, path: String) -> Result<tauri::ipc::Response> {
    let file = path
        .strip_prefix("maps/map-")
        .and_then(|v| v.strip_suffix(".webp"))
        .and_then(|v| v.strip_suffix("-thumb").or(Some(v)));
    if !file.is_some_and(|v| !v.is_empty() && v.bytes().all(|b| b.is_ascii_digit())) {
        return Err("Invalid map resource".into());
    }
    tauri::async_runtime::spawn_blocking(move || {
        BundledAssets(app)
            .read(&path)
            .map(tauri::ipc::Response::new)
    })
    .await
    .map_err(|e| e.to_string())?
}
#[cfg(feature = "calculator")]
#[derive(Default)]
struct NativeState(Mutex<Option<Engine>>);
#[cfg(feature = "calculator")]
fn observations_path(app: &AppHandle) -> Result<PathBuf> {
    Ok(app
        .path()
        .app_data_dir()
        .map_err(|e| e.to_string())?
        .join("observations.json"))
}

#[cfg(feature = "calculator")]
#[tauri::command]
async fn native_request(
    app: AppHandle,
    state: State<'_, NativeState>,
    operation: String,
    data: Value,
) -> Result<Value> {
    // Heavy trajectory and terrain work must not occupy the WebView/UI thread.
    let app = app.clone();
    let _ = state;
    tauri::async_runtime::spawn_blocking(move || {
        let state = app.state::<NativeState>();
        let mut guard = state
            .0
            .lock()
            .map_err(|_| "Native calculator lock failed")?;
        if guard.is_none() {
            let mut engine = Engine::new(Arc::new(BundledAssets(app.clone())))?;
            let path = observations_path(&app)?;
            if path.exists() {
                let bytes = std::fs::read(path).map_err(|e| e.to_string())?;
                engine.observations = serde_json::from_slice(&bytes)
                    .map_err(|e| format!("Could not load saved calibration: {e}"))?;
            }
            *guard = Some(engine);
        }
        let engine = guard.as_mut().unwrap();
        let result = engine.request(&operation, data)?;
        if operation == "impact" {
            let path = observations_path(&app)?;
            std::fs::create_dir_all(path.parent().unwrap()).map_err(|e| e.to_string())?;
            let temporary = path.with_extension("tmp");
            std::fs::write(
                &temporary,
                serde_json::to_vec(&engine.observations).map_err(|e| e.to_string())?,
            )
            .map_err(|e| e.to_string())?;
            // Android rename replaces atomically; Windows requires removing the destination.
            #[cfg(windows)]
            if path.exists() {
                std::fs::remove_file(&path).map_err(|e| e.to_string())?;
            }
            std::fs::rename(temporary, path).map_err(|e| e.to_string())?;
        }
        Ok(result)
    })
    .await
    .map_err(|e| e.to_string())?
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let builder = tauri::Builder::default().plugin(tauri_plugin_fs::init());
    #[cfg(feature = "calculator")]
    let builder = builder.manage(NativeState::default());
    #[cfg(feature = "sketcher")]
    let builder = builder.manage(SketchState::default());
    #[cfg(feature = "kill-tracker")]
    let builder = builder.manage(KillTrackerState::default());
    builder
        .invoke_handler(tauri::generate_handler![
            #[cfg(feature = "calculator")]
            native_request,
            #[cfg(feature = "calculator")]
            native_resource,
            #[cfg(feature = "sketcher")]
            native_sketch,
            #[cfg(feature = "kill-tracker")]
            native_kill_tracker
        ])
        .run(tauri::generate_context!())
        .expect("Could not start worCalc");
}
