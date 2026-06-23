"""
rQuant 启动脚本（推荐）
- 用法：python3 app.py
- 也可：python3 -m scripts.run
- 等价于：python3 -m rquant.web
"""

from rquant.web.app_factory import run

if __name__ == "__main__":
    run()
