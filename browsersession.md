# Remote/local task — only goal: recover X killed Y at T with W

Read `remotesession.md` first. Do not repeat prior work.

The only success criterion is obtaining a structured record equivalent to:

```text
timestamp
killer
victim
weapon/cause
```

Indirect identifiers are acceptable only if they can be resolved:

```text
timestamp
killer_entity
victim_entity
weapon/cause
```

Do not spend time on formation, reconnect, roster metadata, generic logging, SteamID mapping, BattleReport, or other subsystems unless they directly help recover attacker → victim kill data.

## Tasks, in order

1. Inspect a native MatchReplay file for discrete kill/death events containing both attacker and victim references.

2. Search replay data for:

   * known player names as UTF-8/ASCII;
   * known player names as UTF-16LE;
   * known SteamID64 as decimal text;
   * known SteamID64 as little-endian uint64;
   * entity/player identifiers;
   * weapon/cause identifiers;
   * kill/death/event records.

3. Determine whether the replay is compressed, containerized, chunked, or otherwise encoded before concluding that strings/IDs are absent.

4. Use a replay containing at least one known death/kill and correlate bytes/records around the known event time.

5. Determine whether replay data can produce:

   ```text
   attacker_ref + victim_ref [+ weapon/cause]
   ```

   If not, clearly report that and move on.

6. In `WarOfRights.exe`, locate and xref:

   ```text
   @ui_DeathScreen.KilledBy
   @ui_DeathScreen.TeamKilledBy
   @ui_DeathScreen.CauseOfDeath
   @ui_DeathScreen.BodyPart
   @ui_DeathScreen.Distance
   ```

7. Follow those xrefs backward and identify where killer identity and cause/weapon values originate.

8. In `WarOfRights.exe`, locate and xref:

   ```text
   Play_UX_KillConfirmation_Bullet
   Play_UX_KillConfirmation_Bullet_Head
   ```

9. Follow those xrefs backward and determine whether the kill-confirmation path receives:

   * only a boolean/result;
   * target EntityId/player reference;
   * hit information;
   * weapon/cause;
   * a larger combat/death event structure.

10. Locate and xref:

    ```text
    @ui_DeathScreen.TeamKilledBy
    @ui_TeamKill
    @ui_TeamKilled
    Punishing player with SteamId: %llu
    ```

11. Determine whether the death-screen, teamkill, and kill-confirmation paths converge on a shared kill/death/damage handler.

12. For any likely common handler, identify whether its arguments or referenced structure contain:

    ```text
    killer / shooter / attacker
    victim / target
    weapon / cause
    hit type
    entity IDs
    timestamp / event time
    ```

13. Prefer xref-driven analysis from the known strings above. Do not perform broad blind reverse engineering unless necessary.

14. If static analysis cannot resolve the event path, perform one controlled live test with a known death/kill and exact timestamp, then correlate:

    * replay;
    * high-verbosity log;
    * death-screen fields;
    * any runtime-visible identifiers.

15. Append results to `remotesession.md`.

For every useful finding include:

* exact string/address/function or replay offset;
* source file;
* relevant pseudocode/disassembly/bytes;
* what it proves;
* what remains unknown.

Separate conclusions into:

```text
FACT
INFERENCE
UNKNOWN
```

## Priority

1. Native replay attacker → victim event.
2. Death-screen killer/cause data source.
3. Shooter kill-confirmation target data source.
4. Teamkill attacker/victim path.
5. Shared combat/death handler.

Stop pursuing a branch if it cannot plausibly yield:

```text
X killed Y at T with W
```

The objective is not to discover generally interesting client data. The objective is specifically to recover the attacker-victim kill relationship and its cause/weapon.
