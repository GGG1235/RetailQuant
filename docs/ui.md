# RetailQuant UI 交互文档

> 生成：2026-06-18 | 面向 AI 维护者 | 覆盖 `templates/index.html` 所有交互元素

---

## 页面布局（从上到下）

```
┌─ navbar ──────────────────────────────────────────┐
│ rQuant  市场状态  最后刷新              🔄 ⚙️ 用户 │
└────────────────────────────────────────────────────┘
┌─ flash 消息条（条件渲染）──────────────────────────┐
└────────────────────────────────────────────────────┘
┌─ 板块热力图 (Treemap) ────────────────────────────┐
│ 🗺️ 板块热力图  [行业板块] [概念板块]   颜色=涨跌幅 │
│ ┌──────────────────────────────────────────────┐  │
│ │          Canvas 900×500                      │  │
│ │  ┌────┐ ┌───┐ ┌──────┐                      │  │
│ │  │半导体│ │银行│ │ 白酒 │  …                 │  │
│ │  └────┘ └───┘ └──────┘                      │  │
│ └──────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────┘
┌─ 顶部卡片 ────────────────────────────────────────┐
│ 总资产 可用资金 总市值 今日盈亏 仓位 买入信号 卖出提示 │
└────────────────────────────────────────────────────┘
┌─ 第一行：板块热力图 + 今日决策 ────────────────────┐
│ 板块热力图         │ 卖出提示 + 买入信号 Top5      │
│ ┌─────────────────┐  │ ┌──────────────────────┐  │
│ │ [urgent] 止损   │  │ │ ChanLun2B / BuyHold  │  │
│ │ 建议卖 ¥xx.xx   │  │ │ 现价→买价 止损 止盈   │  │
│ └─────────────────┘  │ └──────────────────────┘  │
└────────────────────────────────────────────────────┘
┌─ 第二行：当前持仓 + 持仓分布 ──────────────────────┐
│ 📦 当前持仓 [+添加][充值][提现] │ 🥧 持仓分布       │
│ ┌─────────────────┐  │ ┌──────────────────────┐  │
│ │ 代码 名称 股数  │  │ │ 代码 名称 现价 涨幅  │  │
│ │ 成本 现价 市值  │  │ │ 板块 [买入][−][分析] │  │
│ │ 盈亏 [卖]      │  │ │ 饼图 + 仓位统计       │  │
│ └─────────────────┘  │ └──────────────────────┘  │
└────────────────────────────────────────────────────┘
┌─ 买入信号列表（可按策略大类/策略名筛选）────────────┐
└────────────────────────────────────────────────────┘
┌─ 交易历史（条件渲染，可折叠）──────────────────────┐
└────────────────────────────────────────────────────┘
┌─ 自选股 + 策略状态 ───────────────────────────────┐
└────────────────────────────────────────────────────┘
┌─ 系统日志（10 秒刷新）─────────────────────────────┐
└────────────────────────────────────────────────────┘
```

---

## UI 元素逐项清单

### 1. Navbar（导航栏）

| 属性 | 值 |
|---|---|
| 位置 | 页面最顶部，全宽 |
| 样式 | `background: rgba(0,0,0,0.3); border-bottom: 1px solid rgba(255,255,255,0.1)` |
| 子元素 | |

| 元素 | 样式 | 作用 | 触发函数 |
|---|---|---|---|
| `rQuant` | `.logo` 渐变文字 | 品牌标识 | 无 |
| `{{ today }}` | `#nav-date` | 显示当前日期 | 服务端渲染 |
| 市场状态 | `#state-label` + `.state-dot` | 显示开盘/休市状态 | `reloadMarketStatus()` |
| 最后刷新 | `#last-refresh` | 每秒更新时间 | `refreshLastRefresh()` |
| `🔄` | `.btn-icon` | 整页刷新 | `location.reload()` |
| `⚙️` | `.btn-icon` | 设置入口占位 | 无 |
| `👤` | `.avatar` | 用户占位 | 无 |

---

### 2. Flash 消息条

| 属性 | 值 |
|---|---|
| 位置 | 容器顶部，卡片上方 |
| 样式 | `.flash` — 圆角 4px，10px 内边距 |
| 条件 | 仅在有 `get_flashed_messages()` 时渲染 |

| 子类 | 样式 |
|---|---|
| `.flash-success` | 绿色半透明底 + 绿色文字 |
| `.flash-error` | 红色半透明底 + 红色文字 |

