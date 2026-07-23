"""时段窗口 API"""
from datetime import time as dtime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import App, TimeWindow
from app.schemas import TimeWindowCreate, TimeWindowOut

router = APIRouter(prefix="/api/windows", tags=["windows"])


class BatchWindowsRequest(BaseModel):
    weekdays: List[int] = Field(..., min_length=1)
    start_time: str
    end_time: str


def _parse_t(s: str) -> dtime:
    parts = s.strip().split(":")
    return dtime(int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0)


@router.get("/app/{app_id}", response_model=List[TimeWindowOut])
def list_windows(app_id: int, db: Session = Depends(get_db)):
    if not db.query(App).get(app_id):
        raise HTTPException(404, "应用不存在")
    return (
        db.query(TimeWindow)
        .filter(TimeWindow.app_id == app_id)
        .order_by(TimeWindow.weekday, TimeWindow.start_time)
        .all()
    )


@router.post("/app/{app_id}", response_model=TimeWindowOut, status_code=201)
def create_window(app_id: int, payload: TimeWindowCreate, db: Session = Depends(get_db)):
    if not db.query(App).get(app_id):
        raise HTTPException(404, "应用不存在")
    if payload.start_time == payload.end_time:
        raise HTTPException(400, "开始与结束时间不能相同")
    w = TimeWindow(
        app_id=app_id,
        weekday=payload.weekday,
        start_time=payload.start_time,
        end_time=payload.end_time,
    )
    db.add(w)
    db.commit()
    db.refresh(w)
    return w


@router.post("/app/{app_id}/batch", response_model=List[TimeWindowOut], status_code=201)
def batch_create_windows(app_id: int, payload: BatchWindowsRequest, db: Session = Depends(get_db)):
    """一次为多个星期添加相同起止时段。"""
    if not db.query(App).get(app_id):
        raise HTTPException(404, "应用不存在")
    start = _parse_t(payload.start_time)
    end = _parse_t(payload.end_time)
    if start == end:
        raise HTTPException(400, "开始与结束时间不能相同")
    created = []
    for wd in payload.weekdays:
        if wd < 0 or wd > 6:
            continue
        w = TimeWindow(app_id=app_id, weekday=wd, start_time=start, end_time=end)
        db.add(w)
        created.append(w)
    db.commit()
    for w in created:
        db.refresh(w)
    return created


@router.delete("/{window_id}")
def delete_window(window_id: int, db: Session = Depends(get_db)):
    w = db.query(TimeWindow).get(window_id)
    if not w:
        raise HTTPException(404, "时段不存在")
    db.delete(w)
    db.commit()
    return {"ok": True}


@router.put("/app/{app_id}/replace", response_model=List[TimeWindowOut])
def replace_windows(app_id: int, items: List[TimeWindowCreate], db: Session = Depends(get_db)):
    if not db.query(App).get(app_id):
        raise HTTPException(404, "应用不存在")
    db.query(TimeWindow).filter(TimeWindow.app_id == app_id).delete()
    created = []
    for payload in items:
        if payload.start_time == payload.end_time:
            raise HTTPException(400, "开始与结束时间不能相同")
        w = TimeWindow(
            app_id=app_id,
            weekday=payload.weekday,
            start_time=payload.start_time,
            end_time=payload.end_time,
        )
        db.add(w)
        created.append(w)
    db.commit()
    for w in created:
        db.refresh(w)
    return created
