/* QuantLab frontend — vanilla JS, no build step, no framework.
   Charting is TradingView's own open-source lightweight-charts library. */

const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const S = { meta: null, result: null, charts: [], syncing: false };

/* ------------------------------------------------------------------ utils */
const fmtUsd = v => v == null ? '—' :
  '$' + Number(v).toLocaleString('en-US', { maximumFractionDigits: v >= 1000 ? 0 : 2 });
const fmtPct = (v, d = 2) => v == null ? '—' : (v >= 0 ? '+' : '') + Number(v).toFixed(d) + '%';
const fmtNum = (v, d = 2) => v == null ? '—' : Number(v).toFixed(d);
const cls = v => v == null ? 'neu' : v > 0 ? 'pos' : v < 0 ? 'neg' : 'neu';
const dt = t => new Date(t * 1000).toLocaleDateString('en-US',
  { month: 'short', day: 'numeric', year: '2-digit' });
const dtt = t => new Date(t * 1000).toLocaleString('en-US',
  { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });

async function api(path, body) {
  const r = await fetch(path, body ? {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
  } : {});
  const j = await r.json();
  if (!r.ok || j.error) throw new Error(j.error || `HTTP ${r.status}`);
  return j;
}

function msg(el, kind, html) {
  $(el).innerHTML = `<div class="notice ${kind}">${html}</div>`;
  glossify($(el));
}

/** Link glossary terms in one or more freshly-rendered containers. */
function gl(...sels) { sels.forEach(s => glossify(typeof s === 'string' ? $(s) : s)); }
function busy(btn, on, label) {
  btn.disabled = on;
  btn.innerHTML = on ? `<span class="spin"></span> ${label || 'Working…'}` : btn.dataset.label;
}

/* --------------------------------------------------------------- controls */
function readConfig() {
  const num = id => parseFloat($('#' + id).value) || 0;
  return {
    initial_cash: num('initial_cash') || 10000,
    fee_bps: num('fee_bps'), slippage_bps: num('slippage_bps'),
    size_pct: num('size_pct') || 100,
    stop_loss_pct: num('stop_loss_pct'), take_profit_pct: num('take_profit_pct'),
    trailing_stop_pct: num('trailing_stop_pct'), atr_stop_mult: num('atr_stop_mult'),
    allow_short: $('#allow_short').checked,
    reenter_after_stop: $('#reenter_after_stop').checked,
  };
}

function readParams() {
  const out = {};
  $$('#params [data-param]').forEach(el => {
    out[el.dataset.param] = el.type === 'checkbox' ? el.checked : parseFloat(el.value);
  });
  return out;
}

function currentStrategy() { return S.meta.strategies.find(s => s.key === $('#strategy').value); }

function buildParams() {
  const st = currentStrategy();
  $('#blurb').textContent = st.blurb;
  $('#params').innerHTML = st.params.length ? st.params.map(p => {
    const tip = p.help ? ` title="${p.help.replace(/"/g, '&quot;')}"` : '';
    if (p.type === 'bool') {
      return `<label class="chk"${tip}><input type="checkbox" data-param="${p.name}"
        ${p.default ? 'checked' : ''}> ${p.label}</label>`;
    }
    return `<label class="fld"${tip}><span>${p.label}</span>
      <input type="number" data-param="${p.name}" value="${p.default}"
      step="${p.step ?? 1}" ${p.min != null ? `min="${p.min}"` : ''} ${p.max != null ? `max="${p.max}"` : ''}></label>`;
  }).join('') : '<div class="muted small">No parameters — this one just holds.</div>';
  buildOptControls();
}

/* ------------------------------------------------------------- backtest */
async function runBacktest() {
  const btn = $('#run');
  busy(btn, true, 'Fetching data…');
  $('#bt-msg').innerHTML = '';
  try {
    S.result = await api('/api/backtest', {
      symbol: $('#symbol').value, timeframe: $('#timeframe').value,
      days: +$('#days').value, strategy: $('#strategy').value,
      params: readParams(), config: readConfig(), refresh: S.forceRefresh,
    });
    S.forceRefresh = false;
    renderStats(); renderCharts(); renderTrades(); renderTicker();
  } catch (e) {
    msg('#bt-msg', 'err', `<b>Couldn't run that.</b> ${e.message}`);
  } finally { busy(btn, false); }
}

const STAT_HELP = {
  'Total Return': 'What your account gained or lost over the whole test, after fees and slippage.',
  'vs Buy & Hold': 'How much you beat (or lost to) simply buying on day one and never selling. Negative means the strategy was not worth running.',
  'Max Drawdown': 'The worst peak-to-trough fall in account value. This is the number that decides whether you could actually stick with it.',
  'Sharpe': 'Return per unit of volatility. Under 1 is weak, 1-2 is respectable, over 2 in a backtest usually means overfitting.',
  'Win Rate': 'Share of trades that made money. Misleading on its own — check profit factor too.',
  'Profit Factor': 'Gross wins divided by gross losses. Above 1.5 is decent, above 2 is strong, below 1 loses money.',
  'Trades': 'How many round trips. Very few trades means the result is mostly luck; hundreds means fees matter a lot.',
  'Expectancy': 'Average dollars made per trade, wins and losses combined.',
  'Time in Market': 'What share of the period you were actually holding. Low numbers mean less exposure to overnight risk.',
  'Total Fees': 'Everything paid to the exchange. Compare this against your profit — it is often the whole difference.',
  'Avg Win / Loss': 'Average winning trade against average losing trade.',
  'Worst Streak': 'Longest run of consecutive losses. This is what you would have had to sit through.',
};

function renderStats() {
  const s = S.result.stats, L = S.result.latest;
  const card = (k, v, klass, sub) => `<div class="stat">
      <div class="k">${k}${STAT_HELP[k] ? `<span class="info" title="${STAT_HELP[k]}">?</span>` : ''}</div>
      <div class="v ${klass || 'neu'}">${v}</div>
      ${sub ? `<div class="sub">${sub}</div>` : ''}</div>`;

  $('#stats').innerHTML = [
    card('Total Return', fmtPct(s.total_return_pct), cls(s.total_return_pct),
      fmtUsd(s.final_equity) + ' final'),
    card('vs Buy & Hold', fmtPct(s.alpha_pct), cls(s.alpha_pct),
      'B&H: ' + fmtPct(s.buy_hold_return_pct)),
    card('Max Drawdown', fmtPct(s.max_drawdown_pct), 'neg',
      'B&H: ' + fmtPct(s.buy_hold_max_drawdown_pct)),
    card('Sharpe', fmtNum(s.sharpe), s.sharpe > 1 ? 'pos' : 'neu', 'Sortino ' + fmtNum(s.sortino)),
    card('Win Rate', fmtNum(s.win_rate_pct, 1) + '%', 'neu', `${s.num_trades} trades`),
    card('Profit Factor', s.profit_factor >= 999 ? '∞' : fmtNum(s.profit_factor),
      s.profit_factor > 1.5 ? 'pos' : s.profit_factor < 1 ? 'neg' : 'neu'),
    card('Expectancy', fmtUsd(s.expectancy), cls(s.expectancy), 'per trade'),
    card('Avg Win / Loss', fmtUsd(s.avg_win) + ' / ' + fmtUsd(Math.abs(s.avg_loss)), 'neu',
      'payoff ' + fmtNum(s.payoff_ratio)),
    card('Time in Market', fmtNum(s.time_in_market_pct, 0) + '%', 'neu',
      'avg ' + fmtNum(s.avg_bars_held, 0) + ' bars held'),
    card('Total Fees', fmtUsd(s.total_fees), 'neg',
      s.total_fees > Math.abs(s.final_equity - s.buy_hold_final_equity) ? 'more than your edge' : ''),
    card('Worst Streak', s.max_consecutive_losses + ' losses', 'neu',
      'best ' + s.max_consecutive_wins + ' wins'),
    card('CAGR', fmtPct(s.cagr_pct), cls(s.cagr_pct), fmtNum(s.years, 1) + ' years tested'),
  ].join('');

  // A short, blunt verdict in plain English.
  const notes = [];
  if (S.result.demo) notes.push(['err',
    '<b>DEMO MODE.</b> These prices are randomly generated, not real market data. Restart without <code>--demo</code> to use live prices.']);
  if (s.num_trades === 0) {
    notes.push(['warn', 'This strategy never triggered a single trade over the period. Loosen the entry conditions or lengthen the date range.']);
  } else {
    if (!s.beat_buy_hold) notes.push(['warn',
      `<b>It lost to buy &amp; hold.</b> The strategy returned ${fmtPct(s.total_return_pct)} while doing nothing returned ${fmtPct(s.buy_hold_return_pct)}. All that trading cost you ${fmtPct(Math.abs(s.alpha_pct))} — plus ${fmtUsd(s.total_fees)} in fees.`]);
    else notes.push(['ok',
      `<b>Beat buy &amp; hold by ${fmtPct(s.alpha_pct)}</b>, with a max drawdown of ${fmtPct(s.max_drawdown_pct)} versus ${fmtPct(s.buy_hold_max_drawdown_pct)} for holding. Now test it on a different coin and a different date range before believing it.`]);
    if (s.num_trades < 15) notes.push(['warn',
      `Only ${s.num_trades} trades. That is far too small a sample to distinguish skill from luck — treat these numbers as noise.`]);
    if (s.max_drawdown_pct < -50) notes.push(['warn',
      `A ${fmtPct(s.max_drawdown_pct)} drawdown means at the worst point your account was down more than half. Almost nobody keeps running a system through that.`]);
    // Gross profit is what you'd have made with zero costs. If fees ate a big
    // share of it, the idea is really a transaction-cost problem.
    const grossProfit = Math.abs(s.final_equity - readConfig().initial_cash) + s.total_fees;
    if (s.num_trades > 30 && s.total_fees > 0.3 * grossProfit)
      notes.push(['warn', `Fees came to ${fmtUsd(s.total_fees)} across ${s.num_trades} trades — a large slice of the gross result. High-frequency ideas die on costs.`]);
  }
  if (L) {
    const state = L.signal_now > 0 ? 'LONG' : L.signal_now < 0 ? 'SHORT' : 'FLAT';
    notes.push(['ok', `<b>Right now:</b> this strategy would be <b>${state}</b> on ${S.result.symbol} at ${fmtUsd(L.price)} — RSI ${fmtNum(L.rsi, 0)}, ADX ${fmtNum(L.adx, 0)}, ${L.trend_up ? 'above' : 'below'} its long-term trend line. <span class="muted">(Signal from the last closed candle — not advice.)</span>`]);
  }
  $('#bt-msg').innerHTML = notes.map(([k, h]) => `<div class="notice ${k}">${h}</div>`).join('');
  gl('#stats', '#bt-msg');
}

