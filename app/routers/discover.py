"""应用发现 API"""
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import App
from app.schemas import AppOut
from app.services.category import (
    apply_category_defaults,
    normalize_category,
    suggest_category,
)
from app.services.discover import discover_apps
from app.services.process_win import normalize_process_name

router = APIRouter(prefix="/api/discover", tags=["discover"])


class DiscoveredApp(BaseModel):
    name: str
    exe_path: str
    process_name: str
    source: str
    suggested_category: str = "other"
    already_registered: bool = False
    registered_id: Optional[int] = None


class DiscoverResponse(BaseModel):
    ok: bool
    total: int
    running_count: int = 0
    start_menu_count: int = 0
    errors: List[str] = Field(default_factory=list)
    items: List[DiscoveredApp] = Field(default_factory=list)


class ImportItem(BaseModel):
    name: str
    exe_path: str
    process_name: Optional[str] = None
    category: Optional[str] = None
    enabled: bool = True
    daily_limit_minutes: Optional[int] = Field(None, ge=1)
    apply_defaults: bool = True


class ImportRequest(BaseModel):
    items: List[ImportItem]


@router.get("/apps", response_model=DiscoverResponse)
def list_discovered(
    include_start_menu: bool = Query(True),
    db: Session = Depends(get_db),
):
    """扫描本机应用。始终 200；部分失败时 ok=false 仍返回已发现项。"""
    try:
        existing = db.query(App).all()
        by_path = {
            (a.exe_path or "").replace("/", "\\").lower(): a.id for a in existing
        }

        raw_items, meta = discover_apps(include_start_menu=include_start_menu)
        out: List[DiscoveredApp] = []
        for item in raw_items:
            try:
                key = item["exe_path"].replace("/", "\\").lower()
                rid = by_path.get(key)
                sug = suggest_category(
                    item.get("name", ""),
                    item.get("exe_path", ""),
                    item.get("process_name", ""),
                )
                out.append(
                    DiscoveredApp(
                        name=item["name"],
                        exe_path=item["exe_path"],
                        process_name=item["process_name"],
                        source=item["source"],
                        suggested_category=sug,
                        already_registered=rid is not None,
                        registered_id=rid,
                    )
                )
            except Exception as e:
                meta.setdefault("errors", []).append(f"item_skip:{e}")

        errors = list(meta.get("errors") or [])
        return DiscoverResponse(
            ok=len(errors) == 0,
            total=len(out),
            running_count=int(meta.get("running_count") or 0),
            start_menu_count=int(meta.get("start_menu_count") or 0),
            errors=errors,
            items=out,
        )
    except Exception as e:
        return DiscoverResponse(
            ok=False,
            total=0,
            errors=[f"discover_fatal:{e}"],
            items=[],
        )


@router.post("/import", response_model=List[AppOut])
def import_discovered(payload: ImportRequest, db: Session = Depends(get_db)):
    created = []
    existing_paths = {
        (a.exe_path or "").replace("/", "\\").lower() for a in db.query(App).all()
    }
    for item in payload.items:
        key = item.exe_path.replace("/", "\\").lower()
        if key in existing_paths:
            continue
        proc = item.process_name or normalize_process_name(Path(item.exe_path).name)
        cat = normalize_category(
            item.category
            or suggest_category(item.name, item.exe_path, proc)
        )
        app = App(
            name=item.name,
            exe_path=item.exe_path,
            process_name=normalize_process_name(proc),
            category=cat,
            enabled=item.enabled,
            daily_limit_minutes=item.daily_limit_minutes,
        )
        db.add(app)
        db.flush()
        if item.apply_defaults:
            apply_category_defaults(
                db, app, set_limits=(item.daily_limit_minutes is None)
            )
            if item.daily_limit_minutes is not None:
                app.daily_limit_minutes = item.daily_limit_minutes
        created.append(app)
        existing_paths.add(key)
    db.commit()
    for a in created:
        db.refresh(a)
    return created
