"""
server.py — the API + static file server.

Deliberately built on Python's standard-library HTTP server. No Flask, no
FastAPI, no uvicorn, no node_modules. `pip install pandas numpy` is the entire
dependency list, which means this thing still runs in three years when every
framework has had four breaking releases.
"""

from __future__ import annotations

import json
import math
import os
import re
import traceback
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from itertools import product
from urllib.parse import urlparse, parse_qs

import numpy as np
import pandas as pd

import data as dat
import indicators as ta
import news
import paper
import rank
import strategies as strat
from engine import BacktestConfig, run_backtest, buy_and_hold_curve

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


# ----------------------------------------------------------------------------
# JSON helpers
# ----------------------------------------------------------------------------

def clean(obj):
    """Make numpy/pandas values JSON-safe. NaN and inf become null."""
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return clean(obj.tolist())
    if isinstance(obj, pd.Series):
        return clean(obj.tolist())
    return obj


def fmt_usd(v: float) -> str:
    return f"${v:,.0f}"


def series_points(times, values):
    """Chart-ready [{time, value}] with nulls stripped."""
    out = []
    for t, v in zip(times, values):
        f = float(v) if v is not None else float("nan")
        if not (math.isnan(f) or math.isinf(f)):
            out.append({"time": int(t), "value": f})
    return out


# ----------------------------------------------------------------------------
# Core operations
# ----------------------------------------------------------------------------

def load(symbol: str, tf: str, days: int, refresh: bool = False) -> pd.DataFrame:
    df = dat.get_candles(symbol, tf, days, use_cache=not refresh)
    # Strategies using a 200-period trend filter need 200 bars of warm-up before
    # they produce a single signal. A coin listed three months ago simply cannot
    # be backtested on a 200-EMA, and pretending otherwise would give you a
    # confident-looking result computed from almost no data.
    if len(df) < 250:
        raise dat.DataError(
            f"Only {len(df)} candles available for {symbol} on {tf}. "
            f"Strategies here need ~250 minimum (the 200-period trend filter alone "
            f"burns 200 bars warming up). Fixes: use a shorter timeframe (1h instead "
            f"of 4h gives 4x the bars), pick a longer date range, or accept that this "
            f"coin is too new to backtest. A result from 80 candles would be noise "
            f"dressed up as an answer.")
    return df


def cfg_from(body: dict, tf: str) -> BacktestConfig:
    c = body.get("config", {}) or {}
    return BacktestConfig(
        initial_cash=float(c.get("initial_cash", 10_000)),
        fee_bps=float(c.get("fee_bps", 10)),
        slippage_bps=float(c.get("slippage_bps", 5)),
        size_pct=float(c.get("size_pct", 100)),
        allow_short=bool(c.get("allow_short", False)),
        stop_loss_pct=float(c.get("stop_loss_pct", 0)),
        take_profit_pct=float(c.get("take_profit_pct", 0)),
        trailing_stop_pct=float(c.get("trailing_stop_pct", 0)),
        atr_stop_mult=float(c.get("atr_stop_mult", 0)),
        max_bars_held=int(c.get("max_bars_held", 0)),
        reenter_after_stop=bool(c.get("reenter_after_stop", False)),
        timeframe_seconds=dat.TIMEFRAMES[tf],
    )


