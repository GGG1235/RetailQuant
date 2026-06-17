"""
rQuant.strategy — 兼容层
- 老的 app.py / 测试可能 import 这个文件
- 内部从 strategies 包 re-export，旧 API 仍然能用
- 老的 chanlun2b_signal / buyhold_signal 已升级到 strategies/legacy/ 下的优化版
- 新代码请直接 from strategies import ...
"""

from __future__ import annotations
from typing import Any

import pandas as pd

# 转发到新的 strategies 包
from strategies import (
    Signal,
    STRATEGIES,
    all_strategies,
    by_category,
    categories,
    scan_sell,
    scan_stock,
)
from strategies.legacy.buyhold import BuyHold
from strategies.legacy.chanlun2b import ChanLun2B

# ============== 老 API 兼容（薄包装）==============
# 单函数接口：直接调用优化版策略的 signal_buy
_buyhold_instance = BuyHold()
_chanlun2b_instance = ChanLun2B()


def chanlun2b_signal(code: str, name: str, sector: str, df: pd.DataFrame) -> Signal | None:
    """缠论二买（优化版）—— 6 重过滤：底分型+多头排列+MA60↑+量能+强势收盘+RSI"""
    return _chanlun2b_instance.signal_buy(code, name, sector, df)


def buyhold_signal(code: str, name: str, sector: str, df: pd.DataFrame) -> Signal | None:
    """Buy & Hold 低吸（优化版）—— 4 重确认：超跌+超卖+缩量+止跌"""
    return _buyhold_instance.signal_buy(code, name, sector, df)


def scan_stock_legacy(code: str, name: str, sector: str, df: pd.DataFrame) -> list[Signal]:
    """老的 scan_stock —— 跑所有策略（包含 legacy）"""
    return scan_stock(code, name, sector, df)


def sell_signal(position: dict[str, Any], df: pd.DataFrame) -> dict[str, Any] | None:
    """老的 sell_signal —— 跑所有策略的卖出信号"""
    return scan_sell(position, df)


# 兼容老 import
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
