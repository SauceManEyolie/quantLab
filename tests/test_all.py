"""
test_all.py — correctness tests that run with NO network connection.

Run with:  python3 tests/test_all.py

These aren't decorative. The whole point of a backtester is that you trust its
numbers enough to risk money on them, so the arithmetic gets checked by hand
against closed-form answers wherever possible.
"""

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import data as dat            # noqa: E402
import indicators as ta       # noqa: E402
import strategies as strat    # noqa: E402
from engine import BacktestConfig, run_backtest  # noqa: E402

PASS, FAIL = 0, 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


def approx(a, b, tol=1e-6):
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


def bars(rows):
    """Build a tiny hand-made OHLCV frame. rows = [(o,h,l,c)] with volume 1."""
    t0 = 1_700_000_000
    return pd.DataFrame({
        "time": [t0 + i * 3600 for i in range(len(rows))],
        "open": [r[0] for r in rows], "high": [r[1] for r in rows],
        "low": [r[2] for r in rows], "close": [r[3] for r in rows],
        "volume": [1.0] * len(rows),
    })


# ============================================================================
print("\n--- indicators ---")
# ============================================================================

s = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=float)
check("SMA(3) last = 9.0", approx(ta.sma(s, 3).iloc[-1], 9.0))
check("SMA warmup is NaN", pd.isna(ta.sma(s, 3).iloc[1]))

# EMA by hand: alpha = 2/(3+1) = 0.5, seeded with SMA-free recursive form
e = ta.ema(s, 3)
check("EMA(3) is between SMA and last value", ta.sma(s, 3).iloc[-1] < e.iloc[-1] <= 10.0)

# RSI on a monotonically rising series must be exactly 100 (no losses at all)
rising = pd.Series(np.arange(1, 60, dtype=float))
check("RSI of pure uptrend = 100", approx(ta.rsi(rising, 14).iloc[-1], 100.0, 1e-9))
falling = pd.Series(np.arange(60, 1, -1, dtype=float))
check("RSI of pure downtrend = 0", approx(ta.rsi(falling, 14).iloc[-1], 0.0, 1e-9))

# RSI of a flat line: no gains, no losses -> our convention returns 100
flat = pd.Series([50.0] * 40)
check("RSI bounded 0..100", ta.rsi(flat, 14).dropna().between(0, 100).all())

# Bollinger: on constant data, bands collapse onto the mean
bb = ta.bollinger(flat, 20, 2.0)
check("Bollinger on flat data has zero width", approx(bb["upper"].iloc[-1], 50.0))

# ATR on bars with a constant 10-wide range and no gaps must equal 10
const = bars([(100, 105, 95, 100)] * 40)
check("ATR of constant 10-range bars = 10", approx(ta.atr(const, 14).iloc[-1], 10.0, 1e-6))

# Donchian must be shifted — the current bar can't be in its own channel
d = ta.donchian(bars([(10, 20, 5, 15)] * 5 + [(10, 99, 5, 15)]), 3)
check("Donchian excludes current bar", d["upper"].iloc[-1] == 20.0,
      f"got {d['upper'].iloc[-1]}")

# MACD hist = macd - signal, always
m = ta.macd(pd.Series(np.random.default_rng(1).normal(100, 5, 200).cumsum()))
check("MACD hist == macd - signal", np.allclose(
    (m["macd"] - m["signal"]).dropna(), m["hist"].dropna()))

# no-lookahead sanity: truncating the series must not change earlier values
full = ta.rsi(pd.Series(np.random.default_rng(2).normal(0, 1, 300).cumsum() + 100), 14)
trunc = ta.rsi(pd.Series(np.random.default_rng(2).normal(0, 1, 300).cumsum() + 100)[:200], 14)
check("RSI is causal (past values unchanged by future data)",
      np.allclose(full[:200].dropna(), trunc.dropna()))


# ============================================================================
print("\n--- engine: execution mechanics ---")
# ============================================================================

# Straight line up: 100 -> 110 over 5 bars.
df = bars([(100, 101, 99, 100), (102, 103, 101, 102), (104, 105, 103, 104),
           (106, 107, 105, 106), (108, 109, 107, 110)])
always_long = pd.Series([1.0] * 5)
cfg0 = BacktestConfig(initial_cash=1000, fee_bps=0, slippage_bps=0, size_pct=100)
r = run_backtest(df, always_long, cfg0)

# Signal at bar 0's close -> fill at bar 1's OPEN (102). Exit at final close (110).
expected = 1000 * (110 / 102)
check("entry fills at NEXT bar's open, not the signal bar",
      approx(r["stats"]["final_equity"], expected, 1e-9),
      f"got {r['stats']['final_equity']:.4f}, expected {expected:.4f}")
check("one round trip recorded", r["stats"]["num_trades"] == 1)
check("entry price == bar 1 open", approx(r["trades"][0]["entry_price"], 102.0))
check("exit price == last close", approx(r["trades"][0]["exit_price"], 110.0))

# Zero-signal strategy must do literally nothing.
r0 = run_backtest(df, pd.Series([0.0] * 5), cfg0)
check("flat signal -> no trades, cash untouched",
      r0["stats"]["num_trades"] == 0 and approx(r0["stats"]["final_equity"], 1000.0))

# Fees: 50 bps per side on a round trip = 1% total drag.
cfg_fee = BacktestConfig(initial_cash=1000, fee_bps=50, slippage_bps=0, size_pct=100)
rf = run_backtest(df, always_long, cfg_fee)
# Worked by hand: notional is scaled by 1/(1+fee) so cash never goes negative.
notional_in = 1000 / 1.005          # 995.0249
units_ = notional_in / 102          # 9.755146
expected_fee = (units_ * 110) * (1 - 0.005)   # sell proceeds minus exit fee
check("fees charged on both sides, cash never goes negative",
      approx(rf["stats"]["final_equity"], expected_fee, 1e-9),
      f"got {rf['stats']['final_equity']:.4f}, expected {expected_fee:.4f}")
check("fee case underperforms zero-fee case",
      rf["stats"]["final_equity"] < r["stats"]["final_equity"])

