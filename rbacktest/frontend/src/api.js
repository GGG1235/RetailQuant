const API_BASE = '';

/**
 * Fetch all available stock symbols from the backend.
 * @returns {Promise<string[]>}
 */
export async function fetchStocks() {
  const res = await fetch(`${API_BASE}/api/stocks`);
  const data = await res.json();
  return data.stocks;
}

/**
 * Fetch strategy metadata (name, label, params schema).
 * @returns {Promise<Array<{name: string, label: string, params: Object}>>}
 */
export async function fetchStrategies() {
  const res = await fetch(`${API_BASE}/api/strategies`);
  const data = await res.json();
  return data.strategies;
}

/**
 * Submit backtest parameters and return results.
 * @param {Object} params - vt_symbols, start, end, capital, strategies, ...
 * @returns {Promise<{task_id: string, results: Object}>}
 */
export async function runBacktest(params) {
  const res = await fetch(`${API_BASE}/api/backtest`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.error || 'Backtest failed');
  }
  return res.json();
}
