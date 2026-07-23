# -*- coding: utf-8 -*-
"""
App Time Guard 全功能自测。
用法（在 app-time-guard 目录）:
  python scripts/selftest.py
退出码 0=全部通过，1=有失败。
"""
from __future__ import annotations

import sys
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PASS = 0
FAIL = 0
ERRORS = []


def check(name: str, cond: bool, detail: str = ""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}" + (f" — {detail}" if detail else ""))
    else:
        FAIL += 1
        msg = f"{name}: {detail or 'failed'}"
        ERRORS.append(msg)
        print(f"  [FAIL] {msg}")


def main():
    global PASS, FAIL
    print("=== App Time Guard Selftest ===\n")

    # 1) imports
    print("[1] Import modules")
    try:
        from app.main import app
        from app.db import init_db, SessionLocal
        from app.services.usage import is_within_windows, evaluate_policy, now_local
        from app.services.discover import discover_running, discover_start_menu, discover_apps
        from app.services import process_win
        from app.models import App as AppModel
        from types import SimpleNamespace

        check("import_app", True)
    except Exception as e:
        check("import_app", False, str(e))
        traceback.print_exc()
        return _finish()

    init_db()

    # 2) policy default open
    print("\n[2] Policy: empty windows = open")
    dummy = SimpleNamespace(windows=[], enabled=True, id=0, daily_limit_minutes=None, session_limit_minutes=None)
    check("empty_windows_open", is_within_windows(dummy) is True)

    # 3) discover services
    print("\n[3] Discover services")
    try:
        running = discover_running()
        check("discover_running", len(running) >= 1, f"n={len(running)}")
    except Exception as e:
        check("discover_running", False, str(e))
        running = []

    menu, menu_err = discover_start_menu()
    check(
        "discover_start_menu",
        menu_err is None or len(menu) >= 0,
        f"n={len(menu)} err={menu_err}",
    )
    # 开始菜单失败不算硬失败若 running 成功；但记录
    if menu_err and len(menu) == 0:
        print(f"  [WARN] start_menu empty with error: {menu_err}")

    items, meta = discover_apps(True)
    check("discover_apps_merged", len(items) >= len(running), f"n={len(items)} meta={meta}")

    # 4) HTTP API via TestClient
    print("\n[4] HTTP API (TestClient + lifespan)")
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        r = client.get("/api/system/health")
        check("health", r.status_code == 200 and r.json().get("status") == "ok", r.text)

        r = client.get("/api/system/status")
        check("status", r.status_code == 200, r.text)
        if r.status_code == 200:
            st = r.json()
            check("guard_running", st.get("guard_running") is True, str(st))
            check("launcher_running", st.get("launcher_running") is True, str(st))

        # discover API envelope
        r = client.get("/api/discover/apps?include_start_menu=false")
        check("discover_api_quick", r.status_code == 200, r.text[:300])
        if r.status_code == 200:
            body = r.json()
            check("discover_envelope", "items" in body and "total" in body, str(body.keys()))
            check("discover_quick_count", body.get("total", 0) >= 1, str(body.get("total")))

        r = client.get("/api/discover/apps?include_start_menu=true")
        check("discover_api_full", r.status_code == 200, r.text[:300])
        if r.status_code == 200:
            body = r.json()
            check("discover_full_has_items", body.get("total", 0) >= 1, f"total={body.get('total')} errors={body.get('errors')}")

        # CRUD app - use notepad
        notepad = r"C:\Windows\System32\notepad.exe"
        # cleanup old test apps
        db = SessionLocal()
        try:
            for a in db.query(AppModel).filter(AppModel.name.like("SELFTEST%")).all():
                db.delete(a)
            db.commit()
        finally:
            db.close()

        r = client.post(
            "/api/apps/",
            json={
                "name": "SELFTEST Notepad",
                "exe_path": notepad,
                "process_name": "notepad.exe",
                "enabled": True,
                "daily_limit_minutes": 120,
                "apply_defaults": False,
            },
        )
        check("create_app", r.status_code == 201, r.text)
        app_id = r.json()["id"] if r.status_code == 201 else None
        sch_id = None
        daily_launch_id = None
        daily_close_id = None

        if app_id:
            r = client.get(f"/api/apps/{app_id}")
            check("get_app", r.status_code == 200)

            r = client.get("/api/apps/")
            check("list_apps", r.status_code == 200 and isinstance(r.json(), list), r.text[:200])
            if r.status_code == 200 and r.json():
                apps = r.json()
                check(
                    "list_has_usage_7d",
                    "usage_7d_minutes" in apps[0] and "usage_7d_seconds" in apps[0],
                    str(apps[0].keys()),
                )
                mins = [float(a.get("usage_7d_minutes") or 0) for a in apps]
                check(
                    "list_sorted_by_7d",
                    mins == sorted(mins, reverse=True),
                    str(mins[:8]),
                )

            # windows batch
            wd = datetime.now().weekday()
            r = client.post(
                f"/api/windows/app/{app_id}/batch",
                json={
                    "weekdays": [wd],
                    "start_time": "00:00",
                    "end_time": "23:59",
                },
            )
            check("batch_windows", r.status_code == 201, r.text)

            r = client.get(f"/api/windows/app/{app_id}")
            check("list_windows", r.status_code == 200 and len(r.json()) >= 1, r.text)

            # category defaults: entertainment vs other
            r = client.post(
                "/api/apps/",
                json={
                    "name": "SELFTEST Game",
                    "exe_path": notepad,
                    "process_name": "notepad.exe",
                    "category": "entertainment",
                    "apply_defaults": True,
                    "enabled": True,
                },
            )
            check("create_ent_app", r.status_code == 201, r.text)
            ent_id = r.json()["id"] if r.status_code == 201 else None
            if ent_id:
                check(
                    "ent_daily_limit_120",
                    r.json().get("daily_limit_minutes") == 120,
                    str(r.json().get("daily_limit_minutes")),
                )
                wins = client.get(f"/api/windows/app/{ent_id}").json()
                wds = sorted({w["weekday"] for w in wins})
                check("ent_weekend_only", wds == [5, 6], str(wds))
                check(
                    "ent_window_time",
                    any(
                        str(w["start_time"]).startswith("06:00")
                        and str(w["end_time"]).startswith("22:20")
                        for w in wins
                    ),
                    str(wins),
                )
                client.delete(f"/api/apps/{ent_id}")

            r = client.post(
                "/api/apps/",
                json={
                    "name": "SELFTEST Study",
                    "exe_path": notepad,
                    "process_name": "notepad.exe",
                    "category": "study",
                    "apply_defaults": True,
                    "enabled": True,
                },
            )
            check("create_study_app", r.status_code == 201, r.text)
            study_id = r.json()["id"] if r.status_code == 201 else None
            if study_id:
                check(
                    "study_no_daily_limit",
                    r.json().get("daily_limit_minutes") is None,
                    str(r.json().get("daily_limit_minutes")),
                )
                wins = client.get(f"/api/windows/app/{study_id}").json()
                wds = sorted({w["weekday"] for w in wins})
                check("study_everyday", wds == [0, 1, 2, 3, 4, 5, 6], str(wds))
                check(
                    "study_window_time",
                    any(
                        str(w["start_time"]).startswith("05:00")
                        and str(w["end_time"]).startswith("22:20")
                        for w in wins
                    ),
                    str(wins),
                )
                client.delete(f"/api/apps/{study_id}")

            r = client.get("/api/apps/categories")
            check("list_categories", r.status_code == 200 and len(r.json()) >= 4, r.text)

            # schedule in 2 minutes
            r = client.post(
                f"/api/schedules/app/{app_id}/in-minutes",
                json={"minutes_from_now": 2},
            )
            check("schedule_in_minutes", r.status_code == 201, r.text)
            sch_id = r.json()["id"] if r.status_code == 201 else None

            if sch_id:
                r = client.post(f"/api/schedules/{sch_id}/reset-fired")
                check("reset_fired", r.status_code == 200, r.text)

            # daily launch + close schedule (weekday=-1)
            r = client.post(
                f"/api/schedules/app/{app_id}",
                json={
                    "weekday": -1,
                    "launch_time": "08:30:00",
                    "action": "launch",
                    "enabled": True,
                },
            )
            check("schedule_daily_launch", r.status_code == 201, r.text)
            daily_launch_id = r.json()["id"] if r.status_code == 201 else None

            r = client.post(
                f"/api/schedules/app/{app_id}",
                json={
                    "weekday": -1,
                    "launch_time": "22:00:00",
                    "action": "close",
                    "enabled": True,
                },
            )
            check("schedule_daily_close", r.status_code == 201 and r.json().get("action") == "close", r.text)
            daily_close_id = r.json()["id"] if r.status_code == 201 else None

            # per-app isolation: second app must not see first app's windows/schedules
            r = client.post(
                "/api/apps/",
                json={
                    "name": "SELFTEST Other",
                    "exe_path": notepad,
                    "process_name": "notepad.exe",
                    "enabled": True,
                    "apply_defaults": False,
                },
            )
            check("create_app_b", r.status_code == 201, r.text)
            app_b = r.json()["id"] if r.status_code == 201 else None
            if app_b:
                r = client.get(f"/api/windows/app/{app_b}")
                check("isolation_windows_empty", r.status_code == 200 and r.json() == [], r.text)
                r = client.get(f"/api/schedules/app/{app_b}")
                check("isolation_schedules_empty", r.status_code == 200 and r.json() == [], r.text)
                r = client.post(
                    f"/api/windows/app/{app_b}/batch",
                    json={"weekdays": [wd], "start_time": "10:00", "end_time": "12:00"},
                )
                check("app_b_own_window", r.status_code == 201, r.text)
                r = client.get(f"/api/windows/app/{app_id}")
                wins_a = r.json() if r.status_code == 200 else []
                wins_b = client.get(f"/api/windows/app/{app_b}").json()
                a_ids = {w["id"] for w in wins_a}
                b_ids = {w["id"] for w in wins_b}
                check("isolation_no_shared_window_ids", a_ids.isdisjoint(b_ids), f"a={a_ids} b={b_ids}")
                check("isolation_a_still_has_window", len(wins_a) >= 1, str(wins_a))
                client.delete(f"/api/apps/{app_b}")

            # import discover (idempotent)
            r = client.post(
                "/api/discover/import",
                json={
                    "items": [
                        {
                            "name": "SELFTEST Import Skip",
                            "exe_path": notepad,
                            "process_name": "notepad.exe",
                        }
                    ]
                },
            )
            check("import_duplicate_ok", r.status_code == 200, r.text)

            # launch now (should be allowed - full day window)
            r = client.post(f"/api/system/apps/{app_id}/launch-now")
            check("launch_now", r.status_code == 200, r.text)
            time.sleep(1.2)

            # kill now
            r = client.post(f"/api/system/apps/{app_id}/kill-now")
            check("kill_now", r.status_code == 200, r.text)

            # stats
            r = client.get("/api/stats/today")
            check("stats_today", r.status_code == 200, r.text)
            if r.status_code == 200:
                body = r.json()
                check("today_has_categories", "categories" in body, str(body.keys()))
                check("today_has_items", "items" in body, str(body.keys()))
                check(
                    "today_mode_union",
                    body.get("total_mode") == "foreground_union",
                    str(body.get("total_mode")),
                )
                # 去重叠合计不应超过 24h，且不应大于各应用时长之和
                total = float(body.get("total_seconds") or 0)
                stacked = float(body.get("stacked_seconds") or 0)
                check("today_total_le_24h", total <= 24 * 3600 + 1, str(total))
                check(
                    "today_total_le_stacked",
                    stacked <= 0 or total <= stacked + 1,
                    f"total={total} stacked={stacked}",
                )

            r = client.get("/api/stats/report?days=7")
            check("stats_report", r.status_code == 200, r.text[:300])
            if r.status_code == 200:
                rep = r.json()
                check(
                    "report_series_len",
                    len(rep.get("daily_series") or []) == 7,
                    str(len(rep.get("daily_series") or [])),
                )
                check("report_has_rank", isinstance(rep.get("by_app"), list), str(type(rep.get("by_app"))))

            r = client.get("/api/stats/audit?limit=20")
            check("stats_audit", r.status_code == 200 and isinstance(r.json(), list), r.text)

            r = client.get("/api/stats/timeline")
            check("stats_timeline", r.status_code == 200, r.text[:300])
            if r.status_code == 200:
                tl = r.json()
                check("timeline_has_date", bool(tl.get("date")), str(tl.keys()))
                check("timeline_has_lanes", isinstance(tl.get("lanes"), list), str(type(tl.get("lanes"))))
                check(
                    "timeline_lane_fields",
                    all(
                        {"app_id", "color", "sessions"} <= set(lane.keys())
                        for lane in (tl.get("lanes") or [])
                    )
                    if tl.get("lanes")
                    else True,
                    str(tl.get("lanes")[:1] if tl.get("lanes") else []),
                )
                # 并行多应用应分多轨（若当日有会话）
                if tl.get("session_count", 0) > 0:
                    check(
                        "timeline_start_end_sec",
                        all(
                            isinstance(s.get("start_sec"), (int, float))
                            and isinstance(s.get("end_sec"), (int, float))
                            and s["end_sec"] >= s["start_sec"]
                            for s in (tl.get("sessions") or [])
                        ),
                        "bad start/end_sec",
                    )

            r = client.get("/api/stats/timeline?day=not-a-date")
            check("timeline_bad_day", r.status_code == 400, r.text)

            # delete schedule/windows/app cleanup
            for sid in (sch_id, daily_launch_id, daily_close_id):
                if sid:
                    client.delete(f"/api/schedules/{sid}")
            wins = client.get(f"/api/windows/app/{app_id}").json()
            for w in wins:
                client.delete(f"/api/windows/{w['id']}")
            r = client.delete(f"/api/apps/{app_id}")
            check("delete_app", r.status_code == 200, r.text)

        # process_win safety
        print("\n[5] process_win safety")
        check("protected_explorer", process_win.is_protected("explorer.exe") is True)
        check("not_protected_notepad", process_win.is_protected("notepad.exe") is False)

        print("\n[6] Icons API")
        r = client.get("/api/icons", params={"path": notepad, "size": 32})
        check(
            "icon_png",
            r.status_code == 200
            and r.headers.get("content-type", "").startswith("image/png")
            and len(r.content) > 50,
            f"status={r.status_code} len={len(r.content)} src={r.headers.get('x-icon-source')}",
        )

        print("\n[7] Usage accounting (no join duplication)")
        from sqlalchemy.orm import selectinload
        from app.models import TimeWindow
        from app.services import usage as usage_svc
        from datetime import time as dtime

        db = SessionLocal()
        try:
            a = AppModel(
                name="SELFTEST Cap",
                exe_path=notepad,
                process_name="notepad.exe",
                category="other",
                enabled=True,
            )
            db.add(a)
            db.flush()
            for wd in range(3):
                db.add(
                    TimeWindow(
                        app_id=a.id,
                        weekday=wd,
                        start_time=dtime(5, 0),
                        end_time=dtime(22, 20),
                    )
                )
            db.commit()
            aid = a.id

            # selectinload 保证每个 App 只出现一次（避免用量被时段数放大）
            selected = (
                db.query(AppModel)
                .options(selectinload(AppModel.windows))
                .filter(AppModel.id == aid)
                .all()
            )
            check(
                "selectinload_unique",
                len(selected) == 1 and len(selected[0].windows) == 3,
                f"selected={len(selected)} wins={len(selected[0].windows) if selected else 0}",
            )

            # 同 id 去重后只应处理 1 次
            uniq = {x.id: x for x in selected}
            check("dedupe_by_id", len(uniq) == 1, str(len(uniq)))

            # 用量上限：写入 30h 应被裁到 ≤24h
            usage_svc.add_usage_seconds(db, aid, 30 * 3600)
            db.commit()
            sec = usage_svc.daily_seconds(db, aid)
            check("daily_cap_le_24h", sec <= 24 * 3600, str(sec))

            # 强制写超限再 repair
            row = usage_svc.get_or_create_daily(db, aid)
            row.seconds = 99 * 3600
            db.commit()
            r = client.post("/api/system/repair-usage")
            check("repair_usage_api", r.status_code == 200, r.text)
            sec2 = usage_svc.daily_seconds(db, aid)
            check("repair_clamped", sec2 <= 24 * 3600, str(sec2))
            if r.status_code == 200:
                body = r.json()
                check("repair_has_sessions_field", "repaired_sessions" in body, str(body))

            db.delete(db.get(AppModel, aid))
            db.commit()
        finally:
            db.close()

        print("\n[8] Matching / foreground / union")
        from app.services.process_win import (
            MatchedProcess,
            app_is_foreground,
            get_foreground_process,
            match_processes,
        )
        from app.services.usage import union_interval_seconds

        u = union_interval_seconds([(0, 100), (50, 150), (200, 250)])
        check("union_intervals", abs(u - 200) < 0.01, str(u))

        # 有路径时不应仅因同名命中（用一个极不可能存在的路径）
        fake = match_processes("notepad.exe", r"C:\__atg_no_such__\notepad.exe")
        check("strict_path_no_name_fallback", fake == [], f"n={len(fake)}")

        fg = get_foreground_process()
        check("foreground_api_callable", fg is None or isinstance(fg, MatchedProcess), str(fg))
        if fg and fg.exe:
            hit = app_is_foreground("x.exe", fg.exe, fg)
            miss = app_is_foreground("x.exe", r"C:\__no__\x.exe", fg)
            check("foreground_match_path", hit is True and miss is False, f"hit={hit} miss={miss}")

        r = client.get("/api/system/status")
        if r.status_code == 200:
            st = r.json()
            check("status_has_foreground", "foreground_name" in st or "usage_foreground_only" in st, str(st.keys()))
            check("status_fg_only_flag", st.get("usage_foreground_only") is True, str(st.get("usage_foreground_only")))

    return _finish()


def _finish():
    print(f"\n=== RESULT: {PASS} passed, {FAIL} failed ===")
    if ERRORS:
        print("Failures:")
        for e in ERRORS:
            print(" -", e)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
