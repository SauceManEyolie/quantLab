"""
strategies.py — the pluggable strategy library.

A strategy is just a function:

    def my_strategy(df, p) -> pd.Series   # values in {-1, 0, 1}

where the returned Series is the DESIRED POSITION for each bar
(1 = long, 0 = flat, -1 = short). The engine handles the rest.

Each strategy also declares a parameter schema, which the web UI reads to
auto-generate its sliders. Add a strategy here and it appears in the app with
no frontend changes at all.

TO ADD YOUR OWN: copy any block below, change the logic, register it at the
bottom. That's the whole extension mechanism.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import indicators as ta
import rank


# ----------------------------------------------------------------------------
# Helper: turn entry/exit events into a held position
# ----------------------------------------------------------------------------

def hold(entries: pd.Series, exits: pd.Series, shorts: pd.Series | None = None,
         short_exits: pd.Series | None = None) -> pd.Series:
    """
    Convert boolean entry/exit events into a continuously-held position series.
    Once you enter, you stay in until an exit fires. If both fire on the same
    bar, exit wins (safer).
    """
    raw = pd.Series(np.nan, index=entries.index)
    raw[entries.fillna(False).astype(bool)] = 1.0
    if shorts is not None:
        raw[shorts.fillna(False).astype(bool)] = -1.0
    raw[exits.fillna(False).astype(bool)] = 0.0
    if short_exits is not None:
        raw[short_exits.fillna(False).astype(bool)] = 0.0
    return raw.ffill().fillna(0.0)


def cross_over(a: pd.Series, b: pd.Series) -> pd.Series:
    """True on the bar where a crosses from below b to above b."""
    return (a > b) & (a.shift(1) <= b.shift(1))


def cross_under(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a < b) & (a.shift(1) >= b.shift(1))


# ----------------------------------------------------------------------------
# Strategies
# ----------------------------------------------------------------------------

def s_buy_hold(df: pd.DataFrame, p: dict) -> pd.Series:
    return pd.Series(1.0, index=df.index)


def s_rsi_reversion(df: pd.DataFrame, p: dict) -> pd.Series:
    """Buy fear, sell greed. Works in ranges, gets run over by strong trends."""
    r = ta.rsi(df["close"], int(p["rsi_len"]))
    entries = r < p["oversold"]
    exits = r > p["exit_level"]
    shorts = (r > p["overbought"]) if p.get("use_shorts") else None
    short_exits = (r < p["exit_level"]) if p.get("use_shorts") else None
    return hold(entries, exits, shorts, short_exits)


def s_ema_cross(df: pd.DataFrame, p: dict) -> pd.Series:
    """The classic trend follower. Loses small and often, wins big and rarely."""
    fast = ta.ema(df["close"], int(p["fast"]))
    slow = ta.ema(df["close"], int(p["slow"]))
    entries = cross_over(fast, slow)
    exits = cross_under(fast, slow)
    if p.get("use_shorts"):
        return hold(entries, pd.Series(False, index=df.index), exits, pd.Series(False, index=df.index))
    return hold(entries, exits)


def s_macd(df: pd.DataFrame, p: dict) -> pd.Series:
    """Long while MACD momentum is positive. Same family as EMA cross, smoother."""
    m = ta.macd(df["close"], int(p["fast"]), int(p["slow"]), int(p["signal"]))
    entries = cross_over(m["macd"], m["signal"])
    exits = cross_under(m["macd"], m["signal"])
    if p.get("require_positive"):
        entries = entries & (m["macd"] > 0)
    return hold(entries, exits)


def s_bollinger_reversion(df: pd.DataFrame, p: dict) -> pd.Series:
    """Buy the lower band, sell back at the middle. Textbook mean reversion."""
    b = ta.bollinger(df["close"], int(p["length"]), float(p["mult"]))
    entries = df["close"] < b["lower"]
    exits = df["close"] > b["mid"]
    return hold(entries, exits)


def s_donchian_breakout(df: pd.DataFrame, p: dict) -> pd.Series:
    """
    Turtle-style breakout: buy new N-bar highs, exit on M-bar lows.
    Feels awful to trade (you always buy the top) and has made a lot of money.
    """
    up = ta.donchian(df, int(p["entry_len"]))["upper"]
    dn = ta.donchian(df, int(p["exit_len"]))["lower"]
    entries = df["close"] > up
    exits = df["close"] < dn
    return hold(entries, exits)


def s_trend_filtered_dip(df: pd.DataFrame, p: dict) -> pd.Series:
    """
    Buy dips, but ONLY when the long-term trend is up.

    This is the single most valuable idea in the whole file: a regime filter.
    The same dip-buying logic that gets destroyed in a bear market is often
    fine in a bull market. Filtering by trend is usually worth more than
    tuning the entry.
    """
    trend = ta.ema(df["close"], int(p["trend_len"]))
    r = ta.rsi(df["close"], int(p["rsi_len"]))
    bull = df["close"] > trend
    entries = bull & (r < p["oversold"])
    exits = (r > p["exit_level"]) | (~bull)
    return hold(entries, exits)


def s_adx_trend(df: pd.DataFrame, p: dict) -> pd.Series:
    """Only trade the EMA cross when ADX says a real trend exists."""
    a = ta.adx(df, int(p["adx_len"]))
    fast = ta.ema(df["close"], int(p["fast"]))
    slow = ta.ema(df["close"], int(p["slow"]))
    strong = a["adx"] > p["adx_min"]
    entries = cross_over(fast, slow) & strong
    exits = cross_under(fast, slow) | (a["adx"] < p["adx_exit"])
    return hold(entries, exits)


def s_volume_breakout(df: pd.DataFrame, p: dict) -> pd.Series:
    """
    Enter when volume spikes AND price moves up — something real happened.
    Exit after a fixed number of bars or when momentum fades.
    """
    vz = ta.volume_zscore(df, int(p["vol_len"]))
    ret = df["close"].pct_change(int(p["ret_len"])) * 100.0
    ema_s = ta.ema(df["close"], int(p["exit_ema"]))
    entries = (vz > p["vol_z_min"]) & (ret > p["min_move_pct"])
    exits = df["close"] < ema_s
    return hold(entries, exits)


def s_bb_squeeze(df: pd.DataFrame, p: dict) -> pd.Series:
    """
    Volatility contraction then expansion. When bands get unusually tight,
    a big move often follows — trade the direction it breaks.
    """
    b = ta.bollinger(df["close"], int(p["length"]), float(p["mult"]))
    tight = b["width"] < b["width"].rolling(int(p["lookback"]), min_periods=int(p["lookback"])).quantile(
        float(p["squeeze_pct"]) / 100.0)
    was_tight = tight.shift(1).astype("boolean").fillna(False).astype(bool)
    entries = was_tight & (df["close"] > b["upper"])
    exits = df["close"] < b["mid"]
    return hold(entries, exits)


def s_composite(df: pd.DataFrame, p: dict) -> pd.Series:
    """
    Score-based ensemble: every ingredient votes, you trade when enough agree.

    Robust by construction — no single indicator can drag you into a trade
    alone, which cuts the false signals that kill single-indicator systems.
    """
    close = df["close"]
    score = pd.Series(0.0, index=df.index)

    score += (close > ta.ema(close, int(p["trend_len"]))).astype(float)              # trend up
    score += (ta.rsi(close, 14) < p["rsi_max"]).astype(float)                        # not overbought
    m = ta.macd(close)
    score += (m["hist"] > 0).astype(float)                                           # momentum up
    b = ta.bollinger(close, 20, 2.0)
    score += (b["pct_b"] < float(p["pctb_max"])).astype(float)                       # not stretched
    score += (ta.adx(df, 14)["adx"] > p["adx_min"]).astype(float)                    # trend has strength

    entries = score >= p["entry_score"]
    exits = score <= p["exit_score"]
    return hold(entries, exits)


def s_quality_score(df: pd.DataFrame, p: dict) -> pd.Series:
    """
    THE SHORTLIST FORMULA, BACKTESTED.

    This runs the exact same scoring function the Shortlist tab uses to rank
    coins — see rank.py. Long while the score is above your entry threshold,
    flat when it falls to the exit threshold.

    Run this before you trust any ranking the shortlist gives you. If the
    formula has no edge over three years of history on the coin you're looking
    at, then its opinion about today is worth nothing either.
    """
    weights = {k: float(p[f"w_{k}"]) for k in rank.DEFAULT_WEIGHTS if f"w_{k}" in p}
    score = rank.quality_score(df, weights, {"trend_len": p.get("trend_len", 200)})
    entries = score >= p["entry_score"]
    exits = score <= p["exit_score"]
    return hold(entries, exits)


# ----------------------------------------------------------------------------
# Registry — the UI reads this to build its controls
# ----------------------------------------------------------------------------

def _p(name, label, default, lo=None, hi=None, step=1, kind="number", help=""):
    return {"name": name, "label": label, "default": default, "min": lo,
            "max": hi, "step": step, "type": kind, "help": help}


REGISTRY: dict[str, dict] = {
    "buy_hold": {
        "label": "Buy & Hold (baseline)",
        "family": "baseline",
        "blurb": "Buy on bar one, never sell. This is the benchmark every other strategy has to beat. If your clever system loses to this, it isn't clever.",
        "fn": s_buy_hold,
        "params": [],
    },
    "rsi_reversion": {
        "label": "RSI Mean Reversion",
        "family": "mean reversion",
        "blurb": "Buy when RSI says the market is oversold, sell when it recovers. Profitable in choppy, range-bound markets; painful in sustained downtrends.",
        "fn": s_rsi_reversion,
        "params": [
            _p("rsi_len", "RSI length", 14, 2, 50, 1, help="Lookback for RSI. Shorter = twitchier."),
            _p("oversold", "Buy below RSI", 30, 5, 50, 1, help="Lower = fewer but more extreme entries."),
            _p("exit_level", "Sell above RSI", 55, 40, 90, 1, help="Where you take profit."),
            _p("overbought", "Short above RSI", 70, 50, 95, 1, help="Only used if shorting is on."),
            _p("use_shorts", "Allow shorts", False, kind="bool"),
        ],
    },
    "ema_cross": {
        "label": "EMA Crossover (trend)",
        "family": "trend",
        "blurb": "Go long when the fast average crosses above the slow one. Many small losses in chop, occasional large wins in trends. Judge it on total P&L, not win rate.",
        "fn": s_ema_cross,
        "params": [
            _p("fast", "Fast EMA", 20, 2, 100, 1),
            _p("slow", "Slow EMA", 50, 5, 300, 1),
            _p("use_shorts", "Flip short on down-cross", False, kind="bool"),
        ],
    },
    "macd": {
        "label": "MACD Momentum",
        "family": "trend",
        "blurb": "Long while MACD is above its signal line. A smoother cousin of the EMA cross with slightly later entries and fewer whipsaws.",
        "fn": s_macd,
        "params": [
            _p("fast", "Fast", 12, 2, 60, 1),
            _p("slow", "Slow", 26, 5, 200, 1),
            _p("signal", "Signal", 9, 2, 50, 1),
            _p("require_positive", "Only when MACD > 0", True, kind="bool",
               help="Extra filter: ignore crosses that happen below zero."),
        ],
    },
    "bollinger_reversion": {
        "label": "Bollinger Band Reversion",
        "family": "mean reversion",
        "blurb": "Buy when price pokes below the lower band, sell when it returns to the middle. Classic 'snap back to average' trade.",
        "fn": s_bollinger_reversion,
        "params": [
            _p("length", "Length", 20, 5, 100, 1),
            _p("mult", "Std dev multiplier", 2.0, 0.5, 4.0, 0.1),
        ],
    },
    "donchian_breakout": {
        "label": "Donchian Breakout (Turtle)",
        "family": "breakout",
        "blurb": "Buy new N-bar highs, exit on M-bar lows. The original Turtle Traders system. Low win rate, big winners — you must let them run.",
        "fn": s_donchian_breakout,
        "params": [
            _p("entry_len", "Breakout lookback", 20, 5, 200, 1),
            _p("exit_len", "Exit lookback", 10, 3, 100, 1),
        ],
    },
    "trend_filtered_dip": {
        "label": "Dip Buy + Trend Filter",
        "family": "hybrid",
        "blurb": "Buy oversold dips, but only while price is above its long-term average. Adding the trend filter is usually worth more than any amount of tuning.",
        "fn": s_trend_filtered_dip,
        "params": [
            _p("trend_len", "Trend EMA", 200, 20, 500, 1, help="Only buy while price is above this."),
            _p("rsi_len", "RSI length", 14, 2, 50, 1),
            _p("oversold", "Buy below RSI", 40, 5, 60, 1),
            _p("exit_level", "Sell above RSI", 65, 40, 90, 1),
        ],
    },
    "adx_trend": {
        "label": "ADX-Gated Trend",
        "family": "trend",
        "blurb": "An EMA cross that only fires when ADX confirms a real trend is underway. Fewer trades, higher quality — the point is to sit out the chop.",
        "fn": s_adx_trend,
        "params": [
            _p("fast", "Fast EMA", 20, 2, 100, 1),
            _p("slow", "Slow EMA", 50, 5, 300, 1),
            _p("adx_len", "ADX length", 14, 5, 50, 1),
            _p("adx_min", "Enter above ADX", 25, 10, 50, 1),
            _p("adx_exit", "Exit below ADX", 20, 5, 40, 1),
        ],
    },
    "volume_breakout": {
        "label": "Volume Spike Breakout",
        "family": "breakout",
        "blurb": "Enter when volume is abnormally high AND price is moving up — evidence that real money is involved, not just noise.",
        "fn": s_volume_breakout,
        "params": [
            _p("vol_len", "Volume lookback", 20, 5, 100, 1),
            _p("vol_z_min", "Min volume z-score", 2.0, 0.5, 5.0, 0.1, help="2.0 means 'twice as unusual as normal'."),
            _p("ret_len", "Move lookback (bars)", 3, 1, 20, 1),
            _p("min_move_pct", "Min move %", 1.0, 0.0, 10.0, 0.1),
            _p("exit_ema", "Exit below EMA", 20, 5, 100, 1),
        ],
    },
    "bb_squeeze": {
        "label": "Volatility Squeeze Breakout",
        "family": "breakout",
        "blurb": "When Bollinger Bands get unusually tight the market is coiling. Trade the direction it breaks out of the squeeze.",
        "fn": s_bb_squeeze,
        "params": [
            _p("length", "BB length", 20, 5, 100, 1),
            _p("mult", "Std dev multiplier", 2.0, 0.5, 4.0, 0.1),
            _p("lookback", "Squeeze lookback", 100, 20, 500, 1),
            _p("squeeze_pct", "Squeeze percentile", 20, 1, 50, 1, help="Bands in the tightest X% of the lookback."),
        ],
    },
    "quality_score": {
        "label": "Quality Score (the shortlist formula)",
        "family": "hybrid",
        "blurb": "The exact formula the Shortlist tab uses to rank coins, run as a strategy. Six weighted factors produce a 0-100 score; you hold while it's above your entry threshold. Backtest this before trusting any ranking it gives you — if it has no edge on history, its opinion about today is worthless.",
        "fn": s_quality_score,
        "params": [
            _p("entry_score", "Buy above score", 65, 30, 95, 1,
               help="65 means most factors must agree before you buy."),
            _p("exit_score", "Sell below score", 45, 10, 80, 1,
               help="Set well below the entry to avoid flip-flopping around one level."),
            _p("trend_len", "Trend EMA", 200, 20, 400, 1),
            _p("w_trend", "Weight: above trend", 0.30, 0, 1, 0.05),
            _p("w_momentum", "Weight: momentum", 0.20, 0, 1, 0.05),
            _p("w_macd", "Weight: MACD", 0.15, 0, 1, 0.05),
            _p("w_rsi_zone", "Weight: RSI zone", 0.15, 0, 1, 0.05),
            _p("w_strength", "Weight: ADX strength", 0.10, 0, 1, 0.05),
            _p("w_volume", "Weight: volume", 0.10, 0, 1, 0.05),
        ],
    },
    "composite": {
        "label": "Composite Score (ensemble)",
        "family": "hybrid",
        "blurb": "Five signals each cast a vote; you go long only when enough agree. Harder to overfit than any single indicator, and usually the most stable performer here.",
        "fn": s_composite,
        "params": [
            _p("trend_len", "Trend EMA", 100, 20, 400, 1),
            _p("rsi_max", "RSI must be below", 70, 40, 95, 1),
            _p("pctb_max", "Bollinger %B below", 0.9, 0.1, 1.5, 0.05),
            _p("adx_min", "ADX above", 20, 5, 50, 1),
            _p("entry_score", "Votes needed to buy", 4, 1, 5, 1, help="Out of 5."),
            _p("exit_score", "Votes to exit at", 2, 0, 4, 1),
        ],
    },
}


# Plain-English exit rules, for the guided trade planner. Answering "where am I
# done?" in advance is the blank most beginners leave empty — which is exactly
# why they end up holding losers and selling winners.
EXIT_RULES: dict[str, str] = {
    "buy_hold": "Never — this one is a benchmark, not a trade.",
    "rsi_reversion": "Sell when RSI climbs back above your exit level (the bounce has happened).",
    "ema_cross": "Sell when the fast EMA crosses back below the slow EMA (momentum turned).",
    "macd": "Sell when MACD crosses below its signal line (momentum faded).",
    "bollinger_reversion": "Sell when price returns to the middle Bollinger band (it snapped back).",
    "donchian_breakout": "Sell when price makes a new N-bar low (the breakout failed).",
    "trend_filtered_dip": "Sell when RSI recovers above your exit level, OR immediately if price falls below its long-term trend line.",
    "adx_trend": "Sell when the fast EMA crosses back down, or when ADX drops below your exit threshold (the trend died).",
    "volume_breakout": "Sell when price closes below the exit EMA (the surge is over).",
    "bb_squeeze": "Sell when price falls back to the middle Bollinger band.",
    "composite": "Sell when the number of agreeing signals drops to your exit score.",
    "quality_score": "Sell when the quality score falls to your exit threshold — meaning the factors that justified the trade no longer agree.",
}


def defaults(key: str) -> dict:
    return {p["name"]: p["default"] for p in REGISTRY[key]["params"]}


def build_signal(key: str, df: pd.DataFrame, params: dict | None = None) -> pd.Series:
    if key not in REGISTRY:
        raise KeyError(f"unknown strategy {key!r}; available: {sorted(REGISTRY)}")
    p = defaults(key)
    if params:
        for k, v in params.items():
            if k in p and isinstance(p[k], bool):
                p[k] = v if isinstance(v, bool) else str(v).lower() in ("true", "1", "yes")
            elif k in p:
                try:
                    p[k] = float(v)
                except (TypeError, ValueError):
                    p[k] = v
            else:
                p[k] = v
    sig = REGISTRY[key]["fn"](df, p)
    return pd.Series(sig, index=df.index).fillna(0.0)


def schema() -> list[dict]:
    """JSON-safe description of every strategy, for the frontend."""
    return [
        {"key": k, "label": v["label"], "family": v["family"],
         "blurb": v["blurb"], "params": v["params"],
         "exit_rule": EXIT_RULES.get(k, "")}
        for k, v in REGISTRY.items()
    ]
