"""
rQuant.app — Flask Web（默认端口 8080）
- 看板：持仓 + 信号 + 曲线
- 操作：买 / 卖 / 加仓
- 不做多用户、不做密码、不做缓存层
- 启动：python3 app.py
- 自定义端口：RQUANT_PORT=5060 python3 app.py
"""

from __future__ import annotations
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, request, redirect, url_for, jsonify, flash

# 让同目录的模块可 import
sys.path.insert(0, str(Path(__file__).resolve().parent))

import data
import strategy
import portfolio as pf
import board
import squarify

app = Flask(__name__)
app.secret_key = "rquant-dev-key"  # 仅本地用

DEFAULT_PORT = int(os.environ.get("RQUANT_PORT", "8080"))


def _log(msg: str):
    """统一日志输出：带时间戳，写 stderr 确保 waitress 不吞"""
    ts = datetime.now().strftime("%H:%M:%S")
    sys.stderr.write(f"[{ts}] [app] {msg}\n")
    sys.stderr.flush()


def _safe_float(x, default=0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _safe_int(x, default=0) -> int:
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
    return {s["code"]: s["name"] for s in data.get_pool()}


# ============== 首页 ==============


@app.route("/")
def index():
    _log("首页被访问 —— 如果你看到这行，说明浏览器确实连接到了服务器")
    positions_raw = pf.get_positions()

    # 0. 预填充自选股行情（批量拉取，带 5 分钟缓存）
    watchlist_codes = data.get_watchlist_codes()
    data.populate_watchlist_info(watchlist_codes)

    # 1. 持仓（市值 / 盈亏）
    positions = []
    total_cost = 0.0
    total_market = 0.0
    for p in positions_raw:
        df = data.fetch_kline(p["code"], 70)
        current = float(df["close"].iloc[-1]) if not df.empty else p["avg_cost"]
        market_value = current * p["shares"]
        pnl = market_value - p["avg_cost"] * p["shares"]
        positions.append(
            {
                **p,
                "current_price": round(current, 2),
                "market_value": round(market_value, 2),
                "pnl": round(pnl, 2),
                "pnl_pct": round((current / p["avg_cost"] - 1) * 100, 2) if p["avg_cost"] > 0 else 0,
            }
        )
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
        buy_signals.extend(strategy.scan_stock(s["code"], s["name"], s["sector"], df))

    # 4. 交易历史 + 5. 自选股视图
    trades = sorted(pf.list_trades(), key=lambda x: x["datetime"], reverse=True)
    snapshots = sorted(pf.list_snapshots(), key=lambda x: x["date"])
    watchlist_stocks = _build_watchlist_view(watchlist_codes, positions_raw)

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
        watchlist_codes=watchlist_codes,
        watchlist_stocks=watchlist_stocks,
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
    name = _pool_name_map().get(code, code)
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
    pf.add_trade(
        "SELL",
        code,
        result.get("code", code),
        shares,
        price,
        note=f"盈亏 ¥{result['pnl']:+.2f}",
    )
    flash(
        f"🔴 已卖出 {code} {shares} 股 @ ¥{price}，盈亏 ¥{result['pnl']:+.2f}",
        "success",
    )
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
    total_market = 0.0
    for p in positions:
        df = data.fetch_kline(p["code"], 70)
        if not df.empty:
            total_market += float(df["close"].iloc[-1]) * p["shares"]
    pf.save_snapshot(positions, total_market, note="手动保存")
    return jsonify({"ok": True, "date": datetime.now().strftime("%Y-%m-%d")})


# ============== 板块行情 API ==============

# Treemap 画布尺寸（与前端 Canvas 宽高比一致）
TREEMAP_W, TREEMAP_H = 900, 500


def _compute_treemap(boards: list[dict]) -> list[dict]:
    """用 squarify 库计算 Treemap 矩形坐标，附加到每个板块上"""
    if not boards:
        return boards
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


@app.route("/api/boards")
def api_boards():
    """返回板块排行 JSON + Treemap 坐标"""
    board_type = request.args.get("type", "sector")
    _log(f"GET /api/boards?type={board_type}")
    try:
        if board_type == "concept":
            boards = board.fetch_concept_boards(30)
        else:
            boards = board.fetch_sector_boards(30)
        boards = _compute_treemap(boards)
        if not boards:
            _log(f"/api/boards: {board_type} 板块数据为空")
        else:
            _log(f"/api/boards: Treemap坐标已计算, {board_type} {len(boards)} 个板块")
        return jsonify({"type": board_type, "boards": boards, "count": len(boards)})
    except Exception as e:
        _log(f"/api/boards 异常: {e}")
        return jsonify({"type": board_type, "boards": [], "count": 0, "error": str(e)}), 500


@app.route("/api/board/<code>/stocks")
def api_board_stocks(code):
    """返回板块成分股 TOP 20（涨幅降序）"""
    _log(f"GET /api/board/{code}/stocks")
    try:
        stocks = board.fetch_board_stocks(code, 20)
        # 同步写入全局股票字典
        for s in stocks:
            data.upsert_stock(
                s["code"],
                name=s.get("name", ""),
                price=s.get("price", 0),
                change_pct=s.get("change_pct", 0),
                turnover=s.get("turnover", 0),
            )
        if not stocks:
            _log(f"/api/board/{code}/stocks: 成分股数据为空")
        else:
            _log(f"/api/board/{code}/stocks: 返回 {len(stocks)} 只股票")
        return jsonify({"code": code, "stocks": stocks, "count": len(stocks)})
    except Exception as e:
        _log(f"/api/board/{code}/stocks 异常: {e}")
        return jsonify({"code": code, "stocks": [], "count": 0, "error": str(e)}), 500


# ============== 自选股 API ==============


@app.route("/api/watchlist")
def api_watchlist():
    """返回当前自选股 code 列表"""
    codes = data.get_watchlist_codes()
    return jsonify({"codes": codes, "count": len(codes)})


@app.route("/api/watchlist/toggle", methods=["POST"])
def api_watchlist_toggle():
    """切换自选股状态：如果已在自选则移除，否则添加"""
    payload = request.get_json(silent=True) or {}
    code = (payload.get("code", "") or "").strip().lower()
    if not code:
        return jsonify({"ok": False, "error": "缺少 code"}), 400
    codes = data.get_watchlist_codes()
    if code in codes:
        data.remove_from_watchlist(code)
        _log(f"自选股 移除: {code}")
        return jsonify({"ok": True, "code": code, "in_watchlist": False, "action": "removed"})
    data.add_to_watchlist(code)
    # 优先用缓存；无缓存或过期则走数据源池拉取行情
    _ensure_stock_info(code)
    _log(f"自选股 添加: {code}")
    return jsonify({"ok": True, "code": code, "in_watchlist": True, "action": "added"})


def _ensure_stock_info(code: str) -> bool:
    """确保内存字典中有该股票的最新行情（缓存有效则跳过，否则走数据源池→K线兜底）。
    返回 True 表示命中了有效缓存。
    """
    cached = data.get_stock(code)
    cache_age = time.time() - cached.get("_updated_at", 0) if cached.get("_updated_at") else 9999
    if cache_age < 300 and cached.get("price"):
        return True

    name = cached.get("name", code)
    price = cached.get("price", 0)
    change_pct = cached.get("change_pct", 0)

    try:
        quote = pool.fetch_quote(code)
        if quote:
            name = quote.get("name", name)
            price = quote.get("price", price)
            change_pct = quote.get("change_pct", change_pct)
    except Exception:
        pass

    if not price:
        try:
            df = data.fetch_kline(code, 5)
            if not df.empty and len(df) >= 2:
                price = float(df["close"].iloc[-1])
                prev = float(df["close"].iloc[-2])
                if prev > 0:
                    change_pct = round((price - prev) / prev * 100, 2)
        except Exception:
            pass

    data.upsert_stock(code, name=name, price=price, change_pct=change_pct)
    return False


@app.route("/api/watchlist/stocks")
def api_watchlist_stocks():
    """返回自选股行情（从内存字典补全，含是否持仓判断）"""
    codes = data.get_watchlist_codes()
    data.populate_watchlist_info(codes)
    rows = _build_watchlist_view(codes, pf.get_positions())
    _log(f"自选股 行情 API: {len(rows)} 只")
    return jsonify({"stocks": rows, "count": len(rows)})


# ============== 自选股 添加（含行情拉取） ==============


@app.route("/api/watchlist/add_with_info", methods=["POST"])
def api_watchlist_add_with_info():
    """添加自选股并拉取最新行情（优先用缓存，超过5分钟则刷新）"""
    payload = request.get_json(silent=True) or {}
    code = (payload.get("code", "") or "").strip().lower()
    if not code:
        return jsonify({"ok": False, "error": "缺少 code"}), 400

    # 1. 检查内存缓存是否有效（5 分钟内）
    cached = data.get_stock(code)
    cache_age = time.time() - cached.get("_updated_at", 0) if cached.get("_updated_at") else 9999
    if cache_age < 300 and cached.get("price"):
        # 缓存有效，直接加入自选
        added = data.add_to_watchlist(code)
        return jsonify({
            "ok": True, "code": code, "added": added,
            "name": cached.get("name", code),
            "price": cached.get("price", 0),
            "change_pct": cached.get("change_pct", 0),
            "sector": cached.get("sector", ""),
            "from_cache": True,
        })

    # 2. 拉取最新行情
    name = cached.get("name", code)
    price = cached.get("price", 0)
    change_pct = cached.get("change_pct", 0)

    try:
        quote = pool.fetch_quote(code)
        if quote:
            name = quote.get("name", name)
            price = quote.get("price", price)
            change_pct = quote.get("change_pct", change_pct)
    except Exception:
        pass

    # 3. 如果行情拉不到，从 K 线提取
    if not price:
        try:
            df = data.fetch_kline(code, 5)
            if not df.empty and len(df) >= 2:
                price = float(df["close"].iloc[-1])
                prev = float(df["close"].iloc[-2])
                if prev > 0:
                    change_pct = round((price - prev) / prev * 100, 2)
        except Exception:
            pass

    # 4. 写入内存字典
    data.upsert_stock(code, name=name, price=price, change_pct=change_pct)

    # 5. 加入自选股
    added = data.add_to_watchlist(code)
    _log(f"自选股 添加(含行情): {code} name={name} price={price}")
    return jsonify({
        "ok": True, "code": code, "added": added,
        "name": name, "price": price,
        "change_pct": change_pct,
        "sector": cached.get("sector", ""),
        "from_cache": False,
    })


# ============== 自选股 策略分析 ==============


@app.route("/api/watchlist/analyze/<code>", methods=["POST"])
def api_watchlist_analyze(code):
    """对单只自选股运行策略分析，返回买卖信号"""
    code = code.strip().lower()

    # 1. 拉 K 线
    df = data.fetch_kline(code, 70)
    if df.empty or len(df) < 25:
        return jsonify({"ok": True, "code": code, "buy_signals": [], "sell_signal": None, "error": "K线数据不足"})

    # 2. 获取股票信息
    info = data.get_stock(code)
    name = info.get("name", code)
    sector = info.get("sector", "")

    # 3. 买入信号
    buy_signals = []
    for sig in strategy.scan_stock(code, name, sector, df):
        buy_signals.append({
            "code": sig.code, "name": sig.name, "sector": sig.sector,
            "strategy": sig.strategy, "current_price": sig.current_price,
            "suggested_buy": sig.suggested_buy, "stop_loss": sig.stop_loss,
            "take_profit": sig.take_profit, "reason": sig.reason,
            "confidence": sig.confidence,
        })

    # 4. 卖出信号（如果持仓）
    sell_signal = None
    positions = pf.get_positions()
    for p in positions:
        if p["code"] == code:
            sig = strategy.sell_signal(p, df)
            if sig:
                sell_signal = {**sig, "code": code, "name": p["name"]}
            break

    _log(f"自选股 分析: {code} buy={len(buy_signals)} sell={bool(sell_signal)}")
    return jsonify({"ok": True, "code": code, "buy_signals": buy_signals, "sell_signal": sell_signal})


# ============== 错误 ==============


@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, message="页面不存在"), 404


@app.errorhandler(500)
def server_error(e):
    return render_template("error.html", code=500, message=str(e)), 500


# ============== 启动 ==============

if __name__ == "__main__":
    print(
        f"rQuant 启动（双栈）：\n"
        f"  http://localhost:{DEFAULT_PORT}/\n"
        f"  http://127.0.0.1:{DEFAULT_PORT}/\n"
        f"  http://[::1]:{DEFAULT_PORT}/"
    )
    _log("日志系统已就绪，等待请求中…")
    try:
        from waitress import serve

        # 双 listen = IPv4 + IPv6 同时监听，避免 localhost 在 macOS 上解析到 ::1 时连不上
        serve(
            app,
            listen=[f"127.0.0.1:{DEFAULT_PORT}", f"[::1]:{DEFAULT_PORT}"],
            ident="rquant",
        )
    except ImportError:
        # Flask dev server 不支持双 listen，回退到单 host
        app.run(host="127.0.0.1", port=DEFAULT_PORT, debug=True)


# 运行时添加数据池引用（供 API 使用）
from datasources import pool