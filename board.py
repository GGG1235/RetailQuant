"""
rQuant.board — 板块行情数据层
- 通过 Sina 行情 API 获取行业 ETF 实时数据
- 行业板块 / 概念板块均可覆盖
- 5 分钟内存缓存
"""
from __future__ import annotations
import re
import time
from datetime import datetime
from typing import List, Dict, Any, Optional

import requests

SINA_QUOTE_API = "https://hq.sinajs.cn/list="
SINA_HEADERS = {"Referer": "https://finance.sina.com.cn/"}

# ============== 行业 ETF 映射（板块名 → ETF 代码） ==============

INDUSTRY_ETFS: List[Dict[str, str]] = [
    {"code": "sh512480", "name": "半导体"},
    {"code": "sh512800", "name": "银行"},
    {"code": "sh512880", "name": "证券"},
    {"code": "sh512690", "name": "白酒"},
    {"code": "sz159928", "name": "消费"},
    {"code": "sh512010", "name": "医药"},
    {"code": "sh516160", "name": "新能源"},
    {"code": "sh515790", "name": "光伏"},
    {"code": "sh512660", "name": "军工"},
    {"code": "sh512200", "name": "房地产"},
    {"code": "sz159611", "name": "电力"},
    {"code": "sh515210", "name": "钢铁"},
    {"code": "sh512400", "name": "有色金属"},
    {"code": "sz159865", "name": "养殖"},
    {"code": "sh561230", "name": "化工"},
    {"code": "sh510050", "name": "上证50"},
    {"code": "sh510300", "name": "沪深300"},
    {"code": "sh510500", "name": "中证500"},
    {"code": "sh588000", "name": "科创50"},
    {"code": "sz159949", "name": "创业板50"},
    {"code": "sh515030", "name": "新能车"},
    {"code": "sh512170", "name": "医疗"},
    {"code": "sh561160", "name": "锂电池"},
    {"code": "sh515050", "name": "5G通信"},
    {"code": "sh516510", "name": "云计算"},
    {"code": "sh512100", "name": "中证1000"},
    {"code": "sz159766", "name": "旅游"},
    {"code": "sh516970", "name": "基建"},
    {"code": "sh516090", "name": "新材料"},
    {"code": "sh515880", "name": "通信"},
]

CONCEPT_ETFS: List[Dict[str, str]] = [
    {"code": "sh515030", "name": "新能车"},
    {"code": "sh561160", "name": "锂电池"},
    {"code": "sh515050", "name": "5G通信"},
    {"code": "sh516510", "name": "云计算"},
    {"code": "sh515790", "name": "光伏"},
    {"code": "sh516090", "name": "新材料"},
    {"code": "sh512480", "name": "半导体"},
    {"code": "sh516160", "name": "新能源"},
    {"code": "sz159766", "name": "旅游"},
    {"code": "sh512660", "name": "军工"},
    {"code": "sz159865", "name": "养殖"},
    {"code": "sh516970", "name": "基建"},
    {"code": "sh515210", "name": "钢铁"},
    {"code": "sh561230", "name": "化工"},
    {"code": "sh515880", "name": "通信"},
    {"code": "sh512170", "name": "医疗"},
    {"code": "sh512010", "name": "医药"},
    {"code": "sh512690", "name": "白酒"},
    {"code": "sz159928", "name": "消费"},
    {"code": "sh512200", "name": "房地产"},
    {"code": "sh512400", "name": "有色金属"},
    {"code": "sh512880", "name": "证券"},
    {"code": "sz159611", "name": "电力"},
    {"code": "sh512800", "name": "银行"},
    {"code": "sz159949", "name": "创业板50"},
    {"code": "sh588000", "name": "科创50"},
    {"code": "sh510050", "name": "上证50"},
    {"code": "sh510300", "name": "沪深300"},
    {"code": "sh510500", "name": "中证500"},
    {"code": "sh512100", "name": "中证1000"},
]

# ============== 缓存 ==============

_cache: Dict[str, tuple] = {}  # key → (data, timestamp)


def _log(msg: str):
    import sys
    ts = datetime.now().strftime("%H:%M:%S")
    sys.stderr.write(f"[{ts}] [board] {msg}\n")
    sys.stderr.flush()


def _cached(key: str, ttl: int = 300):
    if key in _cache:
        data, ts = _cache[key]
        if time.time() - ts < ttl:
            return data
    return None


def _set_cache(key: str, data: Any):
    _cache[key] = (data, time.time())


# ============== Sina 行情解析 ==============

