# Grand Unified Delivery Plan — "GTA Modding 2026"

> **For agentic workers:** Execute wave-by-wave via subagent-driven development; steps use checkbox syntax. Part 1 is DONE (this doc retained as spec-of-record for verification).

**Goal:** Launch = the definitive fan package (what Rockstar should have shipped): multi-game detection, engineered pools/presets, one-artifact distribution; tied into the wider RW-era ecosystem (dirtysa port, native TXD engine, Ariane tooling, cross-game bridges).

**Architecture:** 64-bit PyQt5 orchestrator over maintained file-based runtime (UAL -> Mod Loader -> CLEO 5.4 -> SilentPatch/skygfx). INI/pipe coupling only; no native hooks beyond gta_bridge.asi.

**Tech Stack:** Python 3.13 venv64, PyQt5, PyInstaller onedir, SQLite (gta_limits.db, sadie.db), ASI C++ (premake5/MSBuild Win32), txdlite RW engine.

## Global Constraints
- NEVER rename modloader folders | never write inside *.img dirs | never regenerate DXT3 mips | never delete backups | DLC sources ground truth.
- Nothing ships unverified addresses (triple-verify protocol: plugin-sdk xref + decomp triad + branch test).
- Presets write [SALIMITS] only via LimitAdjuster authority; [PROFILES] owned by profile_manager.
- Console cp1252: ASCII output only. Offscreen QMessageBox segfaults -> inline labels. Never Q*Layout(self) on ScreenBase.
- Agent routing: CN-only OpenRouter fallback chains; mimo=inline only (see oh-my-opencode-slim.jsonc).

