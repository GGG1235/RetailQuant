# RetailQuant

A 股个人量化看板（单实例、本地优先、零外部账号）—— Flask + 缠论近似 + 板块 Treemap + 自选股 + 数据源池。

> 📖 **9 个策略的详细说明**（触发条件、信心度算法、参数、适用场景）见 [`STRATEGIES.md`](STRATEGIES.md)。本文档专注架构、启动、修改记录。

- ✅ **策略引擎**（6 大类 / 7 个策略：缠论 / 量价突破 / 海龟 / 多因子 / ETF 轮动 / 网格 / 游资）
- ✅ 止损 / 止盈信号（-7% / +15% / 跌破 MA60）
- ✅ Flask + 看板（持仓、信号、资金曲线）
- ✅ 加仓 / 减仓 / 删除交易
- ✅ 板块 Treemap（行业 / 概念 Tab）
- ✅ 自选股（持久化 + 弹窗切换 + 实时行情）
- ✅ **数据源池**（多源路由 / 健康度跟踪 / 自动 failover / 30s 批量缓存）

---

## 启动

### 方式一：uv（推荐）

```bash
uv sync                     # 创建虚拟环境 + 安装依赖
uv run python app.py        # 启动
# 浏览器访问 http://localhost:8080
```

### 方式二：pip

```bash
pip install -r requirements.txt
python3 app.py
# 浏览器访问 http://localhost:8080
```

自定义端口：

```bash
RQUANT_PORT=5060 uv run python app.py
# 或
RQUANT_PORT=5060 python3 app.py
```

> 没有 waitress 时自动 fallback 到 Flask dev server。
> 启动方式默认双栈监听（IPv4 + IPv6），`localhost` / `127.0.0.1` / `[::1]` 都能访问。

## 代码检查

```bash
uv run ruff check    # 代码规范检查
uv run ruff format   # 代码自动格式化
```

> ruff 已声明在 `pyproject.toml` 的 `dev` 依赖组中，`uv sync` 会自动安装，无需系统级安装。

---

## 修改记录

### 2026-06-17 · 策略引擎 v1（6 大类 / 7 个策略 / 0 业务变更）

#### 6 大类策略

| 大类 | 策略 | 信号 | 数据需求 |
|---|---|---|---|
| `volume_breakout` | **VpBreakout** | 突破 20 日新高 + 量比 ≥ 1.5 + 强势收盘 | 日 K |
| `turtle` | **DonchianTurtle** | 20 日新高入场，10 日新低离场（2×ATR 止损） | 日 K |
| `etf_rotation` | **CrossBorderDca** | 跨境 ETF MA60 下方 + RSI<35 → 加仓 | 日 K |
| `etf_rotation` | **DividendLowvolRotation** | 红利低波 20 日动量 + 放量 → 持有 | 日 K + 动量 |
| `factor` | **MultiFactor** | 动量+RSI+量比-波动率 综合得分 | 日 K（⚠️ 财务因子待东财/聚宽） |
| `grid` | **GridMartingale** | 日线波动率网格 + 马丁加仓预警 | 日 K（⚠️ 理想用分钟级） |
| `pattern` | **DragonTigerPattern** | 涨停/连板形态（涨幅 ≥ 9.5% 近似） | 日 K（⚠️ 待涨停板接口） |
| `legacy` | **ChanLun2B** | **优化版**：底分型(5日窗口)+突破+多头排列+量能+RSI 7 重过滤 | 日 K |
| `legacy` | **BuyHold** | **优化版**：超跌+超卖+缩量+止跌 4 重确认 | 日 K |

#### 目录结构

```
strategies/
├── __init__.py            # 入口：自动注册 + scan_stock / scan_sell
├── base.py                # Strategy Protocol + Signal dataclass + 指标工具
├── registry.py            # @register + STRATEGIES 字典
├── etf_rotation/
│   ├── cross_border_dca.py
│   ├── dividend_lowvol_rotation.py
│   └── universe.py        # ETF 池子（跨境 + 红利低波）
├── volume_breakout/vp_breakout.py
├── turtle/donchian.py
├── factor/multi_factor.py
├── grid/grid_martingale.py
└── pattern/dragon_tiger.py
```

#### 统一接口

```python
@dataclass
class Signal:
    code, name, sector, strategy, category
    current_price, suggested_buy, stop_loss, take_profit
    reason, confidence
    extra: dict  # 策略特有字段（kind/分数/原始指标）
```