def do_backtest(body: dict) -> dict:
    symbol = body.get("symbol", "BTC").upper()
    tf = body.get("timeframe", "1h")
    days = int(body.get("days", 365))
    key = body.get("strategy", "rsi_reversion")
    params = body.get("params", {}) or {}

    df = load(symbol, tf, days, bool(body.get("refresh")))
    cfg = cfg_from(body, tf)
    signal = strat.build_signal(key, df, params)
    atr_s = ta.atr(df, 14)
    res = run_backtest(df, signal, cfg, atr_series=atr_s)

    times = df["time"].tolist()
    close = df["close"]
    bundle_params = {
        "ema_fast": int(params.get("fast", params.get("ema_fast", 20))),
        "ema_slow": int(params.get("slow", params.get("ema_slow", 50))),
        "ema_trend": int(params.get("trend_len", 200)),
        "rsi": int(params.get("rsi_len", 14)),
    }
    ind = ta.compute_bundle(df, bundle_params)

    return clean({
        "symbol": symbol, "timeframe": tf, "days": days, "strategy": key,
        "demo": os.environ.get("QUANTLAB_DEMO") == "1",
        "strategy_label": strat.REGISTRY[key]["label"],
        "params": {**strat.defaults(key), **params},
        "candles": [
            {"time": int(t), "open": float(o), "high": float(h), "low": float(l), "close": float(c)}
            for t, o, h, l, c in zip(times, df["open"], df["high"], df["low"], close)
        ],
        "volume": [{"time": int(t), "value": float(v),
                    "color": "rgba(38,166,154,.35)" if c >= o else "rgba(239,83,80,.35)"}
                   for t, v, o, c in zip(times, df["volume"], df["open"], close)],
        "overlays": {
            "ema_fast": series_points(times, ind["ema_fast"]),
            "ema_slow": series_points(times, ind["ema_slow"]),
            "ema_trend": series_points(times, ind["ema_trend"]),
            "bb_upper": series_points(times, ind["bb_upper"]),
            "bb_lower": series_points(times, ind["bb_lower"]),
            "vwap": series_points(times, ind["vwap"]),
        },
        "panels": {
            "rsi": series_points(times, ind["rsi"]),
            "macd": series_points(times, ind["macd"]),
            "macd_signal": series_points(times, ind["macd_signal"]),
            "macd_hist": series_points(times, ind["macd_hist"]),
            "adx": series_points(times, ind["adx"]),
            "atr_pct": series_points(times, ind["atr_pct"]),
            "vol_z": series_points(times, ind["vol_z"]),
        },
        "equity": series_points(res["times"], res["equity"]),
        "buy_hold": series_points(times, buy_and_hold_curve(df, cfg.initial_cash)),
        "trades": res["trades"],
        "markers": res["markers"],
        "stats": res["stats"],
        "latest": {
            "price": float(close.iloc[-1]),
            "rsi": float(ind["rsi"].iloc[-1]) if pd.notna(ind["rsi"].iloc[-1]) else None,
            "adx": float(ind["adx"].iloc[-1]) if pd.notna(ind["adx"].iloc[-1]) else None,
            "atr_pct": float(ind["atr_pct"].iloc[-1]) if pd.notna(ind["atr_pct"].iloc[-1]) else None,
            "signal_now": float(signal.iloc[-1]),
            "trend_up": bool(close.iloc[-1] > ind["ema_trend"].iloc[-1]) if pd.notna(ind["ema_trend"].iloc[-1]) else None,
        },
    })


def do_optimize(body: dict) -> dict:
    """
    Grid-search parameters, but split the data in half first.

    Optimize on the first 70% (in-sample), then report how the SAME parameters
    did on the untouched last 30% (out-of-sample). If a parameter set looks
    brilliant in-sample and mediocre out-of-sample, you found noise, not edge.
    That gap is the most honest number in this entire application.
    """
    symbol = body.get("symbol", "BTC").upper()
    tf = body.get("timeframe", "1h")
    days = int(body.get("days", 365))
    key = body.get("strategy", "rsi_reversion")
    sweep = body.get("sweep", {}) or {}
    metric = body.get("metric", "total_return_pct")
    max_combos = int(body.get("max_combos", 400))

    df = load(symbol, tf, days)
    cfg = cfg_from(body, tf)
    atr_s = ta.atr(df, 14)

    split = int(len(df) * 0.7)
    is_df, oos_df = df.iloc[:split].reset_index(drop=True), df.iloc[split:].reset_index(drop=True)
    is_atr, oos_atr = atr_s.iloc[:split].reset_index(drop=True), atr_s.iloc[split:].reset_index(drop=True)

    names = list(sweep.keys())
    grids = [sweep[n] for n in names]
    combos = list(product(*grids))[:max_combos] if names else [()]

    rows = []
    for combo in combos:
        p = dict(zip(names, combo))
        merged = {**(body.get("params") or {}), **p}
        try:
            is_res = run_backtest(is_df, strat.build_signal(key, is_df, merged), cfg, is_atr)
            oos_res = run_backtest(oos_df, strat.build_signal(key, oos_df, merged), cfg, oos_atr)
        except Exception:
            continue
        rows.append({
            "params": p,
            "in_sample": {k: is_res["stats"].get(k) for k in
                          ("total_return_pct", "sharpe", "max_drawdown_pct", "win_rate_pct",
                           "num_trades", "profit_factor")},
            "out_sample": {k: oos_res["stats"].get(k) for k in
                           ("total_return_pct", "sharpe", "max_drawdown_pct", "win_rate_pct",
                            "num_trades", "profit_factor")},
        })

    rows.sort(key=lambda r: (r["in_sample"].get(metric) or -9e9), reverse=True)

    # Overfitting check: correlation between in-sample and out-of-sample rank.
    overfit_note = "not enough results to judge"
    if len(rows) >= 5:
        a = np.array([r["in_sample"].get(metric) or 0.0 for r in rows], float)
        b = np.array([r["out_sample"].get(metric) or 0.0 for r in rows], float)
        if a.std() > 0 and b.std() > 0:
            corr = float(np.corrcoef(a, b)[0, 1])
            if corr > 0.5:
                overfit_note = f"correlation {corr:.2f} — parameters generalize reasonably well"
            elif corr > 0.1:
                overfit_note = f"correlation {corr:.2f} — weak. Treat the 'best' params with suspicion."
            else:
                overfit_note = (f"correlation {corr:.2f} — the in-sample winners do NOT hold up "
                                f"out-of-sample. This strategy is being fit to noise.")

    return clean({
        "symbol": symbol, "strategy": key, "metric": metric,
        "tested": len(rows), "results": rows[:100],
        "split_note": f"optimized on {len(is_df)} bars, validated on {len(oos_df)} unseen bars",
        "overfit_note": overfit_note,
    })


