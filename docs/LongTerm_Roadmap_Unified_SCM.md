# Long-Term Roadmap: Unified SCM / Cross-Game Scripts (III+VC+SA)

Status: REASSESSED 2026-08-26. Origin: external writeup claim "Merging GTA III+VC SCM into SA" — assessed against plugin-sdk-sa ground truth and known precedents (GTA:United, Gostown Paradise, MTA Neon).

## Goal Reassessment (2026-08-26)
North-star goal (MMO-style 64-bit launcher + game-side ASI for SA SkyGfx+, extensible to all 32-bit games) is intact, but the path was re-sequenced by reality:

- **Shipped (foundation track):** SH Silent Hill fog (confirmed "sick"), PC-native limit rescale (Buildings/Dummys/Objects=65535, ColModel=40000, EntryInfoNode=100000), bridge v2.2 with StreamingSupervisor + FPS governor, CLEO save path, ModLoader pack-down. These are the *prerequisites* the MMO launcher needs — a stable, good-looking, well-streaming SA.
- **Gating problem:** User verdict on bridge v2.2 = "fps more stable but still runs like ass." Perf is the current blocker, not features. The MMO launcher cannot sit on a game that doesn't run well.
- **Broken item:** Mipgen vegetation pipeline (export→Magic.TXD→import) broke the game (striped textures) → full rollback. Root cause = partial texture sets from an `int()` parse error on 5/9 beach_las textures. PAUSED pending fix.
- **New asset:** Full GTA Vice City PC source tree at `F:\OMFG\TORW-GTA88\GTASource\VC_PC_TG\VC_PC\VC\` (engine C++ in gta_source/, game data in data/models/final). De-risks cross-game Phase F (map merge) and the wrapper prototype's "next game = VC" path — real VC source, not just addresses.

**Re-sequenced priority:**
1. Get SA running smoothly (chase perf; texture/TXD optimization DEPRIORITIZED — see Native TXD Engine track).
2. Resume MMO-launcher feature work (overlay, monitoring, presets).
3. Cross-game SCM (Phases A–F below) — now with VC source in hand.
4. **Native TXD Engine (longer-term infrastructure):** reimplement Magic.TXD inside the launcher app. The real path for texture optimization AND for auto-fixing/patching user installs; the current manual mipgen export is only a stopgap.

## Active Track: Visual & Perf Overhaul (Foundation for MMO Launcher)
| Item | Status | Notes |
|------|--------|-------|
| SH Silent Hill fog | SHIPPED | heightFog density 0.0032, color R0.36/G0.40/B0.50, falloff 0.55; timecyc FogSt=25 ×92 rows; FarClp 1400 night/dusk |
| PC-native limits | SHIPPED | db-driven, redeploys persist; backup III.VC.SA.LimitAdjuster.ini.pre_pcnative.bak |
| Bridge v2.2 (StreamingSupervisor + FPS governor) | SHIPPED | 254,464B; user: "fps more stable but still runs like ass" |
| CLEO save path | SHIPPED | CLEO/gta_bridge_save.cs, magic BRGS |
| ModLoader pack-down | SHIPPED | 12 mods → modloader/skygfx_plus_extras (857 files) |
| Mipgen vegetation (stopgap; superseded by Native TXD Engine) | EXPORT RESOLVED / DEPRIORITIZED | old int() bug gone; full export 2935/0 OK, _build.ini written (215 folders). Manual Magic.TXD build still required — deferred; real solution = embed Magic.TXD natively (see Track). |
| Perf chase (Parallax 123MB, dual-pass veg, streaming tuning) | BLOCKED | gated behind mipgen resolution + user play-test |

## Track: Native TXD Engine (embed Magic.TXD) — STRATEGIC INFRASTRUCTURE
**Goal:** Reimplement the entirety of Magic.TXD's functionality inside the launcher app (64-bit Python side) — TXD read/write, mipmap generation, platform/format conversion, and compression — natively, no external GUI.

**Why:** The current mipgen pipeline depends on Magic.TXD's GUI (no CLI), making optimization a manual, non-automatable step. Embedding it turns texture work into a first-class, scriptable launcher feature.

**User-facing payoff:** Parts of the engine double as an **install-repair mode** — the app can detect and auto-fix/patch broken or partial TXD installs for end users (e.g., the striped-texture class of breakage we hit), not just optimize them.

**Sub-items (phased):**
- TXD container parse/write (RW 3.6 legacy layout already decoded: TEXTURE.STRUCT @76 fmt / @80 w / @82 h / @85 mips / @92 pixels; DXT1/3/5 + A8R8G8B8).
- Mipmap generation (the part Magic.TXD does post-export) — generate mips natively instead of round-tripping through PNG.
- Platform/format conversion (mobile→PC, compression on/off, quality).
- Batch/CLI API + headless build (replaces the manual Magic.TXD mass-build step).
- Install-repair mode: scan a game dir, flag partial/broken txds, offer one-click fix/patch.

**Status:** Not started. Current mipgen export (2935/0, _build.ini ready) is a stopgap proving the decode path; the native engine supersedes it.

## Phases (SCM / Cross-Game — original plan, statuses updated)

### Phase A — Mirage Pool v1/v2
Bridge ASI shared-memory pool for overflow state + streaming pressure relief. v1 deployed (gta_bridge.asi 252,928B); bridge v2.2 superseded it with in-ASI StreamingSupervisor (no separate Mirage Pool round-trip yet proven). Round-trip test inconclusive — diagnose via cleo.log/watchdog before next run.

### Phase B — SCM header patches
Raise mission count + globals space in SA's SCM loader. Requires verified addresses from plugin-sdk-sa (script space 0xA49960, header parse routine). Gate: none ships until addresses verified.

### Phase C — Transpiler (Sanny -> unified SCM)
Compile III/VC main.scm through Sanny into SA-compatible bytecode. Precedent: MTA Neon.

### Phase D — CLEO opcode plugin
Unified opcodes via CLEO custom opcode system (active in our install).

### Phase E — Saves via CLEO (SHIPPED - pragmatic path)
CLEO/gta_bridge_save.cs — magic BRGS, extra state to CLEO\bridge_extra.dat (0A9A/0A9D/0A9E/0A9B). F8 snapshot, auto-restore. Native save-block hook deferred.

### Phase F — Map merge research
The 70%. III/VC maps into SA: RW toolchain (Img-Factory), COL conversion, coordinate alignment, LOD/streaming. **NEW: VC source tree at F:\OMFG\... provides real VC engine + map data — research gate can now start from source, not just addresses.**

## Related
- docs/LongTerm_Goal_Platform_Presets.md — platform/preset layer
- docs/Wrapper_Prototype_CrossGame.md — cross-game lift pattern
- Vault: Projects/Unified SCM Roadmap.md (mirror)
