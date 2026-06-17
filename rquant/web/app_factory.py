"""
rquant.web.app_factory — Flask 应用工厂
- create_app()：构造 Flask app
- run()：启动 waitress（双栈监听）
"""

from __future__ import annotations
import os
from pathlib import Path

# 让 templates / static 能被 Flask 找到（基于项目根目录）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_TEMPLATE_DIR = _PROJECT_ROOT / "templates"
_STATIC_DIR = _PROJECT_ROOT / "static"

from flask import Flask  # noqa: E402

from rquant.data_source import start_mq  # noqa: E402

from .routes import register_routes  # noqa: E402
from .views import _log  # noqa: E402

DEFAULT_PORT = int(os.environ.get("RQUANT_PORT", "8080"))


def create_app() -> Flask:
    """Flask 应用工厂"""
    # 启动后台消息队列 worker（批量刷新 K 线 / 异步任务派发）
    start_mq()
    app = Flask(
        __name__,
        template_folder=str(_TEMPLATE_DIR),
        static_folder=str(_STATIC_DIR),
    )
    app.secret_key = "rquant-dev-key"  # 仅本地用
    register_routes(app)
    return app


def run(port: int = DEFAULT_PORT) -> None:
    """启动 waitress（双栈 IPv4 + IPv6）"""
    app = create_app()
    print(f"rQuant 启动（双栈）：\n  http://localhost:{port}/\n  http://127.0.0.1:{port}/\n  http://[::1]:{port}/")
    _log("日志系统已就绪，等待请求中…")
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


if __name__ == "__main__":
    run()