/* ----------------------------------------------------------------- charts */
const CHART_BASE = {
  layout: { background: { color: 'transparent' }, textColor: '#7b8699', fontSize: 11 },
  grid: { vertLines: { color: '#181d27' }, horzLines: { color: '#181d27' } },
  rightPriceScale: { borderColor: '#222938' },
  timeScale: { borderColor: '#222938', timeVisible: true, secondsVisible: false },
  crosshair: { mode: 0 },
  handleScale: { axisPressedMouseMove: { time: true, price: false } },
};

function mkChart(el, extra) {
  const c = LightweightCharts.createChart(el, { ...CHART_BASE, ...(extra || {}), autoSize: true });
  S.charts.push(c);
  return c;
}

function syncCharts() {
  S.charts.forEach(src => {
    src.timeScale().subscribeVisibleLogicalRangeChange(range => {
      if (S.syncing || !range) return;
      S.syncing = true;
      S.charts.forEach(t => { if (t !== src) t.timeScale().setVisibleLogicalRange(range); });
      S.syncing = false;
    });
  });
}

function renderCharts() {
  S.charts.forEach(c => c.remove());
  S.charts = [];
  const R = S.result;
  $('#chart-title').textContent = `${R.symbol} · ${R.timeframe} · ${R.strategy_label}`;

  /* --- price --- */
  const pc = mkChart($('#c-price'));
  const candles = pc.addCandlestickSeries({
    upColor: '#26a69a', downColor: '#ef5350', borderVisible: false,
    wickUpColor: '#26a69a', wickDownColor: '#ef5350',
  });
  candles.setData(R.candles);
  pc.priceScale('right').applyOptions({ scaleMargins: { top: 0.08, bottom: 0.26 } });

  const vol = pc.addHistogramSeries({ priceFormat: { type: 'volume' }, priceScaleId: '' });
  vol.setData(R.volume);
  vol.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });

  const legend = [];
  const addLine = (data, color, width, title, dashed) => {
    if (!data || !data.length) return;
    const s = pc.addLineSeries({
      color, lineWidth: width, priceLineVisible: false, lastValueVisible: false,
      lineStyle: dashed ? 2 : 0, crosshairMarkerVisible: false,
    });
    s.setData(data);
    if (title) legend.push(`<span><i class="dot" style="background:${color}"></i>${title}</span>`);
  };

  if ($('#ov_ema').checked) {
    addLine(R.overlays.ema_fast, '#4c8dff', 1, 'EMA fast');
    addLine(R.overlays.ema_slow, '#e3b341', 1, 'EMA slow');
    addLine(R.overlays.ema_trend, '#9a6dff', 1, 'EMA trend');
  }
  if ($('#ov_bb').checked) {
    addLine(R.overlays.bb_upper, '#4d5768', 1, 'BB', true);
    addLine(R.overlays.bb_lower, '#4d5768', 1, '', true);
  }
  if ($('#ov_vwap').checked) addLine(R.overlays.vwap, '#26a69a', 1, 'VWAP', true);
  $('#chart-legend').innerHTML = legend.join('');

  if ($('#ov_marks').checked) {
    candles.setMarkers(R.markers.map(m => m.type === 'entry' ? {
      time: m.time, position: 'belowBar', color: '#26a69a',
      shape: m.side === 'long' ? 'arrowUp' : 'arrowDown', text: m.side === 'long' ? 'BUY' : 'SELL',
    } : {
      time: m.time, position: 'aboveBar', color: m.pnl >= 0 ? '#4c8dff' : '#ef5350',
      shape: 'circle', text: (m.pnl >= 0 ? '+' : '') + Math.round(m.pnl),
    }).sort((a, b) => a.time - b.time));
  }

  /* --- equity --- */
  const ec = mkChart($('#c-equity'));
  const eq = ec.addAreaSeries({
    lineColor: '#4c8dff', topColor: 'rgba(76,141,255,.25)',
    bottomColor: 'rgba(76,141,255,0)', lineWidth: 2, priceLineVisible: false,
  });
  eq.setData(R.equity);
  const bh = ec.addLineSeries({ color: '#4d5768', lineWidth: 1, lineStyle: 2, priceLineVisible: false });
  bh.setData(R.buy_hold);

  /* --- RSI --- */
  const rc = mkChart($('#c-rsi'));
  const rsi = rc.addLineSeries({ color: '#9a6dff', lineWidth: 1, priceLineVisible: false });
  rsi.setData(R.panels.rsi);
  [[70, '#ef5350'], [30, '#26a69a'], [50, '#2b3242']].forEach(([v, c]) =>
    rsi.createPriceLine({ price: v, color: c, lineWidth: 1, lineStyle: 2, axisLabelVisible: true }));
  rc.priceScale('right').applyOptions({ scaleMargins: { top: 0.12, bottom: 0.12 } });

  /* --- MACD --- */
  const mc = mkChart($('#c-macd'));
  const hist = mc.addHistogramSeries({ priceLineVisible: false });
  hist.setData(R.panels.macd_hist.map(p => ({
    time: p.time, value: p.value, color: p.value >= 0 ? 'rgba(38,166,154,.55)' : 'rgba(239,83,80,.55)',
  })));
  mc.addLineSeries({ color: '#4c8dff', lineWidth: 1, priceLineVisible: false }).setData(R.panels.macd);
  mc.addLineSeries({ color: '#e3b341', lineWidth: 1, priceLineVisible: false }).setData(R.panels.macd_signal);

  syncCharts();
  pc.timeScale().fitContent();
}

/* ----------------------------------------------------------------- trades */
function renderTrades() {
  const T = S.result.trades;
  const head = $('#trades thead'), body = $('#trades tbody');
  if (!T.length) { head.innerHTML = ''; body.innerHTML = '<tr><td class="empty">No trades</td></tr>'; return; }
  head.innerHTML = `<tr><th>#</th><th>Side</th><th>Entry</th><th>Exit</th><th>Price In</th>
    <th>Price Out</th><th>P&amp;L</th><th>Return</th><th>Bars</th><th>Worst Dip</th><th>Exit</th></tr>`;
  body.innerHTML = T.map((t, i) => `<tr>
      <td>${i + 1}</td>
      <td><span class="pill ${t.side}">${t.side}</span></td>
      <td>${dtt(t.entry_time)}</td><td>${dtt(t.exit_time)}</td>
      <td>${fmtUsd(t.entry_price)}</td><td>${fmtUsd(t.exit_price)}</td>
      <td class="${cls(t.pnl)}">${fmtUsd(t.pnl)}</td>
      <td class="${cls(t.pnl_pct)}">${fmtPct(t.pnl_pct)}</td>
      <td>${t.bars_held}</td>
      <td class="neg">${fmtPct(t.mae_pct)}</td>
      <td><span class="pill ${t.exit_reason}">${t.exit_reason}</span></td>
    </tr>`).join('');
}

