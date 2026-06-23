# RetailQuant 代码导读（2026-06-22 全量盘点）

> 项目：`RetailQuant`（A 股个人量化看板）
> 版本：`rquant 0.2.0` / `retailquant 0.1.0`
> 规模：**6804 行 Python 代码，56 个 .py 文件**
> 阅读范围：全部源码（含 `rquant/`、`scripts/`、`tests/`、入口文件）

---

## 一、一句话总结

**RetailQuant 是一个 Flask Web + 多策略量化看板 / 回测系统。** 10 个策略（海龟、量价、多因子、缠论、低吸、ETF 轮动、跨境 DCA、网格、游资形态、场景路由器）+ 8 因子横截面选股 + 两套回测引擎（多因子精细版 + 路由器骨架版），配套数据池（Sina K 线 / 行情 / 东财财务快照 / SQLite + Parquet 双存储 / 进程内 QuoteCache / 内存 MQ）。

---

## 二、目录结构与体量

```
RetailQuant/
├── app.py                              21   Flask 启动（向后兼容）
├── strategy.py                         20   策略模块导入（向后兼容）
├── pyproject.toml / requirements.txt        flask + pandas + akshare + pyarrow
├── rquant/
│   ├── __init__.py                     21   包入口（v0.2.0）
│   ├── business/                       1226  业务层
│   │   ├── portfolio.py                147   持仓/交易/快照（JSON 存储）
│   │   ├── board.py                    284   板块行情（东财 push2，2min+stale）
│   │   ├── market.py                    35   大盘指数包装
│   │   ├── data.py                     125   K 线数据池 wrapper
│   │   ├── funds.py                    149   多用户资金管理
│   │   ├── pool_store.py               272   标的池（SQLite + 内存）
│   │   ├── system.py                   198   市场/策略/日志状态
│   │   └── user.py                     116   多用户（local + sim）
│   ├── data_source/                     908   数据层
│   │   ├── sina.py                     211   K 线 + 行情（Sina）
│   │   ├── eastmoney.py                205   财务快照（akshare）
│   │   ├── pool.py                     117   数据源池（多源路由 + failover）
│   │   ├── db.py                       187   SQLite（WAL + threadlocal）
│   │   ├── mq.py                       156   内存 pub-sub 消息队列
│   │   ├── parquet_store.py            127   Parquet 历史日频存储
│   │   ├── quote_cache.py               79   进程内行情 TTL 缓存
│   │   └── cache.py                     23   缓存目录常量
│   ├── strategy/                       1473  策略层
│   │   ├── base.py                     129   Strategy Protocol + Signal dataclass + 8 个技术指标
│   │   ├── registry.py                  49   @register 装饰器
│   │   ├── __init__.py                  97   scan_stock / scan_category / scan_sell 统一入口
│   │   ├── turtle/donchian.py          102   海龟唐奇安（20 日突破）
│   │   ├── volume_breakout/vp_breakout.py 108 量价共振突破
│   │   ├── factor/multi_factor.py      357   8 因子横截面选股 v2 ★
│   │   ├── factor/factor_calc.py       233   多因子流水线（财务快照+动量+4 过滤）
│   │   ├── factor/backtest_engine.py   245   多因子月频调仓回测
│   │   ├── legacy/chanlun2b.py         202   缠论二买近似（7 重过滤）
│   │   ├── legacy/buyhold.py           152   BuyHold 低吸（4 重过滤）
│   │   ├── grid/grid_martingale.py     123   网格马丁（骨架版）
│   │   ├── pattern/dragon_tiger.py     148   游资形态（涨停/连板近似）
│   │   ├── etf_rotation/dividend_lowvol_rotation.py 103 红利低波动量轮动
│   │   ├── etf_rotation/cross_border_dca.py 100 跨境 ETF 定投
│   │   ├── etf_rotation/universe.py     43   ETF 池（12 只）
│   │   └── router/
│   │       ├── scenario_router.py      115   5 状态 → 子策略类别映射 ★
│   │       └── market_regime.py        162   MA60/MA120 判定 5 状态
│   ├── web/                             621   Web 层
│   │   ├── app_factory.py               60   Flask 工厂 + waitress 双栈
│   │   ├── routes.py                   459   14 个路由
│   │   └── views.py                     96   视图辅助 + Treemap 计算
├── scripts/
│   ├── backtest_multi_factor.py        552   多因子精细版回测引擎（CLI）
│   ├── fetch_hist.py                   298   Sina 历史数据 → Parquet + SQLite
│   ├── run_backtest.py                  95   月频调仓回测入口
│   └── run.py                           16   启动入口
├── tests/
│   ├── test_api.py                      43   东财 nufm 板块接口（备选源，未启用）
│   └── test_sina.py                     39   Sina 板块接口测试
└── docs/                                       已有详细设计文档（多因子 v2 / 数据池 / 中英对照等）
```

