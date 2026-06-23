"""
rquant.business.data — 业务数据层（精简版）
- K 线拉取走 DataSourcePool（rquant.data_source）
- 自选股 / 标的池 → rquant.business.pool_store
- _stock_store 仍是"已查看过的股票临时信息"（含 name/price/change_pct/turnover），
  用于前端 watchlist 视图补全；与 pool 解耦
"""

from __future__ import annotations
import json
import time
from pathlib import Path

import pandas as pd

from config import config
from rquant.data_source import pool

# 业务数据目录（portfolio / trades / snapshots 等 JSON 存这里）
DATA_DIR = config.project_root / config.paths.data_dir
DATA_DIR.mkdir(exist_ok=True)

STALE_DAYS = config.cache.stale_days


# ============== JSON 工具（被 portfolio.py 复用）==============


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


# ============== K 线（数据池 wrapper）==============


def fetch_kline(code: str, days: int = 250) -> pd.DataFrame:
    """从数据源池拉 K 线，返回 DataFrame（列：date, open, high, low, close, volume）

    数据源失败时返回空 DataFrame，业务层需要容错。
    """
    try:
        return pool.to_dataframe(code, days)
    except Exception as e:
        print(f"⚠️ 拉数失败 {code}: {e}")
        return pd.DataFrame()


# ============== 全局内存股票字典（已查看过的快照）==============
# 用途：前端 watchlist 视图补全（name/price/change_pct/turnover）
# 区别于 pool_store：这里存"实时查看后的快照"，pool 是"配置/标的池"
# 重启清空（不需要持久化，K线数据池本身是 source of truth）

_stock_store: dict[str, dict] = {}


def upsert_stock(code: str, **kwargs) -> None:
    """将股票信息写入全局内存字典（合并更新），自动记录更新时间戳"""
    _stock_store.setdefault(code, {}).update(kwargs)
    _stock_store[code]["_updated_at"] = time.time()


def get_stock(code: str) -> dict:
    """从内存字典读取单只股票信息"""
    return _stock_store.get(code, {})


def get_all_stocks() -> dict[str, dict]:
    """返回全局股票字典的浅拷贝"""
    return dict(_stock_store)


def populate_watchlist_info(codes: list[str]) -> None:
    """批量拉取自选股行情填充内存字典（带 5 分钟缓存）。
    调用方可放心重复调用，已缓存且未过期的 code 会被跳过。
    """
    if not codes:
        return
    now = time.time()
    to_fetch: list[str] = []
    for code in codes:
        cached = _stock_store.get(code, {})
        age = now - cached.get("_updated_at", 0) if cached.get("_updated_at") else 9999
        if age >= config.business.watchlist_cache_seconds or not cached.get("price"):
            to_fetch.append(code)
    if not to_fetch:
        return
    try:
        quotes = pool.fetch_quotes(to_fetch)
        for code, quote in quotes.items():
            upsert_stock(
                code,
                name=quote.get("name", code),
                price=quote.get("price", 0),
                change_pct=quote.get("change_pct", 0),
            )
    except Exception:
        pass