function renderTicker() {
  const L = S.result.latest, s = S.result.stats;
  $('#ticker').innerHTML = `
    <span class="muted">${S.result.symbol}</span>
    <span class="px">${fmtUsd(L.price)}</span>
    <span class="muted">RSI ${fmtNum(L.rsi, 0)}</span>
    <span class="${cls(s.total_return_pct)}">${fmtPct(s.total_return_pct)}</span>`;
}

/* ---------------------------------------------------------------- compare */
async function runCompare() {
  const btn = $('#run-compare');
  busy(btn, true, 'Running all strategies…');
  try {
    const r = await api('/api/compare', {
      symbol: $('#symbol').value, timeframe: $('#timeframe').value,
      days: +$('#days').value, config: readConfig(),
    });
    const rows = r.results.map(x => x.error ? `<tr><td>${x.label}</td>
        <td colspan="7" class="muted">${x.error}</td></tr>` : `
      <tr class="clickable" data-key="${x.key}">
        <td>${x.label}</td>
        <td><span class="pill">${x.family}</span></td>
        <td class="${cls(x.total_return_pct)}">${fmtPct(x.total_return_pct)}</td>
        <td class="${cls(x.alpha_pct)}">${fmtPct(x.alpha_pct)}</td>
        <td class="neg">${fmtPct(x.max_drawdown_pct)}</td>
        <td class="${x.sharpe > 1 ? 'pos' : ''}">${fmtNum(x.sharpe)}</td>
        <td>${fmtNum(x.win_rate_pct, 1)}%</td>
        <td>${x.profit_factor >= 999 ? '∞' : fmtNum(x.profit_factor)}</td>
        <td>${x.num_trades}</td>
      </tr>`).join('');
    $('#compare-out').innerHTML = `<table><thead><tr>
        <th>Strategy</th><th>Type</th><th>Return</th><th>vs Buy&amp;Hold</th><th>Max DD</th>
        <th>Sharpe</th><th>Win%</th><th>PF</th><th>Trades</th></tr></thead>
      <tbody>${rows}</tbody></table>
      <div class="muted small" style="padding:10px 2px">Click any row to load it into the Backtest tab.
      Defaults only — a strategy near the bottom here might win once tuned, and one at the top might just be lucky on this coin.</div>`;
    gl('#compare-out');
    $$('#compare-out tr.clickable').forEach(tr => tr.onclick = () => {
      $('#strategy').value = tr.dataset.key; buildParams();
      switchView('backtest'); runBacktest();
    });
  } catch (e) { msg('#compare-out', 'err', e.message); }
  finally { busy(btn, false); }
}

/* --------------------------------------------------------------- optimize */
function buildOptControls() {
  const st = currentStrategy();
  const nums = st.params.filter(p => p.type !== 'bool');
  if (!nums.length) {
    $('#opt-controls').innerHTML = '<div class="muted">This strategy has no numeric parameters to sweep.</div>';
    return;
  }
  $('#opt-controls').innerHTML = `
    <div style="display:flex;gap:20px;flex-wrap:wrap;align-items:end;margin-bottom:10px">
      ${nums.slice(0, 4).map((p, i) => `
        <div style="min-width:230px">
          <label class="chk"><input type="checkbox" class="opt-on" data-name="${p.name}"
            ${i < 2 ? 'checked' : ''}> <b>${p.label}</b></label>
          <div class="row">
            <input type="number" class="opt-from" data-name="${p.name}"
              value="${Math.max(p.min ?? 1, Math.round(p.default * 0.5) || 1)}" placeholder="from">
            <input type="number" class="opt-to" data-name="${p.name}"
              value="${Math.round(p.default * 1.8) || 10}" placeholder="to">
            <input type="number" class="opt-step" data-name="${p.name}"
              value="${Math.max(p.step ?? 1, Math.round(p.default * 0.15) || 1)}" placeholder="step">
          </div>
        </div>`).join('')}
      <div>
        <label class="fld" style="width:170px;margin:0"><span>Rank by</span>
          <select id="opt-metric">
            <option value="total_return_pct">Total return</option>
            <option value="sharpe">Sharpe ratio</option>
            <option value="profit_factor">Profit factor</option>
          </select></label>
      </div>
      <button class="btn" id="run-optimize" style="width:170px">Run Sweep</button>
    </div>`;
  $('#run-optimize').dataset.label = 'Run Sweep';
  $('#run-optimize').onclick = runOptimize;
}

async function runOptimize() {
  const btn = $('#run-optimize');
  const sweep = {};
  $$('.opt-on:checked').forEach(cb => {
    const n = cb.dataset.name;
    const g = c => parseFloat($(`.opt-${c}[data-name="${n}"]`).value);
    const [from, to, step] = [g('from'), g('to'), g('step')];
    const vals = [];
    for (let v = from; v <= to + 1e-9 && vals.length < 60; v += (step || 1)) vals.push(+v.toFixed(4));
    if (vals.length) sweep[n] = vals;
  });
  if (!Object.keys(sweep).length) { msg('#optimize-out', 'warn', 'Tick at least one parameter to sweep.'); return; }
  const total = Object.values(sweep).reduce((a, v) => a * v.length, 1);

  busy(btn, true, `Testing ${total}…`);
  try {
    const r = await api('/api/optimize', {
      symbol: $('#symbol').value, timeframe: $('#timeframe').value, days: +$('#days').value,
      strategy: $('#strategy').value, params: readParams(), config: readConfig(),
      sweep, metric: $('#opt-metric').value,
    });
    const keys = Object.keys(sweep);
    const bad = r.overfit_note.includes('NOT hold up') || r.overfit_note.includes('weak');
    const rows = r.results.map(x => {
      const gap = (x.out_sample.total_return_pct ?? 0) - (x.in_sample.total_return_pct ?? 0);
      return `<tr>
        ${keys.map(k => `<td>${x.params[k]}</td>`).join('')}
        <td class="${cls(x.in_sample.total_return_pct)}">${fmtPct(x.in_sample.total_return_pct)}</td>
        <td>${fmtNum(x.in_sample.sharpe)}</td>
        <td>${x.in_sample.num_trades}</td>
        <td class="${cls(x.out_sample.total_return_pct)}">${fmtPct(x.out_sample.total_return_pct)}</td>
        <td>${fmtNum(x.out_sample.sharpe)}</td>
        <td>${x.out_sample.num_trades}</td>
        <td class="${gap < -20 ? 'neg' : 'muted'}">${fmtPct(gap)}</td>
      </tr>`;
    }).join('');
    $('#optimize-out').innerHTML = `
      <div class="notice ${bad ? 'warn' : 'ok'}"><b>Overfitting check:</b> ${r.overfit_note}<br>
        <span class="muted small">${r.split_note}. Tested ${r.tested} combinations.</span></div>
      <table><thead><tr>
        ${keys.map(k => `<th>${k}</th>`).join('')}
        <th>IS Return</th><th>IS Sharpe</th><th>IS Trades</th>
        <th>OOS Return</th><th>OOS Sharpe</th><th>OOS Trades</th><th>Gap</th>
      </tr></thead><tbody>${rows}</tbody></table>
      <div class="muted small" style="padding:10px 2px">
        IS = in-sample (first 70%, what was optimized). OOS = out-of-sample (last 30%, never seen).
        A big negative Gap means those settings only worked on the data they were fitted to.
        Prefer a parameter region where <i>neighbouring</i> values all do fine over a single spectacular row.
      </div>`;
    gl('#optimize-out');
  } catch (e) { msg('#optimize-out', 'err', e.message); }
  finally { busy(btn, false); }
}

