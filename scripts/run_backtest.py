"""
scripts/run_backtest.py — 多因子选股回测入口

用法:
    uv run python scripts/run_backtest.py

流程:
    1) 下载东财财务快照（若本地缓存缺失）
    2) 执行回测
    3) 结果写入 data/backtest_result.json
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from rquant.data_source.eastmoney import download_snapshot, last_snapshot_date
from rquant.strategy.factor.backtest_engine import run_backtest


def main():
    # ----- 配置 -----
    ROOT = Path(__file__).resolve().parent.parent
    SNAP_DATE = "2025-12-31"  # 财务快照日期
    START_DATE = "2026-01-01"  # 回测起始
    END_DATE = "2026-06-17"  # 回测结束
    INITIAL_CAPITAL = 1_000_000  # 初始资金
    TOP_N = 30  # 每期持仓数

    # ----- 1) 下载财务快照 -----
    last = last_snapshot_date()
    print(f"最近快照: {last}")

    if last != SNAP_DATE:
        print(f"下载快照: {SNAP_DATE}")
        n = download_snapshot(SNAP_DATE)
        if n == 0:
            print("❌ 财务数据下载失败，退出")
            sys.exit(1)

    # ----- 2) 执行回测 -----
    print(f"\n{'=' * 50}")
    print("多因子选股回测 V1.0")
    print(f"快照: {SNAP_DATE}  |  区间: {START_DATE} → {END_DATE}")
    print(f"初始资金: ¥{INITIAL_CAPITAL:,}  |  Top-N: {TOP_N}")
    print(f"{'=' * 50}\n")

    result = run_backtest(
        snap_date=SNAP_DATE,
        start_date=START_DATE,
        end_date=END_DATE,
        initial_capital=INITIAL_CAPITAL,
        top_n=TOP_N,
    )

    if result is None:
        print("❌ 回测失败")
        sys.exit(1)

    # ----- 3) 保存结果到本地 JSON -----
    out_path = ROOT / "data" / "backtest_result.json"
    out_path.parent.mkdir(exist_ok=True)

    # 序列化 monthly_nav 中的日期
    output = {
        "generated_at": datetime.now().isoformat(),
        "config": {
            "snap_date": SNAP_DATE,
            "start_date": START_DATE,
            "end_date": END_DATE,
            "initial_capital": INITIAL_CAPITAL,
            "top_n": TOP_N,
        },
        "metrics": {
            "cumulative_return": result["cumulative_return"],
            "annual_return": result["annual_return"],
            "max_drawdown": result["max_drawdown"],
            "sharpe_ratio": result["sharpe_ratio"],
            "turnover": result["turnover"],
        },
        "monthly_nav": result.get("monthly_nav", []),
    }

    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ 结果已保存: {out_path}")


if __name__ == "__main__":
    main()
