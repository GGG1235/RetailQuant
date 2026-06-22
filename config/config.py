"""
config — 全局配置读取

用法：
    from config import config

    port = config.server.port                    # 8080
    cache_dir = config.paths.cache_dir           # 字符串（需配合 config.project_root 使用）
    sina_url = config.data_source.sina.kline_url # URL 字符串

设计：
  - 单例：模块级 `config` 实例
  - 从项目根目录 config.toml 读取（tomllib，Python 3.11+ 内置）
  - 加载时校验所有必需配置项，缺失则报错退出
  - 支持环境变量覆盖（server.port → RQUANT_PORT）

"""

from __future__ import annotations

import copy
import os
import threading
import tomllib
from pathlib import Path
from typing import Any


# ============================================================
# 项目根目录 = config 目录的父目录
# ============================================================
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 默认配置文件路径
_DEFAULT_CONFIG_PATH = _PROJECT_ROOT / "config.toml"


# ============================================================
# 必需配置项 schema —— 每个 section 下必须包含的 key 集合。
# 新增/删除配置项时请同步更新此处和 config.toml 两端。
# _REQUIRED_SCHEMA 的 leaf value 为 set[str] 表示该 section 的必需 key；
# 为 dict 表示嵌套 section，递归校验。
# ============================================================
_REQUIRED_SCHEMA: dict[str, Any] = {
    "server": {"port", "secret_key"},
    "paths": {"cache_dir", "data_dir", "parquet_subdir"},
    "database": {"db_name", "eastmoney_db_name", "busy_timeout"},
    "data_source": {
        "sina": {"kline_url", "quote_url", "referer", "timeout", "unhealthy_cooldown"},
        "eastmoney": {"board_url", "board_fields"},
    },
    "cache": {"quote_ttl", "board_cache_ttl", "board_stale_ttl", "stale_days"},
    "message_queue": {"max_workers", "queue_size"},
    "business": {
        "default_initial_funds",
        "max_log_entries",
        "default_index_code",
        "watchlist_cache_seconds",
    },
    "treemap": {"width", "height"},
    "fetch_hist": {"max_datalen", "request_timeout", "inter_code_delay"},
}


# ============================================================
# Config 核心类
# ============================================================


class _ConfigNode:
    """嵌套属性访问节点：config.server.port"""

    def __init__(self, data: dict[str, Any]):
        for key, value in data.items():
            if isinstance(value, dict):
                value = _ConfigNode(value)
            object.__setattr__(self, key, value)

    def __getattr__(self, name: str) -> Any:
        raise AttributeError(f"配置项不存在: {name!r}")

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("Config 为只读，请修改 config.toml 文件")

    def __repr__(self) -> str:
        items = {k: v for k, v in self.__dict__.items() if not k.startswith("_")}
        return f"ConfigNode({items})"


class Config:
    """全局配置单例

    读取 config.toml，校验所有必需项，缺失则报错。
    支持环境变量覆盖（RQUANT_PORT）。
    """

    _instance: Config | None = None
    _lock = threading.Lock()

    # 各节由 _build_nodes 动态注入，注解仅用于静态类型检查
    server: _ConfigNode
    paths: _ConfigNode
    database: _ConfigNode
    data_source: _ConfigNode
    cache: _ConfigNode
    message_queue: _ConfigNode
    business: _ConfigNode
    treemap: _ConfigNode
    fetch_hist: _ConfigNode

    def __init__(self, config_path: Path | None = None):
        self._config_path = config_path or _DEFAULT_CONFIG_PATH
        self._raw: dict[str, Any] = {}
        self._reload()

    # ----- 单例 -----

    @classmethod
    def instance(cls, config_path: Path | None = None) -> Config:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(config_path)
        return cls._instance

    # ----- 内部 -----

    def _reload(self) -> None:
        """重新加载配置（从 config.toml 读取，校验必需项，最后应用环境变量）"""
        if not self._config_path.exists():
            raise FileNotFoundError(
                f"配置文件不存在: {self._config_path}\n请在项目根目录创建 config.toml（可参考 config.toml 示例）"
            )

        raw_text = self._config_path.read_text(encoding="utf-8")
        toml_data = tomllib.loads(raw_text)

        # 校验所有必需配置项
        missing = self._validate(_REQUIRED_SCHEMA, toml_data)
        if missing:
            msg = "config.toml 缺少以下必需配置项:\n" + "\n".join(f"  - {k}" for k in missing)
            raise KeyError(msg)

        self._raw = toml_data
        self._apply_env_overrides()
        self._build_nodes()

    @staticmethod
    def _validate(
        schema: dict[str, Any] | set[str],
        data: dict[str, Any],
        prefix: str = "",
    ) -> list[str]:
        """递归校验 data 是否包含 schema 中定义的所有 key。
        返回缺失 key 的路径列表（如 'data_source.sina.kline_url'），无缺失返回空列表。
        """
        missing: list[str] = []
        if isinstance(schema, set):
            # leaf：schema 是期望的 key 集合
            for key in schema:
                full_key = f"{prefix}.{key}" if prefix else key
                if key not in data:
                    missing.append(full_key)
        else:
            # branch：schema 是嵌套结构
            for key, sub_schema in schema.items():
                full_key = f"{prefix}.{key}" if prefix else key
                if key not in data:
                    missing.append(full_key)
                else:
                    missing.extend(Config._validate(sub_schema, data[key], full_key))
        return missing

    def _apply_env_overrides(self) -> None:
        """环境变量覆盖"""
        if os.environ.get("RQUANT_PORT"):
            try:
                self._raw["server"]["port"] = int(os.environ["RQUANT_PORT"])
            except ValueError:
                pass

    def _build_nodes(self) -> None:
        """将 _raw dict 转为嵌套 _ConfigNode 并挂到 self 上"""
        for key, value in self._raw.items():
            node = _ConfigNode(value)
            object.__setattr__(self, key, node)

    # ----- 实用方法 -----

    def as_dict(self) -> dict[str, Any]:
        """返回原始配置 dict（用于调试/序列化）"""
        return copy.deepcopy(self._raw)

    @property
    def project_root(self) -> Path:
        """返回项目根目录"""
        return _PROJECT_ROOT


# ============================================================
# 模块级单例：from config import config
# ============================================================

config = Config.instance()
