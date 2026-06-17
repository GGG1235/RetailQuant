"""
rQuant.strategies.pattern.dragon_tiger — 江恩/游资形态（骨架）
- 基线版：用日涨幅近似涨停板（科创板/创业板 20cm，主板 10cm）
- 形态识别：首板/二板/三板、突破前高
- 严格时序：只看 ≤ dt 的数据
- ⚠️ 完整版需要：涨停板接口（涨跌幅 >= 阈值）、连板天数、龙虎榜数据

信号逻辑：
- 买入触发：当日涨幅 ≥ 9.5%（近似主板涨停） + 突破 5 日新高
- 信心度：连板天数越多信心越高（基线版从 K线推算"连板"：连续 N 日涨幅 > 5%）
- 卖出：次日不板（涨幅 < 5%） / -5% 止损 / +20% 止盈

注册：@register
"""

from __future__ import annotations
from typing import Any

import pandas as pd

from ..base import Signal, change_pct
from ..registry import register


# 主板涨停阈值（含近似 10cm 和北交所 30cm）
_LIMIT_THRESHOLD = 0.095  # 9.5% 视为涨停
_STRONG_BAR = 0.05  # 5% 视为大阳线（连板判定）


def _count_consecutive_strong_bars(df: pd.DataFrame) -> int:
    """从最后一天往前数连续大阳线天数（含当日）"""
    if df is None or len(df) < 2:
        return 0
    n = 0
    for i in range(len(df) - 1, 0, -1):
        prev_close = float(df["close"].iloc[i - 1])
        if prev_close <= 0:
            break
        chg = float(df["close"].iloc[i]) / prev_close - 1
        if chg >= _STRONG_BAR:
            n += 1
        else:
            break
    return n


@register
class DragonTigerPattern:
    """游资形态（涨停/连板近似）"""

    name = "DragonTigerPattern"
    category = "pattern"
    description = "涨停板/连板形态识别（涨幅阈值近似，需涨停板接口升级）"

    # 参数
    LIMIT_THRESHOLD = _LIMIT_THRESHOLD
    STRONG_BAR = _STRONG_BAR
    NEW_HIGH_N = 5  # 突破 5 日新高
    TAKE_PROFIT = 0.20
    STOP_LOSS = -0.05  # 游资策略止损严

    def signal_buy(self, code: str, name: str, sector: str, df: pd.DataFrame) -> Signal | None:
        if df is None or len(df) < self.NEW_HIGH_N + 1:
            return None

        close = float(df["close"].iloc[-1])
        prev_close = float(df["close"].iloc[-2])
        if prev_close <= 0:
            return None
        chg = close / prev_close - 1

        # 涨停或近涨停
        if chg < self.LIMIT_THRESHOLD:
            return None

        # 突破 5 日新高（不含当日）
        prev_n_high = float(df["high"].iloc[-(self.NEW_HIGH_N + 1) : -1].max())
        if close <= prev_n_high:
            return None

        # 连板天数
        consecutive = _count_consecutive_strong_bars(df)
        # 标记板数
        if consecutive >= 3:
            board_tag = f"{consecutive}连板"
        elif consecutive == 2:
            board_tag = "2连板"
        else:
            board_tag = "首板"

        confidence = max(60.0, min(90.0, 65.0 + consecutive * 8))

        suggested = round(close * 1.02, 2)  # 涨停板次日 +2% 排队
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
                f"游资形态：{board_tag}（涨幅 {chg * 100:+.2f}%），突破 5 日高点 ¥{prev_n_high:.3f}，"
                f"连板 {consecutive} 天"
            ),
            confidence=round(confidence, 1),
            extra={
                "consecutive_boards": consecutive,
                "board_tag": board_tag,
                "change_pct": round(chg * 100, 2),
                "prev_n_high": prev_n_high,
                "kind": "dragon_tiger",
                "need_data_source": "涨停板接口 / 龙虎榜 / 板块成分股（当前用涨幅近似）",
            },
        )

    def signal_sell(self, position: dict[str, Any], df: pd.DataFrame) -> dict[str, Any] | None:
        if df is None or df.empty or len(df) < 3:
            return None
        close = float(df["close"].iloc[-1])
        chg = change_pct(df)
        avg_cost = position.get("avg_cost", 0)
        if avg_cost <= 0:
            return None
        pnl_pct = (close / avg_cost - 1) * 100

        # 次日不板 → 走人
        if chg < 0.03 and pnl_pct > 3:
            return {
                "reason": f"次日不板（涨幅 {chg * 100:+.2f}% < 3%），游资走人",
                "suggested_price": round(close * 0.99, 2),
                "urgency": "urgent",
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
