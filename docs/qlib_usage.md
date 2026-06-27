# Qlib A股量化数据平台

微软开源的 AI 量化研究平台，提供高性能数据存储、因子引擎和内置 ML 模型。

## 快速开始

```bash
# 初始化项目
uv init --name quant-qlib
uv add pyqlib@git+https://github.com/microsoft/qlib
uv add numpy pandas requests matplotlib plotly flask

# 下载 A 股数据（两种方式）
# 方式一：社区每日更新数据（推荐，最新到昨天）
wget https://github.com/chenditc/investment_data/releases/latest/download/qlib_bin.tar.gz
tar -xzf qlib_bin.tar.gz -C ~/.qlib/qlib_data/cn_data --strip-components=1
rm qlib_bin.tar.gz

# 方式二：Qlib 官方预打包数据（截止 2020-09-25）
uv run python -c "
from qlib.tests.data import GetData
GetData(delete_zip_file=True).qlib_data(
    name='qlib_data', target_dir='~/.qlib/qlib_data/cn_data', region='cn'
)
"
```

## 数据概览

| 指标 | 社区数据 | 官方数据 |
|------|---------|---------|
| 标的数 | 6,110 | 3,875 |
| 交易日 | 6,415 天 | 4,943 天 |
| 时间范围 | 2000-01-04 ~ 昨天 | 1999-11-10 ~ 2020-09-25 |
| 大小 | 837 MB | 334 MB |
| 市场覆盖 | 沪/深/北交所 | 沪/深 |
| 更新频率 | 每日 | 冻结 |

## 数据格式

```
~/.qlib/qlib_data/cn_data/
├── features/                  # 每个标的一个目录
│   └── sz002475/              # 立讯精密
│       ├── close.day.bin      # 收盘价
│       ├── open.day.bin       # 开盘价
│       ├── high.day.bin       # 最高价
│       ├── low.day.bin        # 最低价
│       ├── volume.day.bin     # 成交量
│       ├── amount.day.bin     # 成交额
│       ├── vwap.day.bin       # 均价
│       ├── adjclose.day.bin   # 后复权收盘价
│       ├── change.day.bin     # 涨跌幅 (%)
│       └── factor.day.bin     # 复权因子
├── calendars/
│   └── day.txt                # 交易日历 (YYYY-MM-DD)
└── instruments/
    ├── all.txt                # 全部标的 (代码\t上市日\t退市日)
    ├── csi300.txt             # 沪深300 成分股
    ├── csi500.txt             # 中证500
    ├── csi800.txt             # 中证800
    ├── csi1000.txt            # 中证1000
    └── csiall.txt             # 全A成分股
```

`.day.bin` 是 numpy float32 二进制数组，第 i 个值对应 `day.txt` 第 i 个交易日。读取时直接 mmap，零解析开销。

## 常用操作

### 初始化

```python
import qlib
from qlib.constant import REG_CN

qlib.init(
    provider_uri="~/.qlib/qlib_data/cn_data",
    region=REG_CN,             # REG_US 则为美股
)

from qlib.data import D
```

### 查询单只股票日线

```python
df = D.features(
    ["sz002475"],              # 标的一览
    ["$close", "$open", "$high", "$low", "$volume", "$vwap"],
    start_time="2025-01-01",
    end_time="2026-06-27",
)
df = df.droplevel("instrument")
print(df.tail())
```

### 查询多只股票 / 指数成分股

```python
# 沪深300全部成分股
df = D.features(
    D.instruments(market="csi300"),
    ["$close", "$volume"],
    start_time="2025-06-01",
    end_time="2025-06-30",
)

# 自定义股票池
df = D.features(
    ["sz002475", "sh600519", "sz000858"],
    ["$close", "$adjclose"],
    start_time="2025-01-01",
    end_time="2025-06-27",
)
```

### 可用因子

```python
"$open"        # 开盘价
"$close"       # 收盘价
"$high"        # 最高价
"$low"         # 最低价
"$volume"      # 成交量
"$amount"      # 成交额
"$vwap"        # 均价
"$adjclose"    # 后复权收盘价
"$change"      # 涨跌幅 (%)
"$factor"      # 复权因子
"$open / 4 + $close * 3 / 4"   # 支持表达式
"Ref($close, 5)"               # 5 日前收盘价
"Mean($close, 20)"             # 20 日均线
"Std($close, 20)"              # 20 日标准差
"$high / $low - 1"             # 振幅
```

### 行情查询

```python
# 交易日历
cal = D.calendar()
print(cal[:5])  # 前5个交易日

# 标的列表
from qlib.data import D
all_stocks = D.list_instruments(D.instruments(market="all"))
print(len(all_stocks))

# 查询某标的上市/退市日期
csi300 = D.list_instruments(
    D.instruments(market="csi300"),
    start_time="2025-01-01",
    as_list=True,
)
```

### 训练 AI 模型

```python
import qlib
from qlib.constant import REG_CN
from qlib.contrib.model.pytorch_lstm import LSTM
from qlib.contrib.data.handler import Alpha158

qlib.init(provider_uri="~/.qlib/qlib_data/cn_data", region=REG_CN)

# 构造 Alpha158 因子集
handler_conf = {
    "start_time": "2010-01-01",
    "end_time": "2020-12-31",
    "fit_start_time": "2010-01-01",
    "fit_end_time": "2017-12-31",
    "instruments": "csi300",
}
dataset = Alpha158(**handler_conf)

# 使用内置 LSTM 模型
model = LSTM(input_dim=158, output_dim=1)
```

### 回测

```bash
# 运行 Qlib 内置工作流
uv run qrun --model_name LightGBM \
    --dataset Alpha158 \
    --market csi300 \
    --benchmark SH000300
```

## 数据更新

```bash
# 社区数据每日更新，重新下载覆盖即可
wget -q https://github.com/chenditc/investment_data/releases/latest/download/qlib_bin.tar.gz
rm -rf ~/.qlib/qlib_data/cn_data/features ~/.qlib/qlib_data/cn_data/calendars ~/.qlib/qlib_data/cn_data/instruments
tar -xzf qlib_bin.tar.gz -C ~/.qlib/qlib_data/cn_data --strip-components=1
rm qlib_bin.tar.gz

# 或使用 qlib 仓库内置的 Yahoo Finance 采集脚本
python ~/github/qlib/scripts/data_collector/yahoo/collector.py \
    update_data_to_bin \
    --qlib_data_1d_dir ~/.qlib/qlib_data/cn_data \
    --region CN --interval 1d
```

## 参考

- [Qlib GitHub](https://github.com/microsoft/qlib)
- [社区数据源](https://github.com/chenditc/investment_data)
- [Qlib 官方文档](https://qlib.readthedocs.io/)