# Slippage: buy higher, sell lower.
cfg_slip = BacktestConfig(initial_cash=1000, fee_bps=0, slippage_bps=100, size_pct=100)
rs = run_backtest(df, always_long, cfg_slip)
check("slippage worsens entry price", rs["trades"][0]["entry_price"] > 102.0)
check("slippage worsens exit price", rs["trades"][0]["exit_price"] < 110.0)

# Position sizing: half size => roughly half the P&L.
cfg_half = BacktestConfig(initial_cash=1000, fee_bps=0, slippage_bps=0, size_pct=50)
rh = run_backtest(df, always_long, cfg_half)
pnl_full = r["stats"]["final_equity"] - 1000
pnl_half = rh["stats"]["final_equity"] - 1000
check("50% sizing halves the P&L", approx(pnl_half, pnl_full / 2, 1e-9),
      f"{pnl_half:.4f} vs {pnl_full/2:.4f}")


# ============================================================================
print("\n--- engine: risk exits ---")
# ============================================================================

# Enter at 100, then a bar that dips to 88. A 10% stop must fire at 90.
dfs = bars([(100, 101, 99, 100), (100, 101, 99, 100), (100, 101, 88, 95),
            (95, 96, 94, 95), (95, 96, 94, 95)])
cfg_stop = BacktestConfig(initial_cash=1000, fee_bps=0, slippage_bps=0,
                          size_pct=100, stop_loss_pct=10)
rst = run_backtest(dfs, pd.Series([1.0] * 5), cfg_stop)
check("stop-loss triggers on the bar's LOW, not its close",
      rst["trades"][0]["exit_reason"] == "stop",
      f"reason={rst['trades'][0]['exit_reason']}")
check("stop fills at the stop price (90)", approx(rst["trades"][0]["exit_price"], 90.0),
      f"got {rst['trades'][0]['exit_price']}")

# Take profit at +10% on a bar that spikes to 115.
dft = bars([(100, 101, 99, 100), (100, 101, 99, 100), (100, 115, 99, 102),
            (102, 103, 101, 102), (102, 103, 101, 102)])
cfg_tp = BacktestConfig(initial_cash=1000, fee_bps=0, slippage_bps=0,
                        size_pct=100, take_profit_pct=10)
rtp = run_backtest(dft, pd.Series([1.0] * 5), cfg_tp)
check("take-profit triggers on the bar's HIGH", rtp["trades"][0]["exit_reason"] == "target")
check("target fills at 110", approx(rtp["trades"][0]["exit_price"], 110.0))

# When a bar could hit BOTH stop and target, the stop must win (pessimistic).
dfb = bars([(100, 101, 99, 100), (100, 101, 99, 100), (100, 120, 80, 100),
            (100, 101, 99, 100)])
cfg_both = BacktestConfig(initial_cash=1000, fee_bps=0, slippage_bps=0, size_pct=100,
                          stop_loss_pct=10, take_profit_pct=10)
rb = run_backtest(dfb, pd.Series([1.0] * 4), cfg_both)
check("ambiguous bar resolves pessimistically (stop before target)",
      rb["trades"][0]["exit_reason"] == "stop",
      f"reason={rb['trades'][0]['exit_reason']}")

# No re-entry immediately after a stop unless explicitly allowed.
long_after_stop = pd.Series([1.0] * 8)
dfr = bars([(100, 101, 99, 100)] * 2 + [(100, 101, 80, 90)] + [(90, 91, 89, 90)] * 5)
r_block = run_backtest(dfr, long_after_stop,
                       BacktestConfig(initial_cash=1000, fee_bps=0, slippage_bps=0,
                                      size_pct=100, stop_loss_pct=10))
r_allow = run_backtest(dfr, long_after_stop,
                       BacktestConfig(initial_cash=1000, fee_bps=0, slippage_bps=0,
                                      size_pct=100, stop_loss_pct=10,
                                      reenter_after_stop=True))
check("stop lockout prevents instant re-entry", r_block["stats"]["num_trades"] == 1,
      f"got {r_block['stats']['num_trades']}")
check("reenter_after_stop=True does re-enter", r_allow["stats"]["num_trades"] >= 2,
      f"got {r_allow['stats']['num_trades']}")

# max_bars_held
r_to = run_backtest(bars([(100, 101, 99, 100)] * 12), pd.Series([1.0] * 12),
                    BacktestConfig(initial_cash=1000, fee_bps=0, slippage_bps=0,
                                   size_pct=100, max_bars_held=3))
check("max_bars_held forces a timeout exit",
      any(t["exit_reason"] == "timeout" for t in r_to["trades"]))
check("timeout is a neutral exit, so re-entry is allowed",
      r_to["stats"]["num_trades"] >= 2, f"got {r_to['stats']['num_trades']}")

# Take-profit is also neutral: an always-long signal should cycle through targets.
r_cyc = run_backtest(bars([(100, 101, 99, 100), (100, 101, 99, 100), (100, 115, 99, 100),
                           (100, 101, 99, 100), (100, 115, 99, 100), (100, 101, 99, 100)]),
                     pd.Series([1.0] * 6),
                     BacktestConfig(initial_cash=1000, fee_bps=0, slippage_bps=0,
                                    size_pct=100, take_profit_pct=10))
check("take-profit allows re-entry (target is a neutral exit)",
      r_cyc["stats"]["num_trades"] >= 2, f"got {r_cyc['stats']['num_trades']}")


# ---- short selling ----
# Price falls 100 -> 80. A short entered at bar 1's open must make money.
dn = bars([(100, 101, 99, 100), (100, 101, 99, 98), (98, 99, 90, 92),
           (92, 93, 85, 86), (86, 87, 79, 80)])
r_short = run_backtest(dn, pd.Series([-1.0] * 5),
                       BacktestConfig(initial_cash=1000, fee_bps=0, slippage_bps=0,
                                      size_pct=100, allow_short=True))
tr = r_short["trades"][0]
check("short trade is recorded as short", tr["side"] == "short")
# entry at open[1]=100, exit at close[4]=80 -> +20% on 1000
check("short profits when price falls",
      approx(r_short["stats"]["final_equity"], 1000 * (1 + (100 - 80) / 100), 1e-9),
      f"got {r_short['stats']['final_equity']:.4f}")

