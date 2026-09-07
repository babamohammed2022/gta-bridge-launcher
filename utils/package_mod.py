#!/usr/bin/env python3
"""package_mod.py - Build the SAS87 distributable package bundle.

Output layout (dist/SAS87_<YYYYMMDD>/):

  GTA_Bridge_Launcher/   (onedir copy — stale-guard against app.py/launcher.py)
  txdfix.dll             (from managers/)
  launcher_data/dlc/     (selected ship packs, default SAS87_SHIP_PACKS)
  launcher_data/dlc_presets/sas87.json  (preset referencing ALL_MODS parts)
  README.txt
  MANIFEST.txt

Read-only over launcher_data/dlc/<pack_id>/ (ground-truth pack folders).
The only artifact written is the SAS87_<YYYYMMDD>/ directory tree under --out.

Usage: python utils/package_mod.py [--out DIR] [--packs id1,id2,...] [--no-launcher]
"""
import argparse
import datetime
import importlib.util
import json
import os
import re
import shutil
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from utils.pack_build import JUNK_PATTERNS, is_junk  # noqa: E402

# Import ALL_MODS directly from installer_src/config.py, bypassing the
# installer_src package __init__.py (which pulls in bs4-dependent modules).
_config_spec = importlib.util.spec_from_file_location(
    "installer_src.config",
    str(PROJECT / "installer_src" / "config.py"),
)
_config_mod = importlib.util.module_from_spec(_config_spec)
# Register in sys.modules so dataclass decorator can resolve cls.__module__
sys.modules["installer_src.config"] = _config_mod
_config_spec.loader.exec_module(_config_mod)
ALL_MODS = _config_mod.ALL_MODS

DLC_ROOT = PROJECT / "launcher_data" / "dlc"
DEFAULT_OUT = PROJECT / "dist"
OUT_DIR_NAME = "SAS87_%s"  # % YYYYMMDD

# Default set of ship packs — the minimal preloaded DLC that ships inside the
# SAS87 bundle. The user does NOT need to download these separately.
SAS87_SHIP_PACKS = [
    "runtime_redist",    # ASI loader + CLEO/MoonLoader runtime
    "cleo_scripts",      # bridge CLEO scripts
    "skygfx_core",       # skygfx.asi + skygfx.ini
    "silentpatch",       # SilentPatchSA
    "limit_adjuster",    # III.VC.SA.LimitAdjuster
    "data_patches",      # colorcycle.dat / weathers2.dat / map fixes
    "bridge_scripts",    # bridge-specific scripts (modloader layer)
    "sas87_september",   # full conversion: 25 SAS87 content packs (dircopy -> modloader/)
]

GAME_VERSION_NOTE = ("Target game: clean GTA San Andreas 1.0 US (hoodlum). "
                     "Do NOT stack on another modded install.")

# Same junk/exclude filters as friend_zip
EXCLUDE_PATTERNS = [
    r"^cleo_saves$",
    r".*\.sav$",
    r".*\.cs$",
]
EXCLUDE_RE = [re.compile(p, re.IGNORECASE) for p in EXCLUDE_PATTERNS]


def is_excluded(name: str) -> bool:
    return any(rx.match(name) for rx in EXCLUDE_RE)


def collect_pack_files(pack_dir: Path):
    """Walk one pack folder read-only; return [(abs_path, arcname), ...].

    arcname = launcher_data/dlc/<pack_id>/<relpath> — preserves the deploy
    layout expected by the launcher.
    """
    entries = []
    for dirpath, dirnames, filenames in os.walk(pack_dir):
        dirnames[:] = sorted(d for d in dirnames
                             if not is_junk(d) and not is_excluded(d))
        rel_top = Path(dirpath).relative_to(pack_dir)
        for fn in sorted(filenames):
            if is_junk(fn) or is_excluded(fn):
                continue
            abs_path = Path(dirpath) / fn
            rel = fn if str(rel_top) == "." else str(rel_top / fn)
            arcname = "launcher_data/dlc/%s/%s" % (pack_dir.name, rel)
            entries.append((abs_path, arcname))
    return entries


