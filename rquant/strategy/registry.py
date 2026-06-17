"""
rQuant.strategies.registry — 策略注册中心
- @register 装饰器自动发现策略
- STRATEGIES: name -> Strategy 实例
- by_category: 按大类取策略
- 增删策略：只需在策略模块上 @register，导入即生效
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import Strategy


_STRATEGIES: dict[str, "Strategy"] = {}


def register(cls):
    """装饰器：把策略类实例注册到 STRATEGIES。name 必须唯一。"""
    instance = cls()
    if instance.name in _STRATEGIES:
        raise ValueError(f"策略名重复: {instance.name!r}")
    _STRATEGIES[instance.name] = instance
    return cls


def all_strategies() -> list["Strategy"]:
    """返回所有已注册策略实例"""
    return list(_STRATEGIES.values())


def by_category(category: str) -> list["Strategy"]:
    """按大类过滤"""
    return [s for s in _STRATEGIES.values() if s.category == category]


def get(name: str) -> "Strategy | None":
    """按 name 取单个策略"""
    return _STRATEGIES.get(name)


def categories() -> list[str]:
    """返回所有大类（去重）"""
    return sorted({s.category for s in _STRATEGIES.values()})


# 兼容老 import: `from strategies import STRATEGIES`
STRATEGIES = _STRATEGIES