# allow_short=False must silently clamp a -1 signal to flat.
r_noshort = run_backtest(dn, pd.Series([-1.0] * 5),
                         BacktestConfig(initial_cash=1000, fee_bps=0, slippage_bps=0,
                                        size_pct=100, allow_short=False))
check("allow_short=False ignores short signals",
      r_noshort["stats"]["num_trades"] == 0 and approx(r_noshort["stats"]["final_equity"], 1000.0))

# Short stop-loss fires on the bar's HIGH.
up = bars([(100, 101, 99, 100), (100, 101, 99, 100), (100, 120, 99, 110),
           (110, 111, 109, 110)])
r_sstop = run_backtest(up, pd.Series([-1.0] * 4),
                       BacktestConfig(initial_cash=1000, fee_bps=0, slippage_bps=0,
                                      size_pct=100, allow_short=True, stop_loss_pct=10))
check("short stop triggers on the bar's HIGH at 110",
      r_sstop["trades"][0]["exit_reason"] == "stop" and
      approx(r_sstop["trades"][0]["exit_price"], 110.0),
      f"{r_sstop['trades'][0]['exit_reason']} @ {r_sstop['trades'][0]['exit_price']}")


# ============================================================================
print("\n--- engine: metrics ---")
# ============================================================================

# Equity halves then recovers -> max drawdown must be exactly -50%.
dd_df = bars([(100, 100, 100, 100), (100, 100, 100, 100), (100, 100, 100, 100),
              (50, 50, 50, 50), (100, 100, 100, 100), (100, 100, 100, 100)])
rdd = run_backtest(dd_df, pd.Series([1.0] * 6),
                   BacktestConfig(initial_cash=1000, fee_bps=0, slippage_bps=0, size_pct=100))
check("max drawdown of a 50% dip = -50%", approx(rdd["stats"]["max_drawdown_pct"], -50.0, 1e-6),
      f"got {rdd['stats']['max_drawdown_pct']:.4f}")

# Buy & hold benchmark uses first close to last close.
check("buy&hold return uses close-to-close",
      approx(r["stats"]["buy_hold_return_pct"], 100 * (110 / 100 - 1), 1e-9),
      f"got {r['stats']['buy_hold_return_pct']}")

# Win rate arithmetic on a synthetic set of 4 trades: 3 up, 1 down
syn = dat.synthetic(600, "1h", seed=3)
rsyn = run_backtest(syn, strat.build_signal("rsi_reversion", syn),
                    BacktestConfig(initial_cash=10000, timeframe_seconds=3600))
st = rsyn["stats"]
wins = [t for t in rsyn["trades"] if t["pnl"] > 0]
check("win_rate matches the trade list",
      st["num_trades"] == 0 or approx(st["win_rate_pct"], 100 * len(wins) / st["num_trades"], 1e-9))
check("final_equity equals initial + sum of trade P&L",
      st["num_trades"] == 0 or approx(st["final_equity"],
                                      10000 + sum(t["pnl"] for t in rsyn["trades"]), 1e-6),
      f"{st['final_equity']:.2f} vs {10000 + sum(t['pnl'] for t in rsyn['trades']):.2f}")
check("time in market is a sane percentage", 0 <= st["time_in_market_pct"] <= 100)
check("max drawdown is never positive", st["max_drawdown_pct"] <= 0)


# ============================================================================
print("\n--- strategies ---")
# ============================================================================

big = dat.synthetic(3000, "1h", seed=11)
for key in strat.REGISTRY:
    try:
        sig = strat.build_signal(key, big)
        ok = (len(sig) == len(big)) and sig.isin([-1.0, 0.0, 1.0]).all() and not sig.isna().any()
        res = run_backtest(big, sig, BacktestConfig(initial_cash=10000, timeframe_seconds=3600),
                           ta.atr(big, 14))
        finite = np.isfinite(res["stats"]["final_equity"]) and res["stats"]["final_equity"] >= 0
        check(f"strategy '{key}' produces a valid signal and runs", ok and finite)
    except Exception as e:
        check(f"strategy '{key}' runs", False, f"{type(e).__name__}: {e}")

# Buy & hold strategy should closely track the benchmark (small gap = first-bar entry)
rbh = run_backtest(big, strat.build_signal("buy_hold", big),
                   BacktestConfig(initial_cash=10000, fee_bps=0, slippage_bps=0,
                                  timeframe_seconds=3600))
gap = abs(rbh["stats"]["total_return_pct"] - rbh["stats"]["buy_hold_return_pct"])
check("buy_hold strategy ~ matches buy&hold benchmark", gap < 5.0, f"gap {gap:.2f}pp")

# No-lookahead: feeding the engine only the first half must reproduce the same
# early trades. If a strategy peeked at the future, this breaks.
half = big.iloc[:1500].reset_index(drop=True)
r_full = run_backtest(big, strat.build_signal("ema_cross", big),
                      BacktestConfig(initial_cash=10000, timeframe_seconds=3600))
r_half = run_backtest(half, strat.build_signal("ema_cross", half),
                      BacktestConfig(initial_cash=10000, timeframe_seconds=3600))
n_cmp = min(len(r_full["trades"]), len(r_half["trades"])) - 1
same = all(approx(r_full["trades"][i]["entry_price"], r_half["trades"][i]["entry_price"], 1e-9)
           for i in range(max(0, n_cmp)))
check("no lookahead: past trades identical when future data is removed", same)


# ============================================================================
print("\n--- data utilities ---")
# ============================================================================

syn = dat.synthetic(500, "1h", seed=5)
check("synthetic data has valid OHLC relationships",
      bool(((syn["high"] >= syn["low"]) & (syn["high"] >= syn["open"]) &
            (syn["high"] >= syn["close"]) & (syn["low"] <= syn["open"]) &
            (syn["low"] <= syn["close"])).all()))
check("synthetic prices are positive", bool((syn["close"] > 0).all()))

rs = dat.resample(syn, 3600, 14400)
check("resample 1h -> 4h reduces bar count ~4x", abs(len(rs) - len(syn) / 4) <= 2)
check("resampled volume is conserved", approx(rs["volume"].sum(), syn["volume"].sum(), 1e-6))
check("resampled high is the max of its children", rs["high"].max() <= syn["high"].max() + 1e-9)

