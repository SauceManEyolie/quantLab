"""
engine.py — the backtest engine.

THE ONE RULE THIS FILE EXISTS TO ENFORCE
----------------------------------------
A signal computed from bar i's CLOSE is executed at bar i+1's OPEN.

You never get to buy at the price that made you want to buy. Every "amazing"
home-made backtest that turns $1k into $4M has broken that rule somewhere.
Here it is structural: the loop physically cannot fill an order on the same bar
that generated the signal.

Also modelled honestly:
  * trading fees on both sides of every trade
  * slippage (you buy a touch above and sell a touch below the quoted price)
  * stops checked against the bar's actual high/low, not its close
  * when a stop and a target could both have been hit inside one bar, we assume
    the STOP hit first — the pessimistic assumption, because we cannot see
    inside the bar and optimism here is how people blow up accounts

Positions are position-target based: the strategy emits a desired position in
{1 = long, 0 = flat, -1 = short} for each bar, and the engine reconciles.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from typing import Any

import numpy as np
import pandas as pd

SECONDS_PER_YEAR = 31_557_600


# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------

@dataclass
class BacktestConfig:
    initial_cash: float = 10_000.0
    fee_bps: float = 10.0          # 10 bps = 0.10% per side (typical retail taker fee)
    slippage_bps: float = 5.0      # 5 bps = 0.05% adverse fill
    size_pct: float = 100.0        # % of equity committed per trade
    allow_short: bool = False

    # Risk exits — set to 0 to disable
    stop_loss_pct: float = 0.0     # e.g. 5.0 = exit if 5% against you
    take_profit_pct: float = 0.0
    trailing_stop_pct: float = 0.0
    atr_stop_mult: float = 0.0     # if > 0, stop = entry -/+ mult * ATR (overrides stop_loss_pct)
    max_bars_held: int = 0         # force exit after N bars, 0 = never

    # After a risk exit fires, wait for the signal to go flat before re-entering.
    # Without this you get "stopped out, buy back immediately, stopped out again"
    # loops that shred an account with fees.
    reenter_after_stop: bool = False

    timeframe_seconds: int = 3600  # used only for annualizing metrics


@dataclass
class Trade:
    side: str                 # "long" | "short"
    entry_time: int
    entry_price: float
    exit_time: int
    exit_price: float
    units: float
    pnl: float
    pnl_pct: float            # return on the capital committed to THIS trade
    fees: float
    bars_held: int
    exit_reason: str          # "signal" | "stop" | "target" | "trail" | "timeout" | "end"
    mae_pct: float = 0.0      # worst unrealized drawdown during the trade
    mfe_pct: float = 0.0      # best unrealized gain during the trade


# ----------------------------------------------------------------------------
# The engine
# ----------------------------------------------------------------------------

def run_backtest(df: pd.DataFrame, signal: pd.Series, cfg: BacktestConfig,
                 atr_series: pd.Series | None = None) -> dict[str, Any]:
    """
    df     — OHLCV with columns time, open, high, low, close, volume
    signal — desired position per bar, values in {-1, 0, 1}, same index as df
    """
    d = df.reset_index(drop=True)
    sig = pd.Series(signal).reset_index(drop=True).fillna(0.0).clip(-1, 1)
    atr_arr = (pd.Series(atr_series).reset_index(drop=True).to_numpy(float)
               if atr_series is not None else np.full(len(d), np.nan))

    if not cfg.allow_short:
        sig = sig.clip(lower=0)

    t = d["time"].to_numpy(np.int64)
    o, h, l, c = (d[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    s = sig.to_numpy(float)
    n = len(d)

    fee_rate = cfg.fee_bps / 10_000.0
    slip = cfg.slippage_bps / 10_000.0
    size_frac = max(0.0, min(cfg.size_pct, 100.0)) / 100.0

    cash = cfg.initial_cash
    units = 0.0                  # >0 long, <0 short, 0 flat
    position = 0                 # -1 / 0 / 1
    pending: int | None = None   # position we intend to hold, fill at next open

    entry_price = entry_time = entry_bar = 0.0
    entry_fees = 0.0
    peak_price = trough_price = 0.0
    stop_px = target_px = 0.0

    blocked_dir = 0              # direction we're locked out of after a risk exit
    trades: list[Trade] = []
    equity = np.empty(n, dtype=float)
    exposure = np.zeros(n, dtype=float)
    markers: list[dict] = []

    def buy_fill(px: float) -> float:
        return px * (1.0 + slip)

    def sell_fill(px: float) -> float:
        return px * (1.0 - slip)

    def open_position(direction: int, px: float, bar: int) -> None:
        nonlocal cash, units, position, entry_price, entry_time, entry_bar
        nonlocal entry_fees, peak_price, trough_price, stop_px, target_px

        eq = cash  # flat, so equity == cash
        # You cannot spend 100% of your account on the asset AND also pay the
        # fee — the fee comes out of the same pocket. Scaling the notional down
        # keeps cash from going negative, i.e. keeps us off accidental margin.
        notional = eq * size_frac / (1.0 + fee_rate)
        if notional <= 0:
            return
        fill = buy_fill(px) if direction > 0 else sell_fill(px)
        qty = notional / fill
        fee = notional * fee_rate

        if direction > 0:
            cash -= notional + fee
            units = qty
        else:
            cash += notional - fee
            units = -qty

        position = direction
        entry_price, entry_time, entry_bar, entry_fees = fill, t[bar], bar, fee
        peak_price = trough_price = fill

        # Pre-compute the exit levels for this trade.
        a = atr_arr[bar] if bar < len(atr_arr) else np.nan
        if cfg.atr_stop_mult > 0 and np.isfinite(a) and a > 0:
            dist = cfg.atr_stop_mult * a
            stop_px = fill - dist if direction > 0 else fill + dist
        elif cfg.stop_loss_pct > 0:
            k = cfg.stop_loss_pct / 100.0
            stop_px = fill * (1 - k) if direction > 0 else fill * (1 + k)
        else:
            stop_px = 0.0

        if cfg.take_profit_pct > 0:
            k = cfg.take_profit_pct / 100.0
            target_px = fill * (1 + k) if direction > 0 else fill * (1 - k)
        else:
            target_px = 0.0

        markers.append({"time": int(t[bar]), "type": "entry", "side": "long" if direction > 0 else "short",
                        "price": float(fill)})

    def close_position(px: float, bar: int, reason: str) -> None:
        nonlocal cash, units, position, entry_fees
        if position == 0:
            return
        fill = sell_fill(px) if position > 0 else buy_fill(px)
        notional = abs(units) * fill
        fee = notional * fee_rate

        if position > 0:
            cash += notional - fee
            gross = (fill - entry_price) * units
        else:
            cash -= notional + fee
            gross = (entry_price - fill) * abs(units)

        total_fees = entry_fees + fee
        pnl = gross - total_fees
        committed = entry_price * abs(units)
        pnl_pct = 100.0 * pnl / committed if committed else 0.0

        if position > 0:
            mae = 100.0 * (trough_price / entry_price - 1.0)
            mfe = 100.0 * (peak_price / entry_price - 1.0)
        else:
            mae = 100.0 * (1.0 - peak_price / entry_price)
            mfe = 100.0 * (1.0 - trough_price / entry_price)

        trades.append(Trade(
            side="long" if position > 0 else "short",
            entry_time=int(entry_time), entry_price=float(entry_price),
            exit_time=int(t[bar]), exit_price=float(fill),
            units=float(abs(units)), pnl=float(pnl), pnl_pct=float(pnl_pct),
            fees=float(total_fees), bars_held=int(bar - entry_bar),
            exit_reason=reason, mae_pct=float(mae), mfe_pct=float(mfe),
        ))
        markers.append({"time": int(t[bar]), "type": "exit", "side": "long" if position > 0 else "short",
                        "price": float(fill), "reason": reason, "pnl": float(pnl)})
        units, position, entry_fees = 0.0, 0, 0.0

    # ---- main loop -------------------------------------------------------
    for i in range(n):
        # 1. Fill any order that was decided on the previous bar's close.
        if pending is not None and pending != position:
            if position != 0:
                close_position(o[i], i, "signal")
            if pending != 0:
                open_position(pending, o[i], i)
            pending = None

        # 2. Now live through bar i. Update excursions, then check exits
        #    against the bar's real high/low.
        if position != 0:
            peak_price = max(peak_price, h[i])
            trough_price = min(trough_price, l[i])

            exit_px, reason = None, ""
            if position > 0:
                trail_px = (peak_price * (1 - cfg.trailing_stop_pct / 100.0)
                            if cfg.trailing_stop_pct > 0 else 0.0)
                hard = max(stop_px, trail_px)
                # pessimistic: stop is checked before target
                if hard > 0 and l[i] <= hard:
                    exit_px, reason = min(hard, o[i]), ("trail" if trail_px >= stop_px and trail_px > 0 else "stop")
                elif target_px > 0 and h[i] >= target_px:
                    exit_px, reason = max(target_px, o[i]), "target"
            else:
                trail_px = (trough_price * (1 + cfg.trailing_stop_pct / 100.0)
                            if cfg.trailing_stop_pct > 0 else math.inf)
                hard = min(stop_px if stop_px > 0 else math.inf, trail_px)
                if hard < math.inf and h[i] >= hard:
                    exit_px, reason = max(hard, o[i]), ("trail" if trail_px <= (stop_px or math.inf) else "stop")
                elif target_px > 0 and l[i] <= target_px:
                    exit_px, reason = min(target_px, o[i]), "target"

            if exit_px is None and cfg.max_bars_held > 0 and (i - entry_bar) >= cfg.max_bars_held:
                exit_px, reason = c[i], "timeout"

            if exit_px is not None:
                # Only ADVERSE exits lock the direction out. Hitting your target
                # or timing out is a neutral event — re-entering is legitimate.
                if not cfg.reenter_after_stop and reason in ("stop", "trail"):
                    blocked_dir = position
                close_position(float(exit_px), i, reason)
                pending = None  # don't immediately re-enter on the same stale signal

        # 3. Mark to market at the close.
        equity[i] = cash + units * c[i]
        exposure[i] = 1.0 if position != 0 else 0.0

        # 4. Decide what we want to hold going into the next bar.
        if i < n - 1:
            want = int(s[i])
            # A risk exit locks out that direction until the signal goes flat,
            # so we can't get whipsawed straight back into the same losing trade.
            if blocked_dir != 0:
                if want == blocked_dir:
                    want = position
                else:
                    blocked_dir = 0
            if want != position:
                pending = want

    # Close anything still open at the final bar.
    if position != 0:
        close_position(c[n - 1], n - 1, "end")
        equity[n - 1] = cash

    stats = _metrics(equity, trades, c, t, cfg, exposure)
    return {
        "equity": equity.tolist(),
        "times": t.tolist(),
        "trades": [asdict(x) for x in trades],
        "markers": markers,
        "stats": stats,
        "config": asdict(cfg),
    }


# ----------------------------------------------------------------------------
# Performance metrics
# ----------------------------------------------------------------------------

def _safe(x: float) -> float:
    return float(x) if np.isfinite(x) else 0.0


def _metrics(equity: np.ndarray, trades: list[Trade], close: np.ndarray,
             times: np.ndarray, cfg: BacktestConfig, exposure: np.ndarray) -> dict[str, Any]:
    n = len(equity)
    if n < 2:
        return {"error": "not enough data"}

    start_eq, end_eq = cfg.initial_cash, equity[-1]
    total_return = 100.0 * (end_eq / start_eq - 1.0)

    span_seconds = max(1, int(times[-1] - times[0]))
    years = span_seconds / SECONDS_PER_YEAR
    cagr = 100.0 * ((end_eq / start_eq) ** (1 / years) - 1.0) if years > 0 and end_eq > 0 else 0.0

    bars_per_year = SECONDS_PER_YEAR / max(1, cfg.timeframe_seconds)
    rets = np.diff(equity) / np.where(equity[:-1] == 0, np.nan, equity[:-1])
    rets = np.nan_to_num(rets, nan=0.0, posinf=0.0, neginf=0.0)

    sd = rets.std(ddof=1) if len(rets) > 1 else 0.0
    sharpe = (rets.mean() / sd * math.sqrt(bars_per_year)) if sd > 0 else 0.0
    downside = rets[rets < 0]
    dsd = downside.std(ddof=1) if len(downside) > 1 else 0.0
    sortino = (rets.mean() / dsd * math.sqrt(bars_per_year)) if dsd > 0 else 0.0

    # Max drawdown: worst peak-to-trough fall in account value.
    # This is the number that decides whether you can actually stick with a
    # strategy. A 60% drawdown is mathematically survivable and psychologically
    # almost never survived.
    running_peak = np.maximum.accumulate(equity)
    dd = (equity - running_peak) / np.where(running_peak == 0, np.nan, running_peak)
    dd = np.nan_to_num(dd, nan=0.0)
    max_dd = 100.0 * dd.min()
    dd_idx = int(dd.argmin())
    peak_idx = int(np.argmax(equity[:dd_idx + 1])) if dd_idx > 0 else 0

    # longest time spent underwater, in bars
    underwater, longest, cur = dd < -1e-12, 0, 0
    for u in underwater:
        cur = cur + 1 if u else 0
        longest = max(longest, cur)

    # Buy & hold benchmark — the bar every strategy must clear.
    bh_end = start_eq * (close[-1] / close[0])
    bh_return = 100.0 * (close[-1] / close[0] - 1.0)
    bh_peak = np.maximum.accumulate(close)
    bh_dd = 100.0 * float(((close - bh_peak) / bh_peak).min())

    pnls = np.array([x.pnl for x in trades], dtype=float)
    wins, losses = pnls[pnls > 0], pnls[pnls < 0]
    gross_win, gross_loss = float(wins.sum()), float(-losses.sum())

    # Consecutive win/loss streaks
    best_streak = worst_streak = cur_w = cur_l = 0
    for p in pnls:
        if p > 0:
            cur_w, cur_l = cur_w + 1, 0
        elif p < 0:
            cur_l, cur_w = cur_l + 1, 0
        best_streak, worst_streak = max(best_streak, cur_w), max(worst_streak, cur_l)

    win_rate = 100.0 * len(wins) / len(pnls) if len(pnls) else 0.0
    avg_win = float(wins.mean()) if len(wins) else 0.0
    avg_loss = float(losses.mean()) if len(losses) else 0.0
    expectancy = float(pnls.mean()) if len(pnls) else 0.0

    reasons: dict[str, int] = {}
    for tr in trades:
        reasons[tr.exit_reason] = reasons.get(tr.exit_reason, 0) + 1

    return {
        "final_equity": _safe(end_eq),
        "total_return_pct": _safe(total_return),
        "cagr_pct": _safe(cagr),
        "buy_hold_return_pct": _safe(bh_return),
        "buy_hold_final_equity": _safe(bh_end),
        "buy_hold_max_drawdown_pct": _safe(bh_dd),
        "alpha_pct": _safe(total_return - bh_return),
        "beat_buy_hold": bool(total_return > bh_return),
        "max_drawdown_pct": _safe(max_dd),
        "max_drawdown_start": int(times[peak_idx]),
        "max_drawdown_end": int(times[dd_idx]),
        "longest_drawdown_bars": int(longest),
        "sharpe": _safe(sharpe),
        "sortino": _safe(sortino),
        "calmar": _safe(cagr / abs(max_dd)) if max_dd < 0 else 0.0,
        "volatility_pct": _safe(sd * math.sqrt(bars_per_year) * 100.0),
        "num_trades": len(trades),
        "win_rate_pct": _safe(win_rate),
        "avg_win": _safe(avg_win),
        "avg_loss": _safe(avg_loss),
        "profit_factor": _safe(gross_win / gross_loss) if gross_loss > 0 else (999.0 if gross_win > 0 else 0.0),
        "expectancy": _safe(expectancy),
        "payoff_ratio": _safe(abs(avg_win / avg_loss)) if avg_loss else 0.0,
        "best_trade": _safe(pnls.max()) if len(pnls) else 0.0,
        "worst_trade": _safe(pnls.min()) if len(pnls) else 0.0,
        "max_consecutive_wins": int(best_streak),
        "max_consecutive_losses": int(worst_streak),
        "total_fees": _safe(sum(x.fees for x in trades)),
        "avg_bars_held": _safe(np.mean([x.bars_held for x in trades])) if trades else 0.0,
        "time_in_market_pct": _safe(100.0 * exposure.mean()),
        "exit_reasons": reasons,
        "bars": n,
        "years": _safe(years),
    }


def buy_and_hold_curve(df: pd.DataFrame, initial_cash: float) -> list[float]:
    c = df["close"].to_numpy(float)
    return (initial_cash * c / c[0]).tolist()
