#!/usr/bin/env python3
"""friend_zip.py - Build the shareable "friend zip v4" mod-pack archive.

Replaces the manual checklist assembly planned in
docs/plans/2026-08-26-roadmap-execution.md (Task 6 step 5: "Rebuild friend
zip from checklist output") and docs/RELEASE_CHECKLIST.md section
"Distributable (friend zip)".

Read-only over launcher_data/dlc/<pack_id>/ (ground-truth pack folders,
roadmap Global Constraint #6). The only artifact written is
<out>/friend_zip_v4_YYYYMMDD.zip (MANIFEST.txt + README.txt live inside
the zip, so nothing else is ever written outside --out).

Usage: python utils/friend_zip.py [--out DIR] [--packs id1,id2,...]
"""
import argparse
import datetime
import os
import re
import sys
import zipfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from utils.pack_build import JUNK_PATTERNS, is_junk  # noqa: E402

DLC_ROOT = PROJECT / "launcher_data" / "dlc"
DEFAULT_OUT = PROJECT / "dist"
ZIP_NAME = "friend_zip_v4_%s.zip"  # % YYYYMMDD

# Friend-zip contents list, derived from the docs:
#   - docs/RELEASE_CHECKLIST.md "Distributable (friend zip)": "Contents per
#     FRIEND_TEST_README.txt" -> ASI loader + CLEO runtime, skygfx,
#     SilentPatch, LimitAdjuster, data patches.
#   - docs/plans/2026-08-26-roadmap-execution.md Task 3 step 4: "Re-enable
#     (remove .disabled), add to friend zip contents list" -> the recompiled
#     gta_bridge_save.cs rides in the cleo_scripts pack (supersedes the older
#     checklist note "no .cs scripts" for the bridge save script).
#     *** SUPERSEDED 2026-08-27 *** User decision: no custom scripts ship.
#     The cleo_scripts pack ships runtime-CLEO-only (no .cs files). The
#     EXCLUDE_PATTERNS list below excludes *.cs to enforce this.
#   - Pack ids are the canonical ones from launcher_data/dlc/index.json.
#     Community mods (launcher_data/dlc/mods_index.json: Parallax, HD vehicle
#     textures, ...) are NOT part of the friend zip.
FRIEND_ZIP_PACKS = [
    "runtime_redist",   # ASI loader + CLEO/MoonLoader runtime (layer 0)
    "cleo_scripts",     # bridge CLEO scripts — runtime-CLEO-only, no .cs (2026-08-27)
    "skygfx_core",      # skygfx.asi + skygfx.ini
    "silentpatch",      # SilentPatchSA
    "limit_adjuster",   # III.VC.SA.LimitAdjuster
    "data_patches",     # colorcycle.dat / weathers2.dat / map fixes
]

GAME_VERSION_NOTE = ("Target game: clean GTA San Andreas 1.0 US (hoodlum). "
                     "Do NOT stack on another modded install.")

# Personal save data — never ship. Excluded from generated zips on top of the
# shared JUNK_PATTERNS junk filter (pack_build.is_junk). Matches CLEO per-slot
# save folders (cleo_scripts/cleo/cleo_saves/cs0.sav ... cs7.sav) and any
# *.sav file anywhere in a pack tree.
EXCLUDE_PATTERNS = [
    r"^cleo_saves$",   # cleo_saves/ folder (any depth)
    r".*\.sav$",       # *.sav save files
    r".*\.cs$",        # runtime-CLEO-only ship — no custom scripts (2026-08-27)
]
EXCLUDE_RE = [re.compile(p, re.IGNORECASE) for p in EXCLUDE_PATTERNS]


def is_excluded(name: str) -> bool:
    return any(rx.match(name) for rx in EXCLUDE_RE)