cleaned = dat._clean(syn, "1h")
check("_clean drops the still-forming candle", len(cleaned) <= len(syn))
check("_clean output is sorted by time", bool(cleaned["time"].is_monotonic_increasing))


# ============================================================================
print("\n--- paper trading ---")
# ============================================================================

import tempfile             # noqa: E402
import paper                # noqa: E402

paper.STATE_PATH = os.path.join(tempfile.mkdtemp(), "paper_test.json")
st = paper.reset(10_000.0)
FEE = paper.DEFAULT_FEE_BPS / 10_000.0

paper.buy(st, "BTC", 2000, 50_000, "oversold + uptrend", 5, "LONG")
check("buy deducts notional AND fee from cash",
      approx(st["cash"], 10_000 - 2000 - 2000 * FEE, 1e-9), f"cash {st['cash']}")
pos = st["positions"]["BTC"]
check("units = usd / price", approx(pos["units"], 2000 / 50_000, 1e-12))
check("cost basis = fill price", approx(pos["cost_basis"], 50_000, 1e-12))

# Averaging in at a higher price must raise the blended basis, and the basis
# must still reconcile to total dollars spent.
paper.buy(st, "BTC", 1000, 60_000, "adding on strength", 3, "LONG")
pos = st["positions"]["BTC"]
check("averaging in blends the cost basis",
      approx(pos["units"] * pos["cost_basis"], 3000, 1e-6),
      f"{pos['units'] * pos['cost_basis']}")
check("blended basis sits between the two fills", 50_000 < pos["cost_basis"] < 60_000)

# Sell half at a profit; realized P&L must net out the exit fee.
units_before = pos["units"]
tr = paper.sell(st, "BTC", 0.5, 70_000, "taking half off")
sold = units_before * 0.5
expected_pnl = sold * 70_000 - sold * pos["cost_basis"] - (sold * 70_000) * FEE
check("realized P&L nets out the exit fee", approx(tr["pnl"], expected_pnl, 1e-9),
      f"{tr['pnl']:.6f} vs {expected_pnl:.6f}")
check("partial sell keeps the position open", "BTC" in st["positions"])
check("partial sell is flagged", tr["partial"] is True)
check("remaining units halve", approx(st["positions"]["BTC"]["units"], units_before / 2, 1e-12))

# The accounting identity that proves nothing leaks:
#   equity == initial + realized + unrealized - entry_fees
m = paper.mark(st, {"BTC": 70_000})
check("portfolio identity holds exactly",
      approx(m["equity"], m["identity_check"], 1e-9),
      f"equity {m['equity']:.6f} vs identity {m['identity_check']:.6f}")
check("equity == cash + holdings", approx(m["equity"], m["cash"] + m["holdings_value"], 1e-9))
check("fee split adds up", approx(m["entry_fees"] + m["exit_fees"], m["total_fees"], 1e-12))

paper.sell(st, "BTC", 1.0, 70_000, "closing out")
check("full sell removes the position", "BTC" not in st["positions"])
m = paper.mark(st, {})
check("after closing everything, equity is all cash",
      approx(m["equity"], m["cash"], 1e-12) and approx(m["holdings_value"], 0.0, 1e-12))
check("identity still holds with no positions",
      approx(m["equity"], m["identity_check"], 1e-9))

# Guard rails
try:
    paper.buy(st, "ETH", 100, 3000, "", 3); check("buy requires a written reason", False)
except paper.PaperError: check("buy requires a written reason", True)
try:
    paper.buy(st, "ETH", 10 ** 9, 3000, "moon", 3); check("buy rejects overspending", False)
except paper.PaperError: check("buy rejects overspending", True)
try:
    paper.sell(st, "DOGE", 1.0, 0.1, "nope"); check("sell rejects unknown position", False)
except paper.PaperError: check("sell rejects unknown position", True)
check("confidence is clamped to 1-5",
      paper.buy(st, "ETH", 100, 3000, "clamp test", 99)["confidence"] == 5)

# The stop travels with the position — a forgotten stop is not a stop.
st4 = paper.reset(10_000.0)
paper.buy(st4, "BTC", 1000, 100.0, "stop tracking test", 3, "LONG",
          stop_price=90.0, target_price=120.0)
check("stop price is stored on the position", st4["positions"]["BTC"]["stop_price"] == 90.0)
check("target price is stored on the position", st4["positions"]["BTC"]["target_price"] == 120.0)

m4 = paper.mark(st4, {"BTC": 100.0})["positions"][0]
check("distance to stop is reported", approx(m4["stop_distance_pct"], 10.0, 1e-9),
      f"{m4['stop_distance_pct']}")
check("an untouched stop is not flagged", m4["stop_breached"] is False)

m4 = paper.mark(st4, {"BTC": 89.0})["positions"][0]
check("a breached stop is flagged", m4["stop_breached"] is True)
check("breached stop reports negative distance", m4["stop_distance_pct"] < 0)

paper.buy(st4, "ETH", 500, 50.0, "no stop set", 2)
m5 = [r for r in paper.mark(st4, {"BTC": 100.0, "ETH": 50.0})["positions"] if r["symbol"] == "ETH"][0]
check("positions without a stop degrade gracefully",
      m5["stop_price"] is None and m5["stop_distance_pct"] is None and m5["stop_breached"] is False)

# Persistence round trip
paper.save(st)
reloaded = paper.load()
check("state survives save/load",
      approx(reloaded["cash"], st["cash"], 1e-12) and
      len(reloaded["trades"]) == len(st["trades"]))

# Scorecard: build a portfolio where high conviction genuinely did better.
st2 = paper.reset(100_000.0)
paper.STATE_PATH = paper.STATE_PATH  # same temp file
for i in range(6):
    paper.buy(st2, "BTC", 1000, 100, "high conviction setup", 5)
    paper.sell(st2, "BTC", 1.0, 120, "target hit")          # +20%
for i in range(6):
    paper.buy(st2, "ETH", 1000, 100, "low conviction punt", 1)
    paper.sell(st2, "ETH", 1.0, 95, "cut it")               # -5%
sc = paper.scorecard(st2)
check("scorecard counts every closed trade", sc["trades"] == 12)
check("conviction edge is positive when conviction paid off",
      sc["conviction_edge"] > 20, f"edge {sc['conviction_edge']}")
