//! Native integration for the archived, build-verified read-only collector.
use serde_json::{json, Value};
use std::{
    collections::HashMap,
    fs::{File, OpenOptions},
    io::{Read, Seek, SeekFrom, Write},
    path::PathBuf,
};
type Result<T> = std::result::Result<T, String>;
const MAX_BUFFER: usize = 64 * 1024 * 1024;
const KNOWN_HASH: &str = "2e8439241eba3e82eb7a60a548eb661617767b986fe415bb00f48d8ee07a5270";

fn word(raw: &[u8], offset: usize) -> u64 {
    u64::from_le_bytes(raw[offset..offset + 8].try_into().unwrap())
}
fn header(raw: &[u8]) -> Result<(usize, usize)> {
    if raw.len() != 24 {
        return Err("Invalid event-buffer header length".into());
    }
    let (start, end, capacity) = (word(raw, 0), word(raw, 8), word(raw, 16));
    if start > end || end > capacity || (start == 0 && capacity != 0) {
        return Err("Invalid event-buffer pointers".into());
    }
    if end - start > MAX_BUFFER as u64 {
        return Err("Event buffer exceeds safety limit".into());
    }
    Ok((start as usize, (end - start) as usize))
}

#[derive(Default)]
struct Decoder {
    previous: Option<Vec<u8>>,
    cursor: usize,
    generation: u64,
}
impl Decoder {
    fn observe(
        &mut self,
        current: &[u8],
        names: &HashMap<String, String>,
    ) -> (String, usize, Vec<Value>) {
        if self.previous.as_deref() == Some(current) {
            return ("unchanged".into(), current.len(), vec![]);
        }
        let initial = self.previous.is_none();
        let append = self
            .previous
            .as_ref()
            .is_some_and(|p| current.starts_with(p));
        let offset = if append {
            self.previous.as_ref().unwrap().len()
        } else {
            0
        };
        let kind = if initial {
            "initial"
        } else if append {
            "append"
        } else if current.len() < self.previous.as_ref().unwrap().len() {
            "reset"
        } else {
            "rewrite"
        };
        if !append {
            self.cursor = 0;
            self.generation += 1;
        }
        let mut rows = Vec::new();
        while self.cursor + 4 <= current.len() {
            let event_type =
                u32::from_le_bytes(current[self.cursor..self.cursor + 4].try_into().unwrap());
            let size = match event_type {
                0 => 40,
                1 => 16,
                2 => 32,
                _ => break,
            };
            if self.cursor + size > current.len() {
                break;
            }
            let raw = &current[self.cursor..self.cursor + size];
            if event_type == 0 {
                let victim = word(raw, 8).to_string();
                let killer = word(raw, 16).to_string();
                let flags = raw[34];
                let formation = if flags & 4 != 0 {
                    "out_of_line"
                } else if flags & 2 != 0 {
                    "unmapped_1"
                } else {
                    "unmapped_0"
                };
                rows.push(json!({"victim":{"steam_id_64":victim,"name":names.get(&victim)},
                    "killer":{"steam_id_64":killer,"name":names.get(&killer)},
                    "damage_type":raw[24],"cause_category":if (4..=9).contains(&raw[24]) {"bullet"} else {"unmapped"},
                    "teamkill":flags & 1 != 0,"formation":formation,"flags":flags,
                    "buffer_offset":self.cursor,"buffer_generation":self.generation,
                    "preexisting_at_attach":initial,"timestamp_is_observation":true,
                    "observed_at_ms":now_ms(),"raw_hex":raw.iter().map(|b| format!("{b:02x}")).collect::<String>()}));
            }
            self.cursor += size;
        }
        self.previous = Some(current.to_vec());
        (kind.into(), offset, rows)
    }
}
fn now_ms() -> u128 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis()
}

