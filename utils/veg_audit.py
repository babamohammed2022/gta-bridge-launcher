#!/usr/bin/env python3
"""veg_audit.py — Diagnose+Rescue for tree brown-blob issue.

Three read-only audits + one write rescue pass:

  1. DFF TEXTURE-REF AUDIT
     For every DFF in veg packs (skygfx_plus_extras tree/veg subdirs,
     Improved and Fixed Original Vegetation), collect referenced texture
     names via dff_texture_refs. Cross-check against all TXD texture names
     in the same pack tree.  Report DFFs with UNRESOLVED refs.

  2. IPL SANITY
     Parse IPL files in veg packs for entity lines referencing model names;
     verify each model exists as a .dff in that same pack.  Report orphans.

  3. DXT3 RESCUE MINING (read-only scan)
     For each of the 165 corrupt files identified by veg_repair.py (corrupt
     DXT3 mips, upstream damage in both modloader AND DLC), search ALL
     backup generations (txd_mipfix_*, veg_striped_restore_*) and any
     other pristine TXDs under launcher_data/ for byte-variants whose
     txdlite scan reports ZERO mip issues.

  4. DXT3 RESCUE WRITE (--apply flag only)
     For each corrupt file where a clean variant was found, copy that
     variant into modloader (backing up the current corrupt copy first to
     launcher_data/backups/dxt3_rescue_20260827/), then verify post-copy.
     Files with NO clean source remain untouched (no DXT3 regen).

Usage:
  python utils/veg_audit.py              # read-only audits 1-3
  python utils/veg_audit.py --apply       # read-only 1-2 + rescue write 3
"""
import argparse
import os
import shutil
import struct
import sys
from collections import defaultdict
from pathlib import Path

# ── paths ──────────────────────────────────────────────────────────────────
GAME_MODLOADER = Path("E:/games/gtasa_skygfx_plus/modloader")
PROJECT = Path(__file__).resolve().parent.parent
DLC_ROOT = PROJECT / "launcher_data" / "dlc"
BACKUP_ROOT = PROJECT / "launcher_data" / "backups"
RESCUE_BACKUP = BACKUP_ROOT / "dxt3_rescue_20260827"

sys.path.insert(0, str(PROJECT / "managers"))
from txdlite import TxdFile, mip_issues, DXT3_FMT, FLAG_COMPRESSED, expected_level_size
from mapdata import dff_texture_refs


# ── helpers ────────────────────────────────────────────────────────────────
def _veg_packs():
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


def _is_fakeimg(p):
    """True if any parent dir ends with .img (override-critical, never touch)."""
    return any(part.lower().endswith(".img") for part in p.parts[:-1])


def _gather_txd_texture_names(pack_path):
    """Return set of all texture names across all TXDs in a pack tree."""
    names = set()
    for p in sorted(pack_path.rglob("*.txd")):
        if _is_fakeimg(p):
            continue
        try:
            txd = TxdFile.load(str(p))
            names.update(t.name for t in txd.textures)
        except Exception:
            pass
    return names


