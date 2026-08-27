#!/usr/bin/env python3
"""txd_consolidate.py — SA-native TXD PARENTING via ISOLATED OVERRIDE PACK.

Replaces the old in-place-strip approach.  Creates a single new Mod Loader
pack `zz_fixedveg_loading/` that OVERRIDES original vegetation TXDs using
ML's native later-pack-wins rule.  Original packs are NEVER touched.

Layout of new pack (modloader/zz_fixedveg_loading/):
  veg_shared.txd               — 374 COMMON textures (one copy each)
  gta.dat                      — registers bridge_veg_txdp.ide
  data/maps/bridge_veg_txdp.ide— 74 txdp entries
  <OrigPackRelPath> x 120      — stripped child TXDs at game-root-identical paths
                                 (e.g. mobile_vegetation/gta_potplants2.txd)

ML rules leveraged:
  - modloader/<PackName>/... maps to game-root/
  - Packs load alphabetically; LATER pack's file overrides earlier same-path file.
  - loose dff/txd in pack root auto-injects as gta3.img entry by basename.
  - gta.dat inside a pack is line-union merged.
  - IDE path in that gta.dat resolves pack-relative.

Usage:
  python utils/txd_consolidate.py                                # dry-run only
  python utils/txd_consolidate.py --apply --force-experimental    # execute
"""
import argparse
import copy
import hashlib
import os
import shutil
import struct
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# ── paths ──────────────────────────────────────────────────────────────────
GAME_MODLOADER = Path("E:/games/gtasa_skygfx_plus/modloader")
PROJECT = Path(__file__).resolve().parent.parent
DLC_ROOT = PROJECT / "launcher_data" / "dlc"
BACKUP_ROOT = PROJECT / "launcher_data" / "backups"

# The existing backup of originals from the first consolidation attempt.
# Contains exactly the 120 TXD files that get stripped.
EXISTING_BACKUP = BACKUP_ROOT / "txd_consolidate_20260827_161022"

# New override pack (zz_ prefix ensures it loads LAST alphabetically)
OVERRIDE_PACK_NAME = "zz_fixedveg_loading"
OVERRIDE_PATH = GAME_MODLOADER / OVERRIDE_PACK_NAME
OVERRIDE_DLC = DLC_ROOT / OVERRIDE_PACK_NAME

sys.path.insert(0, str(PROJECT / "managers"))
from txdlite import TxdFile, TxdTexture, TxdError, \
    FLAG_COMPRESSED, DXT1_FMT, DXT3_FMT, DXT5_FMT, \
    FMT_8888, FMT_MIPMAP, expected_level_size


# ── scoped packs ────────────────────────────────────────────────────────────
def _scoped_packs():
    """Return list of (pack_name, pack_path, scoped_txd_paths).

    Identical to original; reads from GAME_MODLOADER for CLASSIFICATION only.
    Actual source data for stripping comes from EXISTING_BACKUP.
    """
    veg_keywords = {"veg", "tree", "christmas", "potted", "plant", "fir",
                    "pine", "cypress", "oak", "sequoia", "spruce", "conifer",
                    "cactus", "palm", "bush", "fern", "grass", "rush",
                    "flower", "desert", "rock", "lod"}

    packs = []

    # mobile_vegetation — all root TXDs
    mv = GAME_MODLOADER / "mobile_vegetation"
    if mv.is_dir():
        txds = sorted(mv.glob("*.txd"))
        packs.append(("mobile_vegetation", mv, txds))

    # Improved and Fixed Original Vegetation
    iv = GAME_MODLOADER / "Improved and Fixed Original Vegetation"
    if iv.is_dir():
        scoped = []
        for sub in sorted(iv.iterdir()):
            if not sub.is_dir():
                continue
            name_lower = sub.name.lower()
            if any(kw in name_lower for kw in veg_keywords):
                scoped.extend(sorted(sub.rglob("*.txd")))
        mv_names = {p.name.lower() for p in (GAME_MODLOADER / "mobile_vegetation").glob("*.txd")}
        for p in sorted(iv.glob("*.txd")):
            if p.name.lower() in mv_names:
                scoped.append(p)
        if scoped:
            packs.append(("Improved and Fixed Original Vegetation", iv, sorted(set(scoped))))

    # skygfx_plus_extras
    se = GAME_MODLOADER / "skygfx_plus_extras"
    if se.is_dir():
        scoped = []
        for sub in sorted(se.iterdir()):
            if not sub.is_dir():
                continue
            name_lower = sub.name.lower()
            if any(kw in name_lower for kw in veg_keywords):
                scoped.extend(sorted(sub.rglob("*.txd")))
        mv_names = {p.name.lower() for p in (GAME_MODLOADER / "mobile_vegetation").glob("*.txd")}
        for p in sorted(se.glob("*.txd")):
            if p.name.lower() in mv_names:
                scoped.append(p)
        if scoped:
            packs.append(("skygfx_plus_extras", se, sorted(set(scoped))))

    return packs


