"""
rquant.data_source.eastmoney — 东财财务数据源（基于 akshare）
- 批量下载沪深A股财务快照（PE / PB / ROE / 总市值 / 名称）
- SQLite 本地缓存
- 历史数据 → 按月存储快照，满足回测需求

用法:
    download_snapshot("2025-12-31")  → 下载当日全市场快照
    get_all_snapshots("2025-12-31")  → 读取缓存快照
"""

from __future__ import annotations

import os
import sqlite3
import time
from typing import Optional

from config import config
from rquant.log import info, warning, error

# SQLite 缓存路径
_DB_PATH = config.project_root / config.paths.cache_dir / config.database.eastmoney_db_name


def _ensure_db() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS financial_snapshot (
            code      TEXT    NOT NULL,
            snap_date TEXT    NOT NULL,
            name      TEXT    NOT NULL,
            pe_ttm    REAL,
            pb        REAL,
            roe       REAL,
            mcap      REAL,
            fetched_at REAL   NOT NULL,
            PRIMARY KEY (code, snap_date)
        )
        """
    )
    conn.commit()
    return conn


def _patch_akshare_session():
    """让 akshare 内部 session 跳过系统代理"""
    os.environ.setdefault("NO_PROXY", os.environ.get("NO_PROXY", "") + ",*.eastmoney.com,*.eastmoney.com.cn")
    try:
        from akshare.utils.request import _session as _ak_sess  # type: ignore

        if hasattr(_ak_sess, "trust_env"):
            _ak_sess.trust_env = False
    except Exception:
        pass


def download_snapshot(snap_date: Optional[str] = None) -> int:
    """批量下载全A股财务快照（通过 akshare），写入 SQLite。返回写入条数。

    若网络不可达（如企业代理拦截），将打印错误并返回 0。
    """
    if snap_date is None:
        snap_date = time.strftime("%Y-%m-%d")

    _patch_akshare_session()

    try:
        import akshare as ak
        import pandas as pd
    except ImportError:
        error("eastmoney", "akshare 未安装，请运行: uv add akshare")
        return 0

    info("eastmoney", "正在从 akshare 拉取全 A 股行情（含 PE/PB/ROE/市值）...")
    try:
        df: pd.DataFrame = ak.stock_zh_a_spot_em()
    except Exception as e:
        error("eastmoney", f"拉取失败: {e}")
        error("eastmoney", "提示：可能是系统代理拦截。请尝试关闭代理后重试。")
        return 0

    if df is None or df.empty:
        warning("eastmoney", "未获取到数据")
        return 0

    # 列名映射（akshare 返回中文列名）
    col_map = {
        "代码": "code",
        "名称": "name",
        "市盈率-动态": "pe_ttm",
        "市净率": "pb",
        "净资产收益率": "roe",
        "总市值": "mcap",
    }
    # 兼容不同版本的 akshare 列名
    for cn, en in list(col_map.items()):
        if cn not in df.columns and en not in df.columns:
            # 尝试备选列名
            alt_map = {"市盈率-动态": "市盈率", "净资产收益率": "ROE"}
            if cn in alt_map:
                alt_cn = alt_map[cn]
                if alt_cn in df.columns:
                    col_map[cn] = en
                    continue
            col_map.pop(cn)

    conn = _ensure_db()
    now = time.time()
    count = 0
    rows: list[tuple] = []

    for _, row in df.iterrows():
        code = str(row.get("代码", ""))
        name = str(row.get("名称", ""))
        if not code or code == "nan":
            continue

        pe_ttm = _safe_float(row.get("市盈率-动态"))
        pb = _safe_float(row.get("市净率"))
        roe = _safe_float(row.get("净资产收益率"))
        mcap = _safe_float(row.get("总市值"))

        rows.append((code, snap_date, name, pe_ttm, pb, roe, mcap, now))
        count += 1

    if rows:
        conn.executemany(
            "INSERT OR REPLACE INTO financial_snapshot(code, snap_date, name, pe_ttm, pb, roe, mcap, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()

    conn.close()
    info("eastmoney", f"快照完成: {count} 条 ({snap_date})")
    return count


def _safe_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        v = float(val)
        if v != v:  # NaN
            return None
        return v
    except (ValueError, TypeError):
        return None


def get_snapshot(code: str, snap_date: Optional[str] = None) -> Optional[dict]:
    """查询单只股票的财务快照"""
    conn = _ensure_db()
    if snap_date:
        row = conn.execute(
            "SELECT code, snap_date, name, pe_ttm, pb, roe, mcap FROM financial_snapshot WHERE code=? AND snap_date=?",
            (code, snap_date),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT code, snap_date, name, pe_ttm, pb, roe, mcap "
            "FROM financial_snapshot WHERE code=? ORDER BY snap_date DESC LIMIT 1",
            (code,),
        ).fetchone()
    conn.close()
    if row is None:
        return None
    return {
        "code": row[0],
        "snap_date": row[1],
        "name": row[2],
        "pe_ttm": row[3],
        "pb": row[4],
        "roe": row[5],
        "mcap": row[6],
    }


def get_all_snapshots(snap_date: str) -> dict[str, dict]:
    """获取某日全量快照，返回 {code: {name, pe_ttm, pb, roe, mcap}}"""
    conn = _ensure_db()
    rows = conn.execute(
        "SELECT code, name, pe_ttm, pb, roe, mcap FROM financial_snapshot WHERE snap_date=?",
        (snap_date,),
    ).fetchall()
    conn.close()
    result = {}
    for r in rows:
        result[r[0]] = {
            "name": r[1],
            "pe_ttm": r[2],
            "pb": r[3],
            "roe": r[4],
            "mcap": r[5],
        }
    return result


def last_snapshot_date() -> Optional[str]:
    """返回最近的快照日期"""
    conn = _ensure_db()
    row = conn.execute("SELECT snap_date FROM financial_snapshot ORDER BY snap_date DESC LIMIT 1").fetchone()
    conn.close()
    return row[0] if row else None
