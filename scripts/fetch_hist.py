#!/usr/bin/env python
"""
scripts/fetch_hist.py — 批量拉取 A 股历史日频数据 → Parquet 存储

数据源：Sina K 线接口（datalen=5000 覆盖 2005 年至今）
存储：data/parquet/{code}.parquet

用法：
  python scripts/fetch_hist.py sh600519                  # 单只股票，默认拉全量（2005至今）
  python scripts/fetch_hist.py --from 2010-01-01 --to 2020-01-01 sh600519   # 指定日期范围
  python scripts/fetch_hist.py sh600519 sz000001          # 多只
  python scripts/fetch_hist.py --list                     # 列出已缓存的股票
  python scripts/fetch_hist.py --info sh600519            # 查看缓存信息

注意：
  - amount（成交额）和 turnover（换手率）Sina 不提供，写入为 0
  - 日期过滤在本地完成（拉全量 5000 条后裁剪）
  - 多只股票之间自动间隔 2s，防止被 Sina 限流
"""

from __future__ import annotations

import argparse
import sys
import time

# (date/datetime 未直接使用，akshare 内部依赖)
from pathlib import Path

import pandas as pd
import requests

# 确保项目根目录在 sys.path 中
_PROJ_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJ_ROOT))

from rquant.data_source.parquet_store import info, list_codes, write  # noqa: E402

# Sina K 线接口
_SINA_KLINE_URL = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
# 拉到最大深度（实测 5000 条覆盖 2005 年至今）
_MAX_DATALEN = 5000
_REQUEST_TIMEOUT = 15


def _fetch_sina(code: str) -> list[dict]:
    """从 Sina 拉取单只股票的全量日 K 线（最多 5000 条）"""
    url = f"{_SINA_KLINE_URL}?symbol={code}&scale=240&ma=no&datalen={_MAX_DATALEN}"
    r = requests.get(url, timeout=_REQUEST_TIMEOUT)
    if r.status_code != 200 or not r.text.strip():
        return []
    data = r.json()
    if not isinstance(data, list) or not data:
        return []
    return data


def fetch_one(code: str, start: str | None, end: str | None, retries: int = 2) -> int:
    """
    拉取一只股票的历史日频数据，写入 Parquet。
    返回写入行数。

    参数：
      code: 股票代码（如 sh600519）
      start: 起始日期（YYYY-MM-DD），None 表示不限制
      end: 结束日期（YYYY-MM-DD），None 表示不限制
      retries: 重试次数
    """
    delay = 1.0
    for attempt in range(retries + 1):
        try:
            raw = _fetch_sina(code)
            break
        except Exception as e:
            if attempt < retries:
                print(f"  [WARN] 第 {attempt + 1} 次失败: {e}，{delay}s 后重试...")
                time.sleep(delay)
                delay *= 2
            else:
                print(f"  [FAIL] 拉取失败（{retries + 1} 次后）: {e}")
                return 0

    if not raw:
        print("  [WARN] 返回空数据")
        return 0

    # Sina 返回: {day, open, high, low, close, volume}
    df = pd.DataFrame(raw)
    df = df.rename(
        columns={
            "day": "date",
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "volume": "volume",
        }
    )

    # 标准化类型
    df["date"] = pd.to_datetime(df["date"])
    # Sina 返回的字符串数值，"0.000"/"0" 表示无效，转为 NaN 后 drop
    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype("int64")

    # Sina 不提供 amount / turnover，填 0
    df["amount"] = 0
    df["turnover"] = 0.0

    # 日期范围过滤
    if start:
        df = df[df["date"] >= pd.Timestamp(start)]
    if end:
        df = df[df["date"] <= pd.Timestamp(end)]

    if df.empty:
        print(f"  [WARN] 日期范围 {start} ~ {end} 内无数据（全量 {len(raw)} 条）")
        return 0

    write(code, df, mode="replace")
    return len(df)


def main():
    parser = argparse.ArgumentParser(
        description="拉取 A 股历史日频数据 → Parquet（数据源：Sina）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/fetch_hist.py sh600519
  python scripts/fetch_hist.py --from 2010-01-01 --to 2020-01-01 sh600519
  python scripts/fetch_hist.py sh600519 sz000001 sh600460
  python scripts/fetch_hist.py --list
  python scripts/fetch_hist.py --info sh600519
        """,
    )
    parser.add_argument("codes", nargs="*", help="股票代码（如 sh600519）")
    parser.add_argument("--from", dest="start", default=None, help="起始日期 YYYY-MM-DD（默认：不限制）")
    parser.add_argument("--to", dest="end", default=None, help="结束日期 YYYY-MM-DD（默认：不限制）")
    parser.add_argument("--list", action="store_true", help="列出已缓存的股票")
    parser.add_argument("--info", metavar="CODE", help="查看某只股票的缓存信息")

    args = parser.parse_args()

    # --list
    if args.list:
        codes = list_codes()
        if not codes:
            print("（暂无缓存数据）")
        else:
            print(f"已缓存 {len(codes)} 只股票：")
            for c in codes:
                inf = info(c)
                if inf:
                    print(
                        f"  {c:12s}  {inf['rows']:5d} 行  {inf['date_from']} ~ {inf['date_to']}  {inf['size_kb']:6.1f} KB"
                    )
        return

    # --info
    if args.info:
        inf = info(args.info)
        if inf is None:
            print(f"未找到 {args.info} 的缓存数据")
        else:
            print(f"{inf['code']}: {inf['rows']} 行, {inf['date_from']} ~ {inf['date_to']}, {inf['size_kb']} KB")
        return

    # 拉取
    if not args.codes:
        parser.print_help()
        return

    total_rows = 0
    total_elapsed = 0.0
    for i, code in enumerate(args.codes, 1):
        date_range = ""
        if args.start or args.end:
            date_range = f" ({args.start or '不限'} ~ {args.end or '不限'})"
        print(f"[{i}/{len(args.codes)}] {code}{date_range} ...")
        t0 = time.time()
        rows = fetch_one(code, args.start, args.end)
        elapsed = time.time() - t0
        total_rows += rows
        total_elapsed += elapsed
        if rows > 0:
            print(f"  [OK] {rows} 行 ({elapsed:.1f}s)")
        else:
            print(f"  [FAIL] 无数据 ({elapsed:.1f}s)")

        if i < len(args.codes):
            time.sleep(2.0)

    print(f"\n总计: {total_rows} 行, 耗时 {total_elapsed:.1f}s")


if __name__ == "__main__":
    main()
