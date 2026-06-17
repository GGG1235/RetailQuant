# strategy.py 设计详解

> 面向 AI 维护者 | 2026-06-17 | 配合 `大纲.md` 使用

---

## 1. 模块定位

`strategy.py` 是 RetailQuant 的**核心逻辑层**——项目和其他看股票软件的唯一区别。它不碰 HTTP、不碰文件、不碰数据库。唯一外部依赖是 `pandas`（OHLC DataFrame）。

**职责边界：** 输入 K 线 → 输出信号。不管理仓位、不管理资金、不判断市场状态。

---

## 2. 公开接口总览

| 函数 | 输入 | 输出 | 调用方 |
|------|------|------|--------|
| `chanlun2b_signal(code, name, sector, df)` | K线 DataFrame | `Signal \| None` | `scan_stock()` |
| `buyhold_signal(code, name, sector, df)` | K线 DataFrame | `Signal \| None` | `scan_stock()` |
| `scan_stock(code, name, sector, df)` | K线 DataFrame | `list[Signal]` | `app.py:index()` |
| `sell_signal(position, df)` | 持仓 dict + K线 | `dict \| None` | `app.py:index()` |

**约定：**
- `df` 必须有列 `close`（小写），至少 N 根 K 线。数据不足 → 返回 `None`。
- 所有价格单位：人民币元。
- `code` 格式：`sh600519`（小写）。

---

## 3. Signal 数据结构

```python
@dataclass
class Signal:
    code: str           # 股票代码
    name: str           # 股票名称
    sector: str         # 所属板块（如 "半导体"）
    strategy: str       # 策略名 "ChanLun2B" | "BuyHold"
    current_price: float       # 最新收盘价
    suggested_buy: float       # 建议买入价（含 0.5% 安全垫）
    stop_loss: float           # 止损价
    take_profit: float         # 止盈价
    reason: str                # 触发原因（人类可读）
    confidence: float          # 置信度 0-100
    market_state: str = "SIDEWAYS"  # 预留字段，当前未使用
```

**字段语义：**
- `suggested_buy` = `current_price × 1.005`，即比现价高 0.5%。设计意图：允许小幅追高，不要求精确抄底。
- `stop_loss` / `take_profit` 的计算基数不同：缠论以 `suggested_buy` 为基，BuyHold 以 `current_price` 为基。因为前者是追涨信号买入价更可能成交在 suggested_buy，后者是低吸信号可能在 current_price 附近成交。
- `confidence` 不是概率，是设计者的主观权重。用于前端排序或过滤（当前未用）。
- `market_state` 目前固定 `"SIDEWAYS"`，是为未来市场环境判断预留的槽位。

---

## 4. 策略一：缠论 2B 近似（chanlun2b_signal）

### 4.1 策略逻辑

缠论原版的"第二类买点"（2B）定义：下跌趋势结束后的第一次回调不破前低。当前实现是**最简近似**——只用均线关系拟合，不做分型/笔/线段。

**触发条件（三个同时满足）：**

```
① close > MA5        （收盘价站在 5 日均线上方）
② MA5 > MA20         （短期均线在中期均线上方——多头排列确认）
③ prev_close < prev_MA5  （昨日收盘在昨日 MA5 下方——确认今日是「上穿」日）
```

条件③是关键：防止连续多日站上 MA5 后的重复信号。只取"刚站上"的那一天。

### 4.2 参数

| 参数 | 值 | 原理 |
|------|----|------|
| 最短数据要求 | 25 根 K 线 | MA20 至少需要 20 根 + 前日 MA5 需要 5 根缓冲 |
| MA 窗口 | 5 / 20 | 缠论常用周期（1周 / 1月） |
| 建议买入价 | `close × 1.005` | +0.5% 安全垫 |
| 止损 | `suggested_buy × 0.93` | -7%，基于买入价 |
| 止盈 | `suggested_buy × 1.15` | +15%，基于买入价 |
| 置信度 | 80 | 主观：均线上穿是较强的趋势确认信号 |

### 4.3 边界情况

- `df` 为 `None` 或长度 < 25 → 返回 `None`
- 满足条件但 MA5 和 MA20 几乎相等 → 仍然触发（不做差值阈值过滤）
- 多日连续满足时只第一天触发（条件③自动过滤后续日）

---

## 5. 策略二：Buy & Hold 低吸（buyhold_signal）

### 5.1 策略逻辑

最简化的长线持有策略。不判断趋势方向，只做一件事：**价格比长期均线便宜时提醒买入**。

**触发条件：**

```
close < MA60 × 0.95
```

即现价低于 60 日均线的 95%。相当于"打折 5% 以上"的低位区域。

### 5.2 参数

| 参数 | 值 | 原理 |
|------|----|------|
| 最短数据要求 | 60 根 K 线 | MA60 恰好需要 60 根 |
| MA 窗口 | 60 | 季度线（约 3 个月） |
| 触发折扣 | 0.95 | 低于均线 5% 才触发，避免轻微波动频繁信号 |
| 建议买入价 | `close × 1.005` | +0.5% 安全垫 |
| 止损 | `close × 0.90` | -10%，基于现价 |
| 止盈 | `close × 1.20` | +20%，基于现价 |
| 置信度 | 60 | 主观：纯估值信号，无趋势确认，可靠性低于缠论 |

### 5.3 设计意图

