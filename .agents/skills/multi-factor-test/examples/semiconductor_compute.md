# 经典案例：半导体与算力 10 股多因子打分实战 (Semiconductor & Compute Case)

本示例展示了在 2026年6月19日 运行升级重构后的多因子流水线对 10 只核心科技成长股进行板块归类、双通道落盘及多因子打分排序的真实执行细节。本案例可作为未来进行任意主题板块多因子验证的标准参考范本。

---

## 一、 经典案例 10 只成分股明细

| 证券代码 | 股票名称 | 所属主题 | 传统分类 (Sector) | 市场大类 (Market) | 涨跌停限制 (Limit) |
|:---|:---|:---|:---|:---|:---|
| `sh600460` | 士兰微 | `theme:semiconductor` | 半导体 | 沪市主板 (`market:sh_main`) | 10% 限制 (`limit:10cm`) |
| `sz002371` | 北方华创 | `theme:semiconductor` | 半导体 | 深市主板 (`market:sz_main`) | 10% 限制 (`limit:10cm`) |
| `sh603501` | 韦尔股份 | `theme:semiconductor` | 半导体 | 沪市主板 (`market:sh_main`) | 10% 限制 (`limit:10cm`) |
| `sh603986` | 兆易创新 | `theme:semiconductor` | 半导体 | 沪市主板 (`market:sh_main`) | 10% 限制 (`limit:10cm`) |
| `sz002049` | 紫光国微 | `theme:semiconductor` | 半导体 | 深市主板 (`market:sz_main`) | 10% 限制 (`limit:10cm`) |
| `sz000977` | 浪潮信息 | `theme:compute` | 算力 | 深市主板 (`market:sz_main`) | 10% 限制 (`limit:10cm`) |
| `sh603019` | 中科曙光 | `theme:compute` | 算力 | 沪市主板 (`market:sh_main`) | 10% 限制 (`limit:10cm`) |
| `sh601138` | 工业富联 | `theme:compute` | 算力 | 沪市主板 (`market:sh_main`) | 10% 限制 (`limit:10cm`) |
| `sz000938` | 紫光股份 | `theme:compute` | 算力 | 深市主板 (`market:sz_main`) | 10% 限制 (`limit:10cm`) |
| `sz000034` | 神州数码 | `theme:compute` | 算力 | 深市主板 (`market:sz_main`) | 10% 限制 (`limit:10cm`) |

---

## 二、 全流程操作命令与物理落盘详情

### 1. 执行物理数据拉取与多渠道落盘
执行以下 Bash 命令，同步拉取 2025-06-19 到 2026-06-19 一年周期的日频 K 线。
```bash
python scripts/fetch_hist.py --from 2025-06-19 --to 2026-06-19 sh600460 sz002371 sh603501 sh603986 sz002049 sz000977 sh603019 sh601138 sz000938 sz000034
```

*   **物理数据落盘情况**：
    *   **Parquet 物理列存**：在项目根目录的 `data/parquet/` 文件夹下生成了 10 个 `.parquet` 列存文件（大小在 12.6 KB 到 13.3 KB 之间），每只股票均精准包含 **243 个有效交易日**（紫光国微受停牌影响为 233 个交易日）。
    *   **SQLite 缓存（`rquant.db`）**：批量入库 2420 条 K 线缓存记录。
    *   **标的池注册**：`pool` 表成功注册这 10 只股票，并将标准的 JSON tags 解析完毕。例如 `sh603986` 的标签值为 `["role:trade", "theme:semiconductor", "strategy:factor", "strategy:breakout", "trade:t1", "data:daily", "market:sh_main", "limit:10cm"]`。
    *   **基本面快照（`eastmoney.db`）**：10 只个股的估值与总市值快照全部写入 `financial_snapshot` 表。

---

## 三、 多因子策略打分排序计算报告

使用 `MultiFactor` 策略类对这 10 只已落盘股票的历史数据执行打分，最终输出的降序报告如下：

