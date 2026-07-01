# Qlib → vnpy 数据获取与转换完整流程

## 概述

从零开始：下载 A 股日线数据 → Qlib 导出 Parquet → vnpy AlphaLab 格式，全流程文档。

## 流程图

```
┌─────────────────────────────────────────────────────────────┐
│  阶段一：获取原始数据                              ~5 分钟   │
│                                                             │
│  GitHub Release (chenditc/investment_data)  837 MB 下载      │
│  ↓ wget + tar                                               │
│  ~/.qlib/qlib_data/cn_data/                                 │
│  ├── features/{股票}/{字段}.day.bin    ← numpy float32 二进制│
│  ├── calendars/day.txt                ← 交易日历            │
│  └── instruments/{all,csi300,...}.txt  ← 股票池              │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  阶段二：Qlib 导出为 Parquet（中间格式）          ~20 分钟   │
│                                                             │
│  qlib.init() → D.features() → pandas DataFrame               │
│  ↓ polars cast                                               │
│  qlib_daily.parquet（单个文件，859 MB）                       │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  阶段三：转换为 vnpy AlphaLab 格式               ~6 分钟     │
│                                                             │
│  duckdb 列映射 + polars datetime 修正                        │
│  ↓                                                          │
│  research/daily/{代码}.{交易所}.parquet   ← 6,110 个文件     │
│  research/contract.json                 ← 交易费率配置       │
└─────────────────────────────────────────────────────────────┘
```

**总耗时：约 30 分钟**（含 wget 下载，不含 Qlib 安装）

---

## 阶段一：获取 A 股日线数据（Qlib 格式）

### 1.1 数据源

社区每日更新数据（推荐）：
- 仓库: `chenditc/investment_data`
- 地址: `https://github.com/chenditc/investment_data/releases/latest/download/qlib_bin.tar.gz`
- 覆盖：沪/深/北交所，6100+ 标的，2000-01-04 ~ 昨天

官方预打包数据（冻结，截止 2020-09-25）：
- `qlib.tests.data.GetData().qlib_data(target_dir='~/.qlib/qlib_data/cn_data', region='cn')`
- 覆盖：沪/深，3875 标的，1999-11-10 ~ 2020-09-25

### 1.2 下载与安装

```bash
# 方式一：社区数据（推荐）
wget https://github.com/chenditc/investment_data/releases/latest/download/qlib_bin.tar.gz
mkdir -p ~/.qlib/qlib_data/cn_data
tar -xzf qlib_bin.tar.gz -C ~/.qlib/qlib_data/cn_data --strip-components=1
rm qlib_bin.tar.gz

# 方式二：官方数据
uv run python3 -c "
from qlib.tests.data import GetData
GetData(delete_zip_file=True).qlib_data(
    name='qlib_data', target_dir='~/.qlib/qlib_data/cn_data', region='cn'
)
"
```

### 1.3 数据目录结构

```
~/.qlib/qlib_data/cn_data/
├── features/                  # 每个标的一个目录
│   └── sz002475/              # 示例：立讯精密
│       ├── close.day.bin      # numpy float32，第 i 个值 = day.txt 第 i 日的收盘价
│       ├── open.day.bin
│       ├── high.day.bin
│       ├── low.day.bin
│       ├── volume.day.bin
│       ├── amount.day.bin     # 成交额
│       ├── vwap.day.bin       # 均价（= amount / volume）
│       ├── adjclose.day.bin   # 后复权收盘价
│       ├── change.day.bin     # 涨跌幅（%）
│       └── factor.day.bin     # 复权因子（累积乘数）
├── calendars/
│   └── day.txt                # 交易日历，每行一个 YYYY-MM-DD
└── instruments/
    ├── all.txt                # 全部标的: 代码\t上市日\t退市日
    ├── csi300.txt             # 沪深300 成分股
    ├── csi500.txt             # 中证500
    ├── csi800.txt             # 中证800
    ├── csi1000.txt            # 中证1000
    └── csiall.txt             # 全A 成分股
```

`.day.bin` 的设计优势：
- 零解析开销：`np.memmap()` 直接映射到内存
- 存一列读一列：要 `close` 就只读 `close.day.bin`，不碰其他字段
- float32 紧凑：6415 天 × 4 字节 = 25 KB / 列 / 股票，全 A 6100 只约 1.3 GB

### 1.4 数据验证

```python
import qlib
from qlib.constant import REG_CN
from qlib.data import D

qlib.init(provider_uri="~/.qlib/qlib_data/cn_data", region=REG_CN)

# 查询单只股票
df = D.features(
    ["sh600519"],
    ["$close", "$open", "$high", "$low", "$volume"],
    start_time="2024-01-01",
    end_time="2024-12-31",
)
print(df.tail())

# 验证交易日历
cal = D.calendar()
print(f"交易日: {len(cal)} 天, {cal[0]} ~ {cal[-1]}")

# 验证标的数量
all_stocks = D.list_instruments(D.instruments(market="all"))
print(f"全A标: {len(all_stocks)} 只")
```

