"""
rQuant.strategies.etf_rotation.cross_border_dca — 跨境 ETF 定投
- 基线版：MA60 下方 + RSI 超卖 → 加仓信号
- 严格时序：只用 ≤ dt 的数据
- ⚠️ 跨境 ETF 有 T+0/T+1 差异、有溢价折价，实盘需关注

信号逻辑：
- 买入触发：现价 < MA60 × 0.95 AND RSI(14) < 35 AND 量比 > 0.8（不是无量阴跌）
- 信心度：超卖越深信心越高
- 卖出：>+10% 止盈 / -8% 止损 / 跌破 MA60

注册：@register
"""

from __future__ import annotations
from typing import Any

import pandas as pd

from ..base import Signal, ma, rsi, vol_ratio
from ..registry import register


@register
class CrossBorderDca:
    """跨境 ETF 定投（基线版）"""

    name = "CrossBorderDca"
    category = "etf_rotation"
    description = "跨境 ETF MA60 下方 + RSI 超卖 → 加仓信号"

    # 参数
    MA_N = 60
    MA_DROP_RATIO = 0.95  # 现价 < MA60 × 0.95
    RSI_BUY = 35
    VOL_RATIO_MIN = 0.8  # 过滤无量阴跌
    TAKE_PROFIT = 0.10
    STOP_LOSS = -0.08

    def signal_buy(self, code: str, name: str, sector: str, df: pd.DataFrame) -> Signal | None:
        if df is None or len(df) < self.MA_N:
            return None

        close = float(df["close"].iloc[-1])
        ma60 = ma(df, self.MA_N)
        rsi_v = rsi(df, 14)
        vr = vol_ratio(df, 5)

        # 过滤条件
        if close >= ma60 * self.MA_DROP_RATIO:
            return None  # 不在低位
        if rsi_v >= self.RSI_BUY:
            return None  # 不超卖
        if vr < self.VOL_RATIO_MIN:
            return None  # 无量阴跌

        # 信心度：RSI 越低越有信心（线性插值）
        confidence = max(40.0, min(85.0, 100 - rsi_v * 1.4))

        suggested = round(close * 1.005, 2)  # +0.5% 容忍滑点
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
                f"跨境定投：现价 ¥{close:.3f} < MA60×{self.MA_DROP_RATIO}（¥{ma60 * self.MA_DROP_RATIO:.3f}），"
                f"RSI={rsi_v:.1f}，量比={vr:.2f}"
            ),
            confidence=round(confidence, 1),
            extra={"rsi": rsi_v, "ma60": ma60, "vol_ratio": vr, "kind": "cross_border_dca"},
        )

    def signal_sell(self, position: dict[str, Any], df: pd.DataFrame) -> dict[str, Any] | None:
        if df is None or df.empty or len(df) < self.MA_N:
            return None
        close = float(df["close"].iloc[-1])
        avg_cost = position.get("avg_cost", 0)
        if avg_cost <= 0:
            return None
        pnl_pct = (close / avg_cost - 1) * 100

        if pnl_pct >= self.TAKE_PROFIT * 100:
            return {
                "reason": f"达到 +{self.TAKE_PROFIT * 100:.0f}% 止盈（当前 {pnl_pct:+.1f}%）",
                "suggested_price": round(close * 0.995, 2),
                "urgency": "normal",
            }
        if pnl_pct <= self.STOP_LOSS * 100:
            return {
                "reason": f"触发 {self.STOP_LOSS * 100:.0f}% 止损（当前 {pnl_pct:+.1f}%）",
                "suggested_price": round(close * 0.99, 2),
                "urgency": "urgent",
            }
        # 跌破 MA60 离场
        ma60 = ma(df, self.MA_N)
        if close < ma60:
            return {
                "reason": f"跌破 MA60（¥{ma60:.3f}），趋势走坏",
                "suggested_price": round(close * 0.995, 2),
                "urgency": "normal",
            }
        return None
