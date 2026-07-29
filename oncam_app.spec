# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['core/main.py'],
    pathex=[],
    binaries=[
        ('yolov5su.pt', '.'),
    ],
    datas=[
        ('translations', 'translations'),
        ('camera', 'camera'),
        ('ptz', 'ptz'),
        ('rangefinder', 'rangefinder'),
        ('relayx3', 'relayx3'),
        ('rlf', 'rlf'),
        ('ui', 'ui'),
        ('core', 'core'),
    ],
    hiddenimports=[
        'PyQt6',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'cv2',
        'numpy',
        'onvif',
        'zeep',
        'serial',
        'torch',
        'ultralytics',
        'requests',
        'PIL',
        'pkg_resources.py2_warn',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='OnCam',
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
    icon=None,
)
