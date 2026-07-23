"""Pydantic schemas"""
from datetime import date, datetime, time
from typing import List, Optional

from pydantic import BaseModel, Field


class AppBase(BaseModel):
    name: str
    exe_path: str
    process_name: str
    category: str = "other"
    enabled: bool = True
    daily_limit_minutes: Optional[int] = Field(None, ge=1)
    session_limit_minutes: Optional[int] = Field(None, ge=1)
    notes: Optional[str] = None


class AppCreate(AppBase):
    apply_defaults: bool = True


class AppUpdate(BaseModel):
    name: Optional[str] = None
    exe_path: Optional[str] = None
    process_name: Optional[str] = None
    category: Optional[str] = None
    enabled: Optional[bool] = None
    daily_limit_minutes: Optional[int] = Field(None, ge=1)
    session_limit_minutes: Optional[int] = Field(None, ge=1)
    notes: Optional[str] = None
    apply_defaults: Optional[bool] = None


class AppOut(AppBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    usage_7d_seconds: float = 0.0
    usage_7d_minutes: float = 0.0
    usage_rank: Optional[int] = None

    class Config:
        from_attributes = True


class TimeWindowCreate(BaseModel):
    weekday: int = Field(..., ge=0, le=6)
    start_time: time
    end_time: time


class TimeWindowOut(TimeWindowCreate):
    id: int
    app_id: int

    class Config:
        from_attributes = True


class LaunchScheduleCreate(BaseModel):
    weekday: int = Field(..., ge=-1, le=6, description="-1=每天, 0=周一...6=周日")
    launch_time: time
    action: str = Field("launch", pattern="^(launch|close)$")
    enabled: bool = True


class LaunchScheduleUpdate(BaseModel):
    weekday: Optional[int] = Field(None, ge=-1, le=6)
    launch_time: Optional[time] = None
    action: Optional[str] = Field(None, pattern="^(launch|close)$")
    enabled: Optional[bool] = None


class LaunchScheduleOut(LaunchScheduleCreate):
    id: int
    app_id: int
    last_fired_date: Optional[date] = None

    class Config:
        from_attributes = True


class UsageDailyOut(BaseModel):
    app_id: int
    app_name: Optional[str] = None
    date: date
    seconds: float
    kill_count: int
    launch_count: int


class AuditLogOut(BaseModel):
    id: int
    created_at: datetime
    action: str
    app_id: Optional[int] = None
    detail: Optional[str] = None

    class Config:
        from_attributes = True


class SystemStatus(BaseModel):
    guard_running: bool
    launcher_running: bool
    last_guard_scan_at: Optional[datetime] = None
    last_launcher_check_at: Optional[datetime] = None
    launcher_last_error: Optional[str] = None
    launcher_last_tick: Optional[str] = None
    today_kill_count: int = 0
    tracked_apps: int = 0
    host: str
    port: int
    usage_foreground_only: bool = True
    foreground_pid: Optional[int] = None
    foreground_name: Optional[str] = None
    foreground_exe: Optional[str] = None
    foreground_app_id: Optional[int] = None
    foreground_app_name: Optional[str] = None
    live_tracked: int = 0