#[derive(Default)]
struct Names {
    values: HashMap<String, String>,
    offset: u64,
    pending: String,
}
impl Names {
    fn refresh(&mut self, path: &PathBuf) {
        let Ok(mut file) = File::open(path) else {
            return;
        };
        let Ok(metadata) = file.metadata() else {
            return;
        };
        if metadata.len() < self.offset {
            self.offset = 0;
            self.pending.clear();
        }
        if file.seek(SeekFrom::Start(self.offset)).is_err() {
            return;
        }
        let mut bytes = Vec::new();
        // Bound log work per poll; retain incomplete lines until the next read.
        if file.take(1024 * 1024).read_to_end(&mut bytes).is_err() {
            return;
        }
        self.offset += bytes.len() as u64;
        self.pending.push_str(&String::from_utf8_lossy(&bytes));
        if let Some(end) = self.pending.rfind('\n') {
            for line in self.pending[..end].lines() {
                if let Some((id, name)) = parse_name(line) {
                    self.values.insert(id, name);
                }
            }
            self.pending = self.pending[end + 1..].to_owned();
        }
    }
}
fn parse_name(line: &str) -> Option<(String, String)> {
    let (_, rest) = line.split_once("Player ")?;
    let (name, id) = rest
        .split_once(" has joined the server. SteamID: ")
        .or_else(|| rest.split_once(" has left the server. SteamID: "))?;
    let id: String = id.chars().take_while(|c| c.is_ascii_digit()).collect();
    if id.is_empty() {
        None
    } else {
        Some((id, name.to_owned()))
    }
}

pub struct Session {
    reader: platform::Reader,
    decoder: Decoder,
    names: Names,
    game_log: PathBuf,
    directory: PathBuf,
    binary: File,
    changes: File,
    deaths: File,
    csv: File,
}
impl Session {
    pub fn start(root: PathBuf) -> Result<Self> {
        let reader = platform::Reader::open()?;
        std::fs::create_dir_all(&root).map_err(|e| e.to_string())?;
        let mut directory = root.join(format!("capture-{}", now_ms()));
        let mut suffix = 0;
        loop {
            match std::fs::create_dir(&directory) {
                Ok(()) => break,
                Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => {
                    suffix += 1;
                    directory = root.join(format!("capture-{}-{suffix}", now_ms()));
                }
                Err(e) => return Err(e.to_string()),
            }
        }
        let create = |name: &str| {
            OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(directory.join(name))
                .map_err(|e| e.to_string())
        };
        std::fs::write(
            directory.join("metadata.json"),
            json!({"schema_version":1,"process_access_mask":"0x1010",
            "executable_sha256":KNOWN_HASH,"executable":reader.executable,"module_base":reader.base,
            "recorder_active_rva":"0x15EFD50","event_buffer_start_rva":"0x15EFE10"})
            .to_string(),
        )
        .map_err(|e| e.to_string())?;
        let mut csv = create("deaths.csv")?;
        writeln!(csv,"observed_at_ms,killer_steam_id_64,killer_name,victim_steam_id_64,victim_name,damage_type,formation,teamkill,preexisting_at_attach").map_err(|e| e.to_string())?;
        let game_log = reader
            .executable
            .parent()
            .and_then(|p| p.parent())
            .and_then(|p| p.parent())
            .ok_or("Invalid game executable path")?
            .join("game.log");
        Ok(Self {
            reader,
            decoder: Decoder::default(),
            names: Names::default(),
            game_log,
            binary: create("capture.bin")?,
            changes: create("changes.jsonl")?,
            deaths: create("deaths.jsonl")?,
            csv,
            directory,
        })
    }
    pub fn poll(&mut self) -> Result<Value> {
        let (active, buffer) = self.reader.snapshot()?;
        self.names.refresh(&self.game_log);
        let (kind, offset, rows) = self.decoder.observe(&buffer, &self.names.values);
        if kind != "unchanged" {
            let capture_offset = self.binary.stream_position().map_err(|e| e.to_string())?;
            self.binary
                .write_all(&buffer[offset..])
                .map_err(|e| e.to_string())?;
            writeln!(self.changes,"{}", json!({"kind":kind,"active":active,"observed_at_ms":now_ms(),"buffer_generation":self.decoder.generation,"buffer_offset":offset,"current_size":buffer.len(),"capture_offset":capture_offset,"capture_length":buffer.len()-offset})).map_err(|e| e.to_string())?;
            for row in &rows {
                writeln!(self.deaths, "{row}").map_err(|e| e.to_string())?;
                let fields = [
                    &row["observed_at_ms"],
                    &row["killer"]["steam_id_64"],
                    &row["killer"]["name"],
                    &row["victim"]["steam_id_64"],
                    &row["victim"]["name"],
                    &row["damage_type"],
                    &row["formation"],
                    &row["teamkill"],
                    &row["preexisting_at_attach"],
                ];
                writeln!(
                    self.csv,
                    "{}",
                    fields
                        .iter()
                        .map(|v| format!(
                            "\"{}\"",
                            v.as_str()
                                .map(str::to_owned)
                                .unwrap_or_else(|| if v.is_null() {
                                    String::new()
                                } else {
                                    v.to_string()
                                })
                                .replace('"', "\"\"")
                        ))
                        .collect::<Vec<_>>()
                        .join(",")
                )
                .map_err(|e| e.to_string())?;
            }
            for file in [
                &mut self.binary,
                &mut self.changes,
                &mut self.deaths,
                &mut self.csv,
            ] {
                file.flush().map_err(|e| e.to_string())?;
            }
        }
        Ok(
            json!({"running":true,"active":active,"buffer_size":buffer.len(),"directory":self.directory,"deaths":rows}),
        )
    }
}