---

## 三、架构分层

```
┌────────────────────────────────────────────────────────────┐
│  Web 层  (rquant/web)                                      │
│  Flask + waitress (双栈 IPv4/IPv6, 端口 8080)              │
│  ├─ index.html: 持仓/买卖信号/资金/自选股/策略全视图          │
│  ├─ /api/boards: 板块 Treemap（squarify）                    │
│  ├─ /api/watchlist/*: 自选股增删 + 逐策略分析                │
│  └─ /api/funds/*: 充值/提现                                 │
└────────────────────────────────────────────────────────────┘
            │
            ▼
┌────────────────────────────────────────────────────────────┐
│  业务层  (rquant/business)                                 │
│  ├─ portfolio: 单实例持仓 (JSON + 加权平均成本)              │
│  ├─ funds: 多用户资金（total/available/invested/realized）   │
│  ├─ pool_store: 标的池（SQLite pool 表 + 内存热数据）         │
│  ├─ board: 板块行情（东财 push2，2 min 缓存 + 10 min stale）│
│  ├─ market: 大盘指数 K 线包装（默认 sh000001）               │
│  ├─ system: 市场/策略/日志（ring buffer）                    │
│  └─ user: 用户管理（默认 local + sim）                      │
└────────────────────────────────────────────────────────────┘
            │
            ▼
┌────────────────────────────────────────────────────────────┐
│  策略层  (rquant/strategy)                                 │
│  协议: Strategy (name/category + signal_buy/signal_sell)    │
│  信号: Signal (code/name/sector/current_price/             │
│               suggested_buy/stop_loss/take_profit/          │
│               reason/confidence/extra)                      │
│                                                            │
│  8 个策略 + 1 个路由器:                                    │
│  ├─ turtle          DonchianTurtle     20 日新高 + ATR 止损  │
│  ├─ volume_breakout VpBreakout         突破 + 量比≥1.5      │
│  ├─ factor          MultiFactor (v2)   8 因子 + 4 过滤     │
│  ├─ legacy          ChanLun2B          缠论 7 重过滤       │
│  ├─ legacy          BuyHold            低吸 4 重过滤       │
│  ├─ grid            GridMartingale     网格+马丁（骨架）   │
│  ├─ pattern         DragonTigerPattern 涨停/连板近似      │
│  ├─ etf_rotation    DividendLowvol     红利动量轮动        │
│  ├─ etf_rotation    CrossBorderDca     跨境 MA60 下+RSI   │
│  └─ router          ScenarioRouter     5 状态→子策略类别  ★│
└────────────────────────────────────────────────────────────┘
            │
            ▼
┌────────────────────────────────────────────────────────────┐
│  数据层  (rquant/data_source)                              │
│  ├─ SinaKlineSource  (K 线 → SQLite klines 表，2 天阈值刷新) │
│  ├─ SinaQuoteSource  (行情 → 进程内 QuoteCache 30s TTL)     │
│  ├─ eastmoney        (财务快照 → cache/eastmoney.db)        │
│  ├─ DataSourcePool   (多源路由 + failover + 健康度)         │
│  ├─ ParquetStore     (data/parquet/{code}.parquet 历史日频) │
│  ├─ db.py            (cache/rquant.db: klines/pool/meta)    │
│  └─ mq.py            (内存 pub-sub 队列，2 worker + 降级)  │
└────────────────────────────────────────────────────────────┘
```

