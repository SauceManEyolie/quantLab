/* glossary.js — plain-English definitions, auto-linked into the UI.
 *
 * Any term below gets a dotted underline wherever it appears in rendered output.
 * Hover (or tap) it for the explanation. The point is that you never have to
 * leave the screen you're working on to look something up.
 *
 * Each entry:
 *   t     title shown in the popover
 *   s     one-line version — what it IS
 *   d     the useful part — what it's FOR, or how it misleads
 *   code  optional analogy for someone who programs
 *   alt   extra spellings/phrasings that should also link
 *   exact true = match case-sensitively (for LONG / FLAT / R, which are also
 *         ordinary English words in lowercase)
 */

const GLOSSARY = {
  /* ---------------------------------------------------------- the data --- */
  candle: {
    t: 'Candle', alt: ['candles', 'bar', 'bars', 'candlestick'],
    s: 'A time bucket summarising price over one period.',
    d: 'Four numbers: open (first trade), high, low, close (last trade). A "4h candle" summarises four hours. The app only ever uses finished candles — trading off one that is still forming leaks partial future information into a backtest.',
    code: 'A GROUP BY over time keeping first / max / min / last. Literally the resample() function in data.py.',
  },
  timeframe: {
    t: 'Timeframe', alt: ['timeframes'],
    s: 'How much time each candle covers.',
    d: 'Bigger buckets mean less noise, fewer decisions, and slower results. Checking a few times a day fits 1h or 4h, holding for days to weeks. Short timeframes lose to fees.',
    code: 'Your sampling rate. Downsampling trades resolution for signal-to-noise.',
  },
  open: { t: 'Open', s: 'The first traded price of a candle.', d: 'The app fills every order at the NEXT candle\'s open — you never get the price that made you want to trade.' },
  close: { t: 'Close', alt: ['closing price'], s: 'The last traded price of a candle.', d: 'Signals are computed from closes because a close is settled. The current forming price changes until the candle ends.' },
  volume: {
    t: 'Volume', s: 'How much was traded during a candle.',
    d: 'Mostly noise on its own. Useful as a spike detector: unusually high volume means something actually happened rather than price drifting.',
  },

  /* -------------------------------------------------------- indicators --- */
  indicator: {
    t: 'Indicator', alt: ['indicators'],
    s: 'A function computed over a rolling window of recent prices.',
    d: 'That is all any of them are. No hidden theory — every indicator in this app is a few lines of pandas you can read in indicators.py. The names are intimidating; the maths is not.',
    code: 'Rolling-window aggregations. You have written these before under different names.',
  },
  'moving average': {
    t: 'Moving average', alt: ['moving averages'],
    s: 'The average price over the last N candles, recalculated each candle.',
    d: 'Smooths out noise so direction becomes visible. The 200-period one is the most-watched "is this in an uptrend" line in all of trading.',
    code: 'A low-pass filter. Strips high-frequency noise to expose the trend.',
  },
  sma: { t: 'SMA (Simple Moving Average)', s: 'A plain average of the last N candles.', d: 'Every candle in the window counts equally.', code: 'Uniform-weight rolling mean.' },
  ema: {
    t: 'EMA (Exponential Moving Average)',
    s: 'A moving average that weights recent candles more heavily.',
    d: 'Turns faster than an SMA, so you get earlier signals and more false ones. Which is better depends entirely on whether the market is trending or chopping.',
    code: 'Exponentially weighted rolling mean — an IIR filter rather than FIR.',
  },
  rsi: {
    t: 'RSI (Relative Strength Index)',
    s: 'Of recent price moves, what share were upward — scaled 0 to 100.',
    d: 'Above 70 means heavy buying lately ("overbought"), below 30 heavy selling ("oversold"). THE COMMON MISTAKE: treating 70 as a sell signal. In a strong trend RSI sits above 70 for weeks while price keeps climbing. It is a condition, not a signal — it only becomes useful combined with a trend filter.',
    code: 'Ratio of positive deltas to total absolute deltas over a window, normalised to 0-100.',
  },
  atr: {
    t: 'ATR (Average True Range)',
    s: 'The average size of a candle, in dollars.',
    d: 'The least glamorous and most useful number here. It is your unit of "normal movement" — if the average 4h candle is $600, a $600 move means nothing happened. The app uses it to place stops far enough away that ordinary noise cannot reach them.',
    code: 'Mean absolute change per bucket. Like a standard deviation but in price units, so it is directly comparable to a stop distance.',
  },
  adx: {
    t: 'ADX', s: 'Trend STRENGTH — not direction.',
    d: 'Above about 25 means a real trend is happening. Below 20 means chop, and breakout strategies fail in chop. Best used as a filter: run trend strategies only when ADX is high.',
    code: 'A signal-to-noise ratio for directional movement.',
  },
  macd: {
    t: 'MACD', s: 'Fast EMA minus slow EMA, plus a signal line.',
    d: 'A crossover system in different clothing. The histogram flipping from negative to positive is the classic bullish cue.',
    code: 'A band-pass filter — the difference of two low-pass filters at different cutoffs.',
  },
  'bollinger bands': {
    t: 'Bollinger Bands', alt: ['bollinger band', 'bollinger'],
    s: 'A moving average plus and minus two standard deviations.',
    d: 'Bands squeeze when quiet and expand when wild. Price at the lower band means "unusually cheap relative to its own recent range" — which is not the same as cheap.',
    code: 'Rolling mean ± 2 × rolling std. A z-score, drawn.',
  },
  donchian: {
    t: 'Donchian Channel', alt: ['donchian channel'],
    s: 'The highest high and lowest low of the last N candles.',
    d: 'The basis of the Turtle Traders system: buy when price breaks above the N-candle high. Feels awful to trade because you are always buying the top, and has made a lot of money.',
    code: 'Rolling max and min, shifted one bar so the current bar cannot be part of the level it is breaking.',
  },
  vwap: { t: 'VWAP', s: 'Volume-weighted average price.', d: 'The "fair value" large traders benchmark against — where the average dollar actually transacted.' },
  'volume z-score': {
    t: 'Volume z-score', alt: ['vol z', 'z-score'],
    s: 'How unusual today\'s volume is, in standard deviations.',
    d: 'Above 2 means something actually happened — news, a large player, a liquidation cascade. Closest thing to a free signal here, because it is evidence rather than inference.',
    code: '(x − rolling mean) / rolling std. Exactly the normalisation you already know.',
  },
  volatility: {
    t: 'Volatility',
    s: 'How violently price moves, in either direction.',
    d: 'Not the same as risk of loss — it cuts both ways. High volatility forces wider stops, which forces smaller positions.',
  },

  /* ------------------------------------------------------------ trades --- */
  'position size': {
    t: 'Position size', alt: ['position sizing'],
    s: 'How many dollars you put into one trade.',
    d: 'An OUTPUT, not a choice. You decide what you are willing to lose and where the idea is disproven; the size falls out of those two. Picking a size first and then hunting for a stop is backwards, and it is what most beginners do.',
  },
  'stop loss': {
    t: 'Stop-loss', alt: ['stop-loss', 'stop', 'stops', 'stop price'],
    s: 'A price where you exit, decided in advance.',
    d: 'A circuit breaker installed before you have any emotional stake in the outcome. Its entire purpose is that present-you does not trust future-you to be rational at 2am with money on the line.',
    code: 'A precondition check that runs every tick. You commit to the branch before you know the input.',
  },
  'trailing stop': {
    t: 'Trailing stop',
    s: 'A stop that moves up as price rises, but never down.',
    d: 'Locks in gains while letting a winner keep running. The trade-off is that normal pullbacks will sometimes stop you out of a trade that then continues without you.',
  },
  'take profit': {
    t: 'Take profit', alt: ['target', 'target price'],
    s: 'A price where you close the trade in profit.',
    d: 'Answering "where am I done?" in advance is the blank most people leave empty — which is exactly why they hold losers and sell winners early.',
  },
  'risk per trade': {
    t: 'Risk per trade', alt: ['risk %', 'dollars at risk', 'at risk'],
    s: 'What you lose if the stop hits — not what you invest.',
    d: 'Put $2,500 in with a stop 4% below, and you risk $100. On a $10,000 account that is 1%. At 2% risk you can be wrong 50 times in a row and still be trading, which is the entire point.',
  },
  'reward:risk': {
    t: 'Reward-to-risk', alt: ['reward vs risk', 'reward to risk', 'reward : risk', 'r:r'],
    s: 'How much you aim to make versus how much you can lose.',
    d: 'At 2:1 you only need to be right about 33% of the time to break even. This is why win rate alone tells you almost nothing.',
  },
  'r-multiple': {
    t: 'R (unit of risk)', alt: ['r multiple'], exact: false,
    s: '1R = the dollars you risked on that trade.',
    d: 'Made $200 having risked $100? That is +2R. Once you measure in R, position sizes stop mattering and every trade becomes comparable regardless of account size.',
    code: 'Normalisation. You are dividing out the scale so trades are comparable across magnitudes.',
  },
  long: {
    t: 'LONG', exact: true, alt: ['LONG'],
    s: 'You own the asset and profit if it rises.',
    d: 'The normal way to trade. "Going long BTC" just means buying BTC.',
  },
  short: {
    t: 'SHORT', exact: true, alt: ['SHORT'],
    s: 'You profit if the price falls.',
    d: 'You borrow the asset, sell it, and buy it back cheaper. Losses are theoretically unlimited because price can rise forever. Off by default in this app for that reason.',
  },
  flat: {
    t: 'FLAT', exact: true, alt: ['FLAT'],
    s: 'Holding no position — all cash.',
    d: 'An entirely valid state. Most of the time, for most strategies, flat is correct.',
  },
  signal: {
    t: 'Signal', alt: ['signals'],
    s: 'What your strategy says to do right now.',
    d: 'Read from the last CLOSED candle deliberately. Signals based on the forming candle flicker and vanish, which trains you to chase.',
  },
  'cost basis': { t: 'Cost basis', s: 'The average price you paid for what you hold.', d: 'If you buy twice at different prices, this blends them. Your profit is measured from here.' },
  unrealized: {
    t: 'Unrealised P&L', alt: ['unrealised', 'unrealized p&l'],
    s: 'Profit on positions you still hold.',
    d: 'Not money yet. It moves every second and can vanish entirely.',
  },
  realized: {
    t: 'Realised P&L', alt: ['realised', 'realized p&l'],
    s: 'Profit on trades you have actually closed.',
    d: 'This is the only number that is real.',
  },
  equity: { t: 'Equity', s: 'Total account value — cash plus everything you hold at current prices.', d: 'The single number that tracks whether you are actually getting anywhere.' },
  conviction: {
    t: 'Conviction', alt: ['conviction edge'],
    s: 'How sure you were, rated 1-5, recorded before you know the outcome.',
    d: 'The scorecard checks whether your 4-5 rated trades actually beat your 1-2 rated ones. If they do not, your confidence carries no information — uncomfortable, extremely useful, and impossible to discover without writing it down first.',
  },

  /* ----------------------------------------------------------- judging --- */
  backtest: {
    t: 'Backtest', alt: ['backtesting', 'backtested'],
    s: 'Running your rules over historical data to score them.',
    d: 'A filter for BAD ideas, not proof of good ones. A strategy that fails here will almost certainly fail live; one that succeeds has merely earned the right to be paper-traded next.',
    code: 'Evaluating a model on a fixed dataset. Same epistemics, same failure modes.',
  },
  'buy and hold': {
    t: 'Buy & hold', alt: ['buy & hold', 'buy-and-hold'],
    s: 'Buy on day one, never sell.',
    d: 'Your benchmark, and beating it is the whole game. A strategy returning 40% while holding returned 90% means you did more work, took more risk, paid more fees, and made less. Most strategies lose to this.',
    code: 'The naive baseline. If your model cannot beat it, you do not have a model.',
  },
  drawdown: {
    t: 'Drawdown', alt: ['max drawdown', 'maximum drawdown', 'max dd'],
    s: 'The worst peak-to-trough fall in account value.',
    d: 'Hit $12k then dropped to $7k? That is −42%. This predicts whether you will still be running a strategy in six months better than returns do, because nobody sits through −60%.',
  },
  'win rate': {
    t: 'Win rate',
    s: 'The share of trades that made money.',
    d: 'The most misleading stat in trading. A 90% win rate is worthless if the 10% of losses are each 20× a win. Trend systems typically win 35% of the time and make money anyway.',
  },
  'profit factor': {
    t: 'Profit factor',
    s: 'Gross wins divided by gross losses.',
    d: 'Above 1.5 is decent, above 2 is strong, below 1 loses money. Far more honest than win rate because it accounts for size, not just frequency.',
  },
  expectancy: { t: 'Expectancy', s: 'Average dollars made per trade, wins and losses combined.', d: 'What you actually earn for pulling the trigger once.' },
  sharpe: {
    t: 'Sharpe ratio', alt: ['sharpe'],
    s: 'Return per unit of bumpiness.',
    d: 'Under 1 is weak, 1-2 respectable. Above 2 in a backtest usually means you overfit something — be suspicious of your own good results.',
  },
  sortino: { t: 'Sortino ratio', alt: ['sortino'], s: 'Like Sharpe, but only counts downside volatility.', d: 'Upward jumps are not risk. This fixes that.' },
  cagr: { t: 'CAGR', s: 'Annualised growth rate.', d: 'Turns "made 60% over 18 months" into a per-year figure you can compare against anything else.' },
  alpha: { t: 'Alpha', s: 'How much you beat the benchmark by.', d: 'Here it means your return minus buy-and-hold. Negative alpha means the trading was worse than doing nothing.' },
  overfitting: {
    t: 'Overfitting', alt: ['overfit', 'curve-fit', 'curve fitting'],
    s: 'Tuning until it looks perfect on past data by memorising noise.',
    d: 'The central danger of this whole activity. Test 50 parameter combinations and the best one looks brilliant by chance alone. In trading you do not find out from a bad eval score — you find out by losing money.',
    code: 'Exactly the ML term, meaning exactly the same thing. Training accuracy 99%, test accuracy 51%.',
  },
  'in-sample': {
    t: 'In-sample', alt: ['in sample', 'is return'],
    s: 'The slice of history you optimised on.',
    d: 'Results here are always flattering. They have to be — you chose the settings to make them good.',
    code: 'Your training set.',
  },
  'out-of-sample': {
    t: 'Out-of-sample', alt: ['out of sample', 'oos', 'oos return'],
    s: 'The slice of history the optimiser never saw.',
    d: 'The only honest number in an optimisation. If in-sample winners fall apart here, you found a coincidence rather than an edge.',
    code: 'Your held-out test set. Same reason you never report training accuracy.',
  },
  slippage: {
    t: 'Slippage',
    s: 'The gap between the price you wanted and the price you got.',
    d: 'Small on BTC, brutal on small coins. Modelled here as buying slightly high and selling slightly low, because that is what happens.',
    code: 'Theoretical throughput versus actual throughput.',
  },
  bps: {
    t: 'Basis points (bps)', alt: ['basis point', 'basis points'],
    s: 'One hundredth of a percent. 10 bps = 0.1%.',
    d: 'Just a unit, like using milliseconds instead of seconds. Retail crypto fees run roughly 10 bps per side, so a round trip costs about 0.2%.',
  },
  fee: {
    t: 'Fees', alt: ['fees', 'trading fee'],
    s: 'What the exchange charges, on both sides of every trade.',
    d: 'A strategy trading 200 times a year at 0.1% per side burns about 40% of gross profit. Some "profitable" systems are just fee generators.',
  },
  'time in market': {
    t: 'Time in market', alt: ['exposure'],
    s: 'What share of the period you were actually holding something.',
    d: 'Low numbers mean less exposure to overnight shocks. A strategy matching buy-and-hold\'s return while being invested 30% of the time is doing something genuinely better.',
  },

  /* ------------------------------------------------------- strategies --- */
  trend: {
    t: 'Trend', alt: ['trending', 'trend filter'],
    s: 'Whether price has generally been rising or falling.',
    d: 'Usually measured as "is price above its 200-period moving average". Adding this one filter to almost any strategy improves it — not because the line is magic, but because it keeps you out during the periods that do the most damage.',
  },
  'mean reversion': {
    t: 'Mean reversion',
    s: 'Betting that price snaps back to its average after a stretch.',
    d: 'Works in range-bound markets, gets run over by strong trends. The opposite family to trend-following.',
  },
  breakout: {
    t: 'Breakout',
    s: 'Buying when price pushes above a recent high.',
    d: 'Low win rate, occasional very large winners. Requires letting winners run, which is psychologically the hardest thing on this list.',
  },
  regime: {
    t: 'Regime', alt: ['regime filter'],
    s: 'What kind of market you are currently in — trending or chopping.',
    d: 'The same strategy can be excellent in one regime and terrible in the other. Filtering by regime is usually worth more than tuning any parameter.',
  },
  liquidation: {
    t: 'Liquidation cascade', alt: ['liquidation'],
    s: 'Forced selling that triggers more forced selling.',
    d: 'Leveraged traders get closed out automatically, which pushes price down, which closes out more of them. Why crypto crashes are so sharp.',
  },
};

