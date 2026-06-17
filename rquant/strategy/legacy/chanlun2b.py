"""
rQuant.strategies.legacy.chanlun2b — 缠论二买近似（优化版）
- 老版本只有 1 个条件（MA5 上穿 MA20），假信号多
- 优化版加入：底分型识别（5 日窗口）+ 多头排列 + MA60 向上 + 量能 + RSI 过滤

触发条件（必须全部满足）：
  1. 底分型（最近 5 日内）：中间 K 线低点最低 + 中间 K 线收盘 > 左侧收盘
  2. 突破：现价 > 底分型 K 线的高点
  3. 多头排列：MA5 > MA10 > MA20
  4. MA60 方向向上（当日 MA60 > 5 日前 MA60）
  5. 量能：当日 volume ≥ 1.3 × 5 日均量
  6. 强势收盘：close / high ≥ 0.97（不是冲高回落）
  7. RSI ≥ 50（不在超卖区，但不卡上限——突破日 RSI 经常 80+）

信心度：60 + 量能/趋势/RSI 综合得分（最高 90）

注册：@register，category="legacy"
"""

from __future__ import annotations
from typing import Any

import pandas as pd

from ..base import Signal, ma, prev_ma, rsi
from ..registry import register


@register
class ChanLun2B:
    """缠论二买近似（优化版）"""

    name = "ChanLun2B"
    category = "legacy"
    description = "底分型(5日窗口)+突破+多头排列+量能+RSI 7 重过滤的缠论二买近似"

    # 参数
    MA_N_FAST = 5
    MA_N_MID = 10
    MA_N_SLOW = 20
    MA_N_TREND = 60
    FRACTAL_LOOKBACK = 5  # 底分型识别窗口
    VOL_RATIO_MIN = 1.3
    CLOSE_TO_HIGH = 0.97
    RSI_MIN = 50  # 下限：RSI 不在超卖区
    # 不卡 RSI 上限：突破日 RSI 经常 > 80，再追反而错过机会
    TAKE_PROFIT = 0.15
    STOP_LOSS = -0.07

    def _find_bottom_fractal(self, df: pd.DataFrame) -> int | None:
        """在最近 N 根 K 线里找最近的底分型，返回中间 K 线的相对位置（2 = 昨天）

        底分型（宽松版）：i 位置满足
          - low[i] < low[i-1]   (低点更低)
          - low[i] < low[i+1]   (低点更低)
          - close[i] > close[i-1]  (收盘高于左侧)
        不要求 c_i > c_next —— 因为 c_next 可能是"突破日大阳"
        """
        n = len(df)
        lookback = min(self.FRACTAL_LOOKBACK + 2, n)
        if lookback < 3:
            return None
        for rel in range(2, lookback - 1 + 1):  # 2 到 lookback-1
            i = -rel
            i_prev = i - 1
            i_next = i + 1
            try:
                l_prev = float(df["low"].iloc[i_prev])
                l_i = float(df["low"].iloc[i])
                l_next = float(df["low"].iloc[i_next])
                c_prev = float(df["close"].iloc[i_prev])
                c_i = float(df["close"].iloc[i])
            except (IndexError, KeyError):
                continue
            if (l_i < l_prev and l_i < l_next) and (c_i > c_prev):
                return rel
        return None

    def signal_buy(self, code: str, name: str, sector: str, df: pd.DataFrame) -> Signal | None:
        if df is None or len(df) < self.MA_N_TREND + 5:
            return None

        close = float(df["close"].iloc[-1])
        high = float(df["high"].iloc[-1])
        vol_today = float(df["volume"].iloc[-1])

        # 1. 底分型识别（最近 5 日窗口）
        fractal_rel = self._find_bottom_fractal(df)
        if fractal_rel is None:
            return None
        # 底分型 K 线的 high（突破参考点）
        fractal_high = float(df["high"].iloc[-fractal_rel])

        # 2. 突破：现价站上底分型 K 线高点
        if close <= fractal_high:
            return None

        # 3. 多头排列
        ma5 = ma(df, self.MA_N_FAST)
        ma10 = ma(df, self.MA_N_MID)
        ma20 = ma(df, self.MA_N_SLOW)
        if not (ma5 > ma10 > ma20):
            return None

        # 4. MA60 方向向上
        ma60 = ma(df, self.MA_N_TREND)
        ma60_prev = prev_ma(df, self.MA_N_TREND)
        if ma60 <= ma60_prev:
            return None

        # 5. 量能放大
        vol_5avg = float(df["volume"].iloc[-6:-1].mean())
        if vol_5avg <= 0 or vol_today < vol_5avg * self.VOL_RATIO_MIN:
            return None

        # 6. 强势收盘
        if high <= 0 or (close / high) < self.CLOSE_TO_HIGH:
            return None

        # 7. RSI 过滤（只卡下限，不卡上限）
        rsi_v = rsi(df, 14)
        if rsi_v < self.RSI_MIN:
            return None

        # 信心度综合计算
        vol_ratio = vol_today / vol_5avg
        vol_score = min(10.0, max(0.0, (vol_ratio - self.VOL_RATIO_MIN) * 10))

        ma_spread_pct = (ma5 - ma20) / ma20 * 100 if ma20 > 0 else 0
        trend_score = min(10.0, max(0.0, ma_spread_pct))

        # RSI 得分：50-70 健康区间给满分，>70 不扣分（突破日允许）
        if self.RSI_MIN <= rsi_v <= 70:
            rsi_score = 10.0
        else:
            rsi_score = 5.0  # 超买区不扣分但不给满分

        # 形态得分：底分型越近得分越高
        shape_score = max(0.0, 10.0 - (fractal_rel - 2) * 3)

        confidence = min(90.0, 60.0 + vol_score + trend_score + rsi_score + shape_score)

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
                f"缠论二买优化版：{fractal_rel}日前底分型 + 突破 ¥{fractal_high:.2f} + "
                f"多头 MA5({ma5:.2f})>MA10({ma10:.2f})>MA20({ma20:.2f}) + "
                f"MA60↑ + 量比 {vol_ratio:.2f} + RSI {rsi_v:.1f}"
            ),
            confidence=round(confidence, 1),
            extra={
                "kind": "legacy_chanlun_optimized",
                "bottom_fractal": True,
                "fractal_rel_pos": fractal_rel,
                "fractal_high": round(fractal_high, 3),
                "ma5": round(ma5, 3),
                "ma10": round(ma10, 3),
                "ma20": round(ma20, 3),
                "ma60": round(ma60, 3),
                "vol_ratio": round(vol_ratio, 2),
                "rsi": round(rsi_v, 1),
            },
        )

    def signal_sell(self, position: dict[str, Any], df: pd.DataFrame) -> dict[str, Any] | None:
        if df is None or df.empty or len(df) < self.MA_N_SLOW:
            return None
        close = float(df["close"].iloc[-1])
        ma20 = ma(df, self.MA_N_SLOW)
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
        if close < ma20 * 0.97:
            return {
                "reason": f"跌破 MA20×0.97（¥{ma20 * 0.97:.2f}），多头排列破坏",
                "suggested_price": round(close * 0.99, 2),
                "urgency": "normal",
            }
        return None