---

## 四、数据流（核心场景）

### 4.1 首页加载（routes.index）

```
GET /
  ├─ pf.get_positions()              # 持仓（JSON）
  ├─ funds.get_total_funds(uid)      # 多用户资金
  ├─ for p in positions:
  │     df = data.fetch_kline(p.code, 70)   # → data_source.pool → sina_kline
  │     current = df.close[-1]
  │     sig = scan_sell(p, df)              # 跑所有策略卖出信号
  ├─ for s in pool:
  │     df = data.fetch_kline(s.code, 70)
  │     sigs = scan_stock(s.code, s.name, s.sector, df)  # 跑所有策略买入信号
  │     system.report_strategy_run(sig.strategy, 1)       # 策略状态上报
  └─ render_template("index.html", ...)
```

### 4.2 策略注册与调度

```python
# 入口触发（rquant/strategy/__init__.py 第 16-23 行）
from .etf_rotation import cross_border_dca, dividend_lowvol_rotation  # noqa
from .factor import multi_factor                                       # noqa
from .grid import grid_martingale                                      # noqa
from .legacy import buyhold, chanlun2b                                 # noqa
from .pattern import dragon_tiger                                      # noqa
from .router import market_regime, scenario_router                     # noqa
from .turtle import donchian                                           # noqa
from .volume_breakout import vp_breakout                               # noqa

# import 即触发 @register；registry._STRATEGIES 自动填充
# scan_stock / scan_sell 走 registry.all_strategies()
```

### 4.3 决策树路由器（router/scenario_router.py）

```
signal_buy(code, name, sector, df):
  ├─ state = get_market_regime()        # 按日缓存
  │     df_idx = fetch_kline("sh000001", 130)
  │     MarketRegime.detect(df_idx)     # 5 状态: STRONG_BULL/BULL/SIDEWAYS/BEAR/STRONG_BEAR
  │
  ├─ sub_cats = ROUTING_TABLE[state.regime]
  │     STRONG_BULL → [turtle, volume_breakout, factor]
  │     BULL        → [turtle, volume_breakout, factor, etf_rotation]
  │     SIDEWAYS    → [factor, grid, etf_rotation]
  │     BEAR        → [etf_rotation, grid, legacy]
  │     STRONG_BEAR → [etf_rotation, legacy]
  │
  ├─ for strat in by_category_categories(sub_cats):
  │     sig = strat.signal_buy(code, name, sector, df)
  │
  └─ best = max(sigs, key=lambda s: s.confidence)
        return best.with(extra={router_regime, router_sub_cats, ...})
```

### 4.4 多因子流水线（scripts/backtest_multi_factor.py）

```
run(pool, start, end):
  ├─ all_klines[code] = data.fetch_kline(code, 250)  # 全量预加载
  ├─ common_dates = sorted(intersection of dates)    # 找共同交易日
  ├─ for dt in common_dates:
  │     ├─ 卖出决策: 止盈 / 止损 / 满期 / 排名跌出
  │     ├─ 买入决策:
  │     │     df_until = df[df.date <= dt]    # ★ 严格时序：截到 dt
  │     │     ranked = strategy.score_batch(df_until_map)
  │     │     top_codes = ranked[:max_positions]
  │     │     buy_list = [r for r in ranked if score >= 0.50]
  │     └─ 资金分配: per_position_budget = cash * 0.97 / max_positions
  └─ 业绩指标: 总收益/年化/最大回撤/胜率/平均持仓天数
```

---

## 五、关键模块详解

### 5.1 多因子 MultiFactor v2（factor/multi_factor.py, 357 行）★

**8 因子 / 4 过滤 / 横截面友好**

