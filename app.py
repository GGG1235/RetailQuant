"""
rQuant.app — 阉割版 Flask Web（端口 5060）
- 看板：持仓 + 信号 + 曲线
- 操作：买 / 卖 / 加仓
- 不做多用户、不做密码、不做缓存层
"""
from __future__ import annotations
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from flask import Flask, render_template, request, redirect, url_for, jsonify, flash

# 让同目录的模块可 import
sys.path.insert(0, str(Path(__file__).resolve().parent))

import data
import strategy
import portfolio as pf

app = Flask(__name__)
app.secret_key = "rquant-dev-key"  # 仅本地用


def _safe_float(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _safe_int(x, default=0):
    try:
        return int(x)
    except (TypeError, ValueError):
        return default


# ============== 首页 ==============

@app.route("/")
def index():
    # 1. 持仓
    positions_raw = pf.get_positions()
    positions = []
    total_cost = 0
    total_market = 0
    for p in positions_raw:
        df = data.fetch_kline(p["code"], 70)
        current = float(df["close"].iloc[-1]) if not df.empty else p["avg_cost"]
        market_value = current * p["shares"]
        pnl = market_value - p["avg_cost"] * p["shares"]
        positions.append({
            **p,
            "current_price": round(current, 2),
            "market_value": round(market_value, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round((current / p["avg_cost"] - 1) * 100, 2) if p["avg_cost"] > 0 else 0,
        })
        total_cost += p["avg_cost"] * p["shares"]
        total_market += market_value
    total_pnl = total_market - total_cost
    total_pnl_pct = (total_market / total_cost - 1) * 100 if total_cost > 0 else 0

    # 2. 卖出信号
    sell_signals = []
    for p in positions:
        df = data.fetch_kline(p["code"], 70)
        sig = strategy.sell_signal(p, df)
        if sig:
            sell_signals.append({**sig, "code": p["code"], "name": p["name"]})

    # 3. 买入信号（扫整个池）
    buy_signals = []
    for s in data.get_pool():
        df = data.fetch_kline(s["code"], 70)
        sigs = strategy.scan_stock(s["code"], s["name"], s["sector"], df)
        for sig in sigs:
            buy_signals.append(sig)

    # 4. 快照
    snapshots = pf.list_snapshots()
    # 按日期排序
    snapshots.sort(key=lambda x: x["date"])

    # 5. 交易历史
    trades = sorted(pf.list_trades(), key=lambda x: x["datetime"], reverse=True)

    return render_template(
        "index.html",
        today=datetime.now().strftime("%Y-%m-%d"),
        positions=positions,
        total_cost=round(total_cost, 2),
        total_market=round(total_market, 2),
        total_pnl=round(total_pnl, 2),
        total_pnl_pct=round(total_pnl_pct, 2),
        sell_signals=sell_signals,
        buy_signals=buy_signals,
        snapshots=snapshots,
        trades=trades,
    )


# ============== 买入 ==============

@app.route("/position/add", methods=["POST"])
def add_position():
    code = request.form.get("code", "").strip().lower()
    shares = _safe_int(request.form.get("shares"), 0)
    price = _safe_float(request.form.get("price"), 0)
    if not code or shares <= 0 or price <= 0:
        flash("请填写完整：代码/股数/价格", "error")
        return redirect(url_for("index"))
    if shares % 100 != 0:
        flash("股数必须是 100 的整数倍", "error")
        return redirect(url_for("index"))
    # 找名字
    name = code
    for s in data.get_pool():
        if s["code"] == code:
            name = s["name"]
            break
    pf.add_position(code, name, shares, price)
    pf.add_trade("BUY", code, name, shares, price, note="手动买入")
    flash(f"✅ 已买入 {code} {shares} 股 @ ¥{price}", "success")
    return redirect(url_for("index"))


# ============== 卖出 ==============

@app.route("/position/sell/<code>", methods=["POST"])
def sell_position(code):
    shares = _safe_int(request.form.get("shares"), 0)
    price = _safe_float(request.form.get("price"), 0)
    if shares <= 0 or price <= 0:
        flash("请填写股数和价格", "error")
        return redirect(url_for("index"))
    try:
        result = pf.sell_position(code, shares, price)
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("index"))
    pf.add_trade("SELL", code, result.get("code", code), shares, price,
                 note=f"盈亏 ¥{result['pnl']:+.2f}")
    flash(f"🔴 已卖出 {code} {shares} 股 @ ¥{price}，盈亏 ¥{result['pnl']:+.2f}", "success")
    return redirect(url_for("index"))


# ============== 删除交易 ==============

@app.route("/trade/delete/<trade_id>", methods=["POST"])
def delete_trade(trade_id):
    pf.delete_trade(trade_id)
    flash(f"已删除交易 {trade_id}", "success")
    return redirect(url_for("index"))


# ============== 保存快照 ==============

@app.route("/api/snapshot", methods=["POST"])
def save_snapshot():
    positions = pf.get_positions()
    total_market = 0
    for p in positions:
        df = data.fetch_kline(p["code"], 70)
        if not df.empty:
            total_market += float(df["close"].iloc[-1]) * p["shares"]
    pf.save_snapshot(positions, total_market, note="手动保存")
    return jsonify({"ok": True, "date": datetime.now().strftime("%Y-%m-%d")})


# ============== 错误 ==============

@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, message="页面不存在"), 404


@app.errorhandler(500)
def server_error(e):
    return render_template("error.html", code=500, message=str(e)), 500


# ============== 启动 ==============

if __name__ == "__main__":
    port = int(os.environ.get("RQUANT_PORT", "5060"))
    print(f"🚀 rQuant 启动：http://localhost:{port}")
    try:
        from waitress import serve
        serve(app, host="0.0.0.0", port=port)
    except ImportError:
        app.run(host="0.0.0.0", port=port, debug=True)
