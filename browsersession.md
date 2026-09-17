# Browser-session handoff — War of Rights client investigation

This file is the handoff from the browser/research session to the Windows remote/local session.

Read `remotesession.md` first. Do **not** repeat work already documented there.

## Current state

The strongest local findings already established are:

* Current client: War of Rights `0.0.201.2`, Steam build `25368613`.
* Ordinary connected-client logs already expose direct lifecycle identity records:

```text
Player %s has joined the server. SteamID: %llu. DLC: %u
Player %s has left the server. SteamID: %llu
```

* A real September 2026 connected log contains hundreds of these lines, so `name <-> SteamID64` is already available from normal client logs.
* Current player-list/native strings use `EntityId`, including strings such as:

```text
Mute player with EntityId: %u
Unmute player with EntityId: %u
Demote player with EntityId: %u
Player list entry for EntityId: %u
```

* The same player-list/UI domain exposes:

```text
@ui_ViewSteamProfile
```

Therefore the important unresolved identity problem is now narrower:

```text
SteamID64 / player name <-> EntityId
```

* Current generic logging CVars exist:

```text
log_Verbosity
log_WriteToFileVerbosity
log_WriteToFile
log_IncludeTime
```

* `DumpCommandsVars` and `DumpVars` are not available.
* Useful current WoR diagnostics CVars already found include:

```text
Diagnostics.Game.Customization
Diagnostics.Game.Outfitter
Diagnostics.Game.UI.Events
Diagnostics.Game.Deployment.Verbosity
Diagnostics.Game.Modes.Verbosity
Online.Diagnostics.Common.Verbosity
Online.Diagnostics.Client.Verbosity
```

* Current death-screen fields independently include:

  * killer/teamkiller
  * cause of death
  * body part
  * distance
  * formation
  * time alive
  * kills
  * deaths
* Current audio assets expose separate bullet kill and bullet head-kill confirmation events.
* Formation runtime CVars and `FormationManager` strings exist.
* The old Gameplay `Debug Logging` UI is absent from the current build.

Do not spend time re-proving any of the above.

---

# Next task: controlled live-server capture

The next useful step is a **small, instrumented live-server session** designed specifically to discover runtime links between SteamID/name, EntityId, gameplay state, and combat/death events.

## 1. Prepare logging

Before joining a server:

1. Preserve the current `game.log` and relevant `logbackups` files.

2. Set/query:

```text
log_Verbosity 4
log_WriteToFileVerbosity 4
log_WriteToFile 1
log_IncludeTime 3
```

If any value is rejected or clamped, record the accepted value exactly.

3. Keep the useful WoR diagnostics CVars at the highest accepted values already discovered, especially:

```text
Online.Diagnostics.Common.Verbosity
Online.Diagnostics.Client.Verbosity
Diagnostics.Game.Deployment.Verbosity
Diagnostics.Game.Modes.Verbosity
```

Record the actual values used.

Do not blindly change unrelated gameplay/network CVars.

## 2. Join one populated public server

A short normal session is sufficient.

Stay connected long enough to naturally produce several identifiable lifecycle/gameplay events.

Record wall-clock times for as many of these as occur:

```text
local connection to server
team selection
regiment/battery selection
company selection
class/role selection
spawn
2–3 clearly visible player joins/leaves
local death
local hit confirmation
local headshot confirmation
local bullet kill confirmation
teamkill notification
role/class change
disconnect/leave
```

Do not deliberately disrupt the match just to generate events.

If practical, note exact player names involved in one or two observed events for later correlation.

## 3. Preserve and search the complete log

After leaving the server, preserve the resulting log before launching the game again.

Search the **complete high-verbosity log** case-insensitively for:

```text
SteamID
SteamId
EntityId
Entity
Player list
Player
ConnectionManager
OnlineSession
Session
Channel
Formation
Death
Killed
Kill
Hit
Head
TeamKill
Cause
BodyPart
Role
Class
Regiment
Company
Deployment
```

Do not only collect matching lines. Inspect surrounding context.

## 4. Primary target: SteamID/name <-> EntityId

Inspect context around every line shaped like:

```text
Player <name> has joined the server. SteamID: <id>
```

Also search each known player name from the test session across the complete log.

We are specifically looking for any line that associates the same player with:

```text
EntityId
entity number
session identifier
connection identifier
player handle
another stable numeric ID
```

Potentially useful evidence could look conceptually like:

```text
Player Example joined ... SteamID: 7656...
...
Created player/entity ...
EntityId: 1234
```

or:

```text
EntityId 1234
Player Example
```

The lines do not need to be adjacent if timing/order gives a strong correlation.

If any plausible identity bridge is found, preserve a generous amount of surrounding log context.

This is the highest-priority discovery.

## 5. Track the local player's stable identifiers

For the local player, determine whether any numeric identifier repeats across:

```text
connection
team/unit selection
class selection
spawn
death
respawn
role change
disconnect
```

For every candidate identifier, record:

* exact value
* every log line containing it
* timestamp
* event occurring at that time

We want to know whether one client-side gameplay identifier follows a player through the whole lifecycle.

## 6. Combat/death correlation

If the local player dies, use the recorded timestamp and inspect nearby log output.

Look for information corresponding to the fields already known to exist in the current death screen:

```text
killer
teamkiller
cause of death
weapon
body part
distance
formation
```

If possible, note what the death screen visibly showed so it can be compared against logged/internal data.

If a local hit/headshot/bullet-kill confirmation occurs, inspect the same time window for:

```text
EntityId
target/player reference
SteamID
weapon
damage
hit type
result code
death state
kill state
```

The important question is whether shooter-side kill confirmation is:

```text
only a boolean/result
```

or something closer to:

```text
result + target/entity reference
```

Do not infer more than the evidence supports.

## 7. Formation observation

If convenient during normal play, record the time when the local player clearly changes between formation states.

For example:

```text
In Formation
Skirmishing
Out of Line
```

Search the log around those timestamps for:

```text
Formation
Cluster
Buff
Skirmish
OutOfLine
```

We are not trying to reconstruct the complete formation algorithm yet.

We only want to know whether formation transitions/state are surfaced in any observable current-client output.

## 8. Useful negative results

Negative findings are important.

Explicitly record if:

```text
EntityId never appears in a connected high-verbosity log
join/leave remains the only identity-rich log output
combat events produce no meaningful lines
death-screen fields are not reflected in logs
formation state changes are never logged
SteamID and EntityId never appear in the same observable path
maximum verbosity creates little or no additional gameplay output
```

That will tell us whether logs are exhausted as an acquisition path.

## 9. Append results to remotesession.md

Append a new clearly dated section to `remotesession.md`.

For each useful finding include:

```text
timestamp
exact log line(s)
source log filename/path
player name, if relevant
SteamID64, if relevant
EntityId/other identifier, if relevant
real gameplay action occurring at that time
```

Separate:

```text
FACT
INFERENCE
UNKNOWN
```

Do not repeat the previous static-analysis findings unless necessary to explain new evidence.

---

# Priority order

The most valuable discoveries are:

1. **Any direct or indirect `SteamID64/name <-> EntityId` bridge.**
2. Any stable identifier following one player across join/spawn/role/death/leave.
3. Structured combat/death information observable by the connected client.
4. Evidence concerning explicit formation-state output.
5. Additional useful current diagnostics CVars discovered naturally.

If item 1 is found, preserve all surrounding context before continuing.

Do not begin memory scanning, hooking, injection, packet reverse engineering, or invasive runtime modification during this pass.

The purpose of this test is to determine whether current first-party logging already exposes enough structure to avoid those paths.
