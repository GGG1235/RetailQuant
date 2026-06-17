"""
rquant.data_source.cache — 数据源缓存目录 + 通用常量
- 业务数据（portfolio.json / trades.json / watchlist.json）→ data/
- K 线 / 行情缓存 → cache/
"""

from __future__ import annotations
from pathlib import Path

# K 线 / 行情 JSON 缓存目录
CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

# Sina 接口常量
SINA_KLINE_URL = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
SINA_QUOTE_URL = "https://hq.sinajs.cn/list="
SINA_HEADERS = {"Referer": "https://finance.sina.com.cn/"}

# 通用常量
STALE_DAYS = 5
PRICE_COLS = ("open", "high", "low", "close", "volume")
DEFAULT_TIMEOUT = 8
UNHEALTHY_COOLDOWN = 60