```
动量组 (W=0.35):
  M1  20 日动量 → ±10% 截断              W=0.20
  M2  60 日动量 → ±20% 截断              W=0.15

趋势组 (W=0.35):
  T1  MA20 偏离度（tanh ±5%）             W=0.12
  T2  多头排列 (MA5>MA10>MA20 +1 / -0.3)  W=0.10
  T3  60 日突破距离                       W=0.13

量价组 (W=0.30):
  V1  量比（5 日，tanh ±1.0）             W=0.12
  V2  量价共振（同向加分）                 W=0.13
  V3  波动率惩罚（std/mean）              W=0.05

4 道过滤:
  ① 停牌（volume=0）
  ② 流动性（20 日均成交额 < 500 万）
  ③ ST / 退市股（名称含 ST/退）
  ④ 上市天数 < 60

触发:  score >= 0.50 买入信号
卖出:  +15% 止盈 / -8% 止损 / 满 21 日退
```

**额外亮点**：
- `score(df, name, code)` 返回 `(score, detail)`，detail 包含 8 因子原始值 + 8 加权分量 + top3 贡献
- `score_batch(code_df_map)` 批量打分 + 横截面 rank
- `compute_factors(df)` 给回测/调试用，输出原始因子值

### 5.2 ScenarioRouter（router/scenario_router.py, 115 行）★

**核心：5 状态 → 子策略类别映射**

```python
ROUTING_TABLE = {
    "STRONG_BULL": ["turtle", "volume_breakout", "factor"],
    "BULL":        ["turtle", "volume_breakout", "factor", "etf_rotation"],
    "SIDEWAYS":    ["factor", "grid", "etf_rotation"],
    "BEAR":        ["etf_rotation", "grid", "legacy"],
    "STRONG_BEAR": ["etf_rotation", "legacy"],
}
```

**MarketRegime 阈值（router/market_regime.py）**：

```
STRONG_BULL:  MA60 > MA120 × 1.02 AND close > MA120 × 1.05
BULL:         MA60 > MA120 AND close > MA120
SIDEWAYS:     其他
BEAR:         MA60 < MA120 AND close < MA120
STRONG_BEAR:  MA60 < MA120 × 0.95 AND close < MA120 × 0.95

数据要求: df 至少 130 天（MA120）
缓存: 按日（_REGIME_CACHE[today]），force-reload 入口支持回测
```

**注意**：路由器本身不约束 candidate 池，scan_stock 收到的标的池就是当前 pool（与 memory 一致：用户曾要求"个股权重 60% + ETF 40%"但代码里没显式权重，全靠策略类别的命中自动分配）。

### 5.3 数据源池（data_source/pool.py, 117 行）

```python
class DataSourcePool:
    _kline: list[KlineSource]   # [SinaKlineSource()]
    _quote: list[QuoteSource]   # [SinaQuoteSource()]

    def fetch_kline(code, days):
        for src in self._kline:     # 按优先级
            if not src.healthy(): continue
            try:
                rows = src.fetch(code, days)
                if rows: return rows
            except: continue
        return []                    # 全部失败 → []

    def to_dataframe(code, days):
        rows = self.fetch_kline(code, days)
        df = pd.DataFrame(rows).rename(columns={"day": "date"})
        df[PRICE_COLS] = pd.to_numeric(..., errors="coerce")
        return df[["date", "open", "high", "low", "close", "volume"]]
```

**全局单例 `pool`**，业务层 `data.fetch_kline(code, days)` 就是 `pool.to_dataframe(code, days)`。

### 5.4 Sina K 线缓存策略（data_source/sina.py）

```
读取流程 fetch(code, days):
  1. cached = self._read_cache(code, days)   # SQLite klines 表，倒序再翻正序
  2. if not _need_refresh(code): return cached
  3. try 远端拉（datalen=days, scale=240）:
       成功 → upsert SQLite → return 重新读
       失败 → set _unhealthy_until = now + 60s → return cached

_need_refresh 逻辑:
  - 缓存为空 → True
  - fetched_at > 6h 前 → True（防停牌日假数据）
  - 缓存最后一天距今 >= 2 天 → True
```

