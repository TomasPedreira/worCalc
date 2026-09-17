# War of Rights September 2026 local client evidence

This report contains only new evidence obtained from the installed September 2026 War of Rights client. It does not repeat the prior public-source architecture research.

## 1. Debug Logging key

The current **0.0.201.2 / Steam build 25368613** client no longer exposes a Gameplay → Debug Logging setting.

- Visible UI levels: **none**
- Exact JSON key: **none**
- Persisted values: **none**

Evidence:

- `C:\Program Files (x86)\Steam\steamapps\common\War of Rights\UserConfig\local\settings.json` contains no Debug, Diagnostics, or Logging entry.
- The current executable's Gameplay-option table contains entries such as:
  - `@ui_Game.Replays.AllowSaving`
  - `@ui_Game.Player.PlayerEffects.DynamicDof`
  - `@ui_Game.Freelook.DuringActions`
  - `@ui_Game.KillConfirmation`
  It contains no Debug Logging binding.
- `GameData.pak :: Localization/english/MainMenuOptionsGameplay.json` and the other English localization files contain no `Debug Logging`, diagnostics, or verbosity label.
- Repeated menu-only launches left `settings.json` byte-identical to the backup.

Backup:

```text
C:\Program Files (x86)\Steam\steamapps\common\War of Rights\UserConfig\local\settings.json.codex-backup-20260917-142808
SHA-256: C83B57AACBB05131CAAECEF0CB303E02D0653C01E284FB759A187742AF295DE4
```

The executable does contain this generic diagnostics-level text:

```text
-1 = Disabled.
 0 = Errors only.
 1 = Errors and warnings.
 2 = Errors, warnings and messages.
 3 = Errors, warnings, messages and comments.
```

Source: `WarOfRights.exe`. Action: searched extracted executable strings and current menu/localization definitions.

## 2. Current console and CVar surface

Source log:

```text
C:\Program Files (x86)\Steam\steamapps\common\War of Rights\logbackups\Game Build(2) 17 Sep 26 (14 46 07).log
```

Action: entered each command at the main-menu console and inspected the resulting log.

Exact results:

```text
[Warning] Unknown command: DumpCommandsVars
[Warning] Unknown command: DumpVars
    log_Verbosity = 0 [DUMPTODISK]
    log_WriteToFileVerbosity = 0 [DUMPTODISK]
    log_WriteToFile = 1 [DUMPTODISK]
    log_IncludeTime = 1 []
```

| Input | Current status |
| --- | --- |
| `DumpCommandsVars` | Unknown command |
| `DumpVars` | Unknown command |
| `log_Verbosity` | Exists; value `0`; `[DUMPTODISK]` |
| `log_WriteToFileVerbosity` | Exists; value `0`; `[DUMPTODISK]` |
| `log_WriteToFile` | Exists; value `1`; `[DUMPTODISK]` |
| `log_IncludeTime` | Exists; value `1` |

Because both enumeration commands are absent, no generated command/CVar dump exists to search.

Additional working diagnostics CVars found and queried:

```text
Diagnostics.Game.Customization = 1 []
Diagnostics.Game.Outfitter = 1 []
Diagnostics.Game.UI.Events = 0 []
Diagnostics.Game.Deployment.Verbosity = 1 []
Diagnostics.Game.Modes.Verbosity = 1 []
Online.Diagnostics.Common.Verbosity = 2 []
Online.Diagnostics.Client.Verbosity = 2 []
```

Source:

```text
C:\Program Files (x86)\Steam\steamapps\common\War of Rights\logbackups\Game Build(2) 17 Sep 26 (14 47 59).log
```

The tested server-side diagnostics command was unavailable to the client and returned an unknown-command warning.

## 3. Current binary string anchors

Source binary:

```text
C:\Program Files (x86)\Steam\steamapps\common\War of Rights\WarOfRights.exe
SHA-256: 2E8439241EBA3E82EB7A60A548EB661617767B986FE415BB00F48D8EE07A5270
```

No separate War of Rights gameplay DLL was present alongside the executable, so all useful native anchors below came from `WarOfRights.exe`.

### Identity and lifecycle

```text
Player %s has joined the server. SteamID: %llu. DLC: %u
Player %s has left the server. SteamID: %llu
[OnlineSessionComponent::OnlineSessionComponent] CPU: %s
ClientReceiveSessionsMessage
ClientReceiveSessionsStatusMessage
```

These are current-build strings, not only historical log artifacts. The join/leave format directly couples player name and SteamID64 at the client logging site.

### Connection tokens

