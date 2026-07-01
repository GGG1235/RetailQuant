"""
convert_data.py — 一键将 Qlib 日线数据转换为 vnpy AlphaLab 格式

用法：
    uv run python3 research/backtest_learning/convert_data.py

数据来源（二选一，脚本自动检测）：
    1. qlib_daily.parquet（项目根目录）— 已存在的中间文件，直接转换
    2. ~/.qlib/qlib_data/cn_data/    — Qlib 原生 .bin 格式，先导出再转换

输出：
    research/daily/{代码}.{交易所}.parquet   — 每只股票一个文件
    research/contract.json                   — 交易费率配置
"""

import json
import sys
import time
from pathlib import Path

from vnpy.trader.constant import Interval as _  # noqa: F401  确保 trader 模块可导入

# ═══════════════════════════════════════════════════════════════
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent / "vnpy"
QLIB_PARQUET = PROJECT_ROOT / "qlib_daily.parquet"
OUTPUT_DAILY = PROJECT_ROOT / "research" / "daily"
OUTPUT_DIR = OUTPUT_DAILY.parent
CONTRACT_JSON = OUTPUT_DIR / "contract.json"

LONG_RATE = 0.0005
SHORT_RATE = 0.0015
SIZE = 1
PRICE_TICK = 0.01
# ═══════════════════════════════════════════════════════════════


def step(msg: str) -> None:
    """打印带时间戳的步骤标题"""
    t = time.strftime("%H:%M:%S")
    print(f"\n[{t}] {msg}")


def info(msg: str) -> None:
    print(f"       {msg}")


