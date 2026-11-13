# QuantLab

A free, local TradingView-style research tool for crypto: real candles, real indicators,
and a backtest engine that refuses to lie to you.

Everything runs on your machine. No accounts, no API keys, no subscription, no data leaves
your computer.

---

## Run it

```bash
pip3 install pandas numpy      # the entire dependency list
cd quantlab
python3 run.py
```

Your browser opens at `http://127.0.0.1:8777`.

```bash
python3 run.py --demo      # fabricated data — try the UI with no internet
python3 run.py --test      # run the 55-test correctness suite
python3 run.py --port 9000
```

The first backtest on a new coin/timeframe downloads history (10–60s for a year of
hourly candles). After that it's cached in `cache/` and instant. The `↻` button
in the header forces a fresh download.

---

## What's in it

**Shortlist** — ranks the market 0–100 on six weighted, measurable factors, showing exactly how
many points each factor contributed to each coin. Critically, **the same formula is registered as
a backtestable strategy** (`quality_score`), so you can test the ranking rule itself over years of
history before trusting what it says about today. Relative strength vs BTC and news attention are
shown but deliberately excluded from the score — neither can be backtested, and blending them in
would make the whole thing unfalsifiable.

**Guided Trade** — the beginner entry point. Pick a coin, click Plan, and it fills in the four
numbers every trade needs: what to buy, how much (sized backwards from your risk tolerance and
current volatility), where you're wrong (an ATR-scaled stop), and where you're done (the exit
rule, in advance). Each with a plain-English sentence, a go/no-go verdict from your strategy,
and one click to execute on paper.

**Backtest** — pick a coin, timeframe, strategy, and risk settings. Get a candlestick chart
with trade markers, an equity curve against buy-and-hold, RSI and MACD panels, a full
metrics panel, and every individual trade in a table.

**Compare Strategies** — runs all 11 strategies on the same data and ranks them. Click any
row to load it.

**Optimize** — sweeps parameter ranges, but splits history 70/30 first: it optimizes on the
first 70% and reports how those same settings did on the untouched last 30%. It tells you
when the "best" parameters are just fitted noise.

**Radar** — information feeds. Aggregated headlines from CoinDesk, Cointelegraph, Decrypt,
CryptoSlate, The Block, Bitcoin Magazine, three subreddits and Google News (all free RSS, no
keys). A **narrative tracker** that counts which names appear across your feeds, weighting recent
mentions and rewarding coverage by *many different outlets* over repetition by one. CoinGecko
trending. And a new-Solana-token feed from GeckoTerminal that ships with the documented survival
base rates and mechanical risk flags — liquidity, age, volume-to-liquidity ratio, buy/sell skew.

**Scanner** — scores a basket of coins on current conditions (trend, RSI, MACD turns, ADX,
volume spikes) and ranks them. A research shortlist, not a buy list.

**Paper Trading** — a $10,000 fake portfolio at real live prices, persisted to disk. Every trade
requires a written reason and a conviction rating 1–5, and is stamped with what the systematic
strategy said at that moment. The scorecard then computes your **Conviction Edge**: whether your
high-conviction trades actually beat your low-conviction ones. If they don't, your confidence
carries no information — which is the most useful thing you can learn about your own trading and
the one you'd otherwise pay real money for.

**Glossary** — 56 terms in plain English, searchable. Terms are also auto-underlined everywhere
in the app: hover any of them for the definition without leaving what you're doing. Most entries
include a "in code terms" analogy (a candle is a `GROUP BY` over time; overfitting is the ML term
meaning exactly the same thing).

**How to read this** — a plain-English tab explaining every metric and, more usefully, which
ones are misleading.

See **[PLAYBOOK.md](PLAYBOOK.md)** for the full workflow: what every term means, how to turn a
vague idea into a testable hypothesis, the five-gate validation gauntlet, and a four-week plan.

---

## Why the numbers here are worse than other backtesters

Because the pessimism is deliberate. Every one of these is a place where sloppier tools
quietly manufacture profit:

| Rule | Why |
|---|---|
| Signals fire on a bar's close, fill at the **next** bar's open | You never get the price that made you want to trade. This is enforced structurally — the loop cannot fill on the signal bar. |
| Fees charged on **both** sides of every round trip | A 0.1% fee on a strategy trading 200 times a year is a 40% drag on gross. |
| Slippage: buy a little high, sell a little low | Your order moves the book, especially on small coins. |
| Stops checked against the bar's **high/low**, not its close | A stop that only checks closes never actually gets hit. |
| If one bar could have hit both stop and target, the **stop** wins | We can't see inside a candle. Optimism here is how people blow up. |
| The still-forming candle is dropped | Otherwise partial future data leaks into the final bar. |
| Position sizing scaled by `1/(1+fee)` | You can't spend 100% of your account AND pay the fee. |
| After a stop fires, that direction is locked out until the signal goes flat | Prevents "stopped out, buy back, stopped out" fee-shredding loops. |

