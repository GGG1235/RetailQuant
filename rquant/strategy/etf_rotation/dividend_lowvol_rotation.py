"""
rQuant.strategies.etf_rotation.dividend_lowvol_rotation — 红利低波 ETF 轮动
- 简化版基线：动量轮动（20 日涨幅最高的持有/加仓）
- 严格时序：只用 ≤ dt 的数据
- ⚠️ 完整版需要股息率因子（财务数据），当前用动量近似

信号逻辑：
- 买入触发：20 日动量 > 0 且 > 5 日均量（资金流入）
- 信心度：动量越大信心越高
- 卖出：动量转负 或 跌破 MA20

注册：@register
"""

from __future__ import annotations
from typing import Any

import pandas as pd

from ..base import Signal, ma, momentum, vol_ratio
from ..registry import register


@register
class DividendLowvolRotation:
    """红利低波 ETF 动量轮动（基线版）"""

    name = "DividendLowvolRotation"
    category = "etf_rotation"
    description = "红利低波 ETF 动量轮动（20日动量>0 且放量 → 加仓/持有）"

    # 参数
    MOMENTUM_N = 20
    MOMENTUM_MIN = 0.0  # 20 日涨幅必须 > 0
    VOL_RATIO_MIN = 1.0
    TAKE_PROFIT = 0.12
    STOP_LOSS = -0.10

    def signal_buy(self, code: str, name: str, sector: str, df: pd.DataFrame) -> Signal | None:
        if df is None or len(df) < self.MOMENTUM_N + 5:
            return None

        close = float(df["close"].iloc[-1])
        mom = momentum(df, self.MOMENTUM_N) * 100  # 转 %
        vr = vol_ratio(df, 5)
        ma20 = ma(df, 20)

        # 过滤
        if mom <= self.MOMENTUM_MIN:
            return None  # 动量不在正区间
        if vr < self.VOL_RATIO_MIN:
            return None  # 无量
        if close < ma20 * 0.98:
            return None  # 偏离均线过远

        # 信心度
        confidence = max(45.0, min(80.0, 50 + mom * 2))

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
            reason=(f"红利低波轮动：20日动量 {mom:+.2f}%，量比 {vr:.2f}，现价 > MA20×0.98（¥{ma20 * 0.98:.3f}）"),
            confidence=round(confidence, 1),
            extra={"momentum_20d": mom, "vol_ratio": vr, "ma20": ma20, "kind": "dividend_lowvol"},
        )

    def signal_sell(self, position: dict[str, Any], df: pd.DataFrame) -> dict[str, Any] | None:
        if df is None or df.empty or len(df) < self.MOMENTUM_N:
            return None
        close = float(df["close"].iloc[-1])
        mom = momentum(df, self.MOMENTUM_N) * 100
        avg_cost = position.get("avg_cost", 0)
        if avg_cost <= 0:
            return None
        pnl_pct = (close / avg_cost - 1) * 100

        if mom < 0:
            return {
                "reason": f"20日动量转负（{mom:+.2f}%），趋势走坏",
                "suggested_price": round(close * 0.995, 2),
                "urgency": "normal",
            }
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
        # 跌破 MA20 离场
        ma20 = ma(df, 20)
        if close < ma20:
            return {
                "reason": f"跌破 MA20（¥{ma20:.3f}），趋势走坏",
                "suggested_price": round(close * 0.995, 2),
                "urgency": "normal",
            }
        return None
