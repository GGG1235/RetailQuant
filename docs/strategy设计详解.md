# rquant/strategy/ 设计详解

> 面向 AI 维护者 | 2026-06-23 | 配合 `docs/大纲.md` 使用

---

## 1. 模块定位

`rquant/strategy/` 是 RetailQuant 的**核心逻辑层**——项目和其他看股票软件的唯一区别。它不碰 HTTP、不碰文件、不碰数据库。唯一外部依赖是 `pandas`（OHLC DataFrame）。

**职责边界：** 输入 K 线 → 输出信号。不管理仓位、不管理资金、不判断市场状态（市场状态由 router 子模块独立负责）。

**架构：** Protocol + 装饰器注册模式。`Strategy` 协议定义接口，`@register` 自动发现策略，`scan_*` 函数统一入口。

---

## 2. 公开接口总览

### 入口函数

| 函数 | 输入 | 输出 | 调用方 |
|------|------|------|--------|
| `scan_stock(code, name, sector, df)` | K线 DataFrame | `list[Signal]` | `routes.py:index()` |
| `scan_category(category, code, name, sector, df)` | K线 DataFrame + 大类名 | `list[Signal]` | ScenarioRouter |
| `scan_sell(position, df)` | 持仓 dict + K线 | `dict \| None` | `routes.py:index()` |
| `all_strategies()` | — | `list[Strategy]` | 查询/调试 |
| `by_category(category)` | 大类名 | `list[Strategy]` | ScenarioRouter |
| `get(name)` | 策略名 | `Strategy \| None` | 单策略调用 |

### 通用指标（`base.py`）

```python
ma(df, n)           # N 日 MA              prev_ma(df, n)      # 昨日 N 日 MA
highest(df, n)      # N 日最高             lowest(df, n)       # N 日最低
atr(df, n=14)       # ATR                  rsi(df, n=14)       # RSI
vol_ratio(df, n=5)  # 量比                 momentum(df, n=20)  # N 日动量
change_pct(df)      # 当日涨跌幅
```

---

## 3. Signal 数据结构

```python
@dataclass
class Signal:
    code: str                    # 股票代码
    name: str                    # 股票名称
    sector: str                  # 所属板块
    strategy: str                # 策略 ID（如 "DonchianTurtle"）
    category: str                # 大类（如 "turtle"）
    current_price: float         # 最新收盘价
    suggested_buy: float         # 建议买入价（+0.5% 容忍滑点）
    stop_loss: float             # 止损价
    take_profit: float           # 止盈价
    reason: str                  # 触发原因（人类可读）
    confidence: float            # 置信度 0-100
    market_state: str = "SIDEWAYS"
    extra: dict[str, Any] = field(default_factory=dict)  # 策略特有字段（原始指标、参数等）
```

**字段语义：**

- `suggested_buy` = `current_price × 1.005`，即比现价高 0.5%。允许小幅追高，不要求精确抄底。
- `stop_loss` / `take_profit` 的基数由各策略自行决定（一般为 `suggested_buy`）。
- `confidence` 是策略内置信度评分，范围 0-100，前端按此降序排列信号。
- `extra` 字典可存放策略专有数据，如 `router_regime`、`martingale_action`、因子的原始值等。

---

## 4. Strategy 协议

```python
class Strategy(Protocol):
    name: str           # 唯一 ID（如 "DonchianTurtle"）
    category: str       # 大类（如 "turtle"）
    description: str    # 一句话说明

    def signal_buy(self, code: str, name: str, sector: str,
                   df: pd.DataFrame) -> Signal | None: ...
    def signal_sell(self, position: dict[str, Any],
                    df: pd.DataFrame) -> dict[str, Any] | None: ...
```

所有策略必须实现 `signal_buy` 和 `signal_sell`。`df` 列名固定为 `date, open, high, low, close, volume`（全小写）。数据不足或条件不满足 → 返回 `None`。

---

## 5. 注册中心（`registry.py`）

```python
@register
class MyStrategy:
    name = "MyStrategy"
    category = "my_category"
    description = "..."

    def signal_buy(self, code, name, sector, df) -> Signal | None: ...
    def signal_sell(self, position, df) -> dict | None: ...
```

`@register` 在 import 时实例化策略类并按 `name` 注册到全局 `_STRATEGIES` 字典。`rquant/strategy/__init__.py` 导入各子模块即触发注册，无需显式调用。

---

## 6. 策略清单（8 大类 / 10 个策略）

| 大类 | 策略 | 模块 | 核心逻辑 |
|------|------|------|----------|
| `volume_breakout` | VpBreakout | `vp_breakout.py` | 突破 20 日新高 + 量比 ≥ 1.5 + 强势收盘 |
| `turtle` | DonchianTurtle | `donchian.py` | 20 日新高入场，10 日新低离场，2×ATR 止损 |
| `etf_rotation` | CrossBorderDca | `cross_border_dca.py` | 跨境 ETF：MA60 下方 + RSI<35 → 低位买入 |
| `etf_rotation` | DividendLowvolRotation | `dividend_lowvol_rotation.py` | 红利低波：20 日动量 + 放量确认 → 轮动持有 |
| `factor` | MultiFactor | `multi_factor.py` | 8 因子（动量×2+趋势×3+量价×3）+ 4 过滤 + 横截面排序 |
| `grid` | GridMartingale | `grid_martingale.py` | 20 日区间网格 + 马丁加仓预警 |
| `pattern` | DragonTigerPattern | `dragon_tiger.py` | 涨幅 ≥ 9.5% 近似涨停 + 连板识别 |
| `legacy` | ChanLun2B | `chanlun2b.py` | 底分型 + 多头排列 + 量能 + RSI 共 7 重过滤 |
| `legacy` | BuyHold | `buyhold.py` | 超跌 + 超卖 + 缩量 + 止跌共 6 重确认 |
| `router` | ScenarioRouter | `scenario_router.py` | 根据大盘 5 状态动态路由子策略组合 |

