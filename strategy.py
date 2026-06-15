"""
rQuant.strategy — 阉割版策略层
- ChanLun2BApprox：MA5 上穿 MA20 → 买入信号
- BuyHold：买入持有，跌破 MA60 卖出（最简择时）
- 不做仓位管理、不做市场状态判断、不做宏观
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
import pandas as pd


@dataclass
class Signal:
    """单只股票的信号"""
    code: str
    name: str
    sector: str
    strategy: str        # "ChanLun2B" / "BuyHold"
    current_price: float
    suggested_buy: float
    stop_loss: float
    take_profit: float
    reason: str
    confidence: float    # 0-100
    market_state: str = "SIDEWAYS"


def _calc_ma(df: pd.DataFrame, n: int) -> float:
    if len(df) < n:
        return float(df["close"].iloc[-1])
    return float(df["close"].tail(n).mean())


def chanlun2b_signal(code: str, name: str, sector: str, df: pd.DataFrame) -> Optional[Signal]:
    """缠论二买近似：站上 MA5 + MA5 > MA20 → 买入
    最简版：只做这一个条件，不加缩量、不加其他过滤器
    """
    if df is None or len(df) < 25:
        return None
    close = float(df["close"].iloc[-1])
    ma5 = _calc_ma(df, 5)
    ma20 = _calc_ma(df, 20)
    ma60 = _calc_ma(df, 60)
    prev_close = float(df["close"].iloc[-2])
    prev_ma5 = float(df["close"].iloc[-6:-1].mean())  # 昨天 MA5

    # 站上 MA5 + MA5 > MA20
    if close > ma5 and ma5 > ma20 and prev_close < prev_ma5:
        # 建议买入 = 现价 +0.5%（不强求不踏空）
        suggested = round(close * 1.005, 2)
        # 止损 = 建议价 × 0.93（-7%）
        stop_loss = round(suggested * 0.93, 2)
        # 止盈 = 建议价 × 1.15（+15%）
        take_profit = round(suggested * 1.15, 2)
        return Signal(
            code=code, name=name, sector=sector,
            strategy="ChanLun2B",
            current_price=close,
            suggested_buy=suggested,
            stop_loss=stop_loss,
            take_profit=take_profit,
            reason=f"站上 MA5({ma5:.2f}) + MA5>MA20({ma20:.2f})",
            confidence=80,
        )
    return None


def buyhold_signal(code: str, name: str, sector: str, df: pd.DataFrame) -> Optional[Signal]:
    """Buy & Hold 近似：现价 < MA60 的 95% → 触发"加仓"信号
    最简：低位吸筹
    """
    if df is None or len(df) < 60:
        return None
    close = float(df["close"].iloc[-1])
    ma60 = _calc_ma(df, 60)
    if close < ma60 * 0.95:
        return Signal(
            code=code, name=name, sector=sector,
            strategy="BuyHold",
            current_price=close,
            suggested_buy=round(close * 1.005, 2),
            stop_loss=round(close * 0.90, 2),
            take_profit=round(close * 1.20, 2),
            reason=f"现价 ¥{close:.2f} < MA60×0.95（¥{ma60*0.95:.2f}）",
            confidence=60,
        )
    return None


def scan_stock(code: str, name: str, sector: str, df: pd.DataFrame) -> List[Signal]:
    """对单只股票跑所有策略，返回命中的信号列表"""
    signals = []
    s1 = chanlun2b_signal(code, name, sector, df)
    if s1:
        signals.append(s1)
    s2 = buyhold_signal(code, name, sector, df)
    if s2:
        signals.append(s2)
    return signals


def sell_signal(position: Dict[str, Any], df: pd.DataFrame) -> Optional[Dict[str, Any]]:
    """对单只持仓判断卖出（最简：跌破 MA60 触发卖出）
    position: {code, name, avg_cost, shares, ...}
    返回 None 或 {reason, suggested_price, urgency}
    """
    if df is None or len(df) < 60:
        return None
    close = float(df["close"].iloc[-1])
    ma60 = _calc_ma(df, 60)
    avg_cost = position.get("avg_cost", 0)
    pnl_pct = (close / avg_cost - 1) * 100 if avg_cost > 0 else 0

    # 1. 止损 -7%
    if pnl_pct <= -7:
        return {
            "reason": f"触发 -7% 止损线（当前 {pnl_pct:+.1f}%）",
            "suggested_price": round(close * 0.99, 2),
            "urgency": "urgent",
        }
    # 2. 止盈 +15%
    if pnl_pct >= 15:
        return {
            "reason": f"达到 +15% 止盈线（当前 {pnl_pct:+.1f}%）",
            "suggested_price": round(close * 0.995, 2),
            "urgency": "normal",
        }
    # 3. 跌破 MA60
    if close < ma60 * 0.95:
        return {
            "reason": f"跌破 MA60×0.95（¥{ma60*0.95:.2f}）",
            "suggested_price": round(close * 0.99, 2),
            "urgency": "normal",
        }
    return None
