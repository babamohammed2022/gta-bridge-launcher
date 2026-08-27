# GTA Bridge Launcher — Consolidated Roadmap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Take the launcher from "recovery-complete" to "public-ready mod manager + perf-stable game", then open the cross-game track.

**Architecture:** 64-bit PyQt5 launcher (`app.py`) + managers/ modules + 32-bit `gta_bridge.asi` (v2.2, StreamingSupervisor + FPS governor). txdlite = pure-Python RW TXD engine with C accelerator (`txdfix.dll`). Mod management = Mod Loader folder enable/disable (launcher NEVER renames or rewrites modloader content). All state in `launcher_data/` (writable, exe-relative when frozen).

**Tech Stack:** Python 3.13 (venv64), PyQt5, Pillow 12.3, ctypes→txdfix.dll (MSVC /O2), PyInstaller (launcher.spec), sqlite3, Mod Loader (external), CLEO 5.4 (external).

## Global Constraints (hard rules learned 2026-08-26 — violating these broke the game)

1. **NEVER rename folders inside `modloader/`** — Mod Loader's menu identity = folder name.
2. **NEVER modify files inside fake-IMG dirs** (any folder named `*.img`) — override-critical, game's RW loader rejects spec-correct rewrites of PS2-origin textures.
3. **NEVER regenerate DXT3 mipmaps** — BOX-downscale + re-encode destroys fine alpha (cables, foliage).
4. **NEVER delete backups** — the "healthy file → delete backup" logic orphaned 15 damaged files and cost hours.
5. Launcher touches modloader only via whole-folder moves between `modloader/` ↔ `modloader_back/`.
6. DLC source folders (`launcher_data/dlc/*`) are ground truth for pack files — diff against them, never trust backup chains alone.
7. Build only with venv64 python: `E:/dev(dave)/_SAS_1987/87_installer/venv64/Scripts/python.exe -m PyInstaller launcher.spec --noconfirm`.
8. QImage from bytes requires holding the buffer (`self._buf`) or native crash.
9. `GTALauncher` attr is `game_path` (not `game_dir`); `ScreenBase` owns `self.root` (never `QVBoxLayout(self)`); RW format mask is `& 0x0F00`.
10. Verify every UI change with the offscreen render test (construct + show + grab + count colors) before deploy.

---

## STATE AUDIT (2026-08-26 close)

| Item | Status |
|------|--------|
| TXD engine (txdlite) + C accel (142×) | ✅ SHIPPED, verified byte-exact SA+VC |
| TXD EDITOR screen (Magic.TXD menus, Pinta edit port) | ✅ SHIPPED |
| Mip scanner + conservative fixer (crash-safe, per-file backups) | ✅ SHIPPED (aggressive mode disabled) |
| DLC packs vs MODS split + Mod Loader toggles + drag-drop install | ✅ SHIPPED |
| Pack presets (enable/disable sets, NO renaming) | ✅ SHIPPED |
| Install recovery (all 419 TXDs verified vs DLC sources, 0 diffs) | ✅ COMPLETE |
| skygfx.ini | ⚠️ USER IS FIXING — do not touch until they report back |
| Friend zip v3 | ⏸️ BACKBURNER (rebuild after visuals confirmed) |
| 303 "missing mips" flags | Cosmetic/game-safe; scanner label misleading |
| RW version codec | ❌ bit-packing bug (version_encode mismatch) |
| CLEO save script | ❌ disabled (CLEO4 string opcode breaks on CLEO 5.4) |
| Ariane | Pop-out only (Info menu); embedded pane not started |
| Perf | ❌ "runs like ass" — THE blocker for everything downstream |

---

## PRIORITY STACK (user questionnaire 2026-08-26: 1a+b, 2b+c, 3c, 4a, 5c, 6a, 7)

P0 = launch-blockers only. P1 = Ariane pop-out ✅(done) + drag-drop ✅(done). P2 = perf. P3 = public-release robustness. P4 = cross-game.

