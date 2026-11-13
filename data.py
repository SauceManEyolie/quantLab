"""
data.py — free OHLCV candle data, no API keys, no paid tiers.

Sources are tried in order until one works:
    1. Binance          — 1000 candles/request, deepest history, fastest.
    2. Binance.US       — same API, works when the .com domain is geo-blocked.
    3. Coinbase Exchange— 300 candles/request, always reachable from the US.
    4. Kraken           — 720 candles, recent history only. Last resort.

Everything is cached to disk as CSV, so the second run of a backtest is instant
and you stop hammering public endpoints (which is how you get rate-limited).

All timestamps are unix seconds, UTC. All candles are CLOSED candles: the
still-forming current candle is dropped, because trading on a bar that hasn't
finished yet is a classic way to fool yourself in a backtest.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from typing import Iterable

import numpy as np
import pandas as pd

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
os.makedirs(CACHE_DIR, exist_ok=True)

USER_AGENT = "QuantLab/1.0 (personal research tool)"
COLUMNS = ["time", "open", "high", "low", "close", "volume"]

# Timeframe -> seconds
TIMEFRAMES = {
    "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600,
    "12h": 43200, "1d": 86400, "3d": 259200, "1w": 604800,
}

# Symbols the UI offers. Base asset -> quote is always USD/USDT depending on venue.
# Any ticker the exchanges list will work — this is just what the dropdowns
# suggest. Type anything else into the symbol box and it'll be fetched.
DEFAULT_SYMBOLS = [
    # majors
    "BTC", "ETH", "SOL", "XRP", "BNB", "ADA", "AVAX", "DOT", "LINK", "LTC",
    "BCH", "XLM", "TRX", "TON", "ICP", "ETC", "HBAR", "VET", "ALGO", "ATOM",
    # layer 2s and infrastructure
    "ARB", "OP", "MATIC", "IMX", "STRK", "MNT", "STX", "NEAR", "APT", "SUI",
    "SEI", "TIA", "INJ", "KAS", "FIL", "GRT", "AR",
    # defi
    "UNI", "AAVE", "MKR", "LDO", "CRV", "SNX", "RUNE", "JUP", "PYTH", "ONDO",
    "ENA", "JTO", "W",
    # ai / depin
    "RNDR", "FET", "TAO", "AKT",
    # exchange-listed memecoins — real liquidity, real history, still volatile
    "DOGE", "SHIB", "PEPE", "BONK", "WIF", "FLOKI",
    # gaming / metaverse
    "SAND", "MANA", "AXS", "GALA", "APE", "BLUR",
]


class DataError(RuntimeError):
    pass


# ----------------------------------------------------------------------------
# Low-level HTTP
# ----------------------------------------------------------------------------

def _get_json(url: str, timeout: int = 20):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


# ----------------------------------------------------------------------------
# Source: Binance (and Binance.US)
# ----------------------------------------------------------------------------

_BINANCE_TF = {
    "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m", "1h": "1h",
    "2h": "2h", "4h": "4h", "6h": "6h", "12h": "12h", "1d": "1d",
    "3d": "3d", "1w": "1w",
}


def _fetch_binance(host: str, base: str, tf: str, start_ms: int, end_ms: int) -> pd.DataFrame:
    if tf not in _BINANCE_TF:
        raise DataError(f"{host} does not support timeframe {tf}")
    symbol = f"{base.upper()}USDT"
    rows, cursor = [], start_ms
    step_ms = TIMEFRAMES[tf] * 1000

    while cursor < end_ms:
        q = urllib.parse.urlencode({
            "symbol": symbol, "interval": _BINANCE_TF[tf],
            "startTime": cursor, "endTime": end_ms, "limit": 1000,
        })
        batch = _get_json(f"https://{host}/api/v3/klines?{q}")
        if not batch:
            break
        for k in batch:
            rows.append([int(k[0]) // 1000, float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])])
        last_open = int(batch[-1][0])
        cursor = last_open + step_ms
        if len(batch) < 1000:
            break
        time.sleep(0.12)  # stay well under the public rate limit

    if not rows:
        raise DataError(f"{host} returned no candles for {symbol} {tf}")
    return pd.DataFrame(rows, columns=COLUMNS)


# ----------------------------------------------------------------------------
# Source: Coinbase Exchange
# ----------------------------------------------------------------------------

_COINBASE_GRANULARITY = {60, 300, 900, 3600, 21600, 86400}


def _fetch_coinbase(base: str, tf: str, start_s: int, end_s: int) -> pd.DataFrame:
    """
    Coinbase only supports 6 granularities. For anything else we fetch the
    largest supported granularity that divides it evenly and resample up.
    """
    want = TIMEFRAMES[tf]
    native = max((g for g in _COINBASE_GRANULARITY if want % g == 0), default=None)
    if native is None:
        raise DataError(f"Coinbase cannot build timeframe {tf}")

    product = f"{base.upper()}-USD"
    rows, cursor = [], start_s
    span = native * 300  # 300 candles per request

    while cursor < end_s:
        chunk_end = min(cursor + span, end_s)
        q = urllib.parse.urlencode({
            "granularity": native,
            "start": pd.to_datetime(cursor, unit="s", utc=True).isoformat().replace("+00:00", "Z"),
            "end": pd.to_datetime(chunk_end, unit="s", utc=True).isoformat().replace("+00:00", "Z"),
        })
        batch = _get_json(f"https://api.exchange.coinbase.com/products/{product}/candles?{q}")
        # Coinbase returns [time, low, high, open, close, volume] — note the order!
        for c in batch:
            rows.append([int(c[0]), float(c[3]), float(c[2]), float(c[1]), float(c[4]), float(c[5])])
        cursor = chunk_end
        time.sleep(0.16)

    if not rows:
        raise DataError(f"Coinbase returned no candles for {product}")
    df = pd.DataFrame(rows, columns=COLUMNS).drop_duplicates("time").sort_values("time")
    return resample(df, native, want) if native != want else df


# ----------------------------------------------------------------------------
# Source: Kraken
# ----------------------------------------------------------------------------

_KRAKEN_TF = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240, "1d": 1440, "1w": 10080}
_KRAKEN_ALIAS = {"BTC": "XBT"}


def _fetch_kraken(base: str, tf: str, start_s: int) -> pd.DataFrame:
    if tf not in _KRAKEN_TF:
        raise DataError(f"Kraken does not support timeframe {tf}")
    pair = f"{_KRAKEN_ALIAS.get(base.upper(), base.upper())}USD"
    q = urllib.parse.urlencode({"pair": pair, "interval": _KRAKEN_TF[tf], "since": start_s})
    payload = _get_json(f"https://api.kraken.com/0/public/OHLC?{q}")
    if payload.get("error"):
        raise DataError(f"Kraken error: {payload['error']}")
    result = payload.get("result", {})
    key = next((k for k in result if k != "last"), None)
    if key is None:
        raise DataError("Kraken returned no data")
    rows = [[int(c[0]), float(c[1]), float(c[2]), float(c[3]), float(c[4]), float(c[6])]
            for c in result[key]]
    return pd.DataFrame(rows, columns=COLUMNS)


# ----------------------------------------------------------------------------
# Resampling
# ----------------------------------------------------------------------------

def resample(df: pd.DataFrame, from_seconds: int, to_seconds: int) -> pd.DataFrame:
    """Aggregate small candles into bigger ones. open=first, high=max, low=min, close=last."""
    if to_seconds % from_seconds != 0:
        raise DataError(f"cannot resample {from_seconds}s into {to_seconds}s")
    d = df.copy()
    d["bucket"] = (d["time"] // to_seconds) * to_seconds
    g = d.groupby("bucket").agg(
        open=("open", "first"), high=("high", "max"),
        low=("low", "min"), close=("close", "last"), volume=("volume", "sum"),
    ).reset_index().rename(columns={"bucket": "time"})
    return g[COLUMNS]


# ----------------------------------------------------------------------------
# Cache
# ----------------------------------------------------------------------------

def _cache_path(base: str, tf: str) -> str:
    return os.path.join(CACHE_DIR, f"{base.upper()}_{tf}.csv")


def _read_cache(base: str, tf: str) -> pd.DataFrame | None:
    path = _cache_path(base, tf)
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_csv(path)
        return df[COLUMNS] if set(COLUMNS).issubset(df.columns) else None
    except Exception:
        return None


def _write_cache(base: str, tf: str, df: pd.DataFrame) -> None:
    df[COLUMNS].to_csv(_cache_path(base, tf), index=False)


def clear_cache(base: str | None = None) -> int:
    n = 0
    for f in os.listdir(CACHE_DIR):
        if f.endswith(".csv") and (base is None or f.upper().startswith(base.upper() + "_")):
            os.remove(os.path.join(CACHE_DIR, f))
            n += 1
    return n


# ----------------------------------------------------------------------------
# Public entry point
# ----------------------------------------------------------------------------

def _clean(df: pd.DataFrame, tf: str) -> pd.DataFrame:
    """Sort, dedupe, drop the unfinished candle, sanity-check OHLC relationships."""
    d = df.copy()
    d = d.dropna(subset=COLUMNS)
    d = d.drop_duplicates(subset="time", keep="last").sort_values("time")

    # Drop the currently-forming candle — it is incomplete and would leak
    # partial future information into the final bar of a backtest.
    step = TIMEFRAMES[tf]
    now_bucket = (int(time.time()) // step) * step
    d = d[d["time"] < now_bucket]

    # Basic integrity: high must be the max, low the min.
    d = d[(d["high"] >= d["low"]) & (d["high"] >= d["open"]) & (d["high"] >= d["close"]) &
          (d["low"] <= d["open"]) & (d["low"] <= d["close"]) & (d["close"] > 0)]

    return d.reset_index(drop=True)


def get_candles(base: str, tf: str = "1h", days: int = 365,
                use_cache: bool = True, sources: Iterable[str] | None = None) -> pd.DataFrame:
    """
    Return a DataFrame of closed candles: time, open, high, low, close, volume.

    base  — asset ticker, e.g. "BTC"
    tf    — timeframe key from TIMEFRAMES, e.g. "1h"
    days  — how far back to go
    """
    if tf not in TIMEFRAMES:
        raise DataError(f"unknown timeframe {tf!r}; try one of {sorted(TIMEFRAMES)}")

    # Demo mode: fabricated data, for trying the UI offline. Clearly flagged in
    # the interface so nobody mistakes a random walk for the actual market.
    if os.environ.get("QUANTLAB_DEMO") == "1":
        n = min(6000, max(300, int(days * 86400 / TIMEFRAMES[tf])))
        # zlib.crc32, not hash() — Python randomizes string hashing per process,
        # so hash() would give a different fake price series after every restart
        # and paper-trading positions would jump in value for no reason.
        seed = zlib.crc32(base.upper().encode()) % 9999
        base_px = {"BTC": 60000, "ETH": 3000, "SOL": 140}.get(base.upper(), 50 + seed % 400)
        return _clean(synthetic(n, tf, seed=seed, start_price=base_px), tf)

    now = int(time.time())
    start = now - days * 86400

    if use_cache:
        cached = _read_cache(base, tf)
        if cached is not None and len(cached) > 0:
            covered_from = cached["time"].min()
            newest = cached["time"].max()
            fresh_enough = (now - newest) < TIMEFRAMES[tf] * 2
            if covered_from <= start + TIMEFRAMES[tf] and fresh_enough:
                out = _clean(cached[cached["time"] >= start], tf)
                if len(out) > 0:
                    return out
            # Partial cache: only fetch the gap at the right-hand edge.
            if covered_from <= start + TIMEFRAMES[tf]:
                new = _download(base, tf, newest + 1, now, sources)
                merged = pd.concat([cached, new], ignore_index=True)
                merged = _clean(merged, tf)
                _write_cache(base, tf, merged)
                return merged[merged["time"] >= start].reset_index(drop=True)

    fetched = _download(base, tf, start, now, sources)
    cleaned = _clean(fetched, tf)
    if use_cache and len(cleaned):
        _write_cache(base, tf, cleaned)
    return cleaned


def _download(base: str, tf: str, start_s: int, end_s: int,
              sources: Iterable[str] | None = None) -> pd.DataFrame:
    order = list(sources) if sources else ["binance", "binanceus", "coinbase", "kraken"]
    errors = []
    for src in order:
        try:
            if src == "binance":
                return _fetch_binance("api.binance.com", base, tf, start_s * 1000, end_s * 1000)
            if src == "binanceus":
                return _fetch_binance("api.binance.us", base, tf, start_s * 1000, end_s * 1000)
            if src == "coinbase":
                return _fetch_coinbase(base, tf, start_s, end_s)
            if src == "kraken":
                return _fetch_kraken(base, tf, start_s)
        except (urllib.error.URLError, urllib.error.HTTPError, DataError, ValueError, TimeoutError) as e:
            errors.append(f"{src}: {type(e).__name__} {e}")
            continue
    raise DataError("all data sources failed —\n  " + "\n  ".join(errors))


def latest_price(base: str) -> float | None:
    """Spot price right now, for the live ticker in the UI."""
    if os.environ.get("QUANTLAB_DEMO") == "1":
        try:
            return float(get_candles(base, "1h", 7)["close"].iloc[-1])
        except Exception:
            return None
    for url, path in [
        (f"https://api.binance.com/api/v3/ticker/price?symbol={base.upper()}USDT", ("price",)),
        (f"https://api.binance.us/api/v3/ticker/price?symbol={base.upper()}USDT", ("price",)),
        (f"https://api.exchange.coinbase.com/products/{base.upper()}-USD/ticker", ("price",)),
    ]:
        try:
            payload = _get_json(url, timeout=8)
            for k in path:
                payload = payload[k]
            return float(payload)
        except Exception:
            continue
    return None


# ----------------------------------------------------------------------------
# Offline synthetic data — for testing the engine without a network connection
# ----------------------------------------------------------------------------

def synthetic(n: int = 2000, tf: str = "1h", seed: int = 7,
              start_price: float = 30000.0, drift: float = 0.00005,
              vol: float = 0.012) -> pd.DataFrame:
    """
    Generate a realistic-looking random price series (geometric Brownian motion
    with volatility clustering). Used by the test suite so engine correctness
    can be verified with zero network access.
    """
    rng = np.random.default_rng(seed)
    step = TIMEFRAMES[tf]
    vol_state = np.abs(rng.normal(1.0, 0.25, n)).cumsum() / np.arange(1, n + 1)
    rets = rng.normal(drift, vol, n) * vol_state
    close = start_price * np.exp(np.cumsum(rets))
    open_ = np.concatenate([[start_price], close[:-1]])
    noise = np.abs(rng.normal(0, vol * 0.6, n)) * close
    high = np.maximum(open_, close) + noise
    low = np.minimum(open_, close) - noise
    low = np.maximum(low, 1e-8)
    volume = np.abs(rng.lognormal(3.0, 0.6, n)) * 100
    end = (int(time.time()) // step) * step
    times = np.arange(end - n * step, end, step)
    return pd.DataFrame({
        "time": times.astype(np.int64), "open": open_, "high": high,
        "low": low, "close": close, "volume": volume,
    })
