# Project: GTA Bridge Launcher
64-bit Python launcher (PyQt5 app.py) + 32-bit ASI (asi_bridge/gta_bridge.asi) for GTA SA.
Game dir: E:/games/gtasa_skygfx_plus (co-located GTA_Bridge_Launcher.exe). Clean baseline: H:/games/clean_sa.
Key modules: launcher.py (GTALauncher deploy chain: write_bridge_ini -> deploy_asi dual root+scripts -> deploy_fixes timecyc -> deploy_dlc), limit_adjuster_settings.py (LIMIT_CATEGORIES 8 cats, PRESETS 11 incl Top of the 2007 + PS2/Xbox/PS3/PS4/PS5), bridge_client.py (named pipe client), app.py (PyQt5 UI: PLAY/LIMITS/MODS/INSTALLER), utils/{rw_inspect,pack_build,package_game_diff}.py.
DB: gta_limits.db tables game_limits/world_data/color_palettes/vram_config/dlc_state.


## UI v2 (2026-08-25)
app.py PlayScreen: PREVIEW panel (title/path/bridge status) + QUICK MODS box (index.json packs, [ON]/[OFF] toggles -> db set_dlc_enabled + DeployWorker deploy_dlc). CONFLICT_GROUPS mutual exclusion in _toggle_pack (enabling a pack disables enabled siblings: vegetation/model_fixes/map groups); clash+off buttons greyed with 'Clashes with X' tooltip. Buttons carry .pack_id attr. index.json may be list OR {packs:[...]} - both parsed defensively. LIMITS: preset slider strip (QScrollArea), spinbox min-width 130 + AlignRight, LIMIT_RELATIONS tooltips (scales-with guidance). Smoke: qm_smoke.py 8/8 ALL OK offscreen.


## UI v3 redesign + DXVK (2026-08-25)
- Yellow SAS87 theme (T: TEXT_BRIGHT #ffe600, SELECT_BLUE #0057d8, PANEL_BG #14120a); NavButton white text, checked = SELECT_BLUE bg.
- LIMITS = GTA V layout: cat_list QListWidget (8 categories) + rows_lay per-category rows + desc_bar hint bar; Crysis roll-out preset menu (preset_btn + preset_menu QScrollArea, QPropertyAnimation maximumHeight 0<->230 OutCubic 180ms).
- _on_change_text DEFINED (was connected-but-missing = the 'crash on setting limits'); saves text limits via db set_limit.
- PLAY right rail: DLC box FIRST (stretch 2, SELECT_BLUE border, was 'QUICK MODS') + PREVIEW below; qm buttons carry .pack_id; CONFLICT_GROUPS mutual exclusion in _toggle_pack.
- DXVK chain: game -> d3d9.dll (our proxy, cpp/d3d9_proxy, FusionFix pattern, 87KB x86) -> vulkan.dll (DXVK v3.0.2 x86 vendored) -> Vulkan; skygfx/ASIs see normal D3D9.
- launcher.py: _dxvk_source_dir frozen-aware, is_dxvk_active (vulkan.dll present), deploy_dxvk(enable) wired in launch_game after deploy_dlc; VRAM gating in write_bridge_ini: no DXVK -> clamp 2048 (SM3.0), DXVK -> up to 8192 (8GB only with DXVK).
- Frozen-build gotchas: tkinter import optional in limit_adjuster_settings (tk=None sentinel, no eager '-> tk.Frame' annotations); launcher.spec entry=app.py + fonts datas; PyInstaller 6.22.2 (6.21 SystemError).


## Limits v2 (2026-08-25)
- bridge.cpp MemoryAvailable cap 2048->4095 MB (u32 immediate max; LAA 32-bit ceiling; ini 8172 clamps to 4095 in-game). ASI rebuilt 264,704B deployed root+scripts.
- LIMIT_CATEGORIES defaults extended (fresh installs): Peds 240, Vehicles 230, Buildings 300000, Dummys 150000 (vegetation), Objects 60000 (vegetation), VisibleLodPtrs 600000, VisibleEntityPtrs 300000, ColModel 42000, AlphaEntityList 8000, StreamingInfo 18000, ExtraObjectsDir 1536, PedIntelligence 240.
- launcher.py seed_default_limits(): first-run auto-seeds 46 extended defaults (guard: Peds is not None -> skip; never overwrites user values). Chain: seed_default_limits -> deploy_dxvk -> write_bridge_ini -> deploy_asi -> deploy_fixes -> deploy_dlc.
- MoonLoader 126 fix: bass.dll + d3dx9_43.dll (from E:/SDKs/sa-essentials) in game root. Broken raw-text gta_bridge_diag.cs removed (CLEO 2F2F).


## State 2026-08-25 late (bridge v2.1 era)
- Launch chain: seed_default_limits -> deploy_dxvk -> write_bridge_ini (LimitAdjuster.ini [SALIMITS] MTA-max + gta_bridge.ini [BRIDGE]) -> deploy_asi -> deploy_fixes -> deploy_dlc -> Popen + _start_exit_watchdog (logs GAME EXITED EARLY code=N if <15s).
- Game STABLE on bridge v2.1 (241,152B): streaming 1024MB, DynamicRenderScale 1.2-4.8, vegetation off, pipe GTABRIDGE 2.0, MEM (2047,88), USAGE via CPools globals.
- Crash saga root causes (all fixed): Buildings>180k world corruption (MTA #5252), _apply_all GTAV-redesign bug (only wrote current category), DLC pack ini clobber, Gemini hallucinated addresses.
- Deferred: Mirage Pool v1 (64-bit companion shared-memory asset bridge, b93), LocTri cache 2728, col-jump 0x5DB96F, vegetation patches (need verified addresses), mipmap/SMAA/rotor, Durango patterns, installers (launcher+DLC separate), frozen-exe logging to exe dir.


## Render slider + night timecyc (2026-08-25 late)
- LIMITS screen: RENDER DISTANCE QSlider (10-60 = 1.0x-6.0x) -> db max_lod_scale -> write_bridge_ini [BRIDGE]; streaming_mem_mb also db-driven (default 2048).
- Night timecyc fix (fix_night_farclip.py in TEMP): night hours 00/20/22 FarClp 2500 FogSt 50, dusk 19 2000/40; 92 lines; ships via launcher_data/fixes + game data/.
- mobile_vegetation TXDs have NO mipmaps (mipmaps=1) — mobile assets stripped; Magic.TXD batch regen = future option. Improved-veg pack = DFF-only (pairs with mobile TXDs); modloader priority improved=7 > mobile=6.
- Console-launched games die when bash tool command ends (process-tree cleanup) — user PLAY from GUI exe is the real test path.
