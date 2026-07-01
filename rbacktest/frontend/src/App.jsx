import { useState } from 'react';
import ParamPanel from './components/ParamPanel';
import { MenuIcon, CloseIcon, GripIcon } from './components/Icons';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine, Legend,
} from 'recharts';
import './App.css';

/* ------------------------------------------------------------------ */
/*  Constants                                                         */
/* ------------------------------------------------------------------ */

const STRATEGY_COLORS = ['#cf1322', '#1890ff', '#722ed1'];

const STRATEGY_LABELS = {
  equal_weight: '动量轮动',
  grid_martingale: '网格马丁格尔',
  vp_breakout: '量价突破',
};

const METRIC_ROWS = [
  { key: 'total_return',          label: '总收益率',   fmt: v => `${v.toFixed(2)}%`, better: 'higher' },
  { key: 'annual_return',         label: '年化收益率', fmt: v => `${v.toFixed(2)}%`, better: 'higher' },
  { key: 'max_ddpercent',         label: '最大回撤',   fmt: v => `${v.toFixed(2)}%`, better: 'lower'  },
  { key: 'sharpe_ratio',          label: '夏普比率',   fmt: v => v.toFixed(2),        better: 'higher' },
  { key: 'end_balance',           label: '结束资金',   fmt: v => `¥${Number(v).toLocaleString()}`, better: 'higher' },
  { key: 'total_trade_count',     label: '总成交笔数', fmt: v => v,                  better: 'neutral'},
  { key: 'total_days',            label: '总交易日',   fmt: v => v,                  better: 'neutral'},
  { key: 'profit_days',           label: '盈利天数',   fmt: v => v,                  better: 'higher' },
  { key: 'loss_days',             label: '亏损天数',   fmt: v => v,                  better: 'lower'  },
  { key: 'total_commission',      label: '总手续费',   fmt: v => `¥${Number(v).toFixed(2)}`, better: 'lower'  },
  { key: 'return_drawdown_ratio', label: '收益回撤比', fmt: v => v.toFixed(2),        better: 'higher' },
];

const CHART_TYPES = [
  { key: 'return',   label: '收益率曲线' },
  { key: 'drawdown', label: '回撤曲线'   },
  { key: 'capital',  label: '资金变化'   },
];

/* ------------------------------------------------------------------ */
/*  Helpers                                                           */
/* ------------------------------------------------------------------ */

/** Find the index of the "best" value (highest or lowest) in an array. */
function bestIndex(values, better) {
  if (better === 'higher') {
    let best = -Infinity, idx = -1;
    values.forEach((v, i) => { if (v > best) { best = v; idx = i; } });
    return idx;
  }
  if (better === 'lower') {
    let best = Infinity, idx = -1;
    values.forEach((v, i) => { if (v < best) { best = v; idx = i; } });
    return idx;
  }
  return -1;
}

/**
 * Merge daily data from multiple strategies into a single Recharts-ready array.
 * @param {Object} stratResults - { strategyName: { daily: [...] } }
 * @param {Function} fn - (dailyRecord, capitalRef) => number
 * @param {number} capitalRef - reference capital for return/pnl calculations
 */
function mergeMultiSeries(stratResults, fn, capitalRef) {
  const allDates = new Set();
  const seriesMap = {};
  const snames = Object.keys(stratResults);

  snames.forEach(sn => {
    seriesMap[sn] = {};
    (stratResults[sn].daily || []).forEach(d => {
      allDates.add(d.date);
      seriesMap[sn][d.date] = fn(d, capitalRef);
    });
  });

  return [...allDates].sort().map(d => {
    const row = { date: d };
    snames.forEach(sn => { row[STRATEGY_LABELS[sn] || sn] = seriesMap[sn][d] ?? null; });
    return row;
  });
}

/* ------------------------------------------------------------------ */
/*  App component                                                     */
/* ------------------------------------------------------------------ */

