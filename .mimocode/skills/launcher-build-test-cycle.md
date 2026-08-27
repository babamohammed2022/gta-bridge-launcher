# Skill: Launcher Build-Test Cycle

1. Edit code (app.py / launcher.py / utils/*).
2. `python -m py_compile <file>` — syntax gate.
3. Offscreen UI smoke: `QT_QPA_PLATFORM=offscreen` + venv64 python
   (`E:/dev(dave)/_SAS_1987/87_installer/venv64`) run ui_smoke2.py.
   QMessageBox segfaults offscreen — use inline status labels.
4. Logic tests: `python verify_launcher.py` (6 checks) + `python test_bridge_sim.py` (14 checks).
5. Package: PyInstaller via venv64 → dist/launcher.exe (PE 0x8664) → copy as
   GTA_Bridge_Launcher.exe beside gta_sa.exe.
6. Update `.serena/memories/*.md` + re-run `.sadie/sadie.py init` +
   `.sadie/sadie_vault_sync.py` so memory stays fresh.