每个策略实现：

```python
class VpBreakout:
    name = "VpBreakout"
    category = "volume_breakout"
    description = "..."

    def signal_buy(self, code, name, sector, df) -> Signal | None: ...
    def signal_sell(self, position, df) -> dict | None: ...
```

#### 一键调用

```python
import strategy

# 跑所有 7 个策略
sigs = strategy.scan_stock(code, name, sector, df)

# 按大类过滤
sigs = strategy.scan_category("turtle", code, name, sector, df)

# 卖出
sig = strategy.sell_signal(position, df)

# 看注册了哪些策略
for s in strategy.all_strategies():
    print(s.category, s.name, s.description)
```

#### 扩展一个新策略

```python
# strategies/xxx/yyy.py
from ..base import Signal, ma
from ..registry import register

@register
class MyStrategy:
    name = "MyStrategy"
    category = "xxx"
    description = "我的策略"

    def signal_buy(self, code, name, sector, df) -> Signal | None:
        if df is None or len(df) < 20:
            return None
        ...
        return Signal(...)

    def signal_sell(self, position, df) -> dict | None:
        ...
```

`strategies/__init__.py` 的 import 触发 `@register`，**新策略 0 配置接入**。

#### 数据降级说明

| 策略 | 缺失能力 | 当前近似方式 | 升级方向 |
|---|---|---|---|
| MultiFactor | 财务数据（PE/PB/股息率/ROE） | 只用 K线因子（动量/RSI/量比/波动率） | 接东财/聚宽 → 加财务因子 |
| GridMartingale | 分钟级 K 线 | 用日线波动率算网格 | 接分钟线 → 高频网格 |
| DragonTigerPattern | 涨停板/连板/龙虎榜 | 涨幅 ≥ 9.5% 近似涨停 | 接涨停板接口 + 板块成分股 |

所有降级在 `Signal.extra.need_data_source` 字段明示。

#### 老策略优化

老的 `ChanLun2B` 和 `BuyHold` 从 1 个条件升级到 4-7 个条件，并拆到 `strategies/legacy/`，接入新引擎自动注册：

| 策略 | 老版 | 优化版 |
|---|---|---|
| `ChanLun2B` | MA5 上穿 MA20（1 个条件，假信号多） | 底分型（5日窗口）+ 突破 + MA5>MA10>MA20 多头排列 + MA60↑ + 量能 ≥ 1.3×5日均量 + 强势收盘 + RSI≥50（7 重过滤） |
| `BuyHold` | 现价 < MA60×0.95（1 个条件） | 20 日跌幅 > 10% + MA60 距离 -35%~-5% + RSI < 30 + 3日/20日量比 < 0.7（缩量见底）+ 当日反弹 + 最近 3 日有阴线（4 重确认） |

#### 兼容

- `strategy.py` 变成兼容层（薄包装），老的 `chanlun2b_signal / buyhold_signal / scan_stock / sell_signal` **全部保留**
- `app.py` / `portfolio.py` **零改动**

#### 验证

```
ruff check    → All checks passed!
ruff format   → 全部格式化
策略注册       → 9 个（6 大类 + legacy 优化版）
模拟 K 线单测  → ChanLun2B conf=79.8 触发（底分型+突破+多头排列+放量）
                BuyHold conf=85.0 触发（-25% 超跌+RSI 18+缩量止跌）
杂乱反例       → 全部不触发 ✓
老 API 兼容    → chanlun2b_signal / buyhold_signal 仍可用
真实 K 线      → sh600460 命中 2 信号，sh512010 命中 1 信号
```

---

### 2026-06-17 · 数据源池化重构（业务层净减 95 行，0 接口变更）

把 Sina K 线 / 行情抽到独立的数据源池，业务层（`data.py` / `board.py`）改成 wrapper。

#### 新增

| 文件 | 行数 | 内容 |
|---|---|---|
| `datasources.py` | 230 | `KlineSource` / `QuoteSource` Protocol + `SinaKlineSource`（JSON 缓存）+ `SinaQuoteSource`（30s 批量缓存）+ `DataSourcePool`（优先级路由 + 健康度跟踪 + 自动 failover） |

#### 业务层简化

| 文件 | 前 | 后 | 净减 |
|---|---|---|---|
| `data.py` | 167 行 | 95 行 | -72 |
| `board.py` | 165 行 | 142 行 | -23 |

#### 接口零变更