def plan_packs(pack_ids):
    """Resolve pack ids to (pack_id, entries, stats); warn+skip missing ones."""
    planned = []
    skipped = []
    for pid in pack_ids:
        pack_dir = DLC_ROOT / pid
        if not pack_dir.is_dir():
            print("[WARN] pack folder missing, skipped: %s" % pack_dir)
            skipped.append(pid)
            continue
        entries = collect_pack_files(pack_dir)
        if not entries:
            print("[WARN] pack empty after junk filter, skipped: %s" % pid)
            skipped.append(pid)
            continue
        stats = {
            "file_count": len(entries),
            "bytes": sum(abs_path.stat().st_size
                         for abs_path, _arcname in entries),
        }
        planned.append((pid, entries, stats))
    return planned, skipped


def collect_launcher(bin_dir):
    """Collect the onedir launcher + txdfix.dll.

    LOUD FAIL sys.exit(2) on missing files. STALE GUARD: exit(2) if exe is
    older than app.py or launcher.py (same pattern as friend_zip).
    Returns [(abs_path, arcname), ...] and stats dict.
    """
    bin_dir = Path(bin_dir)
    required = [
        ("GTA_Bridge_Launcher.exe", bin_dir / "GTA_Bridge_Launcher.exe",
         "GTA_Bridge_Launcher/GTA_Bridge_Launcher.exe"),
        ("txdfix.dll", PROJECT / "managers" / "txdfix.dll", "txdfix.dll"),
    ]

    missing = []
    entries = []
    for label, abs_path, arcname in required:
        if not abs_path.exists():
            missing.append(label)
            continue
        entries.append((abs_path, arcname))

    # Also copy the _internal/ folder alongside the exe
    internal_dir = bin_dir / "_internal"
    if internal_dir.is_dir():
        for item in internal_dir.rglob("*"):
            if item.is_file():
                rel = item.relative_to(bin_dir)
                entries.append((item, "GTA_Bridge_Launcher/%s" % rel.as_posix()))
    else:
        missing.append("_internal/ (onedir support folder)")

    if missing:
        print("[FAIL] missing launcher binaries:")
        for m in missing:
            print("       - %s" % m)
        print("")
        print("  Hint: Build first: PyInstaller launcher.spec")
        print("  Then point --out at dist/ (default)")
        sys.exit(2)

    # STALE GUARD: exe mtime older than max(app.py, launcher.py)
    exe_path = bin_dir / "GTA_Bridge_Launcher.exe"
    exe_mtime = exe_path.stat().st_mtime
    src_mtimes = []
    for src in [PROJECT / "app.py", PROJECT / "launcher.py"]:
        if src.exists():
            src_mtimes.append(src.stat().st_mtime)
    if src_mtimes and exe_mtime < max(src_mtimes):
        print("[FAIL] exe STALE, rebuild: %s" % exe_path)
        print("  Hint: PyInstaller launcher.spec")
        sys.exit(2)

    stats = {
        "file_count": len(entries),
        "bytes": sum(p.stat().st_size for p, _ in entries),
    }
    return entries, stats


def build_preset(planned_packs):
    """Load the real SAS87 September preset (or fall back to ALL_MODS generation)."""
    preset_file = PROJECT / "launcher_data" / "dlc_presets" / "sas87_september.json"
    if preset_file.is_file():
        try:
            return json.load(open(preset_file, encoding="utf-8"))
        except Exception as e:
            print("  [WARN] preset load failed %s: %s" % (preset_file, e))

    parts = []
    for mod in ALL_MODS:
        if mod.extract_to_sa_root:
            dest_rel = "modloader/%s" % mod.id
        else:
            dest_rel = "modloader/%s" % mod.id
        part = {
            "name": mod.id,
            "dest_rel": dest_rel,
            "source_url": mod.url,
            "archive_hint": "%s.zip" % mod.id,
            "size": None,
        }
        if mod.page_url:
            part["page_url"] = mod.page_url
        parts.append(part)

    preset = {
        "id": "sas87",
        "title": "SAS 1987",
        "description": "GTA San Andreas Stories 1987 — full conversion mod pack",
        "category": "total_conversion",
        "version": "3.0.0",
        "parts": parts,
    }
    return preset


