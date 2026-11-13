"""
indicators.py — technical indicator math, pure pandas/numpy.

Every function takes a DataFrame `df` with columns:
    time (int, unix seconds), open, high, low, close, volume
and returns a pandas Series (or DataFrame for multi-line indicators)
aligned to df's index.

Design rule: NOTHING here may look at future bars. Every value at index i
is computed only from data at indices <= i. This is what keeps backtests honest.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ----------------------------------------------------------------------------
# Moving averages
# ----------------------------------------------------------------------------

def sma(series: pd.Series, length: int) -> pd.Series:
    """Simple moving average — the plain average of the last `length` values."""
    return series.rolling(length, min_periods=length).mean()


def ema(series: pd.Series, length: int) -> pd.Series:
    """
    Exponential moving average — weights recent bars more heavily.
    Reacts faster than SMA, which means earlier signals but more false ones.
    """
    return series.ewm(span=length, adjust=False, min_periods=length).mean()


def wilder_ma(series: pd.Series, length: int) -> pd.Series:
    """
    Wilder's smoothing (used inside RSI / ATR / ADX).
    It's an EMA with alpha = 1/length instead of 2/(length+1).
    Using the wrong one is the single most common reason a home-made RSI
    doesn't match TradingView's.
    """
    return series.ewm(alpha=1.0 / length, adjust=False, min_periods=length).mean()


# ----------------------------------------------------------------------------
# Momentum / oscillators
# ----------------------------------------------------------------------------

def rsi(close: pd.Series, length: int = 14) -> pd.Series:
    """
    Relative Strength Index, 0-100, Wilder's original formulation.

    Plain English: of the recent price moves, what share were upward?
    Above 70 = lots of buying lately ("overbought").
    Below 30 = lots of selling lately ("oversold").

    Reality check: "overbought" does not mean "about to fall". In a strong
    trend RSI can sit above 70 for weeks. That's why the backtester exists.
    """
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)

    avg_gain = wilder_ma(gain, length)
    avg_loss = wilder_ma(loss, length)

    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))
    # avg_loss == 0 means nothing but gains -> RSI is exactly 100
    out = out.where(avg_loss != 0.0, 100.0)
    out = out.where(avg_gain != 0.0, out.where(avg_loss == 0.0, 0.0))
    return out


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """
    MACD = fast EMA - slow EMA. Signal = EMA of MACD. Hist = MACD - Signal.

    Plain English: measures whether short-term momentum is pulling away from
    long-term momentum. Histogram flipping positive is a classic bullish cue.
    """
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return pd.DataFrame({
        "macd": macd_line,
        "signal": signal_line,
        "hist": macd_line - signal_line,
    })


def stochastic(df: pd.DataFrame, k: int = 14, d: int = 3, smooth: int = 3) -> pd.DataFrame:
    """
    Stochastic oscillator: where does the current close sit inside the recent
    high-low range? 100 = at the top of the range, 0 = at the bottom.
    """
    lowest = df["low"].rolling(k, min_periods=k).min()
    highest = df["high"].rolling(k, min_periods=k).max()
    rng = (highest - lowest).replace(0.0, np.nan)
    raw_k = 100.0 * (df["close"] - lowest) / rng
    k_line = raw_k.rolling(smooth, min_periods=smooth).mean()
    return pd.DataFrame({"k": k_line, "d": k_line.rolling(d, min_periods=d).mean()})


def roc(close: pd.Series, length: int = 12) -> pd.Series:
    """Rate of change, in percent, over `length` bars."""
    return 100.0 * (close / close.shift(length) - 1.0)


# ----------------------------------------------------------------------------
# Volatility
# ----------------------------------------------------------------------------

def true_range(df: pd.DataFrame) -> pd.Series:
    """The largest of: today's range, gap up from yesterday, gap down."""
    prev_close = df["close"].shift(1)
    return pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)


def atr(df: pd.DataFrame, length: int = 14) -> pd.Series:
    """
    Average True Range — average size of a bar, in price units.

    This is the most useful "boring" indicator you have. Use it to size stops:
    a 2*ATR stop adapts automatically to calm vs. violent markets, whereas a
    flat "5% stop" gets shaken out constantly in high volatility.
    """
    return wilder_ma(true_range(df), length)


def bollinger(close: pd.Series, length: int = 20, mult: float = 2.0) -> pd.DataFrame:
    """
    Bollinger Bands: a moving average plus/minus `mult` standard deviations.
    Bands squeeze when the market is quiet and expand when it's wild.
    %B tells you where price sits: 0 = lower band, 1 = upper band.
    """
    mid = sma(close, length)
    sd = close.rolling(length, min_periods=length).std(ddof=0)
    upper, lower = mid + mult * sd, mid - mult * sd
    width = (upper - lower) / mid.replace(0.0, np.nan)
    pct_b = (close - lower) / (upper - lower).replace(0.0, np.nan)
    return pd.DataFrame({
        "mid": mid, "upper": upper, "lower": lower,
        "width": width, "pct_b": pct_b,
    })