详细触发条件、信心度算法、参数参见 `STRATEGIES.md`。

---

## 7. 统一扫描入口

### scan_stock — 跑所有策略

```python
def scan_stock(code: str, name: str, sector: str, df: pd.DataFrame) -> list[Signal]:
    for strat in all_strategies():
        sig = strat.signal_buy(code, name, sector, df)
        if sig is not None:
            signals.append(sig)
    return signals
```

每个策略独立判断，互不排斥。同一只股票可能触发多个策略信号。

### scan_category — 按大类跑策略

```python
def scan_category(category: str, code, name, sector, df) -> list[Signal]:
    for strat in by_category(category):
        sig = strat.signal_buy(code, name, sector, df)
        ...
```

ScenarioRouter 用此函数按市场状态启用不同大类。

### scan_sell — 卖出信号

```python
def scan_sell(position: dict, df: pd.DataFrame) -> dict | None:
    for strat in all_strategies():
        sig = strat.signal_sell(position, df)
        if sig is not None:
            return {**sig, "strategy": strat.name, "category": strat.category}
    return None
```

**短路逻辑**：跑所有策略的 `signal_sell`，返回第一个非 `None` 的卖出信号。

**调用链：** `routes.py:index()` → 预加载所有 K 线 → 遍历持仓调 `scan_sell()` / 遍历标的池调 `scan_stock()` → 渲染前端。

---

## 8. 场景路由器（ScenarioRouter）

### 大盘状态识别

`market_regime.py` 基于上证指数 K 线（默认 `sh000001`）的 MA60/MA120/close 关系判定 5 种状态：

| 状态 | 条件 | 含义 |
|------|------|------|
| `STRONG_BULL` | MA60 > MA120×1.02 + close > MA120×1.05 | 强进攻 |
| `BULL` | MA60 > MA120 + close > MA120 | 进攻 |
| `SIDEWAYS` | 其他 | 震荡 |
| `BEAR` | MA60 < MA120 + close < MA120 | 防守 |
| `STRONG_BEAR` | MA60 < MA120×0.95 + close < MA120×0.95 | 极致防守 |

### 状态 → 子策略映射

| 状态 | 启用的子策略类别 |
|------|------------------|
| `STRONG_BULL` | turtle + volume_breakout + factor |
| `BULL` | turtle + volume_breakout + factor + etf_rotation |
| `SIDEWAYS` | factor + grid + etf_rotation |
| `BEAR` | etf_rotation + grid + legacy |
| `STRONG_BEAR` | etf_rotation + legacy |

### 缓存策略

- **实盘路径**：`get_market_regime()` 按"调用日的日期"缓存，当天状态稳定。
- **回测路径**：传 `index_df` 时按"数据最后日期"缓存；必须传 `use_cache=False` 避免污染实盘缓存。
- **回测入口**：`ScenarioRouter.signal_buy_at(code, name, sector, df, regime_state)` — 调用方传入已算好的 regime state。

---

## 9. 扩展指南

### 加一个新买入策略

```python
# 1. 创建 rquant/strategy/<category>/<name>.py
from ..base import Signal, ma
from ..registry import register

@register
class MyStrategy:
    name = "MyStrategy"
    category = "my_category"
    description = "..."

    MA_N = 20
    TAKE_PROFIT = 0.15
    STOP_LOSS = -0.07

    def signal_buy(self, code, name, sector, df) -> Signal | None:
        if df is None or len(df) < self.MA_N:
            return None
        close = float(df["close"].iloc[-1])
        # ... 你的判断逻辑 ...
        return Signal(
            code=code, name=name, sector=sector,
            strategy=self.name, category=self.category,
            current_price=close,
            suggested_buy=round(close * 1.005, 2),
            stop_loss=round(close * (1 + self.STOP_LOSS), 2),
            take_profit=round(close * (1 + self.TAKE_PROFIT), 2),
            reason="...", confidence=80.0, extra={},
        )

    def signal_sell(self, position, df) -> dict | None:
        # 卖出逻辑
        ...
```

```python
# 2. 在 rquant/strategy/<category>/__init__.py 加：
from . import my_strategy  # noqa: F401

# 3. 在 rquant/strategy/__init__.py 加：
from .my_category import my_strategy  # noqa: F401
```

**新策略 0 配置接入**——`@register` 自动发现，`scan_stock` 无需改动。

### 调整参数

策略参数是类属性，运行时可改：

```python
from rquant.strategy import get
get("DonchianTurtle").TAKE_PROFIT = 0.30
```

---

## 10. 设计约束 / 已知局限

| 约束 | 说明 |
|------|------|
| 单时间帧 | 策略基于日 K，不跨帧确认（GridMartingale 理想用分钟级） |
| 无复权处理 | 不处理除权除息（依赖数据源提供的复权价格） |
| 无仓位计算 | 信号只说买不买，仓位由回测引擎或前端决定 |
| 固定止损止盈 | 各策略硬编码止盈止损参数，无动态调整 |
| 财务因子缺失 | MultiFactor 当前仅技术因子，PE/PB/ROE 待财务数据源接入 |
| 涨停不可买 | DragonTigerPattern 用涨幅近似涨停，无法判断涨停板是否可买入 |
| 场景路由器依赖大盘 K 线 | 无指数数据时回退到 SIDEWAYS |
