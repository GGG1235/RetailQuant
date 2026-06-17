"""
rquant.data_source.sina — Sina 数据源实现
- SinaKlineSource: K 线 + SQLite 缓存（走 db.py）
- SinaQuoteSource: 实时行情 + 进程内 QuoteCache（30s TTL）
- 大盘指数复用 K 线源（sh000001 等）
"""

from __future__ import annotations
import re
import time
from datetime import datetime
from typing import Optional

from . import db
from .cache import (
    DEFAULT_TIMEOUT,
    SINA_HEADERS,
    SINA_KLINE_URL,
    SINA_QUOTE_URL,
    UNHEALTHY_COOLDOWN,
)
from .quote_cache import quote_cache


# ============== K 线源 ==============


class SinaKlineSource:
    """Sina K 线源 + SQLite 缓存"""

    name = "sina_kline"

    def __init__(self, timeout: int = DEFAULT_TIMEOUT):
        self.timeout = timeout
        self._unhealthy_until = 0.0

    # ----- 缓存读 -----

    def _read_cache(self, code: str, days: int) -> list[dict]:
        """从 SQLite 读最近 days 天的缓存"""
        rows = db.query_all(
            "SELECT date, open, high, low, close, volume FROM klines WHERE code = ? ORDER BY date DESC LIMIT ?",
            (code, days),
        )
        # 翻成正序（老→新），与原 JSON 行为一致
        return [
            {
                "day": r["date"],
                "open": r["open"],
                "high": r["high"],
                "low": r["low"],
                "close": r["close"],
                "volume": r["volume"],
            }
            for r in reversed(rows)
        ]

    def _last_date(self, code: str) -> Optional[str]:
        row = db.query_one(
            "SELECT date FROM klines WHERE code = ? ORDER BY date DESC LIMIT 1",
            (code,),
        )
        return row["date"] if row else None

    # ----- 缓存写 -----

    def _upsert(self, code: str, rows: list[dict]) -> None:
        """批量 UPSERT（INSERT OR REPLACE）"""
        now = time.time()
        seq = [
            (code, r.get("day"), r.get("open"), r.get("high"), r.get("low"), r.get("close"), r.get("volume"), now)
            for r in rows
            if r.get("day")
        ]
        db.executemany(
            "INSERT OR REPLACE INTO klines"
            "(code, date, open, high, low, close, volume, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            seq,
        )

    def _need_refresh(self, code: str) -> bool:
        """判断是否需要重新拉远端：缓存为空 / 最后一天距今 >= 2 个交易日"""
        last = self._last_date(code)
        if not last:
            return True
        try:
            last_dt = datetime.strptime(last, "%Y-%m-%d").date()
            # 取最后缓存日的"fetched_at"：超过 6 小时强制重拉（防停牌日 / 周末假数据）
            row = db.query_one(
                "SELECT fetched_at FROM klines WHERE code = ? AND date = ?",
                (code, last),
            )
            if row and (time.time() - row["fetched_at"]) > 6 * 3600:
                return True
            delta = (datetime.now().date() - last_dt).days
            # 2 天阈值：周末 / 节假日不浪费请求
            return delta >= 2
        except ValueError:
            return True

    # ----- 主入口 -----

    def fetch(self, code: str, days: int = 250) -> list[dict]:
        """拉 K 线 + SQLite 缓存。返回原始行（{day, open, high, low, close, volume}）。"""
        cached = self._read_cache(code, days)

        if not self._need_refresh(code):
            return cached

        try:
            url = f"{SINA_KLINE_URL}?symbol={code}&scale=240&ma=no&datalen={days}"
            r = __import__("requests").get(url, timeout=self.timeout)
            if r.status_code == 200 and r.text.strip():
                fresh = r.json()
                if isinstance(fresh, list) and fresh:
                    self._upsert(code, fresh)
                    self._unhealthy_until = 0.0
                    return self._read_cache(code, days)
        except Exception:
            self._unhealthy_until = time.time() + UNHEALTHY_COOLDOWN

        return cached

    def healthy(self) -> bool:
        return time.time() > self._unhealthy_until


# ============== 行情源 ==============


class SinaQuoteSource:
    """Sina 实时行情源 + QuoteCache（30s TTL）+ 击穿保护"""

    name = "sina_quote"

    def __init__(self, timeout: int = DEFAULT_TIMEOUT):
        self.timeout = timeout
        self._unhealthy_until = 0.0

    def fetch(self, code: str) -> Optional[dict]:
        return self.fetch_batch([code]).get(code)

    def fetch_batch(self, codes: list[str]) -> dict[str, dict]:
        """批量拉行情：先查 QuoteCache，miss 的再发请求（带击穿保护）"""
        if not codes:
            return {}

        result: dict[str, dict] = {}
        to_fetch: list[str] = []
        for c in codes:
            cached = quote_cache.get(c)
            if cached is not None:
                result[c] = cached
            else:
                to_fetch.append(c)

        if not to_fetch:
            return result

        # 击穿合并：去掉 inflight 的
        need_network: list[str] = []
        for c in to_fetch:
            if quote_cache.acquire_inflight(c):
                need_network.append(c)

        if not need_network:
            return result

        try:
            url = SINA_QUOTE_URL + ",".join(need_network)
            r = __import__("requests").get(url, headers=SINA_HEADERS, timeout=self.timeout)
            if r.status_code == 200:
                for c in need_network:
                    item = self._parse_line(c, r.text)
                    if item is not None:
                        quote_cache.put(c, item)
                        result[c] = item
                self._unhealthy_until = 0.0
        except Exception:
            self._unhealthy_until = time.time() + UNHEALTHY_COOLDOWN
        finally:
            for c in need_network:
                quote_cache.release_inflight(c)

        return result

    def _parse_line(self, code: str, text: str) -> Optional[dict]:
        m = re.search(rf'var hq_str_{code}="([^"]*)"', text)
        if not m:
            return None
        fields = m.group(1).split(",")
        if len(fields) < 4:
            return None
        try:
            prev_close = float(fields[2])
            current = float(fields[3])
        except (ValueError, IndexError):
            return None
        if prev_close <= 0:
            return None
        return {
            "code": code,
            "name": fields[0],
            "price": round(current, 3),
            "change_pct": round((current - prev_close) / prev_close * 100, 2),
            "change_amt": round(current - prev_close, 3),
        }

    def healthy(self) -> bool:
        return time.time() > self._unhealthy_until
