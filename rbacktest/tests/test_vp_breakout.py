"""
Tests for the volume-price breakout strategy.
"""

from backend.backtest_engine import run_backtest


class TestVpBreakout:
    """VP Breakout: buy on breakout + volume + strength, exit on rules."""

    def test_smoke_run(self, default_stocks, short_dates):
        """Strategy completes with valid output structure."""
        result = run_backtest({
            "vt_symbols": default_stocks,
            **short_dates,
            "capital": 1_000_000,
            "strategies": ["vp_breakout"],
            "strategy_params": {
                "vp_breakout": {
                    "high_n": 11, "vol_ratio_min": 1.5,
                    "close_to_high": 0.97, "ma_exit": 10,
                    "take_profit": 0.30, "stop_loss": -0.10,
                    "top_k": 3, "cash_ratio": 0.95, "price_add": 0.005,
                },
            },
        })

        stats = result["results"]["vp_breakout"]["statistics"]
        daily = result["results"]["vp_breakout"]["daily"]
        assert stats["capital"] == 1_000_000
        assert stats["total_days"] > 0
        assert len(daily) == stats["total_days"]

    def test_produces_trades_on_volatile_period(self, large_stocks, default_dates):
        """With enough stocks, breakout strategy should find entries."""
        result = run_backtest({
            "vt_symbols": large_stocks,
            **default_dates,
            "capital": 1_000_000,
            "strategies": ["vp_breakout"],
            "strategy_params": {
                "vp_breakout": {
                    "high_n": 11, "vol_ratio_min": 1.2,
                    "close_to_high": 0.95, "ma_exit": 10,
                    "take_profit": 0.30, "stop_loss": -0.15,
                    "top_k": 5, "cash_ratio": 0.95, "price_add": 0.005,
                },
            },
        })
        stats = result["results"]["vp_breakout"]["statistics"]
        assert stats["total_trade_count"] > 0, (
            "VP Breakout should find trades with sufficient pool and loose filters"
        )

    def test_max_drawdown_within_range(self, large_stocks, default_dates):
        """Max drawdown percentage must be between -100% and 0%."""
        result = run_backtest({
            "vt_symbols": large_stocks,
            **default_dates,
            "capital": 1_000_000,
            "strategies": ["vp_breakout"],
            "strategy_params": {
                "vp_breakout": {
                    "high_n": 11, "vol_ratio_min": 1.5,
                    "close_to_high": 0.97, "ma_exit": 10,
                    "take_profit": 0.30, "stop_loss": -0.10,
                    "top_k": 5, "cash_ratio": 0.95, "price_add": 0.005,
                },
            },
        })
        dd = result["results"]["vp_breakout"]["statistics"]["max_ddpercent"]
        assert -100 <= dd <= 0, f"Drawdown out of range: {dd}%"

    def test_end_balance_consistent_with_return(self, large_stocks, default_dates):
        """End balance must match total_return formula."""
        result = run_backtest({
            "vt_symbols": large_stocks,
            **default_dates,
            "capital": 1_000_000,
            "strategies": ["vp_breakout"],
            "strategy_params": {
                "vp_breakout": {
                    "high_n": 11, "vol_ratio_min": 1.5,
                    "close_to_high": 0.97, "ma_exit": 10,
                    "take_profit": 0.30, "stop_loss": -0.10,
                    "top_k": 5, "cash_ratio": 0.95, "price_add": 0.005,
                },
            },
        })
        stats = result["results"]["vp_breakout"]["statistics"]
        expected_balance = stats["capital"] * (1 + stats["total_return"] / 100)
        assert abs(stats["end_balance"] - expected_balance) < 1.0, (
            f"end_balance={stats['end_balance']} vs expected={expected_balance}"
        )

    def test_profit_loss_days_sum_to_total(self, large_stocks, default_dates):
        """profit_days + loss_days must not exceed total_days."""
        result = run_backtest({
            "vt_symbols": large_stocks,
            **default_dates,
            "capital": 1_000_000,
            "strategies": ["vp_breakout"],
            "strategy_params": {
                "vp_breakout": {
                    "high_n": 11, "vol_ratio_min": 1.5,
                    "close_to_high": 0.97, "ma_exit": 10,
                    "take_profit": 0.30, "stop_loss": -0.10,
                    "top_k": 5, "cash_ratio": 0.95, "price_add": 0.005,
                },
            },
        })
        stats = result["results"]["vp_breakout"]["statistics"]
        assert stats["profit_days"] + stats["loss_days"] <= stats["total_days"]


class TestVpBreakoutEdgeCases:

    def test_tight_filters_produce_fewer_trades(self, large_stocks, default_dates):
        """Stricter breakout filters should reduce trade count."""
        def run(filters):
            return run_backtest({
                "vt_symbols": large_stocks,
                **default_dates,
                "capital": 1_000_000,
                "strategies": ["vp_breakout"],
                "strategy_params": {"vp_breakout": filters},
            })

        loose = run({
            "high_n": 5, "vol_ratio_min": 1.0, "close_to_high": 0.90,
            "ma_exit": 10, "take_profit": 0.50, "stop_loss": -0.50,
            "top_k": 5, "cash_ratio": 0.95, "price_add": 0.005,
        })
        tight = run({
            "high_n": 20, "vol_ratio_min": 3.0, "close_to_high": 0.99,
            "ma_exit": 5, "take_profit": 0.05, "stop_loss": -0.01,
            "top_k": 1, "cash_ratio": 0.95, "price_add": 0.005,
        })

        loose_trades = loose["results"]["vp_breakout"]["statistics"]["total_trade_count"]
        tight_trades = tight["results"]["vp_breakout"]["statistics"]["total_trade_count"]
        assert tight_trades <= loose_trades, (
            f"Tighter filters ({tight_trades} trades) should not exceed "
            f"looser filters ({loose_trades} trades)"
        )

    def test_no_stocks_no_crash(self, short_dates):
        """Empty stock list should return empty results gracefully."""
        result = run_backtest({
            "vt_symbols": [],
            **short_dates,
            "capital": 1_000_000,
            "strategies": ["vp_breakout"],
            "strategy_params": {
                "vp_breakout": {
                    "high_n": 11, "vol_ratio_min": 1.5,
                    "close_to_high": 0.97, "ma_exit": 10,
                    "take_profit": 0.30, "stop_loss": -0.10,
                    "top_k": 3, "cash_ratio": 0.95, "price_add": 0.005,
                },
            },
        })
        stats = result["results"]["vp_breakout"]["statistics"]
        assert stats["total_trade_count"] == 0
