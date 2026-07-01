"""
Backtest engine — wraps VNPY Alpha backtesting for the REST API.

Exposes:
    list_available_stocks()    — scan data/daily/ for parquet files
    list_available_strategies()— strategy metadata for the frontend
    run_backtest(params)       — execute one or more strategies, return JSON-safe results
"""

import uuid
from datetime import datetime, date
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from vnpy.alpha import AlphaLab, AlphaStrategy, BacktestingEngine
from vnpy.trader.constant import Direction, Interval
from vnpy.trader.object import BarData, TradeData

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def list_available_stocks() -> list[str]:
    """Return all stock symbols found in data/daily/*.parquet."""
    daily_dir = DATA_DIR / "daily"
    if not daily_dir.exists():
        return []

    stocks: list[str] = []
    for f in sorted(daily_dir.glob("*.parquet")):
        symbol = f.stem
        if symbol.endswith((".SSE", ".SZSE")):
            stocks.append(symbol)
    return stocks


def list_available_strategies() -> list[dict]:
    """Return strategy metadata consumed by the frontend param panel.

    Each entry describes the strategy name, display label, description,
    and the config schema for every tunable parameter.
    """
    return [
        {
            "name": "equal_weight",
            "label": "动量轮动",
            "description": "每月初按过去 lookback 日收益率排序，等权持有前 top_k 只",
            "params": {
                "top_k":    {"type": "int",   "default": 3,  "min": 1,   "max": 20,  "label": "持仓数量"},
                "lookback": {"type": "int",   "default": 20, "min": 5,   "max": 120, "label": "回顾天数"},
                "price_add":{"type": "float", "default": 0.01,"min": 0,   "max": 0.1, "step": 0.001, "label": "调仓滑点"},
            },
        },
        {
            "name": "grid_martingale",
            "label": "网格马丁格尔",
            "description": "每日计算网格位置，低位买入 / 高位卖出",
            "params": {
                "grid_n":           {"type": "int",   "default": 10,  "min": 5,   "max": 60,  "label": "网格K线数"},
                "top_k":            {"type": "int",   "default": 5,   "min": 1,   "max": 30,  "label": "持仓数量"},
                "break_stop_pct":   {"type": "float", "default": 0.05,"min": 0.01,"max": 0.3, "step": 0.01, "label": "破网止损比例"},
                "take_profit_ratio":{"type": "float", "default": 0.75,"min": 0.5, "max": 0.95,"step": 0.05, "label": "止盈位置比"},
                "price_add":        {"type": "float", "default": 0.02,"min": 0,   "max": 0.1, "step": 0.001,"label": "调仓滑点"},
            },
        },
        {
            "name": "vp_breakout",
            "label": "量价突破",
            "description": "突破前N日高点 + 量能放大 + 强势收盘时买入；止盈 / 止损 / 破均线卖出",
            "params": {
                "high_n":         {"type": "int",   "default": 11,   "min": 5,   "max": 60,  "label": "突破窗口"},
                "vol_ratio_min":  {"type": "float", "default": 1.5,  "min": 1.0, "max": 5.0, "step": 0.1,  "label": "量比最低阈值"},
                "close_to_high":  {"type": "float", "default": 0.97, "min": 0.9, "max": 1.0, "step": 0.01, "label": "强势收盘比"},
                "ma_exit":        {"type": "int",   "default": 10,   "min": 5,   "max": 60,  "label": "离场均线"},
                "take_profit":    {"type": "float", "default": 0.30, "min": 0.05,"max": 1.0, "step": 0.01, "label": "止盈线"},
                "stop_loss":      {"type": "float", "default":-0.10, "min":-0.5, "max":-0.01,"step": 0.01, "label": "止损线"},
                "top_k":          {"type": "int",   "default": 5,    "min": 1,   "max": 20,  "label": "持仓数量"},
                "cash_ratio":     {"type": "float", "default": 0.95, "min": 0.5, "max": 1.0, "step": 0.05, "label": "现金使用率"},
                "price_add":      {"type": "float", "default":0.005, "min": 0,   "max": 0.1, "step": 0.001,"label": "调仓滑点"},
            },
        },
    ]


