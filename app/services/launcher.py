"""定时启停调度线程（按单应用 schedule 触发）。"""
from __future__ import annotations

import threading
from datetime import datetime, time
from typing import Optional

from sqlalchemy.orm import selectinload

from app.config import settings
from app.db import SessionLocal
from app.models import App, LaunchSchedule
from app.services import process_win, usage


class LauncherState:
    def __init__(self):
        self.running = False
        self.last_check_at: Optional[datetime] = None
        self.last_error: Optional[str] = None
        self.last_tick_detail: Optional[str] = None


launcher_state = LauncherState()


def _normalize_time(t: time) -> time:
    return time(hour=t.hour, minute=t.minute, second=getattr(t, "second", 0) or 0)


def _weekday_matches(sch_weekday: int, today_wd: int) -> bool:
    """weekday=-1 表示每天。"""
    if sch_weekday == -1:
        return True
    return sch_weekday == today_wd


class LaunchScheduler:
    def __init__(self):
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="LaunchScheduler", daemon=True
        )
        self._thread.start()
        launcher_state.running = True

    def stop(self):
        self._stop.set()
        launcher_state.running = False

    def _loop(self):
        while not self._stop.is_set():
            try:
                self._tick()
                launcher_state.last_error = None
            except Exception as e:
                launcher_state.last_error = str(e)
            launcher_state.last_check_at = datetime.now()
            self._stop.wait(settings.launcher_interval_seconds)

    def _tick(self):
        db = SessionLocal()
        fired = 0
        skipped_wait = 0
        try:
            now = usage.now_local()
            wd = usage.python_weekday(now)
            fire_grace = float(getattr(settings, "launcher_fire_grace_seconds", 300) or 300)

            schedules = (
                db.query(LaunchSchedule)
                .options(selectinload(LaunchSchedule.app).selectinload(App.windows))
                .filter(LaunchSchedule.enabled == True)  # noqa: E712
                .all()
            )
            for sch in schedules:
                app = sch.app
                if not app or not app.enabled:
                    continue
                if not _weekday_matches(int(sch.weekday), wd):
                    continue
                if sch.last_fired_date == now.date():
                    continue

                launch_t = _normalize_time(sch.launch_time)
                target = datetime.combine(now.date(), launch_t)
                delta = (now - target).total_seconds()
                action = (sch.action or "launch").strip().lower()
                if action not in ("launch", "close"):
                    action = "launch"

                if delta < 0:
                    skipped_wait += 1
                    continue
                if delta > fire_grace:
                    usage.write_audit(
                        db,
                        f"{action}_missed",
                        app.id,
                        f"schedule_id={sch.id}; delta={int(delta)}s > grace={int(fire_grace)}s",
                    )
                    sch.last_fired_date = now.date()
                    continue

                if action == "close":
                    results = process_win.kill_matched(app.process_name, app.exe_path)
                    sch.last_fired_date = now.date()
                    fired += 1
                    killed = sum(1 for r in results if r.get("ok"))
                    for _ in range(killed):
                        usage.bump_kill(db, app.id)
                    usage.write_audit(
                        db,
                        "schedule_close",
                        app.id,
                        f"schedule_id={sch.id}; killed={killed}; results={results}; delta={int(delta)}s",
                    )
                    continue

                # launch
                allowed, reason = usage.evaluate_policy(db, app, session_seconds=0.0, at=now)
                if not allowed:
                    usage.write_audit(
                        db,
                        "launch_deferred",
                        app.id,
                        f"schedule_id={sch.id}; reason={reason}; will_retry",
                    )
                    continue

                ok, msg = process_win.launch_exe(app.exe_path)
                sch.last_fired_date = now.date()
                fired += 1
                if ok:
                    usage.bump_launch(db, app.id)
                    usage.write_audit(
                        db,
                        "launch",
                        app.id,
                        f"schedule_id={sch.id}; {msg}; delta={int(delta)}s",
                    )
                else:
                    usage.write_audit(
                        db,
                        "launch_failed",
                        app.id,
                        f"schedule_id={sch.id}; {msg}",
                    )

            db.commit()
            launcher_state.last_tick_detail = (
                f"checked={len(schedules)} fired={fired} waiting={skipped_wait}"
            )
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


launch_scheduler = LaunchScheduler()
