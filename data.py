"""
rQuant.data — 最简数据层
- 仅 Sina 一个源
- 本地 JSON 缓存（按 code 分文件）
- 不做异步、不做熔断、不做质量校验（最简实现）
"""
from __future__ import annotations
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

import requests
import pandas as pd

CACHE_DIR = Path(__file__).parent / "data"
CACHE_DIR.mkdir(exist_ok=True)

SINA_URL = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"


def _cache_path(code: str) -> Path:
    return CACHE_DIR / f"{code}.json"


def fetch_kline(code: str, days: int = 250) -> pd.DataFrame:
    """从 Sina 拉 K 线 + JSON 缓存
    days: 取最近多少根（240 = 日线，1 根=1 天）
    """
    cache_file = _cache_path(code)
    cached = []
    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text())
        except Exception:
            cached = []

    # 简单判断：缓存最后一天距今超过 1 个交易日 → 重拉
    # 工作日 + 1 天缓冲
    last_date = ""
    if cached:
        last_date = cached[-1].get("day", "")
    need_refresh = True
    if last_date:
        try:
            last_dt = datetime.strptime(last_date, "%Y-%m-%d")
            # 超过 5 个日历日才重拉（应付周末/节假日）
            need_refresh = (datetime.now() - last_dt).days >= 5
        except Exception:
            need_refresh = True

    if need_refresh:
        try:
            url = f"{SINA_URL}?symbol={code}&scale=240&ma=no&datalen={days}"
            r = requests.get(url, timeout=5)
            if r.status_code == 200 and r.text.strip():
                fresh = r.json()
                if isinstance(fresh, list) and fresh:
                    # 合并：缓存旧的 + 新增
                    existing_dates = {x.get("day") for x in cached}
                    merged = list(cached)
                    for row in fresh:
                        if row.get("day") not in existing_dates:
                            merged.append(row)
                    # 重新按日期排序 + 截到 days 根
                    merged.sort(key=lambda x: x.get("day", ""))
                    merged = merged[-days:]
                    cached = merged
                    cache_file.write_text(json.dumps(cached, ensure_ascii=False), encoding='utf-8')
        except Exception as e:
            print(f"⚠️ 拉数失败 {code}: {e}")

    if not cached:
        return pd.DataFrame()

    df = pd.DataFrame(cached)
    df = df.rename(columns={"day": "date", "open": "open", "high": "high",
                            "low": "low", "close": "close", "volume": "volume"})
    for c in ["open", "high", "low", "close", "volume"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df[["date", "open", "high", "low", "close", "volume"]]


# ============== 全局内存股票字典 ==============

_stock_store: Dict[str, Dict[str, Any]] = {}

def upsert_stock(code: str, **kwargs: Any) -> None:
    """将股票信息写入全局内存字典（合并更新）"""
    if code not in _stock_store:
        _stock_store[code] = {}
    _stock_store[code].update(kwargs)

def get_stock(code: str) -> Dict[str, Any]:
    """从内存字典读取单只股票信息"""
    return _stock_store.get(code, {})

def get_all_stocks() -> Dict[str, Dict[str, Any]]:
    """返回全局股票字典的浅拷贝"""
    return dict(_stock_store)


# ============== 自选股（仅持久化 code 列表） ==============

WATCHLIST_FILE = CACHE_DIR / "watchlist.json"

def _load_json(path: Path, default=None):
    if not path.exists():
        return default if default is not None else []
    try:
        return json.loads(path.read_text())
    except Exception:
        return default if default is not None else []

def _save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')

def get_watchlist_codes() -> List[str]:
    """返回自选股 code 列表"""
    return _load_json(WATCHLIST_FILE, [])

def add_to_watchlist(code: str) -> bool:
    """添加 code 到自选股（持久化），返回是否真正新增"""
    codes = get_watchlist_codes()
    if code not in codes:
        codes.append(code)
        _save_json(WATCHLIST_FILE, codes)
        return True
    return False

def remove_from_watchlist(code: str) -> bool:
    """从自选股移除 code（持久化），返回是否真正删除"""
    codes = get_watchlist_codes()
    if code in codes:
        codes.remove(code)
        _save_json(WATCHLIST_FILE, codes)
        return True
    return False


# ============== 标的池（用于信号扫描） ==============

_DEFAULT_POOL = [
    {"code": "sh600460", "name": "士兰微", "sector": "半导体"},
    {"code": "sh600519", "name": "贵州茅台", "sector": "消费"},
    {"code": "sh601318", "name": "中国平安", "sector": "金融"},
    {"code": "sz000001", "name": "平安银行", "sector": "金融"},
    {"code": "sh600036", "name": "招商银行", "sector": "金融"},
]

def get_pool() -> List[Dict[str, str]]:
    """返回扫描池：优先从自选股列表 + 内存字典拼装，为空时回退默认池"""
    codes = get_watchlist_codes()
    if not codes:
        return list(_DEFAULT_POOL)
    pool = []
    for code in codes:
        info = _stock_store.get(code, {})
        pool.append({
            "code": code,
            "name": info.get("name", code),
            "sector": info.get("sector", ""),
        })
    return pool