check("win rate matches 6 of 12", approx(sc["win_rate"], 50.0, 1e-9))
check("by_confidence buckets populated", 5 in sc["by_confidence"] and 1 in sc["by_confidence"])

# And the inverse: overconfidence must be detected and called out.
st3 = paper.reset(100_000.0)
for i in range(5):
    paper.buy(st3, "BTC", 1000, 100, "sure thing", 5)
    paper.sell(st3, "BTC", 1.0, 85, "wrong again")          # -15%
for i in range(5):
    paper.buy(st3, "ETH", 1000, 100, "meh", 1)
    paper.sell(st3, "ETH", 1.0, 110, "worked out")          # +10%
sc3 = paper.scorecard(st3)
check("negative conviction edge is detected", sc3["conviction_edge"] < -20,
      f"edge {sc3['conviction_edge']}")
check("scorecard warns about anti-correlated confidence",
      any("anti-correlated" in n for n in sc3["notes"]))

check("empty scorecard is handled", paper.scorecard(paper.reset(1000))["trades"] == 0)


# ============================================================================
print("\n--- trade planner (the four blanks) ---")
# ============================================================================

os.environ["QUANTLAB_DEMO"] = "1"
paper.STATE_PATH = os.path.join(tempfile.mkdtemp(), "plan_test.json")
paper.reset(10_000.0)

import server                # noqa: E402

plan = server.do_plan({"symbol": "BTC", "timeframe": "4h", "strategy": "trend_filtered_dip",
                       "risk_profile": {"risk_pct": 2.0, "stop_atr_mult": 2.0,
                                        "target_r": 2.0, "max_position_pct": 100.0}})
P, entry = plan["plan"], plan["entry_price"]

check("planner returns all four blanks",
      all(P.get(k) is not None for k in
          ("size_usd", "stop_price", "target_price", "exit_rule")))
check("stop sits below entry", P["stop_price"] < entry)
check("target sits above entry", P["target_price"] > entry)

# Stop distance must be exactly stop_atr_mult x ATR.
check("stop distance == 2 x ATR",
      approx(entry - P["stop_price"], 2 * plan["atr"], 1e-9),
      f"{entry - P['stop_price']:.4f} vs {2 * plan['atr']:.4f}")

# THE core sizing identity: dollars actually at risk == the % you chose.
check("dollars at risk == 2% of the account",
      approx(P["risk_usd"], 200.0, 1e-6), f"risk_usd {P['risk_usd']:.4f}")
check("risk_pct_of_account reports 2%", approx(P["risk_pct_of_account"], 2.0, 1e-9))

# size = risk / (stop distance as a fraction of entry)
expected_size = 200.0 / ((entry - P["stop_price"]) / entry)
check("position size = risk / stop-distance-fraction",
      approx(P["size_usd"], expected_size, 1e-6),
      f"{P['size_usd']:.4f} vs {expected_size:.4f}")
check("units = size / entry", approx(P["units"], P["size_usd"] / entry, 1e-12))

# Reward:risk must be exactly target_r, and breakeven win rate consistent.
reward = P["size_usd"] * (P["target_price"] - entry) / entry
check("reward is exactly 2x the risk", approx(reward, 2 * P["risk_usd"], 1e-6),
      f"reward {reward:.2f} vs risk {P['risk_usd']:.2f}")
check("breakeven win rate = 100/(1+R)", approx(P["breakeven_win_rate"], 100 / 3, 1e-9))

# A WIDER stop must produce a SMALLER position for the same risk. This inversion
# is the single most important idea in position sizing.
wide = server.do_plan({"symbol": "BTC", "timeframe": "4h", "strategy": "trend_filtered_dip",
                       "risk_profile": {"risk_pct": 2.0, "stop_atr_mult": 4.0,
                                        "target_r": 2.0, "max_position_pct": 100.0}})
check("doubling the stop distance halves the position size",
      approx(wide["plan"]["size_usd"], P["size_usd"] / 2, 1e-4),
      f"{wide['plan']['size_usd']:.2f} vs {P['size_usd'] / 2:.2f}")
check("wider stop keeps dollars-at-risk identical",
      approx(wide["plan"]["risk_usd"], P["risk_usd"], 1e-6))

# Halving risk% must halve the position.
half = server.do_plan({"symbol": "BTC", "timeframe": "4h", "strategy": "trend_filtered_dip",
                       "risk_profile": {"risk_pct": 1.0, "stop_atr_mult": 2.0,
                                        "target_r": 2.0, "max_position_pct": 100.0}})
check("halving risk% halves the position size",
      approx(half["plan"]["size_usd"], P["size_usd"] / 2, 1e-4))

# The max-position cap must bind and be reported honestly.
capped = server.do_plan({"symbol": "BTC", "timeframe": "4h", "strategy": "trend_filtered_dip",
                         "risk_profile": {"risk_pct": 50.0, "stop_atr_mult": 2.0,
                                          "target_r": 2.0, "max_position_pct": 25.0}})
check("max-position cap limits size to 25% of account",
      approx(capped["plan"]["size_usd"], 2500.0, 1e-6), f"{capped['plan']['size_usd']:.2f}")
check("cap is disclosed to the user", "max-position" in (capped["plan"]["capped_by"] or ""),
      f"capped_by={capped['plan']['capped_by']}")
check("capped trade risks LESS than requested, never more",
      capped["plan"]["risk_usd"] < 5000.0)

check("survivable-losses count is consistent",
      P["max_consecutive_losses_survivable"] == int(10_000 / P["risk_usd"]))
check("every blank has a plain-English sentence", len(plan["plain"]) >= 5)
check("verdict lists reasons or warnings",
      len(plan["verdict"]["reasons"]) + len(plan["verdict"]["warnings"]) > 0)
check("exit rule text is present", len(P["exit_rule"]) > 20)

# Risk profile persists to disk.
server.do_set_risk({"risk_pct": 1.5, "stop_atr_mult": 3.0})
rp = paper.load()["risk_profile"]
check("risk profile persists", approx(rp["risk_pct"], 1.5) and approx(rp["stop_atr_mult"], 3.0))
server.do_set_risk({"risk_pct": 999})
check("risk_pct is clamped to a sane maximum", paper.load()["risk_profile"]["risk_pct"] <= 100.0)