---

### 3. 板块热力图（Treemap）

| 属性 | 值 |
|---|---|
| 容器 | `<div class="box" id="treemap-box">` |
| 位置 | Flash 下方，顶部卡片上方 |

| 元素 | 样式 | 作用 | 触发函数 |
|---|---|---|---|
| 标题 `🗺️ 板块热力图` | h2，色 `#fff` | 区块标识 | 无 |
| `行业板块` Tab | `.tab-btn.active` — 青色高亮 | 切换到东方财富行业板块 | `switchTab('sector')` |
| `概念板块` Tab | `.tab-btn` — 灰色 | 切换到东方财富概念板块 | `switchTab('concept')` |
| 图例 | `.treemap-legend` | 大小=成交额，颜色=涨跌幅 | 无 |
| Canvas | `id="treemap-canvas"`，900×500，响应式 | 绘制板块 Treemap 矩形 | `loadTreemap()` → `drawTreemap()` |
| 加载遮罩 | `id="treemap-loading"`，绝对定位覆盖 Canvas | 加载中提示 | 显示/隐藏于 `loadTreemap()` |

**Canvas 交互：**

| 事件 | 行为 | 触发函数 |
|---|---|---|
| `mousemove` | 鼠标悬停在矩形上 → `cursor: pointer` | 内联 Canvas 事件 |
| `click` | 点击矩形 → 弹出成分股弹窗 | `showStocks(item.code, item.name)` |

**颜色规则：**

- 涨（`change_pct ≥ 0`）：`rgb(200~255, 20~60, 20~60)` — 红/暖色调
- 跌（`change_pct < 0`）：`rgb(20~60, 170~220, 30~80)` — 绿色调
- 强度：`min(|pct| / 10, 1)` — 涨幅越大颜色越深

---

### 4. 成分股弹窗

| 属性 | 值 |
|---|---|
| 容器 | `<div id="stock-modal" class="modal">` |
| 显示/隐藏 | `display: flex` / `display: none` |
| 样式 | 全屏半透明黑色遮罩，居中白色卡片 |

| 元素 | 样式 | 作用 | 触发函数 |
|---|---|---|---|
| 标题 | `h3`，色 `#00d4ff` | 显示板块名 + 代码 | `showStocks(code, name)` 动态设置 |
| 成分股表格 | `.stock-table` — 列：代码/名称/涨幅/换手/操作 | 展示板块内 TOP 20 股票 | 无 |
| 操作列按钮 | `.btn-wl-add`（青色 +）或 `.btn-wl-remove`（红色 −），22×22 圆形 | 加入/移出自选股 | `toggleWatchlist(code, btn)` |
| 空提示 | `id="stock-modal-empty"` | "暂无成分股数据" | 条件显示 |
| 关闭按钮 | `.btn` | 关闭弹窗 | `closeStockModal()` |

---

### 5. 顶部卡片

| 属性 | 值 |
|---|---|
| 容器 | `<div class="cards">` — grid 自适应列 |
| 样式 | `.card` — 半透明背景，圆角 8px，边框 |

| 卡片 | 数据来源 | 条件样式 |
|---|---|---|
| 总资产 | `total_assets` | 无 |
| 可用资金 | `available_funds` | 无 |
| 总市值 | `total_market` | 无 |
| 今日盈亏 | `total_pnl` + `total_pnl_pct` | `.up`（正）`.down`（负） |
| 仓位占比 | `position_ratio`（`total_market / total_assets`） + `positions|length` | 无 |
| 买入信号 | `buy_signals|length` | 无 |
| 卖出提示 | `sell_signals|length` | `.red` |

---

### 6. 卖出提示区

| 属性 | 值 |
|---|---|
| 容器 | `<div class="box" id="sell-signals-box">` |
| 布局 | `.row` 左列（与买入信号并列） |

| 元素 | 样式 | 作用 |
|---|---|---|
| 标题 `📉 卖出提示` | h2 + `.badge.red` 计数 | 区块标识 + 信号数量 |
| 信号卡片 | `.signal` — 深色背景，圆角 6px | 每条信号独立卡片 |

| 信号子元素 | 样式 | 内容 |
|---|---|---|
| `.sig-head` | flex，左右分布 | `<b>`code + name；`.urgency-tag`（urgent 红 / normal 黄） |
| `.sig-reason` | 13px，色 `#b0bec5` | 触发原因（如"触发 -7% 止损线"） |
| `.sig-detail` | 12px，色 `#78909c` | 建议卖出价 |

