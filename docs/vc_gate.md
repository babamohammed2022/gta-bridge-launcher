# VC Gate — Launcher Cross-Game Assessment

Date: 2026-08-26 | Status: GO for Phase 1 (low risk), phased

## What already works
- **txdlite reads VC TXDs**: 23/23 files in `H:/games/VC/txd` round-trip byte-exact (validated 2026-08-26). VC PC textures use the same D3D native layout (platform field differs but parser preserves it).
- **Architecture is game-agnostic**: game detection = exe name; profiles/packs/DLC are per-game-dir already.

## Phase 1: VC detection + TXD editor support (~half day)
- [ ] Game detection: `gta_vc.exe` presence → game='vc'
- [ ] Per-game defaults: VC limit set (from `E:/SDKs/III.VC.SA.LimitAdjuster` docs), VC-friendly pack scaffold
- [ ] TXD EDITOR: verify decode of all VC raster formats found in `H:/games/VC/txd` (scan for platform≠9 natives; VC PC is mostly D3D8/9 — same layout)
- [ ] Mod Loader: confirm VC build supports modloader.asi (it does — III/VC/SA unified)

## Phase 2: VC-specific quirks (research)
- [ ] VC TXD version stamps differ (3.4.0.3 = 0x4003FFFF) — version_friendly already handles
- [ ] DFF: VC geometry flags differ from SA — out of scope until DFF parser exists (Ariane spike Phase 1)
- [ ] SkyGfx VC build exists (`E:/SDKs/skygfx*` family) — preset research from VC source at `F:\OMFG\TORW-GTA88\GTASource\VC_PC_TG\VC_PC\VC\`

## Phase 3: III
- Same pattern as VC. III TXDs = oldest RW (3.1.0.1) — txdlite version codec handles.

## Risks
- VC native textures may include PS2-remnant quirks like SA's — the fake-IMG/DXT3 rules apply equally.
- Limit adjuster configs differ per game — `limit_adjuster_settings.py` LIMIT_CATEGORIES needs a VC table (research from III.VC.SA.LimitAdjuster repo, already cloned).

## Recommendation
GO: Phase 1 when SA perf is stable. No SA work blocked by this.