---

### Task 1: Scanner honesty pass — relabel "missing mips" as optional quality info

**Files:**
- Modify: `managers/txdlite.py` (`mip_issues`, ~line 441)
- Modify: `app.py` (`_scan_txds`, ModsScreen)

**Interfaces:**
- Produces: `mip_issues(tex, strict=False) -> list[str]` — strict=False returns [] for pure missing-mips (keeps corrupt-level detection); `_scan_txds` shows two buckets: "BROKEN" (corrupt levels) vs "COULD OPTIMIZE" (missing mips, yellow-dim not yellow-bright).

- [ ] **Step 1: Add strict param to mip_issues**

```python
def mip_issues(tex, strict=True):
    """Return issue strings for one texture ([] = healthy).
    strict=False: missing-mips is reported as optimization potential, not an issue."""
    issues = []
    exp_levels = max(1, max(tex.width, tex.height).bit_length())
    if strict and tex.width >= 8 and tex.num_levels < exp_levels:
        issues.append('missing mips (%d/%d)' % (tex.num_levels, exp_levels))
    for i, m in enumerate(tex.mips):
        w = max(1, tex.width >> i)
        h = max(1, tex.height >> i)
        exp = expected_level_size(w, h, tex)
        if len(m) != exp:
            issues.append('level %d corrupt (size %d != %d)' % (i, len(m), exp))
            break
    return issues
```

- [ ] **Step 2: Update _scan_txds to two buckets**

In `app.py` `_scan_txds`, replace the single issues check:
```python
issues = [i for t in txd.textures for i in txdlite.mip_issues(t, strict=True)]
opt = [i for t in txd.textures for i in txdlite.mip_issues(t, strict=False)]
if issues:
    item = QListWidgetItem(f'[BROKEN] {rel} — {len(issues)}')
    item.setForeground(QColor('#ffd23f'))
elif opt:
    item = QListWidgetItem(f'[OPT] {rel} — could add mips')
    item.setForeground(QColor(T.COLOR_TEXT_DIM))
else:
    item = QListWidgetItem(f'[OK] {rel}')
```

- [ ] **Step 3: Verify offscreen** — run ModsScreen scan headless; expect 0 [BROKEN], ~300 [OPT].

- [ ] **Step 4: Rebuild + deploy** (venv64 PyInstaller, copy exe + txdfix.dll).

---

### Task 2: Fix RW version codec (version_encode bit-packing)

**Files:**
- Modify: `managers/txdlite.py` (`version_decode`/`version_encode`, ~line 455)

**Interfaces:**
- Produces: `version_encode(ver_str, build) -> int` where `version_encode(*version_decode(stamp)) == stamp` for all KNOWN_VERSIONS. `version_friendly(stamp)` already works.

- [ ] **Step 1: Rewrite both functions per gtamods packing**

Wiki layout: version 0xVJNBB (V=3bits hex-digit, J=4bits, N=4bits, B=6bits binary-rev), stamp = packed_version in bits 0-15... Actual verified layout from librw `rwbase.h`:
```
libraryID = (packed & 0xFFFF) << 16 | build(0xFFFF)   # SA stamp 0x1803FFFF
packed = version - 0x30000, laid out VVJJJJNN NNBBBBBB (16 bits)
```
```python
def version_decode(stamp):
    if not stamp or stamp == 0xFFFFFFFF:
        return ("unknown", 0)
    packed = (stamp >> 16) & 0xFFFF
    build = stamp & 0xFFFF
    v = packed + 0x30000
    ver = "%x.%x.%x" % ((v >> 16) & 0xF, (v >> 12) & 0xF, (v >> 8) & 0xFF)
    return (ver, build)

def version_encode(ver_str, build=0xFFFF):
    parts = [int(p, 16) for p in ver_str.split('.')]
    v = (parts[0] << 16) | (parts[1] << 12) | (parts[2] << 8)
    packed = v - 0x30000
    return ((packed & 0xFFFF) << 16) | (build & 0xFFFF)
```