def make_manifest_txt(planned, skipped, when, preset_parts_count):
    """MANIFEST.txt body: pack ids, file counts, byte sizes, preset parts, date."""
    lines = [
        "GTA BRIDGE - SAS87 PACKAGE MANIFEST",
        "====================================",
        "Generated: %s" % when.strftime("%Y-%m-%d %H:%M:%S"),
        "Builder:   utils/package_mod.py",
        "Source:    launcher_data/dlc/<pack_id>/ (ground-truth pack folders)",
        GAME_VERSION_NOTE,
        "",
        "%-42s %8s %12s" % ("pack", "files", "MB"),
        "-" * 64,
    ]
    total_files = 0
    total_bytes = 0
    for pid, _entries, stats in planned:
        total_files += stats["file_count"]
        total_bytes += stats["bytes"]
        lines.append("%-42s %8d %12.1f" % (
            pid, stats["file_count"], stats["bytes"] / 1048576))
    lines.append("-" * 64)
    lines.append("%-42s %8d %12.1f" % (
        "TOTAL (%d packs)" % len(planned), total_files, total_bytes / 1048576))
    if skipped:
        lines.append("")
        lines.append("Skipped (missing/empty): %s" % ", ".join(skipped))
    lines.append("")
    lines.append("Preset parts (externally-sourced mods): %d" % preset_parts_count)
    lines.append("")
    lines.append("Install instructions: see README.txt in this package.")
    return "\n".join(lines) + "\n"


def make_readme_txt(planned, preset_parts, has_launcher):
    """README.txt body: install steps + per-part table."""
    pack_list = "\n".join("  - %s" % pid for pid, _e, _s in planned)
    lines = [
        "GTA BRIDGE - SAS87 PACKAGE",
        "===========================",
        "",
        "This package contains the curated DLC packs (see MANIFEST.txt for",
        "exact per-pack file counts and sizes):",
        pack_list,
        "",
        "HOW TO INSTALL",
        "--------------",
    ]
    if has_launcher:
        lines += [
            "  1. Copy the ENTIRE GTA_Bridge_Launcher/ folder next to",
            "     gta_sa.exe (the game directory).",
            "  2. Copy txdfix.dll next to gta_sa.exe.",
            "  3. Copy launcher_data/ next to gta_sa.exe (merge with",
            "     existing launcher_data/ if present).",
            "  4. Run GTA_Bridge_Launcher.exe.",
            "  5. Open the INSTALLER screen and load the SAS 1987 preset",
            "     (launcher_data/dlc_presets/sas87_september.json).",
            "  6. Download and install each part listed below.",
            "",
        ]
    else:
        lines += [
            "  1. Copy launcher_data/ next to gta_sa.exe (merge with",
            "     existing launcher_data/ if present).",
            "  2. Open the launcher INSTALLER screen and load the SAS 1987",
            "     preset (launcher_data/dlc_presets/sas87_september.json).",
            "  3. Download and install each part listed below.",
            "",
        ]

    lines += [
        "EXTERNAL MODS TO DOWNLOAD",
        "-------------------------",
        "These mods are NOT included in the package. You must download them",
        "from their respective sources. The launcher can do this for you",
        "via the INSTALLER screen.",
        "",
        "%-30s %-50s %-30s" % ("name", "get: page_url", "place: dest_rel"),
        "-" * 112,
    ]
    for part in preset_parts:
        name = part["name"]
        page = part.get("page_url", part["source_url"])
        dest = part["dest_rel"]
        lines.append("%-30s %-50s %-30s" % (name, page, dest))

    lines += [
        "",
        "EXTRA FILES",
        "-----------",
        "If you have additional mod archives (e.g. vehicle packs, texture",
        "packs), drop them into launcher_data/dlc_presets/archives/ then",
        "use the launcher DLC panel to install them.",
        "",
        "REQUIREMENTS",
        "------------",
        GAME_VERSION_NOTE,
        "",
        "UNINSTALL",
        "---------",
        "Toggle the pack off on the launcher MODS screen, or delete its",
        "folder from modloader/.",
        "",
    ]
    return "\n".join(lines) + "\n"