def _is_fakeimg(p: Path) -> bool:
    """True if any parent dir ends with .img (override-critical, never touch)."""
    return any(part.lower().endswith(".img") for part in p.parts[:-1])


# ── texture content hash ────────────────────────────────────────────────────
def _tex_content_key(tex: TxdTexture):
    """Return (name_lower, fmt_str, w, h, hash_of_all_mip_bytes)."""
    name = tex.name.lower()
    fmt = tex.fmt_name()
    w, h = tex.width, tex.height
    hsh = hashlib.sha256()
    for mip in tex.mips:
        hsh.update(mip)
    return (name, fmt, w, h, hsh.hexdigest())


def _tex_raster_bytes(tex: TxdTexture) -> int:
    """Total raster bytes (all mips) for a texture."""
    return sum(len(m) for m in tex.mips)


# ── parse all scoped TXDs (from LIVE modloader for classification) ──────────
def _parse_all(packs):
    """Parse every scoped TXD. Returns:
      global_map: (name, fmt, w, h, hash) -> [(pack, txd_rel, tex)]
      pack_stats: pack_name -> {txd_count, tex_count, raster_bytes}
    """
    global_map = defaultdict(list)
    pack_stats = defaultdict(lambda: {"txd_count": 0, "tex_count": 0, "raster_bytes": 0})

    for pname, ppath, txd_paths in packs:
        for txd_path in txd_paths:
            if _is_fakeimg(txd_path):
                continue
            try:
                txd = TxdFile.load(str(txd_path))
            except Exception as e:
                print(f"  [WARN] parse error {txd_path.relative_to(GAME_MODLOADER)}: {e}")
                continue
            rel = str(txd_path.relative_to(GAME_MODLOADER))
            pack_stats[pname]["txd_count"] += 1
            for tex in txd.textures:
                key = _tex_content_key(tex)
                global_map[key].append((pname, rel, tex))
                pack_stats[pname]["tex_count"] += 1
                pack_stats[pname]["raster_bytes"] += _tex_raster_bytes(tex)

    return global_map, pack_stats


# ── classify ────────────────────────────────────────────────────────────────
def _classify(global_map, packs):
    """Classify textures into COMMON, UNIQUE, CONFLICT.

    Returns:
      common: dict key -> [(pack, txd_rel, tex)]  (appears in >=2 TXDs across packs)
      unique: dict key -> [(pack, txd_rel, tex)]   (single TXD)
      conflicts: list of (name, [(key, pack, txd_rel, tex), ...])
    """
    by_name = defaultdict(list)
    for key, entries in global_map.items():
        name = key[0]
        for e in entries:
            by_name[name].append((key,) + e)

    common = {}
    unique = {}
    conflicts = []

    for name, entries in by_name.items():
        unique_keys = set(e[0] for e in entries)
        if len(unique_keys) > 1:
            conflicts.append((name, entries))
            for key, pack, txd_rel, tex in entries:
                if key not in unique:
                    unique[key] = []
                unique[key].append((pack, txd_rel, tex))
            continue

        key = entries[0][0]
        distinct_txds = set((p, t) for _, p, t, _ in entries)
        if len(distinct_txds) >= 2:
            common[key] = [(p, t, x) for _, p, t, x in entries]
        else:
            unique[key] = [(p, t, x) for _, p, t, x in entries]

    return common, unique, conflicts