def do_scan(body: dict) -> dict:
    """Rank a basket of coins by current indicator conditions — the screener."""
    symbols = body.get("symbols") or dat.DEFAULT_SYMBOLS[:12]
    tf = body.get("timeframe", "4h")
    days = int(body.get("days", 180))

    out = []
    for sym in symbols:
        try:
            df = dat.get_candles(sym, tf, days)
            if len(df) < 210:
                continue
            b = ta.compute_bundle(df)
            last, prev = b.iloc[-1], b.iloc[-2]
            trend_up = bool(last["close"] > last["ema_trend"])
            notes = []
            score = 0
            if trend_up:
                score += 2; notes.append("above 200 EMA")
            if last["rsi"] < 35:
                score += 2; notes.append(f"oversold (RSI {last['rsi']:.0f})")
            elif last["rsi"] > 70:
                score -= 1; notes.append(f"overbought (RSI {last['rsi']:.0f})")
            if last["macd_hist"] > 0 and prev["macd_hist"] <= 0:
                score += 2; notes.append("MACD just turned up")
            if last["adx"] > 25:
                score += 1; notes.append(f"trending (ADX {last['adx']:.0f})")
            if last["vol_z"] > 2:
                score += 1; notes.append(f"volume spike ({last['vol_z']:.1f}σ)")
            if last["close"] < last["bb_lower"]:
                score += 1; notes.append("below lower Bollinger")

            out.append({
                "symbol": sym, "price": float(last["close"]), "score": score,
                "rsi": float(last["rsi"]), "adx": float(last["adx"]),
                "atr_pct": float(last["atr_pct"]), "vol_z": float(last["vol_z"]),
                "trend_up": trend_up,
                "chg_24h_pct": float(100 * (last["close"] / df["close"].iloc[-max(2, int(86400 / dat.TIMEFRAMES[tf]))] - 1)),
                "notes": notes,
            })
        except Exception as e:
            out.append({"symbol": sym, "error": f"{type(e).__name__}: {e}"})

    ok = [x for x in out if "error" not in x]
    ok.sort(key=lambda x: x["score"], reverse=True)
    return clean({"timeframe": tf, "results": ok,
                  "failed": [x for x in out if "error" in x]})


# ----------------------------------------------------------------------------
# Live signals — what would the systematic strategy do RIGHT NOW
# ----------------------------------------------------------------------------

def current_signal(symbol: str, tf: str, key: str, params: dict | None = None) -> dict:
    """
    What position the strategy would hold as of the last CLOSED candle.

    Reading it off the last closed candle (not the live one) is deliberate: the
    forming candle changes until it closes, so a signal based on it flickers and
    can vanish. Discipline means acting on settled information.
    """
    df = dat.get_candles(symbol, tf, 400)
    sig = strat.build_signal(key, df, params or {})
    b = ta.compute_bundle(df)
    last, prev = b.iloc[-1], b.iloc[-2]
    now = float(sig.iloc[-1])
    before = float(sig.iloc[-2])

    state = "LONG" if now > 0 else "SHORT" if now < 0 else "FLAT"
    changed = now != before
    action = "HOLD"
    if changed:
        action = "OPEN LONG" if now > 0 else "OPEN SHORT" if now < 0 else "CLOSE"

    return {
        "symbol": symbol, "strategy": key, "timeframe": tf,
        "state": state, "action": action, "just_changed": changed,
        "price": float(last["close"]),
        "candle_time": int(last["time"]),
        "bars_in_state": int((sig[::-1] != now).argmax()) if (sig != now).any() else len(sig),
        "rsi": float(last["rsi"]) if pd.notna(last["rsi"]) else None,
        "adx": float(last["adx"]) if pd.notna(last["adx"]) else None,
        "atr_pct": float(last["atr_pct"]) if pd.notna(last["atr_pct"]) else None,
        "trend_up": bool(last["close"] > last["ema_trend"]) if pd.notna(last["ema_trend"]) else None,
        "macd_up": bool(last["macd_hist"] > 0) if pd.notna(last["macd_hist"]) else None,
        "macd_flip": bool(pd.notna(prev["macd_hist"]) and
                          (last["macd_hist"] > 0) != (prev["macd_hist"] > 0)),
        "vol_z": float(last["vol_z"]) if pd.notna(last["vol_z"]) else None,
        # A sensible stop distance, in price terms, from current volatility.
        "atr_stop_2x": float(last["close"] - 2 * last["atr"]) if pd.notna(last["atr"]) else None,
    }