/* ---------------------------------------------------------------- scanner */
async function runScan() {
  const btn = $('#run-scan');
  busy(btn, true, 'Scanning…');
  try {
    const r = await api('/api/scan', { timeframe: $('#scan-tf').value, days: 180 });
    const max = Math.max(1, ...r.results.map(x => x.score));
    $('#scan-out').innerHTML = `<table><thead><tr>
        <th>Coin</th><th>Price</th><th>24h</th><th>Score</th><th>RSI</th><th>ADX</th>
        <th>Volatility</th><th>Vol z</th><th>Signals</th></tr></thead><tbody>
      ${r.results.map(x => `<tr class="clickable" data-sym="${x.symbol}">
        <td><b>${x.symbol}</b> ${x.trend_up ? '<span class="pill long">uptrend</span>' : ''}</td>
        <td>${fmtUsd(x.price)}</td>
        <td class="${cls(x.chg_24h_pct)}">${fmtPct(x.chg_24h_pct, 1)}</td>
        <td><span class="bar"><i style="width:${Math.max(0, x.score) / max * 100}%"></i></span> ${x.score}</td>
        <td class="${x.rsi < 35 ? 'pos' : x.rsi > 70 ? 'neg' : ''}">${fmtNum(x.rsi, 0)}</td>
        <td>${fmtNum(x.adx, 0)}</td>
        <td>${fmtNum(x.atr_pct, 1)}%</td>
        <td>${fmtNum(x.vol_z, 1)}</td>
        <td style="text-align:left" class="muted">${x.notes.join(' · ') || '—'}</td>
      </tr>`).join('')}</tbody></table>
      ${r.failed.length ? `<div class="muted small" style="padding:8px 2px">Skipped: ${r.failed.map(f => f.symbol).join(', ')}</div>` : ''}
      <div class="muted small" style="padding:10px 2px">Click a coin to backtest it. The score is a rough
      sum of favourable conditions — it is a shortlist for research, and says nothing about what happens next.</div>`;
    gl('#scan-out');
    $$('#scan-out tr.clickable').forEach(tr => tr.onclick = () => {
      $('#symbol').value = tr.dataset.sym; switchView('backtest'); runBacktest();
    });
  } catch (e) { msg('#scan-out', 'err', e.message); }
  finally { busy(btn, false); }
}

