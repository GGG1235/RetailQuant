"""
rQuant 启动脚本（推荐）
- 用法：python3 scripts/run.py
- 也可：python3 -m rquant.web
- 等价于：python3 app.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rquant.web.app_factory import run  # noqa: E402

if __name__ == "__main__":
    run()