```
✓ data.fetch_kline(code, days) -> pd.DataFrame     (签名 + 返回)
✓ data.get_watchlist_codes() / add/remove
✓ data.get_stock / upsert_stock / get_pool
✓ board.fetch_sector_boards(top_n) -> list[dict]   (含 Treemap 坐标)
✓ board.fetch_concept_boards(top_n)
✓ board.fetch_board_stocks(code, top_n)
```

#### 数据池特性

1. **优先级路由**：`pool.add_quote(src, priority=0)` 插入到前面
2. **健康度跟踪**：单源失败 60 秒内不打它（`UNHEALTHY_COOLDOWN`）
3. **批量缓存**：`SinaQuoteSource.BATCH_TTL=30s` 避免重复打 Sina
4. **自动 failover**：源挂了自动降级到下一个健康源
5. **健康面板**：`pool.status()` 返回每个源状态
6. **可扩展**：加 Tencent、东方财富只需写新类 + 注册，业务代码零改动

#### 回归证据

```
ruff check    → All checks passed!
ruff format   → 全部格式化
接口回归       → 8/8 通过
返回结构       → 100% 一致（含 Treemap 坐标 x/y/w/h）
策略单元测试   → chanlun2b / buyhold / sell_signal 全过
真实 K 线拉取  → fetch_kline('sh600460', 30) → 30×6 DataFrame
数据池状态     → sina_kline ✓ healthy / sina_quote ✓ healthy
```

---

### 2026-06-17 · 代码优化（净减 91 行，0 业务逻辑变更）

针对最近一次提交（`cdac79e 新增板块 Treemap 行情、自选股功能、看板优化`）和全项目做的代码优化与冗余清理。

#### Bug 修复

| # | 位置 | 问题 | 修复 |
|---|---|---|---|
| 1 | `requirements.txt` | 缺 `squarify`，`app.py` import 会 `ModuleNotFoundError` | 加 `squarify>=0.4` |
| 2 | `strategy.py:44` | `ma60 = _calc_ma(df, 60)` 计算后从未使用 | 删除 |
| 3 | `app.py:9, 31`, `board.py:11`, `strategy.py:9` | 未使用的 import | 删除 |
| 4 | `app.py` 默认端口 `5060` 与 README `8080` 不一致 | 统一为 `8080`，可通过 `RQUANT_PORT` 覆盖 |

#### 去重

| # | 位置 | 问题 | 修复 |
|---|---|---|---|
| 5 | `board.py:20-84` | `INDUSTRY_ETFS` 和 `CONCEPT_ETFS` **30/30 完全相同**（仅顺序略不同） | 合并为单一 `SECTOR_ETFS` |
| 6 | `board.py:170-203` | `fetch_sector_boards` / `fetch_concept_boards` 镜像函数 | 统一为 `_build_boards_response()`，原 API 名保留 |
| 7 | `app.py:107-117, 299-319` | watchlist 渲染逻辑复制 2 份 | 抽 `_build_watchlist_view()` |
| 8 | `app.py:150-154` | `add_position` 用 `for ... break` 找 name | `_pool_name_map()` 字典查找 |
| 9 | `portfolio.py:22-32` | `_load_json` / `_save_json` 与 `data.py` 完全重复 | 直接 `from data import _load_json, _save_json` |

#### 死代码清理

| # | 位置 | 内容 | 处理 |
|---|---|---|---|
| 10 | `templates/index.html:376-462` | 86 行 JS `squarify()` 实现 + 注释——后端 Python squarify 早就算了坐标 | 整段删除 |
| 11 | `app.py:31`, `board.py:91-95` | `def _log(): import sys` 在函数内重复 import | 移除 |

#### 重构

| # | 位置 | 改动 |
|---|---|---|
| 12 | `data.py:78-83` | 5 列 for 循环 → `df[cols].apply(pd.to_numeric, errors="coerce")` 一次性向量化 |
| 13 | `data.py:90-94` | `upsert_stock` 用 `setdefault(...).update(kwargs)` 替代 4 行 if/None |
| 14 | `strategy.py:91-99` | `scan_stock` 用 tuple + for 替代两个 if 块 |
| 15 | `app.py:14-17` | `int(os.environ.get("RQUANT_PORT", "8080"))` 提取为 `DEFAULT_PORT` 常量 |
| 16 | `app.py` 启动 | waitress `host=0.0.0.0` → `listen=[..., ...]` 双栈（IPv4 + IPv6） |

#### 风格统一

