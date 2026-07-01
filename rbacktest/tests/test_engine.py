"""
Tests for the shared backtest engine helpers and cross-strategy behaviour.
"""

from backend.backtest_engine import (
    list_available_stocks,
    list_available_strategies,
    run_backtest,
)


class TestListStocks:
    """list_available_stocks"""

    def test_returns_non_empty_list(self):
        stocks = list_available_stocks()
        assert isinstance(stocks, list)
        assert len(stocks) > 0

    def test_all_entries_are_strings(self):
        for sym in list_available_stocks():
            assert isinstance(sym, str)


class TestListStrategies:
    """list_available_strategies"""

    def test_returns_three_strategies(self):
        strategies = list_available_strategies()
        assert len(strategies) == 3

    def test_each_has_required_fields(self):
        for s in list_available_strategies():
            assert "name" in s
            assert "label" in s
            assert "description" in s
            assert "params" in s


class TestRunBacktest:
    """run_backtest — cross-strategy behaviour."""

    def test_task_id_is_unique(self, default_stocks, short_dates):
        r1 = run_backtest({
            "vt_symbols": default_stocks,
            **short_dates,
            "capital": 1_000_000,
            "strategies": ["equal_weight"],
            "strategy_params": {
                "equal_weight": {"top_k": 2, "lookback": 10, "price_add": 0.01},
            },
        })
        r2 = run_backtest({
            "vt_symbols": default_stocks,
            **short_dates,
            "capital": 1_000_000,
            "strategies": ["equal_weight"],
            "strategy_params": {
                "equal_weight": {"top_k": 1, "lookback": 10, "price_add": 0.01},
            },
        })
        assert r1["task_id"] != r2["task_id"]

    def test_all_strategies_same_dates(self, default_stocks, default_dates):
        """All strategies in one call must have identical daily count."""
        result = run_backtest({
            "vt_symbols": default_stocks,
            **default_dates,
            "capital": 1_000_000,
            "strategies": ["equal_weight", "grid_martingale", "vp_breakout"],
            "strategy_params": {
                "equal_weight": {"top_k": 3, "lookback": 20, "price_add": 0.01},
                "grid_martingale": {
                    "grid_n": 10, "top_k": 3,
                    "break_stop_pct": 0.05, "take_profit_ratio": 0.75,
                    "price_add": 0.02,
                },
                "vp_breakout": {
                    "high_n": 11, "vol_ratio_min": 1.5,
                    "close_to_high": 0.97, "ma_exit": 10,
                    "take_profit": 0.30, "stop_loss": -0.10,
                    "top_k": 3, "cash_ratio": 0.95, "price_add": 0.005,
                },
            },
        })
        days = [
            len(result["results"][s]["daily"])
            for s in ["equal_weight", "grid_martingale", "vp_breakout"]
        ]
        assert len(set(days)) == 1, f"Daily counts differ: {days}"

    def test_capital_consistent_across_strategies(self, default_stocks, default_dates):
        """All strategies in one call share the same capital."""
        result = run_backtest({
            "vt_symbols": default_stocks,
            **default_dates,
            "capital": 2_000_000,
            "strategies": ["equal_weight", "vp_breakout"],
            "strategy_params": {
                "equal_weight": {"top_k": 2, "lookback": 10, "price_add": 0.01},
                "vp_breakout": {
                    "high_n": 11, "vol_ratio_min": 1.5,
                    "close_to_high": 0.97, "ma_exit": 10,
                    "take_profit": 0.30, "stop_loss": -0.10,
                    "top_k": 2, "cash_ratio": 0.95, "price_add": 0.005,
                },
            },
        })
        for sn in result["results"]:
            assert result["results"][sn]["statistics"]["capital"] == 2_000_000