def copy_to_outdir(out_dir, planned, bin_entries, preset):
    """Write the output directory tree (not a zip — a folder layout)."""
    out_dir.mkdir(parents=True, exist_ok=True)

    # Copy pack files into launcher_data/dlc/<pack_id>/
    for _pid, entries, _stats in planned:
        for abs_path, arcname in entries:
            dest = out_dir / arcname
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(abs_path, dest)
            except OSError as e:
                print("  [WARN] copy failed %s: %s" % (arcname, e))

    # Copy launcher binaries
    if bin_entries:
        for abs_path, arcname in bin_entries:
            dest = out_dir / arcname
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(abs_path, dest)
            except OSError as e:
                print("  [WARN] copy failed %s: %s" % (arcname, e))

    # Write preset
    preset_dir = out_dir / "launcher_data" / "dlc_presets"
    preset_dir.mkdir(parents=True, exist_ok=True)
    preset_path = preset_dir / "sas87_september.json"
    with open(preset_path, "w", encoding="utf-8") as f:
        json.dump(preset, f, indent=2, ensure_ascii=False)
        f.write("\n")

    return out_dir


def main():
    ap = argparse.ArgumentParser(
        description="Build the SAS87 distributable package from launcher_data/dlc packs.")
    ap.add_argument("--out", default=str(DEFAULT_OUT),
                    help="output directory (default: dist/)")
    ap.add_argument("--packs", default=None,
                    help="comma-separated pack ids (default: SAS87_SHIP_PACKS)")
    ap.add_argument("--no-launcher", action="store_true",
                    help="skip launcher binaries (for testing / read-only builders)")
    args = ap.parse_args()

    if args.packs:
        pack_ids = [p.strip() for p in args.packs.split(",") if p.strip()]
    else:
        pack_ids = list(SAS87_SHIP_PACKS)

    if not DLC_ROOT.is_dir():
        print("[FAIL] no dlc root at", DLC_ROOT)
        return 1

    when = datetime.datetime.now()
    planned, skipped = plan_packs(pack_ids)
    if not planned:
        print("[FAIL] zero packs included; no package written")
        return 1

    # Build preset from ALL_MODS
    preset = build_preset(planned)
    preset_parts = preset["parts"]

    # Collect launcher binaries (unless --no-launcher)
    bin_entries = None
    bin_stats = None
    if not args.no_launcher:
        bin_dir = PROJECT / "dist" / "GTA_Bridge_Launcher"
        if bin_dir.is_dir():
            bin_entries, bin_stats = collect_launcher(bin_dir)
        else:
            print("[FAIL] onedir not found at %s" % bin_dir)
            print("  Hint: Build first: PyInstaller launcher.spec")
            return 1
    else:
        print("[INFO] --no-launcher: skipping launcher binaries")

    out_parent = Path(args.out)
    out_parent.mkdir(parents=True, exist_ok=True)
    out_dir = out_parent / (OUT_DIR_NAME % when.strftime("%Y%m%d"))

    # Remove existing output dir if present
    if out_dir.exists():
        print("[WARN] removing existing output: %s" % out_dir)
        shutil.rmtree(out_dir)

    copy_to_outdir(out_dir, planned, bin_entries, preset)

    # Write MANIFEST.txt
    manifest = make_manifest_txt(planned, skipped, when, len(preset_parts))
    (out_dir / "MANIFEST.txt").write_text(manifest, encoding="utf-8")

    # Write README.txt
    readme = make_readme_txt(planned, preset_parts, bool(bin_entries))
    (out_dir / "README.txt").write_text(readme, encoding="utf-8")

    # Summary
    print("\n== SAS87 package summary ==")
    print("%-42s %8s %10s" % ("pack", "files", "MB"))
    total_files = 0
    total_bytes = 0
    for pid, _entries, stats in planned:
        total_files += stats["file_count"]
        total_bytes += stats["bytes"]
        print("%-42s %8d %10.1f" % (
            pid, stats["file_count"], stats["bytes"] / 1048576))
    if bin_stats:
        print("%-42s %8d %10.1f" % (
            "launcher", bin_stats["file_count"], bin_stats["bytes"] / 1048576))
        total_files += bin_stats["file_count"]
        total_bytes += bin_stats["bytes"]
    print("%-42s %8d %10.1f" % (
        "TOTAL (%d packs)" % len(planned), total_files, total_bytes / 1048576))
    if skipped:
        print("skipped: %s" % ", ".join(skipped))
    print("preset parts (external mods): %d" % len(preset_parts))
    print("[OK] wrote %s (%d packs, %d files, %.1f MB)" % (
        out_dir, len(planned), total_files, total_bytes / 1048576))
    return 0


if __name__ == "__main__":
    sys.exit(main())