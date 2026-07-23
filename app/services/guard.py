"""守护线程：检测进程、累计用量、强制终止。"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, Set

from sqlalchemy.orm import selectinload

from app.config import settings
from app.db import SessionLocal
from app.models import App, UsageSession
from app.services import process_win, usage
from app.services.process_win import MatchedProcess, normalize_path, normalize_process_name


class GuardState:
    def __init__(self):
        self.running = False
        self.last_scan_at: Optional[datetime] = None
        self.last_error: Optional[str] = None
        self._lock = threading.Lock()
        # app_id -> {session_id, started_at, seconds}
        self._live: Dict[int, dict] = {}
        self._last_tick_mono: Optional[float] = None
        self.foreground: Optional[dict] = None
        self.foreground_app_id: Optional[int] = None
        self.foreground_app_name: Optional[str] = None

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "running": self.running,
                "last_scan_at": self.last_scan_at,
                "last_error": self.last_error,
                "live_apps": len(self._live),
                "foreground": self.foreground,
                "foreground_app_id": self.foreground_app_id,
                "foreground_app_name": self.foreground_app_name,
            }


guard_state = GuardState()


def _usage_key(app: App) -> str:
    """同一可执行文件只计一次用量（避免重复登记导致翻倍）。"""
    path = normalize_path(app.exe_path)
    if path:
        return f"path:{path}"
    return f"name:{normalize_process_name(app.process_name)}"


def _close_session(db, live: dict, now: datetime, end_reason: str) -> None:
    sess = db.query(UsageSession).get(live["session_id"])
    if sess and not sess.ended_at:
        sess.ended_at = now
        sess.seconds = float(live.get("seconds") or 0)
        sess.end_reason = end_reason


class GuardWorker:
    def __init__(self):
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        guard_state._last_tick_mono = None
        self._close_orphan_sessions()
        self._thread = threading.Thread(target=self._loop, name="GuardWorker", daemon=True)
        self._thread.start()
        guard_state.running = True

    def stop(self):
        self._stop.set()
        guard_state.running = False

    def _close_orphan_sessions(self):
        """进程重启后收尾未结束会话：按已累计秒数收尾，避免墙钟拉长条。"""
        db = SessionLocal()
        try:
            now = usage.now_local()
            open_rows = (
                db.query(UsageSession)
                .filter(UsageSession.ended_at.is_(None))
                .all()
            )
            for sess in open_rows:
                recorded = float(sess.seconds or 0)
                if recorded > 0 and sess.started_at:
                    ended = sess.started_at + timedelta(seconds=recorded)
                    sess.ended_at = min(ended, now)
                elif sess.started_at:
                    # 无可靠计时：零长关闭，防止时间轴出现「从未启动却占满半天」
                    sess.ended_at = sess.started_at
                    sess.seconds = 0.0
                else:
                    sess.ended_at = now
                    sess.seconds = 0.0
                if not sess.end_reason:
                    sess.end_reason = "restart"
            if open_rows:
                usage.write_audit(
                    db, "session_close_restart", None, f"closed={len(open_rows)}"
                )
            db.commit()
            with guard_state._lock:
                guard_state._live.clear()
        except Exception:
            db.rollback()
        finally:
            db.close()

    def _loop(self):
        while not self._stop.is_set():
            try:
                self._tick()
                guard_state.last_error = None
            except Exception as e:
                guard_state.last_error = str(e)
            guard_state.last_scan_at = datetime.now()
            self._stop.wait(settings.guard_interval_seconds)

    def _elapsed_seconds(self) -> float:
        """按真实墙钟计时；首 tick 不计时，避免重启瞬间灌入一整格。"""
        now_mono = time.monotonic()
        configured = float(settings.guard_interval_seconds or 4.0)
        last = guard_state._last_tick_mono
        guard_state._last_tick_mono = now_mono
        if last is None:
            return 0.0
        raw = now_mono - last
        if raw < 0.2:
            return 0.0
        return min(raw, configured * 2.0)

    def _update_foreground(self, fg: Optional[MatchedProcess], apps: list[App]) -> None:
        fg_info = None
        fg_app_id = None
        fg_app_name = None
        if fg:
            fg_info = {
                "pid": fg.pid,
                "name": fg.name,
                "exe": fg.exe,
            }
            for app in sorted(apps, key=lambda a: a.id):
                if process_win.app_is_foreground(app.process_name, app.exe_path, fg):
                    fg_app_id = app.id
                    fg_app_name = app.name
                    break
        with guard_state._lock:
            guard_state.foreground = fg_info
            guard_state.foreground_app_id = fg_app_id
            guard_state.foreground_app_name = fg_app_name

    def _tick(self):
        db = SessionLocal()
        try:
            apps = (
                db.query(App)
                .options(selectinload(App.windows))
                .filter(App.enabled == True)  # noqa: E712
                .all()
            )
            uniq: Dict[int, App] = {}
            for app in apps:
                uniq[app.id] = app
            apps = list(uniq.values())

            # 同一 exe 只认 id 最小的为主登记，避免重复会话/计时
            primary_by_key: Dict[str, int] = {}
            for app in sorted(apps, key=lambda a: a.id):
                key = _usage_key(app)
                primary_by_key.setdefault(key, app.id)

            elapsed = self._elapsed_seconds()
            now = usage.now_local()
            seen_ids: Set[int] = set()
            credited_keys: Set[str] = set()
            fg = process_win.get_foreground_process()
            self._update_foreground(fg, apps)
            fg_only = bool(settings.usage_foreground_only)

            for app in apps:
                seen_ids.add(app.id)
                running = process_win.any_running(app.process_name, app.exe_path)
                focused = process_win.app_is_foreground(
                    app.process_name, app.exe_path, fg
                )
                live = guard_state._live.get(app.id)
                key = _usage_key(app)
                is_primary = primary_by_key.get(key) == app.id

                # 用量/会话：仅主登记 +（可选）仅前台
                should_track = bool(running and is_primary)
                if fg_only:
                    should_track = bool(should_track and focused)

                if should_track:
                    if not live:
                        sess = UsageSession(app_id=app.id, started_at=now, seconds=0.0)
                        db.add(sess)
                        db.flush()
                        live = {
                            "session_id": sess.id,
                            "started_at": now,
                            "seconds": 0.0,
                        }
                        guard_state._live[app.id] = live

                    credit = elapsed > 0 and key not in credited_keys
                    if credit:
                        credited_keys.add(key)
                        live["seconds"] = float(live.get("seconds") or 0) + elapsed
                        usage.add_usage_seconds(db, app.id, elapsed)
                        sess = db.query(UsageSession).get(live["session_id"])
                        if sess and not sess.ended_at:
                            sess.seconds = live["seconds"]
                else:
                    if live:
                        _close_session(db, live, now, "normal")
                        guard_state._live.pop(app.id, None)
                        live = None

                # 策略击杀：进程在跑就管（含后台），与是否计时无关
                if running and is_primary:
                    session_sec = float((live or {}).get("seconds") or 0)
                    allowed, reason = usage.evaluate_policy(db, app, session_sec, now)
                    if not allowed:
                        results = process_win.kill_matched(app.process_name, app.exe_path)
                        usage.bump_kill(db, app.id)
                        end_reason = usage.reason_to_end(reason)
                        if live:
                            _close_session(db, live, now, end_reason)
                            guard_state._live.pop(app.id, None)
                        usage.write_audit(
                            db,
                            "kill",
                            app.id,
                            f"reason={reason}; results={results}",
                        )

            for aid in list(guard_state._live.keys()):
                if aid not in seen_ids:
                    live = guard_state._live.pop(aid, None)
                    if live:
                        _close_session(db, live, now, "normal")

            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


guard_worker = GuardWorker()