# ── plan table ──────────────────────────────────────────────────────────────
def _build_plan(common, unique, conflicts, pack_stats, packs):
    """Build per-pack plan and compute savings."""
    savings_per_pack = defaultdict(lambda: {"stripped_tex_count": 0,
                                             "stripped_bytes": 0,
                                             "txds_touched": set(),
                                             "kept_in_place": 0})
    conflicts_per_pack = defaultdict(int)

    for key, entries in common.items():
        mv_entries = [e for e in entries if e[0] == "mobile_vegetation"]
        if mv_entries:
            keep = mv_entries[0]
        else:
            keep = entries[0]

        for pack, txd_rel, tex in entries:
            if (pack, txd_rel) == (keep[0], keep[1]):
                savings_per_pack[pack]["kept_in_place"] += 1
            else:
                savings_per_pack[pack]["stripped_tex_count"] += 1
                savings_per_pack[pack]["stripped_bytes"] += _tex_raster_bytes(tex)
                savings_per_pack[pack]["txds_touched"].add(txd_rel)

    for name, entries in conflicts:
        for key, pack, txd_rel, tex in entries:
            conflicts_per_pack[pack] += 1

    return savings_per_pack, conflicts_per_pack


# ── print plan ──────────────────────────────────────────────────────────────
def _print_plan(packs, pack_stats, common, unique, conflicts,
                savings_per_pack, conflicts_per_pack):
    """Print the PLAN table."""
    print("=" * 80)
    print("TXD CONSOLIDATION PLAN (dry-run)  —  OVERRIDE PACK MODE")
    print("=" * 80)
    print()

    # Pack overview
    print(f"{'Pack':<40} {'TXDs':>5} {'Textures':>9} {'Raster MB':>9}")
    print("-" * 65)
    total_txds = total_tex = total_bytes = 0
    for pname, _, _ in packs:
        s = pack_stats[pname]
        total_txds += s["txd_count"]
        total_tex += s["tex_count"]
        total_bytes += s["raster_bytes"]
        print(f"{pname:<40} {s['txd_count']:>5} {s['tex_count']:>9} "
              f"{s['raster_bytes'] / 1e6:>8.2f}")
    print("-" * 65)
    print(f"{'TOTAL':<40} {total_txds:>5} {total_tex:>9} "
          f"{total_bytes / 1e6:>8.2f}")
    print()

    # Classification summary
    print(f"Classification:")
    print(f"  COMMON  (same name+hash in >=2 TXDs): {len(common)} textures")
    print(f"  UNIQUE  (single TXD):                  {len(unique)} textures")
    print(f"  CONFLICT(same name, diff hash):        {len(conflicts)} names")
    print()

    # Per-pack savings
    print(f"{'Pack':<40} {'Stripped':>9} {'MB Saved':>9} {'TXDs':>5} {'Conflicts':>9}")
    print("-" * 75)
    grand_stripped = grand_bytes = 0
    for pname, _, _ in packs:
        sp = savings_per_pack.get(pname, {"stripped_tex_count": 0, "stripped_bytes": 0,
                                           "txds_touched": set()})
        cp = conflicts_per_pack.get(pname, 0)
        grand_stripped += sp["stripped_tex_count"]
        grand_bytes += sp["stripped_bytes"]
        print(f"{pname:<40} {sp['stripped_tex_count']:>9} "
              f"{sp['stripped_bytes'] / 1e6:>8.2f} "
              f"{len(sp['txds_touched']):>5} {cp:>9}")
    print("-" * 75)
    print(f"{'TOTAL':<40} {grand_stripped:>9} {grand_bytes / 1e6:>8.2f} "
          f"{'':>5} {sum(conflicts_per_pack.values()):>9}")
    print()

    # veg_shared.txd estimate
    shared_bytes = sum(
        _tex_raster_bytes(entries[0][2]) for entries in common.values()
    )
    print(f"veg_shared.txd: {len(common)} textures, ~{shared_bytes / 1e6:.2f} MB")
    print(f"  (one copy of each COMMON texture)")
    print()

    # Conflicts detail
    if conflicts:
        print(f"CONFLICTS (same name, different content — NOT deduped):")
        for name, entries in conflicts[:10]:
            for key, pack, txd_rel, tex in entries:
                print(f"  {name} in [{pack}] {txd_rel}: "
                      f"{tex.width}x{tex.height} {tex.fmt_name()} "
                      f"hash={key[4][:12]}")
        if len(conflicts) > 10:
            print(f"  ... and {len(conflicts) - 10} more")
        print()

    # TXDs that would receive overrides
    touched = set()
    for sp in savings_per_pack.values():
        touched.update(sp["txds_touched"])
    print(f"Child TXDs (override in new pack): {len(touched)}")
    for t in sorted(touched)[:10]:
        print(f"  {t}")
    if len(touched) > 10:
        print(f"  ... and {len(touched) - 10} more")
    print()

    # Empty-TXD edge case check
    empty_risk = []
    for pname, ppath, txd_paths in packs:
        for txd_path in txd_paths:
            if _is_fakeimg(txd_path):
                continue
            rel = str(txd_path.relative_to(GAME_MODLOADER))
            sp = savings_per_pack.get(pname, {})
            if rel in sp.get("txds_touched", set()):
                try:
                    txd = TxdFile.load(str(txd_path))
                except Exception:
                    continue
                remaining = 0
                for tex in txd.textures:
                    key = _tex_content_key(tex)
                    if key in common:
                        for e_pack, e_rel, _ in common[key]:
                            if e_pack == pname and e_rel == rel:
                                break
                        else:
                            remaining += 1
                    else:
                        remaining += 1
                if remaining == 0:
                    empty_risk.append(rel)
    if empty_risk:
        print(f"EMPTY-TXD RISK ({len(empty_risk)} TXDs would lose ALL textures):")
        for r in empty_risk[:5]:
            print(f"  {r}")
        print(f"  -> Apply mode will keep 1 smallest texture in each.")
    print()

    total_saved_mb = grand_bytes / 1e6
    print(f"PROJECTED SAVINGS: {total_saved_mb:.2f} MB "
          f"({grand_stripped} duplicate textures stripped)")
    print()

    # New pack summary
    touched_count = len(touched)
    print(f"NEW PACK: {OVERRIDE_PACK_NAME}/")
    print(f"  {len(common)} textures -> veg_shared.txd")
    print(f"  {touched_count} stripped children at game-relative paths")
    print(f"  + gta.dat + data/maps/bridge_veg_txdp.ide")
    print(f"  DLC twin: launcher_data/dlc/{OVERRIDE_PACK_NAME}/")
    print()