#[cfg(windows)]
mod platform {
    use super::*;
    use sha2::{Digest, Sha256};
    use windows_sys::Win32::{
        Foundation::{CloseHandle, INVALID_HANDLE_VALUE},
        System::{
            Diagnostics::{Debug::ReadProcessMemory, ToolHelp::*},
            Threading::{OpenProcess, PROCESS_QUERY_LIMITED_INFORMATION, PROCESS_VM_READ},
        },
    };
    struct Handle(usize);
    impl Drop for Handle {
        fn drop(&mut self) {
            unsafe {
                CloseHandle(self.0 as _);
            }
        }
    }
    fn error() -> String {
        std::io::Error::last_os_error().to_string()
    }
    fn snapshot(flags: u32, pid: u32) -> Result<Handle> {
        let handle = unsafe { CreateToolhelp32Snapshot(flags, pid) };
        if handle == INVALID_HANDLE_VALUE {
            Err(error())
        } else {
            Ok(Handle(handle as usize))
        }
    }
    fn wide(value: &[u16]) -> String {
        String::from_utf16_lossy(
            &value[..value.iter().position(|v| *v == 0).unwrap_or(value.len())],
        )
    }
    pub struct Reader {
        handle: Handle,
        pub base: usize,
        pub executable: PathBuf,
    }
    impl Reader {
        pub fn open() -> Result<Self> {
            let processes = snapshot(TH32CS_SNAPPROCESS, 0)?;
            let mut entry: PROCESSENTRY32W = unsafe { std::mem::zeroed() };
            entry.dwSize = std::mem::size_of_val(&entry) as u32;
            let mut ids = Vec::new();
            let mut ok = unsafe { Process32FirstW(processes.0 as _, &mut entry) };
            while ok != 0 {
                if wide(&entry.szExeFile).eq_ignore_ascii_case("WarOfRights.exe") {
                    ids.push(entry.th32ProcessID);
                }
                ok = unsafe { Process32NextW(processes.0 as _, &mut entry) };
            }
            if ids.len() != 1 {
                return Err(if ids.is_empty() {
                    "WarOfRights.exe is not running. Start the game first."
                } else {
                    "Multiple game processes found. Leave only one running."
                }
                .into());
            }
            let modules = snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, ids[0])?;
            let mut module: MODULEENTRY32W = unsafe { std::mem::zeroed() };
            module.dwSize = std::mem::size_of_val(&module) as u32;
            let mut ok = unsafe { Module32FirstW(modules.0 as _, &mut module) };
            while ok != 0 {
                if wide(&module.szModule).eq_ignore_ascii_case("WarOfRights.exe") {
                    let executable = PathBuf::from(wide(&module.szExePath));
                    let mut file = File::open(&executable).map_err(|e| e.to_string())?;
                    let mut digest = Sha256::new();
                    let mut block = vec![0; 1024 * 1024];
                    loop {
                        let count = file.read(&mut block).map_err(|e| e.to_string())?;
                        if count == 0 {
                            break;
                        }
                        digest.update(&block[..count]);
                    }
                    if format!("{:x}", digest.finalize()) != KNOWN_HASH {
                        return Err("Unsupported War of Rights build: executable hash mismatch. The tracker needs verified offsets for this version.".into());
                    }
                    let handle = unsafe {
                        OpenProcess(
                            PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ,
                            0,
                            ids[0],
                        )
                    };
                    if handle.is_null() {
                        return Err(error());
                    }
                    return Ok(Self {
                        handle: Handle(handle as usize),
                        base: module.modBaseAddr as usize,
                        executable,
                    });
                }
                ok = unsafe { Module32NextW(modules.0 as _, &mut module) };
            }
            Err("Game module was not found".into())
        }
        fn read(&self, address: usize, size: usize) -> Result<Vec<u8>> {
            let mut bytes = vec![0; size];
            if size == 0 {
                return Ok(bytes);
            }
            let mut received = 0;
            let ok = unsafe {
                ReadProcessMemory(
                    self.handle.0 as _,
                    address as _,
                    bytes.as_mut_ptr().cast(),
                    size,
                    &mut received,
                )
            };
            if ok == 0 {
                return Err(error());
            }
            if received != size {
                return Err("Short game memory read".into());
            }
            Ok(bytes)
        }
        pub fn snapshot(&self) -> Result<(bool, Vec<u8>)> {
            for _ in 0..5 {
                let active = self.read(self.base + 0x015EFD50, 1)?;
                let before = self.read(self.base + 0x015EFE10, 24)?;
                let (start, size) = header(&before)?;
                let data = self.read(start, size)?;
                if before == self.read(self.base + 0x015EFE10, 24)?
                    && active == self.read(self.base + 0x015EFD50, 1)?
                {
                    return Ok((active[0] != 0, data));
                }
            }
            Err("Event buffer changed during every snapshot attempt; retry capture".into())
        }
    }
}
#[cfg(not(windows))]
mod platform {
    use super::*;
    pub struct Reader {
        pub base: usize,
        pub executable: PathBuf,
    }
    impl Reader {
        pub fn open() -> Result<Self> {
            Err("Kill tracker capture is available on Windows only".into())
        }
        pub fn snapshot(&self) -> Result<(bool, Vec<u8>)> {
            Err("Kill tracker capture is available on Windows only".into())
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn death(flags: u8) -> Vec<u8> {
        let mut raw = vec![0; 40];
        raw[8..16].copy_from_slice(&76561198649671288u64.to_le_bytes());
        raw[16..24].copy_from_slice(&76561198168674032u64.to_le_bytes());
        raw[24] = 4;
        raw[34] = flags;
        raw
    }
    #[test]
    fn confirmed_death_and_independent_flags() {
        let (_, _, rows) = Decoder::default().observe(&death(5), &HashMap::new());
        assert_eq!(rows[0]["victim"]["steam_id_64"], "76561198649671288");
        assert_eq!(rows[0]["killer"]["steam_id_64"], "76561198168674032");
        assert_eq!(rows[0]["formation"], "out_of_line");
        assert_eq!(rows[0]["teamkill"], true);
        assert_eq!(rows[0]["cause_category"], "bullet");
    }
    #[test]
    fn partial_mixed_records_unchanged_and_reset() {
        let mut decoder = Decoder::default();
        let names = HashMap::new();
        let mut bytes = vec![0; 16];
        bytes[0] = 1;
        bytes.extend(death(2));
        assert!(decoder.observe(&bytes[..30], &names).2.is_empty());
        let rows = decoder.observe(&bytes, &names).2;
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0]["buffer_offset"], 16);
        assert_eq!(rows[0]["formation"], "unmapped_1");
        assert!(decoder.observe(&bytes, &names).2.is_empty());
        decoder.observe(&[], &names);
        assert_eq!(
            decoder.observe(&death(0), &names).2[0]["buffer_generation"],
            2
        );
    }
    #[test]
    fn validates_headers_and_unknown_suffix() {
        assert_eq!(header(&[0; 24]).unwrap(), (0, 0));
        assert!(header(&[0; 23]).is_err());
        let mut raw = [0; 24];
        raw[8..16].copy_from_slice(&1u64.to_le_bytes());
        assert!(header(&raw).is_err());
        raw[..8].copy_from_slice(&1u64.to_le_bytes());
        raw[8..16].copy_from_slice(&(MAX_BUFFER as u64 + 2).to_le_bytes());
        raw[16..24].copy_from_slice(&(MAX_BUFFER as u64 + 2).to_le_bytes());
        assert!(header(&raw).is_err());
        assert!(Decoder::default()
            .observe(&[9; 40], &HashMap::new())
            .2
            .is_empty());
    }
    #[test]
    fn resolves_player_lifecycle_names() {
        assert_eq!(
            parse_name("[Log] Player A, B has left the server. SteamID: 76561198168674032. DLC: 0"),
            Some(("76561198168674032".into(), "A, B".into()))
        );
        assert!(parse_name("chat: killed someone").is_none());
    }
}
