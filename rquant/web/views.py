"""
rquant.web.views — 视图辅助函数
- _log / _safe_float / _safe_int
- _build_watchlist_view / _pool_name_map
- _compute_treemap
"""

from __future__ import annotations

from config import config
from rquant.business import data
from rquant.business.pool_store import get_pool
from rquant.log import info

# Treemap 画布尺寸（与前端 Canvas 宽高比一致）
TREEMAP_W, TREEMAP_H = config.treemap.width, config.treemap.height


def _log(msg: str):
    """统一日志输出（loguru 负责 stderr 输出 + 落盘 + ring buffer）"""
    info("app", msg)


def _safe_float(x, default: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _safe_int(x, default: int = 0) -> int:
    try:
        return int(x)
    except (TypeError, ValueError):
        return default


def _build_watchlist_view(codes: list[str], positions_raw: list[dict]) -> list[dict]:
    """把自选股 code 列表补全成前端可直接渲染的视图（含 is_held 标记）"""
    held_codes = {p["code"] for p in positions_raw}
    rows = []
    for code in codes:
        info = data.get_stock(code)
        price = info.get("price", 0)
        change_pct = info.get("change_pct", 0)
        rows.append(
            {
                "code": code,
                "name": info.get("name", code),
                "price": round(price, 2) if price else 0,
                "change_pct": round(change_pct, 2),
                "sector": info.get("sector", ""),
                "is_held": code in held_codes,
            }
        )
    return rows


def _pool_name_map() -> dict[str, str]:
    """code → name 的标的池查找表（用于买入选股时回填名称）"""
    return {s["code"]: s["name"] for s in get_pool()}


def _compute_treemap(boards: list[dict]) -> list[dict]:
    """用 squarify 库计算 Treemap 矩形坐标，附加到每个板块上"""
    if not boards:
        return boards
    import squarify

    values = [max(abs(b["change_pct"]), 0.3) for b in boards]
    normed = squarify.normalize_sizes(values, TREEMAP_W, TREEMAP_H)
    rects = squarify.squarify(normed, 0, 0, TREEMAP_W, TREEMAP_H)
    # squarify 按面积降序输出矩形；用 values 的排序映射回原始 boards 顺序
    indexed = sorted(enumerate(values), key=lambda x: -x[1])
    for rank, (orig_idx, _) in enumerate(indexed):
        r = rects[rank]
        boards[orig_idx]["x"] = r["x"]
        boards[orig_idx]["y"] = r["y"]
        boards[orig_idx]["w"] = r["dx"]
        boards[orig_idx]["h"] = r["dy"]
    return boards


# 策略大类 → 中文名（前端下拉框用）
CATEGORY_LABELS: dict[str, str] = {
    "volume_breakout": "📈 量价突破",
    "turtle": "🐢 海龟/唐奇安",
    "etf_rotation": "🔄 ETF 轮动",
    "factor": "📊 多因子选股",
    "grid": "🕸️ 网格/马丁",
    "pattern": "🐉 游资形态",
    "router": "🎯 场景路由器",
    "legacy": "🧬 老策略",
}