def do_signals(body: dict) -> dict:
    symbols = body.get("symbols") or ["BTC", "ETH", "SOL"]
    tf = body.get("timeframe", "4h")
    key = body.get("strategy", "trend_filtered_dip")
    params = body.get("params") or {}
    out, failed = [], []
    for s in symbols:
        try:
            out.append(current_signal(s.upper(), tf, key, params))
        except Exception as e:
            failed.append({"symbol": s, "error": f"{type(e).__name__}: {e}"})
    order = {"OPEN LONG": 0, "OPEN SHORT": 1, "CLOSE": 2, "HOLD": 3}
    out.sort(key=lambda r: (order.get(r["action"], 9), r["symbol"]))
    return clean({"timeframe": tf, "strategy": key,
                  "strategy_label": strat.REGISTRY[key]["label"],
                  "signals": out, "failed": failed})


# ----------------------------------------------------------------------------
# Paper trading
# ----------------------------------------------------------------------------

def _paper_prices(state: dict, extra: list[str] | None = None) -> dict[str, float]:
    syms = set(state["positions"]) | set(state.get("watchlist", [])) | set(extra or [])
    out = {}
    for s in syms:
        p = dat.latest_price(s)
        if p:
            out[s] = p
    return out


def do_paper_state(body: dict | None = None) -> dict:
    state = paper.load()
    prices = _paper_prices(state)
    return clean({
        "portfolio": paper.mark(state, prices),
        "scorecard": paper.scorecard(state),
        "trades": list(reversed(state["trades"]))[:200],
        "log": list(reversed(state["log"]))[:200],
        "watchlist": state.get("watchlist", []),
        "risk_profile": {**paper._blank()["risk_profile"], **state.get("risk_profile", {})},
        "prices": prices,
        "fee_bps": state.get("fee_bps", paper.DEFAULT_FEE_BPS),
        "demo": os.environ.get("QUANTLAB_DEMO") == "1",
    })


def _stamp(symbol: str, body: dict) -> str:
    """Record what the systematic strategy said at the moment of the trade."""
    try:
        s = current_signal(symbol, body.get("timeframe", "4h"),
                           body.get("strategy", "trend_filtered_dip"), body.get("params"))
        return f"{s['state']} ({s['action']}, RSI {s['rsi']:.0f})" if s.get("rsi") else s["state"]
    except Exception:
        return ""


def do_paper_buy(body: dict) -> dict:
    state = paper.load()
    sym = (body.get("symbol") or "BTC").upper()
    price = dat.latest_price(sym)
    if not price:
        raise dat.DataError(f"couldn't get a live price for {sym}")
    paper.buy(state, sym, float(body.get("usd", 0)), price,
              body.get("reason", ""), int(body.get("confidence", 3)), _stamp(sym, body),
              stop_price=body.get("stop_price"), target_price=body.get("target_price"))
    return do_paper_state()


def do_paper_sell(body: dict) -> dict:
    state = paper.load()
    sym = (body.get("symbol") or "").upper()
    price = dat.latest_price(sym)
    if not price:
        raise dat.DataError(f"couldn't get a live price for {sym}")
    paper.sell(state, sym, float(body.get("fraction", 1.0)), price,
               body.get("reason", ""), _stamp(sym, body))
    return do_paper_state()


def do_paper_reset(body: dict) -> dict:
    paper.reset(float(body.get("cash", paper.DEFAULT_CASH)))
    return do_paper_state()


def do_paper_watchlist(body: dict) -> dict:
    state = paper.load()
    state["watchlist"] = [s.upper() for s in (body.get("symbols") or [])][:20]
    paper.save(state)
    return do_paper_state()


# ----------------------------------------------------------------------------
# Radar — news, narratives, trending, new tokens
# ----------------------------------------------------------------------------

def do_news(body: dict) -> dict:
    sources = body.get("sources") or None
    hours = int(body.get("hours", 48))
    feed = news.fetch_news(sources, hours)
    items = feed["items"]

    q = (body.get("query") or "").strip().lower()
    if q:
        terms = [t for t in re.split(r"[,\s]+", q) if t]
        items = [it for it in items
                 if any(t in (it["title"] + " " + it.get("summary", "")).lower() for t in terms)]

    return clean({
        "items": items[:120],
        "narratives": news.narratives(feed["items"]),
        "failed": feed.get("failed", []),
        "sources": feed.get("sources", []),
        "demo": feed.get("demo", False) or os.environ.get("QUANTLAB_DEMO") == "1",
        "counts": {"total": len(feed["items"]), "shown": len(items[:120])},
    })


def do_trending(body: dict) -> dict:
    return clean(news.fetch_trending())


