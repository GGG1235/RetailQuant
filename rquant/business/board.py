"""
rquant.board — 板块行情业务层
- 数据源：东方财富 push2 接口（行业 / 概念 / 地域板块）
- 直接拉真实板块数据（板块名/涨跌幅/领涨股/股票数）
- 不再使用 ETF 代理板块
- 业务层缓存 2 分钟（serve-stale：拉取失败时用过期缓存顶上）
- 对外 API：fetch_sector_boards / fetch_concept_boards / fetch_board_stocks
"""

from __future__ import annotations
import sys
import time
from datetime import datetime

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ============== 数据源（东方财富 push2）==============

EAST_MONEY_URL = "https://push2delay.eastmoney.com/api/qt/clist/get"
# 板块类型 → 东财 fs 过滤
# m:90 = 板块市场；t:2=行业，t:3=概念，t:1=地域
BOARD_TYPES = {
    "sector": "m:90+t:2",
    "concept": "m:90+t:3",
    "area": "m:90+t:1",
}
# 板块 code 前缀（前端透传用，避免与个股 sh/sz 冲突）
BOARD_CODE_PREFIX = "bk_"

# 复用 session（连接池）+ 自动重试（应对东财偶发断连）
_session = requests.Session()
_session.headers.update(
    {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": "https://quote.eastmoney.com/",
    }
)
# 关键：忽略 HTTP_PROXY/HTTPS_PROXY 等环境变量（直连，避免被系统代理污染）
_session.trust_env = False

# 自动重试：3 次，backoff 0.5/1.0/2.0 秒，只重试可恢复的错
_retry = Retry(
    total=3,
    backoff_factor=0.5,
    status_forcelist=(500, 502, 503, 504),
    allowed_methods=frozenset(["GET"]),
    raise_on_status=False,
)
_adapter = HTTPAdapter(max_retries=_retry, pool_connections=4, pool_maxsize=8)
_session.mount("https://", _adapter)
_session.mount("http://", _adapter)

# ============== 业务层缓存（serve-stale）==============

CACHE_TTL = 120  # 秒（新鲜窗口）
STALE_TTL = 600  # 秒（过期后还能用 10 分钟，serve-stale 兜底）
_cache: dict[str, tuple] = {}  # key → (data, timestamp)


def _log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    sys.stderr.write(f"[{ts}] [board] {msg}\n")
    sys.stderr.flush()


def _cached(key: str, allow_stale: bool = False):
    """读缓存。

    allow_stale=False → 只返回新鲜数据
    allow_stale=True  → 新鲜优先；没有则返回过期但仍在 STALE_TTL 内的数据（兜底）
    """
    item = _cache.get(key)
    if item is None:
        return None
    data, ts = item
    age = time.time() - ts
    if age < CACHE_TTL:
        return data
    if allow_stale and age < STALE_TTL:
        return data
    return None


def _set_cache(key: str, data) -> None:
    _cache[key] = (data, time.time())


# ============== 板块排行 ==============


def _fetch_boards(board_type: str, top_n: int) -> list[dict]:
    """从东方财富拉真实板块排行（按涨跌幅降序）"""
    cache_key = f"boards_{board_type}"
    cached = _cached(cache_key)
    if cached is not None:
        _log(f"{board_type} 板块: 命中缓存, {len(cached)} 条")
        return cached[:top_n]

    fs = BOARD_TYPES.get(board_type)
    if fs is None:
        _log(f"{board_type} 板块: 未知类型")
        return []

    # 字段：f3 涨跌幅(×100) / f4 涨跌额 / f12 板块 code / f14 板块名
    #      f104 股票数 / f128 领涨股名 / f140 领涨股 code
    params = {
        "pn": 1,
        "pz": max(top_n * 2, 50),  # 多拉点保证排序后够
        "po": 1,
        "fid": "f3",
        "fs": fs,
        "fields": "f3,f4,f12,f14,f104,f128,f140",
    }
    try:
        r = _session.get(EAST_MONEY_URL, params=params, timeout=8)
        if r.status_code != 200:
            _log(f"{board_type} 板块: HTTP {r.status_code}")
            return _serve_stale(cache_key, board_type, top_n)
        payload = r.json()
        diff = (payload.get("data") or {}).get("diff") or {}
        if not diff:
            _log(f"{board_type} 板块: 数据为空")
            return _serve_stale(cache_key, board_type, top_n)
    except Exception as e:
        _log(f"{board_type} 板块: 拉取失败 {e}")
        return _serve_stale(cache_key, board_type, top_n)

    rows: list[dict] = []
    for item in diff.values():
        rows.append(
            {
                "code": f"{BOARD_CODE_PREFIX}{item.get('f12', '')}",
                "name": item.get("f14", ""),
                # f3 单位 0.01%：807 → 8.07
                "change_pct": round(item.get("f3", 0) / 100, 2),
                # f4 单位"点"（板块指数点位涨跌）
                "change_amt": round(item.get("f4", 0) / 100, 2),
                "stocks_count": item.get("f104", 0),
                "lead_stock": item.get("f128", ""),
                "lead_stock_code": item.get("f140", ""),
            }
        )
    # 保险再排一次
    rows.sort(key=lambda x: x["change_pct"], reverse=True)
    _log(f"{board_type} 板块: 刷新完成, {len(rows)} 个")
    _set_cache(cache_key, rows)
    return rows[:top_n]