/* ------------------------------------------------------------------------ */
/* Auto-linking                                                              */
/* ------------------------------------------------------------------------ */

// Longest terms first so "moving average" wins over "average" fragments.
// For case-sensitive entries (LONG / SHORT / FLAT) we deliberately drop the
// lowercase key, so ordinary English prose — "a long position", "short on
// time" — never gets underlined. Only the uppercase UI labels link.
const GL_ENTRIES = (() => {
  const out = [];
  for (const [key, v] of Object.entries(GLOSSARY)) {
    const phrases = v.exact ? (v.alt || []) : [key, ...(v.alt || [])];
    for (const phrase of phrases) out.push({ key, phrase, exact: !!v.exact });
  }
  return out.sort((a, b) => b.phrase.length - a.phrase.length);
})();

const esc = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const GL_SKIP = new Set(['SCRIPT', 'STYLE', 'INPUT', 'SELECT', 'TEXTAREA', 'OPTION', 'BUTTON']);

/**
 * Word-boundary regex for a phrase.
 * \b only works next to a word character, so a phrase like "risk %" or "r:r"
 * must not get a trailing \b — it would never match anything.
 */
function glRegex(phrase, exact) {
  const lead = /^\w/.test(phrase) ? '\\b' : '';
  const tail = /\w$/.test(phrase) ? '\\b' : '';
  return new RegExp(lead + esc(phrase) + tail, exact ? '' : 'i');
}

