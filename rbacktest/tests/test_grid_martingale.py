"""
Tests for the grid martingale strategy.
"""

from backend.backtest_engine import run_backtest


class TestGridMartingale:
    """Grid martingale: buy near rolling grid lows, sell on exit signals."""

    def test_smoke_run(self, default_stocks, short_dates):
        """Strategy completes without error and returns valid structure."""
        result = run_backtest({
            "vt_symbols": default_stocks,
            **short_dates,
            "capital": 1_000_000,
            "strategies": ["grid_martingale"],
            "strategy_params": {
                "grid_martingale": {
                    "grid_n": 10, "top_k": 2,
                    "break_stop_pct": 0.05, "take_profit_ratio": 0.75,
                    "price_add": 0.02,
                },
            },
        })

        stats = result["results"]["grid_martingale"]["statistics"]
        daily = result["results"]["grid_martingale"]["daily"]
        assert stats["total_days"] > 0
        assert len(daily) == stats["total_days"]
        assert stats["capital"] == 1_000_000

    def test_produces_trades_over_long_period(self, large_stocks, default_dates):
        """With enough stocks and time, grid should execute trades."""
        result = run_backtest({
            "vt_symbols": large_stocks,
            **default_dates,
            "capital": 1_000_000,
            "strategies": ["grid_martingale"],
            "strategy_params": {
                "grid_martingale": {
                    "grid_n": 10, "top_k": 4,
                    "break_stop_pct": 0.05, "take_profit_ratio": 0.75,
                    "price_add": 0.02,
                },
            },
        })
        stats = result["results"]["grid_martingale"]["statistics"]
        assert stats["total_trade_count"] > 0, (
            "Grid martingale should generate trades with sufficient pool"
        )

    def test_turnover_positive_when_trading(self, large_stocks, default_dates):
        """If trades were executed, turnover must be positive."""
        result = run_backtest({
            "vt_symbols": large_stocks,
            **default_dates,
            "capital": 1_000_000,
            "strategies": ["grid_martingale"],
            "strategy_params": {
                "grid_martingale": {
                    "grid_n": 10, "top_k": 4,
                    "break_stop_pct": 0.05, "take_profit_ratio": 0.75,
                    "price_add": 0.02,
                },
            },
        })
        stats = result["results"]["grid_martingale"]["statistics"]
        if stats["total_trade_count"] > 0:
            assert stats["total_turnover"] > 0, (
                f"{stats['total_trade_count']} trades but turnover is 0"
            )

    def test_daily_records_consistent(self, large_stocks, default_dates):
        """Each daily record must have expected keys with sensible values."""
        result = run_backtest({
            "vt_symbols": large_stocks,
            **default_dates,
            "capital": 1_000_000,
            "strategies": ["grid_martingale"],
            "strategy_params": {
                "grid_martingale": {
                    "grid_n": 10, "top_k": 4,
                    "break_stop_pct": 0.05, "take_profit_ratio": 0.75,
                    "price_add": 0.02,
                },
            },
        })
        daily = result["results"]["grid_martingale"]["daily"]
        required_keys = {"date", "balance", "net_pnl", "ddpercent", "trade_count"}
        for d in daily:
            assert required_keys.issubset(d.keys()), f"Missing keys in {d['date']}"
            assert d["balance"] >= 0

    def test_sharpe_is_finite(self, large_stocks, default_dates):
        """Sharpe ratio must be a finite number."""
        result = run_backtest({
            "vt_symbols": large_stocks,
            **default_dates,
            "capital": 1_000_000,
            "strategies": ["grid_martingale"],
            "strategy_params": {
                "grid_martingale": {
                    "grid_n": 10, "top_k": 4,
                    "break_stop_pct": 0.05, "take_profit_ratio": 0.75,
                    "price_add": 0.02,
                },
            },
        })
        from math import isfinite
        sharpe = result["results"]["grid_martingale"]["statistics"]["sharpe_ratio"]
        assert isfinite(sharpe), f"Sharpe ratio is not finite: {sharpe}"


class TestGridMartingaleEdgeCases:

    def test_insufficient_bars_no_crash(self, default_stocks, short_dates):
        """With grid_n > available bars, strategy should not crash."""
        result = run_backtest({
            "vt_symbols": default_stocks,
            **short_dates,
            "capital": 1_000_000,
            "strategies": ["grid_martingale"],
            "strategy_params": {
                "grid_martingale": {
                    "grid_n": 60, "top_k": 2,
                    "break_stop_pct": 0.05, "take_profit_ratio": 0.75,
                    "price_add": 0.02,
                },
            },
        })
        assert result["results"]["grid_martingale"]["daily"]

    def test_zero_top_k_is_handled(self, default_stocks, short_dates):
        """top_k=0 should not crash (though config min is 1)."""
        result = run_backtest({
            "vt_symbols": default_stocks,
            **short_dates,
            "capital": 1_000_000,
            "strategies": ["grid_martingale"],
            "strategy_params": {
                "grid_martingale": {
                    "grid_n": 10, "top_k": 0,
                    "break_stop_pct": 0.05, "take_profit_ratio": 0.75,
                    "price_add": 0.02,
                },
            },
        })
        stats = result["results"]["grid_martingale"]["statistics"]
        assert stats["total_trade_count"] == 0
