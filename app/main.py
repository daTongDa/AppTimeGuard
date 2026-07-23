"""FastAPI 入口"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db import init_db
from app.paths import static_dir
from app.routers import apps, discover, icons, schedules, stats, system, windows
from app.services.guard import guard_worker
from app.services.launcher import launch_scheduler

STATIC_DIR = static_dir()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # 启动时裁剪历史异常用量（joinedload 翻倍等遗留）
    from app.db import SessionLocal
    from app.services import usage as usage_svc

    db = SessionLocal()
    try:
        n = usage_svc.clamp_daily_seconds(db)
        n_sess = usage_svc.repair_inflated_sessions(db)
        if n or n_sess:
            usage_svc.write_audit(
                db,
                "repair_usage",
                None,
                f"startup_clamped_rows={n}; repaired_sessions={n_sess}",
            )
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()

    guard_worker.start()
    launch_scheduler.start()
    yield
    guard_worker.stop()
    launch_scheduler.stop()


app = FastAPI(
    title="App Time Guard",
    description="Windows 本机应用时段/时长管控（强制杀进程）",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        f"http://{settings.host}:{settings.port}",
        "http://127.0.0.1:8765",
        "http://localhost:8765",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(apps.router)
app.include_router(windows.router)
app.include_router(schedules.router)
app.include_router(stats.router)
app.include_router(system.router)
app.include_router(discover.router)
app.include_router(icons.router)

if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index():
    index_path = STATIC_DIR / "index.html"
    if not index_path.is_file():
        return {"error": "UI missing", "path": str(index_path)}
    return FileResponse(index_path)
