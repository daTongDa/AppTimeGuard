"""用量聚合与策略判断。"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.models import App, AuditLog, TimeWindow, UsageDaily, UsageSession


WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def now_local() -> datetime:
    return datetime.now()


def python_weekday(dt: Optional[datetime] = None) -> int:
    """返回 0=周一 ... 6=周日（与 plan 一致）。"""
    d = dt or now_local()
    return d.weekday()


def is_within_windows(app: App, at: Optional[datetime] = None) -> bool:
    """若未配置任何时段，视为全天开放；配置后仅在时段内允许。"""
    at = at or now_local()
    windows = list(app.windows or [])
    if not windows:
        return True
    wd = python_weekday(at)
    t = at.time().replace(microsecond=0)
    for w in windows:
        if w.weekday != wd:
            continue
        start: time = w.start_time
        end: time = w.end_time
        if start <= end:
            if start <= t <= end:
                return True
        else:
            # 跨午夜
            if t >= start or t <= end:
                return True
    return False


def get_or_create_daily(db: Session, app_id: int, day: Optional[date] = None) -> UsageDaily:
    day = day or now_local().date()
    row = (
        db.query(UsageDaily)
        .filter(UsageDaily.app_id == app_id, UsageDaily.date == day)
        .first()
    )
    if row:
        return row
    row = UsageDaily(app_id=app_id, date=day, seconds=0.0, kill_count=0, launch_count=0)
    db.add(row)
    db.flush()
    return row


def daily_seconds(db: Session, app_id: int, day: Optional[date] = None) -> float:
    row = (
        db.query(UsageDaily)
        .filter(UsageDaily.app_id == app_id, UsageDaily.date == (day or now_local().date()))
        .first()
    )
    return float(row.seconds) if row else 0.0


def add_usage_seconds(db: Session, app_id: int, seconds: float) -> UsageDaily:
    if seconds <= 0:
        return get_or_create_daily(db, app_id)
    daily = get_or_create_daily(db, app_id)
    new_val = float(daily.seconds or 0) + float(seconds)
    # 硬上限：不超过「今天已过去的秒数」与 24h（取较小）
    now = now_local()
    elapsed_today = (now - datetime.combine(now.date(), time.min)).total_seconds()
    cap = min(max(elapsed_today + 60.0, 60.0), 24 * 3600.0)  # +60s 余量
    daily.seconds = min(new_val, cap)
    return daily


def clamp_daily_seconds(db: Session) -> int:
    """将超量日用量裁剪到合理上限，返回修正条数。"""
    now = now_local()
    today = now.date()
    elapsed_today = (now - datetime.combine(today, time.min)).total_seconds()
    today_cap = min(max(elapsed_today + 60.0, 60.0), 24 * 3600.0)
    rows = db.query(UsageDaily).filter(UsageDaily.seconds > 0).all()
    n = 0
    for row in rows:
        cap = today_cap if row.date == today else 24 * 3600.0
        if float(row.seconds or 0) > cap:
            row.seconds = cap
            n += 1
    return n


def repair_inflated_sessions(db: Session) -> int:
    """
    修正异常会话跨度。
    旧逻辑在 restart 时用墙钟写入 seconds，会造成「未真正使用却占满数小时」。
    """
    n = 0
    rows = db.query(UsageSession).filter(UsageSession.started_at.isnot(None)).all()
    for sess in rows:
        if not sess.ended_at:
            continue
        wall = (sess.ended_at - sess.started_at).total_seconds()
        if wall < 0:
            sess.ended_at = sess.started_at
            sess.seconds = 0.0
            n += 1
            continue
        recorded = float(sess.seconds or 0)
        reason = sess.end_reason or ""

        # 旧 bug：restart 时把 seconds 直接设成墙钟 → 两者几乎相等且很长
        if reason == "restart" and wall > 120 and recorded > 0 and abs(wall - recorded) < 30:
            sess.ended_at = sess.started_at
            sess.seconds = 0.0
            n += 1
            continue

        if recorded > 0 and wall > recorded + 90:
            fixed = sess.started_at + timedelta(seconds=recorded)
            if fixed <= sess.ended_at:
                sess.ended_at = fixed
                n += 1
            continue

        if recorded <= 0 and wall > 60:
            if reason == "restart" or wall > 3600:
                sess.ended_at = sess.started_at
                sess.seconds = 0.0
                n += 1
    return n


def union_interval_seconds(intervals: list[tuple[float, float]]) -> float:
    """合并重叠区间后求总秒数。"""
    if not intervals:
        return 0.0
    ordered = sorted(
        ((float(a), float(b)) for a, b in intervals if b > a),
        key=lambda x: x[0],
    )
    if not ordered:
        return 0.0
    total = 0.0
    cur_s, cur_e = ordered[0]
    for s, e in ordered[1:]:
        if s <= cur_e:
            cur_e = max(cur_e, e)
        else:
            total += cur_e - cur_s
            cur_s, cur_e = s, e
    total += cur_e - cur_s
    return total


def day_session_clips(
    db: Session,
    day: Optional[date] = None,
    at: Optional[datetime] = None,
) -> list[dict]:
    """
    某日会话裁剪片段（与时间轴一致）。
    未结束会话用 at/now 作为临时终点。
    返回 [{app_id, start_sec, end_sec, duration_sec}, ...]
    """
    at = at or now_local()
    day = day or at.date()
    day_start = datetime.combine(day, time.min)
    day_end = day_start + timedelta(days=1)
    rows = (
        db.query(UsageSession)
        .filter(UsageSession.started_at < day_end)
        .filter(
            (UsageSession.ended_at.is_(None))
            | (UsageSession.ended_at > day_start)
        )
        .all()
    )
    out: list[dict] = []
    for s in rows:
        if not s.started_at:
            continue
        end = s.ended_at or at
        clip_start = max(s.started_at, day_start)
        clip_end = min(end, day_end)
        if clip_end <= clip_start:
            continue
        dur = (clip_end - clip_start).total_seconds()
        out.append(
            {
                "app_id": s.app_id,
                "start_sec": (clip_start - day_start).total_seconds(),
                "end_sec": (clip_end - day_start).total_seconds(),
                "duration_sec": dur,
                "ongoing": s.ended_at is None,
            }
        )
    return out


def day_active_seconds(
    db: Session,
    day: Optional[date] = None,
    at: Optional[datetime] = None,
) -> tuple[float, dict[int, float]]:
    """
    按前台会话墙钟汇总：同时间多应用不叠加。
    返回 (全日并集秒数, {app_id: 该应用并集秒数})。
    """
    clips = day_session_clips(db, day=day, at=at)
    wall = union_interval_seconds([(c["start_sec"], c["end_sec"]) for c in clips])
    by_app: dict[int, list[tuple[float, float]]] = {}
    for c in clips:
        by_app.setdefault(c["app_id"], []).append((c["start_sec"], c["end_sec"]))
    per_app = {
        aid: union_interval_seconds(ivs) for aid, ivs in by_app.items()
    }
    return wall, per_app


def app_usage_seconds_last_days(
    db: Session,
    days: int = 7,
    at: Optional[datetime] = None,
) -> dict[int, float]:
    """近 N 天各应用前台会话时长（按日并集后再累加）。"""
    at = at or now_local()
    days = max(1, int(days))
    totals: dict[int, float] = {}
    for i in range(days):
        day = at.date() - timedelta(days=days - 1 - i)
        _, per_app = day_active_seconds(db, day=day, at=at)
        for aid, sec in per_app.items():
            totals[aid] = float(totals.get(aid, 0.0)) + float(sec or 0)
    return totals



def bump_kill(db: Session, app_id: int) -> None:
    daily = get_or_create_daily(db, app_id)
    daily.kill_count = int(daily.kill_count or 0) + 1


def bump_launch(db: Session, app_id: int) -> None:
    daily = get_or_create_daily(db, app_id)
    daily.launch_count = int(daily.launch_count or 0) + 1


def write_audit(db: Session, action: str, app_id: Optional[int], detail: str) -> None:
    db.add(AuditLog(action=action, app_id=app_id, detail=detail, created_at=now_local()))


def over_daily_limit(app: App, used_seconds: float) -> bool:
    if not app.daily_limit_minutes:
        return False
    return used_seconds >= app.daily_limit_minutes * 60


def over_session_limit(session_seconds: float, app: App) -> bool:
    if not app.session_limit_minutes:
        return False
    return session_seconds >= app.session_limit_minutes * 60


def evaluate_policy(
    db: Session,
    app: App,
    session_seconds: float,
    at: Optional[datetime] = None,
) -> Tuple[bool, str]:
    """
    返回 (allowed, reason)。
    allowed=False 时应强制杀进程。
    """
    at = at or now_local()
    if not app.enabled:
        return False, "disabled"
    if not is_within_windows(app, at):
        return False, "outside_window"
    used = daily_seconds(db, app.id, at.date())
    if over_daily_limit(app, used):
        return False, "daily_limit"
    if over_session_limit(session_seconds, app):
        return False, "session_limit"
    return True, "ok"


def reason_to_end(reason: str) -> str:
    if reason in ("outside_window",):
        return "killed_window"
    if reason in ("daily_limit", "session_limit", "disabled"):
        return "killed_limit"
    return "killed_limit"