```json
[
  {
    "code": "sh603986",
    "name": "兆易创新",
    "score": 0.8134032260051787,
    "filtered": false,
    "factors": {
      "M1_momentum_20d": 1.0,
      "M2_momentum_60d": 1.0,
      "T1_ma20_bias": 0.9998842590720576,
      "T2_ma_alignment": 1.0,
      "T3_breakout_60d": 0.7573839662447259,
      "V1_vol_ratio": 0.3448035885419125,
      "V2_vol_price_sync": 1.0,
      "V3_volatility": -0.528384626406239
    },
    "weighted_components": {
      "M1_momentum_20d": 0.2,
      "M2_momentum_60d": 0.15,
      "T1_ma20_bias": 0.1199861110886469,
      "T2_ma_alignment": 0.1,
      "T3_breakout_60d": 0.09845991561181437,
      "V1_vol_ratio": 0.0413764306250295,
      "V2_vol_price_sync": 0.13,
      "V3_volatility": -0.02641923132031195
    },
    "rank": 1,
    "rank_pct": 0.1
  },
  {
    "code": "sh601138",
    "name": "工业富联",
    "score": 0.672500961912537,
    "filtered": false,
    "factors": {
      "M1_momentum_20d": 1.0,
      "M2_momentum_60d": 1.0,
      "T1_ma20_bias": 0.8614652157609248,
      "T2_ma_alignment": -0.3,
      "T3_breakout_60d": 0.1912889935256027,
      "V1_vol_ratio": 0.9309250931252098,
      "V2_vol_price_sync": 1.0,
      "V3_volatility": -0.3490688862425472
    },
    "weighted_components": {
      "M1_momentum_20d": 0.2,
      "M2_momentum_60d": 0.15,
      "T1_ma20_bias": 0.10337582589131097,
      "T2_ma_alignment": -0.03,
      "T3_breakout_60d": 0.02486756915832835,
      "V1_vol_ratio": 0.11171101117502517,
      "V2_vol_price_sync": 0.13,
      "V3_volatility": -0.01745344431212736
    },
    "rank": 2,
    "rank_pct": 0.2
  },
  {
    "code": "sh600460",
    "name": "士兰微",
    "score": 0.666733780709775,
    "filtered": false,
    "factors": {
      "M1_momentum_20d": 1.0,
      "M2_momentum_60d": 1.0,
      "T1_ma20_bias": 0.9991462888730069,
      "T2_ma_alignment": 1.0,
      "T3_breakout_60d": 0.8146410136086346,
      "V1_vol_ratio": 0.16179485991572456,
      "V2_vol_price_sync": 0.0,
      "V3_volatility": -0.5696497782799055
    },
    "weighted_components": {
      "M1_momentum_20d": 0.2,
      "M2_momentum_60d": 0.15,
      "T1_ma20_bias": 0.11989755466476083,
      "T2_ma_alignment": 0.1,
      "T3_breakout_60d": 0.1059033317691225,
      "V1_vol_ratio": 0.019415383189886948,
      "V2_vol_price_sync": 0.0,
      "V3_volatility": -0.028482488913995276
    },
    "rank": 3,
    "rank_pct": 0.3
  },
  {
    "code": "sz002371",
    "name": "北方华创",
    "score": 0.6181248613971874,
    "filtered": false,
    "factors": {
      "M1_momentum_20d": 0.8755788171767298,
      "M2_momentum_60d": 1.0,
      "T1_ma20_bias": 0.9806385525629616,
      "T2_ma_alignment": 1.0,
      "T3_breakout_60d": 0.8250395159971653,
      "V1_vol_ratio": -0.11745461645526725,
      "V2_vol_price_sync": 0.0,
      "V3_volatility": -0.3565622290142669
    },
    "weighted_components": {
      "M1_momentum_20d": 0.17511576343534596,
      "M2_momentum_60d": 0.15,
      "T1_ma20_bias": 0.11767662630755539,
      "T2_ma_alignment": 0.1,
      "T3_breakout_60d": 0.1072551370796315,
      "V1_vol_ratio": -0.01409455397463207,
      "V2_vol_price_sync": 0.0,
      "V3_volatility": -0.017828111450713346
    },
    "rank": 4,
    "rank_pct": 0.4
  },
  {
    "code": "sz002049",
    "name": "紫光国微",
    "score": 0.26148815655696156,
    "filtered": false,
    "factors": {
      "M1_momentum_20d": 0.32096546411606086,
      "M2_momentum_60d": 0.712762933484935,
      "T1_ma20_bias": 0.616251458197366,
      "T2_ma_alignment": -0.3,
      "T3_breakout_60d": -0.020886853568636177,
      "V1_vol_ratio": 0.31084602593081184,
      "V2_vol_price_sync": 0.25824082707884577,
      "V3_volatility": -0.43454181881398973
    },
    "weighted_components": {
      "M1_momentum_20d": 0.06419309282321217,
      "M2_momentum_60d": 0.10691444002274025,
      "T1_ma20_bias": 0.07395017498368392,
      "T2_ma_alignment": -0.03,
      "T3_breakout_60d": -0.002715290963922703,
      "V1_vol_ratio": 0.03730152311169742,
      "V2_vol_price_sync": 0.03357130752024995,
      "V3_volatility": -0.021727090940699488
    },
    "rank": 5,
    "rank_pct": 0.5
  },
  {
    "code": "sh603019",
    "name": "中科曙光",
    "score": 0.030687177411943028,
    "filtered": false,
    "factors": {
      "M1_momentum_20d": -0.4900804289544225,
      "M2_momentum_60d": 0.2936962750716332,
      "T1_ma20_bias": 0.45792882961171194,
      "T2_ma_alignment": -0.3,
      "T3_breakout_60d": -0.5542857142857136,
      "V1_vol_ratio": 0.4607166804798284,
      "V2_vol_price_sync": 0.7507864566358431,
      "V3_volatility": -0.4226747154883827
    },
    "weighted_components": {
      "M1_momentum_20d": -0.0980160857908845,
      "M2_momentum_60d": 0.04405444126074498,
      "T1_ma20_bias": 0.054951459553405434,
      "T2_ma_alignment": -0.03,
      "T3_breakout_60d": -0.07205714285714276,
      "V1_vol_ratio": 0.0552860016575794,
      "V2_vol_price_sync": 0.0976022393626596,
      "V3_volatility": -0.021133735774419137
    },
    "rank": 6,
    "rank_pct": 0.6
  },
  {
    "code": "sz000977",
    "name": "浪潮信息",
    "score": 0.00619670432634593,
    "filtered": false,
    "factors": {
      "M1_momentum_20d": -0.0980244307042688,
      "M2_momentum_60d": 0.5176470588235293,
      "T1_ma20_bias": 0.6210203922757142,
      "T2_ma_alignment": -0.3,
      "T3_breakout_60d": -0.7398414894955336,
      "V1_vol_ratio": 0.14235815647046704,
      "V2_vol_price_sync": 0.0,
      "V3_volatility": -0.34543001142904145
    },
    "weighted_components": {
      "M1_momentum_20d": -0.01960488614085376,
      "M2_momentum_60d": 0.0776470588235294,
      "T1_ma20_bias": 0.0745224470730857,
      "T2_ma_alignment": -0.03,
      "T3_breakout_60d": -0.09617939363441938,
      "V1_vol_ratio": 0.017082978776456044,
      "V2_vol_price_sync": 0.0,
      "V3_volatility": -0.017271500571452072
    },
    "rank": 7,
    "rank_pct": 0.7
  },
  {
    "code": "sz000938",
    "name": "紫光股份",
    "score": -0.2652879668481761,
    "filtered": false,
    "factors": {
      "M1_momentum_20d": -0.6153846153846154,
      "M2_momentum_60d": 0.2425515660809774,
      "T1_ma20_bias": -0.10363655540157264,
      "T2_ma_alignment": -0.3,
      "T3_breakout_60d": -1.0,
      "V1_vol_ratio": 0.10258451607594936,
      "V2_vol_price_sync": 0.0,
      "V3_volatility": -0.36935067928649723
    },
    "weighted_components": {
      "M1_momentum_20d": -0.12307692307692308,
      "M2_momentum_60d": 0.03638273491214661,
      "T1_ma20_bias": -0.012436386648188717,
      "T2_ma_alignment": -0.03,
      "T3_breakout_60d": -0.13,
      "V1_vol_ratio": 0.012310141929113923,
      "V2_vol_price_sync": 0.0,
      "V3_volatility": -0.01846753396432486
    },
    "rank": 8,
    "rank_pct": 0.8
  },
  {
    "code": "sz000034",
    "name": "神州数码",
    "score": -0.38440949746834785,
    "filtered": false,
    "factors": {
      "M1_momentum_20d": -0.5105319528739749,
      "M2_momentum_60d": -1.0,
      "T1_ma20_bias": 0.6901725533529802,
      "T2_ma_alignment": -0.3,
      "T3_breakout_60d": -1.0,
      "V1_vol_ratio": -0.14312458162745295,
      "V2_vol_price_sync": 0.0,
      "V3_volatility": -0.7589772700123222
    },
    "weighted_components": {
      "M1_momentum_20d": -0.10210639057479498,
      "M2_momentum_60d": -0.15,
      "T1_ma20_bias": 0.08282070640235763,
      "T2_ma_alignment": -0.03,
      "T3_breakout_60d": -0.13,
      "V1_vol_ratio": -0.017174949795294353,
      "V2_vol_price_sync": 0.0,
      "V3_volatility": -0.03794886350061611
    },
    "rank": 9,
    "rank_pct": 0.9
  },
  {
    "code": "sh603501",
    "name": "韦尔股份",
    "score": -0.6377273390058528,
    "filtered": false,
    "factors": {
      "M1_momentum_20d": -1.0,
      "M2_momentum_60d": -0.6557218734910669,
      "T1_ma20_bias": -0.8031315269570607,
      "T2_ma_alignment": -1.0,
      "T3_breakout_60d": -0.7526812723439367,
      "V1_vol_ratio": -0.10946467584306761,
      "V2_vol_price_sync": 0.0,
      "V3_volatility": -0.6401789648293129
    },
    "weighted_components": {
      "M1_momentum_20d": -0.2,
      "M2_momentum_60d": -0.09835828102366004,
      "T1_ma20_bias": -0.09637578323484727,
      "T2_ma_alignment": -0.1,
      "T3_breakout_60d": -0.09784856540471178,
      "V1_vol_ratio": -0.013135761101168113,
      "V2_vol_price_sync": 0.0,
      "V3_volatility": -0.03200894824146565
    },
    "rank": 10,
    "rank_pct": 1.0
  }
]
```

### 极强势代表分析：兆易创新 (`sh603986`)
*   **总分 (Score)**: `0.813` (🔴 **极强势，触发买入**)
*   **主力动能**: 20日/60日超强动量满分(`1.0`)，中长期主升浪成型。
*   **趋势形态**: 价格在 MA20 之上高位平稳运行 (`T1=0.999`)，且均线呈最标准的经典多头排列形态 (`T2=1.0`)，创 60 日新高后正在向上突破盘整平台。
*   **主力资金**: 量比温和偏强且与大涨共振 (`V2=1.0`)，主力明显有规模性建仓吸筹迹象。