| 条件 | 显示 |
|---|---|
| `sell_signals` 非空 | 渲染信号卡片 |
| `sell_signals` 为空 | 显示 `✅ 无（持仓健康）` |

---

### 7. 买入信号区

| 属性 | 值 |
|---|---|
| 容器 | `<div class="box" id="buy-signals-box">` |
| 布局 | `.row` 右列 |

| 元素 | 样式 | 作用 |
|---|---|---|
| 标题 `🔥 买入信号` | h2 + `.badge.green` 计数 | 区块标识 + 信号数量 |
| 信号卡片 | `.signal` | 每条信号独立卡片 |

| 信号子元素 | 样式 | 内容 |
|---|---|---|
| `.sig-head` | flex | `<b>`code + name · sector；`.strat-tag`（ChanLun2B / BuyHold） |
| `.sig-reason` | 13px，色 `#b0bec5` | 触发原因 |
| `.sig-detail` | 12px，色 `#78909c` | 现价 → 买价 · 止损 · 止盈 |

| 条件 | 显示 |
|---|---|
| `buy_signals` 非空 | 渲染信号卡片 |
| `buy_signals` 为空 | 显示 `📭 今日无信号` |

---

### 8. 持仓区

| 属性 | 值 |
|---|---|
| 容器 | `<div class="box" id="positions-box">` |
| 布局 | `.row` 左列 |

| 元素 | 样式 | 作用 | 触发函数 |
|---|---|---|---|
| 标题 `📦 当前持仓` | h2 | 区块标识 | 无 |
| `+ 添加` 按钮 | `.btn-sm.btn-add` | 展开买入表单 | `showAddForm()` |
| `充值` 按钮 | `.btn-sm.btn-topup` | 打开充值弹窗 | `showTopupModal()` |
| `提现` 按钮 | `.btn-sm.btn-withdraw` | 打开提现弹窗 | `showWithdrawModal()` |
| 买入表单 | `.form`，默认 `display:none` | 输入 code/shares/price → POST `/position/add` | 提交走 form action |
| 取消按钮 | `.btn` | 收起表单 | `hideAddForm()` |
| 持仓表格 | 列：代码/名称/股数/成本/现价/市值/盈亏/操作 | 展示所有持仓 | 无 |
| 盈亏列 | 正 `.green`，负 `.red` | 颜色标识 | 无 |
| `卖` 按钮 | `.btn-sell` — 红色边框 | 打开卖出弹窗 | `showSellForm(code, shares, currentPrice)` |

---

### 9. 卖出弹窗

| 属性 | 值 |
|---|---|
| 容器 | `<div id="sell-modal" class="modal">` |
| 触发 | 持仓表格中点击"卖"按钮 |

| 元素 | 样式 | 作用 | 触发函数 |
|---|---|---|---|
| 标题 `🔴 卖出 <code>` | h3 | 显示卖出目标 | `showSellForm()` 动态设置 |
| 持仓信息 | 灰色文字 | 显示持仓股数 + 现价 | 同上 |
| 卖出价格输入 | `number`，step 0.01 | 输入卖出单价 | `updatePreview()` 实时预览 |
| 卖出股数输入 | `number`，min 100，step 100 | 输入卖出数量 | 同上 |
| 预览区 | `id="sell-preview"`，深色背景 | 实时显示卖出金额和估算税费 | 同上 |
| `确认卖出` | `.btn-primary` | 提交表单 → POST `/position/sell/<code>` | form submit |
| `取消` | `.btn` | 关闭弹窗 | `closeSell()` |

---

### 10. 充值 / 提现弹窗

| 弹窗 | 容器 | 作用 | 触发函数 | API |
|---|---|---|---|---|
| 充值 | `#topup-modal` | 增加总资金和可用资金 | `showTopupModal()` / `doTopup()` | `POST /api/funds/add` |
| 提现 | `#withdraw-modal` | 从可用资金提现，最多清零 | `showWithdrawModal()` / `doWithdraw()` | `POST /api/funds/withdraw` |

---

### 11. 自选股区

| 属性 | 值 |
|---|---|
| 容器 | `<div class="box" id="watchlist-box">` |
| 布局 | `.row` 右列 |