BuyHold 和缠论 2B 是互补关系：
- 缠论抓**趋势启动**（追涨）
- BuyHold 抓**超跌区域**（低吸）

两者独立判断，不做互斥——同一只股票可能同时触发两个信号。

---

## 6. 信号汇聚：scan_stock()

```python
def scan_stock(code, name, sector, df) -> list[Signal]:
    # 对单只股票跑所有买入策略，收集全部命中的 Signal
```

**设计意图：** 扩展新策略时只需要在这里加一行调用，不需要改 `app.py`。

当前逻辑：依次调 `chanlun2b_signal` 和 `buyhold_signal`，收集非 `None` 的结果。两个策略都对同一根 DataFrame 做判断，并行不互斥。

**调用链：** `app.py:index()` → `data.get_pool()` 遍历 → 每只股票 `data.fetch_kline()` → `strategy.scan_stock()` → 前端渲染买入信号列表。

---

## 7. 卖出信号：sell_signal()

### 7.1 不同于买入信号

`sell_signal` 的输入和输出类型与买入函数不同：
- **输入：** `position` 是持仓字典（需要 `avg_cost` 计算盈亏百分比），而不只是 code/name/sector
- **输出：** 普通 dict（不需要 `Signal` 的 `sector`/`strategy`/`confidence` 等字段），含 `urgency`

### 7.2 三条卖出规则（按优先级）

| 优先级 | 条件 | 建议卖出价 | urgency | 原理 |
|--------|------|-----------|---------|------|
| 1 | `pnl_pct ≤ -7%` | `close × 0.99` | `"urgent"` | 硬止损，保命 |
| 2 | `pnl_pct ≥ +15%` | `close × 0.995` | `"normal"` | 硬止盈，落袋 |
| 3 | `close < MA60 × 0.95` | `close × 0.99` | `"normal"` | 跌破均线，趋势转弱 |

**短路逻辑：** 先判断止损 → 再判断止盈 → 再判断跌破均线。命中第一条立即返回，不检查后续。

### 7.3 返回结构

```python
{
    "reason": "触发 -7% 止损线（当前 -8.3%）",  # 人类可读
    "suggested_price": 15.84,                    # 建议卖出价（close × discount）
    "urgency": "urgent"                          # "urgent" | "normal"
}
```

**`suggested_price` 的折扣率差异：**
- 止损/跌破均线：`close × 0.99`（-1%，需要快速出逃）
- 止盈：`close × 0.995`（-0.5%，不急，可以挂高一点）

---

## 8. 辅助：_calc_ma()

```python
def _calc_ma(df: pd.DataFrame, n: int) -> float:
    if len(df) < n:
        return float(df["close"].iloc[-1])  # 数据不够 → 用最新收盘价兜底
    return float(df["close"].tail(n).mean())
```

**数据不足时的兜底策略：** 不抛异常，返回最新收盘价。这避免了刚上市的新股（K 线不够 N 根）导致整个信号扫描崩溃。

---

## 9. 调用时序（app.py → strategy）

```
GET /
  │
  ├─ 对于每只持仓 position:
  │    data.fetch_kline(code, 70) → df
  │    strategy.sell_signal(position, df) → sell_signals[]
  │
  └─ 对于每只标的池 stock:
       data.fetch_kline(code, 70) → df
       strategy.scan_stock(code, name, sector, df) → buy_signals[]
```

**注意：** 目前用 70 天拉数（`days=70`），而均线窗口最长 60。70 ≥ 60 + 少量缓冲，够用。但如果加更长的均线（如 MA120），这里也要改。

---

## 10. 扩展指南

### 加一个新买入策略

```python
# 1. 在 strategy.py 写函数
def my_strategy(code, name, sector, df) -> Signal | None:
    if df is None or len(df) < MIN_BARS:
        return None
    # ... 你的判断逻辑 ...
    return Signal(
        code=code, name=name, sector=sector,
        strategy="MyStrategy",
        current_price=close,
        suggested_buy=round(close * 1.005, 2),
        stop_loss=..., take_profit=...,
        reason="...", confidence=...
    )

# 2. 在 scan_stock() 里加一行
def scan_stock(code, name, sector, df):
    signals = []
    for sig in (
        chanlun2b_signal(code, name, sector, df),
        buyhold_signal(code, name, sector, df),
        my_strategy(code, name, sector, df),   # ← 加这行
    ):
        if sig is not None:
            signals.append(sig)
    return signals
```

app.py 不用改——`scan_stock()` 返回的 `list[Signal]` 自动包含新策略。

### 调整参数

所有策略参数都是硬编码在函数体内。修改步骤：
1. 在目标函数中找到对应常量
2. 直接改数值
3. 同步修改同一策略内的 `reason` 字符串（如果改了阈值）

---

## 11. 设计约束 / 已知局限

| 约束 | 说明 |
|------|------|
| 单时间帧 | 只用日线（`scale=240`），不做多帧确认 |
| 无成交量 | 不检查缩量/放量 |
| 无市场环境 | 不区分牛熊，`market_state` 永远是 SIDEWAYS |
| 无仓位计算 | 信号只说买不买，不谈买多少 |
| 无止损移动 | 止损价在信号生成时固定，不随行情上移 |
| 无季节性 | 不处理除权除息 |
| 硬编码阈值 | -7%/+15%/0.95 等全写在代码里，无配置文件 |
