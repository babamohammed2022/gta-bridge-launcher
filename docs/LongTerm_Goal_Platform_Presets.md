# GTA Bridge Launcher — Long-Term Goal (m0807)

**Date:** 2026-08-24 | **Status:** Pinned for later — clear current ASI/CLEO first

## Status / Reassessment (2026-08-26)
- Goal pinned but re-sequenced: foundation track (fog / PC-native limits / bridge v2.2 / CLEO saves / ModLoader pack-down) SHIPPED; MMO-launcher feature work (overlay, presets, monitoring) DEFERRED behind perf.
- Blocker: SA "runs like ass" per user — perf > features right now.
- Mipgen veg pipeline: export works (2935/0) but depends on Magic.TXD GUI (no CLI) — DEPRIORITIZED; real solution is embedding Magic.TXD natively in the launcher (see roadmap Native TXD Engine track).
- Native TXD Engine: launcher will reimplement Magic.TXD internally — owns TXD optimize AND auto-fix/patch user installs. Added to roadmap as strategic infrastructure.
- New asset: VC source tree at `F:\OMFG\TORW-GTA88\GTASource\VC_PC_TG\VC_PC\VC\` enables cross-game + per-game preset pool research from real engine source.
- Platform presets (PS2/Xbox/PS3/PS4/PS5) still deferred until docs clear + perf stable.

## Goal
MMO-style launcher + game-side ASI (`gta_bridge.asi`) as limits-adjuster / overhaul patch for SA SkyGfx+ (E:/games/gtasa_skygfx_plus). External 64-bit Python launcher owns config/patching/monitoring; ASI applies limits/patches and reports via `\\.\pipe\gta_bridge`.

## Deferred Feature: Platform Emulation Presets (m0804)
Presets that let enhanced SkyGfx emulate exact period limits down to fonts/displays. Choosing preset restores period-correct limits + SkyGfx pipes.

**Preset names (deferred until docs clear):**
- `PS2 (32MB) — Exact` — 32MB RDRAM + 4MB GS eDRAM, PS2 pools (Peds ~110 Buildings ~13k), GS COLCLAMP/DTHE dual-pass, 480i fonts, only PS2 displays
- `Xbox (64MB) — Exact` — 64MB UMA NV2A, 480p, Register Combiners cubemap
- `PS3 (512MB) — Enhanced` — Cell 256 XDR + 256 GDDR3, 720p
- `PS4 (8GB) — Modern` — x86 8GB GDDR5
- `PS5 (16GB) — Next-Gen` — 16GB GDDR6 SSD 4K
- Option per preset: **Full Modern** (host max) vs **Lite** (auto-scaled to host RAM via SystemUtils 1/4 RAM clamp 512–8192)

## Vault↔Code Process Mapping (m0807 asks: does that make sense? YES)

If we keep this goal pinned and break down targeting + map stages vault↔code, we rapidly create features:

1. **Vault spec** → `SDK Locations.md` (LimitAdjuster injector 0x550FF8, CPool, plugin-sdk-sa) + `Platform Presets.md`
2. **Code map** → codebase graph (`get_architecture`, `search_graph`) + `limit_adjuster_settings.py LIMIT_CATEGORIES maxima quadrupled 4M` + `utils/system_utils.py auto VRAM total//4 clamp 512..8192`
3. **Stages:**
   a) Research Pools.cpp 0x550FF8 / MemoryAvailable 0x5B8E64+6 / CPool.h
   b) Launcher PRESETS dict + `_apply_preset` auto VRAM + `GTALauncher.write_bridge_ini` recompute 1/4 RAM each boot + dual-deploy root+scripts
   c) ASI PoolHook MakeCALL + PatchDrawer F5 + PipeServerThread HELLO/PING/STATUS/MEM/USAGE
   d) SkyGfx skygfx.ini dualPass hook
   e) Overlay ASI DrawHUD 0x53E4FF + MoonLoader lua F5/F7 fallback optional (delete to disable)
   f) Verify pipe HELLO/PING pools (-1 until ~9s CPool init) + verify_launcher.py 6/6
   g) Distill → skillpack per stage

**Flow:** vault update → inline edit → premake5 vs2022 → MSBuild Win32 → dual-deploy → launch_test → compress. Deferring platform presets to docs keeps momentum on current stability; next sprint pulls this note as spec.
