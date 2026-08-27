# Build & verify
Python: 64-bit at C:/Users/aaaaaaaaa/AppData/Local/Programs/Python/Python310-64/python.exe; PyQt5 ONLY in venv64 = E:/dev(dave)/_SAS_1987/87_installer/venv64 (has PyQt5+PyInstaller+psutil+requests+bs4).
GUI run: venv64 python app.py. Smoke: QT_QPA_PLATFORM=offscreen (QMessageBox segfaults offscreen — use inline labels).
EXE: venv64 -m PyInstaller launcher.spec -> dist/launcher.exe (PE 0x8664); copy to game dir as GTA_Bridge_Launcher.exe.
Console cp1252: no unicode checkmarks in print — use [OK]/[FAIL].
Bash: simple single commands only (compound/background commands trigger ChildProcess.kill tool errors).
Verify: verify_launcher.py 6 checks, test_bridge_sim.py 14 checks, live pipe HELLO/PING/pools-after-9s.
