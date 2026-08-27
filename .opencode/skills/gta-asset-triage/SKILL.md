---
name: gta-asset-triage
description: Diagnose and repair damaged TXD/DFF/veg assets in the GTA Bridge Launcher game install (striped textures, brown blob trees, untextured models, mip corruption)
---

# GTA Asset Triage (TXD/DFF/IPL damage)

## When to Use
- Trees/vegetation render as brown/grey blobs or stripes
- Models render untextured while TXDs look fine
- After any mipgen/batch texture operation ran and was rolled back
- User reports "the trees are broken again"

## Workflow
1. **Diff vs ground truth**: `python utils/veg_repair.py --dry-run` — byte-compare enabled modloader packs against `launcher_data/dlc/` (DLC folders are ground truth, rule #6).
2. **Apply restore**: `python utils/veg_repair.py --apply` — backs up to `launcher_data/backups/<stamp>/`, copies DLC version over damaged files.
3. **DXT3 rescue**: `python utils/veg_audit.py --apply` — mines ALL `launcher_data/backups/txd_mipfix_*` generations for clean byte-variants of files whose DLC copy is ALSO corrupt (upstream damage). 245/247 rescued this way once.
4. **DFF/IPL hypothesis check**: `python utils/veg_audit.py` read-only part — unresolved DFF texture refs + IPL orphan scan. Untextured models with healthy TXDs = DFF refs missing (e.g. `pinelo128`).
5. **Missing-texture aliasing**: if a referenced texture exists NOWHERE (not in quarantines, not in gta3.img), author a minimal alias TXD: clone the closest sibling texture via txdlite (bytes preserved, no re-encode), rename, drop into modloader pack AND mirror into `launcher_data/dlc/` twin.
6. **Verify**: rescan touched files — `mip_issues(strict)==0`; re-run audit part; unresolved count must drop.

## Rules (VIOLATING THESE BROKE THE GAME)
- NEVER regenerate DXT3 mips (skip any DXT3 file — rescue from backups instead).
- NEVER write inside `*.img` dirs; NEVER rename modloader folders; NEVER delete backups.
- DLC `launcher_data/dlc/` = ground truth; modloader and dlc must stay in sync after writes.
- Game restart needed for TXD swaps; asi swaps need the asi reloaded (game restart too).
- `MemoryAvailable: 10/2047` on F5 diag = streaming pool nearly exhausted — not an asset bug.