def do_new_pools(body: dict) -> dict:
    return clean(news.fetch_new_pools(body.get("network", "solana")))


# ----------------------------------------------------------------------------
# Shortlist — rank the universe by a formula you can backtest
# ----------------------------------------------------------------------------

def _attention_index(hours: int = 48) -> dict[str, float]:
    """
    Map coin symbols and names to a 0..100 news-attention figure.

    Kept strictly SEPARATE from the technical score. There is no historical
    news archive here, so this half cannot be backtested — and quietly blending
    an unbackestable input into a backtestable score would make the whole thing
    unfalsifiable. It gets its own column and its own caveat.
    """
    try:
        feed = news.fetch_news(None, hours)
        narr = news.narratives(feed["items"], top=120)
    except Exception:
        return {}
    if not narr:
        return {}

    top_score = max(n["score"] for n in narr) or 1.0
    index: dict[str, float] = {}
    for n in narr:
        term = n["term"].upper()
        index[term] = max(index.get(term, 0.0), 100.0 * n["score"] / top_score)
    return index


# Full names so "Solana" in a headline counts toward SOL.
COIN_NAMES = {
    "BTC": "BITCOIN", "ETH": "ETHEREUM", "SOL": "SOLANA", "XRP": "RIPPLE",
    "DOGE": "DOGECOIN", "ADA": "CARDANO", "AVAX": "AVALANCHE", "LINK": "CHAINLINK",
    "MATIC": "POLYGON", "DOT": "POLKADOT", "LTC": "LITECOIN", "BCH": "BITCOINCASH",
    "UNI": "UNISWAP", "ATOM": "COSMOS", "NEAR": "NEAR", "APT": "APTOS",
    "ARB": "ARBITRUM", "OP": "OPTIMISM", "INJ": "INJECTIVE", "SUI": "SUI",
    "TIA": "CELESTIA", "SEI": "SEI", "RNDR": "RENDER", "FIL": "FILECOIN",
}


def do_shortlist(body: dict) -> dict:
    symbols = [s.upper() for s in (body.get("symbols") or dat.DEFAULT_SYMBOLS[:14])]
    tf = body.get("timeframe", "4h")
    days = int(body.get("days", 400))
    top_n = int(body.get("top", 5))
    weights = body.get("weights") or {}
    use_news = bool(body.get("use_news", True))

    attention = _attention_index() if use_news else {}

    try:
        bench = dat.get_candles("BTC", tf, days)
    except Exception:
        bench = None

    rows, failed = [], []
    for sym in symbols:
        try:
            df = dat.get_candles(sym, tf, days)
            if len(df) < 220:
                failed.append({"symbol": sym, "error": "not enough history"})
                continue
            bd = rank.score_breakdown(df, weights)
            band, band_text = rank.verdict(bd["score"])
            b = ta.compute_bundle(df)
            last = b.iloc[-1]

            attn = max(attention.get(sym, 0.0),
                       attention.get(COIN_NAMES.get(sym, sym), 0.0))
            rs = rank.relative_strength(df, bench) if bench is not None else None

            rows.append({
                "symbol": sym, "price": float(last["close"]),
                "score": bd["score"], "band": band, "band_text": band_text,
                "factors": bd["factors"],
                "passed": sum(1 for f in bd["factors"] if f["passed"]),
                "attention": attn,
                "rel_strength_30d": rs,
                "rsi": float(last["rsi"]) if pd.notna(last["rsi"]) else None,
                "adx": float(last["adx"]) if pd.notna(last["adx"]) else None,
                "atr_pct": float(last["atr_pct"]) if pd.notna(last["atr_pct"]) else None,
                "trend_up": bool(last["close"] > last["ema_trend"]) if pd.notna(last["ema_trend"]) else None,
                "chg_7d": float(100 * (last["close"] / df["close"].iloc[-max(2, int(7 * 86400 / dat.TIMEFRAMES[tf]))] - 1)),
            })
        except Exception as e:
            failed.append({"symbol": sym, "error": f"{type(e).__name__}: {e}"})

    rows.sort(key=lambda r: -r["score"])
    shortlist = rows[:top_n]

    strong = [r for r in shortlist if r["score"] >= 65]
    if not rows:
        headline = "Couldn't score anything — check the failed list below."
    elif not strong:
        headline = (f"Nothing currently scores above 65. The top name is {shortlist[0]['symbol']} "
                    f"at {shortlist[0]['score']:.0f}. A shortlist with no strong candidates is a "
                    f"real answer, not a failure — the formula is telling you to stay in cash.")
    else:
        headline = (f"{len(strong)} of {len(rows)} coins score above 65. "
                    f"Top is {strong[0]['symbol']} at {strong[0]['score']:.0f}/100.")

    return clean({
        "timeframe": tf, "days": days, "scored": len(rows), "failed": failed,
        "shortlist": shortlist, "all": rows,
        "headline": headline,
        "weights": {**rank.DEFAULT_WEIGHTS, **weights},
        "factor_help": rank.FACTOR_HELP,
        "news_used": bool(attention),
        "demo": os.environ.get("QUANTLAB_DEMO") == "1",
        "verify": {
            "strategy": "quality_score",
            "note": "This exact formula is registered as the 'Quality Score' strategy. "
                    "Backtest it on any coin here before trusting today's ranking.",
        },
    })


