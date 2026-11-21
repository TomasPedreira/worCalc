# Native Kill tracker

Open the **Kill Tracker** desktop shortcut or
`artifacts/desktop/KillTracker/kill-tracker.exe`. Start War of Rights yourself,
check the read-only authorization box and click **Start capture**. Opening the app
alone does not access the game. **Stop capture** closes the process handle;
closing Kill Tracker also releases it. Capture continues while you use the
separate worCalc or worSketch apps. Kill Tracker bundles no maps or terrain.

The integration requests only `PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ`
(`0x1010`). It verifies the executable SHA-256 before opening the process handle:

`2e8439241eba3e82eb7a60a548eb661617767b986fe415bb00f48d8ee07a5270`

This is the previously verified 0.0.201.2 client. Other builds produce an unsupported
build message and require independently verified recorder offsets before support
can be added. Capture is available only on Windows.

The live feed searches killer/victim names and Steam IDs. Names come from player
join/leave lines in the game's `game.log`; unresolved players show their exact
Steam ID. The feed retains the most recent 2,000 events, while disk capture keeps
all observed changes. “Earlier” marks events already present at attachment. Times
are observation times, rather than exact in-game event times.

The original confirmed death layout is preserved: event types 0, 1 and 2 have
sizes 40, 16 and 32 bytes; only type 0 is decoded. Damage codes 4–9 show as bullet,
formation code 2 as out_of_line; other values remain unmapped. Teamkill is decoded
independently. Unknown record suffixes are preserved without guessing boundaries.
Partial records wait for a subsequent complete snapshot.

Each session creates a unique directory beneath the app data directory's
`kill-captures` folder. The workspace shows its full location. Files include:

- `metadata.json`: verified executable, module base, recorder offsets and access mask.
- `capture.bin`: opaque buffer changes, including unknown records.
- `changes.jsonl`: change type, generation and binary/buffer offsets.
- `deaths.jsonl`: decoded player identities, cause, formation, flags and raw bytes.
- `deaths.csv`: decoded rows for spreadsheet analysis.

The historical Python collector remains in `artifacts/migration`; the active
tracker uses native Tauri commands and Rust directly.