There's a regression test for each of these in `tests/test_all.py`. Run `python3 run.py --test`.

---

## The three things worth internalizing

**1. Beating buy-and-hold is the whole game.** Bitcoin rose over most historical windows.
A strategy returning 40% while holding returned 90% means you did more work, took more risk,
paid more fees, and made less. Most strategies lose to holding. Finding that out here costs
nothing; finding it out live costs money.

**2. Max drawdown matters more than return.** A strategy that returns 200% with a 70%
drawdown is one you will abandon at the bottom. Everyone does. Drawdown predicts whether
you'll still be running it in six months.

**3. Optimizing is how you fool yourself.** Test enough parameter combinations and some
look spectacular by pure chance. That's what the in-sample/out-of-sample split exists for.
Prefer a *region* where neighbouring parameter values all work over a single spectacular row —
a lone spike surrounded by bad results is noise.

---

## Files

```
run.py            entry point (--demo, --test, --port)
start.command     double-click launcher for macOS
brief.py          the spoken login briefing (also writes briefing.md)
install-greeting.command   installs/removes the login briefing via launchd
server.py         stdlib HTTP server + JSON API
data.py           free OHLCV from Binance / Binance.US / Coinbase / Kraken, with cache
indicators.py     RSI, EMA, MACD, Bollinger, ATR, ADX, Donchian, OBV, VWAP, volume z-score
engine.py         the backtest engine + performance metrics
strategies.py     12 strategies + parameter schemas
rank.py           the shortlist scoring formula — shared by the ranking AND the backtest
paper.py          paper trading portfolio, journal, and conviction scorecard
news.py           RSS/Atom aggregation, narrative tracking, new-token risk scoring
web/              index.html, app.js, glossary.js, style.css  (charts by lightweight-charts)
tests/test_all.py 179 correctness tests, no network needed
tests/test_glossary.js  41 frontend tests (needs node; skipped if absent)
PLAYBOOK.md       how to actually use all this
cache/            downloaded candles (safe to delete)
paper_state.json  your paper portfolio (delete to start over)
```

## Adding your own strategy

Open `strategies.py`, write a function returning the desired position per bar, register it:

```python
def s_my_idea(df, p):
    fast = ta.ema(df["close"], int(p["fast"]))
    entries = df["close"] > fast
    exits = df["close"] < fast
    return hold(entries, exits)      # 1 while in, 0 while out

REGISTRY["my_idea"] = {
    "label": "My Idea", "family": "trend",
    "blurb": "What it does, in one sentence.",
    "fn": s_my_idea,
    "params": [_p("fast", "Fast EMA", 20, 5, 200, 1)],
}
```

Restart the server. It appears in the dropdown with auto-generated controls — no frontend
changes needed. The only contract is: **never reference a future bar.** Use `.shift(1)` if
you need the previous value, and the no-lookahead test in the suite will catch you if you slip.

---

## API

Handy if you'd rather script than click.

```bash
curl -X POST localhost:8777/api/backtest -H 'Content-Type: application/json' -d '{
  "symbol":"BTC","timeframe":"4h","days":730,
  "strategy":"trend_filtered_dip","params":{"oversold":35},
  "config":{"initial_cash":10000,"fee_bps":10,"stop_loss_pct":5}
}'
```

`GET /api/meta` · `GET /api/price?symbol=BTC` · `GET /api/clear_cache`
`POST /api/backtest` · `POST /api/compare` · `POST /api/optimize` · `POST /api/scan`
`POST /api/signals` · `POST /api/plan` · `POST /api/risk` · `POST /api/shortlist`
`POST /api/news` · `POST /api/trending` · `POST /api/newpools`
`POST /api/paper` · `POST /api/paper/buy` · `POST /api/paper/sell` · `POST /api/paper/reset`

---

## Limits — read before risking anything

This works on closed candles, so it cannot model intrabar fills, order-book depth,
funding rates, exchange outages, or how you personally behave when down 30%.

**A backtest is a filter for bad ideas, not proof of good ones.** A strategy that fails here
will almost certainly fail live. One that succeeds here has earned the right to be
paper-traded next — nothing more.

Nothing in this tool is financial advice. Past performance does not predict future returns.
Crypto is volatile enough to lose the entire position.
