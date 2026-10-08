//! Durable plan files. A previous revision is retained for interrupted-save recovery.
use serde_json::{json, Value};
use std::{fs, io::Write, path::Path};

const MAX_BYTES: usize = 5 * 1024 * 1024;
type Result<T> = std::result::Result<T, String>;

fn encode(value: &Value) -> Result<Vec<u8>> {
    if value["version"] != 1 || !value["maps"].is_object() {
        return Err("Unsupported sketch plan format".into());
    }
    let bytes = serde_json::to_vec(value).map_err(|e| e.to_string())?;
    if bytes.len() > MAX_BYTES {
        return Err("Plan file is too large".into());
    }
    Ok(bytes)
}

pub fn load(path: &Path) -> Result<Value> {
    let backup = path.with_extension("bak");
    let source = if path.exists() {
        path
    } else if backup.exists() {
        &backup
    } else {
        return Ok(json!({"version":1, "maps":{}}));
    };
    if fs::metadata(source).map_err(|e| e.to_string())?.len() > MAX_BYTES as u64 {
        return Err("Plan file is too large".into());
    }
    let value = serde_json::from_slice(&fs::read(source).map_err(|e| e.to_string())?)
        .map_err(|e| format!("Could not read saved plans: {e}"))?;
    encode(&value)?;
    Ok(value)
}

pub fn save(path: &Path, value: &Value) -> Result<()> {
    let bytes = encode(value)?;
    fs::create_dir_all(path.parent().ok_or("Missing plan directory")?)
        .map_err(|e| e.to_string())?;
    let temporary = path.with_extension("tmp");
    let backup = path.with_extension("bak");
    let mut file = fs::File::create(&temporary).map_err(|e| e.to_string())?;
    file.write_all(&bytes)
        .and_then(|_| file.sync_all())
        .map_err(|e| e.to_string())?;
    drop(file);
    // Windows cannot rename over an existing file. Keep a recoverable previous
    // revision, including if the process exits between these two renames.
    let had_previous = path.exists();
    if had_previous {
        if backup.exists() {
            fs::remove_file(&backup).map_err(|e| e.to_string())?;
        }
        fs::rename(path, &backup).map_err(|e| e.to_string())?;
    }
    if let Err(error) = fs::rename(&temporary, path) {
        if had_previous {
            let _ = fs::rename(&backup, path);
        }
        return Err(format!("Could not save plans: {error}"));
    }
    Ok(())
}

pub fn export(directory: &Path, value: &Value) -> Result<String> {
    let bytes = encode(value)?;
    fs::create_dir_all(directory).map_err(|e| e.to_string())?;
    let stamp = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map_err(|e| e.to_string())?
        .as_millis();
    for suffix in 0..100 {
        let path = directory.join(format!("worcalc-plans-{stamp}-{suffix}.json"));
        match fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&path)
        {
            Ok(mut file) => {
                file.write_all(&bytes)
                    .and_then(|_| file.sync_all())
                    .map_err(|e| e.to_string())?;
                return Ok(path.to_string_lossy().into_owned());
            }
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(error) => return Err(error.to_string()),
        }
    }
    Err("Could not create a unique export file".into())
}

#[cfg(test)]
mod tests {
    use super::*;
    struct Fixture(std::path::PathBuf);
    impl Fixture {
        fn new(name: &str) -> Self {
            let path =
                std::env::temp_dir().join(format!("worcalc-sketch-{name}-{}", std::process::id()));
            fs::create_dir_all(&path).unwrap();
            Self(path)
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }
    #[test]
    fn saves_and_recovers_the_previous_revision_after_interruption() {
        let fixture = Fixture::new("recovery");
        let path = fixture.0.join("sketches.json");
        assert_eq!(load(&path).unwrap(), json!({"version":1,"maps":{}}));
        let first = json!({"version":1,"maps":{"map-1":{"guns":[]}}});
        let second = json!({"version":1,"maps":{"map-2":{"targets":[]}}});
        save(&path, &first).unwrap();
        save(&path, &second).unwrap();
        assert_eq!(load(&path).unwrap(), second);
        fs::remove_file(&path).unwrap();
        assert_eq!(load(&path).unwrap(), first);
        save(&path, &second).unwrap();
        assert_eq!(load(&path).unwrap(), second);
    }
    #[test]
    fn malformed_updates_do_not_overwrite_existing_plans() {
        let fixture = Fixture::new("invalid");
        let path = fixture.0.join("sketches.json");
        let valid = json!({"version":1,"maps":{}});
        save(&path, &valid).unwrap();
        assert!(save(&path, &json!({"version":99,"maps":{}})).is_err());
        assert!(save(&path, &json!({"version":1,"maps":[]})).is_err());
        assert_eq!(load(&path).unwrap(), valid);
        fs::write(&path, b"broken").unwrap();
        assert!(load(&path).is_err());
    }
    #[test]
    fn exports_are_independent_files_with_the_complete_library() {
        let fixture = Fixture::new("export");
        let value = json!({"version":1,"maps":{"map-1":{}}});
        let first = export(&fixture.0, &value).unwrap();
        let second = export(&fixture.0, &value).unwrap();
        assert_ne!(first, second);
        assert_eq!(load(Path::new(&first)).unwrap(), value);
        assert_eq!(load(Path::new(&second)).unwrap(), value);
    }
}