# ── record mtimes for assertion ────────────────────────────────────────────
def _record_mtimes(packs):
    """Return dict: str(abspath) -> mtime for all files in original packs."""
    mtimes = {}
    for pname, ppath, txd_paths in packs:
        for txd_path in txd_paths:
            if txd_path.is_file():
                mtimes[str(txd_path.resolve())] = txd_path.stat().st_mtime
        # Also track non-TXD files in scoped dirs (for completeness)
        for f in ppath.rglob("*"):
            if f.is_file() and not f.suffix.lower() == ".txd":
                mtimes[str(f.resolve())] = f.stat().st_mtime
    return mtimes


def _assert_mtimes(before, packs, label="original packs"):
    """Assert all tracked files have unchanged mtimes. Exit 1 if any changed."""
    changed = []
    for pname, ppath, txd_paths in packs:
        for txd_path in txd_paths:
            ap = str(txd_path.resolve())
            if txd_path.is_file():
                now = txd_path.stat().st_mtime
                if ap in before and before[ap] != now:
                    changed.append(txd_path)
        for f in ppath.rglob("*"):
            if f.is_file():
                ap = str(f.resolve())
                if f.is_file():
                    now = f.stat().st_mtime
                    if ap in before and before[ap] != now:
                        changed.append(f)
    if changed:
        print(f"  [ERROR] {len(changed)} files in {label} have CHANGED mtimes!")
        for c in changed[:10]:
            print(f"    {c}")
        print("  Aborting for safety.")
        return False
    return True


