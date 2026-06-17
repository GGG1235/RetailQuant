"""
rquant.business.pool_store — 标的池管理（SQLite 持久化 + 内存热数据）
- 三类：stock（个股）/ etf（ETF）/ index（大盘指数）
- 启动时一次性 load 到内存（_pool_cache），后续读写全部走内存
- 写操作：内存更新 + 异步刷盘（用 mq）
- 兼容老 API：get_pool() 返回 [{code, name, sector}]
"""

from __future__ import annotations
import json
import time
from typing import Optional

from rquant.data_source import db

# ============== 默认池 ==============

# 预置默认池：5 个标的（与原 _DEFAULT_POOL 保持一致）
_DEFAULT_POOL: list[dict] = [
    {"code": "sh600460", "name": "士兰微", "sector": "半导体", "kind": "stock"},
    {"code": "sh600519", "name": "贵州茅台", "sector": "消费", "kind": "stock"},
    {"code": "sh601318", "name": "中国平安", "sector": "金融", "kind": "stock"},
    {"code": "sz000001", "name": "平安银行", "sector": "金融", "kind": "stock"},
    {"code": "sh600036", "name": "招商银行", "sector": "金融", "kind": "stock"},
]

# ============== 内存热数据 ==============


class _PoolCache:
    """内存中的标的池（启动时全量加载）"""

    def __init__(self):
        self.rows: list[dict] = []  # 全部
        self.by_code: dict[str, dict] = {}  # code → row
        self.loaded = False

    def load(self) -> None:
        rows = db.query_all("SELECT code, name, sector, kind, tags, enabled FROM pool ORDER BY kind, code")
        self.rows = [self._row_to_dict(r) for r in rows if r["enabled"]]
        self.by_code = {r["code"]: self._row_to_dict(r) for r in rows}
        self.loaded = True

    def reload(self) -> None:
        self.loaded = False
        self.load()

    def upsert(
        self,
        code: str,
        name: str,
        sector: str = "",
        kind: str = "stock",
        tags: list[str] | None = None,
        enabled: bool = True,
    ) -> None:
        now = time.time()
        tags_json = json.dumps(tags or [], ensure_ascii=False)
        db.execute(
            "INSERT INTO pool(code, name, sector, kind, tags, enabled, added_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(code) DO UPDATE SET "
            "name = excluded.name, sector = excluded.sector, kind = excluded.kind, "
            "tags = excluded.tags, enabled = excluded.enabled, updated_at = excluded.updated_at",
            (code, name, sector, kind, tags_json, 1 if enabled else 0, now, now),
        )
        # 同步内存
        row = {
            "code": code,
            "name": name,
            "sector": sector,
            "kind": kind,
            "tags": tags or [],
            "enabled": enabled,
        }
        self.by_code[code] = row
        # 更新 rows
        self.rows = [r for r in self.rows if r["code"] != code]
        if enabled:
            self.rows.append(row)

    def remove(self, code: str) -> None:
        db.execute("DELETE FROM pool WHERE code = ?", (code,))
        self.rows = [r for r in self.rows if r["code"] != code]
        self.by_code.pop(code, None)

    def set_enabled(self, code: str, enabled: bool) -> None:
        now = time.time()
        db.execute(
            "UPDATE pool SET enabled = ?, updated_at = ? WHERE code = ?",
            (1 if enabled else 0, now, code),
        )
        if code in self.by_code:
            self.by_code[code]["enabled"] = enabled
        if enabled and code in self.by_code:
            row = self.by_code[code]
            if not any(r["code"] == code for r in self.rows):
                self.rows.append(row)
        else:
            self.rows = [r for r in self.rows if r["code"] != code]

    @staticmethod
    def _row_to_dict(r) -> dict:
        tags_raw = r["tags"]
        try:
            tags = json.loads(tags_raw) if tags_raw else []
        except (TypeError, json.JSONDecodeError):
            tags = []
        return {
            "code": r["code"],
            "name": r["name"],
            "sector": r["sector"] or "",
            "kind": r["kind"] or "stock",
            "tags": tags,
            "enabled": bool(r["enabled"]),
        }


