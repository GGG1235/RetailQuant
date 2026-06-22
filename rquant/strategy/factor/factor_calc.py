"""
rquant.strategy.factor.factor_calc — 因子计算 + 预处理流水线 + Top-N 选股

流水线:
  原始数据 → 硬过滤 → 因子提取 → MAD去极值 → Z-Score → 方向对齐 → 等权重合成 → Top-N

因子方向:
  正向: ROE, 动量 (越高越好)
  负向: PE, PB, 总市值 (越低越好 → 取反)
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from rquant.data_source.eastmoney import get_all_snapshots
from rquant.business.data import fetch_kline

# ============== 常量 ==============

# 硬过滤
MIN_KLINES = 120  # 至少 120 根 K 线（近似上市满 6 个月）
MAX_STALE_DAYS = 5  # K 线最后一天距调仓日 ≤5 天（防停牌）

# MAD 去极值
MAD_N_STD = 3.0  # 截断倍数
MAD_SCALE = 1.4826  # 正态分布修正

# Top-N
DEFAULT_TOP_N = 30


# ============== 硬过滤 ==============


def _hard_filter(
    codes: list[str],
    snapshots: dict[str, dict],
    kline_map: dict[str, pd.DataFrame],
    rebalance_date: str,
) -> list[str]:
    """硬过滤：剔除 ST / 次新股 / 停牌股"""
    passed = []
    for code in codes:
        snap = snapshots.get(code)
        if snap is None:
            continue

        # 1) ST 过滤
        name = snap.get("name", "")
        if "ST" in name.upper():
            continue

        # 2) 次新股过滤：K 线数量不足
        df = kline_map.get(code)
        if df is None or df.empty or len(df) < MIN_KLINES:
            continue

        # 3) 停牌过滤：最新 K 线日期距调仓日过远
        last_date = str(df["date"].iloc[-1])
        try:
            d_last = pd.Timestamp(last_date)
            d_rb = pd.Timestamp(rebalance_date)
            if (d_rb - d_last).days > MAX_STALE_DAYS:
                continue
        except Exception:
            continue

        passed.append(code)
    return passed


# ============== 因子提取 ==============


def _extract_momentum(code: str, df: pd.DataFrame) -> Optional[float]:
    """20 日动量因子：现价 / 20日前收盘 - 1"""
    if df is None or len(df) < 21:
        return None
    try:
        return float(df["close"].iloc[-1] / df["close"].iloc[-21] - 1)
    except Exception:
        return None


def _extract_factors(
    codes: list[str],
    snapshots: dict[str, dict],
    kline_map: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """从财务快照 + K 线中提取四因子，返回 DataFrame（index=code, columns=PE/PB/ROE/MOM/MCAP）"""
    rows = []
    for code in codes:
        snap = snapshots.get(code, {})
        kdf = kline_map.get(code)

        pe = snap.get("pe_ttm")
        pb = snap.get("pb")
        roe = snap.get("roe")
        mcap = snap.get("mcap")
        mom = _extract_momentum(code, kdf) if kdf is not None else None

        # 至少需要一个有效因子
        if all(v is None for v in [pe, pb, roe, mcap, mom]):
            continue

        rows.append(
            {
                "code": code,
                "PE": pe,
                "PB": pb,
                "ROE": roe,
                "MOM": mom,
                "MCAP": mcap,
            }
        )

    return pd.DataFrame(rows).set_index("code")


# ============== 预处理 ==============


def _winsorize_series(s: pd.Series) -> pd.Series:
    """MAD 法去极值"""
    clean = s.dropna()
    if len(clean) < 3:
        return s
    median = clean.median()
    mad = (clean - median).abs().median()
    if mad == 0:
        return s
    upper = median + MAD_N_STD * MAD_SCALE * mad
    lower = median - MAD_N_STD * MAD_SCALE * mad
    return s.clip(lower, upper)


def _zscore_series(s: pd.Series) -> pd.Series:
    """Z-Score 标准化"""
    clean = s.dropna()
    if len(clean) < 3:
        return s
    mean = clean.mean()
    std = clean.std()
    if std == 0:
        return s - mean
    return (s - mean) / std


# ============== 主流水线 ==============


def run_pipeline(
    snap_date: str,
    rebalance_date: str,
    kline_days: int = 250,
    top_n: int = DEFAULT_TOP_N,
) -> Optional[pd.DataFrame]:
    """执行完整选股流水线。

    参数:
        snap_date:       财务快照日期（如 '2024-12-31'）
        rebalance_date:  调仓日（如 '2025-01-02'），用于 K 线截止判断
        kline_days:      拉取 K 线的天数
        top_n:           选取前 N 只股票

    返回:
        包含 code, PE_score, PB_score, ROE_score, MOM_score, MCAP_score, total_score 的 DataFrame
    """
    # 1) 获取财务快照
    snapshots = get_all_snapshots(snap_date)
    if not snapshots:
        print(f"[factor_calc] 无财务快照: {snap_date}")
        return None

    all_codes = list(snapshots.keys())
    print(f"[factor_calc] 财务快照: {len(all_codes)} 只")

    # 2) 拉取 K 线（全部股票）
    kline_map: dict[str, pd.DataFrame] = {}
    fetched = 0
    for code in all_codes:
        df = fetch_kline(code, kline_days)
        if df.empty:
            continue
        # ★ 严格时序：只用 ≤ rebalance_date 的数据，防止 look-ahead bias
        # 例如调仓日是 2025-06-01，不能用到 2025-06-02 之后的收盘价算动量
        df = df[df["date"] <= rebalance_date].reset_index(drop=True)
        if df.empty:
            continue
        kline_map[code] = df
        fetched += 1
    print(f"[factor_calc] K 线获取: {fetched}/{len(all_codes)}")

    # 3) 硬过滤
    passed = _hard_filter(all_codes, snapshots, kline_map, rebalance_date)
    print(f"[factor_calc] 硬过滤后: {len(passed)} 只 (ST/次新/停牌已剔除)")

    if len(passed) < top_n:
        print(f"[factor_calc] 可用股票不足 Top-{top_n}，仅 {len(passed)} 只")
        return None

    # 4) 因子提取
    df_factors = _extract_factors(passed, snapshots, kline_map)
    print(f"[factor_calc] 因子提取: {len(df_factors)} 只有效数据")

    # 5) 预处理（逐列去极值 + 标准化）
    factor_cols = ["PE", "PB", "ROE", "MOM", "MCAP"]
    for col in factor_cols:
        if col in df_factors.columns:
            df_factors[f"{col}_raw"] = df_factors[col]
            df_factors[col] = _winsorize_series(df_factors[col])
            df_factors[f"{col}_z"] = _zscore_series(df_factors[col])

    # 6) 方向对齐：PE/PB/MCAP 越小越好 → 取反；ROE/MOM 越大越好 → 保持
    df_factors["PE_score"] = -df_factors["PE_z"].fillna(0)
    df_factors["PB_score"] = -df_factors["PB_z"].fillna(0)
    df_factors["ROE_score"] = df_factors["ROE_z"].fillna(0)
    df_factors["MOM_score"] = df_factors["MOM_z"].fillna(0)
    df_factors["MCAP_score"] = -df_factors["MCAP_z"].fillna(0)

    # 7) 等权重合成（仅使用有效因子的均值）
    score_cols = ["PE_score", "PB_score", "ROE_score", "MOM_score", "MCAP_score"]
    valid_count = df_factors[score_cols].notna().sum(axis=1)
    df_factors["total_score"] = df_factors[score_cols].sum(axis=1) / valid_count.replace(0, 1)

    # 8) 降序排序 + Top-N
    df_result = df_factors.sort_values("total_score", ascending=False).head(top_n).copy()
    df_result = df_result.reset_index()  # code 变列
    df_result = df_result.rename(columns={"index": "code"})

    # 精简输出列
    out_cols = ["code", "PE_score", "PB_score", "ROE_score", "MOM_score", "MCAP_score", "total_score"]
    existing = [c for c in out_cols if c in df_result.columns]

    print(f"[factor_calc] Top-{top_n} 选股完成")
    return df_result[existing]