def convert_from_parquet() -> None:
    """从单个 Parquet 文件转换（主路径）"""
    import duckdb
    import polars as pl

    file_size = QLIB_PARQUET.stat().st_size
    info(f"读取文件: {QLIB_PARQUET.name} ({file_size/1024/1024:.0f} MB)")

    # ── Step 1: duckdb SQL 列映射 ──
    step("Step 1/4: 列映射（stock_id → vt_symbol, amount → turnover...）")
    con = duckdb.connect(":memory:")

    con.execute(f"""
        CREATE VIEW vnpy_bars AS
        SELECT
            CASE
                WHEN stock_id LIKE 'sh%' THEN substring(stock_id, 3) || '.SSE'
                WHEN stock_id LIKE 'sz%' THEN substring(stock_id, 3) || '.SZSE'
                ELSE stock_id
            END AS vt_symbol,
            date AS datetime,
            open, high, low, close, volume,
            amount AS turnover,
            0.0 AS open_interest
        FROM '{QLIB_PARQUET.resolve()}'
        WHERE close IS NOT NULL AND volume IS NOT NULL
    """)

    symbols = con.execute(
        "SELECT DISTINCT vt_symbol FROM vnpy_bars ORDER BY vt_symbol"
    ).fetchall()

    total = len(symbols)
    total_rows = con.execute("SELECT count(*) FROM vnpy_bars").fetchone()[0]
    info(f"共 {total:,} 只股票，{total_rows:,} 行数据")

    # ── Step 2: 写出 Parquet ──
    step(f"Step 2/4: 写出 Parquet → {OUTPUT_DAILY.relative_to(PROJECT_ROOT)}/")
    OUTPUT_DAILY.mkdir(parents=True, exist_ok=True)

    # 清理旧文件
    old_count = len(list(OUTPUT_DAILY.glob("*.parquet")))
    if old_count:
        info(f"清理旧文件 {old_count:,} 个...")
        for f in OUTPUT_DAILY.glob("*.parquet"):
            f.unlink()

    report_every = max(1, total // 10)

    for i, (sym,) in enumerate(symbols):
        out = OUTPUT_DAILY / f"{sym}.parquet"
        con.execute(f"""
            COPY (
                SELECT datetime, vt_symbol, open, high, low,
                       close, volume, turnover, open_interest
                FROM vnpy_bars
                WHERE vt_symbol = '{sym}'
                ORDER BY datetime
            ) TO '{out.resolve()}' (FORMAT PARQUET)
        """)

        if (i + 1) % report_every == 0:
            info(f"  {i+1}/{total} ({(i+1)*100//total}%)")

    con.close()
    info(f"完成: {total:,} 个文件")

    # ── Step 3: 修正 datetime 类型 ──
    step(f"Step 3/4: 修正 datetime 列类型（Date → Datetime）")
    parquet_files = sorted(OUTPUT_DAILY.glob("*.parquet"))

    for i, f in enumerate(parquet_files):
        df = pl.read_parquet(f)
        df = df.with_columns(pl.col("datetime").cast(pl.Datetime))
        df.write_parquet(f)

        if (i + 1) % report_every == 0:
            info(f"  {i+1}/{total} ({(i+1)*100//total}%)")

    info("完成")

    # ── Step 4: 生成 contract.json ──
    step(f"Step 4/4: 生成合约配置 → {CONTRACT_JSON.relative_to(PROJECT_ROOT)}")
    contracts = {}

    for f in parquet_files:
        sym = f.stem
        contracts[sym] = {
            "long_rate": LONG_RATE,
            "short_rate": SHORT_RATE,
            "size": SIZE,
            "pricetick": PRICE_TICK,
        }

    with open(CONTRACT_JSON, "w", encoding="utf-8") as f:
        json.dump(contracts, f, indent=2, ensure_ascii=False)

    info(f"共 {len(contracts):,} 只股票")


def convert_from_qlib_bin() -> None:
    """从 Qlib 原生 .bin 格式转换（备选路径）"""
    try:
        import qlib
        from qlib.constant import REG_CN
        from qlib.data import D
    except ImportError:
        print("错误：需要安装 Qlib")
        print("  pip install pyqlib@git+https://github.com/microsoft/qlib")
        sys.exit(1)

    import polars as pl

    qlib_dir = str(Path.home() / ".qlib" / "qlib_data" / "cn_data")
    step(f"初始化 Qlib: {qlib_dir}")
    qlib.init(provider_uri=qlib_dir, region=REG_CN)

    all_stocks = D.list_instruments(D.instruments(market="all"), as_list=True)
    total = len(all_stocks)
    info(f"全 A 标的: {total:,} 只")

    step("从 Qlib 导出数据...")
    BATCH = 500
    all_dfs = []

    for i in range(0, total, BATCH):
        batch = all_stocks[i : i + BATCH]
        n = i // BATCH + 1
        total_n = (total + BATCH - 1) // BATCH
        info(f"  批次 {n}/{total_n}: {len(batch)} 只")

        pdf = D.features(
            batch,
            [
                "$open", "$high", "$low", "$close",
                "$volume", "$amount", "$vwap",
                "$factor", "$adjclose", "$change",
            ],
            start_time="2000-01-01",
            end_time="2026-06-30",
        )

        pdf = pdf.reset_index()
        pdf.rename(columns={"instrument": "stock_id"}, inplace=True)
        all_dfs.append(pl.from_pandas(pdf))

    step("合并写入 Parquet...")
    final = pl.concat(all_dfs)
    final = final.select([
        "datetime", "stock_id",
        "open", "high", "low", "close",
        "volume", "amount", "vwap",
        "factor", "adjclose", "change",
    ])

    final.write_parquet(QLIB_PARQUET)
    info(f"导出完成: {QLIB_PARQUET.name} ({QLIB_PARQUET.stat().st_size/1024/1024:.0f} MB)")
    info(f"{final.height:,} 行, {final.width} 列, {final['stock_id'].n_unique():,} 只股票")

    # 递归调用，走 Parquet 路径
    convert_from_parquet()


# ═══════════════════════════════════════════════════════════════
def main():
    print("=" * 55)
    print("  Qlib → vnpy AlphaLab 数据转换")
    print("=" * 55)

    start = time.time()

    if QLIB_PARQUET.exists():
        convert_from_parquet()
    else:
        info(f"未找到 {QLIB_PARQUET.name}，尝试从 Qlib 原生格式导出...")
        convert_from_qlib_bin()

    # ── 总结 ──
    elapsed = time.time() - start
    files = list(OUTPUT_DAILY.glob("*.parquet"))
    total_size = sum(p.stat().st_size for p in files)

    print(f"\n{'='*55}")
    print(f"  ✅ 转换完成 ({elapsed:.0f} 秒)")
    print(f"  输出: {len(files):,} 个文件 / {total_size/1024/1024:.0f} MB")
    print(f"  目录: {OUTPUT_DAILY.relative_to(PROJECT_ROOT)}")
    print(f"  配置: {CONTRACT_JSON.relative_to(PROJECT_ROOT)}")
    print(f"{'='*55}")


if __name__ == "__main__":
    main()