/**
 * Wrap known glossary terms in the given element with hoverable spans.
 * Operates on text nodes only, so it can never corrupt markup or attributes.
 * Each term is linked at most once per call — enough to be useful, not so much
 * that the page turns into a sea of dotted underlines.
 */
function glossify(root) {
  if (!root) return;
  const used = new Set();
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      if (!node.nodeValue || node.nodeValue.trim().length < 2) return NodeFilter.FILTER_REJECT;
      for (let p = node.parentNode; p && p !== root; p = p.parentNode) {
        if (GL_SKIP.has(p.nodeName) || (p.classList && p.classList.contains('gl'))) {
          return NodeFilter.FILTER_REJECT;
        }
      }
      return NodeFilter.FILTER_ACCEPT;
    },
  });

  const targets = [];
  while (walker.nextNode()) targets.push(walker.currentNode);

  for (const node of targets) {
    const parts = [];       // alternating plain strings and {key, text} hits
    let rest = node.nodeValue;
    let found = false;

    // Keep consuming the text left-to-right. Ties at the same position go to
    // the longest phrase, because GL_ENTRIES is sorted longest-first and we
    // only replace the incumbent on a STRICTLY earlier match.
    while (rest) {
      let best = null;
      for (const e of GL_ENTRIES) {
        if (used.has(e.key)) continue;
        const m = glRegex(e.phrase, e.exact).exec(rest);
        if (m && (!best || m.index < best.index)) best = { e, index: m.index, match: m[0] };
      }
      if (!best) break;
      used.add(best.e.key);
      found = true;
      parts.push(rest.slice(0, best.index));
      parts.push({ key: best.e.key, text: best.match });
      rest = rest.slice(best.index + best.match.length);
    }
    if (!found) continue;
    parts.push(rest);

    const frag = document.createDocumentFragment();
    for (const p of parts) {
      if (typeof p === 'string') {
        if (p) frag.append(document.createTextNode(p));
      } else {
        const span = document.createElement('span');
        span.className = 'gl';
        span.dataset.gl = p.key;
        span.textContent = p.text;
        frag.append(span);
      }
    }
    node.parentNode.replaceChild(frag, node);
  }
}

