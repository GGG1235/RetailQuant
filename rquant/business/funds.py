"""
rquant.business.funds — 资金/仓位管理
- total_funds：总资金池（初始资金 + 充值 - 提现），买入/卖出不影响
- available_funds：可用资金（total_funds - 已投入成本）
- 充值：同步增加 total_funds 和 available_funds
- 提现：减少 available_funds（最多清零），同步减少 total_funds
- 仓位占比 = 持仓总市值 / total_funds
- 每个用户独立资金，数据存在用户目录的 funds.json
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .data import _load_json, _save_json
from .user import get_user_data_dir

DEFAULT_INITIAL_FUNDS = 1_000_000  # 默认初始资金 100 万


def _funds_file(user_id: str) -> Path:
    return get_user_data_dir(user_id) / "funds.json"


def _default_data() -> dict:
    return {
        "total_funds": DEFAULT_INITIAL_FUNDS,
        "available_funds": DEFAULT_INITIAL_FUNDS,
        "initial_funds": DEFAULT_INITIAL_FUNDS,
        "total_invested": 0.0,
        "realized_pnl": 0.0,
        "last_updated": datetime.now().isoformat(),
    }


def _load(user_id: str) -> dict:
    data = _load_json(_funds_file(user_id), {})
    if not data:
        return _default_data()
    # 补齐缺失字段（兼容老数据 + 部分写入场景）
    defaults = _default_data()
    for key, val in defaults.items():
        if key not in data:
            data[key] = val
    return data


def _save(user_id: str, data: dict) -> None:
    data["last_updated"] = datetime.now().isoformat()
    _save_json(_funds_file(user_id), data)


# ============== 查询 ==============


def get_funds_snapshot(user_id: str) -> dict:
    """返回用户资金快照"""
    return _load(user_id)


def get_total_funds(user_id: str) -> float:
    """总资金池（初始 + 充值 - 提现）"""
    return _load(user_id).get("total_funds", DEFAULT_INITIAL_FUNDS)


def get_available_funds(user_id: str) -> float:
    """可用资金（还可用于买入的金额）"""
    return _load(user_id).get("available_funds", DEFAULT_INITIAL_FUNDS)


def get_total_invested(user_id: str) -> float:
    """已投入资金总额（持仓成本总和）"""
    return _load(user_id).get("total_invested", 0.0)


# ============== 出入金 ==============


def set_initial_funds(user_id: str, amount: float) -> None:
    """设置初始资金（仅在首次或手动调整时调用）"""
    data = _load(user_id)
    data["total_funds"] = round(amount, 2)
    data["initial_funds"] = round(amount, 2)
    if data["total_invested"] == 0 and data["realized_pnl"] == 0:
        data["available_funds"] = round(amount, 2)
    _save(user_id, data)


def topup_funds(user_id: str, amount: float) -> dict:
    """充值：同步增加 total_funds 和 available_funds"""
    data = _load(user_id)
    data["total_funds"] = round(data["total_funds"] + amount, 2)
    data["available_funds"] = round(data["available_funds"] + amount, 2)
    _save(user_id, data)
    return {"total_funds": data["total_funds"], "available_funds": data["available_funds"]}


def withdraw_funds(user_id: str, amount: float) -> dict:
    """提现：减少 total_funds 和 available_funds。
    如果提现额超出可用资金，则清零可用资金，total_funds 只减可用资金部分。
    返回 {total_funds, available_funds, withdrawn}"""
    data = _load(user_id)
    actual = min(amount, data["available_funds"])
    data["available_funds"] = round(data["available_funds"] - actual, 2)
    data["total_funds"] = round(data["total_funds"] - actual, 2)
    _save(user_id, data)
    return {
        "total_funds": data["total_funds"],
        "available_funds": data["available_funds"],
        "withdrawn": round(actual, 2),
    }


def deduct_on_buy(user_id: str, cost: float) -> float:
    """买入时扣减可用资金，返回扣减后的可用资金"""
    data = _load(user_id)
    data["available_funds"] = round(data["available_funds"] - cost, 2)
    data["total_invested"] = round(data["total_invested"] + cost, 2)
    _save(user_id, data)
    return data["available_funds"]


def add_on_sell(user_id: str, proceeds: float, cost_released: float) -> float:
    """卖出时增加可用资金（释放成本 + 盈亏），返回更新后的可用资金"""
    data = _load(user_id)
    pnl = proceeds - cost_released
    data["available_funds"] = round(data["available_funds"] + proceeds, 2)
    data["total_invested"] = round(data["total_invested"] - cost_released, 2)
    data["realized_pnl"] = round(data["realized_pnl"] + pnl, 2)
    _save(user_id, data)
    return data["available_funds"]


# ============== 仓位计算 ==============


def calc_position_ratio(user_id: str, total_market_value: float) -> float:
    """仓位占比 = 持仓总市值 / total_funds × 100%"""
    total_funds = get_total_funds(user_id)
    if total_funds <= 0:
        return 0.0
    return round(total_market_value / total_funds * 100, 2)


def calc_total_assets(user_id: str, total_market_value: float) -> float:
    """总资产 = 可用资金 + 持仓市值"""
    avail = get_available_funds(user_id)
    return round(avail + total_market_value, 2)
