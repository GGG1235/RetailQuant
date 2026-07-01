# rbacktest

基于 VNPY Alpha 引擎的量化回测系统，前端 React + 后端 Flask，支持多策略对比。

## 架构

```
rbacktest/
├── backend/
│   ├── app.py               Flask API 入口
│   ├── backtest_engine.py    VNPY Alpha 回测封装（三种策略）
│   └── requirements.txt      Python 依赖
├── frontend/
│   ├── src/
│   │   ├── App.jsx           主布局：对比表 + 三张图表
│   │   ├── api.js             API 调用层
│   │   ├── components/
│   │   │   ├── ParamPanel.jsx 参数面板（多策略选择、股票筛选）
│   │   │   └── Icons.jsx      SVG 图标
│   │   ├── App.css
│   │   ├── index.css
│   │   └── main.jsx
│   ├── package.json
│   ├── vite.config.js
│   └── index.html
├── tests/
│   ├── conftest.py               共享 fixtures
│   ├── test_momentum_rotation.py 动量轮动策略 (8 tests)
│   ├── test_grid_martingale.py   网格马丁格尔策略 (7 tests)
│   ├── test_vp_breakout.py       量价突破策略 (7 tests)
│   ├── test_engine.py            引擎 & 跨策略 (7 tests)
│   └── test_api.py               REST API (10 tests)
├── start.sh                   一键启动脚本
└── .gitignore
```

## 内置策略

| 策略 | 名称 | 逻辑 |
|------|------|------|
| `equal_weight` | 动量轮动 | 每月初按过去 N 日收益率排序，等权持有前 top_k 只 |
| `grid_martingale` | 网格马丁格尔 | 每日计算滚动网格，低位买入/高位止盈或破网止损 |
| `vp_breakout` | 量价突破 | 突破前N日高点 + 量能放大 + 强势收盘时买入；止盈/止损/破均线卖出 |

前端可同时勾选多个策略，结果以对比表格和叠加折线图展示。

## 数据准备

系统依赖 VNPY AlphaLab 格式的日线数据。在项目根目录下创建 `data/` 目录：

```
data/
├── daily/            # 日线 parquet 文件（必需）
│   ├── 600519.SSE.parquet
│   ├── 000858.SZSE.parquet
│   └── ...
├── contract.json     # 合约交易配置（手续费、每手股数，必需）
├── minute/           # 分钟线（可选，当前未使用）
├── component/        # 指数成分股（可选，当前未使用）
├── signal/           # 因子信号（可选，当前未使用）
├── dataset/          # 数据集定义（可选，当前未使用）
└── model/            # 模型文件（可选，当前未使用）
```

Parquet 文件需包含列：`datetime`, `vt_symbol`, `open`, `high`, `low`, `close`, `volume`, `turnover`。

`contract.json` 格式示例：
```json
{
  "600519.SSE": {
    "long_rate": 0.0005,
    "short_rate": 0.0015,
    "size": 100,
    "pricetick": 0.01
  }
}
```

> `data/` 下的 `minute/`, `component/`, `signal/`, `dataset/`, `model/` 是 VNPY AlphaLab 的标准目录结构，当前回测仅使用 `daily/` 和 `contract.json`，其余目录留空即可。

如果启动时 `data/daily/` 为空或不存在，后端会打印警告但不会崩溃，API 将返回空股票列表。

## 安装与运行

### 后端

```bash
cd rbacktest/backend
uv venv
uv pip install -r requirements.txt
uv pip install vnpy --index-url https://pypi.tuna.tsinghua.edu.cn/simple
.venv/bin/python app.py
```

后端运行在 `http://localhost:5000`。

### 前端

```bash
cd rbacktest/frontend
npm install
npm run dev
```

前端运行在 `http://localhost:5173`，通过 Vite proxy 转发 `/api` 请求到后端。

### 一键启动

```bash
chmod +x start.sh
./start.sh
```

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/stocks` | 获取可用股票列表 |
| GET | `/api/strategies` | 获取策略元数据（名称、参数schema） |
| POST | `/api/backtest` | 运行回测，支持多策略 |

POST `/api/backtest` 请求示例：

```json
{
  "vt_symbols": ["600519.SSE", "000858.SZSE", "600036.SSE"],
  "start": "2024-06-01",
  "end": "2025-01-01",
  "capital": 1000000,
  "strategies": ["equal_weight", "vp_breakout"],
  "strategy_params": {
    "equal_weight": {"top_k": 3, "lookback": 20, "price_add": 0.01},
    "vp_breakout": {
      "high_n": 11, "vol_ratio_min": 1.5, "close_to_high": 0.97,
      "ma_exit": 10, "take_profit": 0.30, "stop_loss": -0.10,
      "top_k": 5, "cash_ratio": 0.95, "price_add": 0.005
    }
  }
}
```

## 测试

```bash
cd rbacktest
backend/.venv/bin/python -m pytest tests/ -v
```

## 技术栈

- 后端：Python 3.11+, Flask, VNPY Alpha, Polars, NumPy
- 前端：React 18, Vite, Recharts
- 测试：pytest
- 包管理：uv (Python), npm (Node)