# ---------------------------------------------------------------------------
# Helper: convert shares from a target dollar amount
# ---------------------------------------------------------------------------

def _calc_shares(target_value: float, price: float, contract_size: int, cash_available: float | None = None) -> float:
    """Calculate share count for *target_value* at *price*.

    VNPY internally treats volume as shares when contract size=1.
    Capped by available cash when provided.
    """
    if price <= 0:
        return 0.0
    shares: float = float(int(target_value / price))
    if cash_available is not None:
        max_shares: float = float(int(cash_available / price))
        shares = min(shares, max_shares)
    return max(shares, 0.0)


# ---------------------------------------------------------------------------
# Strategy classes
# ---------------------------------------------------------------------------

class EqualWeightStrategy(AlphaStrategy):
    """Momentum rotation: every month pick top_k stocks by past returns."""

    top_k: int = 3
    lookback: int = 20
    price_add: float = 0.01

    def on_init(self) -> None:
        """Initialise bar history cache."""
        self.bar_history: dict[str, list[BarData]] = {}
        self.write_log(f"动量轮动 | top_k={self.top_k} lookback={self.lookback}")

    def on_bars(self, bars: dict[str, BarData]) -> None:
        """Monthly rebalance: rank by lookback return, equal-weight top_k."""
        # Always accumulate bar history for every symbol
        for sym, bar in bars.items():
            if sym not in self.bar_history:
                self.bar_history[sym] = []
            self.bar_history[sym].append(bar)
            if len(self.bar_history[sym]) > self.lookback + 2:
                self.bar_history[sym] = self.bar_history[sym][-(self.lookback + 2):]

        dt = next(iter(bars.values())).datetime if bars else None
        if dt is None or dt.day > 5:
            return

        # Score every stock by past return
        scored: list[tuple[str, float]] = []
        for sym in self.vt_symbols:
            hist = self.bar_history.get(sym, [])
            if len(hist) < self.lookback + 1:
                continue
            past_close = hist[-(self.lookback + 1)].close_price
            if past_close <= 0:
                continue
            ret = hist[-1].close_price / past_close - 1
            scored.append((sym, ret))

        scored.sort(key=lambda x: x[1], reverse=True)
        selected = scored[: self.top_k]

        # Reset all targets
        for s in self.vt_symbols:
            self.target_data[s] = 0.0

        if not selected:
            return

        # Estimate current total equity (cash + position values)
        total_value: float = self.get_cash_available()
        for bar in bars.values():
            pos = self.pos_data.get(bar.vt_symbol, 0)
            if pos > 0:
                total_value += pos * bar.close_price

        per_stock = total_value / len(selected)

        for sym, _ in selected:
            bar = bars.get(sym)
            if bar is None or bar.close_price <= 0:
                continue
            size = self.strategy_engine.sizes.get(sym, 100)
            self.target_data[sym] = _calc_shares(per_stock, bar.close_price, size)

        self.execute_trading(bars, self.price_add)

    def on_trade(self, trade: TradeData) -> None:
        """No per-trade state to maintain."""


