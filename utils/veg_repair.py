#!/usr/bin/env python3
"""veg_repair.py — Repair damaged vegetation TXD mips in modloader packs.

Algorithm:
  1. Enumerate enabled veg-related modloader packs (mobile_vegetation,
     skygfx_plus_extras, and any pack whose name contains Vegetation/vegetation/veg).
  2. For each .txd file:
     a. If byte-identical copy exists under launcher_data/dlc/<pack>/ → healthy, skip.
     b. Else if exists in dlc but DIFFERS → DAMAGED-BY-US: backup, copy dlc version over.
     c. Else (no dlc counterpart) → SCAN with txdlite: for each texture run
        mip_issues(strict). If broken AND base level intact AND fmt not DXT3 →
        backup then REBUILD mips via _mip_chain + encode_replace + save.
        If DXT3 or base damaged → list MANUAL-REVIEW (do NOT touch).
  3. Re-scan every touched file post-fix: must report 0 issues, else revert from
     backup and count as FAILED.
  4. Print summary table.

Usage:
  python utils/veg_repair.py --apply    # execute repairs
  python utils/veg_repair.py --dry-run  # preview only (default)
"""
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

# ── paths ──────────────────────────────────────────────────────────────────
GAME_MODLOADER = Path("E:/games/gtasa_skygfx_plus/modloader")
PROJECT = Path(__file__).resolve().parent.parent
DLC_ROOT = PROJECT / "launcher_data" / "dlc"
BACKUP_ROOT = PROJECT / "launcher_data" / "backups" / "veg_striped_restore_20260827"

# txdlite import
sys.path.insert(0, str(PROJECT / "managers"))
from txdlite import TxdFile, mip_issues, fix_texture_mips, encode_replace, decode_mip, FLAG_COMPRESSED, DXT3_FMT


# ── helpers ────────────────────────────────────────────────────────────────
def _is_fakeimg(p: Path) -> bool:
    """True if any parent dir ends with .img (override-critical, never touch)."""
    return any(part.lower().endswith(".img") for part in p.parts[:-1])


def _veg_packs() -> list[tuple[str, Path]]:
    """Return (pack_name, pack_path) for all veg-related modloader packs."""
    veg_keywords = {"vegetation", "veg", "mobile_vegetation", "skygfx_plus_extras"}
    packs = []
    for entry in sorted(GAME_MODLOADER.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        name_lower = entry.name.lower().replace(" ", "_")
        if any(kw in name_lower for kw in veg_keywords):
            packs.append((entry.name, entry))
    return packs


def _dlc_path(pack_name: str) -> Path | None:
    """Return DLC path for a pack, or None if not curated."""
    # Try exact match first
    candidate = DLC_ROOT / pack_name
    if candidate.is_dir():
        return candidate
    # Try normalized (lowercase, underscores)
    norm = pack_name.lower().replace(" ", "_")
    candidate = DLC_ROOT / norm
    if candidate.is_dir():
        return candidate
    return None


def _backup_file(src: Path, rel: Path) -> Path:
    """Copy src to backup dir preserving relative path. Returns backup path."""
    dst = BACKUP_ROOT / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(src), str(dst))
    return dst


def _restore_from_backup(rel: Path) -> None:
    """Restore file from backup (used on post-fix failure)."""
    src = BACKUP_ROOT / rel
    dst = GAME_MODLOADER / rel
    if src.exists():
        shutil.copy2(str(src), str(dst))


def _scan_txd(txd_path: Path) -> list[dict]:
    """Scan a TXD file for mip issues. Returns list of issue dicts per texture."""
    try:
        txd = TxdFile.load(str(txd_path))
    except Exception as e:
        return [{"texture": "(parse_error)", "issues": [str(e)], "dxt3": False, "base_ok": False}]
    results = []
    for tex in txd.textures:
        issues = mip_issues(tex, strict=True)
        if issues:
            is_dxt3 = bool(tex.flags & FLAG_COMPRESSED) and tex.d3d_format == DXT3_FMT
            # Check base level integrity: must decode and have correct size
            from txdlite import expected_level_size
            w, h = max(1, tex.width), max(1, tex.height)
            exp = expected_level_size(w, h, tex)
            base_ok = len(tex.mips[0]) == exp if tex.mips else False
            results.append({
                "texture": tex.name,
                "issues": issues,
                "dxt3": is_dxt3,
                "base_ok": base_ok,
                "fmt": tex.fmt_name(),
            })
    return results


