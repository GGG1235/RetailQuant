"""
rQuant 启动入口（向后兼容）
- 老的 `python3 app.py` 仍能启动
- 老的 `from app import app` 仍能拿到 Flask 实例（CI 期望）
- 内部转发到 rquant.web.app_factory
"""

import sys
from pathlib import Path

# 让 rquant 包可 import
sys.path.insert(0, str(Path(__file__).resolve().parent))

from rquant.web.app_factory import create_app, run  # noqa: E402

# 暴露 Flask 实例（CI / gunicorn / 其它工具链期望这个名字）
app = create_app()


if __name__ == "__main__":
    run()
