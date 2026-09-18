Objective

We have already proven that the current WoR client receives full remote death events in memory, and the memory observer successfully captured Kepi-like records for all observed deaths.

Do not spend time on raw network packet sniffing unless it becomes necessary.

The current concern is whether WoR exposes the same death-event data through a cleaner outward-facing mechanism than direct process-memory observation.

Investigate whether the complete death event handled by:

WarOfRights.exe + 0x9802C0
preferred VA 0x1409802C0

is subsequently or previously exposed through any of:

file logging other than game.log
replay/report serialization
telemetry
local IPC
named pipe
shared memory / file mapping
localhost TCP/UDP
local HTTP/WebSocket
Windows messaging
event bus / callback dispatcher
plugin/mod interface
any other process-readable interface
Known death-event structure

At handler entry:

RCX = victim player object
RDX = death-event pointer

Known fields:

event + 0x00 = uint32 attacker EntityId
event + 0x04 = uint8 damage/cause type
event + 0x26 = uint8 body-part type
event + 0x36 = uint8 death-behavior type

The same handler resolves attacker EntityId to a player object/name.

Highest-priority target

The handler also appends a compact 0x28-byte death record to an in-memory recorder/event stream when the recorder is active.

Known globals:

0x1415EFD50
0x1415EFE10

Find all readers/xrefs/consumers of these globals and the 0x28 death-record vector.

For every consumer, classify it as:

internal replay only
file serialization
BattleReport/UI
telemetry/network
IPC
other

Main question:

Does any consumer cross the process boundary or expose the event in a cleaner form?

Secondary target

Trace all callees and nearby upstream/downstream paths around 0x1409802C0 looking for:

Serialize
Write
Save
Dump
Queue
Dispatch
Publish
Send
Report
Telemetry
Event
Callback
Observer
Listener
IPC
Pipe
SharedMemory
FileMapping
localhost
127.0.0.1
WebSocket
HTTP

Do not rely only on strings; use xrefs and call graph where possible.

Runtime check if static analysis is inconclusive

Use a controlled death while monitoring only WarOfRights.exe with ProcMon or equivalent.

Look for process activity occurring exactly at death-event time:

file writes
new/opened files
registry writes
named-pipe activity
mapped-file activity
other local IPC

Compare against an idle baseline to remove noise.

Deliverable

Append results to remotesession.md.

Separate clearly:

FACT
INFERENCE
UNKNOWN

For every useful mechanism found, include:

exact function/address or RVA
relevant global/object
what data crosses the boundary
destination/path/endpoint if any
whether it contains attacker + victim + cause
whether it works for remote->remote deaths

If no clean outward-facing sink exists, state that explicitly.

The goal is to determine whether a Kepi-style collector can avoid arbitrary process-memory observation and instead consume a cleaner client-side event/output boundary.
