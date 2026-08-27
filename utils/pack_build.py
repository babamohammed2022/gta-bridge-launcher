#!/usr/bin/env python3
"""pack_build.py - Curate modloader packs into launcher_data/dlc/<id>/ packages.

GGMM's autoinstalling-package maker, modernized:
- Scans each pack in <game>/modloader/
- Copies content into launcher_data/dlc/<id>/ excluding authoring junk
- Writes manifest.json per pack (id, name, category, defaults, stats)
- content_stats sampled via utils/rw_inspect.py (DFF/TXD/COL parsing)

Usage: python pack_build.py [--game DIR] [--project DIR]
"""
import json
import os
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
try:
    from utils.rw_inspect import inspect_any
except ImportError:
    inspect_any = None

DEFAULT_GAME = os.environ.get("GTA_PATH", "E:/games/gtasa_skygfx_plus")
PROJECT = Path(__file__).parent.parent

# Authoring junk excluded from packages (kept out of DLC)
JUNK_PATTERNS = [
    r".*\.7z$", r".*\.psd$", r".*\.png$", r".*\.tga$", r".*\.blend1?$",
    r".*\.fbx$", r".*\.obj$", r".*\.mtl$", r".*_old\..*$", r".*_OLD.*$",
    r".*\u043a\u043e\u043f\u0438\u044f.*$",   # '- копия' duplicate suffix
    r".*desktop\.ini$", r".*Thumbs\.db$", r".*\.bak$", r".*\.tmp$",
]
JUNK_RE = [re.compile(p, re.IGNORECASE) for p in JUNK_PATTERNS]

KEEP_EXT = {".dds", ".txd", ".dff", ".col", ".ide", ".ipl", ".dat", ".ini",
            ".cs", ".txt", ".cfg", ".img", ".fx", ".lua", ".fxp", ".rrr",
            ".ifp", ".scm", ".gxt", ".rad", ".dat"}

# Pack curation table: id -> (category, default_enabled, description)
PACK_META = {
    "DE_Vegetation_by_SA_THE_MODDER": ("vegetation", False,
        "Full vegetation overhaul (gta3.img + maps IDE/IPL/COL). Heavy; off by default."),
    "D_ORG_Patch_SA": ("fixes", True,
        "~60 texture fixes restoring original org details."),
    "Improved and Fixed Original Vegetation": ("vegetation", True,
        "21 categories of improved original vegetation models."),
    "Parallax": ("buildings", True,
        "LA building parallax remap (dff+txd + LA ide/ipl pairs)."),
    "Proper_models": ("models", False,
        "Model corrections. Mostly authoring leftovers; off by default."),
    "Proper_paintjobs": ("paintjobs", True,
        "Cleaned vehicle paintjob textures."),
    "VINE_SIGN": ("props", True, "Vineyard sign prop fix."),
    "gta_v_streetlights": ("lighting", True,
        "GTA V style streetlights/lamps + object.dat flags."),
    "mobile_fences": ("fixes", True, "Mobile-version alpha/fence texture fixes (~57)."),
    "mobile_vegetation": ("vegetation", True, "Mobile-version vegetation texture fixes (~50)."),
    "ps2 map + fixes": ("map", True,
        "PS2-era streamed IPL/COL/DFF restorations (country interiors, bowl, neon jetty)."),
}

RW_SAMPLE_CAP = 60  # max files content-inspected per pack


def is_junk(name: str) -> bool:
    return any(rx.match(name) for rx in JUNK_RE)


