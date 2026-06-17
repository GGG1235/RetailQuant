"""
rquant.data_source.quote_cache — 进程内行情 TTL 缓存
- 短窗口（默认 30s）内同 code 复用
- 击穿保护：inflight set 防同一 code 并发打到数据源
- 过期 lazy 删除（get 时检查）
- 线程安全（Lock）
"""

from __future__ import annotations
import threading
import time
from typing import Optional


class QuoteCache:
    """单实例进程内行情缓存"""

    def __init__(self, ttl: float = 30.0):
        self._ttl = ttl
        self._cache: dict[str, tuple[dict, float]] = {}
        self._inflight: set[str] = set()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._coalesced = 0  # 击穿合并次数

    def get(self, code: str) -> Optional[dict]:
        with self._lock:
            item = self._cache.get(code)
            if item is None:
                return None
            data, ts = item
            if time.time() - ts > self._ttl:
                self._cache.pop(code, None)
                return None
            self._hits += 1
            return data

    def put(self, code: str, data: dict) -> None:
        with self._lock:
            self._cache[code] = (data, time.time())
            self._misses += 1  # 统计：放进去时算一次 miss

    def acquire_inflight(self, code: str) -> bool:
        """尝试标记 code 为"正在拉取"。返回 True 表示需要实际去拉；False 表示别人在拉。"""
        with self._lock:
            if code in self._inflight:
                self._coalesced += 1
                return False
            self._inflight.add(code)
            return True

    def release_inflight(self, code: str) -> None:
        with self._lock:
            self._inflight.discard(code)

    def invalidate(self, code: str) -> None:
        with self._lock:
            self._cache.pop(code, None)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._inflight.clear()

    def stats(self) -> dict:
        with self._lock:
            return {
                "size": len(self._cache),
                "inflight": len(self._inflight),
                "hits": self._hits,
                "misses": self._misses,
                "coalesced": self._coalesced,
                "ttl": self._ttl,
            }


# 全局单例
quote_cache = QuoteCache(ttl=30.0)
