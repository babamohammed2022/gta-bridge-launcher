# GTA San Andreas Stories 1987 — Installer Wizard

A standalone, portable Python installer wizard for the **GTA San Andreas Stories 1987** total-conversion mod.
Built with PyQt5, themed with the **FREE Pricedown Bl font** (Typodermic Fonts — free for commercial use), the **actual GTA logo font**, and a palette inspired by **GTA Vice City Stories carcols.dat** with dark greens preferred for legibility.

Each wizard page has its own **splash image pulled from the actual mod** (downloaded from `babamohammed2022/gta-1987-remastered-mod` on GitHub), anchored to the **bottom-right corner** so the mod's watermark is always visible. The rest of the image fills up and to the left, with a dark green tint overlay for text legibility.

The wizard builds a **fully portable, standalone modded San Andreas folder** — your original install is never touched. Perfect if you have a disk copy of SA but no disk drive (just point the wizard at your already-unpacked + NO-CD'd install).

> **📖 See [INSTALLER_GUIDE.pdf](INSTALLER_GUIDE.pdf)** for the full credits & attribution list AND a step-by-step fork guide for developers who want to rebuild or extend the installer.
> **📋 See [CREDITS.md](CREDITS.md)** for the plain-text credits (same content as the PDF, easier to copy-paste).

## What it does

1. **Mod source choice** — pick "I already have mod files" or "Download everything for me"
2. **Source SA folder** — point at your vanilla GTA SA install (auto-detected via registry + Steam `libraryfolders.vdf` + common paths)
3. **Destination folder** — pick where the wizard creates the standalone modded install (5+ GB free space required)
4. **Version check** — SHA-1 hash + file-size detection against `data/exe_hashes.json`. Recognises v1.0 HOODLUM, v1.01, v2.0 SecuROM, v3.0 Steam, v3.0 Rockstar Launcher
5. **NO-CD downgrade** — if needed, the wizard:
   - Auto-fetches the **HOODLUM v1.0 [ALL] No-CD/Fixed EXE** patch list from **GameCopyWorld**
   - Auto-downloads the recommended patch and replaces `gta_sa.exe` in the destination
   - OR lets you browse for a manually-downloaded patch archive
6. **Copy vanilla SA** → destination (full clone, original stays untouched)
7. **Backup** the freshly-prepared destination to `cache/backups/<timestamp>.zip` (a folder next to the installer)
8. **Download & install mods** (in order):
   - **CLEO 5** (optional) — from `github.com/cleolibrary/CLEO5/releases`
   - **CLEO+** (optional) — from `github.com/JuniorDjjr/CLEOPlus/releases` (GitHub mirror of the MixMods mod)
   - **NewOpcodes** (optional) — from `mixmods.com.br` (Cloudflare-blocked — manual download fallback)
   - **GTA SAS 1987 main mod** (required) — from the official MediaFire link scraped off `gtasas.netlify.app`
9. **Mod URLs are scraped live** from the official site's React JS bundle on every run, so the wizard always uses the freshest links. If the main mod isn't on the official site, **LibertyCity.net search** is used as a fallback
10. **Shared cache** at `cache/` (next to the installer) means re-runs are instant (no re-downloads, no re-extraction)
11. **Launch button** on the completion page starts the game from the new modded folder

## Project layout

```
gta-sas-1987-installer/
├── installer.py                 # Main entry point
├── run.bat                      # Portable launcher (finds Python, installs deps, runs wizard)
├── build_portable.bat           # Builds a true standalone .exe via PyInstaller
├── build.bat                    # Alias for build_portable.bat (kept for backward compat)
├── installer.spec               # PyInstaller spec
├── requirements.txt
├── README.md
├── fonts/
│   ├── PricedownBl.otf            # Free Pricedown font (Typodermic Fonts)
│   ├── FONT_LICENSE.html          # License terms
│   └── Typodermic_EULA.pdf
├── data/
│   └── exe_hashes.json          # Known SA exe versions + SHA-1 hashes
└── src/
    ├── __init__.py
    ├── config.py                # Mod URLs, GCW/LibertyCity URLs, paths, constants
    ├── cache.py                 # Shared cache manager
    ├── sa_detector.py           # Find SA install (registry/Steam/common-paths)
    ├── sa_hashes.py             # SHA-1 hash-based version detection
    ├── scraper.py               # Scrape gtasas.netlify.app + LibertyCity fallback
    ├── downloader.py            # HTTP downloads + MediaFire/GitHub/MixMods/LibertyCity resolvers
    ├── extractor.py             # .zip / .rar / .7z extraction + merge
    ├── backup.py                # Backup originals to .zip
    ├── gamecopyworld.py         # Scrape GCW for NO-CD patches
    ├── installer_stages.py      # detect → copy → nocd → backup → install_mods
    └── ui/
        ├── __init__.py
        ├── theme.py             # VCS dark-green palette + Pricedown font + splash image bg
        ├── splash/              # Per-page splash images (8 PNGs from the mod)
        │   ├── welcome.png
        │   ├── mod_source.png
        │   ├── source_sa.png
        │   ├── destination.png
        │   ├── downgrade.png
        │   ├── backup.png
        │   ├── prereqs.png
        │   └── install.png
        ├── wizard.py            # QWizard subclass + page wiring + splash repaint on page change
        ├── welcome_page.py
        ├── mod_source_page.py   # "I have mods" vs "Download for me"
        ├── source_sa_page.py    # Vanilla SA folder picker
        ├── destination_page.py  # Mod install folder picker
        ├── downgrade_page.py    # Hash check + GCW NO-CD picker (friendly to already-NO-CD'd installs)
        ├── backup_page.py
        ├── prereqs_page.py      # Mod selection (tick/untick)
        ├── install_page.py      # Progress + log
        └── complete_page.py     # Summary + launch button
```

## Running

### Option A: Portable launcher (recommended for end users)

```cmd
:: Double-click run.bat, or:
run.bat
```

The launcher will:
1. Find Python on your system (or use a bundled `python\python.exe` if you drop one in)
2. Verify pip is installed (bootstrap via `ensurepip` if missing)
3. Install required packages with **full visible output** so you can see any errors
4. Fall back to `--user` install if permission denied
5. Fall back to `--no-cache-dir` if the pip cache is corrupted
6. Launch the wizard

**If `run.bat` fails to install dependencies**, double-click **`diagnose.bat`** instead — it prints diagnostic info (Python version, pip availability, network reachability, which packages are missing). Copy the output and share it when asking for help.

**If the wizard itself crashes**, three log files are produced (look in the installer folder):

| File | What it contains |
|------|------------------|
| `wizard_output.log` | Full stdout+stderr from the wizard run (captured by `run.bat` via PowerShell `Tee-Object`) |
| `crash_*.log` | Python traceback with timestamp, Python version, executable path, CWD — written by the wizard's crash handler |
| `cache/logs/install_*.log` | Install log (only if logging started before the crash) |

The `crash_*.log` file is the most useful — it has the full Python traceback showing exactly which line crashed and why. A dialog box will pop up telling you where the file is. Share it back when reporting the bug.

#### Common issues

| Symptom | Fix |
|---------|-----|
| `Python was not found; run without arguments to install from the Microsoft Store` | Install **real Python** from https://www.python.org/downloads/ — tick "Add Python to PATH" on the first installer page. Close and reopen any command prompts. |
| `[ERROR] Failed to install dependencies` | Run `diagnose.bat` to see the actual error. Most common cause: corporate firewall blocking PyPI — try a different network. |
| `pip is not installed` | The launcher will auto-run `python -m ensurepip`. If that fails too, download https://bootstrap.pypa.io/get-pip.py and run `python get-pip.py`. |
| Permission denied during pip install | The launcher auto-retries with `--user`. If still failing, run the command prompt as Administrator. |

### Option B: Run from source

```bash
pip install -r requirements.txt
python installer.py
```

### Option C: Build a true standalone .exe

```cmd
build_portable.bat
```

Output: `dist\GTA_SAS_1987_Installer_Portable\` — a folder containing `GTA_SAS_1987_Installer.exe` (single file, no Python needed on the target machine). Zip it and share.

## Dependencies

- **Python 3.10+**
- **PyQt5** — GUI toolkit
- **requests** — HTTP client
- **beautifulsoup4** — HTML parsing (for the GCW + LibertyCity scrapers)
- **py7zr** — `.7z` extraction
- **rarfile** — `.rar` extraction (needs `unrar.exe` or `7z.exe` on PATH on Windows)
- **psutil** — process info

> For `.rar` extraction, install [7-Zip](https://www.7-zip.org/) or [WinRAR](https://www.rarlab.com/). The wizard auto-detects them at `%PROGRAMFILES%\7-Zip\7z.exe` or `%PROGRAMFILES%\WinRAR\unrar.exe`.

## Customising the mod list

All mod URLs and metadata live in `src/config.py`. Each entry is a `ModSource`:

```python
ModSource(
    id="cleo5",
    name="CLEO 5",
    description="Required for running CLEO scripts.",
    url="https://github.com/cleolibrary/CLEO5/releases",
    install_order=10,
    is_github_release=True,
    optional=True,
    enabled_by_default=False,
)
```

The wizard will (in order):
1. If "I have mods" was selected: try to find the file in the user's archives folder.
2. Try the shared cache (already-downloaded archives).
3. Fall back to downloading from `url`.

## Adding known exe hashes

`data/exe_hashes.json` is the SHA-1 lookup table. The wizard computes SHA-1 of the user's `gta_sa.exe` and looks it up here. If the hash isn't found, it falls back to file-size matching, then to a manual-pick dropdown.

To add a new hash, just append a new entry to the `versions` array:

```json
{
  "id": "v1.0_us_german",
  "label": "v1.0 US (German)",
  "region": "DE",
  "version_string": "1.0.0.0",
  "file_size_bytes": 6180864,
  "sha1": "abcdef1234567890abcdef1234567890abcdef12",
  "mod_compatible": true,
  "needs_downgrade": false,
  "source": "Retail CD (German)",
  "notes": "German v1.0 build."
}
```

## Restore / Uninstall

Backups live in `cache/backups/` (next to the installer). To restore:
1. Close GTA SA.
2. Delete the contents of your destination folder (or just delete the whole folder).
3. Re-run the wizard (it'll re-copy vanilla SA + re-apply mods from cache).

To fully clean up the wizard's own data: delete the `cache/` folder next to the installer.

## Disclaimer

This installer is a fan-made tool and is not affiliated with Rockstar Games or Take-Two Interactive. GTA San Andreas is required and must be legally purchased. The "GTA San Andreas Stories 1987" mod is the property of its respective authors (see `gtasas.netlify.app` for credits). The NO-CD patch from GameCopyWorld is for use with your own legally-purchased game only — please respect Rockstar's EULA and your local laws.