/* ------------------------------------------------------------------------ */
/* Popover                                                                   */
/* ------------------------------------------------------------------------ */

let glPop = null;

function glPopover() {
  if (glPop) return glPop;
  glPop = document.createElement('div');
  glPop.id = 'gl-pop';
  document.body.appendChild(glPop);
  return glPop;
}

function showGlossary(el) {
  const v = GLOSSARY[el.dataset.gl];
  if (!v) return;
  const pop = glPopover();
  pop.innerHTML = `
    <div class="gt">${v.t}</div>
    <div class="gs">${v.s}</div>
    <div class="gd">${v.d}</div>
    ${v.code ? `<div class="gc"><b>In code terms:</b> ${v.code}</div>` : ''}`;
  pop.style.display = 'block';

  const r = el.getBoundingClientRect();
  const w = 330;
  pop.style.width = w + 'px';
  let left = Math.min(Math.max(8, r.left), window.innerWidth - w - 8);
  const h = pop.offsetHeight;
  let top = r.bottom + 7;
  if (top + h > window.innerHeight - 8) top = Math.max(8, r.top - h - 7);
  pop.style.left = left + 'px';
  pop.style.top = top + 'px';
}

function hideGlossary() { if (glPop) glPop.style.display = 'none'; }

document.addEventListener('mouseover', e => {
  const el = e.target.closest && e.target.closest('.gl');
  if (el) showGlossary(el);
});
document.addEventListener('mouseout', e => {
  if (e.target.closest && e.target.closest('.gl')) hideGlossary();
});
document.addEventListener('click', e => {
  const el = e.target.closest && e.target.closest('.gl');
  if (el) { showGlossary(el); e.stopPropagation(); } else hideGlossary();
});
window.addEventListener('scroll', hideGlossary, true);

