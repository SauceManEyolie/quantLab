"""
rank.py — the scoring formula, shared by the live shortlist AND the backtest.

THE POINT OF THIS FILE
----------------------
Most "top coins to buy" lists are unfalsifiable. Someone asserts five tickers,
and there is no way to check whether the method that produced them has ever
worked. This module exists so that cannot happen here.

`quality_score()` returns a score for EVERY BAR of history, not just today.
That single design choice means:

  * The Shortlist tab evaluates it at the latest bar to rank coins today.
  * The `quality_score` strategy evaluates it across years to backtest it.

They are the same function. If the shortlist ranks a coin highly, you can go
and see exactly what that ranking rule would have done over the last three
years, on any coin, with fees and slippage included. A ranking you can backtest
is worth more than an opinion you cannot.

WHAT THE FORMULA ACTUALLY MEASURES
----------------------------------
Six factors, each normalised to 0..1, then weighted. Deliberately boring and
deliberately few — every extra parameter is another chance to overfit.

  trend       Is price above its long-term average?           (regime)
  momentum    Is the fast average above the slow one?         (direction)
  macd        Is short-term momentum positive?                (confirmation)
  rsi_zone    Is price in a healthy range, not stretched?     (entry quality)
  strength    Is there a real trend rather than chop?         (ADX)
  volume      Is participation above normal?                  (conviction)

Every one is causal — computed only from data at or before the bar in question.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import indicators as ta

# Default weights. They sum to 1.0 so the score lands in 0..100.
# These are round numbers on purpose: they were NOT tuned to make a backtest
# look good, which is the only reason to trust them at all. Tune them yourself
# in the Optimize tab and watch the out-of-sample column.
DEFAULT_WEIGHTS = {
    "trend": 0.30,      # by far the most reliable single factor
    "momentum": 0.20,
    "macd": 0.15,
    "rsi_zone": 0.15,
    "strength": 0.10,
    "volume": 0.10,
}

FACTOR_LABELS = {
    "trend": "Above long-term trend",
    "momentum": "Fast average above slow",
    "macd": "Short-term momentum up",
    "rsi_zone": "Not overbought / not falling",
    "strength": "Real trend, not chop",
    "volume": "Participation above normal",
}

FACTOR_HELP = {
    "trend": "Price above its 200-period EMA. The single most valuable filter in the whole app — it keeps you out of the periods that do the most damage.",
    "momentum": "The 20-period EMA above the 50-period. Confirms the medium-term direction agrees with the long-term one.",
    "macd": "MACD histogram positive, meaning short-term momentum is pulling upward.",
    "rsi_zone": "RSI between 40 and 70 scores full marks. Below 40 means price is still falling; above 70 means you'd be buying after the move.",
    "strength": "ADX above 15, scaled to full marks at 35. Low ADX means chop, where these signals fail.",
    "volume": "Volume z-score above zero, full marks at 2 standard deviations. Real participation rather than drift.",
}


def _clip01(s: pd.Series) -> pd.Series:
    return s.clip(0.0, 1.0).fillna(0.0)


def quality_components(df: pd.DataFrame, params: dict | None = None) -> pd.DataFrame:
    """
    Return a DataFrame with one column per factor, each in 0..1, per bar.

    Nothing here peeks at future bars. Indicator warm-up periods produce NaN,
    which becomes 0.0 — an unknown factor scores nothing rather than helping.
    """
    p = {"trend_len": 200, "fast": 20, "slow": 50, "rsi_len": 14,
         "adx_len": 14, "vol_len": 20}
    if params:
        p.update({k: int(v) for k, v in params.items() if k in p})

    close = df["close"]
    out = pd.DataFrame(index=df.index)

    out["trend"] = (close > ta.ema(close, p["trend_len"])).astype(float)
    out["momentum"] = (ta.ema(close, p["fast"]) > ta.ema(close, p["slow"])).astype(float)
    out["macd"] = (ta.macd(close)["hist"] > 0).astype(float)

    # RSI zone: 1.0 across the healthy 40-70 band, tapering to 0 outside it.
    r = ta.rsi(close, p["rsi_len"])
    zone = pd.Series(0.0, index=df.index)
    zone = zone.where(~r.between(40, 70), 1.0)
    zone = zone.where(~r.between(30, 40), (r - 30) / 10.0)      # ramp up 30->40
    zone = zone.where(~r.between(70, 80), (80 - r) / 10.0)      # ramp down 70->80
    out["rsi_zone"] = _clip01(zone)

    out["strength"] = _clip01((ta.adx(df, p["adx_len"])["adx"] - 15.0) / 20.0)
    out["volume"] = _clip01(ta.volume_zscore(df, p["vol_len"]) / 2.0)

    return out.fillna(0.0)


def quality_score(df: pd.DataFrame, weights: dict | None = None,
                  params: dict | None = None) -> pd.Series:
    """Weighted blend of the factors, 0..100, one value per bar."""
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    comp = quality_components(df, params)
    total = sum(w.get(k, 0.0) for k in comp.columns) or 1.0
    score = sum(comp[k] * w.get(k, 0.0) for k in comp.columns) / total
    return (score * 100.0).rename("score")


def score_breakdown(df: pd.DataFrame, weights: dict | None = None,
                    params: dict | None = None) -> dict:
    """
    Explain the CURRENT score: each factor's raw value, weight, and how many
    points it contributed. This is what makes the ranking auditable instead of
    a black box — you can see precisely why a coin placed where it did.
    """
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    comp = quality_components(df, params)
    last = comp.iloc[-1]
    total_w = sum(w.get(k, 0.0) for k in comp.columns) or 1.0

    factors = []
    for k in comp.columns:
        contrib = 100.0 * last[k] * w.get(k, 0.0) / total_w
        factors.append({
            "key": k, "label": FACTOR_LABELS[k], "help": FACTOR_HELP[k],
            "value": float(last[k]), "weight": w.get(k, 0.0),
            "points": float(contrib),
            "max_points": 100.0 * w.get(k, 0.0) / total_w,
            "passed": bool(last[k] >= 0.5),
        })
    factors.sort(key=lambda f: -f["points"])
    return {"score": float(quality_score(df, weights, params).iloc[-1]), "factors": factors}


def relative_strength(df: pd.DataFrame, bench: pd.DataFrame, bars: int = 180) -> float | None:
    """
    How much this coin outperformed the benchmark over the last N bars.

    A cross-sectional measure — it needs another asset to compare against, so it
    cannot live inside a single-asset backtest. The shortlist shows it as a
    separate column for exactly that reason: it is information, but it is NOT
    part of the validated formula, and mixing the two would be dishonest.
    """
    if len(df) < bars + 1 or len(bench) < bars + 1:
        return None
    a = float(df["close"].iloc[-1] / df["close"].iloc[-bars - 1] - 1.0)
    b = float(bench["close"].iloc[-1] / bench["close"].iloc[-bars - 1] - 1.0)
    return 100.0 * (a - b)


def verdict(score: float) -> tuple[str, str]:
    """Plain-English band for a score. Bands are descriptive, not advice."""
    if score >= 80:
        return ("strong", "Nearly every factor lines up. Rare, and worth a look — but "
                          "'everything agrees' often means the move has already started.")
    if score >= 65:
        return ("decent", "Most factors agree. This is the band the backtest is actually built around.")
    if score >= 45:
        return ("mixed", "Roughly half the factors agree. Historically a coin flip — no edge here.")
    if score >= 25:
        return ("weak", "Most factors are against it. The formula would be flat.")
    return ("avoid", "Almost nothing supports buying this right now.")
