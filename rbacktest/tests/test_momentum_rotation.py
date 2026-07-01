"""
Tests for the momentum rotation (equal_weight) strategy.
"""

from backend.backtest_engine import run_backtest


class TestMomentumRotation:
    """Momentum rotation strategy: monthly rebalance by past returns."""

    def test_smoke_run(self, default_stocks, short_dates):
        """Strategy should complete without error and return expected keys."""
        result = run_backtest({
            "vt_symbols": default_stocks,
            **short_dates,
            "capital": 1_000_000,
            "strategies": ["equal_weight"],
            "strategy_params": {
                "equal_weight": {"top_k": 2, "lookback": 10, "price_add": 0.01},
            },
        })

        assert "task_id" in result
        assert "results" in result
        assert "equal_weight" in result["results"]

        stats = result["results"]["equal_weight"]["statistics"]
        daily = result["results"]["equal_weight"]["daily"]

        # Structural assertions
        assert isinstance(stats["total_trade_count"], (int, float))
        assert stats["total_trade_count"] >= 0
        assert "total_return" in stats
        assert stats["capital"] == 1_000_000
        assert len(daily) == stats["total_days"]
        assert len(daily) > 0

    def test_monthly_rebalance_has_trades(self, default_stocks, default_dates):
        """Over a 7-month period the strategy must produce at least one trade."""
        result = run_backtest({
            "vt_symbols": default_stocks,
            **default_dates,
            "capital": 1_000_000,
            "strategies": ["equal_weight"],
            "strategy_params": {
                "equal_weight": {"top_k": 3, "lookback": 20, "price_add": 0.01},
            },
        })
        stats = result["results"]["equal_weight"]["statistics"]
        assert stats["total_trade_count"] > 0, "Expected at least one trade over 7 months"

    def test_top_k_limits_positions(self, default_stocks, default_dates):
        """With top_k=1, turnover should be lower than with top_k=3."""
        def run_with(k):
            return run_backtest({
                "vt_symbols": default_stocks,
                **default_dates,
                "capital": 1_000_000,
                "strategies": ["equal_weight"],
                "strategy_params": {
                    "equal_weight": {"top_k": k, "lookback": 20, "price_add": 0.01},
                },
            })

        r1 = run_with(1)
        r3 = run_with(3)

        t1 = r1["results"]["equal_weight"]["statistics"]["total_turnover"]
        t3 = r3["results"]["equal_weight"]["statistics"]["total_turnover"]
        assert t3 >= t1, "Top_k=3 should have >= turnover than top_k=1"

    def test_daily_records_are_monotonic_dates(self, default_stocks, default_dates):
        """Daily records must have strictly increasing dates."""
        result = run_backtest({
            "vt_symbols": default_stocks,
            **default_dates,
            "capital": 1_000_000,
            "strategies": ["equal_weight"],
            "strategy_params": {
                "equal_weight": {"top_k": 2, "lookback": 10, "price_add": 0.01},
            },
        })
        daily = result["results"]["equal_weight"]["daily"]
        dates = [d["date"] for d in daily]
        assert dates == sorted(dates), "Dates must be sorted"

    def test_balance_never_negative(self, default_stocks, default_dates):
        """Strategy equity balance must never go negative."""
        result = run_backtest({
            "vt_symbols": default_stocks,
            **default_dates,
            "capital": 1_000_000,
            "strategies": ["equal_weight"],
            "strategy_params": {
                "equal_weight": {"top_k": 3, "lookback": 20, "price_add": 0.01},
            },
        })
        daily = result["results"]["equal_weight"]["daily"]
        for d in daily:
            assert d["balance"] >= 0, f"Balance went negative on {d['date']}"

    def test_omitted_param_uses_class_default(self, default_stocks, short_dates):
        """Omitting lookback from strategy_params should not crash."""
        result = run_backtest({
            "vt_symbols": default_stocks,
            **short_dates,
            "capital": 1_000_000,
            "strategies": ["equal_weight"],
            "strategy_params": {
                "equal_weight": {"top_k": 2, "price_add": 0.01},
            },
        })
        assert result["results"]["equal_weight"]["daily"]


class TestMomentumRotationEdgeCases:
    """Edge case handling."""

    def test_single_stock_pool(self, short_dates):
        """Should not crash with only one stock."""
        result = run_backtest({
            "vt_symbols": ["600519.SSE"],
            **short_dates,
            "capital": 1_000_000,
            "strategies": ["equal_weight"],
            "strategy_params": {
                "equal_weight": {"top_k": 1, "lookback": 10, "price_add": 0.01},
            },
        })
        assert result["results"]["equal_weight"]["daily"]

    def test_lookback_below_min_is_accepted(self, default_stocks, short_dates):
        """Passing lookback below config min should still work (class default 20 is used
        since the strategy annotates its own default)."""
        result = run_backtest({
            "vt_symbols": default_stocks,
            **short_dates,
            "capital": 1_000_000,
            "strategies": ["equal_weight"],
            "strategy_params": {
                "equal_weight": {"top_k": 2, "lookback": 1, "price_add": 0.01},
            },
        })
        assert result["results"]["equal_weight"]["daily"]
