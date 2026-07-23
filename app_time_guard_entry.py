"""
App Time Guard 可执行入口（开发与 PyInstaller 打包共用）。
启动本机 Web 服务并打开浏览器。
"""
from __future__ import annotations

import argparse
import socket
import sys
import threading
import time
import webbrowser


def _port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) != 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="App Time Guard")
    parser.add_argument("--host", default=None, help="监听地址，默认 127.0.0.1")
    parser.add_argument("--port", type=int, default=None, help="端口，默认 8765")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args(argv)

    # 延迟导入，便于 PyInstaller 收集依赖
    import uvicorn

    from app.config import settings
    from app.main import app
    from app.paths import app_data_dir, is_frozen

    host = args.host or settings.host
    port = args.port or settings.port

    if not _port_free(host, port):
        print(f"[App Time Guard] 端口 {host}:{port} 已被占用，尝试打开已有界面…")
        if not args.no_browser:
            webbrowser.open(f"http://{host}:{port}/")
        print("若界面无法打开，请结束旧进程后重试。")
        return 1

    url = f"http://{host}:{port}/"
    data = app_data_dir()
    print("=" * 56)
    print("  App Time Guard")
    print(f"  界面: {url}")
    print(f"  数据: {data}")
    print(f"  模式: {'安装包' if is_frozen() else '开发'}")
    print("  关闭本窗口将停止守护。")
    print("=" * 56)

    if not args.no_browser:
        def _open():
            time.sleep(1.0)
            webbrowser.open(url)

        threading.Thread(target=_open, name="OpenBrowser", daemon=True).start()

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
