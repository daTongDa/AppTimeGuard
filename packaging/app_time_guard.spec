# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec：生成 app_time_guard.exe（单文件）。"""
from pathlib import Path

block_cipher = None
# spec 在 packaging/ 下，项目根为其上级
root = Path(SPECPATH).resolve().parent

a = Analysis(
    [str(root / "app_time_guard_entry.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[
        (str(root / "static"), "static"),
    ],
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "uvicorn.lifespan.off",
        "app.main",
        "app.models",
        "app.db",
        "app.config",
        "app.paths",
        "app.routers.apps",
        "app.routers.windows",
        "app.routers.schedules",
        "app.routers.stats",
        "app.routers.system",
        "app.routers.discover",
        "app.routers.icons",
        "app.services.guard",
        "app.services.launcher",
        "app.services.usage",
        "app.services.process_win",
        "app.services.discover",
        "app.services.category",
        "app.services.icons",
        "pydantic_settings",
        "sqlalchemy.sql.default_comparator",
        "multipart",
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
    name="app_time_guard",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