_pool = _PoolCache()


def _ensure_loaded() -> None:
    if not _pool.loaded:
        _pool.load()
        # 首次启动：如果 pool 表为空，注入默认池
        if not _pool.by_code:
            for item in _DEFAULT_POOL:
                _pool.upsert(**item)
            _pool.load()


# ============== 公开 API ==============


def get_pool(kind: Optional[str] = None, enabled_only: bool = True) -> list[dict]:
    """返回标的池列表（默认仅 enabled）

    kind: 过滤 "stock" / "etf" / "index"，None 表示全部
    """
    _ensure_loaded()
    rows = _pool.rows if enabled_only else list(_pool.by_code.values())
    if kind:
        rows = [r for r in rows if r["kind"] == kind]
    # 按 kind / code 排序，保持稳定
    rows.sort(key=lambda r: (r["kind"], r["code"]))
    return rows


def get_pool_codes(kind: Optional[str] = None, enabled_only: bool = True) -> list[str]:
    """返回标的池 code 列表"""
    return [r["code"] for r in get_pool(kind=kind, enabled_only=enabled_only)]


def get_by_code(code: str) -> Optional[dict]:
    """按 code 查池成员"""
    _ensure_loaded()
    return _pool.by_code.get(code)


def add_to_pool(code: str, name: str, sector: str = "", kind: str = "stock", tags: list[str] | None = None) -> None:
    """添加标的到池（同步刷盘 + 内存更新）"""
    _ensure_loaded()
    _pool.upsert(code, name, sector, kind, tags or [], enabled=True)


def remove_from_pool(code: str) -> None:
    """从池中移除"""
    _ensure_loaded()
    _pool.remove(code)


def enable_in_pool(code: str, enabled: bool = True) -> None:
    """启用 / 禁用池成员"""
    _ensure_loaded()
    _pool.set_enabled(code, enabled)


def reload_pool() -> None:
    """强制重载内存（手工 / 调试用）"""
    _pool.reload()


def pool_stats() -> dict:
    """标的池统计"""
    _ensure_loaded()
    by_kind: dict[str, int] = {}
    for r in _pool.by_code.values():
        by_kind[r["kind"]] = by_kind.get(r["kind"], 0) + 1
    return {
        "total": len(_pool.by_code),
        "enabled": len(_pool.rows),
        "by_kind": by_kind,
    }


# ============== 自选股（watchlist）==============
# 自选股是 pool 的子集：watchlist = {enabled + tag 包含 "watchlist"} ∪ 显式加入的
# 为了兼容老 API（get_watchlist_codes / add_to_watchlist / remove_from_watchlist），
# 这里用 meta 表 KV 存 code 列表，保持向后兼容。


def get_watchlist_codes() -> list[str]:
    """返回自选股 code 列表"""
    val = db.meta_get("watchlist")
    if not val:
        return []
    try:
        return list(json.loads(val))
    except (TypeError, json.JSONDecodeError):
        return []


def add_to_watchlist(code: str) -> bool:
    """添加 code 到自选股（持久化），返回是否真正新增"""
    codes = get_watchlist_codes()
    if code in codes:
        return False
    codes.append(code)
    db.meta_set("watchlist", json.dumps(codes, ensure_ascii=False))
    # 同步加入 pool（kind=stock，tag=watchlist）
    info = _pool.by_code.get(code)
    if info is None:
        _pool.upsert(code, name=code, sector="", kind="stock", tags=["watchlist"])
    elif "watchlist" not in info.get("tags", []):
        tags = list(info.get("tags", [])) + ["watchlist"]
        _pool.upsert(code, name=info["name"], sector=info["sector"], kind=info["kind"], tags=tags, enabled=True)
    return True


def remove_from_watchlist(code: str) -> bool:
    """从自选股移除（持久化），返回是否真正删除"""
    codes = get_watchlist_codes()
    if code not in codes:
        return False
    codes.remove(code)
    db.meta_set("watchlist", json.dumps(codes, ensure_ascii=False))
    return True