# ── Task 1: DFF Texture-Ref Audit ──────────────────────────────────────────
def audit_dff_texture_refs(packs):
    """For each DFF in veg packs, check texture refs resolve in sibling TXDs."""
    print("=" * 72)
    print("TASK 1: DFF texture-reference audit")
    print("=" * 72)

    all_results = []
    bare_dffs = []
    pack_txd_names = {}

    for pname, ppath in packs:
        pname_lower = pname.lower().replace(" ", "_")
        is_veg_txd_only = (pname_lower == "mobile_vegetation")
        txd_names = _gather_txd_texture_names(ppath)
        pack_txd_names[pname] = txd_names

        if is_veg_txd_only:
            continue

        dff_count = 0
        unresolved_count = 0

        for dff_path in sorted(ppath.rglob("*.dff")):
            if _is_fakeimg(dff_path):
                continue
            dff_count += 1
            try:
                refs = dff_texture_refs(dff_path.read_bytes())
            except Exception:
                bare_dffs.append((pname, str(dff_path.relative_to(GAME_MODLOADER)),
                                  "(parse_error)"))
                continue
            if not refs:
                bare_dffs.append((pname, str(dff_path.relative_to(GAME_MODLOADER)),
                                  "zero_texture_refs"))
                continue

            missing = [r for r in refs if r not in txd_names]
            if missing:
                rel = str(dff_path.relative_to(GAME_MODLOADER))
                unresolved_count += 1
                all_results.append((pname, rel, len(missing),
                                    sorted(missing)[:5]))

        print(f"  [{pname}] {dff_count} DFFs scanned, "
              f"{unresolved_count} with unresolved refs in same-pack TXDs")

    # Cross-check against UNION of all veg TXDs
    all_veg_tex_names = set()
    for s in pack_txd_names.values():
        all_veg_tex_names.update(s)

    cross_missing = []
    for pname, ppath in packs:
        pname_lower = pname.lower().replace(" ", "_")
        if pname_lower == "mobile_vegetation":
            continue
        for dff_path in sorted(ppath.rglob("*.dff")):
            if _is_fakeimg(dff_path):
                continue
            try:
                refs = dff_texture_refs(dff_path.read_bytes())
            except Exception:
                continue
            if not refs:
                continue
            missing = [r for r in refs if r not in all_veg_tex_names]
            if missing:
                rel = str(dff_path.relative_to(GAME_MODLOADER))
                cross_missing.append((pname, rel, len(missing),
                                      sorted(missing)[:5]))

    print(f"\n  Cross-pack check (all veg TXDs combined):")
    if cross_missing:
        print(f"  {len(cross_missing)} DFFs have refs missing from ALL veg TXDs")
        for pname, rel, n, examples in cross_missing[:10]:
            print(f"    [{pname}] {rel}: {n} missing — {', '.join(examples)}")
        if len(cross_missing) > 10:
            print(f"    ... and {len(cross_missing) - 10} more")
    else:
        print(f"  ZERO — all DFF texture refs resolve across veg packs.")

    if bare_dffs:
        print(f"\n  [!] {len(bare_dffs)} DFFs have ZERO texture refs "
              f"(likely bad DFF or parse error):")
        for pname, rel, why in bare_dffs[:10]:
            print(f"    [{pname}] {rel} — {why}")
        if len(bare_dffs) > 10:
            print(f"    ... and {len(bare_dffs) - 10} more")

    return all_results, cross_missing, bare_dffs


