"""应用 CRUD"""
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import App
from app.schemas import AppCreate, AppOut, AppUpdate
from app.services.category import (
    CATEGORY_LABELS,
    apply_category_defaults,
    default_policy,
    normalize_category,
)
from app.services.process_win import normalize_process_name
from app.services.usage import app_usage_seconds_last_days

router = APIRouter(prefix="/api/apps", tags=["apps"])


def _derive_process_name(
    payload: Union[AppCreate, AppUpdate], existing: Optional[App] = None
) -> str:
    name = getattr(payload, "process_name", None)
    if name:
        return normalize_process_name(name)
    path = getattr(payload, "exe_path", None) or (existing.exe_path if existing else None)
    if path:
        return normalize_process_name(Path(path).name)
    if existing:
        return existing.process_name
    raise HTTPException(status_code=400, detail="需要 process_name 或 exe_path")


@router.get("/categories")
def list_categories():
    return [
        {
            "code": code,
            "label": label,
            "policy": default_policy(code)["summary"],
        }
        for code, label in CATEGORY_LABELS.items()
    ]


@router.get("/", response_model=list[AppOut])
def list_apps(db: Session = Depends(get_db)):
    """按近 7 天前台使用时长降序排列（无用量的排后面，再按 id 倒序）。"""
    apps = db.query(App).all()
    usage = app_usage_seconds_last_days(db, days=7)
    ranked = sorted(
        apps,
        key=lambda a: (-float(usage.get(a.id, 0.0)), -int(a.id or 0)),
    )
    out: list[AppOut] = []
    for i, app in enumerate(ranked, start=1):
        sec = float(usage.get(app.id, 0.0))
        item = AppOut.model_validate(app)
        out.append(
            item.model_copy(
                update={
                    "usage_7d_seconds": round(sec, 1),
                    "usage_7d_minutes": round(sec / 60, 1),
                    "usage_rank": i if sec > 0 else None,
                }
            )
        )
    return out


@router.post("/", response_model=AppOut, status_code=201)
def create_app(payload: AppCreate, db: Session = Depends(get_db)):
    cat = normalize_category(payload.category)
    app = App(
        name=payload.name,
        exe_path=payload.exe_path,
        process_name=_derive_process_name(payload),
        category=cat,
        enabled=payload.enabled,
        daily_limit_minutes=payload.daily_limit_minutes,
        session_limit_minutes=payload.session_limit_minutes,
        notes=payload.notes,
    )
    db.add(app)
    db.flush()
    if payload.apply_defaults:
        apply_category_defaults(
            db, app, set_limits=(payload.daily_limit_minutes is None)
        )
        if payload.daily_limit_minutes is not None:
            app.daily_limit_minutes = payload.daily_limit_minutes
        if payload.session_limit_minutes is not None:
            app.session_limit_minutes = payload.session_limit_minutes
    db.commit()
    db.refresh(app)
    return app


@router.get("/{app_id}", response_model=AppOut)
def get_app(app_id: int, db: Session = Depends(get_db)):
    app = db.query(App).get(app_id)
    if not app:
        raise HTTPException(404, "应用不存在")
    return app


@router.put("/{app_id}", response_model=AppOut)
def update_app(app_id: int, payload: AppUpdate, db: Session = Depends(get_db)):
    app = db.query(App).get(app_id)
    if not app:
        raise HTTPException(404, "应用不存在")
    data = payload.model_dump(exclude_unset=True)
    apply_defaults = data.pop("apply_defaults", None)
    if "category" in data and data["category"] is not None:
        data["category"] = normalize_category(data["category"])
    if "process_name" in data or "exe_path" in data:
        data["process_name"] = _derive_process_name(payload, app)
    for k, v in data.items():
        setattr(app, k, v)
    if apply_defaults:
        apply_category_defaults(db, app, set_limits=True)
    app.updated_at = datetime.now()
    db.commit()
    db.refresh(app)
    return app


@router.post("/{app_id}/apply-defaults", response_model=AppOut)
def apply_defaults(app_id: int, db: Session = Depends(get_db)):
    """按当前分类重写默认时段与日限。"""
    app = db.query(App).get(app_id)
    if not app:
        raise HTTPException(404, "应用不存在")
    apply_category_defaults(db, app, set_limits=True)
    app.updated_at = datetime.now()
    db.commit()
    db.refresh(app)
    return app


@router.delete("/{app_id}")
def delete_app(app_id: int, db: Session = Depends(get_db)):
    app = db.query(App).get(app_id)
    if not app:
        raise HTTPException(404, "应用不存在")
    db.delete(app)
    db.commit()
    return {"ok": True}