# ----------------------------------------------------------------------------
# The trade planner — fills in the four blanks
# ----------------------------------------------------------------------------

def do_plan(body: dict) -> dict:
    """
    Every trade needs four numbers, and most people can only produce the first:

        1. WHAT   — which asset
        2. HOW MUCH — position size in dollars, decided before you feel anything
        3. WHERE YOU'RE WRONG — the stop price that proves the idea failed
        4. WHERE YOU'RE DONE  — the exit rule, written down in advance

    Numbers 2 and 3 are pure arithmetic once you've picked a risk tolerance, and
    they're computed here so nobody has to do them while excited.

    The sizing logic is the important part and it runs BACKWARDS from how most
    beginners think. You do not pick a position size and then wonder where to
    put a stop. You decide what you're willing to lose, decide where the idea is
    disproven, and the position size falls out of those two:

        position = dollars_at_risk / (distance_to_stop_as_a_fraction)

    A volatile coin needs a wider stop, which makes the position SMALLER for the
    same risk. That single inversion is most of professional risk management.
    """
    symbol = (body.get("symbol") or "BTC").upper()
    tf = body.get("timeframe", "4h")
    key = body.get("strategy", "trend_filtered_dip")
    params = body.get("params") or {}

    state = paper.load()
    rp = {**paper._blank()["risk_profile"], **state.get("risk_profile", {})}
    if body.get("risk_profile"):
        rp.update({k: float(v) for k, v in body["risk_profile"].items() if v is not None})
        state["risk_profile"] = rp
        paper.save(state)

    sig = current_signal(symbol, tf, key, params)
    prices = _paper_prices(state, [symbol])
    entry = prices.get(symbol) or sig["price"]

    portfolio = paper.mark(state, prices)
    equity, cash = portfolio["equity"], portfolio["cash"]

    # --- 3. Where you're wrong ------------------------------------------------
    df = dat.get_candles(symbol, tf, 200)
    atr_val = float(ta.atr(df, 14).iloc[-1])
    stop_dist = rp["stop_atr_mult"] * atr_val
    stop_price = entry - stop_dist
    stop_pct = 100.0 * stop_dist / entry

    # --- 2. How much ----------------------------------------------------------
    risk_usd = equity * rp["risk_pct"] / 100.0
    size_by_risk = risk_usd / (stop_dist / entry) if stop_dist > 0 else 0.0

    # The max-position cap applies to the TOTAL holding, not to each purchase.
    # Otherwise you could add 25% at a time indefinitely and quietly end up with
    # 80% of the account in one coin while believing the rule was protecting you.
    held_value = next((r["value"] or 0.0 for r in portfolio["positions"]
                       if r["symbol"] == symbol), 0.0)
    cap_position = max(0.0, equity * rp["max_position_pct"] / 100.0 - held_value)
    size_usd = min(size_by_risk, cap_position, cash)

    capped_by = None
    if size_usd <= 0:
        capped_by = (f"you already hold {fmt_usd(held_value)} of {symbol}, which is at or over "
                     f"your {rp['max_position_pct']:.0f}% limit"
                     if held_value > 0 else "no cash available")
    elif size_usd == cash < min(size_by_risk, cap_position):
        capped_by = "available cash"
    elif size_usd == cap_position < size_by_risk:
        capped_by = (f"the {rp['max_position_pct']:.0f}% max-position rule"
                     + (f" (you already hold {fmt_usd(held_value)})" if held_value > 0 else ""))

    actual_risk = size_usd * stop_dist / entry
    units = size_usd / entry if entry else 0.0

    # --- 4. Where you're done -------------------------------------------------
    target_price = entry + rp["target_r"] * stop_dist
    target_gain = size_usd * (target_price - entry) / entry if entry else 0.0

    # --- Verdict --------------------------------------------------------------
    reasons, warnings = [], []
    if sig["state"] == "LONG":
        reasons.append(f"Your strategy ({strat.REGISTRY[key]['label']}) is currently signalling LONG on {symbol}.")
    else:
        warnings.append(f"Your strategy says {sig['state']}, not LONG. Taking this trade means overriding your own system — allowed, but it gets recorded as an override.")
    if sig.get("just_changed"):
        reasons.append("The signal changed on the most recent closed candle, so this is a fresh setup rather than one you're late to.")
    if sig.get("trend_up"):
        reasons.append("Price is above its long-term trend line, which historically is where dip-buying works.")
    else:
        warnings.append("Price is BELOW its long-term trend line. Buying weakness in a downtrend is the most reliable way to lose money slowly.")
    if sig.get("rsi") is not None:
        if sig["rsi"] < 35:
            reasons.append(f"RSI is {sig['rsi']:.0f} — the market has been selling hard recently, which is what you want when buying a dip.")
        elif sig["rsi"] > 70:
            warnings.append(f"RSI is {sig['rsi']:.0f}. Price is stretched; you'd be buying after a run rather than before one.")
    if sig.get("adx") is not None and sig["adx"] < 20:
        warnings.append(f"ADX is {sig['adx']:.0f}, meaning there's no real trend right now — just chop. Breakouts tend to fail in this condition.")
    if sig.get("atr_pct") and sig["atr_pct"] > 6:
        warnings.append(f"This coin is unusually volatile right now ({sig['atr_pct']:.1f}% per candle), so the stop has to sit far away and the position comes out small. That's correct, not a bug.")
    if symbol in state["positions"]:
        warnings.append(f"You already hold {symbol}. Buying more concentrates your risk into one bet.")

    # --- Plain English --------------------------------------------------------
    plain = [
        f"**Buy ${size_usd:,.0f} of {symbol}** at about ${entry:,.2f} — that's {units:.6f} {symbol}, "
        f"or {100 * size_usd / equity:.0f}% of your ${equity:,.0f} account.",

        f"**You're wrong below ${stop_price:,.2f}** ({stop_pct:.1f}% down). That level is "
        f"{rp['stop_atr_mult']:.1f}× the average candle size, so normal daily noise shouldn't reach it — "
        f"if price gets there, something actually changed.",

        f"**That risks ${actual_risk:,.0f}**, which is {100 * actual_risk / equity:.1f}% of your account. "
        f"You could be wrong {int(equity / actual_risk) if actual_risk else 0} times in a row and still be trading.",

        f"**You're done at ${target_price:,.2f}** (+${target_gain:,.0f}), or earlier if the exit rule fires: "
        f"{strat.EXIT_RULES.get(key, 'see the strategy description')}",

        f"**Reward vs risk is {rp['target_r']:.1f} to 1.** You win ${target_gain:,.0f} if right, lose "
        f"${actual_risk:,.0f} if wrong — so you only need to be right about "
        f"{100 / (1 + rp['target_r']):.0f}% of the time to break even.",
    ]
    if capped_by:
        plain.insert(1, f"_(Size was limited by {capped_by} rather than by your risk setting.)_")

    return clean({
        "symbol": symbol, "timeframe": tf, "strategy": key,
        "strategy_label": strat.REGISTRY[key]["label"],
        "demo": os.environ.get("QUANTLAB_DEMO") == "1",
        "entry_price": entry,
        "verdict": {
            "state": sig["state"], "action": sig["action"],
            "aligned": sig["state"] == "LONG",
            "reasons": reasons, "warnings": warnings,
        },
        "plan": {
            "what": symbol,
            "size_usd": size_usd, "units": units,
            "size_pct_of_account": 100.0 * size_usd / equity if equity else 0.0,
            "capped_by": capped_by,
            "stop_price": stop_price, "stop_pct": stop_pct,
            "risk_usd": actual_risk,
            "risk_pct_of_account": 100.0 * actual_risk / equity if equity else 0.0,
            "stop_basis": f"{rp['stop_atr_mult']:.1f} x ATR({14}) = ${stop_dist:,.2f}",
            "target_price": target_price, "target_gain": target_gain,
            "reward_risk": rp["target_r"],
            "breakeven_win_rate": 100.0 / (1 + rp["target_r"]),
            "exit_rule": strat.EXIT_RULES.get(key, ""),
            "max_consecutive_losses_survivable": int(equity / actual_risk) if actual_risk else 0,
        },
        "account": {"equity": equity, "cash": cash,
                    "open_positions": len(state["positions"])},
        "risk_profile": rp,
        "context": {k: sig.get(k) for k in
                    ("rsi", "adx", "atr_pct", "trend_up", "macd_up", "vol_z", "bars_in_state")},
        "atr": atr_val,
        "plain": plain,
    })