```text
[ConnectionManager::OnClientConnectionStatePacket] Connection with token "%016llX" accepted.
[ConnectionManager::OnClientConnectionStatePacket] Connection with token "%016llX" rejected.
[ConnectionManager::OnClientConnectionStatePacket] Connection with token "%016llX" timed out.
[ConnectionManager::OnClientConnectionStatePacket] Received state for unknown connection token "%016llX".
```

### Tab/player-list and entity bridge

```text
@ui_ViewSteamProfile
Mute player with EntityId: %u
Unmute player with EntityId: %u
Demote player with EntityId: %u
Player list entry for EntityId: %u
```

The exact surrounding wording varies by operation, but the player-list/UI strings use `EntityId`, while the same UI exposes `@ui_ViewSteamProfile`. This is direct local evidence that the current client has a player-list path spanning gameplay entity identity and Steam-profile functionality. The exact internal join key remains unidentified.

### Formation

```text
FormationManager
Game.Formation.Cluster.MinPlayers
Game.Formation.Buff.PlayerPercentage
Game.Formation.Buff.Distance
Game.Formation.Buff.Timeout
Game.Formation.Skirmishing.BuffMinPlayers
Game.Formation.Skirmishing.BuffDistance
```

Related UI/audio formatting strings include formation-state shout/status text. The queried live CVar values were:

```text
Game.Formation.Cluster.MinPlayers = 6
Game.Formation.Buff.PlayerPercentage = 0
Game.Formation.Buff.Distance = 6
Game.Formation.Buff.Timeout = 4
Game.Formation.Skirmishing.BuffMinPlayers = 3
Game.Formation.Skirmishing.BuffDistance = 12
```

Replay/UI definitions also contain an icon field keyed by `EntityId`. These anchors make local formation recomputation a concrete possibility, but do not prove whether the displayed remote state is replicated or recomputed.

### Casualty and death-screen bindings

```text
@ui_DeathScreen.KilledBy
@ui_DeathScreen.TeamKilledBy
@ui_DeathScreen.CauseOfDeath
@ui_DeathScreen.BodyPart
@ui_DeathScreen.Distance
@ui_DeathScreen.Formation
@ui_DeathScreen.TimeAlive
@ui_DeathScreen.Kills
@ui_DeathScreen.Deaths
%s%s %s%s
```

The death screen is therefore supplied with, or derives, multiple separately labelled fields rather than rendering one opaque sentence: killer/teamkiller, cause, body part, distance, formation, time alive, kills, and deaths.

### Teamkill

```text
@ui_DeathScreen.TeamKilledBy
@ui_TeamKill
@ui_TeamKilled
Punishing player with SteamId: %llu
```

The punishment path has a current native string taking a SteamID64, while the death UI has a distinct team-killer label.

### Exact requested-anchor misses

No exact native-string match was found for:

```text
PlatformSystem
PlatformId
SessionId
ConnectionId
ChannelId
ActorId
RMI:Entity
Casualty
Incapacitated
Headshot
Reconnect
```

This is only a string-search result; it does not prove that corresponding concepts or compiled types are absent.

## 4. Package bindings

The readable packages were inspected without modifying the originals.

### Audio events

Source:

```text
C:\Program Files (x86)\Steam\steamapps\common\War of Rights\Assets\Audio.pak
audio/ace/wor_ux.xml
```

Exact triggers:

```text
Play_UX_Hurtmarker_Minieball
Play_UX_Hurtmarker_MinieBallHeadshot
Play_UX_Hurtmarker_Bayonet
Play_UX_Hitmarker_Bayonet
Play_UX_KillConfirmation_Bullet
Play_UX_KillConfirmation_Bullet_Head
```

The soundbank metadata resolves these trigger/event IDs:

```text
3263891933 -> media 98620796
2605860383 -> media 546254172
4155415482 -> media 98620796
3702673027 -> media 546254172
```

The corresponding media names are present in the audio metadata. Bullet kill and bullet head-kill are distinct named client audio events, although pairs share media references.

### Kill-confirmation option

```text
ui_Game.KillConfirmation
```

The current Gameplay settings/localization package contains a visible kill-confirmation label and description. Its runtime value was `1`. No separate visible body-hit or headshot-confirmation option was found.

### Death-screen fields

The `GameData.pak` English localization defines all of the following independently:

```text
Killed By
Team Killed By
Cause of Death
Body Part
Distance
Formation
Time Alive
Kills
Deaths
```

Body-part localization includes specific anatomical regions rather than a binary head/body distinction.

### Player-info and Steam-profile bindings

`GameData.pak` localization and `WarOfRights.exe` contain player-info strings used by the admin/in-game interfaces, including the Steam-profile action. `UI.pak` contains `TabView.gfx`, but ordinary string extraction did not expose usable bindings from that compiled Flash asset. No opaque-archive brute force was performed.

