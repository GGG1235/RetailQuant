"""
rquant.strategy.factor.backtest_engine — 回测引擎
- 月频调仓
- 等资金权重
- 交易成本（佣金+印花税+滑点）
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
import numpy as np

from rquant.strategy.factor.factor_calc import run_pipeline
from rquant.business.data import fetch_kline
from rquant.log import info

# ============== 交易成本 ==============

# 买入端: 佣金万1 + 滑点5bp
BUY_COST = 0.0001 + 0.0005  # = 0.0006

# 卖出端: 佣金万1 + 印花税千1 + 滑点5bp
SELL_COST = 0.0001 + 0.001 + 0.0005  # = 0.0016


# ============== 调仓日生成 ==============


def _monthly_rebalance_dates(start: str, end: str) -> list[str]:
    """生成每月第一个有数据的交易日列表（用 pd.bdate_range 近似）"""
    dates = pd.bdate_range(start=start, end=end, freq="BMS")  # 每月第一个工作日
    return [d.strftime("%Y-%m-%d") for d in dates]


# ============== 回测引擎 ==============


def run_backtest(
    snap_date: str,
    start_date: str,
    end_date: str,
    initial_capital: float = 1_000_000,
    top_n: int = 30,
    kline_days: int = 250,
) -> Optional[dict]:
    """执行单期（固定财务快照）多因子选股回测。

    参数:
        snap_date:       财务快照日期（贯穿整个回测期不变）
        start_date:      回测起始日 YYYY-MM-DD
        end_date:        回测结束日 YYYY-MM-DD
        initial_capital: 初始资金（默认 100 万）
        top_n:           每期持仓数量
        kline_days:      因子计算所需 K 线天数

    返回:
        metrics          dict with cumulative_return, annual_return, max_drawdown,
                          sharpe, turnover, monthly_nav
    """
    rebalance_dates = _monthly_rebalance_dates(start_date, end_date)
    if not rebalance_dates:
        info("backtest", "无调仓日")
        return None

    # 确保 start_date 是第一个调仓日
    first_rb = rebalance_dates[0]
    if first_rb < start_date:
        rebalance_dates = [d for d in rebalance_dates if d >= start_date]

    info("backtest", f"调仓日: {len(rebalance_dates)} 个 ({rebalance_dates[0]} ~ {rebalance_dates[-1]})")

    # ----- 状态变量 -----
    cash = initial_capital
    holdings: dict[str, float] = {}  # code → 持有股数

    monthly_nav: list[dict] = []  # {date, nav, cash, equity}
    total_turnover = 0.0

    for i, rb_date in enumerate(rebalance_dates):
        info("backtest", f"调仓 {i + 1}/{len(rebalance_dates)}: {rb_date}")

        # 1) 运行选股流水线
        df_picks = run_pipeline(
            snap_date=snap_date,
            rebalance_date=rb_date,
            kline_days=kline_days,
            top_n=top_n,
        )

        if df_picks is None or df_picks.empty:
            info("backtest", "→ 无选股结果，跳过本期")
            # 记录净值（不变）
            total = cash + _holdings_value(holdings, rb_date)
            monthly_nav.append({"date": rb_date, "nav": total, "cash": cash, "equity": total - cash})
            continue

        new_codes = list(df_picks["code"])
        info("backtest", f"→ 选股: {len(new_codes)} 只")

        # 2) 卖出不在新持仓中的股票
        sold_value = 0.0
        for code in list(holdings.keys()):
            if code not in new_codes:
                shares = holdings.pop(code)
                price = _get_price(code, rb_date)
                if price > 0:
                    proceed = shares * price * (1 - SELL_COST)
                    cash += proceed
                    sold_value += proceed
                    total_turnover += shares * price

        # 3) 等权重调仓（买入新标的 / 调整已有仓位）
        n_new = len(new_codes)
        if n_new == 0:
            continue

        total_capital = cash + _holdings_value(holdings, rb_date)
        target_per_stock = total_capital / n_new

        for code in new_codes:
            price = _get_price(code, rb_date)
            if price <= 0:
                continue

            current_shares = holdings.get(code, 0)
            current_value = current_shares * price
            diff_value = target_per_stock - current_value

            if abs(diff_value) < price:
                # 差额不够买 1 股，跳过
                continue

            if diff_value > 0:
                # 加仓（含新建仓）
                cost_per_share = price * (1 + BUY_COST)
                buy_shares = int(diff_value / cost_per_share)
                if buy_shares > 0:
                    cost = buy_shares * cost_per_share
                    cash -= cost
                    holdings[code] = current_shares + buy_shares
                    total_turnover += buy_shares * price
            else:
                # 减仓
                sell_shares = int(abs(diff_value) / (price * (1 - SELL_COST)))
                sell_shares = min(sell_shares, current_shares)
                if sell_shares > 0:
                    proceed = sell_shares * price * (1 - SELL_COST)
                    cash += proceed
                    total_turnover += sell_shares * price
                    new_shares = current_shares - sell_shares
                    if new_shares > 0:
                        holdings[code] = new_shares
                    else:
                        holdings.pop(code, None)

        # 5) 记录月末净值
        equity = _holdings_value(holdings, rb_date)
        total = cash + equity
        monthly_nav.append({"date": rb_date, "nav": total, "cash": cash, "equity": equity})

        n_hold = len(holdings)
        info("backtest", f"持仓 {n_hold} 只 | 现金 ¥{cash:,.0f} | 股票市值 ¥{equity:,.0f} | 总资产 ¥{total:,.0f}")

    # 最终净值（用最后一天收盘价清算）

    # ----- 计算指标 -----
    metrics = _compute_metrics(monthly_nav, initial_capital, total_turnover)
    metrics["monthly_nav"] = monthly_nav

    info("backtest", f"累计收益率: {metrics['cumulative_return']:.2%}")
    info("backtest", f"年化收益率: {metrics['annual_return']:.2%}")
    info("backtest", f"最大回撤:   {metrics['max_drawdown']:.2%}")
    info("backtest", f"夏普比率:   {metrics['sharpe_ratio']:.2f}")
    info("backtest", f"平均换手率: {metrics['turnover']:.2%}")

    return metrics


def _get_price(code: str, date_str: str) -> float:
    """获取指定日期收盘价（从 K 线中查找）"""
    df = fetch_kline(code, 365)
    if df.empty:
        return 0.0
    match = df[df["date"] == date_str]
    if not match.empty:
        return float(match["close"].iloc[0])
    # 没精确匹配，取最近一日
    df["date"] = pd.to_datetime(df["date"])
    target = pd.Timestamp(date_str)
    before = df[df["date"] <= target]
    if before.empty:
        return 0.0
    return float(before["close"].iloc[-1])


def _holdings_value(holdings: dict[str, float], date_str: str) -> float:
    """计算持仓市值"""
    total = 0.0
    for code, shares in holdings.items():
        price = _get_price(code, date_str)
        total += shares * price
    return total


def _compute_metrics(monthly_nav: list[dict], initial_capital: float, total_turnover: float) -> dict:
    """从月度净值序列计算指标"""
    if not monthly_nav:
        return {
            "cumulative_return": 0.0,
            "annual_return": 0.0,
            "max_drawdown": 0.0,
            "sharpe_ratio": 0.0,
            "turnover": 0.0,
        }

    nav_series = pd.Series([m["nav"] for m in monthly_nav])
    dates = pd.to_datetime([m["date"] for m in monthly_nav])

    # 累计收益
    final_nav = nav_series.iloc[-1]
    cumulative_return = final_nav / initial_capital - 1

    # 年化收益
    days = (dates[-1] - dates[0]).days
    if days > 0:
        annual_return = (1 + cumulative_return) ** (365 / days) - 1
    else:
        annual_return = 0.0

    # 最大回撤
    peak = nav_series.expanding().max()
    drawdown = (nav_series - peak) / peak
    max_drawdown = float(drawdown.min())

    # 月度收益率
    monthly_returns = nav_series.pct_change().dropna()
    if len(monthly_returns) > 1:
        # 年化夏普（无风险利率设为 0）
        sharpe = (
            float(monthly_returns.mean() / monthly_returns.std() * np.sqrt(12)) if monthly_returns.std() > 0 else 0.0
        )
    else:
        sharpe = 0.0

    # 平均换手率（每期换手 / 期数）
    n_periods = len(monthly_nav)
    turnover = total_turnover / (initial_capital * n_periods) if n_periods > 0 else 0.0

    return {
        "cumulative_return": round(cumulative_return, 6),
        "annual_return": round(annual_return, 6),
        "max_drawdown": round(max_drawdown, 6),
        "sharpe_ratio": round(sharpe, 4),
        "turnover": round(turnover, 6),
    }
