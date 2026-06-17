"""
rquant.business.market — 大盘指数数据封装
- 默认用 sh000001（上证指数）作为大盘基准
- 路由器（scenario_router）通过这个模块拉指数 K 线
- 数据走 data_source 层
"""

from __future__ import annotations

import pandas as pd

from .data import fetch_kline

# 默认大盘指数代码
DEFAULT_INDEX_CODE = "sh000001"


def fetch_index_kline(code: str = DEFAULT_INDEX_CODE, days: int = 130) -> pd.DataFrame:
    """拉大盘指数 K 线

    路由器用这个判断市场状态（牛/熊/震荡）
    """
    return fetch_kline(code, days)


def get_index_name(code: str = DEFAULT_INDEX_CODE) -> str:
    """大盘指数名称（固定映射，避免每次拉数）"""
    name_map = {
        "sh000001": "上证指数",
        "sh000300": "沪深300",
        "sz399001": "深证成指",
        "sz399006": "创业板指",
        "sh000688": "科创50",
    }
    return name_map.get(code, code)
