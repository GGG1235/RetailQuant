"""
rQuant.strategies.etf_rotation.universe — ETF 池子（按策略类别）
- 跨境 ETF：纳指/标普/港股
- 红利低波：中证红利/红利低波/红利 ETF
- 添加新 ETF：直接 append 到对应 list
"""

from __future__ import annotations


# ============== 跨境 ETF（QDII）==============
# 注：跨境 ETF 有 T+0 / T+1 之分、有溢价折价问题
# 这里只列出主流流动性好的，作为定投标的池基线

CROSS_BORDER_ETFS: list[dict[str, str]] = [
    {"code": "sh513100", "name": "纳指ETF", "index": "纳斯达克100"},
    {"code": "sh513500", "name": "标普500", "index": "标普500"},
    {"code": "sh513550", "name": "港股通互联网", "index": "中证港股通互联网"},
    {"code": "sh513180", "name": "恒生科技", "index": "恒生科技"},
    {"code": "sh513130", "name": "恒生医疗", "index": "恒生医疗"},
    {"code": "sh513050", "name": "中概互联", "index": "中概互联50"},
]


# ============== 红利低波 ETF ==============
# 红利 + 低波动策略用，按股息率/波动率选基

DIVIDEND_LOWVOL_ETFS: list[dict[str, str]] = [
    {"code": "sh512890", "name": "红利低波100", "index": "中证红利低波100"},
    {"code": "sh510880", "name": "红利ETF", "index": "上证红利"},
    {"code": "sh515080", "name": "中证红利", "index": "中证红利"},
    {"code": "sh515180", "name": "红利100ETF", "index": "中证红利100"},
    {"code": "sh512040", "name": "价值100ETF", "index": "中证国信价值"},
    {"code": "sh515060", "name": "央企红利", "index": "央企红利"},
]


# ============== 通用工具 ==============


def all_rotation_etfs() -> list[dict[str, str]]:
    """全部轮动池子合并"""
    return list(CROSS_BORDER_ETFS) + list(DIVIDEND_LOWVOL_ETFS)