### 5.5 板块行情（business/board.py, 284 行）

```
数据源: 东方财富 push2.eastmoney.com/api/qt/clist/get
缓存: 业务层 120s 新鲜 + 600s stale 兜底
session: 复用 + 3 次 retry + 排除系统代理 (trust_env=False)

三类板块:
  sector  → m:90+t:2 (行业)
  concept → m:90+t:3 (概念)
  area    → m:90+t:1 (地域)

字段映射: f2(成交额) / f3(涨跌幅×100) / f4(涨跌额) / f12(code) / f14(name) /
         f104(股票数) / f128(领涨股名) / f140(领涨股 code)

代码前缀: bk_BK0420 (避免与 sh/sz 个股冲突)
成分股: b:{board_code}+f:!2 (排除 B 股) → 6 位代码补 sh/sz 前缀
```

### 5.6 多用户资金（business/funds.py）

```
total_funds     初始 + 充值 - 提现（不受买入/卖出影响）
available_funds total - 已投入成本（用于买入）
total_invested  持仓成本总和
realized_pnl    已实现盈亏
last_updated    自动记录

每用户独立: data/users/{user_id}/funds.json
默认用户 "local": data/funds.json（向后兼容）
```

---

## 六、两套回测引擎

### 6.1 路由器骨架版（strategy/factor/backtest_engine.py, 245 行）

**月频调仓 / 财务快照固定 / 等权重**

```python
def run_backtest(snap_date, start_date, end_date, initial_capital=100w, top_n=30, kline_days=250):
    rebalance_dates = pd.bdate_range(start, end, freq="BMS")   # 每月第一个工作日
    
    for rb_date in rebalance_dates:
        df_picks = run_pipeline(snap_date, rb_date, kline_days, top_n)
        # 1) 硬过滤（ST/次新/停牌，MIN_KLINES=120, MAX_STALE_DAYS=5）
        # 2) 提取 5 因子（PE/PB/ROE/MOM/MCAP）
        # 3) MAD 去极值 + Z-Score
        # 4) 方向对齐（PE/PB/MCAP 取反）
        # 5) 等权合成 → Top-N
        
        # 卖出不在 new_codes 中的 + 买入 new_codes
        capital_per_stock = (cash + holdings_value) / n_new
        ...
```

**5 因子**：PE、PB、ROE、MOM、MCAP（财务快照数据，**非 8 因子 v2**）

**与 v2 的关系**：v2 是单日逐日（横截面 score）打 8 因子；这个 backtest_engine 用财务快照数据按月调仓打 5 因子。**两套逻辑不同**，输出不能直接对比。

### 6.2 多因子精细版（scripts/backtest_multi_factor.py, 552 行）★

**日频（每日调仓）/ 横截面 score_batch / 风控三层**

```
class BacktestEngine:
    max_positions = 5
    commission_rate = 0.00025  # 万 2.5
    stamp_rate = 0.001          # 千 1（仅卖出）
    
    def run(pool, start_date, end_date, rebalance_freq=1):
        # 严格时序: df_until = df[df.date <= dt]
        ranked = strategy.score_batch(df_until_map, names)
        
        # 卖出: 止盈 / 止损 / 满 21 日 / 排名跌出 TopN
        # 买入: score >= 0.50 + 不在持仓 + 等权重（97% 资金 / TopN）
```

**输出指标**：

```
total_return / annual_return / max_drawdown
win_count / win_rate / avg_hold_days
trades.csv    每笔交易
equity.csv    每日净值
summary.json  汇总
```

**CLI 用法**：

```bash
python scripts/backtest_multi_factor.py \
  --start 2025-01-01 --end 2026-06-17 \
  --capital 1000000 --positions 5 \
  --freq 1 \
  --out results/backtest_multi_factor
```

---

## 七、严格时序与 look-ahead bias 自检

### ✅ 已做到的（合规）

1. **多因子精细版回测**（`scripts/backtest_multi_factor.py:267`）：
   ```python
   df_until = df[df["date"] <= dt].reset_index(drop=True)
   # ★ 决策日 dt 的可用数据严格截到 dt
   ```