class GridMartingaleStrategy(AlphaStrategy):
    """Buy near rolling grid lows, sell on stop-loss / take-profit signals."""

    grid_n: int = 10
    top_k: int = 5
    break_stop_pct: float = 0.05
    take_profit_ratio: float = 0.75
    price_add: float = 0.02

    def on_init(self) -> None:
        """Initialise caches and entry-price tracking."""
        self.entry_price: dict[str, float] = {}
        self.bar_cache: dict[str, list[BarData]] = {}
        self.pending_sells: set[str] = set()
        self.write_log(f"网格马丁格尔 | top_k={self.top_k} grid_n={self.grid_n}")

    def on_bars(self, bars: dict[str, BarData]) -> None:
        """Scan for entry candidates, check exit conditions on held positions."""
        # ---- maintain bar cache ----
        for sym, bar in bars.items():
            if sym not in self.bar_cache:
                self.bar_cache[sym] = []
            self.bar_cache[sym].append(bar)
            if len(self.bar_cache[sym]) > self.grid_n + 1:
                self.bar_cache[sym] = self.bar_cache[sym][-(self.grid_n + 1):]

        # ---- find buy candidates ----
        candidates: list[tuple[str, float, float]] = []
        for sym in bars:
            hist = self.bar_cache.get(sym, [])
            if len(hist) < self.grid_n + 1:
                continue

            recent = hist[-(self.grid_n + 1):-1]
            grid_high = max(b.high_price for b in recent)
            grid_low = min(b.low_price for b in recent)
            close = hist[-1].close_price
            if grid_high <= grid_low:
                continue

            ratio = (close - grid_low) / (grid_high - grid_low)
            if not (0 <= ratio <= 0.45):
                continue

            confidence = max(40.0, 70.0 - ratio * 100.0)
            candidates.append((sym, ratio, confidence))

        # ---- exit held positions ----
        for sym in [s for s, p in self.pos_data.items() if p > 0]:
            if sym not in bars:
                continue
            hist = self.bar_cache.get(sym, [])
            if len(hist) < self.grid_n + 1:
                continue

            recent = hist[-(self.grid_n + 1):-1]
            grid_high = max(b.high_price for b in recent)
            grid_low = min(b.low_price for b in recent)
            close = hist[-1].close_price
            if grid_high <= grid_low:
                continue

            ratio = (close - grid_low) / (grid_high - grid_low)
            break_price = grid_low * (1.0 - self.break_stop_pct)

            should_sell = close <= break_price
            if not should_sell:
                entry_p = self.entry_price.get(sym)
                if ratio >= self.take_profit_ratio and entry_p and close > entry_p:
                    should_sell = True

            if should_sell and sym not in self.pending_sells:
                pos = self.pos_data.get(sym, 0)
                if pos > 0:
                    self.pending_sells.add(sym)
                    sell_price = bars[sym].close_price * (1 - self.price_add)
                    self.sell(sym, sell_price, pos)

        # ---- enter new positions ----
        candidates.sort(key=lambda x: x[2], reverse=True)
        selected = candidates[: self.top_k]

        if selected:
            cash = self.get_cash_available()
            per = cash / len(selected)
            for sym, _, _ in selected:
                bar = bars.get(sym)
                if bar is None or bar.close_price <= 0:
                    continue
                price = bar.close_price * (1 + self.price_add)
                size = self.strategy_engine.sizes.get(sym, 100)
                shares = _calc_shares(per, price, size)
                if shares > 0:
                    self.buy(sym, price, shares)

    def on_trade(self, trade: TradeData) -> None:
        """Update weighted-average entry price after each fill."""
        if trade.direction == Direction.LONG:
            cur = self.entry_price.get(trade.vt_symbol)
            pos = self.pos_data.get(trade.vt_symbol, 0)
            if cur is None or pos - trade.volume <= 0:
                self.entry_price[trade.vt_symbol] = trade.price
            else:
                old_size = max(0.0, pos - trade.volume)
                self.entry_price[trade.vt_symbol] = (
                    (old_size * cur + trade.volume * trade.price) / pos
                )
        else:
            self.pending_sells.discard(trade.vt_symbol)
            if self.pos_data.get(trade.vt_symbol, 0) <= 0:
                self.entry_price.pop(trade.vt_symbol, None)