---

## 阶段二：Qlib 导出为 Parquet（单文件中间格式）

### 2.1 为什么需要这个中间步骤

Qlib 原生的 `.day.bin` + `day.txt` 格式只有 Qlib 自己读得懂。vnpy 需要 Parquet 文件。所以先用 Qlib 的 `D.features()` 把所有数据读成 DataFrame，再一次性导出为 Parquet 文件作为中间格式。

### 2.2 导出脚本

```python
"""
export_qlib_to_parquet.py — 从 Qlib 原生格式导出为单个 Parquet 文件
"""
import polars as pl
import qlib
from qlib.constant import REG_CN
from qlib.data import D

# 初始化 Qlib
qlib.init(provider_uri="~/.qlib/qlib_data/cn_data", region=REG_CN)

# 获取全 A 标的
all_stocks = D.list_instruments(
    D.instruments(market="all"), as_list=True
)
print(f"全 A 标的: {len(all_stocks)} 只")

# 分批查询，避免内存溢出
BATCH = 500
all_dfs = []

for i in range(0, len(all_stocks), BATCH):
    batch = all_stocks[i : i + BATCH]
    print(f"  批次 {i//BATCH + 1}: {len(batch)} 只股票")

    # Qlib 字段名 → 导出列名
    df = D.features(
        batch,
        [
            "$open", "$high", "$low", "$close",
            "$volume", "$amount", "$vwap",
            "$factor", "$adjclose", "$change",
        ],
        start_time="2000-01-01",
        end_time="2026-06-30",
    )

    # DataFrame 格式: index 为 (instrument, datetime) MultiIndex
    # 转换为扁平格式
    df = df.reset_index()
    df.rename(columns={"instrument": "stock_id"}, inplace=True)

    # pandas → polars → 追加
    pdf = pl.from_pandas(df)
    all_dfs.append(pdf)

# 合并所有批次
final = pl.concat(all_dfs)
final = final.rename({"date": "date"} if "date" in final.columns else {})

# 最终列顺序
final = final.select([
    "date", "stock_id",
    "open", "high", "low", "close",
    "volume", "amount", "vwap",
    "factor", "adjclose", "change",
])

final.write_parquet("qlib_daily.parquet")
print(f"导出完成: {final.height:,} 行, {final.width} 列")
```

### 2.3 导出后验证

```bash
duckdb -c "
SELECT count(*) AS rows,
       count(DISTINCT stock_id) AS symbols,
       MIN(date) AS first, MAX(date) AS last
FROM 'qlib_daily.parquet'
"
```

---

## 阶段三：转换为 vnpy AlphaLab 格式

### 3.1 列映射规则

| Qlib Parquet 列 | vnpy Parquet 列 | 转换逻辑 |
|-----------------|-----------------|----------|
| `stock_id` | `vt_symbol` | `sh600000` → `600000.SSE`<br>`sz000001` → `000001.SZSE` |
| `date` | `datetime` | 直接映射，后续 cast 为 `pl.Datetime` |
| `open` | `open` | 直接映射 |
| `high` | `high` | 直接映射 |
| `low` | `low` | 直接映射 |
| `close` | `close` | 直接映射 |
| `volume` | `volume` | 直接映射 |
| `amount` | `turnover` | 重命名 |
| — | `open_interest` | 固定填 `0.0` |
| `factor` | 丢弃 | vnpy 不需要复权因子 |
| `adjclose` | 丢弃 | vnpy 不需要 |
| `vwap` | 丢弃 | 可在 `load_bar_df()` 中动态计算 |
| `change` | 丢弃 | 可由 close 实时计算 |

### 3.2 转换脚本

**一个脚本完成全部转换**：

```bash
cd /home/kenshin/github/vnpy
uv run python3 research/backtest_learning/convert_data.py
```

实测耗时（AMD Ryzen, NVMe SSD, Python 3.14）：

| 步骤 | 耗时 | 说明 |
|------|------|------|
| wget 下载 qlib_bin.tar.gz | ~3 分钟 | 837 MB，取决于网速 |
| tar 解压 | ~1 分钟 | 6,110 个目录 × 10 个文件 |
| Qlib 导出 Parquet（阶段二） | ~20 分钟 | 12 批 × 1.5 分钟/批 |
| duckdb 列映射 + 写出 | ~6 分钟 | 阶段三，convert_data.py |
| polars datetime 修正 | ~18 秒 | 6,110 个小文件 |

总耗时约 **30 分钟**（含下载，不含 pip install 依赖）。

