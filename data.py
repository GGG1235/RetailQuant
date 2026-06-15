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
                    cache_file.write_text(json.dumps(cached, ensure_ascii=False))
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


# 5 只标的池（阉割版，只保留稳定大票）
STOCK_POOL = [
    {"code": "sh600460", "name": "士兰微", "sector": "半导体"},
    {"code": "sh600519", "name": "贵州茅台", "sector": "消费"},
    {"code": "sh601318", "name": "中国平安", "sector": "金融"},
    {"code": "sz000001", "name": "平安银行", "sector": "金融"},
    {"code": "sh600036", "name": "招商银行", "sector": "金融"},
]


def get_pool() -> List[Dict[str, str]]:
    return STOCK_POOL
