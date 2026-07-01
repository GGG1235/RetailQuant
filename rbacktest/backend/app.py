"""
Flask REST API for backtesting.

Endpoints:
    POST /api/backtest   Run backtest(s) for one or more strategies.
    GET  /api/stocks     List available stock symbols.
    GET  /api/strategies List available strategies and their parameters.
"""

import sys
import traceback
from pathlib import Path

from flask import Flask, request, jsonify
from flask_cors import CORS

from backtest_engine import (
    list_available_stocks,
    list_available_strategies,
    run_backtest,
)

app = Flask(__name__)
CORS(app)


def _check_data_dir() -> None:
    """Verify data/ directory exists and contains required files.

    Prints warnings if data is missing but does not abort startup —
    the API will return empty stock lists when no data is present.
    """
    data_dir = Path(__file__).resolve().parent.parent / "data"
    daily_dir = data_dir / "daily"
    contract_file = data_dir / "contract.json"

    if not data_dir.exists():
        print(f"[WARNING] Data directory not found: {data_dir}")
        print(f"          Please create it and copy daily/*.parquet + contract.json")
        return

    if not daily_dir.exists() or not any(daily_dir.glob("*.parquet")):
        parquet_count = len(list(daily_dir.glob("*.parquet"))) if daily_dir.exists() else 0
        print(f"[WARNING] No daily parquet files found in {daily_dir} ({parquet_count} found)")
        print(f"          The data/ directory has these subdirectories:")
        for d in sorted(data_dir.iterdir()):
            if d.is_dir():
                count = len(list(d.iterdir()))
                print(f"            {d.name}/  ({count} files)")
        return

    if not contract_file.exists():
        print(f"[WARNING] contract.json not found: {contract_file}")
        print(f"          VNPY AlphaLab will use default contract settings.")

    stocks = list_available_stocks()
    print(f"[OK] Data directory ready: {len(stocks)} stocks, contract.json {'found' if contract_file.exists() else 'missing'}")


_check_data_dir()


@app.route("/api/stocks", methods=["GET"])
def get_stocks():
    """Return all available stock symbols as JSON."""
    return jsonify({"stocks": list_available_stocks()})


@app.route("/api/strategies", methods=["GET"])
def get_strategies():
    """Return all available strategy definitions as JSON."""
    return jsonify({"strategies": list_available_strategies()})


@app.route("/api/backtest", methods=["POST"])
def run_backtest_api():
    """Accept backtest parameters, run the backtest, return results.

    Request body: JSON with vt_symbols, start, end, capital, strategies,
                  and strategy-specific parameters.

    Returns: JSON with task_id and per-strategy results (statistics + daily records).
    """
    try:
        params = request.get_json(force=True)
        result = run_backtest(params)
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