# ── Task 2: IPL Sanity ────────────────────────────────────────────────────
def audit_ipl(packs):
    """Parse IPL files in veg packs; check model refs exist as DFFs."""
    print("\n" + "=" * 72)
    print("TASK 2: IPL entity-model sanity check")
    print("=" * 72)

    mismatches = []
    for pname, ppath in packs:
        dff_set = set()
        for dff in ppath.rglob("*.dff"):
            dff_set.add(dff.stem.lower())

        ipl_files = list(ppath.rglob("*.ipl"))
        if not ipl_files:
            print(f"  [{pname}] No IPL files — skipping")
            continue

        print(f"  [{pname}] {len(ipl_files)} IPL files, "
              f"{len(dff_set)} DFFs in pack")
        for ipl_path in sorted(ipl_files):
            # Binary IPLs (stream IPLs) start with binary chunks — skip them
            # Only parse text-format IPLs
            try:
                raw = ipl_path.read_bytes()
            except Exception:
                continue
            # Heuristic: if first 100 bytes contain mostly non-ASCII -> binary
            sample = raw[:min(len(raw), 200)]
            printable = sum(1 for b in sample if 32 <= b <= 126 or b in (9, 10, 13))
            if printable < len(sample) * 0.6:
                continue  # binary IPL, skip
            
            text = raw.decode("ascii", errors="replace")
            for lineno, line in enumerate(text.splitlines(), 1):
                raw_line = line.strip()
                if not raw_line or raw_line.startswith("#") or raw_line.startswith(";"):
                    continue
                # Entity lines: inst/pick keyword or bare CSV
                if raw_line.lower().startswith("inst") or raw_line.lower().startswith("pick"):
                    parts = raw_line.split(None, 1)
                    raw_line = parts[1] if len(parts) > 1 else ""
                parts = raw_line.split(",")
                if len(parts) < 2:
                    continue
                model_field = parts[1].strip().strip('"').strip("'").lower()
                if not model_field or model_field.isdigit() or len(model_field) < 2:
                    continue
                # Skip valid GTA model names that aren't DFFs (like .col, .txd refs)
                if not model_field.isalnum() and not all(c.isalnum() or c == '_' for c in model_field):
                    continue
                if model_field not in dff_set:
                    rel = str(ipl_path.relative_to(GAME_MODLOADER))
                    mismatches.append((pname, rel, lineno, model_field))

    if mismatches:
        print(f"\n  {len(mismatches)} IPL entity references to models "
              f"NOT found as DFFs in same pack:")
        unique_missing = defaultdict(int)
        for pname, rel, lineno, model in mismatches:
            unique_missing[model] += 1
        # Show top missing model names (most frequently referenced)
        top = sorted(unique_missing.items(), key=lambda x: -x[1])[:15]
        for model, count in top:
            print(f"    '{model}' — {count} references")
        print(f"  ({len(unique_missing)} unique missing model names total)")
    else:
        print(f"\n  ZERO mismatches — all IPL model refs resolve "
              f"to DFFs in same pack.")

    return mismatches


# ── Task 3: Corrupt file discovery ─────────────────────────────────────────
def _discover_corrupt_manual_files():
    """Run veg_repair-equivalent scan to find DXT3/damaged-base files.

    Returns dict: rel_path -> {pack, summary}
    """
    paks = _veg_packs()
    corruped = {}

    for pname, ppath in paks:
        for txd_path in sorted(ppath.rglob("*.txd")):
            if _is_fakeimg(txd_path):
                continue
            rel = str(txd_path.relative_to(GAME_MODLOADER))

            try:
                txd = TxdFile.load(str(txd_path))
            except Exception as e:
                corruped[rel] = {"pack": pname,
                                 "summary": f"(parse_error): {e}"}
                continue

            has_issues = False
            is_manual = False
            issues_detail = []
            for tex in txd.textures:
                m = mip_issues(tex, strict=True)
                if m:
                    has_issues = True
                    is_dxt3 = bool(tex.flags & FLAG_COMPRESSED) and \
                              tex.d3d_format == DXT3_FMT
                    w, h = max(1, tex.width), max(1, tex.height)
                    exp = expected_level_size(w, h, tex)
                    base_ok = len(tex.mips[0]) == exp if tex.mips else False
                    if is_dxt3 or not base_ok:
                        is_manual = True
                    issues_detail.append(f"{tex.name}: {'; '.join(m)}")

            if has_issues and is_manual:
                corruped[rel] = {"pack": pname,
                                 "summary": "; ".join(issues_detail)}

    return corruped


