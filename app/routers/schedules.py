"""定时启停 API（按单应用隔离）。"""
from datetime import datetime, timedelta, time as dtime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import App, LaunchSchedule
from app.schemas import LaunchScheduleCreate, LaunchScheduleOut, LaunchScheduleUpdate
from app.services import usage

router = APIRouter(prefix="/api/schedules", tags=["schedules"])


class QuickScheduleRequest(BaseModel):
    minutes_from_now: int = Field(1, ge=1, le=1440)
    action: str = Field("launch", pattern="^(launch|close)$")


@router.get("/app/{app_id}", response_model=List[LaunchScheduleOut])
def list_schedules(app_id: int, db: Session = Depends(get_db)):
    if not db.query(App).get(app_id):
        raise HTTPException(404, "应用不存在")
    return (
        db.query(LaunchSchedule)
        .filter(LaunchSchedule.app_id == app_id)
        .order_by(LaunchSchedule.weekday, LaunchSchedule.launch_time)
        .all()
    )


@router.get("/", response_model=List[LaunchScheduleOut])
def list_all_schedules(db: Session = Depends(get_db)):
    return db.query(LaunchSchedule).order_by(LaunchSchedule.id.desc()).all()


@router.post("/app/{app_id}", response_model=LaunchScheduleOut, status_code=201)
def create_schedule(app_id: int, payload: LaunchScheduleCreate, db: Session = Depends(get_db)):
    if not db.query(App).get(app_id):
        raise HTTPException(404, "应用不存在")
    sch = LaunchSchedule(
        app_id=app_id,
        weekday=payload.weekday,
        launch_time=payload.launch_time,
        action=payload.action or "launch",
        enabled=payload.enabled,
        last_fired_date=None,
    )
    db.add(sch)
    db.commit()
    db.refresh(sch)
    return sch


@router.post("/app/{app_id}/in-minutes", response_model=LaunchScheduleOut, status_code=201)
def create_schedule_in_minutes(
    app_id: int, payload: QuickScheduleRequest, db: Session = Depends(get_db)
):
    """快捷：为「今天 + N 分钟后」创建一条今日调度（方便验证）。"""
    if not db.query(App).get(app_id):
        raise HTTPException(404, "应用不存在")
    now = usage.now_local()
    target = now + timedelta(minutes=payload.minutes_from_now)
    sch = LaunchSchedule(
        app_id=app_id,
        weekday=usage.python_weekday(target),
        launch_time=dtime(target.hour, target.minute, target.second),
        action=payload.action or "launch",
        enabled=True,
        last_fired_date=None,
    )
    db.add(sch)
    db.commit()
    db.refresh(sch)
    usage.write_audit(
        db,
        "schedule_quick",
        app_id,
        f"schedule_id={sch.id}; action={sch.action}; at={target.isoformat()}",
    )
    db.commit()
    return sch


@router.put("/{schedule_id}", response_model=LaunchScheduleOut)
def update_schedule(
    schedule_id: int, payload: LaunchScheduleUpdate, db: Session = Depends(get_db)
):
    sch = db.query(LaunchSchedule).get(schedule_id)
    if not sch:
        raise HTTPException(404, "调度不存在")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(sch, k, v)
    db.commit()
    db.refresh(sch)
    return sch


@router.post("/{schedule_id}/reset-fired")
def reset_fired(schedule_id: int, db: Session = Depends(get_db)):
    """清除今日已触发标记，允许重新触发。"""
    sch = db.query(LaunchSchedule).get(schedule_id)
    if not sch:
        raise HTTPException(404, "调度不存在")
    sch.last_fired_date = None
    db.commit()
    return {"ok": True}


@router.delete("/{schedule_id}")
def delete_schedule(schedule_id: int, db: Session = Depends(get_db)):
    sch = db.query(LaunchSchedule).get(schedule_id)
    if not sch:
        raise HTTPException(404, "调度不存在")
    db.delete(sch)
    db.commit()
    return {"ok": True}
