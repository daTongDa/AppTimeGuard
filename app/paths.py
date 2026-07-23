"""运行路径：开发目录 vs PyInstaller 冻结包。"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False)) and hasattr(sys, "_MEIPASS")


def resource_dir() -> Path:
    """只读资源根目录（含 static）。"""
    if is_frozen():
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent


def app_data_dir() -> Path:
    """可写数据目录（SQLite、缓存）。安装版用 LocalAppData。"""
    if is_frozen():
        root = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        d = root / "AppTimeGuard"
    else:
        d = Path(__file__).resolve().parent.parent / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def static_dir() -> Path:
    return resource_dir() / "static"