# A planned trade must execute into the portfolio at the planned size.
paper.reset(10_000.0)
plan2 = server.do_plan({"symbol": "ETH", "timeframe": "4h", "strategy": "trend_filtered_dip",
                        "risk_profile": {"risk_pct": 2.0, "stop_atr_mult": 2.0,
                                         "target_r": 2.0, "max_position_pct": 25.0}})
res = server.do_paper_buy({"symbol": "ETH", "usd": plan2["plan"]["size_usd"],
                           "reason": "planner integration test", "confidence": 3,
                           "strategy": "trend_filtered_dip", "timeframe": "4h"})
pos = res["portfolio"]["positions"][0]
check("planned trade executes at the planned size",
      approx(pos["units"] * pos["cost_basis"], plan2["plan"]["size_usd"], 1e-6))
check("portfolio identity still holds after a planned trade",
      approx(res["portfolio"]["equity"], res["portfolio"]["identity_check"], 1e-9))

os.environ.pop("QUANTLAB_DEMO", None)


# ============================================================================
print("\n--- spoken login briefing ---")
# ============================================================================

import brief                 # noqa: E402
from datetime import datetime as _dt  # noqa: E402

check("money is spoken without symbols",
      "$" not in brief.say_money(64641.32) and "dollars" in brief.say_money(64641.32),
      brief.say_money(64641.32))
check("large numbers are rounded for speech", brief.say_money(64641.32) == "64,600 dollars",
      brief.say_money(64641.32))
check("millions are spoken as millions", "million" in brief.say_money(2_400_000))
check("sub-dollar prices keep precision", "0.0031" in brief.say_money(0.0031))
check("percentages avoid the percent symbol",
      "%" not in brief.say_pct(-4.2) and brief.say_pct(-4.2) == "4 percent down",
      brief.say_pct(-4.2))
check("time-of-day greeting adapts",
      (brief.greeting_for(8), brief.greeting_for(14), brief.greeting_for(21))
      == ("Good morning", "Good afternoon", "Good evening"))

paper.STATE_PATH = os.path.join(tempfile.mkdtemp(), "brief_test.json")

# --- empty portfolio: the brief must be SHORT ---
empty = paper.reset(10_000.0)
sp, wr = brief.compose(empty, {}, _dt(2026, 8, 6, 8, 0), name="Eyoel")
check("empty-portfolio brief is short", len(sp.split()) < 45, f"{len(sp.split())} words")
check("greets by name", "Eyoel" in sp)
check("says the ledger is empty", "no open positions" in sp.lower())
check("counts reps toward the target", f"of {brief.TARGET_TRADES}" in sp, sp)
check("nudges the outstanding predictions", "predictions" in sp.lower())
check("spoken text carries no symbols",
      not any(c in sp for c in "$%|#*_"), sp)
check("written brief is markdown with sections",
      wr.startswith("# Briefing") and "## Portfolio" in wr and "## Today" in wr)

# --- a breached stop must LEAD, and must be blunt ---
st = paper.reset(10_000.0)
paper.buy(st, "SOL", 2000, 100.0, "guided plan", 4, "LONG", stop_price=90.0, target_price=120.0)
sp_b, wr_b = brief.compose(st, {"SOL": 85.0}, _dt(2026, 8, 6, 8, 0))
first = sp_b.split(".")[1].strip().lower()
check("breached stop is the first thing said", "sol" in first and "stop" in first, first)
check("breach language is direct about acting",
      "your own rule says sell" in sp_b.lower(), sp_b)
check("breach appears in the written brief", "Stop breached" in wr_b)

# --- near a stop: mention it, but don't manufacture drama ---
sp_n, _ = brief.compose(st, {"SOL": 92.0}, _dt(2026, 8, 6, 8, 0))
check("a stop within 3% is flagged", "from its stop" in sp_n, sp_n)
check("near-stop brief still says what to do", "nothing to do" in sp_n.lower(), sp_n)

# --- comfortable position: no stop noise at all ---
sp_ok, _ = brief.compose(st, {"SOL": 130.0}, _dt(2026, 8, 6, 8, 0))
check("a comfortable position produces no stop warning", "stop" not in sp_ok.lower(), sp_ok)
check("comfortable brief stays short", len(sp_ok.split()) < 45, f"{len(sp_ok.split())} words")

# --- past the target: tell him to read the scorecard ---
st2 = paper.reset(10_000.0)
for i in range(brief.TARGET_TRADES):
    paper.buy(st2, "BTC", 100, 100.0, "rep", 3)
    paper.sell(st2, "BTC", 1.0, 105.0, "rep")
sp_done, _ = brief.compose(st2, {}, _dt(2026, 8, 6, 8, 0))
check("hitting the trade target changes the message",
      "conviction edge" in sp_done.lower(), sp_done)

# --- degradation: no prices available ---
sp_off, wr_off = brief.compose(st, {"SOL": None}, _dt(2026, 8, 6, 8, 0))
check("missing prices don't crash the brief", isinstance(sp_off, str) and len(sp_off) > 10)
check("missing prices are disclosed in writing", "Couldn't fetch" in wr_off, wr_off[-200:])

# --- a position with no stop is noted, not nagged about ---
st3 = paper.reset(10_000.0)
paper.buy(st3, "ETH", 1000, 50.0, "manual buy", 2)
_, wr_ns = brief.compose(st3, {"ETH": 55.0}, _dt(2026, 8, 6, 8, 0))
check("a position without a stop is flagged once, in writing",
      "No stop recorded" in wr_ns and wr_ns.count("No stop recorded") == 1)

check("speak() is a no-op off macOS", brief.speak("test") is None)


# ============================================================================
print("\n--- ranking formula (shortlist == backtest) ---")
# ============================================================================

import rank                 # noqa: E402

rdf = dat.synthetic(1200, "4h", seed=21)
comp = rank.quality_components(rdf)

check("all six factors are produced",
      set(comp.columns) == set(rank.DEFAULT_WEIGHTS), str(list(comp.columns)))
check("every factor is bounded 0..1",
      bool(((comp >= 0) & (comp <= 1)).all().all()))