def realized_vol(close: pd.Series, length: int = 20, bars_per_year: int = 8760) -> pd.Series:
    """Annualized standard deviation of log returns — 'how bumpy is this ride'."""
    logret = np.log(close / close.shift(1))
    return logret.rolling(length, min_periods=length).std(ddof=0) * np.sqrt(bars_per_year)


# ----------------------------------------------------------------------------
# Trend strength
# ----------------------------------------------------------------------------

def adx(df: pd.DataFrame, length: int = 14) -> pd.DataFrame:
    """
    ADX measures trend STRENGTH, not direction. Above ~25 usually means
    "a real trend is happening"; below ~20 means "chop, mean-reversion weather".

    Great as a regime filter: run trend strategies only when ADX is high, run
    mean-reversion strategies only when it's low.
    """
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)

    atr_ = wilder_ma(true_range(df), length).replace(0.0, np.nan)
    plus_di = 100.0 * wilder_ma(plus_dm, length) / atr_
    minus_di = 100.0 * wilder_ma(minus_dm, length) / atr_
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan)
    return pd.DataFrame({"adx": wilder_ma(dx, length), "plus_di": plus_di, "minus_di": minus_di})


# ----------------------------------------------------------------------------
# Volume
# ----------------------------------------------------------------------------

def obv(df: pd.DataFrame) -> pd.Series:
    """On-Balance Volume: running total of volume, signed by the day's direction."""
    sign = np.sign(df["close"].diff().fillna(0.0))
    return (sign * df["volume"]).cumsum()


def volume_zscore(df: pd.DataFrame, length: int = 20) -> pd.Series:
    """
    How unusual is today's volume, in standard deviations?
    A z-score above 2 means something actually happened — news, a whale, a
    liquidation cascade. Volume spikes are the closest thing to a free signal.
    """
    v = df["volume"]
    mean = v.rolling(length, min_periods=length).mean()
    sd = v.rolling(length, min_periods=length).std(ddof=0).replace(0.0, np.nan)
    return (v - mean) / sd


def vwap_rolling(df: pd.DataFrame, length: int = 20) -> pd.Series:
    """Rolling volume-weighted average price — the 'fair value' big traders watch."""
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    pv = (tp * df["volume"]).rolling(length, min_periods=length).sum()
    vv = df["volume"].rolling(length, min_periods=length).sum().replace(0.0, np.nan)
    return pv / vv


# ----------------------------------------------------------------------------
# Support / resistance
# ----------------------------------------------------------------------------

def donchian(df: pd.DataFrame, length: int = 20) -> pd.DataFrame:
    """
    Donchian channel — highest high and lowest low of the last N bars.
    This is the whole basis of the famous Turtle Traders system: buy when
    price breaks above the N-bar high.

    NOTE: shifted by 1 bar so the current bar's own high can't be part of the
    level it is supposedly breaking. Forgetting that shift is a classic
    lookahead bug that makes breakout backtests look magical.
    """
    return pd.DataFrame({
        "upper": df["high"].rolling(length, min_periods=length).max().shift(1),
        "lower": df["low"].rolling(length, min_periods=length).min().shift(1),
    })


# ----------------------------------------------------------------------------
# Convenience: compute a standard bundle for charting
# ----------------------------------------------------------------------------

def compute_bundle(df: pd.DataFrame, params: dict | None = None) -> pd.DataFrame:
    """Attach a standard set of indicators to df for the charting UI."""
    p = {
        "rsi": 14, "ema_fast": 20, "ema_slow": 50, "ema_trend": 200,
        "bb_len": 20, "bb_mult": 2.0, "atr": 14, "adx": 14, "vol_z": 20,
    }
    if params:
        p.update(params)

    out = df.copy()
    out["rsi"] = rsi(df["close"], p["rsi"])
    out["ema_fast"] = ema(df["close"], p["ema_fast"])
    out["ema_slow"] = ema(df["close"], p["ema_slow"])
    out["ema_trend"] = ema(df["close"], p["ema_trend"])

    m = macd(df["close"])
    out["macd"], out["macd_signal"], out["macd_hist"] = m["macd"], m["signal"], m["hist"]

    b = bollinger(df["close"], p["bb_len"], p["bb_mult"])
    out["bb_upper"], out["bb_mid"], out["bb_lower"] = b["upper"], b["mid"], b["lower"]
    out["bb_pct_b"], out["bb_width"] = b["pct_b"], b["width"]

    out["atr"] = atr(df, p["atr"])
    out["atr_pct"] = 100.0 * out["atr"] / df["close"]

    a = adx(df, p["adx"])
    out["adx"], out["plus_di"], out["minus_di"] = a["adx"], a["plus_di"], a["minus_di"]

    out["vol_z"] = volume_zscore(df, p["vol_z"])
    out["vwap"] = vwap_rolling(df, 20)
    return out
