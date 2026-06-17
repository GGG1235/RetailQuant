# RetailQuant

A 股个人量化看板（单实例、本地优先、零外部账号）—— Flask + 缠论近似 + 板块 Treemap + 自选股 + 数据源池。

- ✅ 缠论近似（MA5 > MA20 + 站上 MA5 → 买入信号）
- ✅ Buy & Hold 近似（现价 < MA60 × 0.95 → 低吸信号）
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

---

## 修改记录

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
├── strategy.py         # 缠论近似 + BuyHold + 卖出信号
├── portfolio.py        # 持仓管理（JSON 存储）
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
