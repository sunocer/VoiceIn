# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
root = Path(SPECPATH)
assets = root / "voicein_windows" / "assets"
a = Analysis(
    [str(root / "voicein_windows" / "launcher.pyw")],
    pathex=[str(root)],
    binaries=[],
    datas=[
        (str(root / "voicein_windows" / "static"), "voicein_windows/static"),
        (str(root / "voicein_windows" / "codex_bridge.cjs"), "voicein_windows"),
    ],
    hiddenimports=["sounddevice", "pynput.keyboard._win32", "pystray._win32", "PIL.ImageTk"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="VoiceIn-0.1.0-alpha-win-x64",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(assets / "voicein.ico"),
    version=str(root / "voicein_windows" / "version_info.txt"),
)

