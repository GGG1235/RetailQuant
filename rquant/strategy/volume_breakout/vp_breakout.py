"""
rQuant.strategies.volume_breakout.vp_breakout — 量价共振突破
- 基线版：突破 20 日新高 + 成交量 >= 1.5×5日均量 + 收盘接近最高
- 严格时序：只看 ≤ dt 的数据
- 量价共振 = 突破有效性 + 市场认可

信号逻辑：
- 买入触发：close > 20 日最高 + 量比 ≥ 1.5 + 强势收盘（close/high >= 0.97）
- 信心度：量比越大信心越高
- 卖出：跌破 10 日均线 / -7% 止损 / +18% 止盈（强势策略止盈稍宽）

注册：@register
"""

from __future__ import annotations
from typing import Any

import pandas as pd

from ..base import Signal, ma, vol_ratio
from ..registry import register


@register
class VpBreakout:
    """量价共振突破"""

    name = "VpBreakout"
    category = "volume_breakout"
    description = "突破 20 日新高 + 量比 ≥ 1.5 + 强势收盘 → 买入"

    # 参数
    HIGH_N = 20
    VOL_RATIO_MIN = 1.5
    CLOSE_TO_HIGH = 0.97  # 收盘价 / 当日最高价 >= 此值算强势
    MA_EXIT = 10  # 跌破 10 日均线离场
    TAKE_PROFIT = 0.18
    STOP_LOSS = -0.07

    def signal_buy(self, code: str, name: str, sector: str, df: pd.DataFrame) -> Signal | None:
        if df is None or len(df) < self.HIGH_N + 1:
            return None

        close = float(df["close"].iloc[-1])
        high = float(df["high"].iloc[-1])
        prev_high = float(df["high"].iloc[-(self.HIGH_N + 1) : -1].max())
        vr = vol_ratio(df, 5)

        # 突破前 N 日最高
        if close <= prev_high:
            return None
        # 量能放大
        if vr < self.VOL_RATIO_MIN:
            return None
        # 强势收盘（不是冲高回落）
        if high <= 0 or (close / high) < self.CLOSE_TO_HIGH:
            return None

        confidence = max(60.0, min(90.0, 60 + (vr - 1.5) * 15))

        suggested = round(close * 1.005, 2)
        return Signal(
            code=code,
            name=name,
            sector=sector,
            strategy=self.name,
            category=self.category,
            current_price=close,
            suggested_buy=suggested,
            stop_loss=round(suggested * (1 + self.STOP_LOSS), 2),
            take_profit=round(suggested * (1 + self.TAKE_PROFIT), 2),
            reason=(
                f"量价突破：突破 20 日新高 ¥{prev_high:.3f}，量比 {vr:.2f} ≥ {self.VOL_RATIO_MIN}，"
                f"强势收盘 {close / high * 100:.1f}%"
            ),
            confidence=round(confidence, 1),
            extra={"prev_high": prev_high, "vol_ratio": vr, "kind": "vp_breakout"},
        )

    def signal_sell(self, position: dict[str, Any], df: pd.DataFrame) -> dict[str, Any] | None:
        if df is None or df.empty or len(df) < self.MA_EXIT:
            return None
        close = float(df["close"].iloc[-1])
        ma_exit = ma(df, self.MA_EXIT)
        avg_cost = position.get("avg_cost", 0)
        if avg_cost <= 0:
            return None
        pnl_pct = (close / avg_cost - 1) * 100

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
        if close < ma_exit * 0.97:
            return {
                "reason": f"跌破 10 日均线（¥{ma_exit:.3f}），趋势走坏",
                "suggested_price": round(close * 0.99, 2),
                "urgency": "normal",
            }
        return None