def _repair_txd(txd_path: Path) -> bool:
    """Repair mip issues in a TXD. Returns True on success.
    
    Uses encode_replace (full _mip_chain) for corrupt mips or missing mips,
    which generates the complete chain from the base level down to 1x1.
    """
    try:
        txd = TxdFile.load(str(txd_path))
    except Exception:
        return False
    changed = False
    for tex in txd.textures:
        issues = mip_issues(tex, strict=True)
        if not issues:
            continue
        is_dxt3 = bool(tex.flags & FLAG_COMPRESSED) and tex.d3d_format == DXT3_FMT
        if is_dxt3:
            continue  # skip DXT3 per hard rule
        # Check base level integrity
        from txdlite import expected_level_size
        w, h = max(1, tex.width), max(1, tex.height)
        exp = expected_level_size(w, h, tex)
        base_ok = len(tex.mips[0]) == exp if tex.mips else False
        if not base_ok:
            continue  # base damaged, skip
        try:
            # Use encode_replace which generates full _mip_chain via
            # Magic.TXD-parity mipGenLevelGenerator (each dim halves to 1).
            # This handles both "missing mips" and "level N corrupt" cases.
            img = decode_mip(tex, 0)
            encode_replace(tex, img)
            tex.dirty = True
            changed = True
        except Exception:
            continue
    if not changed:
        return False
    try:
        txd.save(str(txd_path))
    except Exception:
        return False
    return True


def _verify_txd(txd_path: Path) -> list[str]:
    """Verify a TXD has zero mip issues. Returns list of remaining issues."""
    try:
        txd = TxdFile.load(str(txd_path))
    except Exception as e:
        return [f"parse_error: {e}"]
    all_issues = []
    for tex in txd.textures:
        issues = mip_issues(tex, strict=True)
        if issues:
            all_issues.append(f"{tex.name}: {'; '.join(issues)}")
    return all_issues