class VpBreakoutStrategy(AlphaStrategy):
    """Buy on volume-price breakout, exit on take-profit / stop-loss / MA cross."""

    high_n: int = 11
    vol_ratio_min: float = 1.5
    close_to_high: float = 0.97
    ma_exit: int = 10
    take_profit: float = 0.30
    stop_loss: float = -0.10
    top_k: int = 5
    cash_ratio: float = 0.95
    price_add: float = 0.005

    def on_init(self) -> None:
        """Initialise caches and entry-price tracking."""
        self.entry_price: dict[str, float] = {}
        self.max_cache: int = max(self.high_n, self.ma_exit) + 2
        self.bar_history: dict[str, list[BarData]] = {}
        self.write_log(f"量价突破 | pool={len(self.vt_symbols)} top_k={self.top_k}")

    def on_bars(self, bars: dict[str, BarData]) -> None:
        """Scan breakouts, exit held positions, enter new ones."""
        # ---- maintain bar cache ----
        for sym, bar in bars.items():
            if sym not in self.bar_history:
                self.bar_history[sym] = []
            self.bar_history[sym].append(bar)
            if len(self.bar_history[sym]) > self.max_cache:
                self.bar_history[sym] = self.bar_history[sym][-self.max_cache:]

        # ---- find breakout candidates ----
        candidates: list[tuple[str, float]] = []
        for sym in bars:
            hist = self.bar_history.get(sym, [])
            if len(hist) < self.high_n + 1:
                continue

            window = hist[-(self.high_n + 1):]
            close = window[-1].close_price
            high_today = window[-1].high_price
            vol_today = window[-1].volume

            if self.pos_data.get(sym, 0) > 0:
                continue

            prev_high = max(b.high_price for b in window[:-1])
            if close <= prev_high:
                continue

            avg_vol = np.mean([b.volume for b in hist[-6:-1]])
            if avg_vol <= 0 or vol_today < self.vol_ratio_min * avg_vol:
                continue

            if high_today <= 0 or (close / high_today) < self.close_to_high:
                continue

            vol_ratio = vol_today / avg_vol
            confidence = max(60.0, min(90.0, 60.0 + (vol_ratio - self.vol_ratio_min) * 15.0))
            candidates.append((sym, confidence))

        # ---- exit held positions ----
        for sym in list(self.pos_data.keys()):
            if self.pos_data[sym] <= 0 or sym not in bars:
                continue

            entry_p = self.entry_price.get(sym)
            hist = self.bar_history.get(sym, [])
            if len(hist) < self.ma_exit + 1 or entry_p is None:
                self.target_data[sym] = self.pos_data[sym]
                continue

            close = hist[-1].close_price
            pnl_pct = close / entry_p - 1

            if pnl_pct >= self.take_profit or pnl_pct <= self.stop_loss:
                self.target_data[sym] = 0.0
                continue

            ma_val = np.mean([b.close_price for b in hist[-self.ma_exit:]])
            if close < ma_val * 0.97:
                self.target_data[sym] = 0.0
                continue

            self.target_data[sym] = self.pos_data[sym]

        self.execute_trading(bars, self.price_add)

        # ---- enter new positions ----
        candidates.sort(key=lambda x: x[1], reverse=True)
        selected = candidates[: self.top_k]

        if selected:
            cash = self.get_cash_available() * self.cash_ratio
            per = cash / len(selected)
            for sym, _ in selected:
                if sym not in bars:
                    continue
                price = bars[sym].close_price * (1 + self.price_add)
                size = self.strategy_engine.sizes.get(sym, 100)
                volume = _calc_shares(per, price, size)
                if volume >= size:
                    self.buy(sym, price, volume)

    def on_trade(self, trade: TradeData) -> None:
        """Update weighted-average entry price after each fill."""
        sym = trade.vt_symbol
        if trade.direction == Direction.LONG:
            new_pos = self.pos_data.get(sym, 0)
            old_pos = new_pos - trade.volume
            old_entry = self.entry_price.get(sym, trade.price)
            self.entry_price[sym] = (
                (old_pos * old_entry + trade.volume * trade.price) / new_pos
                if new_pos > 0
                else trade.price
            )
        else:
            if self.pos_data.get(sym, 0) <= 0:
                self.entry_price.pop(sym, None)


STRATEGY_REGISTRY: dict[str, type[AlphaStrategy]] = {
    "equal_weight": EqualWeightStrategy,
    "grid_martingale": GridMartingaleStrategy,
    "vp_breakout": VpBreakoutStrategy,
}


# ---------------------------------------------------------------------------
# JSON serialisation helpers
# ---------------------------------------------------------------------------

