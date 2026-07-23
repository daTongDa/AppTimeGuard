"""ORM 模型"""
from datetime import datetime, date, time

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.db import Base


class App(Base):
    __tablename__ = "apps"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    exe_path = Column(String(512), nullable=False)
    process_name = Column(String(120), nullable=False)  # e.g. notepad.exe
    # entertainment|study|work|other
    category = Column(String(32), default="other", nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    daily_limit_minutes = Column(Integer, nullable=True)  # None = unlimited
    session_limit_minutes = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    windows = relationship("TimeWindow", back_populates="app", cascade="all, delete-orphan")
    schedules = relationship("LaunchSchedule", back_populates="app", cascade="all, delete-orphan")


class TimeWindow(Base):
    __tablename__ = "time_windows"

    id = Column(Integer, primary_key=True, index=True)
    app_id = Column(Integer, ForeignKey("apps.id", ondelete="CASCADE"), nullable=False, index=True)
    weekday = Column(Integer, nullable=False)  # 0=Mon ... 6=Sun
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)

    app = relationship("App", back_populates="windows")


class LaunchSchedule(Base):
    __tablename__ = "launch_schedules"

    id = Column(Integer, primary_key=True, index=True)
    app_id = Column(Integer, ForeignKey("apps.id", ondelete="CASCADE"), nullable=False, index=True)
    # -1 = 每天；0=周一 ... 6=周日（仅作用于本 app_id）
    weekday = Column(Integer, nullable=False)
    launch_time = Column(Time, nullable=False)
    # launch | close
    action = Column(String(16), default="launch", nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    last_fired_date = Column(Date, nullable=True)

    app = relationship("App", back_populates="schedules")


class UsageSession(Base):
    __tablename__ = "usage_sessions"

    id = Column(Integer, primary_key=True, index=True)
    app_id = Column(Integer, ForeignKey("apps.id", ondelete="CASCADE"), nullable=False, index=True)
    started_at = Column(DateTime, nullable=False)
    ended_at = Column(DateTime, nullable=True)
    seconds = Column(Float, default=0.0)
    end_reason = Column(String(40), nullable=True)  # normal|killed_window|killed_limit|manual


class UsageDaily(Base):
    __tablename__ = "usage_daily"
    __table_args__ = (UniqueConstraint("app_id", "date", name="uq_usage_daily_app_date"),)

    id = Column(Integer, primary_key=True, index=True)
    app_id = Column(Integer, ForeignKey("apps.id", ondelete="CASCADE"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    seconds = Column(Float, default=0.0)
    kill_count = Column(Integer, default=0)
    launch_count = Column(Integer, default=0)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.now, index=True)
    action = Column(String(64), nullable=False)
    app_id = Column(Integer, nullable=True)
    detail = Column(Text, nullable=True)