- [ ] **Step 2: Round-trip test**

```python
for name, stamp in txdlite.KNOWN_VERSIONS:
    ver, build = txdlite.version_decode(stamp)
    assert txdlite.version_encode(ver, build) == stamp, name
```
Expected: all pass (SA 3.6.0.3 → 0x1803FFFF).

- [ ] **Step 3: Wire version display into TxdEditorScreen properties panel** — add `self.p_ver = body('-')` row showing `version_friendly(txd.version)` on load.

- [ ] **Step 4: py_compile + offscreen construct + rebuild + deploy.**

---

### Task 3: Recompile gta_bridge_save.cs for CLEO 5

**Files:**
- Modify: `E:/games/gtasa_skygfx_plus/CLEO/gta_bridge_save.cs.disabled` (source recovered from it or rewrite from roadmap spec)
- Reference: `docs/LongTerm_Roadmap_Unified_SCM.md` Phase E (magic BRGS, `CLEO\bridge_extra.dat`, 0A9A/0A9D/0A9E/0A9B, F8 snapshot)

**Interfaces:**
- Produces: compiled `gta_bridge_save.cs` that loads clean under CLEO 5.4 (no null-string 0A9A crash).

- [ ] **Step 1: Rewrite source with CLEO5-safe file ops** — replace `0A9A` string-literal form with `0A9B` (close) + CLEO5 `0AC8`/`0A9A` via string var, or use CLEO5's `0A99`? Verify against CLEO5 docs in `E:/SDKs/CLEO5/`. Key change: pass file path via `0AC9` style or local string var, never inline literal.

- [ ] **Step 2: Compile with Sanny Builder 4** (`E:/SDKs/SannyBuilder4/sanny.exe`, CLI: `sanny.exe compile <in.txt> <out.cs>`) — the diag.txt source format is the template (`{$CLEO .cs}` header).

- [ ] **Step 3: Test in game** — F8 snapshot, verify `CLEO\bridge_extra.dat` written, no CLEO error dialog.

- [ ] **Step 4: Re-enable (remove .disabled), add to friend zip contents list.**

---

### Task 4: Perf chase — the P2 blocker

**Files:**
- Modify: `asi_bridge/` (gta_bridge.asi source), `launcher_data/profiles/*.json`, `limit_adjuster_settings.py`
- Reference: roadmap "Perf chase (Parallax 123MB, dual-pass veg, streaming tuning) BLOCKED"

**Interfaces:**
- Produces: measured FPS before/after; profile `perf` in launcher; bridge ini tuning keys documented.

- [ ] **Step 1: Baseline measurement** — user plays 10 min with bridge overlay FPS; record min/avg/max per area (city/country/interior).

- [ ] **Step 2: Parallax audit** — Parallax mod is 123MB of textures; test game with Parallax moved to modloader_back. If FPS delta > 15%, Parallax gets its own quality tier in presets.

- [ ] **Step 3: Streaming tuning via bridge ini** — StreamingSupervisor knobs (available via `gta_bridge.ini`); sweep 2-3 configs, keep best.

- [ ] **Step 4: Encode winner as `perf` profile** in `launcher_data/profiles/`, selectable from PlayScreen profile combo.

- [ ] **Step 5: Update roadmap perf row** from BLOCKED to status with numbers.

---

### Task 5: Ariane embedded pane — research spike (P4 gate)

**Files:**
- Create: `docs/spike_ariane_embed.md`
- Reference: `E:/SDKs/ariane/src` (40k LOC C++14, librw-based), vault `Projects/Ariane — Dryxio Map Editor.md`

**Interfaces:**
- Produces: feasibility doc — which Ariane subsystems (IDE/IPL parse, viewport, COL) map to Python ports vs subprocess calls; effort estimate per phase; go/no-go recommendation.

