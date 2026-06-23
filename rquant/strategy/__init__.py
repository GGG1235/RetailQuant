"""
rQuant.strategy — 策略引擎入口
- 导入各子模块即触发 @register
- scan_stock: 跑单只股票的所有策略
- scan_category: 跑某大类的所有策略
- scan_sell: 跑所有策略的卖出信号
"""

from __future__ import annotations
import pandas as pd

from .base import Signal, Strategy, atr, change_pct, highest, lowest, ma, momentum, prev_ma, rsi, vol_ratio
from .registry import STRATEGIES, all_strategies, by_category, categories, get, register
from rquant.log import warning

# 触发子模块的 @register
from .etf_rotation import cross_border_dca, dividend_lowvol_rotation  # noqa: F401
from .factor import multi_factor  # noqa: F401
from .grid import grid_martingale  # noqa: F401
from .legacy import buyhold, chanlun2b  # noqa: F401
from .pattern import dragon_tiger  # noqa: F401
from .router import market_regime, scenario_router  # noqa: F401
from .turtle import donchian  # noqa: F401
from .volume_breakout import vp_breakout  # noqa: F401


# ============== 统一扫描入口 ==============


def scan_stock(code: str, name: str, sector: str, df: pd.DataFrame) -> list[Signal]:
    """对单只股票/ETF 跑所有策略，返回命中的买入信号列表"""
    if df is None or df.empty:
        return []
    signals: list[Signal] = []
    for strat in all_strategies():
        try:
            sig = strat.signal_buy(code, name, sector, df)
        except Exception as e:
            warning("strategy", f"策略 {strat.name} 异常 {code}: {e}")
            sig = None
        if sig is not None:
            signals.append(sig)
    return signals


def scan_category(category: str, code: str, name: str, sector: str, df: pd.DataFrame) -> list[Signal]:
    """对单只股票/ETF 跑指定大类的所有策略"""
    if df is None or df.empty:
        return []
    signals: list[Signal] = []
    for strat in by_category(category):
        try:
            sig = strat.signal_buy(code, name, sector, df)
        except Exception as e:
            warning("strategy", f"策略 {strat.name} 异常 {code}: {e}")
            sig = None
        if sig is not None:
            signals.append(sig)
    return signals


def scan_sell(position: dict, df: pd.DataFrame) -> dict | None:
    """对单只持仓跑所有策略的卖出信号，返回首个非 None"""
    if df is None or df.empty:
        return None
    for strat in all_strategies():
        try:
            sig = strat.signal_sell(position, df)
        except Exception as e:
            warning("strategy", f"策略 {strat.name} 卖出异常 {position.get('code', '')}: {e}")
            continue
        if sig is not None:
            return {**sig, "strategy": strat.name, "category": strat.category}
    return None


__all__ = [
    "Signal",
    "Strategy",
    "STRATEGIES",
    "all_strategies",
    "by_category",
    "categories",
    "get",
    "register",
    "scan_category",
    "scan_sell",
    "scan_stock",
    "atr",
    "change_pct",
    "highest",
    "lowest",
    "ma",
    "momentum",
    "prev_ma",
    "rsi",
    "vol_ratio",
]
