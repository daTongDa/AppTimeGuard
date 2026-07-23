"""Windows 进程枚举、匹配、安全终止与启动。"""
from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Set

import psutil

from app.config import settings

# 永不终止的保护名单（小写）
PROTECTED_PROCESS_NAMES: Set[str] = {
    "system",
    "idle",
    "smss.exe",
    "csrss.exe",
    "wininit.exe",
    "services.exe",
    "lsass.exe",
    "svchost.exe",
    "winlogon.exe",
    "explorer.exe",
    "dwm.exe",
    "fontdrvhost.exe",
    "sihost.exe",
    "taskhostw.exe",
    "runtimebroker.exe",
    "searchhost.exe",
    "startmenuexperiencehost.exe",
}


@dataclass
class MatchedProcess:
    pid: int
    name: str
    exe: Optional[str]


def normalize_process_name(name: str) -> str:
    n = (name or "").strip().lower()
    if n and not n.endswith(".exe"):
        n = n + ".exe"
    return n


def normalize_path(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    try:
        return str(Path(path).resolve()).lower()
    except Exception:
        return path.replace("/", "\\").lower()


def is_protected(name: str, exe: Optional[str] = None) -> bool:
    n = normalize_process_name(name)
    if n in PROTECTED_PROCESS_NAMES:
        return True
    # 保护当前解释器自身
    try:
        self_exe = normalize_path(psutil.Process(os.getpid()).exe())
        if exe and self_exe and normalize_path(exe) == self_exe:
            return True
    except Exception:
        pass
    return False


def list_processes() -> List[MatchedProcess]:
    out: List[MatchedProcess] = []
    for proc in psutil.process_iter(["pid", "name", "exe"]):
        try:
            info = proc.info
            name = info.get("name") or ""
            exe = info.get("exe")
            out.append(MatchedProcess(pid=info["pid"], name=name, exe=exe))
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return out


def paths_equal(a: Optional[str], b: Optional[str]) -> bool:
    na, nb = normalize_path(a), normalize_path(b)
    if na and nb and na == nb:
        return True
    if not a or not b:
        return False
    try:
        pa, pb = Path(a), Path(b)
        if pa.is_file() and pb.is_file():
            return pa.resolve().samefile(pb.resolve())
    except Exception:
        pass
    return False


def match_processes(
    process_name: str,
    exe_path: Optional[str] = None,
) -> List[MatchedProcess]:
    """
    有 exe_path 时只按完整路径匹配（避免同名进程误计）。
    无路径时才按进程名匹配。
    """
    want_name = normalize_process_name(process_name)
    want_path = normalize_path(exe_path) if exe_path else None
    matched: List[MatchedProcess] = []
    for p in list_processes():
        if is_protected(p.name, p.exe):
            continue
        p_name = normalize_process_name(p.name)
        p_path = normalize_path(p.exe)
        if want_path:
            if p_path and paths_equal(p_path, want_path):
                matched.append(p)
            # 故意不回退进程名：AccessDenied/同名会把未启动应用误判为在线
            continue
        if p_name == want_name:
            matched.append(p)
    return matched


def get_foreground_process() -> Optional[MatchedProcess]:
    """当前前台窗口对应进程（Windows）。失败返回 None。"""
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return None
        proc = psutil.Process(int(pid.value))
        name = ""
        exe = None
        try:
            name = proc.name() or ""
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        try:
            exe = proc.exe()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            exe = None
        return MatchedProcess(pid=int(pid.value), name=name, exe=exe)
    except Exception:
        return None


def app_is_foreground(
    process_name: str,
    exe_path: Optional[str],
    fg: Optional[MatchedProcess] = None,
) -> bool:
    """登记应用是否为当前前台窗口所属进程。"""
    fg = fg if fg is not None else get_foreground_process()
    if not fg:
        return False
    want_path = normalize_path(exe_path) if exe_path else None
    fg_path = normalize_path(fg.exe)
    if want_path:
        if fg_path and paths_equal(fg_path, want_path):
            return True
        return False
    return normalize_process_name(fg.name) == normalize_process_name(process_name)


def kill_process_tree(pid: int, grace_seconds: Optional[float] = None) -> tuple[bool, str]:
    grace = grace_seconds if grace_seconds is not None else settings.kill_grace_seconds
    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return True, "already_gone"
    except psutil.AccessDenied:
        return False, "access_denied"

    name = ""
    try:
        name = parent.name()
        if is_protected(name, parent.exe() if parent.is_running() else None):
            return False, "protected"
    except Exception:
        pass

    children = []
    try:
        children = parent.children(recursive=True)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        children = []

    targets = children + [parent]
    for proc in targets:
        try:
            if is_protected(proc.name()):
                continue
            proc.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    _, alive = psutil.wait_procs(targets, timeout=grace)
    for proc in alive:
        try:
            if is_protected(proc.name()):
                continue
            proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            return False, f"kill_failed:{e}"

    return True, f"killed:{name or pid}"


def kill_matched(process_name: str, exe_path: Optional[str] = None) -> List[dict]:
    results = []
    for p in match_processes(process_name, exe_path):
        ok, msg = kill_process_tree(p.pid)
        results.append({"pid": p.pid, "name": p.name, "ok": ok, "message": msg})
    return results


def launch_exe(exe_path: str, cwd: Optional[str] = None) -> tuple[bool, str]:
    path = Path(exe_path)
    if not path.is_file():
        return False, f"exe_not_found:{exe_path}"
    try:
        # Windows: 使用独立进程组启动，不阻塞守护进程
        creationflags = 0
        if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
            creationflags |= subprocess.CREATE_NEW_PROCESS_GROUP
        if hasattr(subprocess, "DETACHED_PROCESS"):
            creationflags |= subprocess.DETACHED_PROCESS
        subprocess.Popen(
            [str(path)],
            cwd=cwd or str(path.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            close_fds=True,
        )
        return True, "launched"
    except Exception as e:
        return False, str(e)


def any_running(process_name: str, exe_path: Optional[str] = None) -> bool:
    return len(match_processes(process_name, exe_path)) > 0