/* ----------------------------------------------------------------- radar */
const ago = ts => {
  if (!ts) return '—';
  const m = (Date.now() / 1000 - ts) / 60;
  if (m < 60) return `${Math.max(0, Math.round(m))}m`;
  if (m < 1440) return `${Math.round(m / 60)}h`;
  return `${Math.round(m / 1440)}d`;
};
const escHtml = s => String(s == null ? '' : s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

async function loadRadar() {
  const btn = $('#n-refresh');
  busy(btn, true, 'Fetching…');
  try {
    const [n, t, p] = await Promise.all([
      api('/api/news', { query: $('#n-query').value, hours: +$('#n-hours').value }),
      api('/api/trending', {}).catch(e => ({ coins: [], error: e.message })),
      api('/api/newpools', { network: 'solana' }).catch(e => ({ pools: [], error: e.message })),
    ]);
    S.radar = { n, t, p };
    renderRadar();
  } catch (e) { msg('#sub-news', 'err', e.message); }
  finally { busy(btn, false); }
}

function renderRadar() {
  const { n, t, p } = S.radar;

  $('#n-status').innerHTML = `<span class="muted">${n.counts.shown} of ${n.counts.total} headlines</span>
    ${n.failed.length ? `<span class="neg">${n.failed.length} source${n.failed.length > 1 ? 's' : ''} unavailable</span>` : ''}`;

  /* ---- headlines ---- */
  $('#sub-news').innerHTML = `
    ${n.demo ? '<div class="notice err">DEMO MODE — these headlines are fixtures, not real news.</div>' : ''}
    ${n.failed.length ? `<div class="notice warn">Couldn't reach: ${n.failed.map(f => escHtml(f.source)).join(', ')}. The rest loaded fine.</div>` : ''}
    <div class="card" style="margin-top:10px">
      <div class="hd">Headlines<div class="legend"><span class="muted">newest first · click to open</span></div></div>
      ${n.items.length ? n.items.map(it => `
        <div class="item">
          <span class="ago">${ago(it.published)}</span>
          <span class="src">${escHtml(it.source_name)}</span>
          <span style="flex:1;min-width:0">
            <a href="${escHtml(it.link)}" target="_blank" rel="noopener noreferrer">${escHtml(it.title)}</a>
            ${it.summary ? `<div class="sum">${escHtml(it.summary).slice(0, 200)}</div>` : ''}
          </span>
        </div>`).join('') : '<div class="empty">Nothing matched that filter.</div>'}
    </div>`;

  /* ---- narratives ---- */
  const nr = n.narratives || [];
  $('#sub-narr').innerHTML = `
    <div class="notice ok" style="margin-top:10px">
      <b>This is the closest thing here to a real information edge.</b> It counts which names appear
      across your feeds, weighting recent mentions higher and rewarding coverage by <i>many different
      outlets</i> over repetition by one. When something you don't recognise suddenly appears in five
      places in a day, that's worth ten minutes of reading. You won't be first — but you'll be earlier
      than price.
    </div>
    ${nr.length ? `<div class="card"><table><thead><tr><th>Term</th><th>Outlets</th><th>Mentions</th>
      <th>Score</th><th style="text-align:left">Where</th></tr></thead><tbody>
      ${nr.map(r => `<tr>
        <td><b>${escHtml(r.term)}</b></td>
        <td>${r.source_count}</td>
        <td>${r.mentions}</td>
        <td><span class="bar" style="width:60px"><i style="width:${Math.min(100, r.score / (nr[0].score || 1) * 100)}%"></i></span></td>
        <td style="text-align:left" class="muted small">
          ${r.headlines.map(h => `<a href="${escHtml(h.link)}" target="_blank" rel="noopener noreferrer"
            style="color:var(--dim)">${escHtml(h.title).slice(0, 74)}</a>`).join('<br>')}</td>
      </tr>`).join('')}</tbody></table></div>`
      : '<div class="empty">Not enough headlines yet — widen the time window.</div>'}`;

  /* ---- trending ---- */
  $('#sub-trend').innerHTML = t.error
    ? `<div class="notice warn" style="margin-top:10px">Trending unavailable: ${escHtml(t.error)}</div>`
    : `<div class="notice ok" style="margin-top:10px">
        Most-searched coins on CoinGecko in the last 24h. <b>Search interest is attention, not opportunity</b> —
        by the time something trends, the move that caused it has usually happened.
      </div>
      <div class="card"><table><thead><tr><th>Coin</th><th>Symbol</th><th>Rank</th><th>Price</th>
        <th>24h</th><th>Market cap</th></tr></thead><tbody>
        ${(t.coins || []).map(c => `<tr>
          <td>${escHtml(c.name)}</td><td><b>${escHtml(c.symbol)}</b></td>
          <td>${c.rank ?? '—'}</td>
          <td>${c.price_usd != null ? fmtUsd(c.price_usd) : '—'}</td>
          <td class="${cls(c.change_24h)}">${c.change_24h != null ? fmtPct(c.change_24h, 1) : '—'}</td>
          <td>${escHtml(c.market_cap || '—')}</td></tr>`).join('')}
      </tbody></table></div>`;

  /* ---- new pools ---- */
  const br = p.base_rates || { facts: [], sources: [] };
  $('#sub-pools').innerHTML = `
    <div class="notice warn" style="margin-top:10px">
      <b>${escHtml(br.headline || 'Base rates')}</b>
      <ul style="margin:8px 0 0 18px;line-height:1.75">
        ${br.facts.map(f => `<li>${escHtml(f)}</li>`).join('')}
      </ul>
      <div class="small" style="margin-top:9px">
        ${(br.sources || []).map(s => `<a href="${escHtml(s.url)}" target="_blank" rel="noopener noreferrer"
          style="color:var(--warn);margin-right:12px">${escHtml(s.label)}</a>`).join('')}
      </div>
    </div>
    ${p.error ? `<div class="notice warn">Feed unavailable: ${escHtml(p.error)}</div>` : ''}
    <div class="card"><div class="hd">Newest Solana pools
      <div class="legend"><span class="muted">risk flags are mechanical, not opinions</span></div></div>
      <table><thead><tr><th>Pair</th><th>Age</th><th>Liquidity</th><th>24h Vol</th><th>24h</th>
        <th>Buys/Sells</th><th>Risk</th><th style="text-align:left">Why</th></tr></thead><tbody>
      ${(p.pools || []).map(x => {
    const lvl = x.risk_score >= 5 ? 3 : x.risk_score >= 3 ? 2 : 1;
    return `<tr>
          <td><a href="${escHtml(x.url)}" target="_blank" rel="noopener noreferrer"
              style="color:var(--text)"><b>${escHtml(x.name)}</b></a></td>
          <td>${x.age_hours != null ? (x.age_hours < 1 ? `${(x.age_hours * 60).toFixed(0)}m` : `${x.age_hours.toFixed(0)}h`) : '—'}</td>
          <td class="${(x.liquidity_usd || 0) < 20000 ? 'neg' : ''}">${x.liquidity_usd != null ? fmtUsd(x.liquidity_usd) : '—'}</td>
          <td>${x.volume_24h != null ? fmtUsd(x.volume_24h) : '—'}</td>
          <td class="${cls(x.change_24h)}">${x.change_24h != null ? fmtPct(x.change_24h, 0) : '—'}</td>
          <td class="muted">${x.buys_24h ?? '—'} / ${x.sells_24h ?? '—'}</td>
          <td><span class="risk r${lvl}">${lvl === 3 ? 'EXTREME' : lvl === 2 ? 'HIGH' : 'HIGH'}</span></td>
          <td style="text-align:left" class="muted small">${(x.risk_flags || []).map(escHtml).join('<br>')}</td>
        </tr>`;
  }).join('')}
      </tbody></table></div>
    <div class="muted small" style="padding:10px 2px;line-height:1.7">
      Every row here is high risk by definition — that's what "new token" means. The lowest label this
      table can show is HIGH. There is no paper-trading integration for these on purpose: this app can
      only model assets with real price history, and a token that is 40 minutes old has none.
    </div>`;

  gl('#sub-news', '#sub-narr', '#sub-trend', '#sub-pools');
}

/* ------------------------------------------------------------- shortlist */
const BAND_CLS = { strong: 'pos', decent: 'pos', mixed: 'neu', weak: 'neg', avoid: 'neg' };

async function runShortlist() {
  const btn = $('#s-run');
  busy(btn, true, 'Scoring the market…');
  try {
    S.short = await api('/api/shortlist', {
      timeframe: $('#s-tf').value, top: +$('#s-top').value,
      use_news: $('#s-news').checked,
    });
    renderShortlist();
  } catch (e) { msg('#s-out', 'err', e.message); }
  finally { busy(btn, false); }
}

function renderShortlist() {
  const d = S.short;

  const card = (r, i) => {
    const maxPts = Math.max(...r.factors.map(f => f.max_points));
    return `<div class="card" style="margin-bottom:9px">
      <div class="hd">
        <span style="color:var(--dim2)">#${i + 1}</span>
        <span style="font-size:15px;font-weight:700;color:var(--text);text-transform:none;letter-spacing:0">${r.symbol}</span>
        <span class="muted" style="text-transform:none;letter-spacing:0">${fmtUsd(r.price)}</span>
        <span class="pill ${BAND_CLS[r.band] === 'pos' ? 'long' : BAND_CLS[r.band] === 'neg' ? 'short' : ''}">${r.band}</span>
        <div class="legend">
          <span style="font-family:var(--mono);font-size:19px;font-weight:700"
            class="${BAND_CLS[r.band]}">${fmtNum(r.score, 0)}<span class="muted" style="font-size:12px">/100</span></span>
        </div>
      </div>
      <div style="padding:12px 14px">
        <div class="muted" style="margin-bottom:11px;line-height:1.6">${r.band_text}</div>

        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:7px;margin-bottom:12px">
          ${r.factors.map(f => `
            <div style="display:flex;align-items:center;gap:9px" title="${f.help.replace(/"/g, '&quot;')}">
              <span style="width:15px;text-align:center;color:${f.passed ? 'var(--up)' : 'var(--dim2)'}">${f.passed ? '✓' : '·'}</span>
              <span style="flex:1;min-width:0;font-size:12px;${f.passed ? '' : 'color:var(--dim2)'}">${f.label}</span>
              <span class="bar" style="width:52px"><i style="width:${f.max_points ? (f.points / f.max_points * 100) : 0}%"></i></span>
              <span style="font-family:var(--mono);font-size:11px;width:38px;text-align:right"
                class="${f.points > 0 ? '' : 'muted'}">${f.points.toFixed(0)}/${f.max_points.toFixed(0)}</span>
            </div>`).join('')}
        </div>

        <div style="display:flex;gap:18px;flex-wrap:wrap;font-size:12px;padding-top:10px;border-top:1px solid var(--line)">
          <span class="muted">RSI <b class="${r.rsi < 35 ? 'pos' : r.rsi > 70 ? 'neg' : 'neu'}">${fmtNum(r.rsi, 0)}</b></span>
          <span class="muted">ADX <b class="neu">${fmtNum(r.adx, 0)}</b></span>
          <span class="muted">Volatility <b class="neu">${fmtNum(r.atr_pct, 1)}%</b></span>
          <span class="muted">7d <b class="${cls(r.chg_7d)}">${fmtPct(r.chg_7d, 1)}</b></span>
          ${r.rel_strength_30d != null ? `<span class="muted">vs BTC <b class="${cls(r.rel_strength_30d)}">${fmtPct(r.rel_strength_30d, 0)}</b>
            <span style="color:var(--dim2)">(not in score)</span></span>` : ''}
          ${r.attention > 0 ? `<span class="muted">News attention <b class="neu">${fmtNum(r.attention, 0)}</b>
            <span style="color:var(--dim2)">(not in score)</span></span>` : ''}
          <span style="margin-left:auto;display:flex;gap:6px">
            <button class="btn ghost s-plan" data-sym="${r.symbol}" style="width:auto;padding:4px 11px">Plan a trade</button>
            <button class="btn ghost s-bt" data-sym="${r.symbol}" style="width:auto;padding:4px 11px">Backtest it</button>
          </span>
        </div>
      </div>
    </div>`;
  };

  const w = d.weights;
  $('#s-out').innerHTML = `
    ${d.demo ? '<div class="notice err">DEMO MODE — scores computed on fabricated prices.</div>' : ''}
    <div class="notice ${d.shortlist.some(r => r.score >= 65) ? 'ok' : 'warn'}">
      <b>${escHtml(d.headline)}</b>
      <div class="muted small" style="margin-top:5px">
        Scored ${d.scored} coins on ${d.timeframe} candles.
        ${d.news_used ? 'News attention included as a separate column.' : 'News attention off.'}
        ${d.failed.length ? ` Skipped: ${d.failed.map(f => escHtml(f.symbol)).join(', ')}.` : ''}
      </div>
    </div>

    ${d.shortlist.map(card).join('')}

    <div class="card" style="margin-top:12px">
      <div class="hd">The formula, in full</div>
      <div style="padding:12px 15px;line-height:1.75">
        <div class="muted" style="margin-bottom:10px">Score = weighted sum of six factors, each scored 0 to 1:</div>
        <div style="font-family:var(--mono);font-size:12px;background:var(--panel2);padding:11px 13px;border-radius:6px;margin-bottom:12px">
          ${Object.entries(w).map(([k, v]) =>
      `${(v * 100).toFixed(0).padStart(3)}%  ${k}`).join('<br>')}
        </div>
        <div class="muted">
          These weights are round numbers on purpose — they were <b>not</b> tuned to make a backtest
          look good, which is the only reason to trust them at all. Tune them yourself in the Optimize
          tab and watch the out-of-sample column carefully.
          <br><br>
          <b>Two columns are deliberately excluded from the score:</b> relative strength vs BTC needs
          a second asset to compute, so it can't live inside a single-asset backtest; and news
          attention has no historical archive, so it can't be backtested at all. Blending an
          unverifiable input into a verifiable score would make the whole thing unfalsifiable. They're
          shown as information, not as part of the maths.
        </div>
      </div>
    </div>`;

  gl('#s-out');
  $$('.s-plan').forEach(b => b.onclick = () => {
    $('#g-symbol').value = b.dataset.sym;
    $('#g-strategy').value = 'quality_score';
    $('#g-tf').value = d.timeframe;
    switchView('guided'); planTrade();
  });
  $$('.s-bt').forEach(b => b.onclick = () => {
    $('#symbol').value = b.dataset.sym;
    $('#strategy').value = 'quality_score'; buildParams();
    $('#timeframe').value = d.timeframe; $('#days').value = '730';
    switchView('backtest'); runBacktest();
  });
}

function verifyFormula() {
  $('#strategy').value = 'quality_score';
  buildParams();
  $('#timeframe').value = S.short ? S.short.timeframe : '4h';
  $('#days').value = '730';
  switchView('backtest');
  runBacktest();
}

/* ---------------------------------------------------------- guided trade */
const md = s => String(s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;')
  .replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')
  .replace(/_\((.+?)\)_/g, '<i class="muted">($1)</i>');

async function planTrade() {
  const btn = $('#g-plan');
  busy(btn, true, 'Working it out…');
  try {
    const d = await api('/api/plan', {
      symbol: $('#g-symbol').value, strategy: $('#g-strategy').value,
      timeframe: $('#g-tf').value,
    });
    S.plan = d;
    renderPlan();
  } catch (e) { msg('#g-out', 'err', e.message); }
  finally { busy(btn, false); }
}

function renderPlan() {
  const d = S.plan, p = d.plan, v = d.verdict;
  const blank = (n, title, value, sub, klass) => `
    <div class="card" style="flex:1;min-width:210px">
      <div class="hd"><span style="color:var(--accent)">${n}</span> &nbsp;${title}</div>
      <div style="padding:12px">
        <div style="font-family:var(--mono);font-size:21px;font-weight:600" class="${klass || ''}">${value}</div>
        <div class="muted small" style="margin-top:5px;line-height:1.5">${sub}</div>
      </div></div>`;

  $('#g-out').innerHTML = `
    ${d.demo ? '<div class="notice err"><b>DEMO MODE</b> — these prices are fabricated.</div>' : ''}

    <div class="notice ${v.aligned ? 'ok' : 'warn'}" style="margin-bottom:10px">
      <b>${v.aligned ? '✓ Your strategy agrees with this trade.' : '⚠ Your strategy is NOT signalling this trade.'}</b>
      &nbsp;<span class="muted">${d.strategy_label} on ${d.symbol} ${d.timeframe} currently says
      <b>${v.state}</b>${v.action !== 'HOLD' ? ` (${v.action})` : ''}.</span>
    </div>

    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px">
      ${blank('1', 'WHAT', d.symbol, `Trading at ${fmtUsd(d.entry_price)} right now.`)}
      ${blank('2', 'HOW MUCH', fmtUsd(p.size_usd),
    `${fmtNum(p.units, 6)} ${d.symbol} — ${fmtNum(p.size_pct_of_account, 0)}% of your account.
       ${p.capped_by ? `<br><i>Limited by ${p.capped_by}.</i>` : ''}`)}
      ${blank('3', "WHERE YOU'RE WRONG", fmtUsd(p.stop_price),
      `${fmtNum(p.stop_pct, 1)}% below entry. Risks <b>${fmtUsd(p.risk_usd)}</b>
       (${fmtNum(p.risk_pct_of_account, 1)}% of account).`, 'neg')}
      ${blank('4', "WHERE YOU'RE DONE", fmtUsd(p.target_price),
        `Gain of ${fmtUsd(p.target_gain)} at target, or exit earlier on the rule.`, 'pos')}
    </div>

    <div class="card" style="margin-bottom:12px">
      <div class="hd">In plain English</div>
      <div style="padding:14px 16px;line-height:1.85">
        ${d.plain.map(s => `<div style="margin-bottom:9px">${md(s)}</div>`).join('')}
      </div>
    </div>

    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px">
      <div class="card" style="flex:1;min-width:290px">
        <div class="hd" style="color:var(--up)">Reasons this setup looks OK</div>
        <div style="padding:12px 16px">${v.reasons.length
      ? v.reasons.map(r => `<div style="margin-bottom:8px;line-height:1.6">• ${r}</div>`).join('')
      : '<span class="muted">None. That is itself an answer.</span>'}</div>
      </div>
      <div class="card" style="flex:1;min-width:290px">
        <div class="hd" style="color:var(--warn)">Reasons to be careful</div>
        <div style="padding:12px 16px">${v.warnings.length
        ? v.warnings.map(r => `<div style="margin-bottom:8px;line-height:1.6">• ${r}</div>`).join('')
        : '<span class="muted">Nothing flagged.</span>'}</div>
      </div>
    </div>

    <div class="stats" style="padding:0 0 12px">
      <div class="stat"><div class="k">Reward : Risk</div><div class="v">${fmtNum(p.reward_risk, 1)} : 1</div>
        <div class="sub">need ${fmtNum(p.breakeven_win_rate, 0)}% right to break even</div></div>
      <div class="stat"><div class="k">Wrong in a row survivable</div><div class="v">${p.max_consecutive_losses_survivable}</div>
        <div class="sub">at this risk level</div></div>
      <div class="stat"><div class="k">Stop basis</div><div class="v" style="font-size:14px">${p.stop_basis}</div>
        <div class="sub">volatility-scaled</div></div>
      <div class="stat"><div class="k">RSI</div><div class="v">${fmtNum(d.context.rsi, 0)}</div>
        <div class="sub">${d.context.rsi < 35 ? 'oversold' : d.context.rsi > 70 ? 'stretched' : 'neutral'}</div></div>
      <div class="stat"><div class="k">Trend</div><div class="v ${d.context.trend_up ? 'pos' : 'neg'}">${d.context.trend_up ? 'UP' : 'DOWN'}</div>
        <div class="sub">vs long-term average</div></div>
      <div class="stat"><div class="k">Account</div><div class="v">${fmtUsd(d.account.equity)}</div>
        <div class="sub">${fmtUsd(d.account.cash)} cash free</div></div>
    </div>

    <div class="card">
      <div class="hd">Take it? (paper money)</div>
      <div style="padding:14px 16px">
        <label class="fld"><span>Your reason — one line, in your own words</span>
          <input type="text" id="g-reason" value="${(v.aligned ? `${d.strategy_label} says LONG; ` : 'Override: ')}RSI ${fmtNum(d.context.rsi, 0)}, trend ${d.context.trend_up ? 'up' : 'down'}"></label>
        <label class="fld" style="max-width:320px"><span>How sure are you, really?</span>
          <select id="g-conf">
            <option value="1">1 — barely an idea</option><option value="2">2 — mild lean</option>
            <option value="3" selected>3 — decent setup</option><option value="4">4 — strong setup</option>
            <option value="5">5 — best I've seen</option>
          </select></label>
        <button class="btn" id="g-take" style="max-width:320px">Take this trade — ${fmtUsd(p.size_usd)} of ${d.symbol}</button>
        <div class="muted small" style="margin-top:10px">
          Then write <b>${fmtUsd(p.stop_price)}</b> down. If price reaches it, the reason you bought is gone —
          sell without renegotiating with yourself. That single habit separates people who survive from people who don't.
        </div>
      </div>
    </div>`;

  gl('#g-out');
  $('#g-take').dataset.label = $('#g-take').textContent;
  $('#g-take').onclick = takePlannedTrade;

  // keep the risk panel in sync with what the server actually has saved
  const rp = d.risk_profile;
  $('#r-risk').value = rp.risk_pct;
  $('#r-atr').value = rp.stop_atr_mult;
  $('#r-target').value = rp.target_r;
  $('#r-max').value = rp.max_position_pct;
}

async function takePlannedTrade() {
  const btn = $('#g-take'), d = S.plan;
  busy(btn, true, 'Placing…');
  try {
    S.paper = await api('/api/paper/buy', {
      symbol: d.symbol, usd: d.plan.size_usd,
      reason: $('#g-reason').value, confidence: +$('#g-conf').value,
      strategy: d.strategy, timeframe: d.timeframe,
      stop_price: d.plan.stop_price, target_price: d.plan.target_price,
    });
    renderPaper();
    msg('#g-out', 'ok', `<b>Done — you own ${fmtNum(d.plan.units, 6)} ${d.symbol}.</b>
      Your stop level is <b>${fmtUsd(d.plan.stop_price)}</b> and your target is
      <b>${fmtUsd(d.plan.target_price)}</b>. It's now in the Paper Trading tab, where you close it.
      <br><br>Nothing else to do. Check back in a day or two — over-monitoring a position is how
      people talk themselves out of good trades.`);
    switchView('paper');
  } catch (e) { msg('#g-out', 'err', e.message); busy(btn, false); }
}

async function saveRisk() {
  const btn = $('#r-save');
  busy(btn, true, 'Saving…');
  try {
    await api('/api/risk', {
      risk_pct: +$('#r-risk').value, stop_atr_mult: +$('#r-atr').value,
      target_r: +$('#r-target').value, max_position_pct: +$('#r-max').value,
    });
    if (S.plan) await planTrade();
  } catch (e) { msg('#g-out', 'err', e.message); }
  finally { busy(btn, false); }
}

/* --------------------------------------------------------- paper trading */
const ACTION_STYLE = {
  'OPEN LONG': ['pos', 'BUY SIGNAL'], 'OPEN SHORT': ['neg', 'SHORT SIGNAL'],
  'CLOSE': ['neg', 'EXIT SIGNAL'], 'HOLD': ['muted', 'no change'],
};

function paperCtx() {
  return {
    strategy: $('#p-strategy').value, timeframe: $('#p-tf').value,
    params: {},   // defaults — the paper tab intentionally uses vanilla settings
  };
}

async function loadPaper() {
  try {
    const d = await api('/api/paper', {});
    S.paper = d;
    renderPaper();
  } catch (e) { msg('#paper-msg', 'err', e.message); }
}

function renderPaper() {
  const d = S.paper, p = d.portfolio, sc = d.scorecard;
  const card = (k, v, klass, sub) => `<div class="stat"><div class="k">${k}</div>
    <div class="v ${klass || 'neu'}">${v}</div>${sub ? `<div class="sub">${sub}</div>` : ''}</div>`;

  $('#paper-stats').innerHTML = [
    card('Portfolio Value', fmtUsd(p.equity), cls(p.equity - p.initial_cash),
      fmtPct(p.total_return_pct) + ' overall'),
    card('Cash', fmtUsd(p.cash), 'neu', fmtNum(p.cash_pct, 0) + '% of portfolio'),
    card('Realized P&L', fmtUsd(p.realized_pnl), cls(p.realized_pnl), 'trades you closed'),
    card('Unrealized P&L', fmtUsd(p.unrealized_pnl), cls(p.unrealized_pnl), 'open positions'),
    card('Closed Trades', sc.trades || 0, 'neu',
      sc.trades ? fmtNum(sc.win_rate, 0) + '% winners' : 'none yet'),
    card('Running', fmtNum(p.days_running, 1) + ' days', 'neu', 'fees ' + fmtUsd(p.total_fees)),
  ].join('');

  const notes = [];
  if (d.demo) notes.push(['err', '<b>DEMO MODE.</b> Prices are fabricated. Restart without <code>--demo</code> for real ones.']);
  if (!p.positions.length && !sc.trades) notes.push(['ok',
    `<b>Start here.</b> Make your first trade with a written reason. The goal for the next few weeks is not to make money — it's to accumulate 30 closed trades with honest notes so the scorecard can tell you something true about how you think.`]);
  $('#paper-msg').innerHTML = notes.map(([k, h]) => `<div class="notice ${k}">${h}</div>`).join('');

  /* positions */
  $('#p-positions').innerHTML = !p.positions.length
    ? '<div class="empty">No open positions.</div>'
    : `<table><thead><tr><th>Coin</th><th>Units</th><th>Avg Cost</th><th>Now</th><th>Value</th>
        <th>Stop</th><th>To stop</th><th>P&amp;L</th><th>Return</th><th>Held</th><th>Conv.</th>
        <th style="text-align:left">Your reason</th><th>Close</th></tr></thead><tbody>
      ${p.positions.map(r => `<tr${r.stop_breached ? ' style="background:#2a1517"' : ''}>
        <td><b>${r.symbol}</b></td>
        <td>${fmtNum(r.units, 4)}</td>
        <td>${fmtUsd(r.cost_basis)}</td>
        <td>${fmtUsd(r.price)}</td>
        <td>${fmtUsd(r.value)}</td>
        <td class="muted">${r.stop_price ? fmtUsd(r.stop_price) : '—'}</td>
        <td class="${r.stop_breached ? 'neg' : r.stop_distance_pct != null && r.stop_distance_pct < 2 ? 'neg' : 'muted'}">
          ${r.stop_breached ? '<b>BREACHED</b>' : r.stop_distance_pct != null ? fmtNum(r.stop_distance_pct, 1) + '%' : '—'}</td>
        <td class="${cls(r.unrealized)}">${fmtUsd(r.unrealized)}</td>
        <td class="${cls(r.unrealized_pct)}">${fmtPct(r.unrealized_pct)}</td>
        <td>${fmtNum(r.held_days, 1)}d</td>
        <td>${'●'.repeat(r.confidence)}</td>
        <td style="text-align:left" class="muted">${r.reason}
          ${r.strategy_said ? `<br><span class="small">system said: ${r.strategy_said}</span>` : ''}</td>
        <td><button class="btn ghost sell-btn" data-sym="${r.symbol}" data-frac="1"
            style="width:auto;padding:3px 9px">Sell all</button>
          <button class="btn ghost sell-btn" data-sym="${r.symbol}" data-frac="0.5"
            style="width:auto;padding:3px 9px">½</button></td>
      </tr>`).join('')}</tbody></table>`;
  $$('.sell-btn').forEach(b => b.onclick = () => sellPosition(b.dataset.sym, +b.dataset.frac));

  /* scorecard */
  if (!sc.trades) {
    $('#p-score').innerHTML = `<div class="notice ok"><b>Scorecard</b><br>${sc.note}</div>`;
  } else {
    const ce = sc.conviction_edge;
    const rows = Object.entries(sc.by_confidence).map(([c, v]) => `<tr>
      <td>${'●'.repeat(+c)}${'○'.repeat(5 - c)}</td><td>${v.n}</td>
      <td class="${cls(v.avg_pct)}">${fmtPct(v.avg_pct)}</td>
      <td>${fmtNum(v.win_rate, 0)}%</td></tr>`).join('');
    $('#p-score').innerHTML = `
      <div class="card"><div class="hd">Scorecard — grading you, not the strategy</div>
      <div style="padding:12px;display:flex;gap:24px;flex-wrap:wrap">
        <div style="flex:0 0 300px">
          <div class="muted small" style="margin-bottom:6px">Average return by conviction</div>
          <table><thead><tr><th>Conviction</th><th>N</th><th>Avg</th><th>Win%</th></tr></thead>
            <tbody>${rows}</tbody></table>
          <div style="margin-top:12px" class="stat">
            <div class="k">Conviction Edge</div>
            <div class="v ${ce == null ? 'neu' : ce > 2 ? 'pos' : ce < -2 ? 'neg' : 'neu'}">
              ${ce == null ? 'n/a' : fmtPct(ce, 1)}</div>
            <div class="sub">high-conviction avg minus low-conviction avg</div>
          </div>
        </div>
        <div style="flex:1;min-width:280px">
          <table><tbody>
            <tr><td style="text-align:left">Win rate</td><td>${fmtNum(sc.win_rate, 1)}%</td></tr>
            <tr><td style="text-align:left">Profit factor</td><td>${sc.profit_factor >= 999 ? '∞' : fmtNum(sc.profit_factor)}</td></tr>
            <tr><td style="text-align:left">Avg win / avg loss</td><td class="pos">${fmtPct(sc.avg_win_pct)}</td></tr>
            <tr><td style="text-align:left">&nbsp;</td><td class="neg">${fmtPct(sc.avg_loss_pct)}</td></tr>
            <tr><td style="text-align:left">Avg hold: winners</td><td>${fmtNum(sc.avg_hold_win, 1)}d</td></tr>
            <tr><td style="text-align:left">Avg hold: losers</td><td>${fmtNum(sc.avg_hold_loss, 1)}d</td></tr>
            <tr><td style="text-align:left">Traded with / against signal</td><td>${sc.traded_with_signal} / ${sc.traded_against_signal}</td></tr>
          </tbody></table>
        </div>
      </div>
      <div style="padding:0 12px 12px">${sc.notes.map(n => `<div class="notice warn" style="margin:6px 0">${n}</div>`).join('')}</div>
      </div>`;
  }

  /* trade log */
  $('#p-trades').innerHTML = !d.trades.length ? '' :
    `<table><thead><tr><th>Closed</th><th>Coin</th><th>In</th><th>Out</th><th>P&amp;L</th>
      <th>Return</th><th>Held</th><th>Conv.</th><th style="text-align:left">Entry reason</th>
      <th style="text-align:left">Exit reason</th></tr></thead><tbody>
    ${d.trades.map(t => `<tr>
      <td>${dtt(t.ts)}</td><td><b>${t.symbol}</b></td>
      <td>${fmtUsd(t.entry_price)}</td><td>${fmtUsd(t.exit_price)}</td>
      <td class="${cls(t.pnl)}">${fmtUsd(t.pnl)}</td>
      <td class="${cls(t.pnl_pct)}">${fmtPct(t.pnl_pct)}</td>
      <td>${fmtNum(t.held_days, 1)}d</td><td>${'●'.repeat(t.confidence)}</td>
      <td style="text-align:left" class="muted">${t.entry_reason}</td>
      <td style="text-align:left" class="muted">${t.exit_reason}</td>
    </tr>`).join('')}</tbody></table>`;

  gl('#paper-stats', '#paper-msg', '#p-score', '#p-positions');
}

async function buyPaper() {
  const btn = $('#p-buy');
  const reason = $('#p-reason').value.trim();
  if (reason.length < 3) { msg('#paper-msg', 'warn', 'Write down why first. Skipping this step defeats the purpose.'); return; }
  busy(btn, true, 'Buying…');
  try {
    S.paper = await api('/api/paper/buy', {
      symbol: $('#p-symbol').value, usd: +$('#p-usd').value,
      reason, confidence: +$('#p-conf').value, ...paperCtx(),
    });
    $('#p-reason').value = '';
    renderPaper();
  } catch (e) { msg('#paper-msg', 'err', e.message); }
  finally { busy(btn, false); }
}

async function sellPosition(symbol, fraction) {
  const reason = prompt(`Closing ${fraction === 1 ? 'all of' : 'half of'} your ${symbol}.\n\nWhy? (Be honest — "panicked" is a valid and useful answer.)`);
  if (reason === null) return;
  try {
    S.paper = await api('/api/paper/sell', { symbol, fraction, reason, ...paperCtx() });
    renderPaper();
  } catch (e) { msg('#paper-msg', 'err', e.message); }
}

async function checkSignals() {
  const btn = $('#p-signals');
  busy(btn, true, 'Checking…');
  const symbols = $('#p-watch').value.split(',').map(s => s.trim().toUpperCase()).filter(Boolean);
  try {
    const d = await api('/api/signals', { symbols, ...paperCtx() });
    $('#p-sig-label').textContent = d.strategy_label + ' · ' + d.timeframe;
    $('#p-signals-out').innerHTML = `<table><thead><tr><th>Coin</th><th>Price</th><th>Says</th>
      <th>Now</th><th>RSI</th><th>ADX</th><th>Vol</th><th>Trend</th><th>2×ATR stop</th></tr></thead><tbody>
      ${d.signals.map(s => {
      const [k, txt] = ACTION_STYLE[s.action] || ['muted', s.action];
      return `<tr><td><b>${s.symbol}</b></td><td>${fmtUsd(s.price)}</td>
        <td class="${k}"><b>${txt}</b></td>
        <td><span class="pill ${s.state === 'LONG' ? 'long' : s.state === 'SHORT' ? 'short' : ''}">${s.state}</span></td>
        <td class="${s.rsi < 35 ? 'pos' : s.rsi > 70 ? 'neg' : ''}">${fmtNum(s.rsi, 0)}</td>
        <td>${fmtNum(s.adx, 0)}</td>
        <td>${fmtNum(s.atr_pct, 1)}%</td>
        <td>${s.trend_up ? '<span class="pos">up</span>' : '<span class="neg">down</span>'}</td>
        <td class="muted">${fmtUsd(s.atr_stop_2x)}</td></tr>`;
    }).join('')}</tbody></table>
      ${d.failed.length ? `<div class="muted small" style="padding:6px 0">Couldn't load: ${d.failed.map(f => f.symbol).join(', ')}</div>` : ''}
      <div class="muted small" style="padding:8px 0">Read from the last <i>closed</i> candle, so it won't
      flicker as the current one forms. The 2×ATR column is a volatility-scaled stop level — a starting
      point for where a long position stops making sense.</div>`;
    gl('#p-signals-out');
    await api('/api/paper/watchlist', { symbols });
  } catch (e) { msg('#paper-msg', 'err', e.message); }
  finally { busy(btn, false); }
}

async function resetPaper() {
  if (!confirm('Wipe the portfolio and all trade history? This cannot be undone.')) return;
  S.paper = await api('/api/paper/reset', { cash: 10000 });
  renderPaper();
}

/* -------------------------------------------------------------------- app */
function switchView(name) {
  $$('.tab').forEach(t => t.classList.toggle('on', t.dataset.view === name));
  $$('.view').forEach(v => v.classList.toggle('on', v.id === 'view-' + name));
  $('#sidebar').style.display = (name === 'backtest' || name === 'optimize') ? '' : 'none';
  if (name === 'paper') loadPaper();
  if (name === 'radar' && !S.radar) loadRadar();
  if (name === 'shortlist' && !S.short) runShortlist();
  if (name === 'glossary' && !S.glossaryReady) {
    renderGlossaryTab('');
    S.glossaryReady = true;
  }
  setTimeout(() => S.charts.forEach(c => c.timeScale().fitContent()), 40);
}

async function init() {
  S.meta = await api('/api/meta');
  // One shared suggestion list. The symbol fields are free-text inputs, so any
  // ticker the exchanges carry works — the list is a convenience, not a limit.
  $('#symlist').innerHTML = S.meta.symbols.map(s => `<option value="${s}">`).join('');
  const tfs = ['15m', '1h', '4h', '12h', '1d'];
  $('#timeframe').innerHTML = S.meta.timeframes.map(t =>
    `<option ${t === '1h' ? 'selected' : ''}>${t}</option>`).join('');
  $('#scan-tf').innerHTML = tfs.map(t => `<option ${t === '4h' ? 'selected' : ''}>${t}</option>`).join('');
  const stratOpts = S.meta.strategies.map(s => `<option value="${s.key}">${s.label}</option>`).join('');
  $('#strategy').innerHTML = stratOpts;
  $('#strategy').value = 'trend_filtered_dip';

  // paper trading controls
  $('#p-strategy').innerHTML = stratOpts;
  $('#p-strategy').value = 'trend_filtered_dip';
  $('#p-tf').innerHTML = tfs.map(t => `<option ${t === '4h' ? 'selected' : ''}>${t}</option>`).join('');
  $('#p-watch').value = 'BTC, ETH, SOL';
  $('#p-buy').dataset.label = 'Buy';
  $('#p-signals').dataset.label = 'Check Signals';
  $('#p-buy').onclick = buyPaper;
  $('#p-signals').onclick = checkSignals;
  $('#p-reset').onclick = resetPaper;

  // guided trade controls
  $('#g-strategy').innerHTML = stratOpts;
  $('#g-strategy').value = 'trend_filtered_dip';
  $('#g-tf').innerHTML = tfs.map(t => `<option ${t === '4h' ? 'selected' : ''}>${t}</option>`).join('');
  $('#g-plan').dataset.label = 'Plan the Trade';
  $('#r-save').dataset.label = 'Save';
  $('#g-plan').onclick = planTrade;
  $('#r-save').onclick = saveRisk;
  $('#g-toggle-risk').onclick = () => {
    const el = $('#g-risk');
    el.style.display = el.style.display === 'none' ? '' : 'none';
  };

  ['run', 'run-compare', 'run-scan'].forEach(id => { const b = $('#' + id); if (b) b.dataset.label = b.textContent; });

  buildParams();
  $('#strategy').onchange = buildParams;
  $('#run').onclick = runBacktest;
  $('#run-compare').onclick = runCompare;
  $('#run-scan').onclick = runScan;
  $('#refresh').onclick = () => { S.forceRefresh = true; runBacktest(); };
  // Tickers are uppercase everywhere; normalise as they type so the field
  // always matches what actually gets sent.
  ['#symbol', '#p-symbol', '#g-symbol'].forEach(id => {
    const el = $(id);
    el.oninput = () => {
      const p = el.selectionStart;
      el.value = el.value.toUpperCase().replace(/[^A-Z0-9]/g, '');
      el.setSelectionRange(p, p);
    };
  });

  $$('.tab').forEach(t => t.onclick = () => switchView(t.dataset.view));
  $('#gl-search').oninput = e => renderGlossaryTab(e.target.value);

  // shortlist
  $('#s-tf').innerHTML = tfs.map(t => `<option ${t === '4h' ? 'selected' : ''}>${t}</option>`).join('');
  $('#s-run').dataset.label = 'Rank the Market';
  $('#s-run').onclick = runShortlist;
  $('#s-verify').onclick = verifyFormula;

  // radar
  $('#n-refresh').dataset.label = 'Refresh Feeds';
  $('#n-refresh').onclick = loadRadar;
  $('#n-query').onkeydown = e => { if (e.key === 'Enter') loadRadar(); };
  $('#n-hours').onchange = loadRadar;
  $$('#view-radar .tab[data-sub]').forEach(b => b.onclick = () => {
    $$('#view-radar .tab[data-sub]').forEach(x => x.classList.toggle('on', x === b));
    $$('#view-radar .subview').forEach(v =>
      v.style.display = v.id === 'sub-' + b.dataset.sub ? '' : 'none');
  });
  // The static explainer tab benefits from the same inline definitions.
  glossify($('#view-learn'));
  $$('#ov_ema,#ov_bb,#ov_vwap,#ov_marks').forEach(c => c.onchange = () => S.result && renderCharts());
  document.addEventListener('keydown', e => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) runBacktest();
  });

  runBacktest();
}

init().catch(e => document.body.insertAdjacentHTML('afterbegin',
  `<div class="notice err" style="margin:20px">Startup failed: ${e.message}</div>`));
