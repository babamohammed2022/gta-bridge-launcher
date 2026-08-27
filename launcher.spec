# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['E:/dev(dave)/projects/gta_bridge_launcher/app.py'],
    pathex=['E:/dev(dave)/projects/gta_bridge_launcher'],
    binaries=[],
    hiddenimports=['py7zr','rarfile','installer_src','installer_src.downloader','installer_src.extractor','installer_src.sa_detector','installer_src.sa_hashes','installer_src.scraper','installer_src.installer_stages','installer_src.cache','installer_src.backup','installer_src.gamecopyworld','installer_src.config','installer_src.ui.wizard','installer_src.ui.theme'],
    datas=[('E:/dev(dave)/projects/gta_bridge_launcher/fonts', 'fonts'),
           ('E:/dev(dave)/projects/gta_bridge_launcher/config', 'config'),
           ('E:/dev(dave)/projects/gta_bridge_launcher/installer_src/data', 'installer_src/data'),
           ('E:/dev(dave)/projects/gta_bridge_launcher/installer_src/ui/splash', 'installer_src/ui/splash')],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='GTA_Bridge_Launcher',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name='GTA_Bridge_Launcher',
)