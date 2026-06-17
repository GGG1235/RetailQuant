"""
rQuant.data — 业务数据层（K 线 / 自选股 / 标的池）
- K 线拉取走 DataSourcePool（datasources.py）
- 自选股 / 内存股票字典 / 标的池 = 纯本地业务数据
"""

from __future__ import annotations
import json
import time
from pathlib import Path

import pandas as pd

from datasources import pool

CACHE_DIR = Path(__file__).parent / "data"
CACHE_DIR.mkdir(exist_ok=True)

STALE_DAYS = 5


# ============== JSON 工具（被 portfolio.py 复用） ==============


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def _save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


# ============== K 线（数据池 wrapper） ==============


def fetch_kline(code: str, days: int = 250) -> pd.DataFrame:
    """从数据源池拉 K 线，返回 DataFrame（列：date, open, high, low, close, volume）

    数据源失败时返回空 DataFrame，业务层需要容错。
    """
    try:
        return pool.to_dataframe(code, days)
    except Exception as e:
        print(f"⚠️ 拉数失败 {code}: {e}")
        return pd.DataFrame()


# ============== 全局内存股票字典 ==============


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
        if age >= 300 or not cached.get("price"):
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


# ============== 自选股（仅持久化 code 列表） ==============


WATCHLIST_FILE = CACHE_DIR / "watchlist.json"


def get_watchlist_codes() -> list[str]:
    """返回自选股 code 列表"""
    return _load_json(WATCHLIST_FILE, [])


def add_to_watchlist(code: str) -> bool:
    """添加 code 到自选股（持久化），返回是否真正新增"""
    codes = get_watchlist_codes()
    if code in codes:
        return False
    codes.append(code)
    _save_json(WATCHLIST_FILE, codes)
    return True


def remove_from_watchlist(code: str) -> bool:
    """从自选股移除 code（持久化），返回是否真正删除"""
    codes = get_watchlist_codes()
    if code not in codes:
        return False
    codes.remove(code)
    _save_json(WATCHLIST_FILE, codes)
    return True


# ============== 标的池（用于信号扫描） ==============


_DEFAULT_POOL = [
    {"code": "sh600460", "name": "士兰微", "sector": "半导体"},
    {"code": "sh600519", "name": "贵州茅台", "sector": "消费"},
    {"code": "sh601318", "name": "中国平安", "sector": "金融"},
    {"code": "sz000001", "name": "平安银行", "sector": "金融"},
    {"code": "sh600036", "name": "招商银行", "sector": "金融"},
]


def get_pool() -> list[dict[str, str]]:
    """返回扫描池：优先从自选股列表 + 内存字典拼装，为空时回退默认池"""
    codes = get_watchlist_codes()
    if not codes:
        return list(_DEFAULT_POOL)
    pool_rows = []
    for code in codes:
        info = _stock_store.get(code, {})
        pool_rows.append(
            {
                "code": code,
                "name": info.get("name", code),
                "sector": info.get("sector", ""),
            }
        )
    return pool_rows