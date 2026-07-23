"""自动发现本机应用：运行中进程 + 开始菜单快捷方式。"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import psutil

from app.services.process_win import (
    PROTECTED_PROCESS_NAMES,
    normalize_path,
    normalize_process_name,
)


SKIP_NAME_KEYWORDS = (
    "uninstall",
    "setup",
    "update",
    "helper",
    "crashpad",
    "installer",
)


def _is_interesting_exe(path: Optional[str], name: str, require_exists: bool = True) -> bool:
    if not path:
        return False
    try:
        p = Path(path)
    except Exception:
        return False
    if p.suffix.lower() != ".exe":
        return False
    if require_exists:
        try:
            if not p.is_file():
                return False
        except OSError:
            return False
    low = (name or p.name).lower()
    proc = normalize_process_name(p.name)
    if proc in PROTECTED_PROCESS_NAMES:
        return False
    if any(k in low for k in SKIP_NAME_KEYWORDS):
        return False
    norm = normalize_path(path) or ""
    if "\\windows\\system32\\" in norm or "\\windows\\syswow64\\" in norm:
        allow = {"notepad.exe", "calc.exe", "mspaint.exe", "write.exe", "cmd.exe"}
        if proc not in allow:
            return False
    return True


def _item(name: str, exe_path: str, source: str) -> dict:
    p = Path(exe_path)
    return {
        "name": (name or p.stem).strip() or p.stem,
        "exe_path": str(p),
        "process_name": normalize_process_name(p.name),
        "source": source,
    }


def discover_running() -> List[dict]:
    seen: Set[str] = set()
    out: List[dict] = []
    for proc in psutil.process_iter(["name", "exe"]):
        try:
            info = proc.info
            exe = info.get("exe")
            name = info.get("name") or (Path(exe).name if exe else "")
            if not _is_interesting_exe(exe, name):
                continue
            key = normalize_path(exe)
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(_item(Path(exe).stem, exe, "running"))
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
        except Exception:
            continue
    return out


def _start_menu_roots() -> List[Path]:
    roots = []
    appdata = os.environ.get("APPDATA")
    programdata = os.environ.get("PROGRAMDATA")
    if appdata:
        roots.append(Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    if programdata:
        roots.append(Path(programdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    return [r for r in roots if r.is_dir()]


def discover_start_menu(limit: int = 500) -> Tuple[List[dict], Optional[str]]:
    """
    通过 PowerShell + WScript.Shell 解析 .lnk。
    返回 (items, error_message)。失败时 items 可能为空但 error 有说明。
    """
    roots = _start_menu_roots()
    if not roots:
        return [], "start_menu_roots_missing"

    # 用临时 JSON 文件避免控制台编码损坏中文路径
    out_file = Path(tempfile.gettempdir()) / f"atg_discover_{os.getpid()}.json"
    roots_json = json.dumps([str(r) for r in roots], ensure_ascii=False)
    script = f"""
$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$shell = New-Object -ComObject WScript.Shell
$roots = ConvertFrom-Json -InputObject @'
{roots_json}
'@
$items = New-Object System.Collections.Generic.List[object]
$count = 0
foreach ($root in $roots) {{
  if (-not (Test-Path -LiteralPath $root)) {{ continue }}
  Get-ChildItem -LiteralPath $root -Recurse -Filter *.lnk -ErrorAction SilentlyContinue | ForEach-Object {{
    if ($count -ge {int(limit)}) {{ return }}
    try {{
      $s = $shell.CreateShortcut($_.FullName)
      $target = [string]$s.TargetPath
      if ($target -and $target.ToLower().EndsWith('.exe')) {{
        $items.Add([PSCustomObject]@{{ Name = $_.BaseName; Path = $target }})
        $count++
      }}
    }} catch {{}}
  }}
}}
$items | ConvertTo-Json -Compress -Depth 3 | Out-File -FilePath '{out_file.as_posix()}' -Encoding utf8
"""
    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            capture_output=True,
            text=True,
            timeout=60,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if completed.returncode not in (0, None) and not out_file.is_file():
            err = (completed.stderr or completed.stdout or "powershell_failed").strip()
            return [], f"powershell_rc={completed.returncode}:{err[:300]}"

        if not out_file.is_file():
            return [], "powershell_no_output_file"

        raw = out_file.read_text(encoding="utf-8-sig").strip()
        if not raw:
            return [], "powershell_empty_json"

        data = json.loads(raw)
        if data is None:
            return [], "powershell_null_json"
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            return [], "powershell_bad_json_type"

        out: List[dict] = []
        seen: Set[str] = set()
        for item in data:
            if not isinstance(item, dict):
                continue
            name = str(item.get("Name") or "").strip()
            path = str(item.get("Path") or "").strip()
            if not name or not path:
                continue
            if not _is_interesting_exe(path, name, require_exists=True):
                continue
            key = normalize_path(path)
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(_item(name, path, "start_menu"))
        return out, None
    except subprocess.TimeoutExpired:
        return [], "powershell_timeout"
    except Exception as e:
        return [], f"start_menu_exception:{e}"
    finally:
        try:
            if out_file.is_file():
                out_file.unlink()
        except OSError:
            pass


def discover_apps(
    include_start_menu: bool = True,
) -> Tuple[List[dict], Dict[str, object]]:
    """
    合并发现结果。永不抛出到上层；meta 含错误与计数。
    """
    meta: Dict[str, object] = {
        "running_count": 0,
        "start_menu_count": 0,
        "errors": [],
    }
    merged: Dict[str, dict] = {}

    try:
        running = discover_running()
        meta["running_count"] = len(running)
        for item in running:
            key = normalize_path(item["exe_path"]) or item["exe_path"].lower()
            merged[key] = item
    except Exception as e:
        meta["errors"].append(f"running:{e}")

    if include_start_menu:
        try:
            menu_items, err = discover_start_menu()
            meta["start_menu_count"] = len(menu_items)
            if err:
                meta["errors"].append(err)
            for item in menu_items:
                key = normalize_path(item["exe_path"]) or item["exe_path"].lower()
                if key not in merged:
                    merged[key] = item
                else:
                    merged[key]["name"] = item["name"]
                    merged[key]["source"] = "running+start_menu"
        except Exception as e:
            meta["errors"].append(f"start_menu:{e}")

    items = sorted(merged.values(), key=lambda x: x["name"].lower())
    meta["total"] = len(items)
    return items, meta
