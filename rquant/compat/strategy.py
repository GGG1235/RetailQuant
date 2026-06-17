"""
rquant.compat.strategy — 兼容层
- 老的 strategy.py 内容（保持向后兼容）
- 老的 API：chanlun2b_signal / buyhold_signal / scan_stock / sell_signal
- 内部全部转发到 rquant.strategy + rquant.strategy.legacy
- 新代码请直接 from rquant.strategy import ...
"""

from __future__ import annotations
from typing import Any

import pandas as pd

# 转发到新位置
from rquant.strategy import (
    Signal,
    STRATEGIES,
    all_strategies,
    by_category,
    categories,
    scan_sell,
    scan_stock,
)
from rquant.strategy.legacy.buyhold import BuyHold
from rquant.strategy.legacy.chanlun2b import ChanLun2B

# 兼容层：单函数风格接口
_buyhold_instance = BuyHold()
_chanlun2b_instance = ChanLun2B()


def chanlun2b_signal(code: str, name: str, sector: str, df: pd.DataFrame) -> Signal | None:
    """缠论二买（优化版）"""
    return _chanlun2b_instance.signal_buy(code, name, sector, df)


def buyhold_signal(code: str, name: str, sector: str, df: pd.DataFrame) -> Signal | None:
    """Buy & Hold 低吸（优化版）"""
    return _buyhold_instance.signal_buy(code, name, sector, df)


def scan_stock_legacy(code: str, name: str, sector: str, df: pd.DataFrame) -> list[Signal]:
    """老的 scan_stock —— 跑所有策略（包含 legacy）"""
    return scan_stock(code, name, sector, df)


def sell_signal(position: dict[str, Any], df: pd.DataFrame) -> dict[str, Any] | None:
    """老的 sell_signal —— 跑所有策略的卖出信号"""
    return scan_sell(position, df)


__all__ = [
    "Signal",
    "STRATEGIES",
    "all_strategies",
    "by_category",
    "categories",
    "chanlun2b_signal",
    "buyhold_signal",
    "scan_stock",
    "scan_stock_legacy",
    "sell_signal",
]
