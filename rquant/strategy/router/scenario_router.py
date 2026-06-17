"""
rQuant.strategies.router.scenario_router — 场景路由器
- 根据大盘状态（牛/熊/震荡）路由到不同子策略组合
- 路由器本身是一个策略类（注册到新引擎）
- 内部组合：先调 MarketRegime 算状态，再选子策略跑

5 个状态 → 子策略类别映射：

  STRONG_BULL: 强进攻
    └─ turtle + volume_breakout + factor
       （趋势 + 突破 + 横截面选股）

  BULL: 进攻
    └─ turtle + volume_breakout + factor + etf_rotation
       （加入 ETF 板块轮动）

  SIDEWAYS: 震荡
    └─ factor + grid + etf_rotation
       （多因子 + 网格 + ETF 轮动）

  BEAR: 防守
    └─ etf_rotation + grid + legacy
       （ETF + 网格 + 老策略低吸）

  STRONG_BEAR: 极致防守
    └─ etf_rotation + legacy
       （只留红利/低吸类，不主动出击）

注册：@register，category="router"
"""

from __future__ import annotations
from typing import Any

import pandas as pd

from ..base import Signal
from ..registry import register
from .market_regime import MarketRegime, get_market_regime


# 状态 → 子策略类别映射
ROUTING_TABLE: dict[str, list[str]] = {
    MarketRegime.STRONG_BULL: ["turtle", "volume_breakout", "factor"],
    MarketRegime.BULL: ["turtle", "volume_breakout", "factor", "etf_rotation"],
    MarketRegime.SIDEWAYS: ["factor", "grid", "etf_rotation"],
    MarketRegime.BEAR: ["etf_rotation", "grid", "legacy"],
    MarketRegime.STRONG_BEAR: ["etf_rotation", "legacy"],
}


@register
class ScenarioRouter:
    """场景路由器"""

    name = "ScenarioRouter"
    category = "router"
    description = "根据大盘状态(牛/熊/震荡)动态路由到不同子策略组合"

    def _pick_subcategories(self, regime: str) -> list[str]:
        return ROUTING_TABLE.get(regime, [])

    def signal_buy(self, code: str, name: str, sector: str, df: pd.DataFrame) -> Signal | None:
        if df is None or df.empty:
            return None

        # 1. 算大盘状态（按日缓存）
        state = get_market_regime()

        # 2. 取该状态下的子策略类别
        sub_cats = self._pick_subcategories(state.regime)
        if not sub_cats:
            return None

        # 3. 跑这些子策略（按多个类别聚合）
        from .scenario_router import by_category_categories

        sigs: list[Signal] = []
        for strat in by_category_categories(sub_cats):
            try:
                sig = strat.signal_buy(code, name, sector, df)
            except Exception as e:
                print(f"⚠️ {strat.name} 异常: {e}")
                continue
            if sig is not None:
                sigs.append(sig)

        if not sigs:
            return None

        # 4. 取 confidence 最高的（如果多个子策略同时命中，路由器给出最强信号）
        best = max(sigs, key=lambda s: s.confidence)
        # 5. 在 extra 里附上市场状态信息
        best.extra["router_regime"] = state.regime
        best.extra["router_regime_desc"] = state.description
        best.extra["router_sub_cats"] = sub_cats
        best.extra["router_candidate_count"] = len(sigs)
        best.extra["kind"] = "scenario_router"
        return best

    def signal_sell(self, position: dict[str, Any], df: pd.DataFrame) -> dict[str, Any] | None:
        """卖出：复用 scan_sell（跑所有策略的卖出信号）"""
        from .. import scan_sell

        return scan_sell(position, df)


def by_category_categories(categories: list[str]) -> list:
    """按多个类别过滤策略"""
    from ..registry import by_category

    result = []
    for cat in categories:
        result.extend(by_category(cat))
    return result