def _serve_stale(cache_key: str, board_type: str, top_n: int) -> list[dict]:
    """拉取失败时兜底：返回过期但未超过 STALE_TTL 的旧数据"""
    stale = _cached(cache_key, allow_stale=True)
    if stale is not None:
        _log(f"{board_type} 板块: 远端失败，回退 stale 缓存 ({len(stale)} 条)")
        return stale[:top_n]
    return []


def fetch_sector_boards(top_n: int = 30) -> list[dict]:
    """行业板块排行（按涨跌幅降序）"""
    return _fetch_boards("sector", top_n)


def fetch_concept_boards(top_n: int = 30) -> list[dict]:
    """概念板块排行（按涨跌幅降序）"""
    return _fetch_boards("concept", top_n)


def fetch_area_boards(top_n: int = 30) -> list[dict]:
    """地域板块排行（按涨跌幅降序）"""
    return _fetch_boards("area", top_n)


# ============== 板块成分股 ==============


def _normalize_board_code(code: str) -> str:
    """前端透传 'bk_BK0420' → 'BK0420'；老 ETF code 原样返回"""
    if code.startswith(BOARD_CODE_PREFIX):
        return code[len(BOARD_CODE_PREFIX) :]
    return code


def _infer_market(code6: str) -> str:
    """6 位代码 → sh/sz（北交所归 sz）"""
    if not code6:
        return "sz"
    head = code6[0]
    # 60/68/90 开头 → 沪市（60=主板，68=科创板，9=B 股）
    if head in ("6", "9"):
        return "sh"
    # 0/3/2/4 开头 → 深市（00/30=主板创业板，20=B 股，4/8=北交所）
    return "sz"


def _fetch_board_stocks(board_code: str, top_n: int) -> list[dict]:
    """从东财拉板块成分股（按涨跌幅降序）"""
    raw_code = _normalize_board_code(board_code)
    cache_key = f"stocks_{raw_code}"
    cached = _cached(cache_key)
    if cached is not None:
        _log(f"成分股 {raw_code}: 命中缓存, {len(cached)} 条")
        return cached[:top_n]

    # 板块 code 长这样：BK0420（东财）
    if not raw_code.upper().startswith("BK"):
        _log(f"成分股 {board_code}: 非板块 code（{raw_code}），跳过")
        return []

    # f:!2 排除 B 股；如需排除 ST 改 f:!50
    fs = f"b:{raw_code}+f:!2"
    params = {
        "pn": 1,
        "pz": max(top_n * 2, 50),
        "po": 1,
        "fid": "f3",
        "fs": fs,
        "fields": "f2,f3,f12,f14",
    }
    try:
        r = _session.get(EAST_MONEY_URL, params=params, timeout=8)
        if r.status_code != 200:
            _log(f"成分股 {raw_code}: HTTP {r.status_code}")
            return _serve_stale_stocks(cache_key, raw_code, top_n)
        payload = r.json()
        diff = (payload.get("data") or {}).get("diff") or {}
        if not diff:
            _log(f"成分股 {raw_code}: 数据为空")
            return _serve_stale_stocks(cache_key, raw_code, top_n)
    except Exception as e:
        _log(f"成分股 {raw_code}: 拉取失败 {e}")
        return _serve_stale_stocks(cache_key, raw_code, top_n)

    rows: list[dict] = []
    for item in diff.values():
        code6 = item.get("f12", "")
        rows.append(
            {
                # 6 位代码补 sh/sz 前缀，跟 data_source 协议对齐
                "code": f"{_infer_market(code6)}{code6}",
                "name": item.get("f14", ""),
                # f2 股价（×100 = 分）；f3 涨跌幅（×100）
                "price": round(item.get("f2", 0) / 100, 3),
                "change_pct": round(item.get("f3", 0) / 100, 2),
                "change_amt": 0,  # 该接口无涨跌额，前端兜底 0
                "turnover": 0,
                "pe": 0,
            }
        )
    rows.sort(key=lambda x: x["change_pct"], reverse=True)
    _log(f"成分股 {raw_code}: 刷新完成, {len(rows)} 只")
    _set_cache(cache_key, rows)
    return rows[:top_n]


def _serve_stale_stocks(cache_key: str, raw_code: str, top_n: int) -> list[dict]:
    """成分股拉取失败时兜底"""
    stale = _cached(cache_key, allow_stale=True)
    if stale is not None:
        _log(f"成分股 {raw_code}: 远端失败，回退 stale 缓存 ({len(stale)} 条)")
        return stale[:top_n]
    return []


def fetch_board_stocks(board_code: str, top_n: int = 20) -> list[dict]:
    """获取板块「成分股」TOP N（按涨跌幅降序）

    兼容：
    - 'bk_BK0420'（新板块 code）
    - 'BK0420'（裸板块 code）
    """
    return _fetch_board_stocks(board_code, top_n)


# ============== 调试 ==============


def clear_cache() -> None:
    """手动清缓存（调试用）"""
    _cache.clear()