| 元素 | 样式 | 作用 | 触发函数 |
|---|---|---|---|
| 标题 `⭐ 自选股` | h2 + `.badge.green` 计数 | 区块标识 + 数量 | 无 |
| 自选股表格 | 列：代码/名称/现价/涨幅/板块/操作/删除/分析 | 展示所有自选股 | 服务端 + JS `reloadWatchlist()` |
| 空状态 | `.empty-state` | 自选股为空时提示 | 无 |

**每行按钮：**

| 按钮 | 条件 | 样式 | 作用 | 触发函数 |
|---|---|---|---|---|
| `买入` | 始终 | `.btn-primary.btn-sm` | 展开买入表单并预填 code + price | `showAddForCode(code, price)` |
| `−` | 始终 | `.btn-del` 圆形红色按钮 22×22 | 从自选股删除 | `removeFromWatchlist(code)` |
| `分析` | 始终 | `.btn-sm.btn-view` | 打开策略评分弹窗 | `showWatchlistAnalysis(code)` |

---

### 12. 自选股分析弹窗

| 属性 | 值 |
|---|---|
| 容器 | `<div id="analysis-modal" class="modal">` |
| 触发 | 自选股行最右侧点击"分析"按钮 |
| 数据来源 | `GET /api/watchlist/analyze/<code>` |

| 元素 | 样式 | 作用 | 触发函数 |
|---|---|---|---|
| 标题 | `#analysis-modal-title` | 显示股票名称/代码 | `showWatchlistAnalysis(code)` 动态设置 |
| 股票信息 | `.modal-subtitle` | 显示 code、板块、现价 | 同上 |
| 分析表格 | `.analysis-table` | 按策略展示大类、评分、触发状态、说明 | 同上 |
| 触发标签 | `.analysis-hit` / `.analysis-miss` | 标识策略是否触发买入条件 | 同上 |
| 关闭按钮 | `.btn` | 关闭弹窗 | `closeAnalysisModal()` |

---

### 13. 策略状态

| 属性 | 值 |
|---|---|
| 容器 | `<div class="box" id="strategy-status-box">` |
| 数据来源 | `GET /api/strategy_status` |
| 刷新 | 页面加载时调用 `reloadStrategyStatus()` |

| 列 | 内容 |
|---|---|
| 策略名称 | `s.name` |
| 状态 | `.strat-status.run/stop` |
| 今日信号 | `s.signals_today` |
| 最后运行 | `s.last_run` |

---

### 14. 系统日志

| 属性 | 值 |
|---|---|
| 容器 | `<div class="box" id="system-log-box">` |
| 数据来源 | `GET /api/system_log` |
| 刷新 | 页面加载 + 每 10 秒 `reloadSystemLog()` |

---

### 15. 交易历史

| 属性 | 值 |
|---|---|
| 容器 | `<div class="box collapsible" id="trades-box">` |
| 条件 | 仅 `trades` 非空时渲染 |
| 展开/收起 | 点击标题触发 `toggleTrades()` |

| 列 | 内容 | 说明 |
|---|---|---|
| ID | `t.id` | 交易唯一标识 |
| 日期 | `t.date` | 交易日期 |
| 方向 | 🟢 买 / 🔴 卖 | `t.side == 'BUY'` 判断 |
| 代码 | `<code>` 样式 | 股票代码 |
| 名称 | `t.name` | 股票名称 |
| 股数 | `t.shares` | 交易数量 |
| 价格 | ¥xx.xx | 成交价 |
| 备注 | `t.note` | 盈亏或手动备注 |
| 状态 | `已成交` | 只读显示 |

---

## 状态机流程图

### 板块 Treemap → 成分股弹窗 → 自选股切换

```
 页面加载
    │
    ▼
 loadTreemap('sector')
    │
    ├─ fetch /api/boards?type=sector
    ├─ drawTreemap(boards)
    │
    ▼
 [用户点击 Canvas 矩形]
    │
    ▼
 showStocks(code, name)
    │
    ├─ fetch /api/board/<code>/stocks
    ├─ 渲染成分股弹窗（每行带 +/- 按钮）
    │
    ▼
 [用户点击 + 按钮]
    │
    ▼
 toggleWatchlist(code, btn)
    │
    ├─ POST /api/watchlist/toggle {code}
    ├─ watchlistCodes.add(code)
    ├─ btn 变为 .btn-wl-remove（红色 −）
    │
    ▼
 reloadWatchlist()
    │
    ├─ fetch /api/watchlist/stocks
    └─ 自选股表格刷新，新股票出现
```

### 自选股 添加 / 删除

