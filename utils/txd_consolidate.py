#!/usr/bin/env python3
"""txd_consolidate.py — SA-native TXD PARENTING consolidation for vegetation.

Uses the vanilla `txdp` IDE mechanism (proven by txdcut.ide) to deduplicate
textures shared across modloader packs.  A single veg_shared.txd holds every
COMMON texture once; child TXDs are stripped of duplicates and reference the
parent via bridge_veg_txdp.ide.

Usage:
  python utils/txd_consolidate.py              # dry-run (plan only)
  python utils/txd_consolidate.py --apply       # execute (NOT this run)

Hard rules (SKILL.md):
  - NEVER write inside *.img dirs
  - NEVER rename modloader folders
  - NEVER delete backups
  - DLC + modloader must stay in sync after writes
  - No game-dir writes this run (dry-run only)
"""
import argparse
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

sys.path.insert(0, str(PROJECT / "managers"))
from txdlite import TxdFile, TxdTexture, TxdError, \
    FLAG_COMPRESSED, DXT1_FMT, DXT3_FMT, DXT5_FMT, \
    FMT_8888, FMT_MIPMAP, expected_level_size


# ── scoped packs ────────────────────────────────────────────────────────────
def _scoped_packs():
    """Return list of (pack_name, pack_path, scoped_txd_paths).

    Scope rules:
      - mobile_vegetation: ALL *.txd in pack root
      - Improved and Fixed Original Vegetation: subdirs whose name contains
        veg/tree/Christmas/Potted, plus any *.txd directly in pack root
        whose textures overlap with mobile_vegetation
      - skygfx_plus_extras: same subdir rule + overlapping root TXDs
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
        # Also check root-level TXDs that overlap with mobile_vegetation
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
    """Return (name_lower, fmt_str, w, h, hash_of_all_mip_bytes).

    Two textures with identical key are byte-identical content.
    """
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


# ── parse all scoped TXDs ──────────────────────────────────────────────────
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
      conflicts: list of (name, [(key, pack, txd_rel, tex), ...])  (same name, diff hash)
    """
    # Group by name first to detect conflicts
    by_name = defaultdict(list)  # name.lower() -> [(key, pack, txd_rel, tex)]
    for key, entries in global_map.items():
        name = key[0]
        for e in entries:
            by_name[name].append((key,) + e)

    common = {}
    unique = {}
    conflicts = []

    for name, entries in by_name.items():
        # Check for same-name-different-hash
        unique_keys = set(e[0] for e in entries)
        if len(unique_keys) > 1:
            # CONFLICT: same name, different content — keep all in place
            conflicts.append((name, entries))
            for key, pack, txd_rel, tex in entries:
                if key not in unique:
                    unique[key] = []
                unique[key].append((pack, txd_rel, tex))
            continue

        key = entries[0][0]
        # Count distinct TXDs (across packs)
        distinct_txds = set((p, t) for _, p, t, _ in entries)
        if len(distinct_txds) >= 2:
            common[key] = [(p, t, x) for _, p, t, x in entries]
        else:
            unique[key] = [(p, t, x) for _, p, t, x in entries]

    return common, unique, conflicts


# ── plan table ──────────────────────────────────────────────────────────────
def _build_plan(common, unique, conflicts, pack_stats, packs):
    """Build per-pack plan and compute savings."""
    # For each common texture, identify which TXDs would be stripped
    # (all but one copy — the one that goes into veg_shared.txd)
    # We keep the copy in mobile_vegetation if present, else the first pack.
    savings_per_pack = defaultdict(lambda: {"stripped_tex_count": 0,
                                             "stripped_bytes": 0,
                                             "txds_touched": set(),
                                             "kept_in_place": 0})
    conflicts_per_pack = defaultdict(int)

    for key, entries in common.items():
        # Prefer keeping the copy in mobile_vegetation
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

    # Conflicts: count per pack
    for name, entries in conflicts:
        for key, pack, txd_rel, tex in entries:
            conflicts_per_pack[pack] += 1

    return savings_per_pack, conflicts_per_pack


# ── print plan ──────────────────────────────────────────────────────────────
def _print_plan(packs, pack_stats, common, unique, conflicts,
                savings_per_pack, conflicts_per_pack):
    """Print the PLAN table."""
    print("=" * 80)
    print("TXD CONSOLIDATION PLAN (dry-run)")
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
    print(f"  (one copy of each COMMON texture, stored in mobile_vegetation/)")
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

    # TXDs that would be touched
    touched = set()
    for sp in savings_per_pack.values():
        touched.update(sp["txds_touched"])
    print(f"TXDs to be modified (stripped): {len(touched)}")
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
                # Count textures that would remain after stripping
                remaining = 0
                for tex in txd.textures:
                    key = _tex_content_key(tex)
                    if key in common:
                        # Check if this TXD is a "child" (would be stripped)
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

    # Savings verdict
    total_saved_mb = grand_bytes / 1e6
    print(f"PROJECTED SAVINGS: {total_saved_mb:.2f} MB "
          f"({grand_stripped} duplicate textures stripped)")
    print()


