"""
paper.py — paper trading at real live prices.

A backtest tells you whether a STRATEGY works. Paper trading tells you whether
YOU work: whether you actually take the signal when it comes, whether you hold
through a 15% drawdown, whether you cut winners early out of nervousness.
Those are different questions and the second one is where most people fail.

Two design choices make this more than a toy:

1. EVERY TRADE REQUIRES A WRITTEN REASON AND A CONVICTION RATING (1-5).
   You are forced to state, before you know the outcome, why you're doing this
   and how sure you are. Later the scorecard checks whether your 5-conviction
   trades actually outperformed your 2-conviction trades. If they don't, your
   confidence carries no information — which is the single most valuable and
   most unwelcome thing you can learn about your own trading.

2. EVERY TRADE IS STAMPED WITH WHAT THE SYSTEMATIC STRATEGY SAID AT THAT MOMENT.
   So you can separate "my discretion beat the system" from "I got lucky
   agreeing with it".

State lives in paper_state.json next to this file. Delete it to start over.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper_state.json")
DEFAULT_CASH = 10_000.0
DEFAULT_FEE_BPS = 10.0


class PaperError(RuntimeError):
    pass


# ----------------------------------------------------------------------------
# Persistence
# ----------------------------------------------------------------------------

def _blank(cash: float = DEFAULT_CASH) -> dict:
    return {
        "version": 1,
        "created": int(time.time()),
        "initial_cash": cash,
        "cash": cash,
        "fee_bps": DEFAULT_FEE_BPS,
        "positions": {},   # symbol -> {units, cost_basis, opened, reason, confidence, strategy_said}
        "trades": [],      # closed and partial sells, with realized P&L
        "log": [],         # every action, including buys
        "watchlist": ["BTC", "ETH", "SOL"],
        # Set once, applied to every planned trade. These four numbers are the
        # whole of retail risk management.
        "risk_profile": {
            "risk_pct": 2.0,          # % of the account you're willing to lose if the stop hits
            "stop_atr_mult": 2.0,     # stop distance = this many ATRs below entry
            "target_r": 2.0,          # take profit at this multiple of the amount risked
            "max_position_pct": 25.0,  # never let one position exceed this share of the account
        },
    }


def load() -> dict:
    if not os.path.exists(STATE_PATH):
        return _blank()
    try:
        with open(STATE_PATH) as f:
            s = json.load(f)
        for k, v in _blank().items():
            s.setdefault(k, v)
        return s
    except (json.JSONDecodeError, OSError):
        return _blank()


def save(state: dict) -> None:
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE_PATH)   # atomic — a crash mid-write can't corrupt your record


def reset(cash: float = DEFAULT_CASH) -> dict:
    s = _blank(cash)
    save(s)
    return s


# ----------------------------------------------------------------------------
# Trading
# ----------------------------------------------------------------------------

def _fee(state: dict, notional: float) -> float:
    return notional * (state.get("fee_bps", DEFAULT_FEE_BPS) / 10_000.0)


def buy(state: dict, symbol: str, usd: float, price: float,
        reason: str, confidence: int, strategy_said: str = "",
        stop_price: float | None = None, target_price: float | None = None) -> dict:
    """
    Spend `usd` of cash on `symbol` at the live `price`.

    The stop and target are stored WITH the position on purpose. A stop you
    decided on and then forgot is not a stop — it's a good intention. Keeping it
    on the record means the app can tell you how close you are to it, and means
    that later you can see whether you actually honoured your own rule.
    """
    symbol = symbol.upper()
    usd = float(usd)
    if usd <= 0:
        raise PaperError("amount must be positive")
    if not reason or len(reason.strip()) < 3:
        raise PaperError("write down why you're taking this trade — that's the whole point")
    confidence = max(1, min(5, int(confidence)))

    fee = _fee(state, usd)
    if usd + fee > state["cash"] + 1e-9:
        raise PaperError(f"not enough cash: need ${usd + fee:,.2f}, have ${state['cash']:,.2f}")

    units = usd / price
    state["cash"] -= usd + fee

    pos = state["positions"].get(symbol)
    if pos:
        # Averaging into an existing position: blend the cost basis.
        pos["cost_basis"] = (pos["cost_basis"] * pos["units"] + usd) / (pos["units"] + units)
        pos["units"] += units
        pos["fees"] = pos.get("fees", 0.0) + fee
        pos["adds"] = pos.get("adds", 0) + 1
        # A stop supplied on a follow-up buy must stick. Otherwise adding to a
        # position that started without one leaves you permanently unprotected,
        # which is the exact failure this whole app exists to prevent.
        if stop_price:
            pos["stop_price"] = float(stop_price)
        if target_price:
            pos["target_price"] = float(target_price)
    else:
        state["positions"][symbol] = {
            "units": units, "cost_basis": price, "opened": int(time.time()),
            "reason": reason.strip(), "confidence": confidence,
            "strategy_said": strategy_said, "fees": fee, "adds": 0,
            "stop_price": float(stop_price) if stop_price else None,
            "target_price": float(target_price) if target_price else None,
        }

    entry = {"ts": int(time.time()), "action": "buy", "symbol": symbol, "price": price,
             "units": units, "usd": usd, "fee": fee, "reason": reason.strip(),
             "confidence": confidence, "strategy_said": strategy_said}
    state["log"].append(entry)
    save(state)
    return entry


def sell(state: dict, symbol: str, fraction: float, price: float,
         reason: str, strategy_said: str = "") -> dict:
    """Sell `fraction` (0-1) of the position in `symbol` at the live `price`."""
    symbol = symbol.upper()
    pos = state["positions"].get(symbol)
    if not pos:
        raise PaperError(f"no open position in {symbol}")
    if not reason or len(reason.strip()) < 3:
        raise PaperError("write down why you're closing — exits are where most money is lost")

    fraction = max(0.0, min(1.0, float(fraction)))
    units = pos["units"] * fraction
    if units <= 0:
        raise PaperError("nothing to sell")

    proceeds = units * price
    fee = _fee(state, proceeds)
    state["cash"] += proceeds - fee

    cost = units * pos["cost_basis"]
    realized = proceeds - cost - fee
    held_days = (time.time() - pos["opened"]) / 86400.0

    trade = {
        "ts": int(time.time()), "symbol": symbol, "entry_price": pos["cost_basis"],
        "exit_price": price, "units": units, "cost": cost, "proceeds": proceeds,
        "pnl": realized, "pnl_pct": 100.0 * realized / cost if cost else 0.0,
        "fee": fee, "held_days": held_days,
        "entry_reason": pos["reason"], "exit_reason": reason.strip(),
        "confidence": pos["confidence"],
        "strategy_said_entry": pos.get("strategy_said", ""),
        "strategy_said_exit": strategy_said,
        "partial": fraction < 0.999,
    }
    state["trades"].append(trade)
    state["log"].append({"ts": trade["ts"], "action": "sell", "symbol": symbol, "price": price,
                         "units": units, "usd": proceeds, "fee": fee,
                         "reason": reason.strip(), "pnl": realized,
                         "strategy_said": strategy_said})

    pos["units"] -= units
    pos["fees"] = pos.get("fees", 0.0) + fee
    if pos["units"] <= 1e-12:
        del state["positions"][symbol]

    save(state)
    return trade


# ----------------------------------------------------------------------------
# Valuation
# ----------------------------------------------------------------------------

def mark(state: dict, prices: dict[str, float]) -> dict:
    """Value the portfolio at current prices."""
    rows, holdings_value = [], 0.0
    for sym, pos in state["positions"].items():
        px = prices.get(sym)
        value = (pos["units"] * px) if px else None
        unreal = (value - pos["units"] * pos["cost_basis"]) if value is not None else None
        if value:
            holdings_value += value
        stop = pos.get("stop_price")
        rows.append({
            "symbol": sym, "units": pos["units"], "cost_basis": pos["cost_basis"],
            "price": px, "value": value,
            "stop_price": stop, "target_price": pos.get("target_price"),
            # How much further price can fall before your own rule says sell.
            # Negative means it has already gone through — act, don't renegotiate.
            "stop_distance_pct": (100.0 * (px - stop) / px) if (px and stop) else None,
            "stop_breached": bool(px and stop and px <= stop),
            "unrealized": unreal,
            "unrealized_pct": (100.0 * unreal / (pos["units"] * pos["cost_basis"]))
                              if unreal is not None and pos["units"] else None,
            "opened": pos["opened"],
            "held_days": (time.time() - pos["opened"]) / 86400.0,
            "reason": pos["reason"], "confidence": pos["confidence"],
            "strategy_said": pos.get("strategy_said", ""),
            "weight_pct": None,
        })

    equity = state["cash"] + holdings_value
    for r in rows:
        r["weight_pct"] = (100.0 * r["value"] / equity) if (r["value"] and equity) else None
    rows.sort(key=lambda r: -(r["value"] or 0))

    # Fee split matters for the accounting identity below: exit fees are already
    # baked into realized P&L, so only ENTRY fees are subtracted separately.
    buy_fees = sum(l.get("fee", 0.0) for l in state["log"] if l["action"] == "buy")
    sell_fees = sum(l.get("fee", 0.0) for l in state["log"] if l["action"] == "sell")

    return {
        "cash": state["cash"], "holdings_value": holdings_value, "equity": equity,
        "initial_cash": state["initial_cash"],
        "total_return_pct": 100.0 * (equity / state["initial_cash"] - 1.0),
        "realized_pnl": sum(t["pnl"] for t in state["trades"]),
        "unrealized_pnl": sum(r["unrealized"] or 0 for r in rows),
        "total_fees": buy_fees + sell_fees,
        "entry_fees": buy_fees, "exit_fees": sell_fees,
        # equity == initial_cash + realized + unrealized - entry_fees   (exact)
        "identity_check": (state["initial_cash"] + sum(t["pnl"] for t in state["trades"])
                           + sum(r["unrealized"] or 0 for r in rows) - buy_fees),
        "positions": rows,
        "days_running": (time.time() - state["created"]) / 86400.0,
        "cash_pct": 100.0 * state["cash"] / equity if equity else 100.0,
    }


# ----------------------------------------------------------------------------
# The scorecard — this is the part that teaches you something
# ----------------------------------------------------------------------------

def scorecard(state: dict) -> dict:
    """
    Grade the trader, not the strategy.

    The headline number is CONVICTION EDGE: average return on your high-conviction
    trades minus average return on your low-conviction ones. If it isn't clearly
    positive, your sense of "this one's a good setup" is currently worth nothing,
    and you should be trading a mechanical system instead of your gut.
    """
    trades = state["trades"]
    if not trades:
        return {"trades": 0, "note": "No closed trades yet. The scorecard needs at least 10 to say anything, and closer to 30 before you should believe it."}

    pnls = [t["pnl"] for t in trades]
    pcts = [t["pnl_pct"] for t in trades]
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] < 0]

    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = -sum(t["pnl"] for t in losses)

    high = [t["pnl_pct"] for t in trades if t["confidence"] >= 4]
    low = [t["pnl_pct"] for t in trades if t["confidence"] <= 2]
    conviction_edge = (sum(high) / len(high) - sum(low) / len(low)) if high and low else None

    by_conf = {}
    for c in range(1, 6):
        g = [t["pnl_pct"] for t in trades if t["confidence"] == c]
        if g:
            by_conf[c] = {"n": len(g), "avg_pct": sum(g) / len(g),
                          "win_rate": 100.0 * len([x for x in g if x > 0]) / len(g)}

    # Did you agree with the systematic signal, and did agreeing help?
    agreed = [t for t in trades if t.get("strategy_said_entry", "").upper().startswith("LONG")]
    disagreed = [t for t in trades if t.get("strategy_said_entry", "") and
                 not t["strategy_said_entry"].upper().startswith("LONG")]

    notes = []
    n = len(trades)
    if n < 10:
        notes.append(f"Only {n} closed trades. Everything below is noise until you have 30+. Keep going.")
    if conviction_edge is not None:
        if conviction_edge > 2:
            notes.append(f"Your high-conviction trades outperformed low-conviction ones by {conviction_edge:.1f} percentage points. That is a real signal that you're reading something — keep sizing up on conviction.")
        elif conviction_edge < -2:
            notes.append(f"Your high-conviction trades did {abs(conviction_edge):.1f} points WORSE than your low-conviction ones. Your confidence is currently anti-correlated with being right. This is common and fixable, but for now trade the mechanical system, not the gut.")
        else:
            notes.append("Your confidence level barely predicts your results. Right now conviction is not information — size every trade the same until that changes.")
    if losses and wins:
        avg_w = gross_win / len(wins)
        avg_l = gross_loss / len(losses)
        if avg_l > avg_w * 1.5:
            notes.append(f"Your average loss (${avg_l:,.0f}) is much bigger than your average win (${avg_w:,.0f}). Classic pattern: cutting winners early, letting losers run. A mechanical stop-loss fixes this faster than willpower does.")
    hold_w = [t["held_days"] for t in wins]
    hold_l = [t["held_days"] for t in losses]
    if hold_w and hold_l and sum(hold_l) / len(hold_l) > 2 * (sum(hold_w) / len(hold_w)):
        notes.append("You hold losers roughly twice as long as winners. That's the disposition effect — hoping a loss comes back while snatching small gains.")
    if disagreed and agreed:
        a = sum(t["pnl_pct"] for t in agreed) / len(agreed)
        d = sum(t["pnl_pct"] for t in disagreed) / len(disagreed)
        notes.append(f"When you traded WITH your strategy's signal you averaged {a:+.1f}%; when you overrode it, {d:+.1f}%.")

    return {
        "trades": n,
        "win_rate": 100.0 * len(wins) / n,
        "avg_pnl": sum(pnls) / n,
        "avg_pct": sum(pcts) / n,
        "best": max(pnls), "worst": min(pnls),
        "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else (999.0 if gross_win else 0.0),
        "avg_win_pct": (sum(t["pnl_pct"] for t in wins) / len(wins)) if wins else 0.0,
        "avg_loss_pct": (sum(t["pnl_pct"] for t in losses) / len(losses)) if losses else 0.0,
        "avg_hold_days": sum(t["held_days"] for t in trades) / n,
        "avg_hold_win": (sum(hold_w) / len(hold_w)) if hold_w else 0.0,
        "avg_hold_loss": (sum(hold_l) / len(hold_l)) if hold_l else 0.0,
        "conviction_edge": conviction_edge,
        "by_confidence": by_conf,
        "traded_with_signal": len(agreed),
        "traded_against_signal": len(disagreed),
        "notes": notes,
    }