# ── Task 3b: DXT3 Rescue Mining ────────────────────────────────────────────
def rescue_mining_scan(corruped):
    """Search all backup dirs for clean variants of corrupt files.

    Returns:
      rescued: [(rel, pack, source_gen, source_path)]
      still_borked: [(rel, pack)]
    """
    print("\n" + "=" * 72)
    print("TASK 3: DXT3 Rescue Mining")
    print("=" * 72)
    print(f"  Scanning {len(corruped)} corrupt files against all backups...\n")

    # Build map: txd_basename.lower() -> list of (dir_name, full_path)
    candidate_map = defaultdict(list)
    for bak_dir in sorted(BACKUP_ROOT.iterdir()):
        if not bak_dir.is_dir():
            continue
        for p in bak_dir.rglob("*.txd"):
            candidate_map[p.name.lower()].append((bak_dir.name, p))

    rescued = []
    still_borked = []

    for rel, info in sorted(corruped.items()):
        fname = Path(rel).name.lower()
        candidates = candidate_map.get(fname, [])

        mod_path = GAME_MODLOADER / rel
        mod_bytes = mod_path.read_bytes() if mod_path.exists() else b""

        clean_found = None
        clean_source = None
        for src_name, src_path in candidates:
            try:
                src_bytes = src_path.read_bytes()
            except Exception:
                continue
            if src_bytes == mod_bytes:
                continue

            try:
                txd = TxdFile.load(str(src_path))
            except Exception:
                continue
            has_issues = False
            for tex in txd.textures:
                m = mip_issues(tex, strict=True)
                if m:
                    has_issues = True
                    break
            if not has_issues:
                clean_found = src_bytes
                clean_source = (src_name, src_path)
                break

        if clean_found is not None:
            rescued.append((rel, info["pack"], clean_source[0],
                           str(clean_source[1])))
        else:
            still_borked.append((rel, info["pack"]))

    # Print summary
    print(f"  RESCUED: {len(rescued)}/{len(corruped)}"
          f" have clean variants in backups")
    if rescued:
        src_counts = defaultdict(int)
        for _, _, sg, _ in rescued:
            src_counts[sg] += 1
        for gen, cnt in sorted(src_counts.items()):
            print(f"    from {gen}: {cnt} files")
        for rel, pack, src_gen, src_path in rescued[:3]:
            print(f"      {rel}  <-  {src_gen}")
        if len(rescued) > 3:
            print(f"      ... and {len(rescued) - 3} more")

    print(f"\n  STILL CORRUPT (no clean source): "
          f"{len(still_borked)}/{len(corruped)}")
    if still_borked:
        for rel, pack in still_borked[:5]:
            print(f"    [{pack}] {rel}")
        if len(still_borked) > 5:
            print(f"    ... and {len(still_borked) - 5} more")

    return rescued, still_borked


def rescue_write(rescued):
    """Write rescued clean variants into modloader with backup."""
    print("\n" + "=" * 72)
    print("TASK 4: DXT3 Rescue WRITE (--apply)")
    print("=" * 72)

    RESCUE_BACKUP.mkdir(parents=True, exist_ok=True)
    written = 0
    failed = 0

    for rel, pack, src_gen, src_path in rescued:
        mod_path = GAME_MODLOADER / rel
        if not mod_path.exists():
            print(f"  SKIP {rel}: not found in modloader")
            continue

        bak_dst = RESCUE_BACKUP / rel
        bak_dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(str(mod_path), str(bak_dst))
        except Exception as e:
            print(f"  FAIL backup {rel}: {e}")
            failed += 1
            continue

        try:
            shutil.copy2(src_path, str(mod_path))
        except Exception as e:
            print(f"  FAIL copy {rel}: {e}")
            failed += 1
            continue

        # Verify post-copy
        try:
            txd = TxdFile.load(str(mod_path))
            has_issues = any(mip_issues(t, strict=True) for t in txd.textures)
        except Exception as e:
            has_issues = True
            print(f"  FAIL verify (parse) {rel}: {e}")

        if has_issues:
            try:
                shutil.copy2(str(bak_dst), str(mod_path))
            except Exception:
                pass
            print(f"  FAIL verify (still corrupt) {rel} — reverted")
            failed += 1
        else:
            written += 1
            print(f"  OK   {rel}  (from {src_gen})")

    print(f"\n  RESULT: {written} rescued, {failed} failed")
    return written, failed