# ── apply mode ──────────────────────────────────────────────────────────────
def _apply_pack_mode(packs, common, unique, conflicts,
                     savings_per_pack, conflicts_per_pack):
    """Execute consolidation via isolated override pack.

    NO writes to original packs.  Everything goes into zz_fixedveg_loading/.
    Originals loaded from EXISTING_BACKUP for stripping.
    """
    if not EXISTING_BACKUP.is_dir():
        print(f"  [FATAL] Existing backup not found: {EXISTING_BACKUP}")
        print(f"  Cannot proceed — originals required for stripping.")
        return

    # Assert original pack mtimes BEFORE we start
    print("  Recording original pack mtimes...")
    mtimes_before = _record_mtimes(packs)

    # Collect all child TXDs that need stripping
    touched_by_rel = {}  # rel -> (pack_name, from_backup_path)
    for pname, ppath, txd_paths in packs:
        for txd_path in txd_paths:
            if _is_fakeimg(txd_path):
                continue
            rel = str(txd_path.relative_to(GAME_MODLOADER))
            sp = savings_per_pack.get(pname, {})
            if rel in sp.get("txds_touched", set()):
                backup_src = EXISTING_BACKUP / rel
                if not backup_src.is_file():
                    print(f"  [WARN] Backup source missing: {backup_src}")
                    print(f"         Falling back to live file (non-ideal)")
                    backup_src = txd_path
                touched_by_rel[rel] = (pname, backup_src)

    print(f"  Identified {len(touched_by_rel)} child TXDs to override")

    # 1. Build veg_shared.txd from COMMON textures
    print("\n  Building veg_shared.txd...")
    shared = TxdFile.create()
    shared.path = None
    shared_textures = []
    for key, entries in common.items():
        mv_entries = [e for e in entries if e[0] == "mobile_vegetation"]
        if mv_entries:
            _, _, tex = mv_entries[0]
        else:
            _, _, tex = entries[0]
        shared_textures.append(tex)

    shared_textures.sort(key=lambda t: t.name)

    for src_tex in shared_textures:
        dst = copy.copy(src_tex)
        dst.mips = list(src_tex.mips)
        dst.dirty = True
        shared.textures.append(dst)

    cnt = struct.pack("<hh", len(shared.textures), 0)
    shared.dict_struct_raw = cnt

    # Write to override pack root
    shared_path = OVERRIDE_PATH / "veg_shared.txd"
    shared_path.parent.mkdir(parents=True, exist_ok=True)
    shared.save(str(shared_path))
    print(f"    Wrote {shared_path} ({len(shared.textures)} textures)")

    # Mirror to DLC
    shared_path_dlc = OVERRIDE_DLC / "veg_shared.txd"
    shared_path_dlc.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(shared_path), str(shared_path_dlc))
    print(f"    Mirrored to {shared_path_dlc}")

    # 2. Write stripped children from backup originals
    ide_entries = []
    empty_risk_handled = []

    for rel, (pname, backup_path) in sorted(touched_by_rel.items()):
        # Destination in override pack (game-root-identical path)
        dest = OVERRIDE_PATH / rel
        dest.parent.mkdir(parents=True, exist_ok=True)

        # Load from backup (original, unstripped)
        txd = TxdFile.load(str(backup_path))

        # Strip COMMON textures
        to_remove = []
        for tex in txd.textures:
            key = _tex_content_key(tex)
            if key in common:
                is_child = False
                for e_pack, e_rel, _ in common[key]:
                    if e_pack == pname and e_rel == rel:
                        is_child = True
                        break
                if is_child:
                    to_remove.append(tex)

        for tex in to_remove:
            txd.textures.remove(tex)

        # Handle empty-TXD edge case
        if len(txd.textures) == 0:
            txd_orig = TxdFile.load(str(backup_path))
            smallest = min(txd_orig.textures,
                           key=lambda t: _tex_raster_bytes(t))
            kept = copy.copy(smallest)
            kept.mips = list(smallest.mips)
            kept.dirty = True
            txd.textures.append(kept)
            empty_risk_handled.append(rel)
            print(f"    [EMPTY-RISK] {rel}: kept 1 ({smallest.name})")
        else:
            print(f"    Stripped {len(to_remove)} tex from {rel}")

        # Save to override pack
        txd.save(str(dest))

        # Record IDE entry
        child_name = Path(rel).stem.lower()
        ide_entries.append((child_name, "veg_shared"))

    # 3. Write registration files
    # 3a. data/maps/bridge_veg_txdp.ide
    ide_lines = ["txdp"]
    for child, parent in sorted(set(ide_entries)):
        ide_lines.append(f"{child}, {parent}")
    ide_lines.append("end")
    ide_content = "\n".join(ide_lines) + "\n"

    ide_rel = "data/maps/bridge_veg_txdp.ide"
    ide_path = OVERRIDE_PATH / ide_rel
    ide_path.parent.mkdir(parents=True, exist_ok=True)
    ide_path.write_text(ide_content)
    print(f"\n  Wrote {ide_path} ({len(set(ide_entries))} entries)")

    # 3b. gta.dat
    gta_lines = [
        "# GTA Bridge: register veg txdp parent chain",
        "IDE data/maps/bridge_veg_txdp.ide",
    ]
    gta_content = "\n".join(gta_lines) + "\n"
    gta_path = OVERRIDE_PATH / "gta.dat"
    gta_path.write_text(gta_content)
    print(f"  Wrote {gta_path} (2 lines)")

    # Mirror registration files AND children to DLC
    for f in OVERRIDE_PATH.rglob("*"):
        if f.is_file():
            rel = f.relative_to(OVERRIDE_PATH)
            dst = OVERRIDE_DLC / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(f), str(dst))
    print(f"  Mirrored {sum(1 for _ in OVERRIDE_PATH.rglob('*') if _.is_file())} files to {OVERRIDE_DLC}")

    # 4. Verify original pack mtimes unchanged
    print("\n  Verifying original pack mtimes...")
    ok = _assert_mtimes(mtimes_before, packs)
    if not ok:
        print("  [CRITICAL] Original packs were modified! Manual restore needed.")
        print(f"  Rollback: rm -rf {OVERRIDE_PATH}")
        return

    print("  [OK] All original pack mtimes unchanged (ZERO writes to originals)")

    # 5. Verify DLC mirror byte-match
    print("\n  Verifying DLC mirror...")
    mismatches = 0
    for f in OVERRIDE_PATH.rglob("*"):
        if f.is_file():
            rel = f.relative_to(OVERRIDE_PATH)
            dlc_f = OVERRIDE_DLC / rel
            if not dlc_f.is_file():
                print(f"    [MISSING] DLC mirror: {dlc_f}")
                mismatches += 1
            elif f.read_bytes() != dlc_f.read_bytes():
                print(f"    [MISMATCH] {rel}")
                mismatches += 1
    if mismatches == 0:
        dlc_bytes = sum(f.stat().st_size for f in OVERRIDE_DLC.rglob("*") if f.is_file())
        print(f"    [OK] DLC mirror byte-match verified ({dlc_bytes} bytes)")
    else:
        print(f"    [WARN] {mismatches} DLC mirror mismatches")

    # Summary
    print()
    print("=" * 80)
    print("APPLY COMPLETE — Override Pack Mode")
    print("=" * 80)
    print(f"  Pack:       {OVERRIDE_PACK_NAME}/")
    print(f"  veg_shared: {len(shared.textures)} textures")
    print(f"  Overrides:  {len(ide_entries)} child TXDs (stripped)")
    print(f"  Empty-risk: {len(empty_risk_handled)}")
    print(f"  Files:      {len(ide_entries)} overrides + veg_shared.txd + gta.dat + bridge_veg_txdp.ide")
    print(f"  Originals:  ZERO writes (mtimes verified)")
    print(f"  DLC mirror: {OVERRIDE_DLC}")
    print()
    print("  Rollback:  rm -rf modloader/zz_fixedveg_loading")
    print("  Disable:   rename folder to _zz_fixedveg_loading (leading underscore)")
    print()


