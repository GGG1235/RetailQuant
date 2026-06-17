"""
rquant.data_source.db — SQLite 存储层
- 单一文件 cache/rquant.db
- 三张表：klines（K线）/ pool（标的池）/ meta（KV 元信息）
- threadlocal 连接：Flask/waitress 多线程安全
- WAL 模式：并发读 + 单写
"""

from __future__ import annotations
import sqlite3
import threading
import time
from typing import Any, Optional

from .cache import CACHE_DIR

DB_PATH = CACHE_DIR / "rquant.db"

# ----- 连接管理 -----

_local = threading.local()
_init_lock = threading.Lock()
_initialized = False


def _configure(conn: sqlite3.Connection) -> None:
    """每个连接的统一设置（行工厂 + 外键）"""
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # writer 端等待最多 5s，避免并发写冲突
    conn.execute("PRAGMA busy_timeout = 5000")


def get_conn() -> sqlite3.Connection:
    """取当前线程的连接（懒创建 + 自动建表）"""
    conn = getattr(_local, "conn", None)
    if conn is not None:
        try:
            conn.execute("SELECT 1")  # 健康检查
            return conn
        except sqlite3.ProgrammingError:
            _local.conn = None
            conn = None

    if not _initialized:
        _ensure_schema()

    conn = sqlite3.connect(
        DB_PATH,
        timeout=5.0,
        isolation_level=None,  # autocommit；显式 BEGIN/COMMIT
        check_same_thread=False,
    )
    _configure(conn)
    _local.conn = conn
    return conn


def close_thread_conn() -> None:
    """线程退出时关连接（daemon thread 不保证调用）"""
    conn = getattr(_local, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
        _local.conn = None


# ----- Schema -----

_SCHEMA_SQL = [
    # K 线
    """
    CREATE TABLE IF NOT EXISTS klines (
        code       TEXT    NOT NULL,
        date       TEXT    NOT NULL,
        open       REAL,
        high       REAL,
        low        REAL,
        close      REAL,
        volume     INTEGER,
        fetched_at REAL    NOT NULL,
        PRIMARY KEY (code, date)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_klines_code_date ON klines(code, date DESC)",
    # 标的池
    """
    CREATE TABLE IF NOT EXISTS pool (
        code       TEXT    PRIMARY KEY,
        name       TEXT    NOT NULL,
        sector     TEXT,
        kind       TEXT    NOT NULL DEFAULT 'stock',
        tags       TEXT,
        enabled    INTEGER NOT NULL DEFAULT 1,
        added_at   REAL    NOT NULL,
        updated_at REAL    NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_pool_kind ON pool(kind, enabled)",
    # 元信息
    """
    CREATE TABLE IF NOT EXISTS meta (
        key        TEXT PRIMARY KEY,
        value      TEXT,
        updated_at REAL NOT NULL
    )
    """,
]


def _ensure_schema() -> None:
    """全局只跑一次：建表 + WAL"""
    global _initialized
    with _init_lock:
        if _initialized:
            return
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        # 临时连接跑 PRAGMA WAL（持久生效）
        boot = sqlite3.connect(DB_PATH, timeout=5.0)
        try:
            boot.execute("PRAGMA journal_mode = WAL")
            boot.execute("PRAGMA synchronous = NORMAL")
            for sql in _SCHEMA_SQL:
                boot.execute(sql)
            boot.commit()
        finally:
            boot.close()
        _initialized = True


# ----- 通用工具 -----


def execute(sql: str, params: tuple = ()) -> None:
    """单条写入（autocommit）"""
    conn = get_conn()
    conn.execute(sql, params)


def executemany(sql: str, seq: list[tuple]) -> None:
    """批量写入"""
    if not seq:
        return
    conn = get_conn()
    conn.execute("BEGIN")
    try:
        conn.executemany(sql, seq)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def query_one(sql: str, params: tuple = ()) -> Optional[sqlite3.Row]:
    conn = get_conn()
    return conn.execute(sql, params).fetchone()


def query_all(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    conn = get_conn()
    return conn.execute(sql, params).fetchall()


def meta_get(key: str, default: Any = None) -> Any:
    row = query_one("SELECT value FROM meta WHERE key = ?", (key,))
    if row is None:
        return default
    val = row["value"]
    # 尝试还原 bool/int
    if val in ("true", "false"):
        return val == "true"
    try:
        if val.isdigit() or (val.startswith("-") and val[1:].isdigit()):
            return int(val)
        return float(val) if "." in val else val
    except (AttributeError, ValueError):
        return val


def meta_set(key: str, value: Any) -> None:
    execute(
        "INSERT INTO meta(key, value, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
        (key, str(value), time.time()),
    )