## PART 1 — Launcher delivery (DONE 2026-08-27)
Commits: a57b73e baseline / 7e5dde8 A+C+D / c09df54 B+E.
- [x] T0 git init (.gitignore excludes dlc packs; json manifests kept) + pytest 9.1.1 + py_compile sweep
- [x] managers/pool_planner.py `recommended_pools(vram_mb,ram_mb,target='balanced')->{streaming,textures,models,max_lod_scale}` TARGETS balanced/quality/perf; callers rewired: system_utils.calculate_dynamic_limits, memory_monitor.calculate_memory_pools, launcher.write_bridge_ini default
- [x] utils/sweep_harness.py BASE/CANDIDATES(c1_stock,c2_lod6,c3_lod6_noveg,c4_perf)/apply_candidate([PROFILES] preserved)/parse_rows/winner_rank(harmonic mean, *0.75 if min<25)/append_csv->launcher_data/logs/sweep_<id>.csv/main
- [x] profile_manager.encode_perf_profile(row)->perf.json {'name','description','skygfx':{},'bridge':ov} uses self.profiles_dir()
- [x] launcher.spec ONEDIR -> dist/GTA_Bridge_Launcher/{exe,_internal/}; checklist Build section folder-copy
- [x] ConfigManager.set_game_path/get_game_path; app.py KNOWN_EXES={gta_sa.exe:gtasa,gta_vc.exe:gtavc,gta-vc.exe:gtavc,gta3.exe:gta3,manhunt.exe:manhunt}; PlayScreen browse row + _browse_game_dir + detect_lbl
- [x] friend_zip v4-final: EXCLUDE .*\.cs$ (+cleo_saves/*.sav legacy); collect_binaries(exe+txdfix.dll+launcher_data manifests+presets+profiles) exit2 loud-miss + STALE guard vs app.py/launcher.py mtimes; README single-artifact install; checklist Distributable canonical

## USER TEST GAUNTLET
- [ ] **T1** FPS baseline city/country/interior (overlay HUD) + rerun Parallax OFF (>15% delta => Parallax quality tier)
  - [x] ~~F8 save test~~ SKIPPED per user 2026-08-27 ("nnothign happens when i press f8 skip that feature"). Deferred revisit: verify cleo/ gta_bridge_save.cs actually deployed+enabled (not .disabled), check cleo.log. Not a shipping blocker — friend zip contains no custom scripts by design.
- [ ] **T2** <=2 sweep drives (harness applies c1..c4; paste 9 numbers per candidate) -> encode_perf_profile winner -> play-screen perf profile real
- [ ] **T3** frozen-exe smoke pass (checklist 13 lines incl crash-log rename test)
- [ ] **T4** extract dist friend zip onto CLEAN SA 1.0 -> launch once -> ship to friend
- [ ] **T5** skygfx visual pass (user game-side ownership)
- [ ] **T6** Mirage Pool round-trip verdict after probe task below

## PART 2/3 — Long arc stages (effort S/M/L/XL)
1. **Mipgen-Veg resume (M)** — beach_las 5/9 striped class fixed by stage-2 mipgen; rebuild 215 folders headless from _build.ini checksummed; modloader deploy no renames. FAIL=stripes return/mip-count mismatch vs @85 header field. Needs stage 2 slice. Blocked by P-lane TXD-engine start.
2. **Native TXD Engine (L)** — txd_engine/{rw,raster,mipgen}.py: writers DXT1/5+A8R8G8B8 (DXT3 read-only passthrough), mipgen box/triangle validated pixel-vs-Magic.TXD, cli/txdtool.py scan|repair|build (repair=re-emit from source PNGs, backup-first). Falsify: 50-txd round-trip byte-identical no-op; scan must flag historical 5/9 breakage.
3. **Mirage-Pool probe (M)** — pipe PROBE opcode (readers-only CPools globals 0xB74484-B744C4, NO hooks), diag/probe_correlate.py timeline (cleo.log x watchdog x pipe USAGE), 3 scenarios (spawn-storm/fast-travel/SH-fog-night). FAIL=p99 probe latency>4ms under StreamingSupervisor spikes. Verdict may kill Mirage Pool permanently (also a win).
4. **Ariane Ph2 COL viewer (M)** — ariane_lite/{col,dff}.py COLL/COL2/COL3 port ref E:/SDKs/ariane/src; wireframe pane InspectorScreen; DFF stats feeding texture-ref audit. Falsify: parse ALL SA cols 0 exceptions; open any col <=2s. Independent/anytime.
5. **SCM B/C/D** — B(M,gated): plugin-sdk CTheScripts crossref -> USER decomp triad incl script-space 0xA49960 -> minimal mission-count patch inert-when-unchanged. C(XL): Sanny III/VC->SA transpiler, MTA-Neon precedent opcode table first. D(L): CLEO unified opcodes. Corrupt main.scm detection on load = FAIL.
6. **Phase F MVP slice (XL)** — one VC island chunk in SA streaming; VC IPL/IDE semantics+origin from source tree; convert via stage-2 + COL parser stage-4; collision walk-through tolerance check. FAR-CLIP: CTimeCycle 0xB7B1D0 is TABLE - no scalar patch. Needs 2+4+F:\ drive.
7. **Platform presets a-g (L)** — pools tables doc -> PRESETS dict+_apply_preset+ini quarter-RAM recompute -> PoolHook MakeCALL+F5 DrawHUD 0x53E4FF/MoonLoader lua -> skygfx dualPass hook -> pipe verify(-1,-1) pre-9s + verify_launcher 6/6 -> skillpack distill. 30min stress per preset. Deferred until PERF VERDICT.
8. **Cross-game tables -> VC Phase1 (L)** — VC pool sites from real VC gta_source/; asi_vc_bridge+bridge_client_vc; limits table from E:/SDKs/III.VC.SA.LimitAdjuster clone; HELLO handshake rename-per-game. Gate: SA C-stable + F:\ drive.

## Dependency DAG / Waves
```
PERF BLOCKER: W1(done code) -> T1/T2(user) -> VERDICT
W2: mipgen(1) needs TXD-engine(2) start || probe(3) || ArianeCOL(4) anytime
W3: presets(7) post-verdict || SCM C || D
W4: SCM B (user triad) || VC Phase1 (C-stable+drive)
W5: PhaseF MVP (2+4+drive)
```

## BLOCKED-BY-USER
Playtests(T1-T6 above) | decomp triad 0xA49960 (CPlantMgr 0x53BAF4/0x5DBC3A stay DISABLED until verified) | F:\OMFG\TORW-GTA88 availability | Mirage kill-or-keep call | preset naming freeze (PS2-Xbox PS3 PS4 PS5 Exact/Lite matrix per LongTerm_Goal_Platform_Presets.md).

## Housekeeping log (2026-08-27)
sadie.db O3DE rows deleted (ids 7-12,14; backup sadie.db.bak-prewave1). Canonical vault = GTA SA Reverse Engineering Documentation. dirtysa tracked in SKYGFXPLUS_DOCS/Projects/dirtysa (Phases 1-4e done; next: dual-lookup names 210/82, ConvertDataToGameUnits drag fix, coord offset +5000 recipe, subclasses CMonsterTruck/CQuadBike/CBmx/CTrailer). Deferred-list formally parked: MiragePool-v1 shm bridge b93, LocTri cache 2728, col-jump 0x5DB96F, separate installers, exe-dir logging, mobile_vegetation batch regen option.

## Evidence: config_registry implementation (2026-08-27)
- **managers/config_registry.py** (NEW) — single source of truth for ALL external configs: skygfx.ini, gta_bridge.ini, III.VC.SA.LimitAdjuster.ini, modloader/modloader.ini. API: `FILES` dict, `resolve()`, `read()`, `save()`, `snapshot_defaults()`, `reset_to_defaults()`, `preflight()`. ConfigParser strict=False, optionxform=str. Snapshot stores hex-encoded bytes + sha256 + full text per file in `launcher_data/config_defaults_snapshot.json`. Reset backs up current file to `launcher_data/backups/config_reset_<ts>/` first.
- **managers/profile_manager.py** — `apply_profile()` BRIDGE writes rerouted through `config_registry.read('gta_bridge')` + `config_registry.save()` so registry is the single writer.
- **app.py LimitsScreen** — added "RESET TO DEFAULTS" button below category list with two-step inline QLabel confirmation (click arms: "CLICK AGAIN TO CONFIRM", 5s timeout via QTimer). On confirm: iterates all registry keys, calls `reset_to_defaults()`, refreshes render-distance slider + all limit spinboxes from re-read files. Result shown in inline label ("RESET OK (n files)" or failure list in orange).
- **app.py PlayScreen** — added `_run_preflight()` method that calls `config_registry.preflight(game_dir)` and shows result in `preflight_lbl` (green "Config preflight: OK" or orange failure summary). Hooked into `_browse_game_dir` (on dir change) and `_play` (on launch).
- **Verification:** (1) py_compile all touched files passes; (2) registry roundtrip on TEMP copies: snapshot_defaults, mutate, reset_to_defaults('skygfx'), assert byte-identical to snapshot; (3) preflight on real game dir returns ok=True problems=[]; (4) offscreen MainWindow grab works (QT_QPA_PLATFORM=offscreen, png to %TEMP%, color count>50).
- **Deferred:** limit_adjuster section defaults intentionally empty — snapshot-driven. modloader.ini [Profiles.Default.Priority] keys not validated in preflight (parses successfully, which is the current check).