def scan_stats(root: Path):
    """Walk a pack tree; return (files_copied_meta, rw_content_stats)."""
    ext_counts = {}
    total_bytes = 0
    file_count = 0
    rw_samples = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not is_junk(d)]
        for fn in sorted(filenames):
            if is_junk(fn):
                continue
            p = Path(dirpath) / fn
            ext = p.suffix.lower()
            try:
                sz = p.stat().st_size
            except OSError:
                continue
            file_count += 1
            total_bytes += sz
            ext_counts[ext] = ext_counts.get(ext, 0) + 1
            if inspect_any and ext in (".dff", ".txd", ".col") and len(rw_samples) < RW_SAMPLE_CAP:
                info = inspect_any(str(p))
                if info and not info.get("error"):
                    rw_samples.append(info)
    stats = {
        "file_count": file_count,
        "bytes": total_bytes,
        "ext_counts": dict(sorted(ext_counts.items(), key=lambda kv: -kv[1])),
    }
    if rw_samples:
        tex_total = sum(s.get("texture_count", 0) for s in rw_samples if "texture_count" in s)
        tri_total = sum(s.get("triangles", 0) for s in rw_samples if "triangles" in s)
        col_entries = sum(s.get("entries", 0) for s in rw_samples if s.get("type") == "col")
        stats["content_stats"] = {
            "sampled_files": len(rw_samples),
            "textures_in_txd_sample": tex_total,
            "triangles_in_dff_sample": tri_total,
            "col_entries_sample": col_entries,
        }
    return stats


def curate_pack(src: Path, dst_root: Path, pack_id: str):
    meta = PACK_META.get(pack_id, ("misc", True, ""))
    dst = dst_root / pack_id
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    copied = 0
    skipped = 0
    for dirpath, dirnames, filenames in os.walk(src):
        rel = Path(dirpath).relative_to(src)
        dirnames[:] = [d for d in dirnames if not is_junk(d)]
        out_dir = dst / rel
        out_dir.mkdir(parents=True, exist_ok=True)
        for fn in sorted(filenames):
            if is_junk(fn):
                skipped += 1
                continue
            sp = Path(dirpath) / fn
            dp = out_dir / fn
            try:
                shutil.copy2(sp, dp)
                copied += 1
            except OSError as e:
                print("  [WARN] copy failed %s: %s" % (fn, e))
    return dst, copied, skipped


def main():
    game = DEFAULT_GAME
    args = sys.argv[1:]
    if "--game" in args:
        game = args[args.index("--game") + 1]
    modloader = Path(game) / "modloader"
    dlc_root = PROJECT / "launcher_data" / "dlc"
    dlc_root.mkdir(parents=True, exist_ok=True)

    if not modloader.exists():
        print("[FAIL] no modloader dir at", modloader)
        return 1

    print("Scanning packs in", modloader)
    # modloader system folders are not content packs
    SYSTEM_DIRS = {".data", ".profiles", ".cache"}
    manifests = []
    for entry in sorted(modloader.iterdir()):
        if not entry.is_dir() or entry.name in SYSTEM_DIRS:
            continue
        pid = entry.name
        cat, default_on, desc = PACK_META.get(pid, ("misc", True, ""))
        print("\n== %s ==" % pid)
        stats = scan_stats(entry)
        print("  files=%d bytes=%.1fMB junk-ext-skip-later" % (
            stats["file_count"], stats["bytes"] / 1048576))
        dst, copied, skipped = curate_pack(entry, dlc_root, pid)
        final_stats = scan_stats(dst)
        manifest = {
            "id": pid.lower().replace(" ", "_"),
            "name": pid,
            "description": desc,
            "version": "1.0",
            "category": cat,
            "default_enabled": default_on,
            "source_priority_hint": None,
            "file_count": final_stats["file_count"],
            "bytes": final_stats["bytes"],
            "stats": final_stats,
        }
        mpath = dst / "manifest.json"
        mpath.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        manifests.append(manifest)
        print("  [OK] curated -> %s (%d copied, %d junk skipped)" % (dst.name, copied, skipped))

    index = {"packs": manifests, "generated_by": "pack_build.py"}
    (dlc_root / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    print("\n[OK] %d packs curated, index.json written to %s" % (len(manifests), dlc_root))
    return 0


if __name__ == "__main__":
    sys.exit(main())
