"""
rquant.data_source.pool — 数据源池
- KlineSource / QuoteSource Protocol
- DataSourcePool: 优先级路由 + 健康度跟踪 + 自动 failover
- 全局单例 `pool`
"""

from __future__ import annotations
from typing import Any, Optional, Protocol

import pandas as pd

from .cache import PRICE_COLS
from .sina import SinaKlineSource, SinaQuoteSource


# ============== 数据源协议 ==============


class KlineSource(Protocol):
    name: str

    def fetch(self, code: str, days: int) -> list[dict]: ...
    def healthy(self) -> bool: ...


class QuoteSource(Protocol):
    name: str

    def fetch(self, code: str) -> Optional[dict]: ...
    def fetch_batch(self, codes: list[str]) -> dict[str, dict]: ...
    def healthy(self) -> bool: ...


# ============== 数据源池 ==============


class DataSourcePool:
    """管理多个 K 线 / 行情源，按优先级和健康度路由，自动 failover"""

    def __init__(self):
        self._kline: list[KlineSource] = [SinaKlineSource()]
        self._quote: list[QuoteSource] = [SinaQuoteSource()]

    # ----- 注册源 -----

    def add_kline(self, source: KlineSource, priority: int = 0) -> None:
        """priority 越小越优先"""
        self._kline.insert(min(priority, len(self._kline)), source)

    def add_quote(self, source: QuoteSource, priority: int = 0) -> None:
        self._quote.insert(min(priority, len(self._quote)), source)

    # ----- K 线 -----

    def fetch_kline(self, code: str, days: int = 250) -> list[dict]:
        last_err: Optional[Exception] = None
        for src in self._kline:
            if not src.healthy():
                continue
            try:
                rows = src.fetch(code, days)
                if rows:
                    return rows
            except Exception as e:
                last_err = e
        if last_err:
            raise last_err
        return []

    def to_dataframe(self, code: str, days: int = 250) -> pd.DataFrame:
        """便捷：fetch_kline + 转 DataFrame（列：date, open, high, low, close, volume）"""
        rows = self.fetch_kline(code, days)
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows).rename(columns={"day": "date"})
        df[list(PRICE_COLS)] = df[list(PRICE_COLS)].apply(pd.to_numeric, errors="coerce")
        return df[["date", *PRICE_COLS]]

    # ----- 行情 -----

    def fetch_quote(self, code: str) -> Optional[dict]:
        for src in self._quote:
            if not src.healthy():
                continue
            try:
                item = src.fetch(code)
                if item is not None:
                    return item
            except Exception:
                continue
        return None

    def fetch_quotes(self, codes: list[str]) -> dict[str, dict]:
        """批量拉行情：走优先级最高的健康源"""
        for src in self._quote:
            if not src.healthy():
                continue
            try:
                result = src.fetch_batch(codes)
                if result:
                    return result
            except Exception:
                continue
        return {}

    # ----- 健康度面板 -----

    def status(self) -> dict[str, list[dict[str, Any]]]:
        return {
            "kline": [{"name": s.name, "healthy": s.healthy()} for s in self._kline],
            "quote": [{"name": s.name, "healthy": s.healthy()} for s in self._quote],
        }


# 全局单例
pool = DataSourcePool()