def do_set_risk(body: dict) -> dict:
    state = paper.load()
    rp = {**paper._blank()["risk_profile"], **state.get("risk_profile", {})}
    for k in ("risk_pct", "stop_atr_mult", "target_r", "max_position_pct"):
        if body.get(k) is not None:
            rp[k] = float(body[k])
    rp["risk_pct"] = max(0.1, min(rp["risk_pct"], 100.0))
    rp["max_position_pct"] = max(1.0, min(rp["max_position_pct"], 100.0))
    rp["stop_atr_mult"] = max(0.5, min(rp["stop_atr_mult"], 10.0))
    rp["target_r"] = max(0.5, min(rp["target_r"], 10.0))
    state["risk_profile"] = rp
    paper.save(state)
    return clean({"risk_profile": rp})


def do_compare(body: dict) -> dict:
    """Run every strategy on the same data with default params. The leaderboard."""
    symbol = body.get("symbol", "BTC").upper()
    tf = body.get("timeframe", "1h")
    days = int(body.get("days", 365))
    df = load(symbol, tf, days)
    cfg = cfg_from(body, tf)
    atr_s = ta.atr(df, 14)

    rows = []
    for key, meta in strat.REGISTRY.items():
        try:
            res = run_backtest(df, strat.build_signal(key, df), cfg, atr_s)
            st = res["stats"]
            rows.append({
                "key": key, "label": meta["label"], "family": meta["family"],
                "total_return_pct": st["total_return_pct"], "sharpe": st["sharpe"],
                "max_drawdown_pct": st["max_drawdown_pct"], "win_rate_pct": st["win_rate_pct"],
                "num_trades": st["num_trades"], "profit_factor": st["profit_factor"],
                "alpha_pct": st["alpha_pct"], "time_in_market_pct": st["time_in_market_pct"],
            })
        except Exception as e:
            rows.append({"key": key, "label": meta["label"], "error": str(e)})

    rows.sort(key=lambda r: r.get("total_return_pct", -9e9), reverse=True)
    return clean({"symbol": symbol, "timeframe": tf, "days": days, "results": rows})


