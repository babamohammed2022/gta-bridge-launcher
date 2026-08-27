# 64-bit Wrapper Launcher — Cross-Game Prototype (m0813)

**Prototype:** GTA Bridge Launcher (E:/dev(dave)/projects/gta_bridge_launcher/) → extends 32-bit games to 64-bit via external launcher + game-side agent.

**Long-term goal (user m0813 verbatim intent):** Make *all* games that used to run on 32-bit run on 64-bit. The wrapper launcher is the prototype — next person lifts entire docs/parts to create similar solutions for GTA VC, Manhunt, God of War, any games.

## Reusable Pattern (liftable)

1. **MMO architecture**
   - 64-bit Python launcher EXE (PyInstaller x64, Windowed) owns config/patching/monitoring, lives beside game EXE (GTA_Bridge_Launcher.exe). Co-location detection: exe_dir/gta_sa.exe → db/config beside exe.
   - 32-bit game-side stub (gta_bridge.asi x86 254KB, PE 014C) injected via Ultimate ASI Loader (vorbisFile.dll). For other games replace with dll proxy / asi / cleo / plugin as game allows.

2. **IPC**
   - Named pipe `\\.\pipe\gta_bridge` line protocol `HELLO`→`GTABRIDGE 1.0`, `PING`→`PONG`, `STATUS`→`alive`, `MEM`→`MEM a u` (ReadMemory safe at 0x8A5A80/0x8E4CB4), `USAGE <name>`→`USAGE n u m`  with `GBridgeClient` retries (EINTR/EINVAL transient) + `BridgeMonitor` thread 1s poll.
   - Future: shared memory for high-bandwidth (streaming) if needed.

3. **Limits patching (game-specific research)**
   - For GTA SA: `Pools.cpp` CALL hooks 0x550FF8 (Peds), 0x55102D (Vehicles), 0x551065 (Buildings) etc via `injector MakeCALL` PoolHook template + `MemoryAvailable` WriteMemory 0x5B8E64+6 capped 2GB (MbToBytes). SDK: E:/SDKs/III.VC.SA.LimitAdjuster/src/shared/{injector,CPool.h}.
   - For GTA VC / Manhunt / GoW: replicate by reading their pool alloc sites (same pattern: hook CPool ctor → replace size), document addresses in vault SDK Locations, keep patch table per game.

4. **Config flow**
   - Python DB `gta_limits.db` (game_limits unique(game,limit_name)) → `gta_bridge.ini` [SALIMITS] via `GTALauncher.write_bridge_ini` every launch (excludes StreamingMemory/MaxColors/MaxModels/VRAM auto-override). Auto VRAM = total//4 clamp 512..8192 (32-bit 4096) via `utils/system_utils.py get_top2007_auto_vram`.
   - Deploy ASI dual root+scripts (some loaders only check root).

5. **Overlay (optional assistant)**
   - In-game ASI DrawHUD hook 0x53E4FF DrawTextInternal 0x719840 etc, F5 paging → delete asi to disable.
   - Optional MoonLoader.lua / CLEO .cs (copy .txt→.cs for actual load) F5/F7 reading same addresses — delete file to disable.

6. **Build**
   - `asi_bridge/premake5.lua` Win32 staticruntime .asi → `premake5 vs2022` + `MSBuild /p:Platform=Win32` (switch slash gotcha)
   - Python EXE: `"64bit/python.exe" -m PyInstaller --onefile --windowed launcher.py` → verify PE 0x8664, test GTALauncher.launch_game + pipe HELLO.

## What to lift for next game (e.g., GTA VC, Manhunt)
- Copy `bridge_client.py` + `GTALauncher` co-location + `write_bridge_ini`/`deploy_asi` (rename pipe/ini per game)
- Create `asi_<game>/src/bridge.cpp` by swapping address table (research step a) + injector copy
- `utils/system_utils.py` auto VRAM scaling reused verbatim
- `docs/LongTerm_Goal_Platform_Presets.md` platform preset theory → adapt period pools per game (PS2 32MB Exact etc)
- `verify_launcher.py` 6-test pattern + live pipe launch_test

## Vault ↔ Code loop
Research → limit_adjuster_settings LIMIT_CATEGORIES maxima → SystemUtils → launcher PRESETS → ASI PoolHook → build → deploy → launch_test pipe → verify 6/6 → compress → distill skillpack. Next builder reads this doc + SDK Locations + vault Long-Term Goal and pastes patch table.

**Next step:** Clear current ASI/CLEO stability (F5 overlay, CLEO .cs), then flesh this cross-game doc with per-game address tables (GTA3 VC SA Manhunt).

## Status (2026-08-26)
- bridge v2.2 SHIPPED (StreamingSupervisor + FPS governor, 254,464B); PC-native limits SHIPPED (db-driven).
- "Next game = VC" path now has real VC source at `F:\OMFG\TORW-GTA88\GTASource\VC_PC_TG\VC_PC\VC\` — address-table research can be done against actual engine C++ (gta_source/), not just SDK guesses.
- Overlay (F5 DrawHUD) + MoonLoader/CLEO assistant still TODO (deferred behind perf).
