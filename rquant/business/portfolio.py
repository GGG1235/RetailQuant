"""
rquant.business.portfolio — 最简持仓管理（JSON 文件存储）
- 不分多用户（单实例）
- 不做 FIFO（直接加权平均）
- 交易记录 / 快照都用 JSON
"""

from __future__ import annotations
import uuid
from datetime import datetime
from pathlib import Path

from .data import _load_json, _save_json  # 复用统一 JSON 工具

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

PORTFOLIO_FILE = DATA_DIR / "portfolio.json"
TRADES_FILE = DATA_DIR / "trades.json"
SNAPSHOTS_FILE = DATA_DIR / "snapshots.json"


# ============== 持仓 ==============


def get_positions() -> list[dict]:
    """读取所有持仓（合并同 code）"""
    return _load_json(PORTFOLIO_FILE, [])


def add_position(code: str, name: str, shares: int, price: float) -> dict:
    """添加持仓（多次买入同 code 自动加权和）"""
    positions = get_positions()
    existing = next((p for p in positions if p["code"] == code), None)
    now = datetime.now().isoformat()
    if existing:
        total_cost = existing["avg_cost"] * existing["shares"] + price * shares
        total_shares = existing["shares"] + shares
        existing["avg_cost"] = round(total_cost / total_shares, 2)
        existing["shares"] = total_shares
        existing["updated_at"] = now
    else:
        positions.append(
            {
                "code": code,
                "name": name,
                "shares": shares,
                "avg_cost": round(price, 2),
                "created_at": now,
                "updated_at": now,
            }
        )
    _save_json(PORTFOLIO_FILE, positions)
    return next(p for p in positions if p["code"] == code)


def sell_position(code: str, shares: int, price: float) -> dict:
    """卖出：减仓或清仓"""
    positions = get_positions()
    existing = next((p for p in positions if p["code"] == code), None)
    if not existing:
        raise ValueError(f"未持有 {code}")
    if shares > existing["shares"]:
        raise ValueError(f"卖出股数 {shares} 超过持仓 {existing['shares']}")
    if shares < 100 or shares % 100 != 0:
        raise ValueError("卖出股数必须是 100 的整数倍")
    pnl = (price - existing["avg_cost"]) * shares
    existing["shares"] -= shares
    if existing["shares"] == 0:
        positions = [p for p in positions if p["code"] != code]
    _save_json(PORTFOLIO_FILE, positions)
    return {
        "code": code,
        "sold_shares": shares,
        "sold_price": price,
        "pnl": round(pnl, 2),
        "remaining": existing.get("shares", 0),
    }


# ============== 交易历史 ==============


def list_trades() -> list[dict]:
    return _load_json(TRADES_FILE, [])


def add_trade(side: str, code: str, name: str, shares: int, price: float, note: str = "") -> dict:
    trades = list_trades()
    now = datetime.now()
    trade = {
        "id": str(uuid.uuid4())[:8],
        "date": now.strftime("%Y-%m-%d"),
        "datetime": now.isoformat(),
        "side": side,
        "code": code,
        "name": name,
        "shares": shares,
        "price": round(price, 2),
        "note": note,
    }
    trades.append(trade)
    _save_json(TRADES_FILE, trades)
    return trade


def delete_trade(trade_id: str) -> None:
    trades = [t for t in list_trades() if t["id"] != trade_id]
    _save_json(TRADES_FILE, trades)


# ============== 快照 ==============


def list_snapshots() -> list[dict]:
    return _load_json(SNAPSHOTS_FILE, [])


def save_snapshot(positions: list[dict], total_market: float, note: str = "") -> None:
    snapshots = list_snapshots()
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    # 同一天只保留一条
    snapshots = [s for s in snapshots if s["date"] != today]
    snapshots.append(
        {
            "date": today,
            "datetime": now.isoformat(),
            "positions_count": len(positions),
            "total_market_value": round(total_market, 2),
            "note": note,
        }
    )
    _save_json(SNAPSHOTS_FILE, snapshots)
