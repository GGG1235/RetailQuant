"""
rquant.data_source.parquet_store — Parquet 历史日频数据存储层

- 目录：data/parquet/
- 每股票一个文件：{code}.parquet
- 列：date, open, high, low, close, volume, amount, turnover
- 完全独立于 SQLite（db.py），不耦合、不破坏现有代码
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# Parquet 数据目录
_PARQUET_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "parquet"

# 标准列定义（按此顺序写入，date 为主键）
_COLUMNS = ["date", "open", "high", "low", "close", "volume", "amount", "turnover"]

# Parquet schema（显式类型，兼容所有 Parquet 读取器）
_SCHEMA = pa.schema(
    [
        ("date", pa.date32()),  # 交易日
        ("open", pa.float64()),  # 开盘价
        ("high", pa.float64()),  # 最高价
        ("low", pa.float64()),  # 最低价
        ("close", pa.float64()),  # 收盘价
        ("volume", pa.int64()),  # 成交量（股）
        ("amount", pa.float64()),  # 成交额（元）
        ("turnover", pa.float64()),  # 换手率（%）
    ]
)


def _ensure_dir() -> None:
    """确保目录存在"""
    _PARQUET_DIR.mkdir(parents=True, exist_ok=True)


def _file_path(code: str) -> Path:
    """返回某只股票的 Parquet 文件路径"""
    return _PARQUET_DIR / f"{code}.parquet"


def exists(code: str) -> bool:
    """检查某只股票的 Parquet 文件是否存在"""
    return _file_path(code).exists()


def read(code: str) -> pd.DataFrame:
    """
    读取某只股票的全部历史日频数据。
    返回空 DataFrame（而非抛异常）当文件不存在时。
    """
    fp = _file_path(code)
    if not fp.exists():
        return pd.DataFrame(columns=_COLUMNS)
    df = pq.read_table(fp).to_pandas()
    # 确保 date 是 date/datetime 类型
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"]).dt.date
    return df.sort_values("date").reset_index(drop=True)


def write(code: str, df: pd.DataFrame, mode: str = "replace") -> None:
    """
    写入一只股票的历史日频数据到 Parquet。

    mode:
      - "replace": 覆盖写入（默认）
      - "append":  追加写入（去重 by date）
    """
    _ensure_dir()
    fp = _file_path(code)

    # 标准化列名和类型
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date

    # 确保所需列都存在
    for col in _COLUMNS:
        if col not in df.columns:
            df[col] = 0 if col in ("volume", "amount", "turnover") else None

    df = df[_COLUMNS].dropna(subset=["date", "open", "high", "low", "close"])

    if mode == "append" and fp.exists():
        existing = read(code)
        df = pd.concat([existing, df], ignore_index=True)
        df = df.drop_duplicates(subset="date", keep="last")

    df = df.sort_values("date").reset_index(drop=True)

    table = pa.Table.from_pandas(df, schema=_SCHEMA, preserve_index=False)
    pq.write_table(table, fp, compression="snappy")


def list_codes() -> list[str]:
    """列出所有已缓存的股票代码"""
    _ensure_dir()
    return sorted([f.stem for f in _PARQUET_DIR.glob("*.parquet")])


def info(code: str) -> Optional[dict]:
    """
    返回某只股票 Parquet 文件的元信息：
    - rows: 总行数
    - date_from: 最早日期
    - date_to: 最晚日期
    - size_kb: 文件大小（KB）
    """
    fp = _file_path(code)
    if not fp.exists():
        return None
    df = read(code)
    return {
        "code": code,
        "rows": len(df),
        "date_from": str(df["date"].min()) if len(df) > 0 else None,
        "date_to": str(df["date"].max()) if len(df) > 0 else None,
        "size_kb": round(fp.stat().st_size / 1024, 1),
    }