export default function App() {
  const [results, setResults] = useState(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [chartOrder, setChartOrder] = useState(['return', 'drawdown', 'capital']);
  const [dragIdx, setDragIdx] = useState(null);

  const stratNames = results ? Object.keys(results.results) : [];
  const capitalRef = stratNames.length > 0
    ? results.results[stratNames[0]].statistics.capital
    : 1000000;

  /* ---- drag handlers ---- */
  const handleDragStart = (idx) => setDragIdx(idx);
  const handleDragOver = (e) => e.preventDefault();

  const handleDrop = (targetIdx) => {
    if (dragIdx === null || dragIdx === targetIdx) return;
    const next = [...chartOrder];
    const [moved] = next.splice(dragIdx, 1);
    next.splice(targetIdx, 0, moved);
    setChartOrder(next);
    setDragIdx(null);
  };

  const sortedCharts = chartOrder
    .map(key => CHART_TYPES.find(c => c.key === key))
    .filter(Boolean);

  /* ---- inline chart renders (avoid separate files for 3 charts) ---- */

  const renderReturnChart = () => {
    if (stratNames.length === 0) return null;
    const data = mergeMultiSeries(results.results, d => (d.balance / capitalRef - 1) * 100, capitalRef);

    return (
      <ResponsiveContainer width="100%" height={400}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="date" tick={{ fontSize: 11 }} interval="preserveStartEnd" minTickGap={40} />
          <YAxis tick={{ fontSize: 11 }} tickFormatter={v => `${v.toFixed(2)}%`} />
          <Tooltip formatter={(v, name) => [`${Number(v).toFixed(4)}%`, name]} />
          <ReferenceLine y={0} stroke="#666" strokeDasharray="3 3" />
          <Legend />
          {stratNames.map((sn, i) => (
            <Line key={sn} type="monotone" dataKey={STRATEGY_LABELS[sn] || sn}
                  stroke={STRATEGY_COLORS[i % STRATEGY_COLORS.length]} strokeWidth={2} dot={false} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    );
  };

  const renderDrawdownChart = () => {
    if (stratNames.length === 0) return null;
    const data = mergeMultiSeries(results.results, d => d.ddpercent, capitalRef);

    return (
      <ResponsiveContainer width="100%" height={400}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="date" tick={{ fontSize: 11 }} interval="preserveStartEnd" minTickGap={40} />
          <YAxis tick={{ fontSize: 11 }} tickFormatter={v => `${v.toFixed(2)}%`} domain={['auto', 0]} />
          <Tooltip formatter={(v, name) => [`${Number(v).toFixed(3)}%`, name]} />
          <Legend />
          {stratNames.map((sn, i) => (
            <Line key={sn} type="monotone" dataKey={STRATEGY_LABELS[sn] || sn}
                  stroke={STRATEGY_COLORS[i % STRATEGY_COLORS.length]} strokeWidth={2} dot={false} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    );
  };

  const renderCapitalChart = () => {
    if (stratNames.length === 0) return null;

    const data = mergeMultiSeries(results.results, d => d.balance - capitalRef, capitalRef);

    return (
      <ResponsiveContainer width="100%" height={400}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="date" tick={{ fontSize: 11 }} interval="preserveStartEnd" minTickGap={40} />
          <YAxis tick={{ fontSize: 11 }} tickFormatter={v => `¥${(v / 10000).toFixed(0)}万`} />
          <Tooltip formatter={(v, name) => [`¥${Number(v).toLocaleString()}`, name]} />
          <ReferenceLine y={0} stroke="#666" strokeDasharray="3 3" />
          <Legend />
          {stratNames.map((sn, i) => (
            <Line key={sn} type="monotone" dataKey={STRATEGY_LABELS[sn] || sn}
                  stroke={STRATEGY_COLORS[i % STRATEGY_COLORS.length]} strokeWidth={2} dot={false} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    );
  };

  /* ---- render ---- */
  return (
    <div className="app">
      <header className="app-header">
        <button
          className="sidebar-toggle"
          onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
          title={sidebarCollapsed ? '展开参数面板' : '收起参数面板'}
        >
          {sidebarCollapsed ? <MenuIcon /> : <CloseIcon />}
        </button>
        <h1>量化回测系统</h1>
        <span className="subtitle">VNPY + Flask + React</span>
      </header>

      <main className="app-main">
        <aside className={`sidebar ${sidebarCollapsed ? 'collapsed' : ''}`}>
          {!sidebarCollapsed && <ParamPanel onResults={setResults} />}
        </aside>

        <section className="content">
          {!results && (
            <div className="placeholder">
              <p>请在左侧选择回测参数，然后点击运行回测</p>
            </div>
          )}

          {results && stratNames.length > 0 && (
            <div className="results">
              {/* ----- comparison table ----- */}
              <div className="chart-wrapper">
                <h3>策略对比</h3>
                <div className="compare-table-wrap">
                  <table className="compare-table">
                    <thead>
                      <tr>
                        <th>指标</th>
                        {stratNames.map((sn, i) => (
                          <th key={sn}>
                            <span className="strategy-dot"
                                  style={{ background: STRATEGY_COLORS[i % STRATEGY_COLORS.length] }} />
                            {STRATEGY_LABELS[sn] || sn}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {METRIC_ROWS.map(row => {
                        const values = stratNames.map(sn => results.results[sn].statistics[row.key]);
                        const best = bestIndex(values, row.better);
                        return (
                          <tr key={row.key}>
                            <td className="metric-label">{row.label}</td>
                            {values.map((v, i) => (
                              <td key={i} className={i === best && stratNames.length > 1 ? 'best' : ''}>
                                {row.fmt(v)}
                              </td>
                            ))}
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="chart-sort-bar">
                <span className="sort-hint">拖动图表可调整顺序</span>
              </div>

              {/* ----- draggable charts ----- */}
              {sortedCharts.map(({ key, label }, idx) => (
                <div
                  key={key}
                  className={`chart-slot ${dragIdx === idx ? 'dragging' : ''}`}
                  draggable
                  onDragStart={() => handleDragStart(idx)}
                  onDragOver={handleDragOver}
                  onDrop={() => handleDrop(idx)}
                  onDragEnd={() => setDragIdx(null)}
                >
                  <div className="chart-handle" title="拖动排序">
                    <GripIcon /> {label}
                  </div>
                  <div className="chart-wrapper">
                    {key === 'return'   && renderReturnChart()}
                    {key === 'drawdown' && renderDrawdownChart()}
                    {key === 'capital'  && renderCapitalChart()}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
