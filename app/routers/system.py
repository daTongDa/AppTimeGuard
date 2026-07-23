"""系统状态与手动操作"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.db import get_db
from app.models import App, UsageDaily
from app.schemas import SystemStatus
from app.services.guard import guard_state, guard_worker
from app.services.launcher import launch_scheduler, launcher_state
from app.services import process_win, usage

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/status", response_model=SystemStatus)
def status(db: Session = Depends(get_db)):
    today = usage.now_local().date()
    kills = (
        db.query(func.coalesce(func.sum(UsageDaily.kill_count), 0))
        .filter(UsageDaily.date == today)
        .scalar()
    )
    tracked = db.query(App).filter(App.enabled == True).count()  # noqa: E712
    snap = guard_state.snapshot()
    fg = snap.get("foreground") or {}
    return SystemStatus(
        guard_running=guard_state.running,
        launcher_running=launcher_state.running,
        last_guard_scan_at=guard_state.last_scan_at,
        last_launcher_check_at=launcher_state.last_check_at,
        launcher_last_error=launcher_state.last_error,
        launcher_last_tick=launcher_state.last_tick_detail,
        today_kill_count=int(kills or 0),
        tracked_apps=tracked,
        host=settings.host,
        port=settings.port,
        usage_foreground_only=bool(settings.usage_foreground_only),
        foreground_pid=fg.get("pid"),
        foreground_name=fg.get("name"),
        foreground_exe=fg.get("exe"),
        foreground_app_id=snap.get("foreground_app_id"),
        foreground_app_name=snap.get("foreground_app_name"),
        live_tracked=int(snap.get("live_apps") or 0),
    )


@router.post("/guard/restart")
def restart_workers():
    guard_worker.stop()
    launch_scheduler.stop()
    guard_worker.start()
    launch_scheduler.start()
    return {"ok": True}


@router.post("/apps/{app_id}/kill-now")
def kill_now(app_id: int, db: Session = Depends(get_db)):
    app = db.query(App).get(app_id)
    if not app:
        raise HTTPException(404, "应用不存在")
    results = process_win.kill_matched(app.process_name, app.exe_path)
    usage.bump_kill(db, app.id)
    usage.write_audit(db, "manual_kill", app.id, str(results))
    db.commit()
    return {"ok": True, "results": results}


@router.post("/apps/{app_id}/launch-now")
def launch_now(app_id: int, db: Session = Depends(get_db)):
    app = db.query(App).options(selectinload(App.windows)).get(app_id)
    if not app:
        raise HTTPException(404, "应用不存在")
    allowed, reason = usage.evaluate_policy(db, app, 0.0)
    if not allowed:
        raise HTTPException(400, detail=f"当前策略不允许启动: {reason}")
    ok, msg = process_win.launch_exe(app.exe_path)
    if ok:
        usage.bump_launch(db, app.id)
        usage.write_audit(db, "manual_launch", app.id, msg)
        db.commit()
        return {"ok": True, "message": msg}
    raise HTTPException(500, detail=msg)


@router.post("/repair-usage")
def repair_usage(db: Session = Depends(get_db)):
    """裁剪异常日用量，并修正被墙钟拉长的会话。"""
    n_daily = usage.clamp_daily_seconds(db)
    n_sess = usage.repair_inflated_sessions(db)
    usage.write_audit(
        db,
        "repair_usage",
        None,
        f"clamped_rows={n_daily}; repaired_sessions={n_sess}",
    )
    db.commit()
    return {"ok": True, "clamped_rows": n_daily, "repaired_sessions": n_sess}


@router.get("/health")
def health():
    return {"status": "ok"}
