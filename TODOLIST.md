# rQuant · TODOLIST（前端照搬参考图 — mock 数据点追踪）

> 上线日期：2026-06-18
> 状态：**前端全部照搬参考图 / 后端按需补 3 个 API / 4 个数据点为 mock 假数据**
> 目标：先有完整视觉 / 流程跑通，再按优先级把 mock 替换为真实实现

---

## ✅ 已完成

### 后端新增 API
- [x] `GET /api/market_status` — A 股市场状态（开/休/午休/集合竞价/周末）
  - 简单时段判断（9:15-15:00），无需新增持久化
  - 文件：`rquant/business/system.py`
- [x] `GET /api/strategy_status` — 策略列表 + 状态 + 信号数 + 最后运行
  - 文件：`rquant/business/system.py`
- [x] `GET /api/system_log` — 内存 ring buffer 系统日志
  - 200 条容量，logging.Handler 装饰器自动收集
  - 桥接 `views._log` + `app_factory` 启动时 ensure
  - 文件：`rquant/business/system.py`
- [x] `board.py` 板块排行返回 `turnover`（成交额，f2 字段）
  - 文件：`rquant/business/board.py`

### 前端照搬
- [x] Navbar：rQuant + 日期 + 市场状态点 + 最后刷新 + 刷新/设置/头像
- [x] 6 张统计卡片（总资产/总市值/今日盈亏/持仓数/买入信号/卖出提示）
- [x] 板块热力图 + tab + 大小=成交额 颜色=涨跌幅 7 段图例
- [x] 今日决策：卖出提示 + 买入信号 Top5
- [x] 当前持仓表（带仓位条 + 卖出按钮）
- [x] 持仓分布（饼图 + 4 维度统计 + 中央 100% 文字）
- [x] 买入信号列表（带筛选 + 评分）
- [x] 交易历史（默认折叠）
- [x] 自选股（0 时显示空状态插画）
- [x] 策略状态表（运行中/停机）
- [x] 系统日志表（按级别着色）
- [x] Treemap hover tooltip（带成交额 / 成分股 / 领涨股）
- [x] 数字 CountUp 动画
- [x] 持仓饼图中央文字（"总市值占比 100.00%"）
- [x] 系统日志每 10 秒自动刷新

---

## ⚠️ Mock 数据点（需要后续替换为真实实现）

### M1. 总资产 = 总市值（前端直接复用 total_market）
- **现状**：参考图里"总资产 ¥112"和"总市值 ¥116"不同，多了 4 元
- **Mock**：目前 `total_assets = total_market`（不区分"持仓市值"和"含现金总资产"）
- **真实实现需要**：
  - 引入"现金 / 余额"概念
  - 新增 `account` 表 / JSON：现金余额
  - `routes.py` 计算 `total_assets = total_market + cash_balance`
- **影响**：高（前后端耦合，但视觉差异小）
- **优先级**：P1（用户实盘需要知道"总资金"vs"已用资金"）

### M2. 策略状态 — 8 个内置策略全部 hard-coded
- **现状**：`system._KNOWN_STRATEGIES` 写死 8 个策略名
- **Mock**：每个策略的状态按名字 hash 决定 running / stopped，最后运行时间随机
- **真实实现需要**：
  - `rquant/strategy/registry` 暴露所有已注册策略名（动态遍历）
  - 每个策略 `generate_signals()` 完成后调 `system.report_strategy_run(name, signal_count)`
  - 移除 `_KNOWN_STRATEGIES` 硬编码
- **影响**：中（数据可能不准，但展示完整）
- **优先级**：P2

### M3. 今日盈亏 = 总盈亏（没有"当日 vs 持仓累计"区分）
- **现状**：`total_pnl` 是持仓总浮动盈亏，没有"今日盈亏"独立字段
- **Mock**：卡片直接显示总盈亏 + 总盈亏率
- **真实实现需要**：
  - 新增 `position_daily_pnl` 表：每个 position 每天的盈亏快照
  - 计算 `今日盈亏 = 今日快照 - 昨日快照`（用 portfolio.json 增量）
  - 或者用 trades 表 + 当前持仓反推
- **影响**：高（用户最关心的数字之一）
- **优先级**：P1

### M4. 持仓集中度提示写死"持仓集中度较高"
- **现状**：模板里硬编码提示语
- **Mock**：`持仓集中度较高，请注意风险控制`
- **真实实现需要**：
  - 计算最大单一持仓占总市值的百分比
  - 大于阈值（如 30%）显示提示
  - 模板改成条件渲染
- **影响**：低（视觉提示，逻辑可后做）
- **优先级**：P3

### M5. 板块热力图大小=成交额（暂未实现）
- **现状**：后端已加 `turnover` 字段，但前端 Treemap 还是用 `change_pct` 绝对值作为面积
- **Mock**：`squarify` 用 |change_pct| 排序
- **真实实现需要**：
  - 前端用 `item.turnover` 作为面积依据
  - 颜色仍用 `change_pct`（颜色图例不变）
  - 面积越大 = 板块越活跃
- **影响**：低（视觉差异）
- **优先级**：P2

### M6. 行情自动刷新（无）
- **现状**：板块 / 持仓 / 卖出信号全部依赖手动刷新页面
- **Mock**：只有"最后刷新 HH:MM:SS"由前端 setInterval 显示
- **真实实现需要**：
  - WebSocket / SSE 推送板块涨跌幅变动
  - 或者前端 setInterval(5min) 拉取
  - 涨跌幅变动时数字闪烁（已有 `.flash-up / .flash-down` CSS 动画）
- **影响**：高（用户盯盘体验）
- **优先级**：P1

---

## 🐛 已知小问题

- [ ] 板块热力图在窗口 resize 时不重绘（需加 `window.addEventListener('resize', drawTreemap)`）
- [ ] 数字 CountUp 在 reload 整个页面时重置（不持久）
- [ ] 系统日志无滚动到底部按钮（日志长了翻不到最新）
- [ ] 自选股空状态点击"前往设置"按钮还是弹的 add form（应该跳到 watchlist 配置页，目前无）
- [ ] 交易历史里"策略"列显示的是 note（应该用 t.strategy 字段，目前 portfolio.py add_trade 没接 strategy）

---

## 📋 优先级排序

| 优先级 | Mock 点 | 估时 | 备注 |
|---|---|---|---|
| **P1** | M3 今日盈亏 | 4h | 需 position_daily_pnl 表 |
| **P1** | M1 总资产（现金）| 2h | 简单 account.json |
| **P1** | M6 自动刷新 | 1d | 前端 setInterval + 数字闪烁 |
| **P2** | M2 策略动态注册 | 2h | 改 strategy/registry |
| **P2** | M5 板块热力图按成交额 | 1h | 纯前端 |
| **P3** | M4 集中度提示 | 30min | 模板条件 |
| **P3** | 小问题 | 1h | 滚动 / 持久 / resize |

合计：~3 天工作量把全部 mock 替换为真实实现。

---

## 📁 相关文件

```
rquant/
├── business/
│   ├── system.py          ← 新增（市场状态/策略/日志）
│   ├── board.py           ← 改动（加 f2 成交额）
│   └── ...
├── web/
│   ├── routes.py          ← 改动（3 个新 API）
│   └── views.py           ← 改动（_log 桥接 system buffer）
templates/
├── index.html             ← 全部重写
static/
└── style.css              ← 全部重写
```
