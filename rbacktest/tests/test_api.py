"""
Integration tests for the backtest REST API.
"""

import json

import pytest

from backend.app import app


@pytest.fixture
def client():
    """Flask test client."""
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestAPIStocks:
    """GET /api/stocks"""

    def test_returns_list(self, client):
        resp = client.get("/api/stocks")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "stocks" in data
        assert isinstance(data["stocks"], list)
        assert len(data["stocks"]) > 0

    def test_contains_known_symbol(self, client):
        resp = client.get("/api/stocks")
        data = json.loads(resp.data)
        assert "600519.SSE" in data["stocks"]

    def test_all_symbols_have_exchange_suffix(self, client):
        resp = client.get("/api/stocks")
        data = json.loads(resp.data)
        for sym in data["stocks"]:
            assert sym.endswith((".SSE", ".SZSE")), f"Bad suffix: {sym}"


class TestAPIStrategies:
    """GET /api/strategies"""

    def test_returns_three_strategies(self, client):
        resp = client.get("/api/strategies")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "strategies" in data
        names = {s["name"] for s in data["strategies"]}
        assert names == {"equal_weight", "grid_martingale", "vp_breakout"}

    def test_each_strategy_has_params(self, client):
        resp = client.get("/api/strategies")
        data = json.loads(resp.data)
        for s in data["strategies"]:
            assert "params" in s
            assert isinstance(s["params"], dict)
            for key, cfg in s["params"].items():
                assert "type" in cfg, f"Missing type in {s['name']}.{key}"
                assert "default" in cfg
                assert "label" in cfg


class TestAPIBacktest:
    """POST /api/backtest"""

    def test_single_strategy_returns_results(self, client):
        resp = client.post(
            "/api/backtest",
            json={
                "vt_symbols": ["600519.SSE", "000858.SZSE"],
                "start": "2024-08-01",
                "end": "2024-10-01",
                "capital": 1_000_000,
                "strategies": ["equal_weight"],
                "strategy_params": {
                    "equal_weight": {"top_k": 1, "lookback": 10, "price_add": 0.01},
                },
            },
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "task_id" in data
        assert "equal_weight" in data["results"]
        assert "statistics" in data["results"]["equal_weight"]
        assert "daily" in data["results"]["equal_weight"]

    def test_multi_strategy_returns_all(self, client):
        resp = client.post(
            "/api/backtest",
            json={
                "vt_symbols": ["600519.SSE", "000858.SZSE"],
                "start": "2024-09-01",
                "end": "2024-11-01",
                "capital": 1_000_000,
                "strategies": ["equal_weight", "vp_breakout"],
                "strategy_params": {
                    "equal_weight": {"top_k": 1, "lookback": 10, "price_add": 0.01},
                    "vp_breakout": {
                        "high_n": 11, "vol_ratio_min": 1.5,
                        "close_to_high": 0.97, "ma_exit": 10,
                        "take_profit": 0.30, "stop_loss": -0.10,
                        "top_k": 2, "cash_ratio": 0.95, "price_add": 0.005,
                    },
                },
            },
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert set(data["results"].keys()) == {"equal_weight", "vp_breakout"}

    def test_missing_symbols_returns_500(self, client):
        """Missing vt_symbols should return 500 with an error message."""
        resp = client.post(
            "/api/backtest",
            json={
                "start": "2024-01-01",
                "end": "2024-06-01",
                "capital": 1_000_000,
                "strategies": ["equal_weight"],
            },
        )
        assert resp.status_code == 500

    def test_empty_stock_list_does_not_crash(self, client):
        resp = client.post(
            "/api/backtest",
            json={
                "vt_symbols": [],
                "start": "2024-08-01",
                "end": "2024-10-01",
                "capital": 1_000_000,
                "strategies": ["equal_weight"],
                "strategy_params": {
                    "equal_weight": {"top_k": 1, "lookback": 10, "price_add": 0.01},
                },
            },
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["results"]["equal_weight"]["statistics"]["total_trade_count"] == 0

    def test_flat_params_still_accepted(self, client):
        """Backward compat: flat params dict should still work."""
        resp = client.post(
            "/api/backtest",
            json={
                "vt_symbols": ["600519.SSE"],
                "start": "2024-09-01",
                "end": "2024-10-01",
                "capital": 1_000_000,
                "strategies": ["equal_weight"],
                "top_k": 1,
                "lookback": 10,
                "price_add": 0.01,
            },
        )
        assert resp.status_code == 200