- 全部 `List` / `Dict` / `Optional[X]` → `list` / `dict` / `X | None`（`__future__ annotations` 下兼容 3.9+）
- `ruff check` **0 错误**，`ruff format` 已应用
- 删除 `_test_*.py` 中的 E401/E402

#### 故意未动

- 业务逻辑：缠论 2B / BuyHold 阈值、止损 -7% / 止盈 +15% / MA60 跌破——实战参数原样
- 路由 / API 形态：11 路由路径、方法、返回 JSON 结构 100% 保持
- `fetch_sector_boards` / `fetch_concept_boards` 名字：留薄包装，不破坏其他模块 import
- 缓存 TTL、CACHE_DIR 路径、JSON 文件结构：全保持

---

## 架构（三层）

```
┌─────────────────────────────────────────┐
│  app.py / strategy.py                   │  业务路由（不变）
└─────────────────┬───────────────────────┘
                  │ data.fetch_kline() / board.fetch_*
┌─────────────────▼───────────────────────┐
│  data.py / board.py  （业务层 wrapper） │  - 接口 100% 不变
│                                         │  - 业务层 2 分钟缓存
└─────────────────┬───────────────────────┘
                  │ pool.fetch_kline / pool.fetch_quotes
┌─────────────────▼───────────────────────┐
│  datasources.py  （数据源池 + Sina 实现）│  - Protocol 抽象
│                                         │  - 健康度跟踪
│  ├── SinaKlineSource  (K线+本地JSON缓存) │  - 30s 短窗口批量缓存
│  ├── SinaQuoteSource  (行情)            │  - 自动 failover
│  └── DataSourcePool  (路由)             │
└─────────────────────────────────────────┘
```

### 扩展示例（加 Tencent 行情源）

```python
# datasources.py 加新源
class TencentQuoteSource:
    name = "tencent_quote"
    def fetch(self, code): ...
    def fetch_batch(self, codes): ...
    def healthy(self): ...

# 注册到池（priority 越小越优先）
from datasources import pool
pool.add_quote(TencentQuoteSource(), priority=0)  # Tencent 优先，Sina 兜底
```

业务代码（`app.py` / `data.py` / `board.py`）**完全不用动**。

---

## 文件

```
rQuant/
├── app.py              # Flask 主程序（11 路由）
├── board.py            # 板块行情业务层（SECTOR_ETFS 映射 + 2 分钟缓存 + Treemap 坐标）
├── data.py             # K 线 wrapper + 自选股 + 内存股票字典 + 标的池
├── datasources.py      # 数据源池（Protocol + SinaKlineSource + SinaQuoteSource + Pool）
├── strategy.py         # 兼容层（老 API + 转发到 strategies）
├── STRATEGIES.md       # 9 个策略详细文档（条件/参数/适用场景）
├── portfolio.py        # 持仓管理（JSON 存储）
├── strategies/         # 策略引擎（6 大类 / 7 个策略）
│   ├── base.py         #   Strategy Protocol + Signal + 指标工具
│   ├── registry.py     #   @register + STRATEGIES
│   ├── etf_rotation/   #   跨境定投 + 红利低波轮动
│   ├── volume_breakout/#   量价共振突破
│   ├── turtle/         #   海龟/唐奇安
│   ├── factor/         #   多因子选股
│   ├── grid/           #   网格/马丁
│   ├── pattern/        #   游资形态
│   └── legacy/         #   老策略优化版（chanlun2b / buyhold）
├── pyproject.toml      # 项目元数据 + 依赖声明（uv 管理）
├── requirements.txt    # 锁定依赖（uv pip compile 生成）
├── _test_api.py        # 备选数据源探针（nufm.dfcfw.com，未启用）
├── _test_sina.py       # 板块接口冒烟测试
├── templates/
│   ├── index.html      # 看板（持仓 + 信号 + Treemap + 自选股）
│   └── error.html
├── static/
│   └── style.css
└── data/               # K 线 JSON 缓存（自动生成）+ watchlist / portfolio / trades
```

## 注意

- 第一次访问会触发 Sina 拉数，沙箱环境可能慢
- 数据每 5 天自动刷新（应付周末/节假日）
- 持仓在 `data/portfolio.json`，删除 = 清空
- 自选股在 `data/watchlist.json`，手动编辑也生效
- 数据源健康度：`from datasources import pool; print(pool.status())` 实时查看
- `_test_*.py` 是开发期探针脚本，发布时可忽略