```
 [成分股弹窗点击 + 按钮]
    │
    ▼
 toggleWatchlist(code, btn)
    │
    ├─ POST /api/watchlist/toggle {code}
    ├─ watchlistCodes.add(code)
    │
    ▼
 reloadWatchlist()
    │
    └─ 表格刷新，新行出现（含 买入 / − / 分析 按钮）


 [点击自选股行末 − 按钮]
    │
    ▼
 removeFromWatchlist(code)
    │
    ├─ POST /api/watchlist/toggle {code}
    ├─ watchlistCodes.delete(code)
    │
    ▼
 reloadWatchlist()
    │
    └─ 表格刷新，该行消失


[点击自选股行末"分析"按钮]
   │
   ▼
showWatchlistAnalysis(code)
   │
   ├─ fetch /api/watchlist/analyze/<code>
   ├─ 按策略渲染评分与触发状态
   │
   └─ 弹出 #analysis-modal
```

### 持仓 买入 / 卖出 + 资金同步

```
 [点击"+ 添加" 或 自选股"买入"]
    │
    ▼
 showAddForm() / showAddForCode(code, price)
    │
    ├─ 买入表单展开，预填 code + price
    ├─ 用户填写 shares
    │
    ▼
 [提交表单]
    │
    ├─ POST /position/add
    ├─ 后端校验 available_funds
    ├─ pf.add_position + pf.add_trade
    ├─ funds.deduct_on_buy
    ├─ redirect → GET /
    │
    └─ 持仓表刷新，新行出现


 [点击持仓行"卖"按钮]
    │
    ▼
 showSellForm(code, held, currentPrice)
    │
    ├─ 卖出弹窗出现
    ├─ 用户调整 price / shares
    ├─ updatePreview() 实时计算卖出金额
    │
    ▼
 [提交表单]
    │
    ├─ POST /position/sell/<code>
    ├─ pf.sell_position + pf.add_trade
    ├─ funds.add_on_sell
    ├─ redirect → GET /
    │
    └─ 持仓表刷新
```

### 充值 / 提现

```
[点击 充值 / 提现]
   │
   ▼
showTopupModal() / showWithdrawModal()
   │
   ▼
doTopup() / doWithdraw()
   │
   ├─ POST /api/funds/add 或 /api/funds/withdraw
   └─ 成功后刷新页面
```

### Tab 切换（行业 ↔ 概念）

```
 [点击"行业板块" 或 "概念板块"]
    │
    ▼
 switchTab(type)
    │
    ├─ currentBoardType = type
    ├─ 更新 .tab-btn.active 样式
    │
    ▼
 loadTreemap(type)
    │
    ├─ fetch /api/boards?type=<type>
    ├─ drawTreemap(boards)
    │
    └─ Canvas 重新绘制
```

---

## JS 函数速查表

