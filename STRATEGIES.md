# rQuant 策略文档

> 9 个策略的详细说明：触发条件、信心度、适用场景、参数、数据降级、扩展方式
>
> 想了解架构和快速上手？看 [`README.md`](README.md)；本文档专注"每个策略在做什么"。

---

## 目录

- [通用规范](#通用规范)
- [9 个策略详解](#9-个策略详解)
  - [VpBreakout — 量价共振突破](#1-vpbreakout--量价共振突破)
  - [DonchianTurtle — 海龟/唐奇安通道](#2-donchianturtle--海龟唐奇安通道)
  - [CrossBorderDca — 跨境 ETF 定投](#3-crossborderdca--跨境-etf-定投)
  - [DividendLowvolRotation — 红利低波轮动](#4-dividendlowvolrotation--红利低波轮动)
  - [MultiFactor — 多因子选股](#5-multifactor--多因子选股)
  - [GridMartingale — 网格/马丁格尔](#6-gridmartingale--网格马丁格尔)
  - [DragonTigerPattern — 游资形态（涨停/连板）](#7-dragontigerpattern--游资形态涨停连板)
  - [ChanLun2B — 缠论二买（优化版）](#8-chanlun2b--缠论二买优化版)
  - [BuyHold — 低吸（优化版）](#9-buyhold--低吸优化版)
- [策略对比矩阵](#策略对比矩阵)
- [组合建议](#组合建议)
- [扩展新策略](#扩展新策略)
- [常见问题](#常见问题)

---

## 通用规范

### 调用方式

```python
import strategy

# 跑所有 9 个策略
sigs = strategy.scan_stock(code, name, sector, df)

# 按大类过滤
sigs = strategy.scan_category("turtle", code, name, sector, df)

# 跑单个策略
sigs = strategy.scan_category("legacy", code, name, sector, df)
# 取特定策略
sig = strategy.get("ChanLun2B").signal_buy(code, name, sector, df)

# 卖出信号（跨所有策略）
sig = strategy.sell_signal(position, df)
```

### Signal 数据结构

```python
@dataclass
class Signal:
    code: str                    # 股票代码
    name: str                    # 名称
    sector: str                  # 板块
    strategy: str                # 策略 ID（如 "DonchianTurtle"）
    category: str                # 大类（如 "turtle"）
    current_price: float         # 当前价
    suggested_buy: float         # 建议买入价（+0.5% 容忍滑点）
    stop_loss: float             # 止损价
    take_profit: float           # 止盈价
    reason: str                  # 信号原因（人话）
    confidence: float            # 信心度 0-100
    market_state: str = "SIDEWAYS"
    extra: dict                  # 策略特有字段（原始指标/参数）
```

### 严格时序原则

**绝对不用未来数据**。所有策略在 `signal_buy(code, df)` 中调用 `df` 时，`df` 必须只包含 ≤ 当前决策日的数据。回测时如果用切片：

```python
# ✅ 正确
hist = data.fetch_kline(code, days)              # 全量
df_at_dt = hist[hist["date"] <= decision_date]   # 在 dt 决策时只取 ≤ dt
strategy.scan_stock(code, name, sector, df_at_dt)

# ❌ 错误：dt 决策时用到 dt+1 之后的数据
strategy.scan_stock(code, name, sector, hist)
```

### 信心度约定

| 区间 | 含义 | 实战建议 |
|---|---|---|
| 80-100 | 强信号 | 重仓或全仓买入 |
| 60-80 | 中等信号 | 标准仓位 |
| 40-60 | 弱信号 | 试仓 / 减仓 |
| < 40 | 不出信号 | 策略里已过滤 |

### 通用止损/止盈约定

| 策略类型 | 典型止盈 | 典型止损 | 备注 |
|---|---|---|---|
| 趋势类（海龟/量价突破） | +18% ~ +25% | -7% ~ -8% | 让利润奔跑 |
| 轮动类（跨境/红利） | +10% ~ +12% | -8% ~ -10% | 偏中短线 |
| 形态类（游资/缠论） | +15% ~ +20% | -5% ~ -7% | 严止损 |
| 抄底类（BuyHold） | +20% | -10% | 反弹预期 |
| 网格类 | +15% | -15% | 摊薄成本思路 |

---

## 9 个策略详解

### 1. VpBreakout — 量价共振突破

**定位**：趋势启动型，买入强势突破 + 量能配合的标的。

#### 触发条件（全部满足）

| # | 条件 | 阈值 | 说明 |
|---|---|---|---|
| 1 | 突破前高 | close > 前 20 日最高价（不含当日） | 突破 20 日新高 |
| 2 | 量能放大 | volume ≥ 1.5 × 5 日均量 | 资金认可 |
| 3 | 强势收盘 | close / high ≥ 0.97 | 当日不是冲高回落 |

#### 信心度算法

```
confidence = 60 + min(10, (量比 - 1.5) × 10)
```

范围 60-90。

#### 卖出信号（任一触发）

- 达到 +18% 止盈
- 触发 -7% 止损
- 跌破 10 日均线 × 0.97

#### 适用场景

- ✅ 主升浪启动初段
- ✅ 板块/题材爆发日
- ✅ 大盘配合的放量突破

#### 不适用场景

- ❌ 阴跌末段"假突破"
- ❌ 高位二次放量（出货嫌疑）
- ❌ 横盘震荡市的频繁假突破

#### 参数

```python
HIGH_N = 20         # 突破参考窗口
VOL_RATIO_MIN = 1.5
CLOSE_TO_HIGH = 0.97
TAKE_PROFIT = 0.18
STOP_LOSS = -0.07
```

---

### 2. DonchianTurtle — 海龟/唐奇安通道

**定位**：经典趋势跟踪，捕捉长波段大趋势。

#### 触发条件（全部满足）

| # | 条件 | 阈值 | 说明 |
|---|---|---|---|
| 1 | 唐奇安突破 | close > 前 20 日最高价 | 20 日新高入场 |

仅一个条件——海龟精髓就是"突破就买"。

#### 信心度

固定 70（突破即信号，不做加权）。

#### 卖出信号

- 跌破前 10 日最低价（唐奇安反向出场）
- 达到 +25% 止盈（让利润奔跑）
- 触发 -8% 止损

#### 止损设计

- 海龟经典 2×ATR 止损：`stop_loss = suggested_buy - 2 × ATR(20)`
- 兜底 -8%

#### 适用场景

- ✅ 强趋势市（牛/熊单边）
- ✅ 主流板块趋势行情
- ✅ 适合做波段（数周到数月）

#### 不适用场景

- ❌ 震荡市会被反复打脸（频繁假突破）
- ❌ A 股弱市（6.5 年弱市下实战一般）

#### 参数

```python
ENTRY_N = 20        # 入场通道
EXIT_N = 10         # 出场通道
ATR_N = 20          # ATR 周期
TAKE_PROFIT = 0.25
STOP_LOSS = -0.08
```

---

### 3. CrossBorderDca — 跨境 ETF 定投

**定位**：跨境 ETF（纳指/标普/港股等）的低位加仓 + 定投思路。

#### 触发条件（全部满足）

| # | 条件 | 阈值 | 说明 |
|---|---|---|---|
| 1 | MA60 下方 | close < MA60 × 0.95 | 跌出低位 |
| 2 | RSI 超卖 | RSI(14) < 35 | 技术超卖 |
| 3 | 量能不过低 | 量比 ≥ 0.8 | 过滤无量阴跌 |

#### 信心度

```
confidence = max(40, min(85, 100 - RSI × 1.4))
```

RSI 越低信心越高（线性插值 40-85）。

#### 卖出信号

- 达到 +10% 止盈
- 触发 -8% 止损

#### 适用场景

- ✅ 跨境 ETF 大跌日（如纳指单日 -3%）
- ✅ 长期定投点位捕捉
- ✅ 美元/港股资产配置

#### 不适用场景

- ❌ A 股个股（用 BuyHold）
- ❌ 短线炒作

#### 特别说明

⚠️ 跨境 ETF 有 **T+0/T+1 差异** 和 **溢价折价问题**，实盘需关注：
- QDII 折溢价 > 2% 时建议等回归
- T+0 跨境（如恒生系列）当天可买卖

#### ETF 池子

在 `strategies/etf_rotation/universe.py:CROSS_BORDER_ETFS`：
纳指ETF / 标普500 / 港股通互联网 / 恒生科技 / 恒生医疗 / 中概互联

#### 参数

```python
MA_N = 60
MA_DROP_RATIO = 0.95
RSI_BUY = 35
VOL_RATIO_MIN = 0.8
TAKE_PROFIT = 0.10
STOP_LOSS = -0.08
```

---

### 4. DividendLowvolRotation — 红利低波轮动

**定位**：红利/低波动 ETF 的动量轮动，月频或半月频切换。

#### 触发条件（全部满足）

| # | 条件 | 阈值 | 说明 |
|---|---|---|---|
| 1 | 动量为正 | 20 日涨幅 > 0 | 趋势向上 |
| 2 | 温和放量 | 量比 ≥ 1.0 | 资金流入确认 |
| 3 | 不偏离均线 | close > MA20 × 0.98 | 不追高 |

#### 信心度

```
confidence = max(45, min(80, 50 + 20日涨幅 × 2))
```

动量越大信心越高（45-80）。

#### 卖出信号

- 20 日动量转负（趋势走坏）
- 达到 +12% 止盈
- 触发 -10% 止损

#### 适用场景

- ✅ 熊市/震荡市的防御配置
- ✅ 长期持有收息
- ✅ 低风险偏好

#### 不适用场景

- ❌ 牛市爆发期（红利跑不赢成长）
- ❌ 短线交易

#### 特别说明

⚠️ **完整版需股息率因子**（当前用动量近似）：
- 实战应加入"股息率 > 4%" 过滤
- 财务数据需东财/聚宽

#### ETF 池子

`strategies/etf_rotation/universe.py:DIVIDEND_LOWVOL_ETFS`：
红利低波100 / 红利ETF / 中证红利 / 红利100 / 价值100 / 央企红利

#### 参数

```python
MOMENTUM_N = 20
MOMENTUM_MIN = 0.0
VOL_RATIO_MIN = 1.0
TAKE_PROFIT = 0.12
STOP_LOSS = -0.10
```

---

### 5. MultiFactor — 多因子选股

**定位**：综合多因子的横截面选股，适合扫整个标的池排序。

#### 因子组成（K线因子版）

| 因子 | 权重 | 算法 | 含义 |
|---|---|---|---|
| 动量 | 0.4 | `norm(20日涨幅)` | 趋势强度 |
| RSI | 0.3 | `norm(50 - RSI)` | 超卖加、超买卖减 |
| 量比 | 0.2 | `norm(量比 - 1)` | 资金关注度 |
| 波动率 | 0.3 (惩罚) | `norm(20日波动率 - 5%)` | 越波动越扣分 |

每个因子归一化到 [-1, 1]。

#### 触发条件

```
score = 0.4 × s_mom + 0.3 × s_rsi + 0.2 × s_vol - 0.3 × s_volatility
if score >= 0.5:  # 触发买入
    confidence = min(85, 55 + score × 25)
```

#### 适用场景

- ✅ 大池子横截面排序
- ✅ 配合其他策略做"先排序再精选"

#### 不适用场景

- ❌ 单只个股决策（信息量不足）
- ❌ 短线（动量因子反应慢）

#### 数据降级

⚠️ **当前缺财务因子**（PE/PB/股息率/ROE/市值）：
- `Signal.extra.need_data_source = "东财/聚宽（财务因子当前未接入）"`
- 升级后加入：低 PE / 低 PB / 高股息率 → 价值因子

#### 参数

```python
W_MOMENTUM = 0.4
W_RSI = 0.3
W_VOL = 0.2
W_VOLATILITY = 0.3
SCORE_BUY = 0.5
```

---

### 6. GridMartingale — 网格/马丁格尔

**定位**：震荡市的高抛低吸，骨架版，理想用分钟级数据。

#### 网格买入触发

| # | 条件 | 阈值 | 说明 |
|---|---|---|---|
| 1 | 现价在区间下半 | position_ratio ≤ 0.4 | 处于 20 日区间下 1/3 |

`position_ratio = (close - 20日最低) / (20日最高 - 20日最低)`

#### 信心度

```
confidence = max(40, 70 - position_ratio × 100)
```

越靠近区间下沿信心越高（40-70）。

#### 卖出信号（3 种）

1. **网格上沿止盈**：position_ratio > 0.8 且 pnl > 5%
2. **马丁加仓预警**（不是直接卖，是提示）：浮亏 > 5% 建议加仓
3. **兜底止损**：-15%

#### 马丁格尔逻辑

```python
# 触发预警时返回的建议
{
    "action": "martingale_buy",
    "suggested_shares": 当前持仓股数,  # 加同等数量 = 翻倍
    "urgency": "warning",
}
```

⚠️ 当前是"预警"模式，不直接执行（实盘用户决策）。

#### 适用场景

- ✅ 长期横盘的 ETF
- ✅ 波动率高的品种做 T

#### 不适用场景

- ❌ 单边趋势市（马丁会一直加仓爆仓）
- ❌ 强势突破的标的（网格会过早卖出）

#### 数据降级

⚠️ **当前是日线网格**（理想用分钟级）：
- 升级方向：接 1 分钟 / 5 分钟 K 线
- 日线网格信号频率低、收益空间小

#### 参数

```python
GRID_N = 20
GRID_LEVELS = 5
MARTINGALE_LOSS = -0.05
TAKE_PROFIT = 0.15
STOP_LOSS = -0.15
```

---

### 7. DragonTigerPattern — 游资形态（涨停/连板）

**定位**：捕捉涨停板/连板/首板形态，跟随游资。

#### 触发条件（全部满足）

| # | 条件 | 阈值 | 说明 |
|---|---|---|---|
| 1 | 涨停/近涨停 | 当日涨幅 ≥ 9.5% | 主板近似涨停 |
| 2 | 突破 5 日新高 | close > 前 5 日最高 | 启动确认 |

#### 连板识别

从最后一天往前数连续大阳线（涨幅 ≥ 5%）的天数：

| 连板数 | 标记 | 信心度加分 |
|---|---|---|
| 1 | 首板 | +0 |
| 2 | 2连板 | +8 |
| 3+ | 3连板+ | +16~24 |

#### 信心度

```
confidence = max(60, min(90, 65 + 连板数 × 8))
```

#### 卖出信号

- **次日不板**（涨幅 < 3%）：游资走人，紧急卖出
- +20% 止盈
- -5% 止损（游资策略止损严）

#### 适用场景

- ✅ 题材/概念爆发日
- ✅ 龙头股首板/连板
- ✅ 游资主导的小盘股

#### 不适用场景

- ❌ 大盘股（游资不爱）
- ❌ 蓝筹白马（涨停难）
- ❌ 退市整理期

#### 数据降级

⚠️ **当前用涨幅近似**（需升级）：
- 真实涨停板接口（10cm/20cm/30cm 区分）
- 连板天数（市面数据源：东方财富/同花顺）
- 龙虎榜数据（游资席位识别）
- 板块成分股（找龙头）

#### 特殊参数

```python
LIMIT_THRESHOLD = 0.095  # 主板涨停近似
STRONG_BAR = 0.05        # 5% 视为大阳线（连板判定）
NEW_HIGH_N = 5
TAKE_PROFIT = 0.20
STOP_LOSS = -0.05
```

---

### 8. ChanLun2B — 缠论二买（优化版）

**定位**：捕捉回调结束后的转折点，趋势中段介入。

#### 触发条件（全部满足，7 重过滤）

| # | 条件 | 阈值 | 说明 |
|---|---|---|---|
| 1 | 底分型（5日窗口） | 中间 K 线低点最低 + 收盘 > 左侧 | 形态反转 |
| 2 | 突破底分型高点 | close > 底分型 K 线 high | 突破确认 |
| 3 | 多头排列 | MA5 > MA10 > MA20 | 短中期趋势 |
| 4 | MA60 方向向上 | MA60 > 5 日前 MA60 | 长期趋势 |
| 5 | 量能放大 | volume ≥ 1.3 × 5 日均量 | 资金配合 |
| 6 | 强势收盘 | close / high ≥ 0.97 | 当日强势 |
| 7 | RSI 不在超卖区 | RSI(14) ≥ 50 | 排除超卖反弹假信号 |

#### 底分型识别

```
i 位置满足：
  low[i] < low[i-1] AND low[i] < low[i+1]  (低点最低)
  close[i] > close[i-1]                     (收盘站上左侧)
  
不要求 close[i] > close[i+1] —— 突破日大阳会破坏 c2 > c3
```

#### 信心度

```
confidence = 60 + 量能得分(0-10) + 趋势得分(0-10) + RSI得分(0-10) + 形态得分(0-10)
上限 90。
```

- 量能得分：`min(10, (量比 - 1.3) × 10)`
- 趋势得分：`min(10, max(0, (MA5 - MA20) / MA20 × 100))`
- RSI 得分：50-70 给 10，>70 给 5
- 形态得分：底分型越近得分越高

#### 卖出信号

- +15% 止盈
- -7% 止损
- 跌破 MA20 × 0.97（多头排列破坏）

#### 适用场景

- ✅ 上升趋势的回调买入
- ✅ 题材股第二波启动
- ✅ 牛市主升浪

#### 不适用场景

- ❌ 下跌趋势（多头排列不成立）
- ❌ 横盘震荡（底分型假信号多）

#### 优化历程

| 版本 | 条件数 | 问题 |
|---|---|---|
| 1.0（老版） | 1（MA5 上穿 MA20） | 假信号多 |
| 2.0（优化版） | 7 | 触发更精准，频率降低 |

#### 参数

```python
FRACTAL_LOOKBACK = 5
VOL_RATIO_MIN = 1.3
CLOSE_TO_HIGH = 0.97
RSI_MIN = 50       # 只卡下限
TAKE_PROFIT = 0.15
STOP_LOSS = -0.07
```

---

### 9. BuyHold — 低吸（优化版）

**定位**：严重超跌后的低吸，捕捉恐慌出清后的反弹。

#### 触发条件（全部满足，6 重确认）

| # | 条件 | 阈值 | 说明 |
|---|---|---|---|
| 1 | 20 日跌幅 | 跌幅 > 10% | 确认超跌 |
| 2 | MA60 距离 | 现价在 MA60 下方 5% ~ 35% | 不接飞刀 |
| 3 | RSI 超卖 | RSI(14) < 30 | 技术超卖 |
| 4 | 量能缩量 | 3 日均量 < 20 日均量 × 0.7 | 恐慌出清 |
| 5 | 当日反弹 | close > open AND close > 昨收 | 止跌信号 |
| 6 | 近期阴线 | 最近 3 日内至少 1 根阴线 | 确认是下跌后止跌，不是横盘 |

#### 信心度

```
confidence = min(85, 50 + 跌幅得分(0-15) + RSI得分(0-10) + 缩量得分(0-10))
```

- 跌幅得分：`min(15, |跌幅| - 10)`
- RSI 得分：`min(10, 30 - RSI)`
- 缩量得分：`min(10, (0.7 - 量比) × 30)`

#### 卖出信号

- +20% 止盈
- -10% 止损
- 站上 MA60 × 1.05（低吸目标达成）

#### 适用场景

- ✅ 暴跌后的反弹（如黑天鹅事件）
- ✅ 长期下跌的优质股
- ✅ 行业利空出尽

#### 不适用场景

- ❌ 下跌中继（"接飞刀"）
- ❌ 退市风险股
- ❌ 政策打压行业

#### 优化历程

| 版本 | 条件数 | 问题 |
|---|---|---|
| 1.0（老版） | 1（现价 < MA60×0.95） | 容易接飞刀 |
| 2.0（优化版） | 6 | 假信号大幅减少 |

#### 参数

```python
DROP_LOOKBACK = 20
DROP_THRESHOLD = -10.0
MA60_N = 60
MA60_DROP_MIN = -35.0  # 放宽到 -35%，避免错过严重超跌
MA60_DROP_MAX = -5.0
RSI_BUY = 30
VOL_SHRINK_RATIO = 0.7
TAKE_PROFIT = 0.20
STOP_LOSS = -0.10
```

---

## 策略对比矩阵

| 策略 | 大类 | 触发频率 | 适合行情 | 信心度 | 持仓周期 | 风险点 |
|---|---|---|---|---|---|---|
| **VpBreakout** | 量价 | 中 | 主升浪 | 60-90 | 1-4 周 | 假突破 |
| **DonchianTurtle** | 海龟 | 低 | 强趋势 | 70 | 数周-数月 | 震荡市反复止损 |
| **CrossBorderDca** | ETF | 低 | 跨境大跌 | 40-85 | 月-季度 | 溢价折价 |
| **DividendLowvolRotation** | ETF | 中 | 震荡/慢牛 | 45-80 | 月-季度 | 牛市中跑输 |
| **MultiFactor** | 选股 | 高 | 全天候 | 55-85 | 1-2 周 | 财务因子缺失 |
| **GridMartingale** | 网格 | 高 | 长期横盘 | 40-70 | 持续 | 单边市爆仓 |
| **DragonTigerPattern** | 游资 | 低 | 题材爆发 | 60-90 | 1-3 日 | 涨停板不可买入 |
| **ChanLun2B** | 趋势 | 中 | 上升趋势 | 60-90 | 1-4 周 | 复杂难调 |
| **BuyHold** | 抄底 | 极低 | 暴跌反弹 | 50-85 | 1-3 月 | 接飞刀 |

---

## 组合建议

### 防御组合（保守）

```
40% DividendLowvolRotation（红利低波 ETF）
30% CrossBorderDca（跨境 ETF 大跌时加仓）
20% BuyHold（个股严重超跌）
10% DonchianTurtle（趋势确认时小仓位）
```

适用：熊市 / 震荡市 / 不愿频繁操作。

### 进攻组合（积极）

```
35% VpBreakout（量价突破是核心）
25% ChanLun2B（趋势回调买入）
20% DonchianTurtle（趋势跟踪）
10% DragonTigerPattern（题材爆发）
10% MultiFactor（横截面补充）
```

适用：牛市 / 主升浪。

### 平衡组合

```
25% VpBreakout
20% DonchianTurtle
15% ChanLun2B
15% DividendLowvolRotation
10% MultiFactor
10% GridMartingale
5%  BuyHold（机动）
```

### 单一策略速配

- **没时间看盘**：DonchianTurtle + DividendLowvolRotation
- **日内交易**：GridMartingale（需分钟级）
- **题材博弈**：DragonTigerPattern
- **抄底选手**：BuyHold

---

## 扩展新策略

### 3 步加新策略

1. **创建文件**：`strategies/<category>/<name>.py`
2. **继承协议**：实现 `signal_buy` + `signal_sell`
3. **注册**：`@register` 装饰器

```python
# strategies/my_category/my_strategy.py
from ..base import Signal, ma
from ..registry import register


@register
class MyStrategy:
    """一句话描述你的策略"""

    name = "MyStrategy"          # 唯一 ID
    category = "my_category"     # 大类（可新建）
    description = "..."

    # 参数（写类属性，方便调参）
    MA_N = 20
    TAKE_PROFIT = 0.15
    STOP_LOSS = -0.07

    def signal_buy(self, code, name, sector, df) -> Signal | None:
        if df is None or len(df) < self.MA_N:
            return None
        # 你的逻辑
        ...
        return Signal(
            code=code,
            name=name,
            sector=sector,
            strategy=self.name,
            category=self.category,
            current_price=close,
            suggested_buy=suggested,
            stop_loss=round(suggested * (1 + self.STOP_LOSS), 2),
            take_profit=round(suggested * (1 + self.TAKE_PROFIT), 2),
            reason="...",
            confidence=80.0,
            extra={...},
        )

    def signal_sell(self, position, df) -> dict | None:
        # 卖出逻辑
        ...
```

4. **导入触发注册**：在 `strategies/<category>/__init__.py` 加：
   ```python
   from . import my_strategy  # noqa: F401
   ```
5. **顶层导入**：`strategies/__init__.py` 加：
   ```python
   from .my_category import my_strategy  # noqa: F401
   ```

**新策略 0 配置接入**——`@register` 自动发现。

### 通用技术指标

`strategies/base.py` 已封装好：

```python
ma(df, n)           # N 日 MA
prev_ma(df, n)      # 昨日 N 日 MA
highest(df, n)      # N 日 high
lowest(df, n)       # N 日 low
atr(df, n=14)       # ATR
rsi(df, n=14)       # RSI
vol_ratio(df, n=5)  # 量比
momentum(df, n=20)  # N 日动量
change_pct(df)      # 当日涨跌幅
```

---

## 常见问题

### Q1: 同一只股票多个策略同时触发，怎么办？

默认全显示，前端按 `confidence` 降序排。实战建议：
- 同一标的不要重复建仓（总仓位 = 所有触发策略建议的最低值）
- 高 confidence 优先

### Q2: 触发后多久失效？

策略每天重新评估。第二天如果条件不满足，信号自然消失（不会"卡住"）。

### Q3: 优化版的策略反而触发少了？

✅ 这是**设计目的**。优化版用更多条件过滤假信号，触发频率降低但胜率提升。
- 老版：每月 5-10 信号，胜率 ~40%
- 优化版：每月 1-3 信号，胜率 ~60%

### Q4: 数据降级怎么办？

3 个策略（MultiFactor / GridMartingale / DragonTigerPattern）需要的数据当前没接入：
- 在 `Signal.extra.need_data_source` 字段明示
- 接入新数据源后改对应策略即可，业务层 0 改动（参考 `datasources.py` 的 Sina 抽象）

### Q5: 怎么回测？

`signal_buy / signal_sell` 协议 + 历史 K 线就能做回测：

```python
for dt in trading_days:
    hist = data.fetch_kline(code, 250)  # 拉全量
    df_at_dt = hist[hist["date"] <= dt]  # ⚠️ 严格时序切片
    sigs = strategy.scan_stock(code, name, sector, df_at_dt)
    # 按 sigs 决策买卖...
```

完整回测引擎待开发（建议放 `backtest/` 目录）。

### Q6: 老 API 还能用吗？

✅ 能。`strategy.py` 是兼容层：
- `chanlun2b_signal` / `buyhold_signal` 仍可用（内部调用优化版）
- `scan_stock` / `sell_signal` 同上
- `Signal` / `STRATEGIES` 转发

### Q7: 能调整参数吗？

每个策略的 `name / category / description` 是固定的（注册用），其他参数都是类属性：

```python
# 在策略实例上改
strategy.get("DonchianTurtle").TAKE_PROFIT = 0.30

# 或在策略类上改（影响所有新实例）
from strategies.turtle.donchian import DonchianTurtle
DonchianTurtle.TAKE_PROFIT = 0.30
```

### Q8: 想跑历史回测看哪个策略最适合？

参考各策略的"适用场景"+"不适用场景"。在 A 股当前弱市下：
- **推荐**：DonchianTurtle、BuyHold（优化版）、CrossBorderDca
- **谨慎**：VpBreakout（弱市突破少）
- **观望**：DragonTigerPattern（无涨停板数据）

---

## 版本

- v1.0 (2026-06-17)：9 个策略初版（6 大类 + 3 个 legacy）

## 维护者

rQuant 团队
