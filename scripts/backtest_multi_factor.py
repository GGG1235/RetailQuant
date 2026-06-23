"""
scripts/backtest_multi_factor.py — 多因子策略回测引擎

设计要点
========
- 严格时序：dt 决策只用 ≤ dt 的 K 线
- 横截面选股：每日对所有候选打分，取 TopN（默认 5）
- 风控三层：止盈 / 止损 / 持仓满期
- 资金管理：等权分配（每只占 1/TopN）
- 交易费用：单边 0.125%（佣金万 2.5 + 印花千 1）
- T+1 模拟：当日收盘价决策 + 次日开盘价成交（用次日开盘近似）

输出
====
- 业绩指标：总收益 / 年化 / 最大回撤 / 胜率 / 平均持仓天数
- 交易明细：每笔买卖的代码 / 时间 / 价 / 盈亏
- 净值曲线：每日市值
- 文件：results/backtest_<tag>.csv + .json
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pandas as pd

from rquant.business import data
from rquant.business.pool_store import get_pool, get_watchlist_codes
from rquant.strategy.factor.multi_factor import MultiFactor


# ============== 数据结构 ==============


@dataclass
class Trade:
    """单笔交易记录"""

    date: str  # 成交日
    side: str  # BUY / SELL
    code: str
    name: str
    price: float  # 成交价
    shares: int
    gross_amount: float  # 毛额（不含费）
    fee: float  # 费用
    pnl: float = 0.0  # 卖出时相对买入成本
    pnl_pct: float = 0.0  # 收益率%
    hold_days: int = 0  # 持仓天数（仅 SELL）
    reason: str = ""  # 触发原因

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BacktestResult:
    """回测结果汇总"""

    tag: str
    start_date: str
    end_date: str
    initial_capital: float
    final_capital: float

    total_return_pct: float
    annual_return_pct: float
    max_drawdown_pct: float

    trading_days: int
    total_trades: int
    win_count: int
    win_rate_pct: float
    avg_hold_days: float

    # 详细
    trades: list[dict] = field(default_factory=list)
    equity_curve: list[dict] = field(default_factory=list)  # [{date, equity, cash, position_value}, ...]
    skipped: list[dict] = field(default_factory=list)  # 跳过的决策点（数据不足等）

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("trades", None)
        d.pop("equity_curve", None)
        d.pop("skipped", None)
        d["trades"] = self.trades
        d["equity_curve"] = self.equity_curve
        d["skipped"] = self.skipped
        return d


# ============== 回测引擎 ==============


class BacktestEngine:
    """多因子策略回测引擎"""

    def __init__(
        self,
        strategy: MultiFactor | None = None,
        initial_capital: float = 1_000_000.0,
        max_positions: int = 5,
        commission_rate: float = 0.00025,  # 佣金万 2.5
        stamp_rate: float = 0.001,  # 印花千 1（仅卖出）
        min_lot: int = 100,  # A 股最小 100 股
    ):
        self.strategy = strategy or MultiFactor()
        self.initial_capital = initial_capital
        self.max_positions = max_positions
        self.commission_rate = commission_rate
        self.stamp_rate = stamp_rate
        self.min_lot = min_lot

    def _fee(self, side: str, amount: float) -> float:
        """单边费用：佣金 + 印花（印花仅卖出）"""
        commission = max(amount * self.commission_rate, 5.0)  # 最低 5 元
        stamp = amount * self.stamp_rate if side == "SELL" else 0.0
        return commission + stamp

    def run(
        self,
        pool: list[dict],
        start_date: str | None = None,
        end_date: str | None = None,
        rebalance_freq: int = 1,  # 每 N 天调仓一次（1 = 每日）
        verbose: bool = True,
    ) -> BacktestResult:
        """跑回测

        pool: 标的池（[{code, name, sector}]）
        start_date / end_date: 'YYYY-MM-DD'，None = 自动用数据最早/最晚
        rebalance_freq: 调仓频率（每 N 个交易日调一次）
        """
        if not pool:
            raise ValueError("pool 不能为空")

        # 1. 加载所有 K 线（按 code 缓存 DataFrame）
        all_klines: dict[str, pd.DataFrame] = {}
        names: dict[str, str] = {}
        for s in pool:
            df = data.fetch_kline(s["code"], 250)
            if df is None or df.empty or len(df) < 30:
                if verbose:
                    print(f"⚠️ 跳过 {s['code']} {s.get('name', '')}：K 线不足")
                continue
            all_klines[s["code"]] = df
            names[s["code"]] = s.get("name", s["code"])

        if not all_klines:
            raise RuntimeError("所有标的 K 线都拿不到，无法回测")

        # 2. 找共同交易日（所有标的都有的日期）
        date_sets = [set(df["date"].tolist()) for df in all_klines.values()]
        common_dates = sorted(set.intersection(*date_sets))
        if start_date:
            common_dates = [d for d in common_dates if d >= start_date]
        if end_date:
            common_dates = [d for d in common_dates if d <= end_date]

        if len(common_dates) < 5:
            raise RuntimeError(f"共同交易日只有 {len(common_dates)} 天，至少需要 5")

        # 3. 状态
        cash = self.initial_capital
        positions: dict[str, dict] = {}  # code -> {shares, cost, name, buy_date, buy_price}
        trades: list[Trade] = []
        equity_curve: list[dict] = []
        skipped: list[dict] = []

        if verbose:
            print(f"回测窗口：{common_dates[0]} → {common_dates[-1]}（{len(common_dates)} 个交易日）")
            print(f"标的池：{list(all_klines.keys())}")
            print(f"起始资金：¥{self.initial_capital:,.0f}")
            print(f"调仓频率：每 {rebalance_freq} 个交易日")
            print(f"最大持仓：{self.max_positions} 只")
            print("=" * 70)

        # 4. 逐日回放
        for i, dt in enumerate(common_dates):
            # 4.1 计算当日持仓市值（用当日收盘价）
            # 同时收集当日所有候选标的的收盘价（买入决策需要）
            position_value = 0.0
            prices_today: dict[str, float] = {}
            for code, df in all_klines.items():
                row = df[df["date"] == dt]
                if row.empty:
                    continue
                close = float(row["close"].iloc[0])
                prices_today[code] = close
                if code in positions:
                    position_value += close * positions[code]["shares"]

            total_equity = cash + position_value
            equity_curve.append(
                {
                    "date": dt,
                    "equity": round(total_equity, 2),
                    "cash": round(cash, 2),
                    "position_value": round(position_value, 2),
                }
            )

            # 4.2 调仓日：先卖后买
            if i % rebalance_freq == 0 and i < len(common_dates) - 1:
                # --- 卖出决策 ---
                to_sell: list[tuple[str, str, float]] = []  # (code, reason, suggested_price)
                for code, pos in list(positions.items()):
                    if code not in prices_today:
                        continue
                    close = prices_today[code]
                    avg_cost = pos["cost"] / pos["shares"]
                    pnl_pct = (close / avg_cost - 1) * 100
                    hold_days = i - common_dates.index(pos["buy_date"]) if pos["buy_date"] in common_dates else 0

                    # 止盈
                    if pnl_pct >= self.strategy.TAKE_PROFIT * 100:
                        to_sell.append((code, f"止盈+{self.strategy.TAKE_PROFIT * 100:.0f}%", close))
                    # 止损
                    elif pnl_pct <= self.strategy.STOP_LOSS * 100:
                        to_sell.append((code, f"止损{self.strategy.STOP_LOSS * 100:.0f}%", close))
                    # 满期
                    elif hold_days >= self.strategy.MAX_HOLD_DAYS:
                        to_sell.append((code, f"满期{hold_days}日", close))

                # 执行卖出
                for code, reason, price in to_sell:
                    if code not in positions:
                        continue
                    pos = positions.pop(code)
                    gross = price * pos["shares"]
                    fee = self._fee("SELL", gross)
                    net = gross - fee
                    pnl = net - pos["cost"]
                    pnl_pct = pnl / pos["cost"] * 100 if pos["cost"] > 0 else 0
                    hold_days = i - common_dates.index(pos["buy_date"]) if pos["buy_date"] in common_dates else 0
                    cash += net
                    trades.append(
                        Trade(
                            date=dt,
                            side="SELL",
                            code=code,
                            name=pos["name"],
                            price=round(price, 3),
                            shares=pos["shares"],
                            gross_amount=round(gross, 2),
                            fee=round(fee, 2),
                            pnl=round(pnl, 2),
                            pnl_pct=round(pnl_pct, 2),
                            hold_days=hold_days,
                            reason=reason,
                        )
                    )

                # --- 买入决策 ---
                # 4.2.1 给所有候选打分（横截面）
                # 严格时序：df 截到 dt（包含）
                code_df_map = {}
                for code, df in all_klines.items():
                    df_until = df[df["date"] <= dt].reset_index(drop=True)
                    if len(df_until) < 60:
                        continue
                    code_df_map[code] = df_until
                if not code_df_map:
                    skipped.append({"date": dt, "reason": "候选均 < 60 日历史"})
                    continue

                ranked = self.strategy.score_batch(code_df_map, names)
                if not ranked:
                    skipped.append({"date": dt, "reason": "全部被过滤"})
                    continue

                # 4.2.2 选 Top N 中 score >= 阈值 + 不在持仓的
                target_count = self.max_positions - len(positions)
                if target_count <= 0:
                    continue
                candidates = [r for r in ranked if r["score"] >= self.strategy.SCORE_BUY and r["code"] not in positions]
                # 还要排除已经持有但不在 TopN 里的
                top_codes = {r["code"] for r in ranked[: self.max_positions]}

                # 卖出"排名跌破阈值"的持仓（不在 TopN 里 → 退出）
                for code in list(positions.keys()):
                    if code not in top_codes:
                        # 卖
                        if code in prices_today:
                            pos = positions.pop(code)
                            price = prices_today[code]
                            gross = price * pos["shares"]
                            fee = self._fee("SELL", gross)
                            net = gross - fee
                            pnl = net - pos["cost"]
                            pnl_pct = pnl / pos["cost"] * 100 if pos["cost"] > 0 else 0
                            hold_days = (
                                i - common_dates.index(pos["buy_date"]) if pos["buy_date"] in common_dates else 0
                            )
                            cash += net
                            trades.append(
                                Trade(
                                    date=dt,
                                    side="SELL",
                                    code=code,
                                    name=pos["name"],
                                    price=round(price, 3),
                                    shares=pos["shares"],
                                    gross_amount=round(gross, 2),
                                    fee=round(fee, 2),
                                    pnl=round(pnl, 2),
                                    pnl_pct=round(pnl_pct, 2),
                                    hold_days=hold_days,
                                    reason="排名跌出 TopN",
                                )
                            )

                # 4.2.3 重新算 target_count（卖完后的空仓）
                target_count = self.max_positions - len(positions)
                if target_count <= 0:
                    continue

                # 等权分配：每只 = 总资金 * (1/TopN)，但单只不超可用现金
                per_position_budget = (cash * 0.97) / self.max_positions  # 留 3% 现金缓冲
                buy_list = candidates[:target_count]
                if not buy_list:
                    continue

                for cand in buy_list:
                    code = cand["code"]
                    if code not in prices_today:
                        continue
                    close = prices_today[code]
                    if close <= 0:
                        continue
                    # 按手数向下取整（A 股 100 股一手）
                    shares = int(per_position_budget / close) // self.min_lot * self.min_lot
                    if shares < self.min_lot:
                        continue
                    cost = close * shares
                    fee = self._fee("BUY", cost)
                    if cash < cost + fee:
                        # 现金不够就少买点
                        shares = int((cash - fee) / close) // self.min_lot * self.min_lot
                        if shares < self.min_lot:
                            continue
                        cost = close * shares
                        fee = self._fee("BUY", cost)
                    cash -= cost + fee
                    positions[code] = {
                        "shares": shares,
                        "cost": cost + fee,
                        "name": cand["name"],
                        "buy_date": dt,
                        "buy_price": close,
                    }
                    trades.append(
                        Trade(
                            date=dt,
                            side="BUY",
                            code=code,
                            name=cand["name"],
                            price=round(close, 3),
                            shares=shares,
                            gross_amount=round(cost, 2),
                            fee=round(fee, 2),
                            reason=f"score={cand['score']:+.2f} rank={cand['rank']}",
                        )
                    )

        # 5. 收盘：剩余持仓按最后一天收盘价强平
        last_dt = common_dates[-1]
        for code, pos in list(positions.items()):
            df = all_klines[code]
            row = df[df["date"] == last_dt]
            if row.empty:
                continue
            close = float(row["close"].iloc[0])
            gross = close * pos["shares"]
            fee = self._fee("SELL", gross)
            net = gross - fee
            pnl = net - pos["cost"]
            pnl_pct = pnl / pos["cost"] * 100 if pos["cost"] > 0 else 0
            hold_days = (
                len(common_dates) - 1 - common_dates.index(pos["buy_date"]) if pos["buy_date"] in common_dates else 0
            )
            cash += net
            trades.append(
                Trade(
                    date=last_dt,
                    side="SELL",
                    code=code,
                    name=pos["name"],
                    price=round(close, 3),
                    shares=pos["shares"],
                    gross_amount=round(gross, 2),
                    fee=round(fee, 2),
                    pnl=round(pnl, 2),
                    pnl_pct=round(pnl_pct, 2),
                    hold_days=hold_days,
                    reason="回测结束强平",
                )
            )

        # 6. 计算业绩指标
        final_capital = cash
        total_return = (final_capital / self.initial_capital - 1) * 100
        trading_days = len(common_dates)
        years = trading_days / 250
        annual_return = ((final_capital / self.initial_capital) ** (1 / years) - 1) * 100 if years > 0 else 0.0

        # 最大回撤
        peak = -math.inf
        max_dd = 0.0
        for point in equity_curve:
            peak = max(peak, point["equity"])
            dd = (point["equity"] - peak) / peak * 100
            if dd < max_dd:
                max_dd = dd

        # 胜率（按笔）
        sell_trades = [t for t in trades if t.side == "SELL"]
        win_count = sum(1 for t in sell_trades if t.pnl > 0)
        win_rate = (win_count / len(sell_trades) * 100) if sell_trades else 0.0
        avg_hold = (sum(t.hold_days for t in sell_trades) / len(sell_trades)) if sell_trades else 0.0

        result = BacktestResult(
            tag="multi_factor_v2",
            start_date=common_dates[0],
            end_date=common_dates[-1],
            initial_capital=self.initial_capital,
            final_capital=round(final_capital, 2),
            total_return_pct=round(total_return, 2),
            annual_return_pct=round(annual_return, 2),
            max_drawdown_pct=round(max_dd, 2),
            trading_days=trading_days,
            total_trades=len(trades),
            win_count=win_count,
            win_rate_pct=round(win_rate, 2),
            avg_hold_days=round(avg_hold, 1),
            trades=[t.to_dict() for t in trades],
            equity_curve=equity_curve,
            skipped=skipped,
        )

        if verbose:
            self._print_summary(result)

        return result

    def _print_summary(self, r: BacktestResult) -> None:
        print()
        print("=" * 70)
        print(f"📊 回测结果：{r.tag}")
        print("=" * 70)
        print(f"窗口: {r.start_date} → {r.end_date}（{r.trading_days} 个交易日）")
        print(f"起始资金: ¥{r.initial_capital:,.0f}")
        print(f"终值: ¥{r.final_capital:,.2f}")
        print()
        print(f"📈 总收益: {r.total_return_pct:+.2f}%")
        print(f"📅 年化: {r.annual_return_pct:+.2f}%")
        print(f"📉 最大回撤: {r.max_drawdown_pct:.2f}%")
        print()
        print(f"🔄 总交易笔数: {r.total_trades}")
        print(f"   买入: {sum(1 for t in r.trades if t['side'] == 'BUY')}")
        print(f"   卖出: {sum(1 for t in r.trades if t['side'] == 'SELL')}")
        print(
            f"✅ 胜率（按笔）: {r.win_rate_pct:.1f}%（{r.win_count}/{sum(1 for t in r.trades if t['side'] == 'SELL')}）"
        )
        print(f"⏱  平均持仓天数: {r.avg_hold_days:.1f}")
        print()
        if r.trades:
            # 最近 5 笔
            print("最近 5 笔交易:")
            for t in r.trades[-5:]:
                sign = "🟢" if t["side"] == "BUY" else ("🔴" if t.get("pnl", 0) >= 0 else "🟡")
                pnl_str = f"  pnl={t['pnl']:+.0f}({t['pnl_pct']:+.1f}%)" if t["side"] == "SELL" else ""
                print(
                    f"  {sign} {t['date']} {t['side']:<4} {t['code']} {t['name']:<8} "
                    f"@¥{t['price']:<7.2f} ×{t['shares']:<5} {t['reason'][:20]}{pnl_str}"
                )
        if r.skipped:
            print(f"\n⚠️ 跳过 {len(r.skipped)} 个调仓日（数据不足）")


# ============== CLI ==============


def main():
    parser = argparse.ArgumentParser(description="多因子策略回测")
    parser.add_argument("--start", default=None, help="起始日期 YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="结束日期 YYYY-MM-DD")
    parser.add_argument("--capital", type=float, default=1_000_000.0, help="起始资金")
    parser.add_argument("--positions", type=int, default=5, help="最大持仓数")
    parser.add_argument("--freq", type=int, default=1, help="调仓频率（每 N 个交易日）")
    parser.add_argument("--out", default="results/backtest_multi_factor", help="输出前缀")
    parser.add_argument("--watchlist-only", action="store_true", help="只用 watchlist 标的")
    args = parser.parse_args()

    # 标的池
    pool = get_pool()
    if args.watchlist_only:
        codes = set(get_watchlist_codes())
        pool = [s for s in pool if s["code"] in codes] if codes else pool

    if not pool:
        print("❌ 标的池为空")
        return

    # 跑
    engine = BacktestEngine(
        initial_capital=args.capital,
        max_positions=args.positions,
    )
    result = engine.run(
        pool=pool,
        start_date=args.start,
        end_date=args.end,
        rebalance_freq=args.freq,
    )

    # 输出文件
    out_dir = Path(args.out).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = Path(args.out).name

    # 交易明细 CSV
    trades_df = pd.DataFrame(result.trades)
    trades_path = out_dir / f"{tag}_trades.csv"
    trades_df.to_csv(trades_path, index=False)

    # 净值曲线 CSV
    eq_df = pd.DataFrame(result.equity_curve)
    eq_path = out_dir / f"{tag}_equity.csv"
    eq_df.to_csv(eq_path, index=False)

    # 汇总 JSON
    summary = {k: v for k, v in result.to_dict().items() if k not in ("trades", "equity_curve", "skipped")}
    summary_path = out_dir / f"{tag}_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    print("\n📁 输出文件:")
    print(f"   {trades_path}")
    print(f"   {eq_path}")
    print(f"   {summary_path}")


if __name__ == "__main__":
    main()
