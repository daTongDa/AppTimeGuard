"""应用配置"""
from pathlib import Path

from pydantic_settings import BaseSettings

from app.paths import app_data_dir, resource_dir


BASE_DIR = resource_dir()
DATA_DIR = app_data_dir()
DATA_DIR.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    host: str = "127.0.0.1"
    port: int = 8765
    database_url: str = f"sqlite:///{(DATA_DIR / 'app_time_guard.db').as_posix()}"
    guard_interval_seconds: float = 4.0
    launcher_interval_seconds: float = 15.0
    launcher_fire_grace_seconds: float = 300.0  # 到点后 5 分钟内可触发
    kill_grace_seconds: float = 2.0
    # True=仅前台窗口计时（后台托盘不计入）；False=进程在跑就计时
    usage_foreground_only: bool = True

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
