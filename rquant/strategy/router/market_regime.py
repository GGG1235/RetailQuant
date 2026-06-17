"""
rQuant.strategies.router.market_regime — 市场状态判断
- 基于指数 K 线（默认 sh000001 上证指数）判断 5 种状态
- 严格时序：只看 ≤ dt 的数据
- 按日缓存：避免每次调用都重算

5 个状态：
  STRONG_BULL:  强进攻（MA60 > MA120 × 1.02 + close > MA120 × 1.05）
  BULL:         进攻（MA60 > MA120 + close > MA120）
  SIDEWAYS:     震荡（其他）
  BEAR:         防守（MA60 < MA120 + close < MA120）
  STRONG_BEAR:  极致防守（MA60 < MA120 × 0.95 + close < MA120 × 0.95）

调用方式：
  from strategies.router.market_regime import MarketRegime, get_market_regime
  regime = get_market_regime()  # 按日缓存
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import pandas as pd

from ..base import ma, prev_ma


# 类型别名
Regime = Literal["STRONG_BULL", "BULL", "SIDEWAYS", "BEAR", "STRONG_BEAR"]


@dataclass
class MarketState:
    """市场状态完整信息"""

    regime: Regime
    close: float
    ma20: float
    ma60: float
    ma120: float
    ma60_direction: float  # MA60 当日 vs 5 日前，正=向上
    description: str

    def to_dict(self) -> dict:
        return {
            "regime": self.regime,
            "close": round(self.close, 3),
            "ma20": round(self.ma20, 3),
            "ma60": round(self.ma60, 3),
            "ma120": round(self.ma120, 3),
            "ma60_direction": round(self.ma60_direction, 4),
            "description": self.description,
        }


class MarketRegime:
    """市场状态检测器"""

    STRONG_BULL = "STRONG_BULL"
    BULL = "BULL"
    SIDEWAYS = "SIDEWAYS"
    BEAR = "BEAR"
    STRONG_BEAR = "STRONG_BEAR"

    # 阈值
    STRONG_BULL_MA_RATIO = 1.02  # MA60 / MA120
    STRONG_BULL_CLOSE_RATIO = 1.05  # close / MA120
    BULL_MA_RATIO = 1.0
    BEAR_MA_RATIO = 1.0
    STRONG_BEAR_MA_RATIO = 0.95
    STRONG_BEAR_CLOSE_RATIO = 0.95

    def detect(self, df: pd.DataFrame) -> MarketState:
        """根据指数 K 线判断市场状态，返回完整 MarketState

        严格时序：所有指标只用 ≤ 最后一天的数据
        """
        if df is None or len(df) < 130:
            return MarketState(
                regime=self.SIDEWAYS,
                close=0.0,
                ma20=0.0,
                ma60=0.0,
                ma120=0.0,
                ma60_direction=0.0,
                description="数据不足，默认震荡",
            )

        close = float(df["close"].iloc[-1])
        ma20 = ma(df, 20)
        ma60 = ma(df, 60)
        ma120 = ma(df, 120)
        ma60_prev = prev_ma(df, 60)
        ma60_dir = ma60 - ma60_prev if ma60_prev > 0 else 0.0

        # 5 个状态判定
        if ma60 > ma120 * self.STRONG_BULL_MA_RATIO and close > ma120 * self.STRONG_BULL_CLOSE_RATIO:
            regime = self.STRONG_BULL
            desc = f"强进攻：close ¥{close:.0f} > MA120×1.05，MA60 强于 MA120×1.02"
        elif ma60 > ma120 * self.BULL_MA_RATIO and close > ma120:
            regime = self.BULL
            desc = f"进攻：close ¥{close:.0f} 站上 MA120，MA60 > MA120"
        elif ma60 < ma120 * self.STRONG_BEAR_MA_RATIO and close < ma120 * self.STRONG_BEAR_CLOSE_RATIO:
            regime = self.STRONG_BEAR
            desc = f"极致防守：close ¥{close:.0f} < MA120×0.95，MA60 弱于 MA120×0.95"
        elif ma60 < ma120 * self.BEAR_MA_RATIO and close < ma120:
            regime = self.BEAR
            desc = f"防守：close ¥{close:.0f} 跌破 MA120，MA60 < MA120"
        else:
            regime = self.SIDEWAYS
            desc = f"震荡：close ¥{close:.0f} 在 MA120 附近（±5% 内）"

        return MarketState(
            regime=regime,
            close=close,
            ma20=ma20,
            ma60=ma60,
            ma120=ma120,
            ma60_direction=ma60_dir,
            description=desc,
        )


# ============== 按日缓存 + 全局单例 ==============

_REGIME_CACHE: dict[str, MarketState] = {}


def get_market_regime(index_df: pd.DataFrame | None = None) -> MarketState:
    """获取市场状态（按日缓存）

    传 index_df 时强制重算（用于测试）
    不传时优先用缓存，缓存 miss 时拉 sh000001 的 K 线算一次
    """
    today = datetime.now().strftime("%Y-%m-%d")

    if index_df is not None:
        # 强制重算
        state = MarketRegime().detect(index_df)
        _REGIME_CACHE[today] = state
        return state

    if today in _REGIME_CACHE:
        return _REGIME_CACHE[today]

    # 缓存 miss —— 拉指数 K 线
    try:
        from rquant.business.data import fetch_kline  # 延迟导入避免循环

        df = fetch_kline("sh000001", 130)
    except Exception:
        df = None

    state = MarketRegime().detect(df)
    _REGIME_CACHE[today] = state
    return state


def clear_regime_cache() -> None:
    """清空缓存（测试用）"""
    _REGIME_CACHE.clear()