| 函数 | 触发方式 | 作用 | 调用的 API |
|---|---|---|---|
| `location.reload()` | Navbar 刷新按钮 | 整页重载 | GET / |
| `refreshLastRefresh()` | 页面加载 + interval | 刷新顶部时间 | 无 |
| `reloadMarketStatus()` | 页面加载 | 拉取市场状态 | `/api/market_status` |
| `reloadStrategyStatus()` | 页面加载 | 拉取策略状态 | `/api/strategy_status` |
| `reloadSystemLog()` | 页面加载 + 10s interval | 拉取系统日志 | `/api/system_log` |
| `switchTab(type)` | Tab 按钮点击 | 切换行业/概念 | `/api/boards?type=` |
| `loadTreemap(type)` | `switchTab()` / 页面加载 | 拉取板块数据并绘 Canvas | `/api/boards?type=` |
| `drawTreemap(items)` | `loadTreemap()` | Canvas 绘制 Treemap 矩形 | 无（纯渲染） |
| `showStocks(code, name)` | Canvas 矩形点击 | 弹出成分股弹窗 | `/api/board/<code>/stocks` |
| `closeStockModal()` | 弹窗关闭按钮 | 关闭成分股弹窗 | 无 |
| `toggleWatchlist(code, btn)` | 成分股弹窗 +/- 按钮 | 加入/移出自选，切换按钮样式 | `/api/watchlist/toggle` |
| `reloadWatchlist()` | 多处触发 | 刷新自选股表格 | `/api/watchlist/stocks` |
| `removeFromWatchlist(code)` | 自选股行 − 按钮 | 移出自选股 | `/api/watchlist/toggle` |
| `escapeHtml(value)` | JS 动态渲染文本前调用 | 转义弹窗表格中的策略说明 | 无 |
| `showWatchlistAnalysis(code)` | 自选股行"分析" | 打开策略评分弹窗 | `/api/watchlist/analyze/<code>` |
| `closeAnalysisModal()` | 策略分析弹窗"关闭" | 关闭策略分析弹窗 | 无 |
| `toggleTrades()` | 交易历史标题点击 | 展开/收起交易历史 | 无 |
| `onCategoryChange()` | 大类筛选变化 | 重建策略筛选下拉 | 无 |
| `applyFilter()` | 策略筛选变化 | 过滤买入信号列表 | 无 |
| `showAddForm()` | 持仓区"+ 添加" | 展开买入表单 | 无 |
| `hideAddForm()` | 买入表单"取消" | 收起买入表单 | 无 |
| `showAddForCode(code, price)` | 自选股行"买入" | 展开买入表单并预填 | 无 |
| `showSellForm(code, held, price)` | 持仓行"卖" | 打开卖出弹窗 | 无（表单 action） |
| `closeSell()` | 卖出弹窗"取消" | 关闭卖出弹窗 | 无 |
| `updatePreview()` | 卖出弹窗输入变化 | 实时计算卖出金额预览 | 无 |
| `deleteTrade(id)` | 交易历史行"删" | 确认后删除交易 | `/trade/delete/<id>` |
| `showTopupModal()` / `closeTopup()` | 充值按钮/取消 | 显示或关闭充值弹窗 | 无 |
| `doTopup()` | 充值确认 | 调用充值 API | `/api/funds/add` |
| `showWithdrawModal()` / `closeWithdraw()` | 提现按钮/取消 | 显示或关闭提现弹窗 | 无 |
| `doWithdraw()` | 提现确认 | 调用提现 API | `/api/funds/withdraw` |

---

## CSS 类速查

| 类名 | 用途 | 关键样式 |
|---|---|---|
| `.navbar` | 顶部导航栏 | flex，半透明黑底 |
| `.container` | 内容区 | max-width 1200px，居中 |
| `.cards` | 顶部四卡片容器 | grid auto-fit |
| `.cards-7` | 顶部七卡片布局 | grid 7 列 |
| `.card` | 单张卡片 | 圆角 8px，半透明背景 |
| `.card.green` / `.card.red` | 盈亏卡片 | 绿/红边框 |
| `.row` | 左右并排容器 | grid 1fr 1fr |
| `.box` | 通用区块 | 圆角 8px，半透明背景 |
| `.badge.green` / `.badge.red` | 计数徽章 | 圆角 10px |
| `.signal` | 信号卡片 | 深色底，圆角 6px |
| `.signal.sig-urgent` | 紧急信号 | 红色边框 |
| `.sig-head` | 信号头部 | flex 左右分布 |
| `.urgency-tag` / `.strat-tag` | 标签 | 圆角 4px，小字 |
| `.tab-btn` / `.tab-btn.active` | Tab 切换按钮 | 灰色 → 青色高亮 |
| `.btn-del` | 自选股删除按钮 | 圆形 22×22，红色 − |
| `.btn-wl-add` / `.btn-wl-remove` | 成分股弹窗 +/- | 圆形 24×24 |
| `.btn-topup` / `.btn-withdraw` | 充值/提现按钮 | 黄/红色按钮 |
| `.modal` | 弹窗遮罩 | fixed 全屏，半透明黑 |
| `.modal-content` | 弹窗内容 | 深色卡片 |
| `.modal-subtitle` | 弹窗副标题 | 灰色小字 |
| `.analysis-modal-content` | 自选股策略分析弹窗 | 宽屏弹窗 |
| `.analysis-table` | 策略分析结果表 | 第 5 列加宽 |
| `.analysis-desc` | 策略描述 | 灰色小字 |
| `.analysis-hit` / `.analysis-miss` | 分析结果状态 | 触发/未触发标签 |
| `.form` | 表单容器 | flex，gap 8px |
| `.held-tag` | 已持仓标签 | 灰色圆角标签 |
| `.flash-success` / `.flash-error` | 消息条 | 绿/红半透明底 |
| `.strat-status.run` / `.strat-status.stop` | 策略状态 | 运行/停机颜色 |
| `.log-table` / `.lvl-*` | 系统日志 | 小字 + 级别标签 |
