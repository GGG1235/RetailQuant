import { useState, useEffect } from 'react';
import { fetchStocks, fetchStrategies, runBacktest } from '../api';

const STRATEGY_COLORS = ['#cf1322', '#1890ff', '#722ed1'];

export default function ParamPanel({ onResults }) {
  const [stocks, setStocks] = useState([]);
  const [strategies, setStrategies] = useState([]);
  const [selectedStocks, setSelectedStocks] = useState([]);
  const [selectedStrategies, setSelectedStrategies] = useState([]);
  const [strategyParams, setStrategyParams] = useState({});
  const [startDate, setStartDate] = useState('2024-01-01');
  const [endDate, setEndDate] = useState('2025-12-31');
  const [capital, setCapital] = useState(1000000);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [expandedStrats, setExpandedStrats] = useState({});

  /* ---- initial data load ---- */
  useEffect(() => {
    fetchStocks().then(setStocks);
    fetchStrategies().then(strats => {
      setStrategies(strats);
      if (strats.length === 0) return;
      const first = strats[0].name;
      setSelectedStrategies([first]);
      const defaults = { [first]: {} };
      if (strats[0].params) {
        Object.entries(strats[0].params).forEach(([k, v]) => {
          defaults[first][k] = v.default;
        });
      }
      setStrategyParams(defaults);
    });
  }, []);

  /* ---- toggle handlers ---- */

  const toggleStrategy = (name) => {
    setSelectedStrategies(prev => {
      if (prev.includes(name)) return prev.filter(s => s !== name);
      const next = [...prev, name];
      if (!strategyParams[name]) {
        const strat = strategies.find(s => s.name === name);
        const defaults = {};
        if (strat && strat.params) {
          Object.entries(strat.params).forEach(([k, v]) => { defaults[k] = v.default; });
        }
        setStrategyParams(prevP => ({ ...prevP, [name]: defaults }));
      }
      return next;
    });
  };

  const toggleStock = (sym) => {
    setSelectedStocks(prev =>
      prev.includes(sym) ? prev.filter(s => s !== sym) : [...prev, sym]
    );
  };

  const handleParamChange = (stratName, key, value) => {
    setStrategyParams(prev => ({
      ...prev,
      [stratName]: { ...prev[stratName], [key]: value },
    }));
  };

  /** Parse a numeric input, falling back to the default on empty/NaN. */
  const safeNumeric = (raw, config) => {
    if (raw === '') return config.default;
    const val = config.type === 'int' ? parseInt(raw, 10) : parseFloat(raw);
    return isNaN(val) ? config.default : val;
  };

  /* ---- run backtest ---- */

  const handleRun = async () => {
    if (selectedStocks.length === 0) {
      setError('请至少选择一只股票');
      return;
    }
    if (selectedStrategies.length === 0) {
      setError('请至少选择一个策略');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const result = await runBacktest({
        vt_symbols: selectedStocks,
        start: startDate,
        end: endDate,
        capital: Number(capital),
        strategies: selectedStrategies,
        strategy_params: strategyParams,
      });
      onResults(result);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  /* ---- derived data ---- */

  const selectedSet = new Set(selectedStocks);
  const filteredStocks = stocks.filter(s =>
    s.toLowerCase().includes(searchTerm.toLowerCase())
  );
  const sortedStocks = [
    ...filteredStocks.filter(s => selectedSet.has(s)).sort(),
    ...filteredStocks.filter(s => !selectedSet.has(s)).sort(),
  ];

  /* ---- render ---- */

  return (
    <div className="param-panel">
      <h2>回测参数</h2>

      {error && <div className="error">{error}</div>}

      {/* strategy multi-select */}
      <div className="param-group">
        <label>策略（可多选比较）</label>
        <div className="strategy-list">
          {strategies.map((s, idx) => {
            const sel = selectedStrategies.includes(s.name);
            return (
              <div key={s.name} className="strategy-item-wrap">
                <label className={`strategy-item ${sel ? 'active' : ''}`}>
                  <input type="checkbox" checked={sel} onChange={() => toggleStrategy(s.name)} />
                  <span className="strategy-dot"
                        style={{ background: STRATEGY_COLORS[idx % STRATEGY_COLORS.length] }} />
                  {s.label}
                </label>
                {sel && s.params && (
                  <button className="expand-toggle"
                          onClick={() => setExpandedStrats(prev => ({ ...prev, [s.name]: !prev[s.name] }))}>
                    {expandedStrats[s.name] ? '收起参数' : '展开参数'}
                  </button>
                )}
                {sel && s.params && expandedStrats[s.name] && (
                  <div className="strategy-params">
                    {Object.entries(s.params).map(([key, config]) => (
                      <div className="param-group param-inline" key={key}>
                        <label>{config.label}</label>
                        <input
                          type="number"
                          value={strategyParams[s.name]?.[key] ?? config.default}
                          onChange={e => handleParamChange(s.name, key, safeNumeric(e.target.value, config))}
                          min={config.min} max={config.max} step={config.step || 1}
                        />
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* common params */}
      <div className="param-grid">
        <div className="param-group">
          <label>起始日期</label>
          <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} />
        </div>
        <div className="param-group">
          <label>结束日期</label>
          <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)} />
        </div>
        <div className="param-group">
          <label>初始资金</label>
          <input type="number" value={capital} onChange={e => setCapital(e.target.value)}
                 min={10000} step={100000} />
        </div>
      </div>

      {/* stock selector */}
      <div className="param-group stock-selector">
        <label>
          股票池
          <span className="count">
            {selectedStocks.length > 0 ? ` (已选 ${selectedStocks.length} 只)` : ''}
          </span>
        </label>
        <input type="text" placeholder="搜索股票代码..." value={searchTerm}
               onChange={e => setSearchTerm(e.target.value)} className="search-input" />
        <div className="stock-list">
          {sortedStocks.slice(0, 200).map(sym => (
            <label key={sym} className={`stock-item ${selectedSet.has(sym) ? 'selected' : ''}`}>
              <input type="checkbox" checked={selectedSet.has(sym)} onChange={() => toggleStock(sym)} />
              {sym}
            </label>
          ))}
          {sortedStocks.length > 200 && (
            <p className="more-hint">还有 {sortedStocks.length - 200} 只股票，请使用搜索过滤</p>
          )}
        </div>
      </div>

      <div className="quick-select">
        <span>快速选择：</span>
        <button onClick={() => setSelectedStocks(stocks.filter(s => s.endsWith('.SSE')).slice(0, 10))}>
          前10沪市
        </button>
        <button onClick={() => setSelectedStocks(stocks.filter(s => s.endsWith('.SZSE')).slice(0, 10))}>
          前10深市
        </button>
        <button onClick={() => {
          const cs300 = [
            '600519.SSE','000858.SZSE','600036.SSE','000333.SZSE','601318.SSE',
            '600276.SSE','000651.SZSE','002415.SSE','600900.SSE','601166.SSE'
          ];
          setSelectedStocks(cs300.filter(s => stocks.includes(s)));
        }}>
          沪深300代表
        </button>
        <button onClick={() => setSelectedStocks([])}>清空</button>
      </div>

      <button className="run-btn" onClick={handleRun}
              disabled={loading || selectedStocks.length === 0 || selectedStrategies.length === 0}>
        {loading ? '回测运行中...' : '运行回测'}
      </button>
    </div>
  );
}