# ── main ───────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Repair damaged vegetation TXD mips")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Preview only (default)")
    parser.add_argument("--apply", action="store_false", dest="dry_run",
                        help="Execute repairs")
    args = parser.parse_args()

    dry_run = args.dry_run
    print(f"{'[DRY-RUN]' if dry_run else '[APPLY]'} Vegetation TXD repair")
    print(f"  Modloader: {GAME_MODLOADER}")
    print(f"  DLC ground truth: {DLC_ROOT}")
    print(f"  Backups: {BACKUP_ROOT}")
    print()

    packs = _veg_packs()
    if not packs:
        print("No vegetation packs found.")
        return 1

    # ── enumerate all TXD files ────────────────────────────────────────────
    all_files: list[tuple[str, Path, Path]] = []  # (pack_name, rel_path, abs_path)
    for pack_name, pack_path in packs:
        for txd_path in sorted(pack_path.rglob("*.txd")):
            if _is_fakeimg(txd_path):
                continue  # skip override-critical IMG dirs
            rel = txd_path.relative_to(GAME_MODLOADER)
            all_files.append((pack_name, rel, txd_path))

    print(f"Found {len(all_files)} TXD files across {len(packs)} packs:")
    for pn, _ in packs:
        cnt = sum(1 for p, _, _ in all_files if p == pn)
        print(f"  {pn}: {cnt} files")
    print()

    # ── classify each file ─────────────────────────────────────────────────
    summary: dict[str, dict] = {}  # pack_name -> {scanned, restored, repaired, manual, failed}
    for pn, _ in packs:
        summary[pn] = {"scanned": 0, "restored": 0, "repaired": 0,
                       "manual": [], "failed": []}

    restored_files = []
    repaired_files = []
    manual_review = []
    failed_files = []

    for pack_name, rel, txd_path in all_files:
        summary[pack_name]["scanned"] += 1
        dlc_dir = _dlc_path(pack_name)
        dlc_file = dlc_dir / rel.relative_to(pack_name) if dlc_dir else None

        # Case A: byte-identical to DLC → healthy
        if dlc_file and dlc_file.exists():
            mod_bytes = txd_path.read_bytes()
            dlc_bytes = dlc_file.read_bytes()
            if mod_bytes == dlc_bytes:
                continue  # healthy

            # Case B: exists in DLC but differs → DAMAGED-BY-US
            if not dry_run:
                _backup_file(txd_path, rel)
                shutil.copy2(str(dlc_file), str(txd_path))
                # Verify: restored file must be byte-identical to DLC
                restored_bytes = txd_path.read_bytes()
                if restored_bytes != dlc_bytes:
                    _restore_from_backup(rel)
                    summary[pack_name]["failed"].append(str(rel))
                    failed_files.append((pack_name, str(rel), ["byte_mismatch_after_restore"]))
                else:
                    summary[pack_name]["restored"] += 1
                    restored_files.append((pack_name, str(rel)))
            else:
                summary[pack_name]["restored"] += 1
                restored_files.append((pack_name, str(rel)))
            continue

        # Case C: no DLC counterpart → scan and repair
        issues = _scan_txd(txd_path)
        has_broken = any(i["issues"] for i in issues)
        if not has_broken:
            continue  # healthy

        # Check if any texture is DXT3 or has damaged base
        can_repair = True
        for iss in issues:
            if iss["issues"]:
                if iss["dxt3"]:
                    can_repair = False
                    break
                if not iss["base_ok"]:
                    can_repair = False
                    break

        if not can_repair:
            # Manual review
            detail = "; ".join(f"{i['texture']}: {'; '.join(i['issues'])}" for i in issues if i["issues"])
            summary[pack_name]["manual"].append(f"{rel} [{detail}]")
            manual_review.append((pack_name, str(rel), detail))
            continue

        if dry_run:
            summary[pack_name]["repaired"] += 1
            repaired_files.append((pack_name, str(rel)))
            continue

        # Execute repair
        _backup_file(txd_path, rel)
        ok = _repair_txd(txd_path)
        if ok:
            remaining = _verify_txd(txd_path)
            if remaining:
                _restore_from_backup(rel)
                summary[pack_name]["failed"].append(str(rel))
                failed_files.append((pack_name, str(rel), remaining))
            else:
                summary[pack_name]["repaired"] += 1
                repaired_files.append((pack_name, str(rel)))
        else:
            _restore_from_backup(rel)
            summary[pack_name]["failed"].append(str(rel))
            failed_files.append((pack_name, str(rel), ["repair_failed"]))

    # ── print summary ──────────────────────────────────────────────────────
    print("=" * 72)
    print(f"{'Pack':<40} {'Scanned':>7} {'Restored':>8} {'Repaired':>8} {'Failed':>6}")
    print("-" * 72)
    grand_scanned = grand_restored = grand_repaired = grand_failed = 0
    for pn, _ in packs:
        s = summary[pn]
        grand_scanned += s["scanned"]
        grand_restored += s["restored"]
        grand_repaired += s["repaired"]
        grand_failed += len(s["failed"])
        print(f"{pn:<40} {s['scanned']:>7} {s['restored']:>8} {s['repaired']:>8} {len(s['failed']):>6}")
    print("-" * 72)
    print(f"{'TOTAL':<40} {grand_scanned:>7} {grand_restored:>8} {grand_repaired:>8} {grand_failed:>6}")
    print()

    if manual_review:
        print("MANUAL-REVIEW (not touched):")
        for pn, rel, detail in manual_review:
            print(f"  [{pn}] {rel}")
            print(f"    {detail}")
        print()

    if failed_files:
        print("FAILED (reverted from backup):")
        for pn, rel, issues in failed_files:
            print(f"  [{pn}] {rel}: {'; '.join(issues)}")
        print()

    if restored_files:
        print("RESTORED from DLC ground truth:")
        for pn, rel in restored_files[:5]:
            print(f"  [{pn}] {rel}")
        if len(restored_files) > 5:
            print(f"  ... and {len(restored_files) - 5} more")
        print()

    if repaired_files:
        print("REPAIRED (mip chain rebuilt):")
        for pn, rel in repaired_files[:5]:
            print(f"  [{pn}] {rel}")
        if len(repaired_files) > 5:
            print(f"  ... and {len(repaired_files) - 5} more")
        print()

    if dry_run:
        print("[DRY-RUN] No changes made. Run with --apply to execute.")
    else:
        print("[APPLY] Repairs complete. Files written directly to modloader — "
              "they are live immediately (no game restart needed for texture swap).")

    return 0 if not failed_files else 1


if __name__ == "__main__":
    sys.exit(main())
