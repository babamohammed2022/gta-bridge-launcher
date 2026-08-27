# Release Checklist — GTA Bridge Launcher

## Build
1. `cd E:/dev(dave)/projects/gta_bridge_launcher`
2. `E:/dev(dave)/_SAS_1987/87_installer/venv64/Scripts/python.exe -m py_compile app.py launcher.py managers/txdlite.py`
3. `E:/dev(dave)/_SAS_1987/87_installer/venv64/Scripts/python.exe -m PyInstaller launcher.spec --noconfirm`
4. Copy to game dir: copy **whole** `dist/GTA_Bridge_Launcher/` folder next to `gta_sa.exe` (exe + `_internal/` together); `managers/txdfix.dll -> txdfix.dll` unchanged. Old single-file `dist/launcher.exe` artifact is retired.
5. Ensure `launcher_data/` next to exe has: `dlc/index.json`, `packs/presets.json`, `profiles/`

## Smoke test (frozen exe)
- [ ] Launches without console errors
- [ ] PLAY screen: profile combo lists legacy+/test/perf; game path correct
- [ ] LIMITS screen: values load, apply works
- [ ] MODS: DLC packs list (9), MOD LOADER FOLDERS lists real folder names
- [ ] MODS: double-click toggle moves folder both ways
- [ ] MODS: drag zip onto MOD LOADER list installs
- [ ] MODS: pack apply enables/disables WITHOUT renaming folders
- [ ] MODS: SCAN TXDS runs, [BROKEN]/[OPT]/[OK] buckets correct
- [ ] TXD EDITOR: open TXD, thumbnails load, preview renders, export PNG works
- [ ] TXD EDITOR: EDIT opens pixel editor, APPLY re-encodes, SAVE writes
- [ ] TXD EDITOR: menus work (File/Edit/Tools/Export/View/Info)
- [ ] INSTALLER screen loads
- [ ] Crash log: rename a required file, launch, verify friendly dialog + log in launcher_data/logs/

## Distributable (friend zip)
- [ ] Build: `python utils/friend_zip.py --out <staging_dir>` (defaults to `dist/`)
- [ ] Contents:
  - 6 packs (runtime_redist, cleo_scripts, skygfx_core, silentpatch, limit_adjuster, data_patches) — no *.cs scripts, no cleo_saves/*.sav, no authoring junk
  - GTA_Bridge_Launcher.exe + txdfix.dll (zip root)
  - launcher_data/dlc/index.json, launcher_data/dlc/mods_index.json, launcher_data/packs/presets.json, launcher_data/profiles/*.json
  - MANIFEST.txt + README.txt
- [ ] Test-extract onto a CLEAN SA 1.0 copy, launch once
- [ ] Clean-copy test: extract to empty dir, verify no stray files outside zip root

## Hard rules re-check (must NEVER ship a build violating these)
- [ ] No code path renames modloader folders
- [ ] No code path writes inside *.img dirs
- [ ] Fixer never regenerates DXT3 mips
- [ ] Fixer never deletes backups