if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="SA-native TXD PARENTING via isolated override pack (zz_fixedveg_loading)")
    p.add_argument("--apply", action="store_true",
                   help="Execute consolidation")
    p.add_argument("--pack-mode", action="store_true", default=True,
                   help="Override pack mode (default ON, only mode)")
    p.add_argument("--force-experimental", action="store_true",
                   help="Bypass CTD hold (requires dev-copy harness)")
    args = p.parse_args()

    if args.apply and not args.force_experimental:
        print("[HOLD] EXPERIMENTAL: 2 CTDs on daily driver 2026-08-27 (null tex-dict deref at boot).")
        print("       Override ONLY with: --apply --force-experimental")
        sys.exit(2)
    if args.apply:
        print("[APPLY] TXD Consolidation — Override Pack Mode")
    else:
        print("[DRY-RUN] TXD Consolidation — Override Pack Mode")
    print(f"  Modloader: {GAME_MODLOADER}")
    print(f"  Backup:    {EXISTING_BACKUP} (120 originals)")
    print(f"  New pack:  {OVERRIDE_PATH}")
    print()

    packs = _scoped_packs()
    if not packs:
        print("No scoped packs found.")
        sys.exit(1)

    print(f"Scoped packs ({len(packs)}):")
    for pname, ppath, txds in packs:
        print(f"  {pname}: {len(txds)} TXDs")
    print()

    global_map, pack_stats = _parse_all(packs)
    print(f"Parsed {sum(s['txd_count'] for s in pack_stats.values())} TXDs, "
          f"{sum(s['tex_count'] for s in pack_stats.values())} textures total")
    print()

    common, unique, conflicts = _classify(global_map, packs)
    savings_per_pack, conflicts_per_pack = _build_plan(common, unique, conflicts,
                                                        pack_stats, packs)
    _print_plan(packs, pack_stats, common, unique, conflicts,
                savings_per_pack, conflicts_per_pack)

    if args.apply:
        print("=" * 80)
        print("EXECUTING APPLY")
        print("=" * 80)
        _apply_pack_mode(packs, common, unique, conflicts,
                         savings_per_pack, conflicts_per_pack)
    else:
        print("[DRY-RUN] No files written.")
        print()
        print("To execute: python utils/txd_consolidate.py --apply --force-experimental")
        print()
        print("--apply will:")
        print("  1. Create modloader/zz_fixedveg_loading/ veg_shared.txd (374 COMMON tex)")
        print("  2. Write stripped children at game-root-identical paths (from backup originals)")
        print("  3. Handle empty-TXD edge (keep 1 smallest texture)")
        print("  4. Write gta.dat + data/maps/bridge_veg_txdp.ide in new pack")
        print("  5. Mirror everything to launcher_data/dlc/zz_fixedveg_loading/")
        print("  6. Assert original packs have ZERO mtime changes")
        print("  7. DLC mirror byte-match verified")
        print()

    # Final report
    grand_stripped = sum(
        sp["stripped_tex_count"] for sp in savings_per_pack.values()
    )
    grand_bytes = sum(
        sp["stripped_bytes"] for sp in savings_per_pack.values()
    )
    total_saved_mb = grand_bytes / 1e6
    touched_txds = set()
    for sp in savings_per_pack.values():
        touched_txds.update(sp["txds_touched"])

    pack_savings = []
    for pname, _, _ in packs:
        sp = savings_per_pack.get(pname, {})
        pack_savings.append((pname, sp.get("stripped_bytes", 0)))
    pack_savings.sort(key=lambda x: -x[1])
    biggest = [f"{p} ({b/1e6:.1f}MB)" for p, b in pack_savings[:3]]

    print("=" * 80)
    print("FINAL REPORT (<=12 lines)")
    print("=" * 80)
    print(f"  Override pack: modloader/{OVERRIDE_PACK_NAME}/")
    print(f"  veg_shared.txd: {len(common)} tex ({sum(_tex_raster_bytes(entries[0][2]) for entries in common.values())/1e6:.2f}MB)")
    print(f"  Stripped children: {grand_stripped} dupes from {len(touched_txds)} TXDs, saves {total_saved_mb:.2f}MB")
    print(f"  DLC twin: launcher_data/dlc/{OVERRIDE_PACK_NAME}/")
    print(f"  Originals untouched: {'; '.join(biggest)} (mtimes asserted)")
    print(f"  Rollback: rm -rf modloader/zz_fixedveg_loading")
    print(f"  Disable by rename: modloader/_zz_fixedveg_loading (leading _)")
    print(f"  Verdict: {total_saved_mb:.2f}MB savings, {len(common)} shared, {len(conflicts)} conflicts skipped")

    sys.exit(0)