/* ------------------------------------------------------------------------ */
/* The reference tab                                                         */
/* ------------------------------------------------------------------------ */

const GL_GROUPS = [
  ['The data', ['candle', 'timeframe', 'open', 'close', 'volume']],
  ['Indicators — all just rolling-window functions', ['indicator', 'moving average', 'sma', 'ema', 'rsi', 'atr', 'adx', 'macd', 'bollinger bands', 'donchian', 'vwap', 'volume z-score', 'volatility']],
  ['Making a trade', ['position size', 'stop loss', 'trailing stop', 'take profit', 'risk per trade', 'reward:risk', 'r-multiple', 'long', 'short', 'flat', 'signal', 'cost basis', 'unrealized', 'realized', 'equity', 'conviction']],
  ['Judging whether it works', ['backtest', 'buy and hold', 'drawdown', 'win rate', 'profit factor', 'expectancy', 'sharpe', 'sortino', 'cagr', 'alpha', 'overfitting', 'in-sample', 'out-of-sample', 'slippage', 'bps', 'fee', 'time in market']],
  ['Kinds of strategy', ['trend', 'mean reversion', 'breakout', 'regime', 'liquidation']],
];

function renderGlossaryTab(filter) {
  const q = (filter || '').trim().toLowerCase();
  const html = GL_GROUPS.map(([title, keys]) => {
    const items = keys.filter(k => {
      if (!q) return true;
      const v = GLOSSARY[k];
      return (k + ' ' + v.t + ' ' + v.s + ' ' + v.d + ' ' + (v.code || '')).toLowerCase().includes(q);
    });
    if (!items.length) return '';
    return `<h3 class="sect" style="margin:22px 0 12px">${title}</h3>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:9px">
      ${items.map(k => {
      const v = GLOSSARY[k];
      return `<div class="card"><div style="padding:12px 14px">
          <div style="font-weight:600;margin-bottom:4px">${v.t}</div>
          <div style="color:var(--accent);margin-bottom:7px">${v.s}</div>
          <div class="muted" style="line-height:1.6">${v.d}</div>
          ${v.code ? `<div class="muted small" style="margin-top:8px;padding-top:8px;border-top:1px solid var(--line)">
            <b>In code terms:</b> ${v.code}</div>` : ''}
        </div></div>`;
    }).join('')}</div>`;
  }).join('');
  document.querySelector('#gl-list').innerHTML = html ||
    '<div class="empty">Nothing matches that.</div>';
}