### Reconnect-related wording

No exact visible `Reconnect` label was found. The relevant visible session wording was:

```text
JOINING SESSION
VIA STEAM
```

The executable also contains an internal retry-related connection string, but not an exact user-facing reconnect label.

## 5. Menu-only log baseline

Maximum discovered client diagnostics values were enabled for the baseline:

```text
Diagnostics.Game.Customization = 1
Diagnostics.Game.Outfitter = 1
Diagnostics.Game.UI.Events = 0
Diagnostics.Game.Deployment.Verbosity = 1
Diagnostics.Game.Modes.Verbosity = 1
Online.Diagnostics.Common.Verbosity = 2
Online.Diagnostics.Client.Verbosity = 2
```

Source:

```text
C:\Program Files (x86)\Steam\steamapps\common\War of Rights\game.log.codex-max-diagnostics-20260917-144850
```

Action: launched to the main menu, waited for the backend connection to be accepted, then exited without joining a server.

The only relevant identity/session line was:

```text
<14:48:40> [ConnectionManager::OnClientConnectionStatePacket] Connection with token "000000006AABEFB8" accepted.
```

The menu-only baseline did **not** log:

- platform/player records;
- SteamID or other platform IDs;
- session IDs or channel IDs;
- entity IDs or actor IDs;
- reconnect records;
- formation/combat records;
- replay or stats records.

### Existing connected-session evidence

Source:

```text
C:\Program Files (x86)\Steam\steamapps\common\War of Rights\logbackups\Game Build(1) 16 Sep 26 (23 04 24).log
```

Action that produced it: a pre-existing normal connected session from 16 September 2026. No live server was joined during this investigation.

The available connected logs contain **724 current-format join/leave lines**. Example exact pair:

```text
<23:10:12> Player {30thNC-BB}2ndLt. Thomas Quarry has joined the server. SteamID: 76561198168674032. DLC: 0
<23:30:13> Player {30thNC-BB}2ndLt. Thomas Quarry has left the server. SteamID: 76561198168674032
```

Together with the same format strings still embedded in `WarOfRights.exe`, this confirms that version 0.0.201.2 retains a directly usable name ↔ SteamID64 join/leave path in ordinary connected-client logs.

## Final local-state notes

- `settings.json` and `system.cfg` were restored and verified against their pre-test hashes.
- Temporary test-user configuration was removed.
- War of Rights was exited; Steam was left open.
- Temporary package extraction data was left in place where cleanup was blocked, without modifying the original archives.

## 6. Remote-only follow-up — 17 September 2026

This pass was performed while no person was available at the Windows desktop. The available remote-control surface could address browser tabs but did not expose native Windows applications, so a controlled live-server gameplay sequence could not be performed. No result below is presented as a substitute for the requested high-verbosity live capture.

### FACT — verbosity-4 menu startup

The client was launched to the main menu with these temporary `system.cfg` values:

```text
log_Verbosity=4
log_WriteToFileVerbosity=4
log_WriteToFile=1
log_IncludeTime=3
Online.Diagnostics.Common.Verbosity=3
Online.Diagnostics.Client.Verbosity=3
Diagnostics.Game.Deployment.Verbosity=3
Diagnostics.Game.Modes.Verbosity=3
```

Source log:

```text
C:\Users\pedre\AppData\Local\Temp\wor-live-capture-20260917-151826\game.menu-verbosity4-diag3.log
SHA-256: F06BCE388C46DB48D21B0DA5C1D641F35CA684BF400160B19941C37BD914E238
```

Action: launched the installed client through Steam, allowed it to reach the main menu/backend connection, and then terminated it without joining a game server.

The log's timestamp shape changed to include both elapsed and wall-clock time, directly demonstrating that `log_IncludeTime=3` took effect:

```text
<  0.218>: <15:19:30> [ConnectionManager::OnClientConnectionStatePacket] Connection with token "000000006AABF6F2" accepted.
```

No unknown-variable, invalid-value, or clamping warning named any of the eight temporary settings. The log did not print their effective values, however, so acceptance of each diagnostics value at `3` was not independently queried.

This menu-only verbosity-4 log still contained no `SteamID`, `EntityId`, player record, session/channel ID, or other player/gameplay identity link.

The original `system.cfg` was restored after the launch. Its restored SHA-256 is:

```text
4ED0D92A832E4D2EF657A8D07A16060BD7DF6BD49BF4CA7BF505ED676D8EDD7A
```

### FACT — exhaustive audit of the existing connected capture

Source:

