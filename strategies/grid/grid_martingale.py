"""
rQuant.strategies.grid.grid_martingale — 网格交易 / 马丁格尔（骨架）
- 基线版：日线波动率网格（理想是分钟级，但当前数据源只到日线）
- 信号类型：
  - "grid_buy"：现价跌入新一格 → 建议买入
  - "grid_sell"：现价涨入新一格 → 建议卖出
  - "martingale_buy"：持仓浮亏扩大 → 建议加仓（马丁：量翻倍）
- 严格时序：网格上下沿用最近 N 日高低点

注册：@register
"""

from __future__ import annotations
from typing import Any

import pandas as pd

from ..base import Signal
from ..registry import register


@register
class GridMartingale:
    """网格交易 / 马丁格尔（骨架版）"""

    name = "GridMartingale"
    category = "grid"
    description = "日线波动率网格 + 马丁加仓（骨架版，理想用分钟级）"

    # 参数
    GRID_N = 20  # 用 20 日高低点定区间
    GRID_LEVELS = 5  # 分 5 格
    MARTINGALE_LOSS = -0.05  # 浮亏 5% 触发马丁加仓
    TAKE_PROFIT = 0.15
    STOP_LOSS = -0.15  # 网格策略止损放宽

    def signal_buy(self, code: str, name: str, sector: str, df: pd.DataFrame) -> Signal | None:
        """网格下沿买入信号"""
        if df is None or len(df) < self.GRID_N + 1:
            return None

        close = float(df["close"].iloc[-1])
        # 网格区间用前 20 日（不含当日）
        high = float(df["high"].iloc[-(self.GRID_N + 1) : -1].max())
        low = float(df["low"].iloc[-(self.GRID_N + 1) : -1].min())
        if high <= low:
            return None

        grid_size = (high - low) / self.GRID_LEVELS
        # 当前价相对网格中位的位置（0=最低, 1=最高）
        position_ratio = (close - low) / (high - low)

        # 信号触发：现价跌入下 1/3 区域（position_ratio <= 0.4）→ 网格买入
        if position_ratio > 0.4:
            return None

        confidence = max(40.0, 70.0 - position_ratio * 100)

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
                f"网格买入：现价 ¥{close:.3f} 处于 20 日区间 ¥{low:.3f}-¥{high:.3f} 的 {position_ratio * 100:.0f}% 位置"
            ),
            confidence=round(confidence, 1),
            extra={
                "grid_high": high,
                "grid_low": low,
                "grid_size": grid_size,
                "position_ratio": round(position_ratio, 3),
                "kind": "grid_buy",
            },
        )

    def signal_sell(self, position: dict[str, Any], df: pd.DataFrame) -> dict[str, Any] | None:
        """马丁加仓 + 网格止盈/止损"""
        if df is None or df.empty or len(df) < self.GRID_N + 1:
            return None
        close = float(df["close"].iloc[-1])
        avg_cost = position.get("avg_cost", 0)
        shares = position.get("shares", 0)
        if avg_cost <= 0 or shares <= 0:
            return None
        pnl_pct = (close / avg_cost - 1) * 100

        # 1. 网格上沿止盈（如果 position_ratio > 0.7）
        high = float(df["high"].iloc[-(self.GRID_N + 1) : -1].max())
        low = float(df["low"].iloc[-(self.GRID_N + 1) : -1].min())
        if high > low:
            pos_ratio = (close - low) / (high - low)
            if pos_ratio > 0.8 and pnl_pct > 5:
                return {
                    "reason": f"网格上沿止盈：现价位于区间 {pos_ratio * 100:.0f}% 位置",
                    "suggested_price": round(close * 0.995, 2),
                    "urgency": "normal",
                }

        # 2. 马丁加仓信号：浮亏 5% 触发（不直接执行，由用户决策）
        if pnl_pct <= self.MARTINGALE_LOSS * 100 and pnl_pct > self.STOP_LOSS * 100:
            return {
                "reason": (f"马丁加仓预警：浮亏 {pnl_pct:+.1f}%，按策略建议加仓 {shares} 股（翻倍）"),
                "suggested_price": round(close * 1.005, 2),
                "urgency": "warning",
                "action": "martingale_buy",
                "suggested_shares": shares,  # 加同等数量 = 翻倍总持仓
            }

        # 3. 兜底止损
        if pnl_pct <= self.STOP_LOSS * 100:
            return {
                "reason": f"触发 {self.STOP_LOSS * 100:.0f}% 兜底止损（当前 {pnl_pct:+.1f}%）",
                "suggested_price": round(close * 0.99, 2),
                "urgency": "urgent",
            }
        return None