# ----------------------------------------------------------------------------
# HTTP plumbing
# ----------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "QuantLab/1.0"

    def log_message(self, fmt, *args):  # quieter console
        if "/api/" in (args[0] if args else ""):
            print(f"  {args[0]}")

    # -- helpers --
    def _send(self, code: int, payload: dict, ctype="application/json"):
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(raw)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        return json.loads(self.rfile.read(n).decode("utf-8") or "{}")

    def _static(self, path: str):
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        full = os.path.normpath(os.path.join(WEB_DIR, rel))
        if not full.startswith(WEB_DIR) or not os.path.isfile(full):
            self._send(404, {"error": "not found"})
            return
        ctype = {"html": "text/html", "js": "application/javascript", "css": "text/css",
                 "json": "application/json", "svg": "image/svg+xml"}.get(full.rsplit(".", 1)[-1],
                                                                         "application/octet-stream")
        with open(full, "rb") as f:
            raw = f.read()
        self.send_response(200)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            if u.path == "/api/meta":
                self._send(200, {
                    "strategies": strat.schema(),
                    "symbols": dat.DEFAULT_SYMBOLS,
                    "timeframes": list(dat.TIMEFRAMES.keys()),
                })
            elif u.path == "/api/price":
                sym = (q.get("symbol", ["BTC"])[0]).upper()
                self._send(200, {"symbol": sym, "price": dat.latest_price(sym)})
            elif u.path == "/api/clear_cache":
                n = dat.clear_cache(q.get("symbol", [None])[0])
                self._send(200, {"cleared": n})
            elif u.path.startswith("/api/"):
                self._send(404, {"error": f"no route {u.path}"})
            else:
                self._static(u.path)
        except Exception as e:
            traceback.print_exc()
            self._send(500, {"error": f"{type(e).__name__}: {e}"})

    def do_POST(self):
        u = urlparse(self.path)
        routes = {"/api/backtest": do_backtest, "/api/optimize": do_optimize,
                  "/api/scan": do_scan, "/api/compare": do_compare,
                  "/api/signals": do_signals, "/api/plan": do_plan,
                  "/api/risk": do_set_risk, "/api/news": do_news,
                  "/api/trending": do_trending, "/api/newpools": do_new_pools,
                  "/api/shortlist": do_shortlist,
                  "/api/paper": do_paper_state, "/api/paper/buy": do_paper_buy,
                  "/api/paper/sell": do_paper_sell, "/api/paper/reset": do_paper_reset,
                  "/api/paper/watchlist": do_paper_watchlist}
        fn = routes.get(u.path)
        if fn is None:
            self._send(404, {"error": f"no route {u.path}"})
            return
        try:
            self._send(200, fn(self._body()))
        except paper.PaperError as e:
            self._send(400, {"error": str(e)})
        except (dat.DataError, KeyError, ValueError) as e:
            self._send(400, {"error": str(e).strip('"')})
        except Exception as e:
            traceback.print_exc()
            self._send(500, {"error": f"{type(e).__name__}: {e}"})


def serve(host: str = "127.0.0.1", port: int = 8777):
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"\n  QuantLab running →  http://{host}:{port}\n")
    print("  Ctrl+C to stop.\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped.\n")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    serve()
