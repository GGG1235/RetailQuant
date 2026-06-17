"""
rQuant.strategies.turtle.donchian — 海龟交易 / 唐奇安通道
- 经典版：20 日突破入场，10 日反向出场，2×ATR 止损
- 严格时序：只看 ≤ dt 的数据
- 基线版简化：固定权重（不按 ATR 算头寸规模），保留通道逻辑

信号逻辑：
- 买入触发：close > 前 20 日最高价（不含当日）
- 卖出：close < 前 10 日最低价（不含当日） / -8% 止损 / +25% 止盈（海龟是趋势策略，止盈宽）

注册：@register
"""

from __future__ import annotations
from typing import Any

import pandas as pd

from ..base import Signal, atr
from ..registry import register


@register
class DonchianTurtle:
    """海龟交易 / 唐奇安通道"""

    name = "DonchianTurtle"
    category = "turtle"
    description = "20 日新高入场，10 日新低离场（海龟趋势）"

    # 参数（海龟经典）
    ENTRY_N = 20
    EXIT_N = 10
    ATR_N = 20
    TAKE_PROFIT = 0.25
    STOP_LOSS = -0.08

    def signal_buy(self, code: str, name: str, sector: str, df: pd.DataFrame) -> Signal | None:
        if df is None or len(df) < self.ENTRY_N + 1:
            return None

        close = float(df["close"].iloc[-1])
        # 前 20 日最高（不含当日）—— 严格时序：昨天的 20 日窗口
        prev_n_high = float(df["high"].iloc[-(self.ENTRY_N + 1) : -1].max())
        a = atr(df, self.ATR_N)

        # 唐奇安突破
        if close <= prev_n_high:
            return None

        confidence = 70.0  # 海龟突破基线信心度

        suggested = round(close * 1.005, 2)
        # 海龟用 2×ATR 止损
        stop = round(suggested - 2 * a, 2)
        return Signal(
            code=code,
            name=name,
            sector=sector,
            strategy=self.name,
            category=self.category,
            current_price=close,
            suggested_buy=suggested,
            stop_loss=stop,
            take_profit=round(suggested * (1 + self.TAKE_PROFIT), 2),
            reason=(
                f"海龟突破：现价 ¥{close:.3f} 突破 20 日高点 ¥{prev_n_high:.3f}，"
                f"ATR({self.ATR_N})={a:.3f} → 2×ATR 止损 ¥{stop:.3f}"
            ),
            confidence=confidence,
            extra={"prev_n_high": prev_n_high, "atr": a, "kind": "turtle_donchian"},
        )

    def signal_sell(self, position: dict[str, Any], df: pd.DataFrame) -> dict[str, Any] | None:
        if df is None or df.empty or len(df) < self.EXIT_N + 1:
            return None
        close = float(df["close"].iloc[-1])
        prev_n_low = float(df["low"].iloc[-(self.EXIT_N + 1) : -1].min())
        avg_cost = position.get("avg_cost", 0)
        if avg_cost <= 0:
            return None
        pnl_pct = (close / avg_cost - 1) * 100

        if close < prev_n_low:
            return {
                "reason": f"海龟离场：跌破 10 日低点 ¥{prev_n_low:.3f}",
                "suggested_price": round(close * 0.99, 2),
                "urgency": "normal",
            }
        if pnl_pct >= self.TAKE_PROFIT * 100:
            return {
                "reason": f"达到 +{self.TAKE_PROFIT * 100:.0f}% 止盈（当前 {pnl_pct:+.1f}%）",
                "suggested_price": round(close * 0.99, 2),
                "urgency": "normal",
            }
        if pnl_pct <= self.STOP_LOSS * 100:
            return {
                "reason": f"触发 {self.STOP_LOSS * 100:.0f}% 止损（当前 {pnl_pct:+.1f}%）",
                "suggested_price": round(close * 0.99, 2),
                "urgency": "urgent",
            }
        return None