check("no NaN leaks out of the factors", not comp.isna().any().any())
check("weights sum to 1", approx(sum(rank.DEFAULT_WEIGHTS.values()), 1.0, 1e-9))

sc = rank.quality_score(rdf)
check("score is bounded 0..100", bool(sc.between(0, 100).all()), f"{sc.min()}..{sc.max()}")
check("score has one value per bar", len(sc) == len(rdf))
check("score actually varies", sc.std() > 1.0, f"std {sc.std():.2f}")

# The score must be the exact weighted sum of its parts — no hidden terms.
manual = sum(comp[k] * w for k, w in rank.DEFAULT_WEIGHTS.items()) * 100.0
check("score == weighted sum of factors, exactly",
      np.allclose(sc.to_numpy(), manual.to_numpy(), atol=1e-9))

# Causality: the score for early bars cannot change when later data is added.
half_df = rdf.iloc[:600].reset_index(drop=True)
check("score is causal — past values unchanged by future data",
      np.allclose(rank.quality_score(half_df).to_numpy()[210:],
                  sc.to_numpy()[210:600], atol=1e-9))

# Breakdown must reconcile with the headline score.
bd = rank.score_breakdown(rdf)
check("breakdown score matches quality_score", approx(bd["score"], float(sc.iloc[-1]), 1e-9))
check("factor points sum to the score",
      approx(sum(f["points"] for f in bd["factors"]), bd["score"], 1e-9),
      f"{sum(f['points'] for f in bd['factors']):.4f} vs {bd['score']:.4f}")
check("max points sum to 100", approx(sum(f["max_points"] for f in bd["factors"]), 100.0, 1e-9))
check("every factor is explained to the user",
      all(f["help"] and f["label"] for f in bd["factors"]))
check("factors are ordered by contribution",
      all(bd["factors"][i]["points"] >= bd["factors"][i + 1]["points"]
          for i in range(len(bd["factors"]) - 1)))

# Custom weights must actually change the answer, and still normalise.
only_trend = rank.quality_score(rdf, {"trend": 1.0, "momentum": 0, "macd": 0,
                                      "rsi_zone": 0, "strength": 0, "volume": 0})
check("weighting one factor at 100% yields a binary 0/100 score",
      set(np.round(only_trend.unique(), 6)).issubset({0.0, 100.0}),
      str(only_trend.unique()[:5]))
check("custom weights change the score", not np.allclose(only_trend, sc))

# THE KEY GUARANTEE: the strategy and the shortlist use the same maths.
strat_sig = strat.build_signal("quality_score", rdf, {"entry_score": 65, "exit_score": 45})
recomputed = rank.quality_score(rdf)
expected_entries = recomputed >= 65
check("the backtested strategy is driven by the same score function",
      bool((strat_sig[expected_entries & (recomputed.shift(1) < 65)] == 1.0).all()
           if (expected_entries & (recomputed.shift(1) < 65)).any() else True))
check("quality_score strategy is registered", "quality_score" in strat.REGISTRY)
check("quality_score strategy runs end to end",
      run_backtest(rdf, strat_sig, BacktestConfig(initial_cash=10000,
                   timeframe_seconds=14400), ta.atr(rdf, 14))["stats"]["num_trades"] >= 0)
check("strategy exposes weights as tunable params",
      all(any(p["name"] == f"w_{k}" for p in strat.REGISTRY["quality_score"]["params"])
          for k in rank.DEFAULT_WEIGHTS))

# Higher entry thresholds must never produce more time in market.
sig_low = strat.build_signal("quality_score", rdf, {"entry_score": 40, "exit_score": 20})
sig_high = strat.build_signal("quality_score", rdf, {"entry_score": 85, "exit_score": 70})
check("a stricter threshold means less time invested",
      sig_high.mean() <= sig_low.mean(), f"{sig_high.mean():.3f} vs {sig_low.mean():.3f}")

# Verdict bands
check("verdict bands are ordered", [rank.verdict(s)[0] for s in (90, 70, 50, 30, 10)]
      == ["strong", "decent", "mixed", "weak", "avoid"])
check("every band has an explanation",
      all(len(rank.verdict(s)[1]) > 30 for s in (90, 70, 50, 30, 10)))

# Relative strength is cross-sectional and excluded from the score.
other = dat.synthetic(1200, "4h", seed=22)
rs = rank.relative_strength(rdf, other, 180)
check("relative strength computes", rs is not None and np.isfinite(rs))
check("relative strength vs itself is zero", approx(rank.relative_strength(rdf, rdf, 180), 0.0, 1e-9))
check("relative strength is absent from the factor set", "rel_strength" not in comp.columns)
check("short history returns None rather than a wrong number",
      rank.relative_strength(rdf.iloc[:50], other.iloc[:50], 180) is None)


# ============================================================================
print("\n--- news feeds and risk scoring ---")
# ============================================================================

import news                 # noqa: E402

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel>
  <title>Test Feed</title>
  <item><title>Solana DEX volume hits record high</title>
    <link>https://example.com/a</link>
    <description>&lt;p&gt;Some &lt;b&gt;HTML&lt;/b&gt; summary here.&lt;/p&gt;</description>
    <pubDate>Mon, 04 Aug 2026 12:00:00 +0000</pubDate></item>
  <item><title>Ethereum upgrade delayed again</title>
    <link>https://example.com/b</link>
    <pubDate>Mon, 04 Aug 2026 09:30:00 GMT</pubDate></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
  <entry><title>Reddit style post about Solana</title>
    <link href="https://reddit.example/x"/>
    <updated>2026-08-04T11:00:00Z</updated>
    <content type="html">body text</content></entry>