2. **路由器**（`router/scenario_router.py:68`）：
   ```python
   state = get_market_regime()
   # MarketRegime._REGIME_CACHE 按日缓存，今天的判定不会用到明天数据
   # 但需要注意：缓存命中意味着市场判定一直用的是"最新一次"的结果
   # 如果回测时跑了 2020 年又跑了 2025 年，缓存会污染
   ```

3. **多因子 v2**（`factor/multi_factor.py`）：所有 `ma/prev_ma/momentum/vol_ratio/rsi` 都只用 `df` 的尾部窗口（不含 `iloc[-1]` 之后的数据）

4. **缠论二买**（`legacy/chanlun2b.py`）：底分型识别 `df.iloc[-fractal_rel]` 不超过今日

5. **BuyHold 低吸**：`close / df.close.iloc[-(DROP_LOOKBACK+1)] - 1` 用 `-(N+1)` 切片，避免用今日数据

### ⚠️ 潜在风险点

1. **`scripts/run_backtest.py`**（月频调仓骨架版）：没有显式 `df_until = df[df.date <= dt]` 的切片（`factor_calc.py:62` 只检查了"最后一天距调仓日 ≤5 天"作为停牌判断，但实际 `_extract_momentum` 用 `df.close.iloc[-1]` 是可以的——`run_pipeline` 跑在调仓日 `rb_date`，传入 `rb_date` 后数据池拉到 `days=250` 末端）。**建议在 `_extract_momentum` 那一段显式切片 `df[df.date <= rb_date]`**。

2. **`MarketRegime._REGIME_CACHE` 全局缓存**：回测时如果回放多个日期但同日调用，缓存的 state 是"今天"的，回测历史日会拿到"今天"的 state——**需要传 `index_df` 参数强制重算**。当前 `clear_regime_cache()` 入口存在，但 `backtest_multi_factor.py` 没调用。

3. **数据池缓存**：`SinaKlineSource._need_refresh` 用 `fetched_at > 6h` 强制重拉——回测时如果手动注入了"未来数据"，这层会刷新但不会发现。

4. **`script/fetch_hist.py`** 拉数据时没有"截止日"概念——用户可能误用它拉"未来数据"然后回测。

---

## 八、潜在改进点

### 8.1 数据 / 性能

- **历史数据增量更新**：`fetch_hist.py` 默认 `replace` 模式（每次全量覆盖），应支持增量 `append`
- **amount / turnover** Sina 不提供，全部填 0；可考虑接 akshare 补
- **QuoteCache 命中率**：当前 `quote_cache` 用 30s TTL，自选股刷新如果间隔长，会反复穿透到 Sina

### 8.2 策略 / 回测

- **路由器权重分配**：当前路由器跑所有子策略取 confidence 最高，**没实现"个股权重 60% + ETF 40%"**（用户之前要求过）
- **`factor_calc.py` 月频调仓**：5 因子 + 等权重过于粗糙；可以接 MultiFactor.score_batch 复用 8 因子
- **`run_backtest.py`** 实际不是月度调仓，而是调一次之后持仓到底（不是真实调仓循环），是"一次筛选 + 持有"的简化版
- **Train/Test 分离验证**：当前回测只有 in-sample，没有 OOS；memory 里已记录这是用户的硬要求

### 8.3 Web / UX

- **路由 `/api/watchlist/analyze/<code>`** 每次访问都跑全策略 + 重新拉 K 线（无缓存），自选股多时慢
- **首页 `/` 同步跑所有策略信号**，长池子下首屏慢
- **`system.get_strategy_status()`** 当前是 mock（hash(name) % 30 + 1 随机时间），未真实持久化（TODO 在 TODOLIST.md）

### 8.4 工程