# ── main ───────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Vegetation diagnose+rescue")
    parser.add_argument("--apply", action="store_true",
                        help="Execute rescue write (phase 3); audits 1-2 read-only")
    args = parser.parse_args()

    print(f"{'[DIAGNOSE]' if not args.apply else '[DIAGNOSE+RESCUE]'} "
          f"Vegetation audit\n")
    print(f"  Modloader: {GAME_MODLOADER}")
    print(f"  Backups:   {BACKUP_ROOT}\n")

    packs = _veg_packs()
    if not packs:
        print("No vegetation packs found.")
        return 1

    print(f"Found {len(packs)} veg packs:")
    for pn, pp in packs:
        txd_count = len(list(pp.rglob("*.txd")))
        dff_count = len(list(pp.rglob("*.dff")))
        print(f"  {pn}: {txd_count} TXDs, {dff_count} DFFs")
    print()

    # ── Task 1: DFF Texture-Ref Audit ────
    dff_results, cross_missing, bare_dffs = audit_dff_texture_refs(packs)

    # ── Task 2: IPL Sanity ─────────────────
    ipl_mismatches = audit_ipl(packs)

    # ── Task 3: DXT3 Rescue Mining ────────
    print()
    corrupt = _discover_corrupt_manual_files()
    print(f"\n  Corrupt-manual files identified: {len(corrupt)}")
    rescued, still_borked = rescue_mining_scan(corrupt)

    # ── Task 4: Rescue Write (--apply only) ──
    if args.apply:
        if not rescued:
            print("\n  No clean candidates to write.")
        else:
            rescue_write(rescued)
    else:
        print("\n  [SKIP] Rescue write; rerun with --apply to execute phase 4")

    # ── FINAL VERDICT ───────────────────────
    print("\n" + "=" * 72)
    print("FINAL REPORT (<=15 lines)")
    print("=" * 72)

    total_dff_issues = len([x for x in dff_results if x[2] > 0])
    total_bare = len(bare_dffs)
    total_ipl = len(ipl_mismatches)

    unique_missing_models = set()
    for _, _, _, m in ipl_mismatches:
        unique_missing_models.add(m)

    print(f"\nA. DFF/IPL VERDICT: "
          f"{'CONFIRMED (partial)' if len(cross_missing) > 0 or total_bare > 0 or len(unique_missing_models) > 0 else 'NOT CONFIRMED'}")

    if len(cross_missing) == 0 and total_bare == 0 and len(unique_missing_models) == 0:
        print(f"   NONE DETECTED — brown blobs are purely the "
              f"{len(corrupt)} DXT3-corrupt TXD files (upstream damage).")
    else:
        if cross_missing:
            for pname, rel, n, exs in cross_missing[:3]:
                print(f"   DFF tex ref unresolved: {rel}: "
                      f"{n} missing (e.g. {','.join(exs[:2])})")
        if bare_dffs:
            print(f"   Zero-tex-ref DFFs (broken?): {len(bare_dffs)}")
            for _, rel, _ in bare_dffs[:3]:
                print(f"     {rel}")
        if unique_missing_models:
            print(f"   IPL orphan model refs: "
                  f"{len(unique_missing_models)} unique names")

    src_counts = defaultdict(int)
    for _, _, sg, _ in rescued:
        src_counts[sg] += 1
    gen_detail = "; ".join(f"{cnt} from {g}" for g, cnt in sorted(src_counts.items()))
    print(f"\nB. RESCUED {len(rescued)}/{len(corrupt)} — {gen_detail}")

    print(f"\nC. REMAINING corrupt (unrescuable): {len(still_borked)}")

    print(f"\nD. RECOMMENDED NEXT STEP:")
    if still_borked:
        print(f"   {len(still_borked)} files need external Magic.TXD batch repair"
              f" (DXT3 regen forbidden in this tool by hard rule)."
              f" Export -> Magic.TXD -> regenerate DXT3 mips -> reimport."
              f" Or: live-with-it (brown blobs on {len(still_borked)} TXDs).")
    else:
        print(f"   All files rescued! No action needed.")

    return 0


if __name__ == "__main__":
    sys.exit(main())