def _serialize(obj: Any) -> Any:
    """Recursively convert NumPy / datetime types to JSON-safe Python types."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


def _empty_statistics(capital: int) -> dict:
    """Return a zeroed-out statistics dict for a strategy with no trades."""
    return {
        "start_date": "", "end_date": "", "total_days": 0,
        "profit_days": 0, "loss_days": 0, "capital": capital,
        "end_balance": capital, "max_drawdown": 0, "max_ddpercent": 0,
        "max_drawdown_duration": 0, "total_net_pnl": 0, "daily_net_pnl": 0,
        "total_commission": 0, "daily_commission": 0,
        "total_turnover": 0, "daily_turnover": 0,
        "total_trade_count": 0, "daily_trade_count": 0,
        "total_return": 0, "annual_return": 0, "daily_return": 0,
        "return_std": 0, "sharpe_ratio": 0, "return_drawdown_ratio": 0,
    }


def _empty_daily(dates: list, capital: int) -> list[dict]:
    """Return zeroed daily records for every date in *dates*."""
    return [
        {
            "date": d.isoformat() if hasattr(d, "isoformat") else str(d),
            "trade_count": 0, "turnover": 0, "commission": 0,
            "trading_pnl": 0, "holding_pnl": 0, "total_pnl": 0,
            "net_pnl": 0, "balance": capital, "return": 0,
            "highlevel": capital, "drawdown": 0, "ddpercent": 0,
        }
        for d in dates
    ]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_backtest(params: dict) -> dict:
    """Run one or more strategy backtests with the same universe and date range.

    Parameters
    ----------
    params : dict
        Required keys: vt_symbols, start, end.
        Optional keys: capital (default 1_000_000), strategies (default ["equal_weight"]).
        Any other keys are filtered per strategy via __annotations__.

    Returns
    -------
    dict
        {"task_id": str, "results": {strategy_name: {"statistics": ..., "daily": [...]}}}
    """
    vt_symbols: list[str] = params["vt_symbols"]
    start = datetime.strptime(params["start"], "%Y-%m-%d")
    end = datetime.strptime(params["end"], "%Y-%m-%d")
    capital = int(params.get("capital", 1_000_000))
    strategy_names: list[str] = params.get("strategies", ["equal_weight"])

    all_results: dict[str, dict] = {}

    for strategy_name in strategy_names:
        strategy_cls = STRATEGY_REGISTRY[strategy_name]
        known_attrs = set(getattr(strategy_cls, "__annotations__", {}).keys())

        # Per-strategy params override flat params for the same key
        flat_params = {k: v for k, v in params.items() if k in known_attrs}
        per_strat = params.get("strategy_params", {}).get(strategy_name, {})
        strategy_params = {**flat_params, **per_strat}

        lab = AlphaLab(str(DATA_DIR))
        engine = BacktestingEngine(lab)
        engine.set_parameters(
            vt_symbols=vt_symbols,
            interval=Interval.DAILY,
            start=start,
            end=end,
            capital=capital,
        )
        engine.add_strategy(
            strategy_cls,
            strategy_params,
            signal_df=pl.DataFrame({"datetime": [], "vt_symbol": [], "signal": []}),
        )
        engine.load_data()
        engine.run_backtesting()
        result_df = engine.calculate_result()

        if result_df is not None and not result_df.is_empty():
            stats_raw = engine.calculate_statistics()
            daily_df = engine.daily_df
            daily_records = [
                {k: _serialize(v) for k, v in row.items()}
                for row in daily_df.iter_rows(named=True)
            ] if daily_df is not None else []
            stats = {k: _serialize(v) for k, v in stats_raw.items()}
        else:
            all_dates = sorted(engine.daily_results.keys())
            daily_records = _empty_daily(all_dates, capital)
            stats = _empty_statistics(capital)
            if all_dates:
                stats["start_date"] = str(all_dates[0])
                stats["end_date"] = str(all_dates[-1])
                stats["total_days"] = len(all_dates)

        all_results[strategy_name] = {
            "statistics": stats,
            "daily": daily_records,
        }

    return {"task_id": str(uuid.uuid4()), "results": all_results}
