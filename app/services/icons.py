"""从 Windows exe 提取关联图标，磁盘缓存。"""
from __future__ import annotations

import hashlib
import subprocess
import tempfile
from pathlib import Path
from typing import Tuple

from app.config import DATA_DIR

# 合法 1×1 透明 PNG
_PLACEHOLDER_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)


def _cache_dir() -> Path:
    d = DATA_DIR / "icon_cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_key(exe_path: str) -> str:
    p = Path(exe_path)
    try:
        mtime = p.stat().st_mtime_ns
    except OSError:
        mtime = 0
    try:
        resolved = str(p.resolve())
    except OSError:
        resolved = exe_path
    raw = f"{resolved}|{mtime}".encode("utf-8", "ignore")
    return hashlib.sha1(raw).hexdigest()


def extract_icon_png(exe_path: str, size: int = 32) -> Tuple[bytes, str]:
    """返回 (png_bytes, source_tag)。失败时返回占位图，不抛异常。"""
    path = (exe_path or "").strip().strip('"')
    if not path:
        return _PLACEHOLDER_PNG, "placeholder"
    p = Path(path)
    if not p.is_file() or p.suffix.lower() not in (".exe", ".dll", ".ico"):
        return _PLACEHOLDER_PNG, "placeholder"

    key = _cache_key(path)
    cache_file = _cache_dir() / f"{key}_{int(size)}.png"
    if cache_file.is_file() and cache_file.stat().st_size > 32:
        try:
            return cache_file.read_bytes(), "cached"
        except OSError:
            pass

    with tempfile.TemporaryDirectory(prefix="atg_icon_") as td:
        out_png = Path(td) / "icon.png"
        ps_script = Path(td) / "extract.ps1"
        script = (
            "$ErrorActionPreference = 'Stop'\n"
            "Add-Type -AssemblyName System.Drawing\n"
            f"$src = @'\n{path}\n'@\n"
            f"$dest = @'\n{out_png.as_posix()}\n'@\n"
            "try {\n"
            "  $icon = [System.Drawing.Icon]::ExtractAssociatedIcon($src.Trim())\n"
            "  if ($null -eq $icon) { exit 2 }\n"
            "  $bmp = $icon.ToBitmap()\n"
            f"  $size = {int(size)}\n"
            "  $resized = New-Object System.Drawing.Bitmap $size, $size\n"
            "  $g = [System.Drawing.Graphics]::FromImage($resized)\n"
            "  $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic\n"
            "  $g.DrawImage($bmp, 0, 0, $size, $size)\n"
            "  $g.Dispose()\n"
            "  $resized.Save($dest.Trim(), [System.Drawing.Imaging.ImageFormat]::Png)\n"
            "  $icon.Dispose(); $bmp.Dispose(); $resized.Dispose()\n"
            "  exit 0\n"
            "} catch { exit 1 }\n"
        )
        ps_script.write_text(script, encoding="utf-8")
        try:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            r = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(ps_script),
                ],
                capture_output=True,
                timeout=8,
                creationflags=flags,
            )
            if r.returncode == 0 and out_png.is_file() and out_png.stat().st_size > 32:
                data = out_png.read_bytes()
                try:
                    cache_file.write_bytes(data)
                except OSError:
                    pass
                return data, "extracted"
        except Exception:
            pass

    return _PLACEHOLDER_PNG, "placeholder"
