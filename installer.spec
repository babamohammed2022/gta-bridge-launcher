# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['E:/dev(dave)/projects/gta_bridge_launcher/installer_src/installer.py'],
    pathex=['E:/dev(dave)/projects/gta_bridge_launcher'],
    binaries=[],
    hiddenimports=[
        'py7zr', 'rarfile', 'requests', 'bs4',
        'installer_src', 'installer_src.downloader', 'installer_src.extractor',
        'installer_src.sa_detector', 'installer_src.sa_hashes', 'installer_src.scraper',
        'installer_src.installer_stages', 'installer_src.cache', 'installer_src.backup',
        'installer_src.gamecopyworld', 'installer_src.config',
        'installer_src.ui', 'installer_src.ui.wizard', 'installer_src.ui.theme',
        'installer_src.ui.welcome_page', 'installer_src.ui.mod_source_page',
        'installer_src.ui.source_sa_page', 'installer_src.ui.destination_page',
        'installer_src.ui.prereqs_page', 'installer_src.ui.downgrade_page',
        'installer_src.ui.install_page', 'installer_src.ui.backup_page',
        'installer_src.ui.complete_page',
    ],
    datas=[
        ('E:/dev(dave)/projects/gta_bridge_launcher/installer_src/data', 'installer_src/data'),
        ('E:/dev(dave)/projects/gta_bridge_launcher/installer_src/ui/splash', 'installer_src/ui/splash'),
    ],
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
    a.binaries,
    a.datas,
    [],
    name='SAS87_Installer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