```text
C:\Program Files (x86)\Steam\steamapps\common\War of Rights\logbackups\Game Build(1) 16 Sep 26 (23 04 24).log
FileVersion/ProductVersion: 0.0.201.1
Size: 272840 bytes
SHA-256: DE05EC1A7E8AFD4191F1F6A743609C4A0C0DBDC5B289036BB3CDBCB9923B89CE
```

Action: searched the complete connected-session log case-insensitively and inspected surrounding context, separating actual subsystem output from chat text, server names, asset warnings, and console-completion output.

Exact zero-match results:

```text
EntityId       0
Player list    0
OnlineSession  0
Session        0
Channel        0
BodyPart       0
TeamKill       0
```

The only generic `Entity` occurrence was startup text:

```text
<23:04:29> Entity system initialization
```

The only `ConnectionManager` occurrence was the menu/backend token, before server selection:

```text
<23:04:32> [ConnectionManager::OnClientConnectionStatePacket] Connection with token "000000006AAB1270" accepted.
```

The local player lifecycle entry was followed by streaming/outfit initialization rather than any player-specific numeric identifier:

```text
<23:10:12> Player {30thNC-BB}2ndLt. Thomas Quarry has joined the server. SteamID: 76561198168674032. DLC: 0
<23:10:12> [streaming_manager_t::dispatch_streaming_update] Performing synchronous streaming update.
<23:10:12> [OutfitComponent_t::InitializeApparelCollectionForUniform] Uniform identifier is zero.
```

The full session contains 724 name/SteamID join-or-leave records but no observable line joining any one of them to an entity, actor, session, channel, or other stable gameplay identifier.

Round-level structured events do appear:

```text
<23:10:13> [ActiveRegimentManager_t::ClSetActiveRegiments]
<23:10:13> CGameRulesEventHelper::OnRoundStarted
<23:12:35> CGameRulesEventHelper::OnVictory TeamID: 2
<23:14:33> [ActiveRegimentManager_t::ClSetActiveRegiments]
<23:14:33> CGameRulesEventHelper::OnRoundStarted
```

These lines establish current client callbacks for active-regiment, round-start, and winning-team state, but contain no player identity or unit payload.

No subsystem log line described a player hit, death, killer, weapon/cause, body part, teamkill, or formation-state transition. Matches for words such as `hit`, `kill`, `death`, and `formation` resolved to chat, server names, asset text, or command/CVar completion—not structured combat records.

### FACT — additional current command/CVar anchors

The connected log contains console-completion output at `23:15:30`. The initiating keystrokes were not recorded, so this is not evidence that `DumpCommandsVars` or `DumpVars` worked. It does provide exact current names:

```text
Game.BattleReport.Debug = 0 []
Game.BattleReport.Dump (Command)
Game.BattleReport.Save (Command)
Game.MatchReplay.Save (Command)
Game.MatchReplay.Start (Command)
Game.MatchReplay.Stop (Command)
Game.Modes.Deployment.OutputActiveDeploymentPoints (Command)
Game.NameTags.CompanyHighlight = 1 []
Game.OfficerOrders.Debug.EnableOrders = 1 []
Game.Outfitter.Progression.RestrictClass = 1 []
Game.Outfitter.Progression.RestrictRank = 1 []
Game.Outfitter.Progression.RestrictRegiment = 1 []
Game.Player.CorpseManager.Debug = 0 []
Game.Player.CorpseManager.DumpAttachmentNames (Command)
Game.Player.Interpolation.Debug = 0 []
Game.Player.Melee.DebugGFX = 0 []
Game.ShoutingManager.Debug = 0 []
```

No state-changing or administrator-oriented command in that list was invoked during this follow-up.

### INFERENCE

- The normal/default connected log path appears exhausted for `SteamID64/name ↔ EntityId`: the identity-rich lifecycle lines and round/gameplay callbacks coexist in the same complete log, but no shared identifier is emitted.
- `ActiveRegimentManager_t::ClSetActiveRegiments` confirms that regiment state reaches a dedicated client-side manager, but the empty log message gives no evidence about whether its payload contains per-player membership.
- The menu launch suggests verbosity `4` is usable and materially changes log formatting/detail, but only `log_IncludeTime=3` has visible output behavior proving the configured value took effect.

### UNKNOWN

- Whether a genuinely connected session at `log_WriteToFileVerbosity=4` exposes additional player/entity or combat information.
- The effective accepted values of the four diagnostics CVars when set to `3`; no console query was possible remotely.
- Whether the local player's entity identifier is available through the Tab/player-list UI path but deliberately omitted from logs.
- Whether death-screen and formation-transition payloads become visible only when their exact local gameplay events occur at elevated verbosity.