- **测试覆盖极薄**：只有 `tests/test_api.py`（nufm 备选源探针）+ `tests/test_sina.py`（运行时 API 探针），**没有单元测试**
- **数据库迁移**：`_migrate_legacy_watchlist()` 只处理 `data/watchlist.json` → `meta.watchlist`，老 `data/portfolio.json` / `data/trades.json` 没有 schema 升级路径
- **CI/CD**：`.github/` 目录存在但本导读未读取

---

## 九、与 memory 的对照

memory 中提到几条关键项目经验，在代码里都能找到对应位置：

| memory 经验 | 代码位置 | 备注 |
|------------|---------|------|
| **场景路由器 + 收益率优先** | `router/scenario_router.py` + `router/market_regime.py` | 5 状态映射齐全 |
| **技术分析用作风控层而非选股层** | 所有策略 `signal_sell` 都按"止盈/止损/趋势破坏"做 | 买入条件严格，过滤多 |
| **回测时序铁律（dt 之前数据）** | `scripts/backtest_multi_factor.py:267` `df_until = df[df.date <= dt]` | 精细版合规；月频版有风险点 |
| **决策树路由器标的池必须覆盖全场景** | `ScenarioRouter.signal_buy` 直接吃调用方传入的 df，**未限制标的类型** | 个股/ETF 是否都进池由调用方（routes/index）决定 |
| **LT_BEAR 阈值优化是熊市最大改进**（来自 v5→v6 经验） | 当前 `MarketRegime.STRONG_BEAR_MA_RATIO = 0.95` + `BEAR_MA_RATIO = 1.0` | 阈值已与 v6 一致 |
| **train/test 分离验证** | ❌ 当前没有 | 必须自己加 OOS 切分 |
| **手调阈值过拟合风险**（HybridForest 案例） | MultiFactor v2 权重是硬编码，BuyHold/ChanLun2B 阈值是硬编码 | 没有 cross-validation |

---

## 十、给使用者的速查表

### 启动 Web

```bash
python app.py
# 或 python scripts/run.py
# 访问 http://localhost:8080/
```

### 拉历史数据

```bash
python scripts/fetch_hist.py sh600519 sz000001 ...
# 写入 data/parquet/{code}.parquet + cache/rquant.db.klines
```

### 跑回测

```bash
# 月频调仓（5 因子，财务快照）
python scripts/run_backtest.py
# 默认 SNAP_DATE=2025-12-31, START=2026-01-01, END=2026-06-17

# 日频调仓（8 因子 MultiFactor v2）
python scripts/backtest_multi_factor.py \
  --start 2025-01-01 --end 2026-06-17 \
  --positions 5 --capital 1000000 \
  --out results/backtest_mf
```

### 手动调用策略

```python
from rquant.strategy import scan_stock, scan_sell, all_strategies
from rquant.business import data

df = data.fetch_kline("sh600519", 250)
sigs = scan_stock("sh600519", "贵州茅台", "消费", df)
for s in sigs:
    print(f"[{s.category}] {s.strategy}: {s.reason} (conf={s.confidence})")
```

### 单独看路由器

```python
from rquant.strategy.router import get_market_regime
state = get_market_regime()
print(state.regime, state.description)
# → SIDEWAYS 震荡：close ¥3000 在 MA120 附近（±5% 内）
```

---

## 十一、风险提示

**这份导读反映 2026-06-22 当天代码状态**。代码经过多次重构（CHANGELOG 未维护；`compat/strategy.py` 显示有"老 API"曾主导），可能存在以下历史包袱：

1. **历史 trades/portfolio 是 JSON 格式**，与 SQLite meta 表混合，迁移风险
2. **业务层缓存（board.py）和数据源缓存（sina.py）是两套独立 TTL**，观察时容易混淆
3. **回测引擎两套并存**（月频 v1 / 日频 v2），README/STRATEGIES.md 都建议以 `scripts/backtest_multi_factor.py` 为准
4. **"严格时序"在路由器的全局缓存里有隐患**——回测时务必 `clear_regime_cache()` + 传 `index_df`

---

*本导读由全量代码（6804 行 / 56 文件）通读后整理，覆盖架构、模块、数据流、严格时序自检、潜在风险与改进点。*