</feed>"""

rss_items = news.parse_feed(RSS, "test", "Test Feed", "news")
check("RSS 2.0 parses", len(rss_items) == 2, f"got {len(rss_items)}")
check("RSS title extracted", rss_items[0]["title"] == "Solana DEX volume hits record high")
check("RSS link extracted", rss_items[0]["link"] == "https://example.com/a")
check("HTML is stripped from summaries",
      "<" not in rss_items[0]["summary"] and "HTML" in rss_items[0]["summary"],
      rss_items[0]["summary"])
check("RFC-822 dates parse", rss_items[0]["published"] > 1_700_000_000)
check("GMT-suffixed dates parse", rss_items[1]["published"] > 1_700_000_000)

atom_items = news.parse_feed(ATOM, "r_test", "Reddit", "social")
check("Atom feeds parse", len(atom_items) == 1)
check("Atom link comes from href", atom_items[0]["link"] == "https://reddit.example/x")
check("ISO-8601 dates parse", atom_items[0]["published"] > 1_700_000_000)
check("source metadata attached",
      atom_items[0]["source_name"] == "Reddit" and atom_items[0]["category"] == "social")

check("malformed dates degrade to 0 rather than crashing", news._parse_date("not a date") == 0)
check("empty date is handled", news._parse_date(None) == 0)
try:
    news.parse_feed(b"<html>not a feed</html>", "x", "X", "news")
    check("non-feed XML does not crash the parser", True)
except Exception as e:
    check("non-feed XML does not crash the parser", False, str(e))

# Narrative counting
now_ts = int(time.time()) if 'time' in dir() else __import__('time').time()
import time as _t  # noqa: E402
now_ts = int(_t.time())
sample = [
    {"title": "Solana network upgrade ships", "summary": "", "published": now_ts - 3600,
     "source_name": "CoinDesk", "link": "a"},
    {"title": "Solana DEX volume climbs", "summary": "", "published": now_ts - 7200,
     "source_name": "Decrypt", "link": "b"},
    {"title": "Solana validators vote", "summary": "", "published": now_ts - 10800,
     "source_name": "The Block", "link": "c"},
    {"title": "Bitcoin holds steady", "summary": "", "published": now_ts - 3600,
     "source_name": "CoinDesk", "link": "d"},
]
narr = news.narratives(sample)
terms = [r["term"] for r in narr]
check("repeated names surface as narratives", "Solana" in terms, str(terms))
check("multi-outlet coverage ranks first", narr[0]["term"] == "Solana", str(terms))
check("outlet diversity is counted", narr[0]["source_count"] == 3, str(narr[0]["source_count"]))
check("single-mention noise is filtered out", "Bitcoin" not in terms or
      next(r for r in narr if r["term"] == "Bitcoin")["mentions"] >= 2)
check("stopwords are excluded", not any(t.lower() in news._STOP for t in terms), str(terms))
check("example headlines are attached", len(narr[0]["headlines"]) > 0)

# Risk scoring on new pools — the numbers that matter
lethal = {"liquidity_usd": 3000, "volume_24h": 90000, "age_hours": 0.3,
          "buys_24h": 500, "sells_24h": 50, "change_24h": 900}
score_l, flags_l = news._risk_flags(lethal)
check("a minutes-old, illiquid, pumping pool scores extreme", score_l >= 8, f"score {score_l}")
check("illiquidity is called out", any("Liquidity" in f for f in flags_l))
check("age is called out", any("minutes old" in f for f in flags_l))
check("wash-trading pattern is called out", any("wash trading" in f for f in flags_l))
check("one-sided flow is called out", any("one-sided" in f for f in flags_l))

healthy = {"liquidity_usd": 400_000, "volume_24h": 200_000, "age_hours": 90,
           "buys_24h": 500, "sells_24h": 480, "change_24h": 5}
score_h, flags_h = news._risk_flags(healthy)
check("an established, liquid pool scores far lower", score_h == 0, f"score {score_h} {flags_h}")
check("risk score is monotonic in badness", score_l > score_h)

mid = {"liquidity_usd": 30_000, "volume_24h": 40_000, "age_hours": 5,
       "buys_24h": 100, "sells_24h": 90, "change_24h": 20}
check("thin-but-not-dead liquidity lands in between",
      score_h < news._risk_flags(mid)[0] < score_l)

check("missing fields never crash the scorer",
      isinstance(news._risk_flags({})[0], int))

# Base rates must be present, factual, and sourced.
check("base rates ship with the feed", len(news.BASE_RATES["facts"]) >= 4)
check("every base-rate claim has a source link",
      len(news.BASE_RATES["sources"]) >= 3 and
      all(s["url"].startswith("http") for s in news.BASE_RATES["sources"]))

# Demo fixtures keep the UI working offline.
os.environ["QUANTLAB_DEMO"] = "1"
d_news = news.fetch_news()
check("demo news fixture works offline", len(d_news["items"]) > 0 and d_news["demo"])
d_pools = news.fetch_new_pools("solana")
check("demo pools fixture works offline", len(d_pools["pools"]) > 0)
check("demo pools carry risk flags", all("risk_score" in p for p in d_pools["pools"]))
check("demo pools include base rates", "facts" in d_pools["base_rates"])
check("demo trending fixture works offline", len(news.fetch_trending()["coins"]) > 0)
os.environ.pop("QUANTLAB_DEMO", None)

# Cache behaviour
news._CACHE.clear()
calls = {"n": 0}


def _counted():
    calls["n"] += 1
    return "value"


news._cached("k", 60, _counted)
news._cached("k", 60, _counted)
check("cache prevents repeat fetches within TTL", calls["n"] == 1, f"{calls['n']} calls")
news._CACHE["k"] = (0, "stale")
news._cached("k", 60, _counted)
check("cache refetches once expired", calls["n"] == 2, f"{calls['n']} calls")


# ============================================================================
print("\n--- demo data stability ---")
# ============================================================================

# Demo prices must be identical across processes, or paper positions would jump
# in value after every restart. (Python randomizes hash() per process.)
os.environ["QUANTLAB_DEMO"] = "1"
import importlib             # noqa: E402
p1 = dat.get_candles("BTC", "1h", 7)["close"].iloc[-1]
importlib.reload(dat)
os.environ["QUANTLAB_DEMO"] = "1"
p2 = dat.get_candles("BTC", "1h", 7)["close"].iloc[-1]
check("demo prices are reproducible across reloads", approx(p1, p2, 1e-12), f"{p1} vs {p2}")
check("different coins get different demo prices",
      not approx(dat.get_candles("ETH", "1h", 7)["close"].iloc[-1], p1, 1e-6))
os.environ.pop("QUANTLAB_DEMO", None)


# ============================================================================
print(f"\n{'='*46}\n  {PASS} passed, {FAIL} failed\n{'='*46}\n")
sys.exit(1 if FAIL else 0)
