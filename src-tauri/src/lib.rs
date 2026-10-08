use serde_json::Value;
use std::{
    path::PathBuf,
    sync::{Arc, Mutex},
};
#[cfg(not(target_os = "android"))]
use tauri::path::BaseDirectory;
use tauri::{AppHandle, Manager, State};
#[cfg(not(target_os = "android"))]
use tauri_plugin_fs::FsExt;
use worcalc_core::{AssetStore, Engine, Result};
mod sketch_store;
#[derive(Default)]
struct SketchState(Mutex<()>);

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
            "load" => sketch_store::load(&path),
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

struct BundledAssets(#[cfg_attr(target_os = "android", allow(dead_code))] AppHandle);
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

#[cfg(target_os = "android")]
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
#[derive(Default)]
struct NativeState(Mutex<Option<Engine>>);
fn observations_path(app: &AppHandle) -> Result<PathBuf> {
    Ok(app
        .path()
        .app_data_dir()
        .map_err(|e| e.to_string())?
        .join("observations.json"))
}

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
    tauri::Builder::default()
        .plugin(tauri_plugin_fs::init())
        .manage(NativeState::default())
        .manage(SketchState::default())
        .invoke_handler(tauri::generate_handler![
            native_request,
            native_resource,
            native_sketch
        ])
        .run(tauri::generate_context!())
        .expect("Could not start worCalc");
}
