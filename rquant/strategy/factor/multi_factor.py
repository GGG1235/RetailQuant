"""
rQuant.strategies.factor.multi_factor — 多因子选股（完整版 v2）

设计原则
========
- 横截面（cross-section）+ 时间序列（time-series）双视角
- 8 个因子分 3 组：动量 / 趋势 / 量价
- 4 道过滤：停牌 / 流动性 / ST / 上市天数
- 严格时序：所有因子只看 ≤ dt 的数据
- 输出 score() 方法供回测引擎用（不只是 trigger 后的 Signal）

8 因子组成
==========
动量组 (W=0.35)
  M1  20 日动量（norm）
  M2  60 日动量（norm）

趋势组 (W=0.35)
  T1  MA20 偏离度（现价/MA20 - 1）
  T2  多头排列得分（MA5>MA10>MA20 给 +1, 否则给负）
  T3  突破 60 日新高（close >= high_60 * 0.98）

量价组 (W=0.30)
  V1  量比（5 日，norm）
  V2  量价共振：量比 + 当日涨幅 同向加分
  V3  波动率惩罚（20 日，越高越扣分）

信号逻辑
========
- 全部因子归一化到 [-1, +1]
- 加权求和 → score ∈ [-1, +1]
- score >= SCORE_BUY (0.5) → 触发买入信号
- 横截面 topN（回测引擎用 score() 排序）
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import math

import pandas as pd

from ..base import Signal, change_pct, ma, momentum, vol_ratio
from ..registry import register


# ============== 因子归一化 ==============


def _norm_tanh(x: float, scale: float = 1.0) -> float:
    """tanh 归一化到 [-1, +1]，scale 控制灵敏度（值越大越不敏感）"""
    return math.tanh(x / scale)


def _norm_clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


# ============== 因子 ==============


def _factor_momentum_20d(df: pd.DataFrame) -> float:
    """M1: 20 日动量 → [-1, +1]（±10% 截断）"""
    if len(df) < 21:
        return 0.0
    mom = momentum(df, 20) * 100  # %
    return _norm_clip(mom / 10.0)


def _factor_momentum_60d(df: pd.DataFrame) -> float:
    """M2: 60 日动量 → [-1, +1]（±20% 截断）"""
    if len(df) < 61:
        return 0.0
    mom = momentum(df, 60) * 100  # %
    return _norm_clip(mom / 20.0)


def _factor_ma20_bias(df: pd.DataFrame) -> float:
    """T1: MA20 偏离度（现价/MA20 - 1）→ tanh(±10% 灵敏度)"""
    if len(df) < 20:
        return 0.0
    ma20 = ma(df, 20)
    if ma20 <= 0:
        return 0.0
    bias = (float(df["close"].iloc[-1]) / ma20 - 1) * 100  # %
    return _norm_tanh(bias, scale=5.0)  # 5% 偏离 → 0.76


def _factor_ma_alignment(df: pd.DataFrame) -> float:
    """T2: 多头排列得分：MA5 > MA10 > MA20 全满足 +1，否则 -0.5"""
    if len(df) < 20:
        return 0.0
    ma5 = ma(df, 5)
    ma10 = ma(df, 10)
    ma20 = ma(df, 20)
    if ma5 > ma10 > ma20:
        return 1.0
    if ma5 < ma10 < ma20:
        return -1.0  # 空头排列
    return -0.3  # 混乱


def _factor_breakout_60d(df: pd.DataFrame) -> float:
    """T3: 60 日突破：close >= high_60 * 0.98 → 接近新高，强度按距离

    距离前高 < 2% → +0.6 ~ +1.0
    距离前高 > 10% → -1.0
    """
    if len(df) < 60:
        return 0.0
    high_60 = float(df["high"].tail(60).max())
    if high_60 <= 0:
        return 0.0
    close = float(df["close"].iloc[-1])
    dist = (high_60 - close) / high_60 * 100  # 距离前高%
    if dist < 0:
        return 1.0  # 突破新高
    return _norm_clip(1.0 - dist / 10.0)  # 2%→0.8, 10%→0


def _factor_vol_ratio(df: pd.DataFrame) -> float:
    """V1: 量比（5 日）→ [-1, +1]（±100% 灵敏度）"""
    if len(df) < 6:
        return 0.0
    vr = vol_ratio(df, 5)
    return _norm_tanh(vr - 1.0, scale=1.0)  # 1.0 → 0, 2.0 → 0.76, 0 → -0.76


def _factor_volume_price_sync(df: pd.DataFrame) -> float:
    """V2: 量价共振：量比 > 1.2 且 当日涨幅 > 0 → +0.5~+1.0
    反向：量比 < 0.8 且 涨幅 < 0 → 负分
    """
    if len(df) < 6:
        return 0.0
    vr = vol_ratio(df, 5)
    chg = change_pct(df) * 100  # %
    if vr > 1.2 and chg > 0:
        return _norm_clip((vr - 1.0) / 2.0 + chg / 5.0)
    if vr < 0.8 and chg < 0:
        return _norm_clip((vr - 1.0) / 2.0 + chg / 5.0)
    return 0.0


def _factor_volatility(df: pd.DataFrame) -> float:
    """V3: 波动率惩罚（20 日 std/mean）→ 越高越负分"""
    if len(df) < 21:
        return 0.0
    close = df["close"].tail(21).iloc[:-1]  # 不含当日
    mean = close.mean()
    if mean <= 0:
        return 0.0
    vol = close.std() / mean * 100  # %
    # 3% → 0, 6% → -0.5, 10% → -1
    return _norm_clip(-(vol - 3.0) / 7.0)


# ============== 过滤 ==============


@dataclass
class FilterResult:
    """过滤检查结果"""

    passed: bool
    reasons: list[str]


def _check_filters(
    df: pd.DataFrame,
    name: str = "",
    code: str = "",
    min_history_days: int = 60,
    min_avg_turnover: float = 5_000_000,
) -> FilterResult:
    """4 道过滤：停牌 / 流动性 / ST / 上市天数"""
    reasons: list[str] = []

    # 1. 停牌：当日成交量为 0
    if float(df["volume"].iloc[-1]) <= 0:
        reasons.append("停牌（成交量=0）")

    # 2. 流动性：20 日均成交额（用 volume * close 估算）
    if len(df) >= 20:
        avg_turnover = float((df["close"].tail(20) * df["volume"].tail(20)).mean())
        if avg_turnover < min_avg_turnover:
            reasons.append(f"流动性差（20日均成交额 {avg_turnover / 1e6:.1f}万 < {min_avg_turnover / 1e4:.0f}万）")

    # 3. ST：名称含 ST
    if "ST" in (name or "").upper() or "退" in (name or ""):
        reasons.append("ST / 退市股")

    # 4. 上市天数：K 线不足视为新股/数据不足
    if len(df) < min_history_days:
        reasons.append(f"上市/数据天数不足（{len(df)} < {min_history_days}）")

    return FilterResult(passed=len(reasons) == 0, reasons=reasons)


# ============== 策略类 ==============


@register
class MultiFactor:
    """多因子选股 v2 — 8 因子 / 4 过滤 / 横截面友好"""

    name = "MultiFactor"
    category = "factor"
    description = "8 因子综合（动量×2 + 趋势×3 + 量价×3）+ 4 道过滤"

    # 因子权重（合计 = 1.0）
    W_MOMENTUM_20D = 0.20
    W_MOMENTUM_60D = 0.15
    W_MA20_BIAS = 0.12
    W_MA_ALIGNMENT = 0.10
    W_BREAKOUT_60D = 0.13
    W_VOL_RATIO = 0.12
    W_VOL_PRICE_SYNC = 0.13
    W_VOLATILITY = 0.05  # 绝对值小，惩罚项

    # 触发阈值
    SCORE_BUY = 0.50
    # 风控
    TAKE_PROFIT = 0.15
    STOP_LOSS = -0.08
    # 持仓
    MAX_HOLD_DAYS = 21  # 21 个交易日不涨就退出
    # 过滤
    MIN_HISTORY_DAYS = 60  # 上市天数
    MIN_AVG_TURNOVER = 5_000_000  # 流动性

    # ============== 单只打分（回测引擎用）==============

    def compute_factors(self, df: pd.DataFrame) -> dict[str, float]:
        """算 8 个原始因子值（未加权），给回测 / 调试用"""
        return {
            "M1_momentum_20d": _factor_momentum_20d(df),
            "M2_momentum_60d": _factor_momentum_60d(df),
            "T1_ma20_bias": _factor_ma20_bias(df),
            "T2_ma_alignment": _factor_ma_alignment(df),
            "T3_breakout_60d": _factor_breakout_60d(df),
            "V1_vol_ratio": _factor_vol_ratio(df),
            "V2_vol_price_sync": _factor_volume_price_sync(df),
            "V3_volatility": _factor_volatility(df),
        }

    def score(self, df: pd.DataFrame, name: str = "", code: str = "") -> tuple[float, dict]:
        """对单只股票打分（含过滤），返回 (score, 详情)"""
        flt = _check_filters(
            df,
            name=name,
            code=code,
            min_history_days=self.MIN_HISTORY_DAYS,
            min_avg_turnover=self.MIN_AVG_TURNOVER,
        )
        if not flt.passed:
            return float("-inf"), {"filtered": True, "reasons": flt.reasons}

        factors = self.compute_factors(df)
        weighted = (
            factors["M1_momentum_20d"] * self.W_MOMENTUM_20D
            + factors["M2_momentum_60d"] * self.W_MOMENTUM_60D
            + factors["T1_ma20_bias"] * self.W_MA20_BIAS
            + factors["T2_ma_alignment"] * self.W_MA_ALIGNMENT
            + factors["T3_breakout_60d"] * self.W_BREAKOUT_60D
            + factors["V1_vol_ratio"] * self.W_VOL_RATIO
            + factors["V2_vol_price_sync"] * self.W_VOL_PRICE_SYNC
            + factors["V3_volatility"] * self.W_VOLATILITY
        )
        return weighted, {
            "filtered": False,
            "factors": factors,
            "weighted_components": {
                "M1_momentum_20d": factors["M1_momentum_20d"] * self.W_MOMENTUM_20D,
                "M2_momentum_60d": factors["M2_momentum_60d"] * self.W_MOMENTUM_60D,
                "T1_ma20_bias": factors["T1_ma20_bias"] * self.W_MA20_BIAS,
                "T2_ma_alignment": factors["T2_ma_alignment"] * self.W_MA_ALIGNMENT,
                "T3_breakout_60d": factors["T3_breakout_60d"] * self.W_BREAKOUT_60D,
                "V1_vol_ratio": factors["V1_vol_ratio"] * self.W_VOL_RATIO,
                "V2_vol_price_sync": factors["V2_vol_price_sync"] * self.W_VOL_PRICE_SYNC,
                "V3_volatility": factors["V3_volatility"] * self.W_VOLATILITY,
            },
        }

    def score_batch(self, code_df_map: dict[str, pd.DataFrame], name_map: dict[str, str] | None = None) -> list[dict]:
        """批量打分 + 横截面 rank（回测用）

        返回按 score 降序排的列表，每项 {code, name, score, rank, factors}
        """
        name_map = name_map or {}
        results: list[dict] = []
        for code, df in code_df_map.items():
            if df is None or df.empty:
                continue
            s, detail = self.score(df, name=name_map.get(code, code), code=code)
            results.append({"code": code, "name": name_map.get(code, code), "score": s, **detail})

        # 过滤掉 -inf
        results = [r for r in results if r["score"] != float("-inf")]
        # rank
        results.sort(key=lambda x: x["score"], reverse=True)
        for i, r in enumerate(results, 1):
            r["rank"] = i
            r["rank_pct"] = i / len(results) if results else 1.0
        return results

    # ============== 标准协议（单只触发）==============

    def signal_buy(self, code: str, name: str, sector: str, df: pd.DataFrame) -> Signal | None:
        s, detail = self.score(df, name=name, code=code)
        if s == float("-inf"):
            return None
        if s < self.SCORE_BUY:
            return None

        close = float(df["close"].iloc[-1])
        confidence = round(min(90.0, 55.0 + s * 30.0), 1)
        suggested = round(close * 1.005, 2)

        f = detail.get("factors", {})
        wc = detail.get("weighted_components", {})
        # 排序 Top-3 贡献因子（绝对值降序）
        top3 = sorted(wc.items(), key=lambda kv: abs(kv[1]), reverse=True)[:3]
        top3_str = " / ".join(f"{k.replace('_', ' ')} {v:+.2f}" for k, v in top3)

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
            reason=(f"多因子综合 {s:+.2f}（{len(f)} 因子）| Top3: {top3_str}"),
            confidence=confidence,
            extra={
                "score": round(s, 3),
                "factors": {k: round(v, 3) for k, v in f.items()},
                "weighted_components": {k: round(v, 3) for k, v in wc.items()},
                "top3": [(k, round(v, 3)) for k, v in top3],
                "kind": "multi_factor_v2",
                "version": 2,
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