def _fetch_etf_quotes(etf_list: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """批量拉取 ETF 实时行情（Sina API）"""
    codes = [e["code"] for e in etf_list]
    if not codes:
        return []

    url = SINA_QUOTE_API + ",".join(codes)
    try:
        r = requests.get(url, headers=SINA_HEADERS, timeout=8)
        if r.status_code != 200:
            _log(f"Sina ETF 行情请求失败: HTTP {r.status_code}")
            return []
    except Exception as e:
        _log(f"Sina ETF 行情异常: {e}")
        return []

    text = r.text
    results = []

    # 建立 code → name 映射
    name_map = {e["code"]: e["name"] for e in etf_list}

    for etf in etf_list:
        code = etf["code"]
        # 从返回文本中提取该 ETF 的数据行
        pattern = rf'var hq_str_{code}="([^"]*)"'
        m = re.search(pattern, text)
        if not m:
            _log(f"Sina ETF 未找到: {code}")
            continue
        fields = m.group(1).split(",")
        if len(fields) < 4:
            continue

        # Sina 字段: name, open, prev_close, current, high, low, ...
        try:
            prev_close = float(fields[2])
            current = float(fields[3])
        except (ValueError, IndexError):
            continue

        if prev_close <= 0:
            continue

        change_pct = round((current - prev_close) / prev_close * 100, 2)
        results.append({
            "code": code,
            "name": name_map.get(code, fields[0]),
            "price": round(current, 3),
            "change_pct": change_pct,
            "change_amt": round(current - prev_close, 3),
        })

    return results


# ============== 公开接口 ==============

def fetch_sector_boards(top_n: int = 30) -> List[Dict[str, Any]]:
    """获取行业板块排行（按涨幅降序）"""
    cache_key = "sector_all"
    cached = _cached(cache_key, ttl=120)  # 2 分钟缓存（盘中快速刷新）
    if cached is not None:
        _log(f"行业板块: 命中缓存, {len(cached)} 条")
        return cached[:top_n]

    data = _fetch_etf_quotes(INDUSTRY_ETFS)
    data.sort(key=lambda x: x["change_pct"], reverse=True)
    if not data:
        _log("行业板块: 返回空数据")
    else:
        _log(f"行业板块: 刷新完成, {len(data)} 只 ETF")
    _set_cache(cache_key, data)
    return data[:top_n]


def fetch_concept_boards(top_n: int = 30) -> List[Dict[str, Any]]:
    """获取概念板块排行（按涨幅降序）"""
    cache_key = "concept_all"
    cached = _cached(cache_key, ttl=120)
    if cached is not None:
        _log(f"概念板块: 命中缓存, {len(cached)} 条")
        return cached[:top_n]

    data = _fetch_etf_quotes(CONCEPT_ETFS)
    data.sort(key=lambda x: x["change_pct"], reverse=True)
    if not data:
        _log("概念板块: 返回空数据")
    else:
        _log(f"概念板块: 刷新完成, {len(data)} 只 ETF")
    _set_cache(cache_key, data)
    return data[:top_n]


def fetch_board_stocks(board_code: str, top_n: int = 20) -> List[Dict[str, Any]]:
    """获取板块「成分股」——返回该 ETF 自身的详情（Sina 方案下无真实成分股）"""
    cache_key = f"stocks_{board_code}"
    cached = _cached(cache_key, ttl=120)
    if cached is not None:
        return cached[:top_n]

    try:
        url = SINA_QUOTE_API + board_code
        r = requests.get(url, headers=SINA_HEADERS, timeout=8)
        if r.status_code != 200:
            _log(f"成分股 {board_code}: HTTP {r.status_code}")
            return []

        pattern = rf'var hq_str_{board_code}="([^"]*)"'
        m = re.search(pattern, r.text)
        if not m:
            return []

        fields = m.group(1).split(",")
        if len(fields) < 6:
            return []

        name = fields[0]
        prev_close = float(fields[2])
        current = float(fields[3])
        change_pct = round((current - prev_close) / prev_close * 100, 2)
        volume = fields[5] if len(fields) > 5 else "0"

        result = [{
            "code": board_code,
            "name": name,
            "price": round(current, 3),
            "change_pct": change_pct,
            "change_amt": round(current - prev_close, 3),
            "turnover": 0,
            "pe": 0,
        }]
        _set_cache(cache_key, result)
        return result[:top_n]
    except Exception as e:
        _log(f"成分股 {board_code}: 异常 {e}")
    return []
