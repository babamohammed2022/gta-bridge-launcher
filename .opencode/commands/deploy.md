---
name: deploy
description: Build and deploy the GTA Bridge Launcher (onedir exe + asi + txdfix.dll) to the game dir with rollback backups
---

# /deploy — GTA Bridge Launcher deploy ritual

Build mode: PyInstaller onedir (dist/GTA_Bridge_Launcher/{exe,_internal/}). Never copy single-file exe anymore.

## Steps

1. Compile gate: `E:/dev(dave)/_SAS_1987/87_installer/venv64/Scripts/python.exe -m py_compile app.py launcher.py managers/*.py utils/*.py`
2. Build: `"…venv64…python.exe" -m PyInstaller launcher.spec --noconfirm` (workdir = project root)
3. Layout assert: `dist/GTA_Bridge_Launcher/GTA_Bridge_Launcher.exe` + `_internal/PyQt5` exist
4. Deploy (workdir project root):
   - `cp -r dist/GTA_Bridge_Launcher /e/games/gtasa_skygfx_plus/`
   - `cp managers/txdfix.dll /e/games/gtasa_skygfx_plus/txdfix.dll`
   - ASI (only if asi_bridge changed): backup first `cp /e/games/gtasa_skygfx_plus/gta_bridge.asi{,.bak-prev}` then `cp asi_bridge/bin/gta_bridge.asi /e/games/gtasa_skygfx_plus/`
5. Verify binary labels after C++ changes: `grep -aoc "<new-label>" asi_bridge/bin/gta_bridge.asi`

## Rules

- If `cp` says `Device or resource busy` → **the game is running**; never force — report and redeploy after user closes it.
- If cp target is a non-directory with same name → old onefile artifact collision; rename it `.bak-old-onefile` first.
- Always keep `.bak-prev` of any asi you overwrite. Never delete backups.
- After C++ edits: verify string markers in binary BEFORE deploy; verify PE32 x86 via `file`.
