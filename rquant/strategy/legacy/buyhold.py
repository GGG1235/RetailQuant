"""
rQuant.strategies.legacy.buyhold — Buy & Hold 低吸（优化版）
- 老版本只有 1 个条件（现价 < MA60 × 0.95），容易接飞刀
- 优化版加入：超卖确认 + 缩量见底 + 止跌信号 + MA60 距离 + 连续阴线

触发条件（必须全部满足）：
  1. 20 日跌幅 > 10%（确认超跌，不是高位回调）
  2. MA60 距离：现价在 MA60 下方 5-25%（不在飞刀区，也不接近均线）
  3. RSI < 30（超卖）
  4. 量能缩量：3 日均量 < 20 日均量 × 0.7（恐慌出清）
  5. 当日反弹：close > open 且 close > 昨收（止跌信号）
  6. 最近 3 日内至少 1 根阴线（确认是下跌后止跌，不是横盘）

信心度：50 + 跌幅得分 + RSI 得分 + 缩量得分（最高 85）

注册：@register，category="legacy"
"""

from __future__ import annotations
from typing import Any

import pandas as pd

from ..base import Signal, ma, rsi
from ..registry import register


@register
class BuyHold:
    """Buy & Hold 低吸（优化版）"""

    name = "BuyHold"
    category = "legacy"
    description = "超跌+超卖+缩量+止跌 4 重确认的低吸信号"

    # 参数
    DROP_LOOKBACK = 20
    DROP_THRESHOLD = -10.0  # 20 日跌幅 > 10%
    MA60_N = 60
    MA60_DROP_MIN = -35.0  # 现价/MA60 跌幅区间（放宽，避免错过严重超跌）
    MA60_DROP_MAX = -5.0
    RSI_BUY = 30
    VOL_SHRINK_RATIO = 0.7  # 3 日均量 / 20 日均量 < 0.7
    TAKE_PROFIT = 0.20
    STOP_LOSS = -0.10

    def signal_buy(self, code: str, name: str, sector: str, df: pd.DataFrame) -> Signal | None:
        if df is None or len(df) < self.MA60_N + 5:
            return None

        close = float(df["close"].iloc[-1])
        open_ = float(df["open"].iloc[-1])
        prev_close = float(df["close"].iloc[-2])

        # 1. 20 日跌幅过滤
        if len(df) < self.DROP_LOOKBACK + 1:
            return None
        chg_20d = (close / float(df["close"].iloc[-(self.DROP_LOOKBACK + 1)]) - 1) * 100
        if chg_20d > self.DROP_THRESHOLD:  # 跌幅不够大
            return None

        # 2. MA60 距离（不要接飞刀，也不接即将反弹的）
        ma60 = ma(df, self.MA60_N)
        if ma60 <= 0:
            return None
        drop_to_ma60 = (close / ma60 - 1) * 100
        if drop_to_ma60 > self.MA60_DROP_MAX or drop_to_ma60 < self.MA60_DROP_MIN:
            return None

        # 3. RSI 超卖
        rsi_v = rsi(df, 14)
        if rsi_v >= self.RSI_BUY:
            return None

        # 4. 量能缩量
        vol_3avg = float(df["volume"].iloc[-3:].mean())
        vol_20avg = float(df["volume"].iloc[-20:].mean())
        if vol_20avg <= 0 or vol_3avg > vol_20avg * self.VOL_SHRINK_RATIO:
            return None

        # 5. 当日止跌（反弹）
        if close <= open_ or close <= prev_close:
            return None

        # 6. 最近 3 日内至少 1 根阴线
        has_recent_bear = any(float(df["close"].iloc[i]) < float(df["open"].iloc[i]) for i in range(-3, 0))
        if not has_recent_bear:
            return None

        # 信心度计算
        drop_score = min(15.0, abs(chg_20d) - abs(self.DROP_THRESHOLD))
        rsi_score = min(10.0, max(0.0, self.RSI_BUY - rsi_v))
        vol_shrink = vol_3avg / vol_20avg if vol_20avg > 0 else 1.0
        shrink_score = min(10.0, max(0.0, (self.VOL_SHRINK_RATIO - vol_shrink) * 30))

        confidence = min(85.0, 50.0 + drop_score + rsi_score + shrink_score)

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
                f"低吸优化版：20 日跌幅 {chg_20d:+.1f}% + "
                f"MA60 距离 {drop_to_ma60:+.1f}% + RSI {rsi_v:.1f} + "
                f"3 日/20 日量比 {vol_shrink:.2f} + 当日反弹"
            ),
            confidence=round(confidence, 1),
            extra={
                "kind": "legacy_buyhold_optimized",
                "chg_20d_pct": round(chg_20d, 2),
                "drop_to_ma60_pct": round(drop_to_ma60, 2),
                "rsi": round(rsi_v, 1),
                "vol_shrink_ratio": round(vol_shrink, 2),
            },
        )

    def signal_sell(self, position: dict[str, Any], df: pd.DataFrame) -> dict[str, Any] | None:
        if df is None or df.empty or len(df) < self.MA60_N:
            return None
        close = float(df["close"].iloc[-1])
        ma60 = ma(df, self.MA60_N)
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
        if close > ma60 * 1.05:
            return {
                "reason": f"站上 MA60×1.05（¥{ma60 * 1.05:.2f}），低吸目标达成",
                "suggested_price": round(close * 0.995, 2),
                "urgency": "normal",
            }
        return None
