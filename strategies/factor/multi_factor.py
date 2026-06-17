"""
rQuant.strategies.factor.multi_factor — 多因子选股（占位版）
- 当前能算的因子（K线数据）：动量、RSI、量比、波动率
- ⚠️ 财务因子（PE/PB/股息率/ROE/市值）需要东财/聚宽数据源，当前返回 N/A
- 严格时序：所有因子只看 ≤ dt 的数据

信号逻辑：
- 综合得分 = 动量得分 + RSI 得分 + 量比得分 - 波动率惩罚
- 得分 ≥ 0.5 → 买入信号
- 信心度 = 60 + min(30, 得分 × 20)

注册：@register
"""

from __future__ import annotations
from typing import Any

import pandas as pd

from ..base import Signal, momentum, rsi, vol_ratio
from ..registry import register


# 因子归一化函数
def _norm_momentum(mom_pct: float) -> float:
    """动量因子：-10% → -1, 0% → 0, +10% → 1，截断"""
    return max(-1.0, min(1.0, mom_pct / 10.0))


def _norm_rsi(rsi_v: float) -> float:
    """RSI 因子：30 → 1, 50 → 0, 70 → -1（超卖加，超买卖减）"""
    return max(-1.0, min(1.0, (50.0 - rsi_v) / 20.0))


def _norm_vol_ratio(vr: float) -> float:
    """量比因子：0.5 → -1, 1.0 → 0, 2.0 → 1"""
    return max(-1.0, min(1.0, (vr - 1.0) / 1.0))


def _norm_volatility(df: pd.DataFrame) -> float:
    """20 日波动率因子：std/mean，>5% 惩罚"""
    if len(df) < 21:
        return 0.0
    close = df["close"].tail(21).iloc[:-1]  # 不含当日
    mean = close.mean()
    if mean <= 0:
        return 0.0
    vol = close.std() / mean * 100  # %
    return max(0.0, (vol - 5.0) / 5.0)  # 5% → 0, 10% → 1


@register
class MultiFactor:
    """多因子选股（K线因子版 + 财务因子占位）"""

    name = "MultiFactor"
    category = "factor"
    description = "动量+RSI+量比-波动率 多因子综合得分（财务因子需数据源）"

    # 因子权重
    W_MOMENTUM = 0.4
    W_RSI = 0.3
    W_VOL = 0.2
    W_VOLATILITY = 0.3  # 惩罚项

    SCORE_BUY = 0.5  # 综合得分 >= 0.5 触发买入
    TAKE_PROFIT = 0.15
    STOP_LOSS = -0.08

    def signal_buy(self, code: str, name: str, sector: str, df: pd.DataFrame) -> Signal | None:
        if df is None or len(df) < 25:
            return None

        mom = momentum(df, 20) * 100  # %
        rsi_v = rsi(df, 14)
        vr = vol_ratio(df, 5)
        vol_pen = _norm_volatility(df)

        s_mom = _norm_momentum(mom)
        s_rsi = _norm_rsi(rsi_v)
        s_vol = _norm_vol_ratio(vr)

        score = self.W_MOMENTUM * s_mom + self.W_RSI * s_rsi + self.W_VOL * s_vol - self.W_VOLATILITY * vol_pen

        if score < self.SCORE_BUY:
            return None

        close = float(df["close"].iloc[-1])
        confidence = round(min(85.0, 55.0 + score * 25.0), 1)

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
                f"多因子综合得分 {score:+.2f}（动量 {s_mom:+.2f}×{self.W_MOMENTUM} + "
                f"RSI {s_rsi:+.2f}×{self.W_RSI} + 量比 {s_vol:+.2f}×{self.W_VOL} - "
                f"波动率 {vol_pen:+.2f}×{self.W_VOLATILITY}）"
            ),
            confidence=confidence,
            extra={
                "score": round(score, 3),
                "components": {
                    "momentum_20d_pct": round(mom, 2),
                    "rsi_14": round(rsi_v, 1),
                    "vol_ratio_5d": round(vr, 2),
                    "volatility_20d": round(vol_pen, 2),
                },
                "need_data_source": "东财/聚宽（财务因子 PE/PB/股息率/ROE 当前未接入）",
                "kind": "multi_factor",
            },
        )

    def signal_sell(self, position: dict[str, Any], df: pd.DataFrame) -> dict[str, Any] | None:
        if df is None or df.empty or len(df) < 25:
            return None
        close = float(df["close"].iloc[-1])
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
        return None