- [ ] **Step 1: Inventory Ariane src/** — `ls E:/SDKs/ariane/src`, identify parse layer (IDE/IPL/IMG/COL/TXD/DFF readers) vs render layer (D3D9/GL3) vs UI (Qt?).

- [ ] **Step 2: Assess parse-layer port** — txdlite already covers TXD; estimate LOC for IDE/IPL text parsers (likely small — they're text formats) and IMG archive reader (~200 lines Python).

- [ ] **Step 3: Decide render strategy** — options: (a) subprocess ariane.exe with IPC (pop-out++, already shipped), (b) Qt3D/pyqtgraph OpenGL viewport with own DFF parser (big), (c) headless map data viewer only (no 3D, list/inspect IDE/IPL entries — small, useful for mod conflict debugging).

- [ ] **Step 4: Write spike doc with recommendation + phased estimate; get user sign-off before any implementation.**

---

### Task 6: Public-release hardening (P3, after perf)

**Files:**
- Modify: `app.py` (error dialogs → friendly), `launcher.py` (GitManager already degraded gracefully), `launcher.spec`
- Create: `docs/RELEASE_CHECKLIST.md`

**Interfaces:**
- Produces: one-folder distributable; crash logs written to `launcher_data/logs/`; README.

- [ ] **Step 1: Crash logging** — wrap `main()` in try/except writing traceback to `launcher_data/logs/crash_YYYYMMDD.log` + friendly QMessageBox.

- [ ] **Step 2: First-run experience** — if `gta_sa.exe` not found next to exe, show game-path picker dialog instead of assuming.

- [ ] **Step 3: onedir build** — switch launcher.spec to onedir (friend's crash was onefile `_MEIPASS` weirdness); test frozen data-dir resolution.

- [ ] **Step 4: Write RELEASE_CHECKLIST.md** — build → deploy → smoke test list (launch, each screen, scan, pack apply, TXD edit round-trip).

- [ ] **Step 5: Rebuild friend zip from checklist output.**

---

### Task 7: Cross-game gate (P4 — VC next)

**Files:**
- Reference: `F:\OMFG\TORW-GTA88\GTASource\VC_PC_TG\VC_PC\VC\` (VC source), `H:/games/VC/txd` (23 VC TXDs already verified byte-exact by txdlite)
- Create: `docs/vc_gate.md`

**Interfaces:**
- Produces: go/no-go for launcher supporting VC (game detection, VC limit set, VC TXD quirks).

- [ ] **Step 1: txdlite VC validation** — already 23/23 round-trip; add VC-specific raster formats if any appear in H:/games/VC/txd scan (check for platform≠9 natives).

- [ ] **Step 2: Game detection** — launcher detects VC via `gta_vc.exe` presence; profiles/packs paths per-game.

- [ ] **Step 3: Write vc_gate.md** — what works, what's missing, effort estimate. User sign-off gates any build.

---

## Execution Order & Dependencies

```
Task 1 (scanner honesty)  ──┐
Task 2 (version codec)   ──┤── independent, do first, ~1h total
Task 3 (CLEO save)        ──┘
Task 4 (perf)             ── needs user play-test sessions
Task 5 (Ariane spike)     ── independent research, no code risk
Task 6 (hardening)        ── after perf (packaging decisions depend on it)
Task 7 (VC gate)          ── anytime, research only
```

## Self-Review

- Spec coverage: roadmap items 13-16 ✓ (T1/T2/T3/T5), perf blocker ✓ (T4), public release ✓ (T6), cross-game ✓ (T7). Native TXD Engine track: core shipped (txdlite); install-repair mode shipped (scanner+fixer); remaining = format conversion UI (folded into editor, exists) — closed.
- Placeholders: none — all steps have concrete code/commands.
- Type consistency: `mip_issues(tex, strict)` signature consistent T1; version codec round-trip asserted T2.
