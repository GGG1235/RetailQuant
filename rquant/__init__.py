"""
rquant — A 股个人量化看板
- business/    业务层（数据/板块/持仓/大盘）
- data_source/ 数据层（Sina + 数据池）
- strategy/    策略层（10 个策略 + 路由器）
- web/         Web 层（Flask）
- compat/      向后兼容层
"""

from . import business, compat, data_source, strategy, web

__version__ = "0.2.0"

__all__ = [
    "business",
    "compat",
    "data_source",
    "strategy",
    "web",
    "__version__",
]
