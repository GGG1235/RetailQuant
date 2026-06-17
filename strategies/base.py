"""
rQuant.strategies.base — 策略协议 + Signal 数据类
- 所有策略实现必须遵循 Strategy Protocol
- Signal 是策略对外输出的统一格式
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Protocol

import pandas as pd


@dataclass
class Signal:
    """单只股票/ETF 的策略信号"""

    code: str
    name: str
    sector: str
    strategy: str  # 策略 ID（如 "DonchianTurtle20"）
    category: str  # 大类（"turtle" / "factor" / ...）
    current_price: float
    suggested_buy: float
    stop_loss: float
    take_profit: float
    reason: str
    confidence: float  # 0-100
    market_state: str = "SIDEWAYS"  # 兼容老字段
    extra: dict[str, Any] = field(default_factory=dict)


class Strategy(Protocol):
    """所有策略必须实现的协议"""

    name: str  # 唯一 ID
    category: str  # 大类
    description: str  # 一句话说明

    def signal_buy(self, code: str, name: str, sector: str, df: pd.DataFrame) -> Signal | None: ...

    def signal_sell(self, position: dict[str, Any], df: pd.DataFrame) -> dict[str, Any] | None: ...


# ============== 通用技术指标工具 ==============


def ma(df: pd.DataFrame, n: int) -> float:
    """最近 N 日收盘均价（含当日）"""
    if len(df) < n:
        return float(df["close"].iloc[-1])
    return float(df["close"].tail(n).mean())


def prev_ma(df: pd.DataFrame, n: int) -> float:
    """昨日 MA（N）—— 即收盘价序列 [-n-1:-1] 的均值"""
    if len(df) < n + 1:
        return float(df["close"].iloc[-1])
    return float(df["close"].iloc[-(n + 1) : -1].mean())


def highest(df: pd.DataFrame, n: int) -> float:
    """N 日最高价（含当日）"""
    if len(df) < n:
        return float(df["high"].iloc[-1])
    return float(df["high"].tail(n).max())


def lowest(df: pd.DataFrame, n: int) -> float:
    """N 日最低价（含当日）"""
    if len(df) < n:
        return float(df["low"].iloc[-1])
    return float(df["low"].tail(n).min())


def atr(df: pd.DataFrame, n: int = 14) -> float:
    """N 日 ATR（Averaged True Range）"""
    if len(df) < n + 1:
        return float(df["close"].iloc[-1] * 0.02)
    high = df["high"].tail(n)
    low = df["low"].tail(n)
    close_prev = df["close"].shift(1).tail(n)
    tr = pd.concat(
        [
            high - low,
            (high - close_prev).abs(),
            (low - close_prev).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return float(tr.mean())


def rsi(df: pd.DataFrame, n: int = 14) -> float:
    """RSI(N) —— 标准 Wilder 平滑"""
    if len(df) < n + 1:
        return 50.0
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0.0).tail(n)
    loss = (-delta.where(delta < 0, 0.0)).tail(n)
    avg_gain = gain.mean()
    avg_loss = loss.mean()
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100 - 100 / (1 + rs))


def vol_ratio(df: pd.DataFrame, n: int = 5) -> float:
    """量比：当日 volume / N 日均量"""
    if len(df) < n + 1:
        return 1.0
    today = float(df["volume"].iloc[-1])
    avg = float(df["volume"].iloc[-(n + 1) : -1].mean())
    return today / avg if avg > 0 else 1.0


def momentum(df: pd.DataFrame, n: int = 20) -> float:
    """N 日动量：现价 / N 日前收盘 - 1"""
    if len(df) < n + 1:
        return 0.0
    return float(df["close"].iloc[-1] / df["close"].iloc[-(n + 1)] - 1)


def change_pct(df: pd.DataFrame) -> float:
    """当日涨跌幅 = 现价 / 昨收 - 1"""
    if len(df) < 2:
        return 0.0
    return float(df["close"].iloc[-1] / df["close"].iloc[-2] - 1)
