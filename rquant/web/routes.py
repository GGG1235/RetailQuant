"""
rquant.web.routes — Flask 路由
- 首页 / 买 / 卖 / 删交易 / 快照 / 板块 / 自选股 / 资金 / 系统状态 / 错误
- 注册到 Flask app 工厂传入的 app
"""

from __future__ import annotations
from datetime import datetime

import pandas as pd
from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from rquant.business import board, data, funds, portfolio as pf, system, user as user_mgr
from rquant.strategy import all_strategies, scan_sell, scan_stock

from .views import (
    CATEGORY_LABELS,
    _build_watchlist_view,
    _compute_treemap,
    _log,
    _pool_name_map,
    _safe_float,
    _safe_int,
)


def register_routes(app: Flask) -> None:
    """把所有路由注册到 Flask app"""

    # ============== 首页 ==============

    @app.route("/")
    def index():
        _log("首页被访问 —— 如果你看到这行，说明浏览器确实连接到了服务器")
        positions_raw = pf.get_positions()
        pool_rows = data.get_pool()

        # 0. 一次性预加载所有需要的 K 线（持仓 + 标的池，去重）
        # 避免 sell_signals / buy_signals / positions 三处各自 fetch 同一只股票
        codes_needed: set[str] = {p["code"] for p in positions_raw} | {s["code"] for s in pool_rows}
        klines: dict[str, "pd.DataFrame"] = {}
        for code in codes_needed:
            try:
                klines[code] = data.fetch_kline(code, 70)
            except Exception as e:
                _log(f"K 线拉取失败 {code}: {e}")
                klines[code] = pd.DataFrame()  # type: ignore[name-defined]

        # 1. 持仓（市值 / 盈亏）
        positions = []
        total_cost = 0.0
        total_market = 0.0
        for p in positions_raw:
            df = klines.get(str(p["code"]), pd.DataFrame())
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

        # 资金/仓位（默认用户）
        uid = user_mgr.get_default_user().id
        total_funds_val = funds.get_total_funds(uid)
        avail_funds = funds.get_available_funds(uid)
        total_assets = funds.calc_total_assets(uid, total_market)
        pos_ratio = round(total_market / total_assets * 100, 2) if total_assets > 0 else 0.0
        invested = funds.get_funds_snapshot(uid).get("total_invested", 0)
        realized_pnl = funds.get_funds_snapshot(uid).get("realized_pnl", 0)

        # 2. 卖出信号
        sell_signals = []
        for p in positions:
            df = klines.get(str(p["code"]), pd.DataFrame())
            sig = scan_sell(p, df)
            if sig:
                sell_signals.append(
                    {
                        **sig,
                        "code": p["code"],
                        "name": p["name"],
                        "current_price": p.get("current_price", 0),
                        "avg_cost": p.get("avg_cost", 0),
                        "shares": p.get("shares", 0),
                    }
                )

        # 3. 买入信号（扫整个池）
        buy_signals: list[dict] = []
        # 按策略统计本轮触发的信号数（一次性上报 system，让策略状态表的 signals_today 有意义）
        from collections import Counter

        per_strategy_hits: Counter = Counter()

        for s in pool_rows:
            df = klines.get(str(s["code"]), pd.DataFrame())
            for sig in scan_stock(s["code"], s["name"], s["sector"], df):
                buy_signals.append(
                    {
                        "code": sig.code,
                        "name": sig.name,
                        "sector": sig.sector,
                        "strategy": sig.strategy,
                        "category": sig.category,
                        "current_price": sig.current_price,
                        "suggested_buy": sig.suggested_buy,
                        "stop_loss": sig.stop_loss,
                        "take_profit": sig.take_profit,
                        "reason": sig.reason,
                        "confidence": sig.confidence,
                    }
                )
                per_strategy_hits[sig.strategy] += 1
        # 把每个策略本轮的命中数上报到 system（signals_today 累加 + last_run 更新）
        for strat_name, hit_count in per_strategy_hits.items():
            system.report_strategy_run(strat_name, signal_count=hit_count)

        # 4. 交易历史 + 5. 自选股视图
        trades = sorted(pf.list_trades(), key=lambda x: x["datetime"], reverse=True)
        snapshots = sorted(pf.list_snapshots(), key=lambda x: x["date"])
        watchlist_codes = data.get_watchlist_codes()
        data.populate_watchlist_info(watchlist_codes)
        watchlist_stocks = _build_watchlist_view(watchlist_codes, positions_raw)

        # 6. 策略列表（按大类分组，前端下拉框用）
        strategies_by_category: dict[str, list[dict]] = {}
        for s in all_strategies():
            strategies_by_category.setdefault(s.category, []).append({"name": s.name, "description": s.description})
        category_options = [
            {"value": cat, "label": CATEGORY_LABELS.get(cat, cat)} for cat in sorted(strategies_by_category.keys())
        ]

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
            category_options=category_options,
            strategies_by_category=strategies_by_category,
            total_funds=total_funds_val,  # 模板用 total_funds
            total_funds_val=total_funds_val,
            avail_funds=avail_funds,
            available_funds=avail_funds,  # 模板用 available_funds（兼容老 key 名）
            total_assets=total_assets,
            pos_ratio=pos_ratio,
            position_ratio=pos_ratio,  # 模板用 position_ratio
            invested=invested,
            realized_pnl=realized_pnl,
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
        uid = user_mgr.get_default_user().id
        cost = round(shares * price, 2)
        available = funds.get_available_funds(uid)
        if cost > available:
            flash(f"可用资金不足：需要 ¥{cost:,.2f}，当前可用 ¥{available:,.2f}", "error")
            return redirect(url_for("index"))
        name = _pool_name_map().get(code, code)
        pf.add_position(code, name, shares, price)
        pf.add_trade("BUY", code, name, shares, price, note="手动买入")
        funds.deduct_on_buy(uid, cost)
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
        uid = user_mgr.get_default_user().id
        position = next((p for p in pf.get_positions() if p["code"] == code), None)
        if position is None:
            flash(f"未持有 {code}", "error")
            return redirect(url_for("index"))
        cost_released = round(position["avg_cost"] * shares, 2)
        position_name = position.get("name", code)
        try:
            result = pf.sell_position(code, shares, price)
        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("index"))
        proceeds = round(shares * price, 2)
        funds.add_on_sell(uid, proceeds, cost_released)
        pf.add_trade(
            "SELL",
            code,
            position_name,
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
            df = data.fetch_kline(str(p["code"]), 70)
            if not df.empty:
                total_market += float(df["close"].iloc[-1]) * p["shares"]
        pf.save_snapshot(positions, total_market, note="手动保存")
        return jsonify({"ok": True, "date": datetime.now().strftime("%Y-%m-%d")})

    # ============== 板块行情 API ==============

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
        info = data.get_stock(code)
        if info.get("name"):
            data.upsert_stock(code, name=info["name"])
        _log(f"自选股 添加: {code}")
        return jsonify({"ok": True, "code": code, "in_watchlist": True, "action": "added"})

    @app.route("/api/watchlist/stocks")
    def api_watchlist_stocks():
        """返回自选股行情（从内存字典补全，含是否持仓判断）"""
        codes = data.get_watchlist_codes()
        rows = _build_watchlist_view(codes, pf.get_positions())
        _log(f"自选股 行情 API: {len(rows)} 只")
        return jsonify({"stocks": rows, "count": len(rows)})

    @app.route("/api/watchlist/analyze/<code>")
    def api_watchlist_analyze(code):
        """逐个策略分析自选股，返回每个策略的评分/触发状态"""
        code = (code or "").strip().lower()
        if not code:
            return jsonify({"ok": False, "error": "缺少 code"}), 400

        info = data.get_stock(code)
        name = info.get("name") or code
        sector = info.get("sector") or ""
        df = data.fetch_kline(code, 160)
        if df.empty:
            return jsonify({"ok": False, "error": "暂无可分析的 K 线数据", "code": code}), 404

        analyses = []
        for strat in all_strategies():
            item = {
                "strategy": strat.name,
                "category": strat.category,
                "category_label": CATEGORY_LABELS.get(strat.category, strat.category),
                "description": strat.description,
                "triggered": False,
                "score": 0.0,
                "reason": "未触发买入条件",
                "suggested_buy": None,
                "stop_loss": None,
                "take_profit": None,
            }
            try:
                sig = strat.signal_buy(code, name, sector, df)
            except Exception as e:
                item["reason"] = f"分析异常：{e}"
                analyses.append(item)
                continue
            if sig is not None:
                item.update(
                    {
                        "triggered": True,
                        "score": sig.confidence,
                        "reason": sig.reason,
                        "suggested_buy": sig.suggested_buy,
                        "stop_loss": sig.stop_loss,
                        "take_profit": sig.take_profit,
                    }
                )
            analyses.append(item)

        analyses.sort(key=lambda x: (not x["triggered"], -x["score"], x["strategy"]))
        _log(f"自选股 分析: {code}，策略 {len(analyses)} 个")
        return jsonify(
            {
                "ok": True,
                "stock": {
                    "code": code,
                    "name": name,
                    "sector": sector,
                    "price": round(float(df["close"].iloc[-1]), 2),
                },
                "analyses": analyses,
            }
        )

    # ============== 错误 ==============

    @app.errorhandler(404)
    def not_found(e):
        return render_template("error.html", code=404, message="页面不存在"), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template("error.html", code=500, message=str(e)), 500

    # ============== 系统状态 API（参考图新增） ==============

    @app.route("/api/market_status")
    def api_market_status():
        """A 股市场状态（开/休/午休）"""
        return jsonify(system.get_market_status())

    @app.route("/api/strategy_status")
    def api_strategy_status():
        """所有策略的运行时状态（当前为 mock，详见 TODOLIST.md）"""
        return jsonify({"strategies": system.get_strategy_status()})

    @app.route("/api/system_log")
    def api_system_log():
        """系统日志（最近 50 条，从内存 ring buffer 读）"""
        return jsonify({"logs": system.get_system_log(limit=50)})

    @app.route("/api/funds/add", methods=["POST"])
    def api_funds_add():
        """手动充值：同步增加 total_funds 和 available_funds"""
        uid = user_mgr.get_default_user().id
        payload = request.get_json(silent=True) or {}
        amount = _safe_float(payload.get("amount"), 0)
        if amount <= 0:
            return jsonify({"ok": False, "error": "金额必须大于0"}), 400
        result = funds.topup_funds(uid, amount)
        _log(f"充值: +{amount:,.0f}，总资金 {result['total_funds']:,.0f}，可用 {result['available_funds']:,.0f}")
        return jsonify(
            {
                "ok": True,
                "added": round(amount, 2),
                "total_funds": round(result["total_funds"], 2),
                "available_funds": round(result["available_funds"], 2),
            }
        )

    @app.route("/api/funds/withdraw", methods=["POST"])
    def api_funds_withdraw():
        """提现：减少 total_funds 和 available_funds，最多清零可用资金"""
        uid = user_mgr.get_default_user().id
        payload = request.get_json(silent=True) or {}
        amount = _safe_float(payload.get("amount"), 0)
        if amount <= 0:
            return jsonify({"ok": False, "error": "金额必须大于0"}), 400
        result = funds.withdraw_funds(uid, amount)
        actual = result["withdrawn"]
        if actual < amount:
            _log(f"提现: 请求 {amount:,.0f}，实际 {actual:,.0f}（可用资金不足，已清零）")
        else:
            _log(f"提现: -{actual:,.0f}，总资金 {result['total_funds']:,.0f}，可用 {result['available_funds']:,.0f}")
        return jsonify(
            {
                "ok": True,
                "requested": round(amount, 2),
                "withdrawn": actual,
                "total_funds": round(result["total_funds"], 2),
                "available_funds": round(result["available_funds"], 2),
            }
        )
