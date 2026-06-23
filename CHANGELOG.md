# Changelog

> RetailQuant 项目变更日志
> 格式参考 [Keep a Changelog](https://keepachangelog.com/)

---

## [Unreleased] - 2026-06-22

### Fixed（修复）

#### 🔴 P0-1：首页 N+1 K 线查询（性能）

- **文件**：`rquant/web/routes.py`
- **问题**：`index()` 路由里持仓 / 卖出信号 / 买入信号三处循环各自调用 `data.fetch_kline(code, 70)`，N 只股票会拉 3N 次 K 线。
- **修复**：在视图入口一次性预加载（持仓 + 标的池 → 去重 → `code → DataFrame` 字典），三处循环复用同一份 DataFrame。
- **影响**：首页首屏 K 线拉取从 3N 降到 1 次；池子 ≥ 20 只时有感。

#### 🔴 P0-2：路由器全局缓存污染回测（正确性）

- **文件**：
  - `rquant/strategy/router/market_regime.py`
  - `rquant/strategy/router/scenario_router.py`
- **问题**：`get_market_regime()` 按"今天日期"缓存 MarketState。**回测时**整次回测都用"今天的 regime"，过去每个月的 BULL / BEAR / SIDEWAYS 被错误替换。
- **修复**：
  - `get_market_regime(index_df=None, use_cache=True)` 增加 `use_cache` 参数。
  - 缓存 key 改为"传入 index_df 的最后日期"而非"今天"，避免污染。
  - 新增 `ScenarioRouter.signal_buy_at(regime_state)` 回测入口，调用方传入已算好的 regime，回测场景必须配合 `use_cache=False`。
- **影响**：回测 OOS 验证可信赖；路由器接入精细版回测引擎时不需要再改 router 本身。

#### 🔴 P0-3：月频回测 look-ahead bias（正确性）

- **文件**：`rquant/strategy/factor/factor_calc.py`
- **问题**：`run_pipeline` 拉 K 线时用全量（默认 250 天 / datalen=5000），不按 `rebalance_date` 切片。调仓日 2025-06-01 算 20 日动量时，可能用到 2025-06-02 之后的收盘价。
- **修复**：`run_pipeline` 第 2 步拉完 K 线后立即按 `rebalance_date` 切片：

  ```python
  df = df[df["date"] <= rebalance_date].reset_index(drop=True)
  ```

- **影响**：月频回测数字会**下降**（之前偏乐观），修后才是真可实盘的数字。

### Verified

- ✅ 5 个相关模块静态 import 正常
- ✅ `get_market_regime(use_cache=False)` 不污染全局缓存
- ✅ 不同日期的 regime 互不串扰（cache 按数据日期 key）
- ✅ `ScenarioRouter.signal_buy_at` 返回 Signal 正常
- ✅ `run_pipeline` 端到端：200 行 K 线（故意含未来数据）→ 切片剩 92 行
- ✅ `ruff check` 无 warning

### Documentation

- 新增 `docs/code-walkthrough-2026-06-22.md`（全量代码导读）
- 新增 `docs/opt-2026-06-22.md`（优化建议 + patch）
- 新增 `CHANGELOG.md`（本文件）
- 同步 `STRATEGIES.md`、`docs/多因子选股回测系统.md`、`docs/大纲.md`、`docs/代码索引.md`

---

## 历史变更

变更日志自 2026-06-22 起维护。之前的版本演变请查阅 git log。
