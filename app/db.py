"""数据库连接"""
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.config import settings


engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@event.listens_for(engine, "connect")
def _set_sqlite_fk(dbapi_conn, _connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _migrate_sqlite():
    """轻量迁移：为已有库补列。"""
    with engine.begin() as conn:
        rows = conn.execute(text("PRAGMA table_info(launch_schedules)")).fetchall()
        if rows:
            cols = {r[1] for r in rows}
            if "action" not in cols:
                conn.execute(
                    text(
                        "ALTER TABLE launch_schedules "
                        "ADD COLUMN action VARCHAR(16) NOT NULL DEFAULT 'launch'"
                    )
                )
        apps_rows = conn.execute(text("PRAGMA table_info(apps)")).fetchall()
        if apps_rows:
            apps_cols = {r[1] for r in apps_rows}
            if "category" not in apps_cols:
                conn.execute(
                    text(
                        "ALTER TABLE apps "
                        "ADD COLUMN category VARCHAR(32) NOT NULL DEFAULT 'other'"
                    )
                )


def init_db():
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_sqlite()
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM time_windows WHERE app_id NOT IN (SELECT id FROM apps)")
        )
        conn.execute(
            text(
                "DELETE FROM launch_schedules WHERE app_id NOT IN (SELECT id FROM apps)"
            )
        )
