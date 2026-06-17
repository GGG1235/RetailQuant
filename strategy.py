"""
rQuant — 兼容层入口
- 老代码 `from strategy import ...` 仍能工作
- 内部转发到 rquant.compat.strategy
"""

# 转发所有符号
from rquant.compat.strategy import *  # noqa: F401,F403
from rquant.compat.strategy import (  # noqa: F401
    Signal,
    STRATEGIES,
    all_strategies,
    by_category,
    buyhold_signal,
    categories,
    chanlun2b_signal,
    scan_stock,
    scan_stock_legacy,
    sell_signal,
)