def collect_pack_files(pack_dir: Path):
    """Walk one pack folder read-only; return [(abs_path, arcname), ...].

    arcname preserves the pack folder name + internal structure
    (<pack_id>/<relpath>) — folder names are NEVER renamed (roadmap hard
    rule #1). JUNK_PATTERNS files/dirs are excluded, plus EXCLUDE_PATTERNS
    personal save data (cleo_saves/ folders, *.sav files).
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
            # forward slashes so the zip extracts identically everywhere
            entries.append((abs_path, "%s/%s" % (pack_dir.name, rel)))
    return entries


def plan_packs(pack_ids):
    """Resolve pack ids to (pack_id, entries, stats); warn+skip missing ones.

    stats are computed from the post-filter entry list (not scan_stats) so
    MANIFEST.txt and the console summary match the zip's actual contents.
    Returns (planned, skipped_ids).
    """
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


def collect_binaries(bin_dir):
    """Collect required binaries + launcher_data manifests/profiles.

    Arcnames mirror deploy layout next to gta_sa.exe (exe + txdfix.dll at
    zip root). LOUD FAIL sys.exit(2) on missing files with build hint.
    STALE GUARD: exit(2) if exe is older than app.py or launcher.py.
    Returns [(abs_path, arcname), ...] and stats dict.
    """
    bin_dir = Path(bin_dir)
    required = [
        ("GTA_Bridge_Launcher.exe", bin_dir / "GTA_Bridge_Launcher.exe",
         "GTA_Bridge_Launcher.exe"),
        ("txdfix.dll", PROJECT / "managers" / "txdfix.dll", "txdfix.dll"),
        ("dlc/index.json", PROJECT / "launcher_data" / "dlc" / "index.json",
         "launcher_data/dlc/index.json"),
        ("dlc/mods_index.json", PROJECT / "launcher_data" / "dlc" / "mods_index.json",
         "launcher_data/dlc/mods_index.json"),
        ("packs/presets.json", PROJECT / "launcher_data" / "packs" / "presets.json",
         "launcher_data/packs/presets.json"),
    ]

    missing = []
    entries = []
    for label, abs_path, arcname in required:
        if not abs_path.exists():
            missing.append(label)
            continue
        entries.append((abs_path, arcname))

    # mods_index.json is optional — warn if missing
    if "dlc/mods_index.json" in missing:
        print("[WARN] launcher_data/dlc/mods_index.json missing (optional, skipped)")
        missing.remove("dlc/mods_index.json")

    # Profiles: every PROJECT/launcher_data/profiles/*.json
    profiles_dir = PROJECT / "launcher_data" / "profiles"
    if profiles_dir.is_dir():
        for pf in sorted(profiles_dir.glob("*.json")):
            entries.append((pf, "launcher_data/profiles/%s" % pf.name))
    else:
        missing.append("profiles/ dir (launcher_data/profiles/)")

    if missing:
        print("[FAIL] missing required binaries / launcher_data files:")
        for m in missing:
            print("       - %s" % m)
        print("")
        print("  Hint: Build first: PyInstaller launcher.spec")
        print("  Then point --binaries at dist/GTA_Bridge_Launcher/")
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


def make_manifest_txt(planned, skipped, when):
    """MANIFEST.txt body: pack ids, file counts, byte sizes, date, game note."""
    lines = [
        "GTA BRIDGE - FRIEND ZIP v4 MANIFEST",
        "===================================",
        "Generated: %s" % when.strftime("%Y-%m-%d %H:%M:%S"),
        "Builder:   utils/friend_zip.py",
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
    lines.append("Install instructions: see README.txt in this zip.")
    return "\n".join(lines) + "\n"


def make_readme_txt(planned, has_binaries):
    """README.txt body: install instructions for the friend.

    Single-artifact install: extract entire zip next to gta_sa.exe so
    GTA_Bridge_Launcher.exe + txdfix.dll + launcher_data/ land together.
    """
    pack_list = "\n".join("  - %s" % pid for pid, _e, _s in planned)
    lines = [
        "GTA BRIDGE - FRIEND ZIP v4",
        "==========================",
        "",
        "This zip contains the curated mod packs (see MANIFEST.txt for the",
        "exact per-pack file counts and sizes):",
        pack_list,
        "",
        "HOW TO INSTALL",
        "--------------",
    ]
    if has_binaries:
        lines += [
            "Single-artifact install (recommended):",
            "  1. Extract the ENTIRE zip next to gta_sa.exe so that",
            "     GTA_Bridge_Launcher.exe, txdfix.dll, and launcher_data/",
            "     all land in the game directory.",
            "  2. Run GTA_Bridge_Launcher.exe and PLAY.",
            "",
            "Manual Mod Loader drag-drop (fallback):",
            "  Drag the pack FOLDERS from this zip into <game>/modloader/.",
            "  Mod Loader identifies each folder by its name - NEVER rename",
            "  the pack folders.",
        ]
    else:
        lines += [
            "Option A (recommended - launcher does the placement):",
            "  1. Put GTA_Bridge_Launcher.exe + txdfix.dll next to gta_sa.exe",
            "     (from the release build - not inside this zip).",
            "  2. Run the launcher, open the INSTALLER screen and install this",
            "     zip - or simply drag-drop this zip onto the MOD LOADER list",
            "     on the MODS screen.",
            "",
            "Option B (manual - Mod Loader drag-drop):",
            "  Drag the pack FOLDERS from this zip into <game>/modloader/.",
            "  Mod Loader identifies each folder by its name - NEVER rename",
            "  the pack folders.",
        ]
    lines += [
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
        "Credits: Magic.TXD / skygfx by dk22pac, SilentPatch by Silent.",
    ]
    return "\n".join(lines) + "\n"


def write_zip(zip_path: Path, planned, skipped, when, bin_entries=None):
    """Write the zip (ZIP_DEFLATED, per installer_src/backup.py pattern)."""
    has_binaries = bool(bin_entries)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for _pid, entries, _stats in planned:
            for abs_path, arcname in entries:
                try:
                    zf.write(abs_path, arcname=arcname)
                except OSError as e:
                    print("  [WARN] zip write failed %s: %s" % (arcname, e))
        if bin_entries:
            for abs_path, arcname in bin_entries:
                try:
                    zf.write(abs_path, arcname=arcname)
                except OSError as e:
                    print("  [WARN] zip write failed %s: %s" % (arcname, e))
        zf.writestr("MANIFEST.txt", make_manifest_txt(planned, skipped, when))
        zf.writestr("README.txt", make_readme_txt(planned, has_binaries))


def main():
    ap = argparse.ArgumentParser(
        description="Build the shareable friend zip v4 from launcher_data/dlc packs.")
    ap.add_argument("--out", default=str(DEFAULT_OUT),
                    help="output directory (default: dist/)")
    ap.add_argument("--packs", default=None,
                    help="comma-separated pack ids (default: FRIEND_ZIP_PACKS)")
    ap.add_argument("--binaries", default=None,
                    help="path to onedir folder (default: PROJECT/dist/GTA_Bridge_Launcher/)")
    args = ap.parse_args()

    if args.packs:
        pack_ids = [p.strip() for p in args.packs.split(",") if p.strip()]
    else:
        pack_ids = list(FRIEND_ZIP_PACKS)

    if not DLC_ROOT.is_dir():
        print("[FAIL] no dlc root at", DLC_ROOT)
        return 1

    when = datetime.datetime.now()
    planned, skipped = plan_packs(pack_ids)
    if not planned:
        print("[FAIL] zero packs included; no zip written")
        return 1

    # Collect binaries if --binaries provided (or default path exists)
    bin_entries = None
    bin_stats = None
    bin_dir = Path(args.binaries) if args.binaries else PROJECT / "dist" / "GTA_Bridge_Launcher"
    if bin_dir.is_dir():
        bin_entries, bin_stats = collect_binaries(bin_dir)
    elif args.binaries:
        print("[FAIL] --binaries path not found: %s" % bin_dir)
        return 1
    # else: no --binaries and default path missing — skip binaries silently

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / (ZIP_NAME % when.strftime("%Y%m%d"))
    write_zip(zip_path, planned, skipped, when, bin_entries)

    # Summary table (pack, files, MB) - post-exclusion counts, matches zip
    print("\n== friend zip v4 summary ==")
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
            "binaries", bin_stats["file_count"], bin_stats["bytes"] / 1048576))
        total_files += bin_stats["file_count"]
        total_bytes += bin_stats["bytes"]
    print("%-42s %8d %10.1f" % (
        "TOTAL (%d packs)" % len(planned), total_files, total_bytes / 1048576))
    if skipped:
        print("skipped: %s" % ", ".join(skipped))
    print("[OK] wrote %s (%d packs, %d files, %.1f MB)" % (
        zip_path, len(planned), total_files, total_bytes / 1048576))
    return 0


if __name__ == "__main__":
    sys.exit(main())