脚本自动检测数据来源：
- 如果 `qlib_daily.parquet` 存在 → 直接从此文件转换（最快）
- 如果不存在 → 尝试从 `~/.qlib/qlib_data/cn_data/` 的 Qlib `.bin` 格式导出

执行过程分 4 步，每步都会打印进度：

```
[10:00:01] Step 1/4: 列映射（stock_id → vt_symbol...）
       读取文件: qlib_daily.parquet (859 MB)
       共 6,110 只股票，17,604,990 行数据

[10:00:05] Step 2/4: 写出 Parquet → research/daily/
       清理旧文件 6,110 个...
        610/6110 (10%)
       1221/6110 (20%)
       ...
       6110/6110 (100%)

[10:00:45] Step 3/4: 修正 datetime 列类型（Date → Datetime）
       6110/6110 (100%)

[10:02:30] Step 4/4: 生成合约配置 → research/contract.json
       共 6,110 只股票

=======================================================
  ✅ 转换完成 (150 秒)
  输出: 6,110 个文件 / 467 MB
  目录: research/daily
  配置: research/contract.json
=======================================================
```

### 3.3 vnpy 官方下载方式（对比参考）

vnpy 官方示例通过 `vnpy.trader.datafeed` 从外部数据源（如 RQData、XtQuant）直接下载成 `BarData`，再调用 `lab.save_bar_data()` 保存。

```python
# vnpy 官方方式（以 XtQuant 为例）
from vnpy.alpha import AlphaLab
from vnpy.trader.datafeed import get_datafeed
from vnpy.trader.object import HistoryRequest
from vnpy.trader.constant import Exchange, Interval

lab = AlphaLab("./research")
datafeed = get_datafeed()

req = HistoryRequest("600519", Exchange.SSE, start, end, Interval.DAILY)
bars = datafeed.query_bar_history(req)  # list[BarData]

lab.save_bar_data(bars)                 # 直接写 parquet
lab.add_contract_setting(
    "600519.SSE",
    long_rate=5/10000,
    short_rate=10/10000,
    size=1,
    pricetick=0.01,
)
```

两种方式对比：

| | Qlib 方式 | vnpy 官方方式 |
|---|---|---|
| 数据源 | 社区 GitHub Release | RQData / XtQuant 等商业 API |
| 费用 | 免费 | 需购买数据服务 |
| 覆盖范围 | 全 A 6100+ 只 | 取决于数据源 |
| 更新频率 | 每日 | 取决于数据源 |
| Qlib 生态 | 直接支持 Qlib 回测/模型 | 需要自建 Qlib 桥接 |

---

## 踩坑记录

### 1. datetime 类型不一致

duckdb 的 `date` 类型导出到 Parquet 后是 `pl.Date`。vnpy 的 `load_bar_data()` 创建 `BarData` 时预期 `datetime.datetime`。不修正会报错：

```
AttributeError: 'datetime.date' object has no attribute 'date'
```

修复：`pl.col("datetime").cast(pl.Datetime)`

### 2. contract.json 的 size 参数

vnpy 引擎计算 PnL 时会乘以 `contract["size"]`：
- 期货: `size=300`（IF 合约乘数）
- A 股: `size=1`（1 股 = 1 单位，不是 100 股/手）

误设 `size=100` 会导致 PnL 放大 100 倍，账户瞬间爆仓。

### 3. 数据价格归一化

Qlib 数据将每条 K 线除以首日收盘价（`first_close=1.0`），使所有股票起点一致。这导致：
- ✅ 百分比收益率正确（归一化因子在分子分母抵消）
- ❌ 绝对仓位规模不反映真实购买力

如需真实价格，在导出阶段二时不要传入 `$close`，改传表达式 `${close} * 1`（Qlib 会自动处理，但最终 DataFrame 仍为归一化值）；或在阶段三的 duckdb SQL 中乘以 `adjclose / close`（但会丢失复权信息）。

### 4. 停牌日处理

停牌日 Qlib 数据中 OHLCV 为 NaN 或 0。在阶段二导出时 Qlib 会返回 NaN，在阶段三通过 `WHERE close IS NOT NULL` 过滤。

---

## 文件索引

| 文件 | 作用 |
|------|------|
| `research/backtest_learning/DATA_CONVERSION.md` | 本文档 |
| `research/backtest_learning/convert_qlib_to_vnpy.py` | 阶段三转换脚本（幂等，可重复执行） |
| `qlib_daily.parquet` | 阶段二输出（中间格式，可在 duckdb 中直接查询） |
| `research/daily/*.parquet` | 阶段三输出（vnpy AlphaLab 可直接加载） |
| `research/contract.json` | 合约交易配置 |
| `/home/kenshin/github/RetailQuant/docs/qlib_usage.md` | Qlib 参考文档 |
| `examples/alpha_research/download_data_xt.ipynb` | vnpy 官方数据下载示例 |
