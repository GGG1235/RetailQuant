"""
rquant.web.app_factory — Flask 应用工厂
- create_app()：构造 Flask app
- run()：启动 waitress（双栈监听）
"""

from __future__ import annotations

import errno
import os
import sys
from pathlib import Path

from flask import Flask

from config import config
from rquant.data_source import start_mq
from rquant.log import error, info, init_logging

from .routes import register_routes


DEFAULT_PORT = int(os.environ.get("RQUANT_PORT", str(config.server.port)))


def create_app() -> Flask:
    """Flask 应用工厂"""
    # 初始化日志系统（幂等，确保后续日志可用）
    init_logging()
    # 启动后台消息队列 worker（批量刷新 K 线 / 异步任务派发）
    start_mq()

    # 让 templates / static 能被 Flask 找到（基于项目根目录）
    _project_root = Path(__file__).resolve().parent.parent.parent
    app = Flask(
        __name__,
        template_folder=str(_project_root / "templates"),
        static_folder=str(_project_root / "static"),
    )
    app.secret_key = config.server.secret_key  # 从 config.toml 读取
    register_routes(app)
    return app


def run(port: int = DEFAULT_PORT) -> None:
    """启动 waitress（双栈 IPv4 + IPv6）"""
    app = create_app()
    info("app", f"rQuant 启动（双栈）：http://localhost:{port}/  http://127.0.0.1:{port}/  http://[::1]:{port}/")
    info("app", "日志系统已就绪，等待请求中…")
    try:
        from waitress import serve

        # 双 listen = IPv4 + IPv6 同时监听，避免 localhost 在 macOS 上解析到 ::1 时连不上
        serve(
            app,
            listen=[f"127.0.0.1:{port}", f"[::1]:{port}"],
            ident="rquant",
        )
    except ImportError:
        # Flask dev server 不支持双 listen，回退到单 host
        app.run(host="127.0.0.1", port=port, debug=True)
    except OSError as e:
        if e.errno == errno.EADDRINUSE:
            error(
                "app",
                f"端口 {port} 已被占用，rQuant 可能已在运行中。如需重启请先关闭已有进程：lsof -ti:{port} | xargs kill",
            )
            sys.exit(1)
        raise


if __name__ == "__main__":
    run()