# ── apply mode (NOT run now) ────────────────────────────────────────────────
def _apply(packs, common, unique, conflicts, savings_per_pack, conflicts_per_pack):
    """Execute consolidation.  NOT called in dry-run mode."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = BACKUP_ROOT / f"txd_consolidate_{stamp}"
    print(f"Backups -> {backup_dir}")

    # 1. Build veg_shared.txd
    shared = TxdFile.create()
    shared.path = None
    # Collect one copy of each COMMON texture (prefer mobile_vegetation)
    shared_textures = []
    for key, entries in common.items():
        mv_entries = [e for e in entries if e[0] == "mobile_vegetation"]
        if mv_entries:
            _, _, tex = mv_entries[0]
        else:
            _, _, tex = entries[0]
        shared_textures.append(tex)

    # Sort by name for deterministic output
    shared_textures.sort(key=lambda t: t.name)

    # We need to deep-copy textures into the shared TXD
    import copy
    for src_tex in shared_textures:
        dst = copy.copy(src_tex)
        dst.mips = list(src_tex.mips)
        dst.dirty = True
        shared.textures.append(dst)

    # Patch dict struct with correct count
    cnt = struct.pack("<hh", len(shared.textures), 0)
    shared.dict_struct_raw = cnt

    # Write veg_shared.txd to mobile_vegetation
    shared_path_mv = GAME_MODLOADER / "mobile_vegetation" / "veg_shared.txd"
    shared.save(str(shared_path_mv))
    print(f"  Wrote {shared_path_mv} ({len(shared.textures)} textures)")

    # Mirror to DLC
    shared_path_dlc = DLC_ROOT / "mobile_vegetation" / "veg_shared.txd"
    shared_path_dlc.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(shared_path_mv), str(shared_path_dlc))
    print(f"  Mirrored to {shared_path_dlc}")

    # 2. Strip COMMON textures from child TXDs
    ide_entries = []  # (child_txd_name_lower, "veg_shared")
    empty_risk_handled = []

    for pname, ppath, txd_paths in packs:
        for txd_path in txd_paths:
            if _is_fakeimg(txd_path):
                continue
            rel = str(txd_path.relative_to(GAME_MODLOADER))
            sp = savings_per_pack.get(pname, {})
            if rel not in sp.get("txds_touched", set()):
                continue

            # Backup
            bak_dst = backup_dir / rel
            bak_dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(txd_path), str(bak_dst))

            # Load and strip
            txd = TxdFile.load(str(txd_path))
            to_remove = []
            for tex in txd.textures:
                key = _tex_content_key(tex)
                if key in common:
                    # Check if THIS TXD is a child for this key
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
                # Keep the smallest texture (by raster bytes)
                # Re-load from backup to get original textures
                txd_orig = TxdFile.load(str(bak_dst))
                smallest = min(txd_orig.textures,
                               key=lambda t: _tex_raster_bytes(t))
                # Copy it back
                import copy
                kept = copy.copy(smallest)
                kept.mips = list(smallest.mips)
                kept.dirty = True
                txd.textures.append(kept)
                empty_risk_handled.append(rel)
                print(f"  [EMPTY-RISK] {rel}: kept 1 smallest texture "
                       f"({smallest.name})")

            # Save
            txd.save(str(txd_path))
            print(f"  Stripped {len(to_remove)} textures from [{pname}] {rel}")

            # Record IDE entry
            child_name = Path(rel).stem.lower()
            ide_entries.append((child_name, "veg_shared"))

    # 3. Write registration files (pack-local, per ML docs)
    # 3a. data/maps/bridge_veg_txdp.ide — the txdp entries (deduplicated)
    ide_lines = ["txdp"]
    for child, parent in sorted(set(ide_entries)):
        ide_lines.append(f"{child}, {parent}")
    ide_lines.append("end")
    ide_content = "\n".join(ide_lines) + "\n"

    ide_rel = "data/maps/bridge_veg_txdp.ide"
    ide_path_mv = GAME_MODLOADER / "mobile_vegetation" / ide_rel
    ide_path_mv.parent.mkdir(parents=True, exist_ok=True)
    ide_path_mv.write_text(ide_content)
    print(f"  Wrote {ide_path_mv} ({len(ide_entries)} entries)")

    # 3b. gta.dat — pack-local merge file registering the IDE
    gta_lines = [
        "# GTA Bridge: register veg txdp parent chain",
        "IDE data/maps/bridge_veg_txdp.ide",
    ]
    gta_content = "\n".join(gta_lines) + "\n"
    gta_path_mv = GAME_MODLOADER / "mobile_vegetation" / "gta.dat"
    gta_path_mv.write_text(gta_content)
    print(f"  Wrote {gta_path_mv} (2 lines)")

    # Mirror registration files to DLC
    for rel in ["gta.dat", "data/maps/bridge_veg_txdp.ide"]:
        src = GAME_MODLOADER / "mobile_vegetation" / rel
        dst = DLC_ROOT / "mobile_vegetation" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dst))
        print(f"  Mirrored to {dst}")

    # Summary
    print()
    print(f"APPLY COMPLETE:")
    print(f"  veg_shared.txd: {len(shared.textures)} textures")
    print(f"  TXDs stripped:  {len(ide_entries)}")
    print(f"  Empty-risk handled: {len(empty_risk_handled)}")
    print(f"  Registration files: gta.dat, data/maps/bridge_veg_txdp.ide")
    print(f"  Backups: {backup_dir}")
    print()
    print("NOTE: gta.dat registers bridge_veg_txdp.ide via Mod Loader's")
    print("  pack-local merge mechanism.  veg_shared.txd at pack root is")
    print("  injected as virtual gta3.img entry (case-insensitive match).")
    print("  Verify on first boot that all child TXDs resolve their parent.")


# ── main ───────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="SA-native TXD PARENTING consolidation for vegetation")
    parser.add_argument("--apply", action="store_true",
                        help="Execute consolidation (NOT this run)")
    args = parser.parse_args()

    if args.apply:
        print("[APPLY] TXD Consolidation")
        print("  WARNING: This modifies game files.  Dry-run only this run.")
        print("  Use --apply only when explicitly instructed.\n")
        # Still print plan first, then show what would happen
    else:
        print("[DRY-RUN] TXD Consolidation")
    print(f"  Modloader: {GAME_MODLOADER}")
    print(f"  Backups:   {BACKUP_ROOT}")
    print()

    packs = _scoped_packs()
    if not packs:
        print("No scoped packs found.")
        return 1

    print(f"Scoped packs ({len(packs)}):")
    for pname, ppath, txds in packs:
        print(f"  {pname}: {len(txds)} TXDs")
    print()

    # Parse
    global_map, pack_stats = _parse_all(packs)
    print(f"Parsed {sum(s['txd_count'] for s in pack_stats.values())} TXDs, "
          f"{sum(s['tex_count'] for s in pack_stats.values())} textures total")
    print()

    # Classify
    common, unique, conflicts = _classify(global_map, packs)

    # Build plan
    savings_per_pack, conflicts_per_pack = _build_plan(common, unique, conflicts,
                                                        pack_stats, packs)

    # Print plan
    _print_plan(packs, pack_stats, common, unique, conflicts,
                savings_per_pack, conflicts_per_pack)

    # Apply mode
    if args.apply:
        print("=" * 80)
        print("EXECUTING APPLY")
        print("=" * 80)
        _apply(packs, common, unique, conflicts,
               savings_per_pack, conflicts_per_pack)
    else:
        print("[DRY-RUN] No files written.")
        print()
        print("To execute: python utils/txd_consolidate.py --apply")
        print()
        print("--apply will:")
        print("  1. Create veg_shared.txd in mobile_vegetation/ + DLC twin")
        print("  2. Strip COMMON textures from child TXDs (backup first)")
        print("  3. Handle empty-TXD edge (keep 1 smallest texture)")
        print("  4. Write gta.dat + data/maps/bridge_veg_txdp.ide in mobile_vegetation/ + DLC twins")
        print("  5. gta.dat registers the IDE via ML pack-local merge mechanism")
        print()

    # ── FINAL REPORT (<=14 lines) ──────────────────────────────────────────
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

    # Biggest packs by savings
    pack_savings = []
    for pname, _, _ in packs:
        sp = savings_per_pack.get(pname, {})
        pack_savings.append((pname, sp.get("stripped_bytes", 0)))
    pack_savings.sort(key=lambda x: -x[1])
    biggest = [f"{p} ({b/1e6:.1f}MB)" for p, b in pack_savings[:3]]

    print("=" * 80)
    print("FINAL REPORT (<=14 lines)")
    print("=" * 80)
    print(f"  Duplicates found: {grand_stripped} textures across "
          f"{len(touched_txds)} TXDs")
    print(f"  Projected savings: {total_saved_mb:.2f} MB")
    print(f"  veg_shared.txd: {len(common)} unique textures, "
          f"~{sum(_tex_raster_bytes(entries[0][2]) for entries in common.values()) / 1e6:.2f} MB")
    print(f"  Biggest packs: {', '.join(biggest)}")
    print(f"  Conflicts (same name, diff hash, kept in place): "
          f"{len(conflicts)} names")
    print(f"  File created: data/maps/bridge_veg_txdp.ide ({len(touched_txds)} entries)")
    print(f"  --apply will: backup each modified TXD; write veg_shared.txd; "
          f"strip children;")
    print(f"                handle empty-TXD edge (keep 1 smallest tex); "
          f"mirror to DLC twin;")
    print(f"                write gta.dat + data/maps/bridge_veg_txdp.ide "
          f"(ML pack-local merge)")
    print(f"  Risks: parent-chain depth=1 (SA native, OK per txdcut.ide); "
          f"empty-TXD edge handled;")
    print(f"         gta.dat merge + IDE registration unverified "
          f"(verify on first boot)")
    print(f"  Verdict: {total_saved_mb:.2f} MB savings — "
          f"{'WORTHWHILE' if total_saved_mb > 1 else 'MINOR'} "
          f"({len(common)} shared textures, {len(conflicts)} conflicts skipped)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
