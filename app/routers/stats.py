"""统计与审计"""
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import App, AuditLog, UsageDaily, UsageSession
from app.schemas import AuditLogOut, UsageDailyOut
from app.services.category import CATEGORY_LABELS, normalize_category
from app.services.usage import day_active_seconds, now_local, union_interval_seconds

router = APIRouter(prefix="/api/stats", tags=["stats"])


def _cap_day_seconds(sec: float) -> float:
    """展示/汇总时再保险：单日不超过 24h。"""
    return min(max(float(sec or 0), 0.0), 24 * 3600.0)


def _app_maps(db: Session):
    apps = db.query(App).all()
    names = {a.id: a.name for a in apps}
    cats = {a.id: normalize_category(getattr(a, "category", None)) for a in apps}
    paths = {a.id: a.exe_path for a in apps}
    return names, cats, paths



@router.get("/daily", response_model=List[UsageDailyOut])
def daily_stats(
    days: int = Query(7, ge=1, le=90),
    app_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    start = now_local().date() - timedelta(days=days - 1)
    q = db.query(UsageDaily).filter(UsageDaily.date >= start)
    if app_id:
        q = q.filter(UsageDaily.app_id == app_id)
    rows = q.order_by(UsageDaily.date.desc(), UsageDaily.app_id).all()
    names, _, _ = _app_maps(db)
    return [
        UsageDailyOut(
            app_id=r.app_id,
            app_name=names.get(r.app_id),
            date=r.date,
            seconds=float(r.seconds or 0),
            kill_count=int(r.kill_count or 0),
            launch_count=int(r.launch_count or 0),
        )
        for r in rows
    ]


@router.get("/today")
def today_summary(db: Session = Depends(get_db)):
    """
    今日报告。
    合计与分项时长来自前台会话：同时间不叠加、不含纯后台。
    击杀/启动仍取 UsageDaily 计数。
    """
    now = now_local()
    today = now.date()
    names, cats, paths = _app_maps(db)

    wall_sec, per_app = day_active_seconds(db, day=today, at=now)
    wall_sec = _cap_day_seconds(wall_sec)

    daily_rows = {
        r.app_id: r
        for r in db.query(UsageDaily).filter(UsageDaily.date == today).all()
    }

    app_ids = set(per_app.keys()) | set(daily_rows.keys())
    items = []
    by_cat: Dict[str, float] = {}
    for aid in app_ids:
        sec = _cap_day_seconds(per_app.get(aid, 0.0))
        cat = cats.get(aid, "other")
        if sec > 0:
            by_cat[cat] = by_cat.get(cat, 0.0) + sec
        daily = daily_rows.get(aid)
        items.append(
            {
                "app_id": aid,
                "app_name": names.get(aid) or f"#{aid}",
                "category": cat,
                "category_label": CATEGORY_LABELS.get(cat, "其他"),
                "exe_path": paths.get(aid),
                "seconds": sec,
                "minutes": round(sec / 60, 1),
                "kill_count": int(daily.kill_count or 0) if daily else 0,
                "launch_count": int(daily.launch_count or 0) if daily else 0,
            }
        )

    items = [i for i in items if i["seconds"] > 0 or i["kill_count"] or i["launch_count"]]
    items.sort(key=lambda x: x["seconds"], reverse=True)

    sum_app = sum(i["seconds"] for i in items) or 0.0
    for i in items:
        i["share_pct"] = round(i["seconds"] / sum_app * 100, 1) if sum_app > 0 else 0.0

    categories = [
        {
            "category": c,
            "label": CATEGORY_LABELS.get(c, c),
            "seconds": s,
            "minutes": round(s / 60, 1),
            "share_pct": round(s / sum_app * 100, 1) if sum_app > 0 else 0.0,
        }
        for c, s in sorted(by_cat.items(), key=lambda x: -x[1])
    ]
    top = next((i for i in items if i["seconds"] > 0), None)
    return {
        "date": today.isoformat(),
        "total_seconds": wall_sec,
        "total_minutes": round(wall_sec / 60, 1),
        "total_mode": "foreground_union",
        "stacked_seconds": round(sum_app, 3),
        "stacked_minutes": round(sum_app / 60, 1),
        "total_kills": sum(i["kill_count"] for i in items),
        "total_launches": sum(i["launch_count"] for i in items),
        "app_count": len([i for i in items if i["seconds"] > 0]),
        "top_app": top,
        "categories": categories,
        "items": items,
    }


@router.get("/report")
def usage_report(
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
):
    """历史用量报告：按日序列 + 应用排行 + 分类汇总。"""
    today = now_local().date()
    start = today - timedelta(days=days - 1)
    rows = (
        db.query(UsageDaily)
        .filter(UsageDaily.date >= start, UsageDaily.date <= today)
        .all()
    )
    names, cats, paths = _app_maps(db)

    by_date: Dict[str, Dict] = {}
    by_app: Dict[int, Dict] = {}
    by_cat: Dict[str, float] = {}

    for r in rows:
        sec = _cap_day_seconds(r.seconds)
        dkey = r.date.isoformat()
        slot = by_date.setdefault(
            dkey, {"date": dkey, "seconds": 0.0, "kill_count": 0, "launch_count": 0, "app_count": 0}
        )
        if sec > 0 or int(r.kill_count or 0) or int(r.launch_count or 0):
            slot["app_count"] += 1
        slot["seconds"] += sec
        slot["kill_count"] += int(r.kill_count or 0)
        slot["launch_count"] += int(r.launch_count or 0)

        app = by_app.setdefault(
            r.app_id,
            {
                "app_id": r.app_id,
                "app_name": names.get(r.app_id) or f"#{r.app_id}",
                "category": cats.get(r.app_id, "other"),
                "exe_path": paths.get(r.app_id),
                "seconds": 0.0,
                "kill_count": 0,
                "launch_count": 0,
                "active_days": 0,
            },
        )
        if sec > 0:
            app["active_days"] += 1
        app["seconds"] += sec
        app["kill_count"] += int(r.kill_count or 0)
        app["launch_count"] += int(r.launch_count or 0)

        cat = cats.get(r.app_id, "other")
        by_cat[cat] = by_cat.get(cat, 0.0) + sec

    daily_series = []
    for i in range(days):
        d = start + timedelta(days=i)
        key = d.isoformat()
        slot = by_date.get(key) or {
            "date": key,
            "seconds": 0.0,
            "kill_count": 0,
            "launch_count": 0,
            "app_count": 0,
        }
        daily_series.append(
            {
                **slot,
                "label": f"{d.month}/{d.day}",
                "weekday": d.weekday(),
                "weekday_label": ["一", "二", "三", "四", "五", "六", "日"][d.weekday()],
                "minutes": round(slot["seconds"] / 60, 1),
            }
        )

    total_seconds = sum(x["seconds"] for x in daily_series)
    apps_rank = sorted(by_app.values(), key=lambda x: x["seconds"], reverse=True)
    for a in apps_rank:
        a["minutes"] = round(a["seconds"] / 60, 1)
        a["share_pct"] = (
            round(a["seconds"] / total_seconds * 100, 1) if total_seconds > 0 else 0.0
        )
        a["category_label"] = CATEGORY_LABELS.get(a["category"], "其他")
        a["avg_minutes_per_active_day"] = (
            round(a["minutes"] / a["active_days"], 1) if a["active_days"] else 0.0
        )

    categories = [
        {
            "category": c,
            "label": CATEGORY_LABELS.get(c, c),
            "seconds": s,
            "minutes": round(s / 60, 1),
            "share_pct": round(s / total_seconds * 100, 1) if total_seconds > 0 else 0.0,
        }
        for c, s in sorted(by_cat.items(), key=lambda x: -x[1])
    ]

    peak = max(daily_series, key=lambda x: x["seconds"]) if daily_series else None
    return {
        "days": days,
        "start": start.isoformat(),
        "end": today.isoformat(),
        "total_seconds": total_seconds,
        "total_minutes": round(total_seconds / 60, 1),
        "avg_minutes_per_day": round(total_seconds / 60 / days, 1) if days else 0.0,
        "total_kills": sum(x["kill_count"] for x in daily_series),
        "total_launches": sum(x["launch_count"] for x in daily_series),
        "active_app_count": len([a for a in apps_rank if a["seconds"] > 0]),
        "peak_day": peak,
        "top_app": apps_rank[0] if apps_rank else None,
        "daily_series": daily_series,
        "by_app": apps_rank,
        "categories": categories,
        "details": [
            {
                "date": r.date.isoformat(),
                "app_id": r.app_id,
                "app_name": names.get(r.app_id) or f"#{r.app_id}",
                "category": cats.get(r.app_id, "other"),
                "category_label": CATEGORY_LABELS.get(
                    cats.get(r.app_id, "other"), "其他"
                ),
                "seconds": _cap_day_seconds(r.seconds),
                "minutes": round(_cap_day_seconds(r.seconds) / 60, 1),
                "kill_count": int(r.kill_count or 0),
                "launch_count": int(r.launch_count or 0),
            }
            for r in sorted(rows, key=lambda x: (x.date, -float(x.seconds or 0)), reverse=True)
        ],
    }


@router.get("/timeline")
def usage_timeline(
    day: Optional[str] = Query(None, description="YYYY-MM-DD，默认今天"),
    db: Session = Depends(get_db),
):
    """
    某日 24h 会话时间轴数据。
    未结束会话 ended_at 为空，前端用当前时间作为临时终点。
    """
    now = now_local()
    if day:
        try:
            the_day = datetime.strptime(day, "%Y-%m-%d").date()
        except ValueError as e:
            raise HTTPException(400, f"日期格式错误: {e}")
    else:
        the_day = now.date()

    day_start = datetime.combine(the_day, time(0, 0, 0))
    day_end = day_start + timedelta(days=1)

    names, cats, paths = _app_maps(db)
    rows = (
        db.query(UsageSession)
        .filter(UsageSession.started_at < day_end)
        .filter(
            (UsageSession.ended_at.is_(None))
            | (UsageSession.ended_at > day_start)
        )
        .order_by(UsageSession.started_at.asc())
        .all()
    )

    palette = [
        "#0d7a6f", "#1570ef", "#dc6803", "#7a5af8", "#dd2590",
        "#039855", "#b54708", "#3538cd", "#e31b54", "#088ab2",
        "#667085", "#12b76a", "#f04438", "#9e77ed", "#ee46bc",
    ]

    sessions = []
    app_ids_order = []
    for s in rows:
        start = s.started_at
        end = s.ended_at or now
        clip_start = max(start, day_start)
        clip_end = min(end, day_end)
        if clip_end <= clip_start:
            continue
        if s.app_id not in app_ids_order:
            app_ids_order.append(s.app_id)
        color = palette[s.app_id % len(palette)]
        dur = (clip_end - clip_start).total_seconds()
        sessions.append(
            {
                "id": s.id,
                "app_id": s.app_id,
                "app_name": names.get(s.app_id) or f"#{s.app_id}",
                "category": cats.get(s.app_id, "other"),
                "category_label": CATEGORY_LABELS.get(
                    cats.get(s.app_id, "other"), "其他"
                ),
                "exe_path": paths.get(s.app_id),
                "color": color,
                "started_at": start.isoformat(sep=" ", timespec="seconds"),
                "ended_at": s.ended_at.isoformat(sep=" ", timespec="seconds")
                if s.ended_at
                else None,
                "ongoing": s.ended_at is None,
                "end_reason": s.end_reason,
                "clip_start": clip_start.isoformat(sep=" ", timespec="seconds"),
                "clip_end": clip_end.isoformat(sep=" ", timespec="seconds"),
                "start_sec": (clip_start - day_start).total_seconds(),
                "end_sec": (clip_end - day_start).total_seconds(),
                "duration_sec": dur,
                "duration_min": round(dur / 60, 1),
            }
        )

    lanes = []
    for aid in app_ids_order:
        app_sessions = [x for x in sessions if x["app_id"] == aid]
        union_sec = union_interval_seconds(
            [(x["start_sec"], x["end_sec"]) for x in app_sessions]
        )
        lanes.append(
            {
                "app_id": aid,
                "app_name": names.get(aid) or f"#{aid}",
                "category": cats.get(aid, "other"),
                "color": palette[aid % len(palette)],
                "exe_path": paths.get(aid),
                "sessions": app_sessions,
                "total_min": round(union_sec / 60, 1),
                "raw_sum_min": round(
                    sum(x["duration_sec"] for x in app_sessions) / 60, 1
                ),
            }
        )

    return {
        "date": the_day.isoformat(),
        "day_start": day_start.isoformat(sep=" ", timespec="seconds"),
        "day_end": day_end.isoformat(sep=" ", timespec="seconds"),
        "now": now.isoformat(sep=" ", timespec="seconds"),
        "is_today": the_day == now.date(),
        "session_count": len(sessions),
        "lane_count": len(lanes),
        "lanes": lanes,
        "sessions": sessions,
    }


@router.get("/audit", response_model=list[AuditLogOut])
def audit_logs(limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    return (
        db.query(AuditLog)
        .order_by(AuditLog.id.desc())
        .limit(limit)
        .all()
    )
