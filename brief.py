#!/usr/bin/env python3
"""
brief.py — the spoken login briefing.

Runs locally on your Mac at login (see install-greeting.command). Reads your
paper portfolio, fetches live prices, and says one short thing out loud.

DESIGN RULE: BE SHORT, AND LEAD WITH WHAT MATTERS.
A greeting that talks for forty seconds every morning gets muted by day three.
This one is about eight seconds when nothing is happening, and the ONLY thing
that makes it longer is a stop being close or breached — because that is the
one piece of information that should interrupt you.

Written text and spoken text are composed separately on purpose. "$64,641.32"
reads fine on screen and sounds terrible out loud; speech gets rounded numbers
and no symbols.

    python3 brief.py            speak it, and write briefing.md
    python3 brief.py --print    just print, don't speak
    python3 brief.py --voice Samantha
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET_TRADES = 30          # the gate before the scorecard means anything
PREDICTIONS_OUTSTANDING = 12  # the week-one calibration exercise


# ----------------------------------------------------------------------------
# Speech-friendly formatting
# ----------------------------------------------------------------------------

def say_money(v: float | None) -> str:
    """Numbers a synthesiser reads well: no symbols, sensible rounding."""
    if v is None:
        return "unknown"
    v = float(v)
    if abs(v) >= 1_000_000:
        return f"{v / 1_000_000:.1f} million dollars"
    if abs(v) >= 1000:
        return f"{round(v / 100) * 100:,.0f} dollars"
    if abs(v) >= 1:
        return f"{v:,.0f} dollars"
    return f"{v:.4f} dollars"


def say_pct(v: float | None) -> str:
    if v is None:
        return "unknown"
    return f"{abs(v):.0f} percent {'up' if v >= 0 else 'down'}"


def greeting_for(hour: int) -> str:
    if hour < 12:
        return "Good morning"
    if hour < 18:
        return "Good afternoon"
    return "Good evening"


# ----------------------------------------------------------------------------
# Composition — pure function so it can be tested without a Mac or a network
# ----------------------------------------------------------------------------

def compose(state: dict, prices: dict[str, float], now: datetime | None = None,
            name: str = "") -> tuple[str, str]:
    """
    Return (spoken_text, written_markdown).

    Ordering is deliberate:
      1. anything through its stop        — act now
      2. anything within 3% of its stop   — watch today
      3. portfolio position               — context
      4. reps toward 30                   — the actual goal
      5. one action, usually "nothing"
    """
    now = now or datetime.now()
    import paper

    mark = paper.mark(state, prices)
    positions = mark["positions"]
    n_trades = len(state.get("trades", []))

    spoken: list[str] = [f"{greeting_for(now.hour)}{(' ' + name) if name else ''}."]
    lines: list[str] = [f"# Briefing — {now.strftime('%A %d %B, %H:%M')}", ""]

    breached = [p for p in positions if p.get("stop_breached")]
    near = [p for p in positions if not p.get("stop_breached")
            and p.get("stop_distance_pct") is not None and p["stop_distance_pct"] < 3.0]

    # ---- 1. stops -----------------------------------------------------------
    if breached:
        names = ", ".join(p["symbol"] for p in breached)
        spoken.append(f"{names} {'is' if len(breached) == 1 else 'are'} through your stop. "
                      f"Your own rule says sell. Do that before you start looking for reasons not to.")
        lines.append(f"## ⚠ Stop breached: {names}")
        for p in breached:
            lines.append(f"- **{p['symbol']}** at ${p['price']:,.2f}, stop was ${p['stop_price']:,.2f}. "
                         f"Unrealised {p['unrealized']:+,.0f}.")
        lines.append("")
    if near:
        for p in near:
            spoken.append(f"{p['symbol']} is {p['stop_distance_pct']:.0f} percent from its stop.")
        lines.append("## Close to stop")
        for p in near:
            lines.append(f"- **{p['symbol']}** {p['stop_distance_pct']:.1f}% above ${p['stop_price']:,.2f}")
        lines.append("")

    # ---- 2. portfolio -------------------------------------------------------
    if not positions:
        spoken.append(f"Portfolio {say_money(mark['equity'])}, all cash, no open positions.")
    else:
        spoken.append(f"Portfolio {say_money(mark['equity'])}, "
                      f"{say_pct(mark['total_return_pct'])} overall, "
                      f"{len(positions)} open position{'s' if len(positions) != 1 else ''}.")

    lines.append("## Portfolio")
    lines.append(f"- Value **${mark['equity']:,.2f}** ({mark['total_return_pct']:+.2f}%)")
    lines.append(f"- Cash ${mark['cash']:,.2f} ({mark['cash_pct']:.0f}%)")
    if positions:
        lines.append("")
        lines.append("| Coin | Now | Cost | P&L | To stop |")
        lines.append("|---|---|---|---|---|")
        for p in positions:
            # Every field here can be None when a price fetch failed. Formatting
            # None with a numeric spec raises, so each one is guarded.
            stop = (f"{p['stop_distance_pct']:.1f}%" if p.get("stop_distance_pct") is not None
                    else "no stop set")
            price = f"${p['price']:,.2f}" if p.get("price") else "—"
            pnl = ("—" if p.get("unrealized") is None
                   else f"{p['unrealized']:+,.0f} ({p['unrealized_pct']:+.1f}%)")
            lines.append(f"| {p['symbol']} | {price} | ${p['cost_basis']:,.2f} | {pnl} | {stop} |")
    lines.append("")

    # ---- 3. reps ------------------------------------------------------------
    if n_trades == 0:
        spoken.append(f"No closed trades yet. Zero of {TARGET_TRADES}.")
    elif n_trades >= TARGET_TRADES:
        spoken.append(f"{n_trades} closed trades. You are past {TARGET_TRADES}. "
                      f"Open the paper trading tab and read your conviction edge.")
    else:
        spoken.append(f"{n_trades} of {TARGET_TRADES} trades.")
    lines.append(f"## Reps\n\n**{n_trades} of {TARGET_TRADES}** closed trades toward your first "
                 f"scorecard read.\n")

    # ---- 4. one action ------------------------------------------------------
    if breached:
        action = "Close the breached position."
    elif n_trades == 0 and not positions:
        action = (f"Run your {PREDICTIONS_OUTSTANDING} strategy predictions, then place a first "
                  f"trade through Guided Trade.")
        spoken.append(f"{PREDICTIONS_OUTSTANDING} predictions still outstanding.")
    elif n_trades >= TARGET_TRADES:
        action = "Read the scorecard."
    elif near:
        action = "Watch the position near its stop. Otherwise nothing."
        spoken.append("Otherwise nothing to do.")
    else:
        action = "Nothing. Check the shortlist if you want a candidate."
        spoken.append("Nothing to do today.")

    lines.append(f"## Today\n\n{action}\n")

    missing = [p["symbol"] for p in positions if not p.get("stop_price")]
    if missing:
        lines.append(f"_No stop recorded for {', '.join(missing)} — placed outside Guided Trade._\n")

    stale = [s for s in prices if prices.get(s) is None]
    if stale:
        lines.append(f"_Couldn't fetch a live price for: {', '.join(stale)}._\n")

    return " ".join(spoken), "\n".join(lines)


# ----------------------------------------------------------------------------
# Runner
# ----------------------------------------------------------------------------

def gather_prices(state: dict) -> dict[str, float]:
    """Live prices for everything held. Degrades to {} with no network."""
    try:
        import data as dat
    except ImportError:
        return {}
    out = {}
    for sym in state.get("positions", {}):
        try:
            p = dat.latest_price(sym)
            if p:
                out[sym] = p
        except Exception:
            continue
    return out


def list_voices(lang: str = "en") -> list[tuple[str, str, str]]:
    """
    Installed macOS voices as (name, locale, sample sentence).

    `say -v '?'` prints lines like:
        Samantha            en_US    # Hello, my name is Samantha.
    Names can contain spaces and parentheses ("Zoe (Premium)"), so the locale
    token is the anchor rather than a plain column split.
    """
    if sys.platform != "darwin":
        return []
    try:
        out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True,
                             timeout=20).stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    import re
    pat = re.compile(r"^(.*?)\s{2,}([a-z]{2}[-_][A-Z]{2})\s*#\s*(.*)$")
    voices = []
    for line in out.splitlines():
        m = pat.match(line.rstrip())
        if m and m.group(2).lower().startswith(lang.lower()):
            voices.append((m.group(1).strip(), m.group(2), m.group(3).strip()))
    return voices


def audition(text: str, rate: int = 185, limit: int = 8) -> None:
    """
    Speak the real briefing in each installed voice, announcing the name first.

    Uses your ACTUAL brief rather than a canned sentence, because voices differ
    most on exactly the things this text is full of — numbers, decimals, and
    ticker symbols read as letters.
    """
    voices = list_voices()
    if not voices:
        print("No voices found (this only works on macOS).")
        return

    # Put the higher-quality voices first — they're the ones worth hearing.
    def quality(v):
        n = v[0].lower()
        return (0 if any(k in n for k in ("premium", "enhanced")) else 1, v[0])
    voices.sort(key=quality)

    print(f"Auditioning {min(limit, len(voices))} of {len(voices)} installed English voices.")
    print("Ctrl+C to stop.\n")
    for name, loc, _ in voices[:limit]:
        print(f"  → {name}  ({loc})")
        try:
            subprocess.run(["say", "-v", name, f"This is {name}."], timeout=30, check=False)
            subprocess.run(["say", "-v", name, "-r", str(rate), text], timeout=90, check=False)
            time.sleep(0.4)
        except KeyboardInterrupt:
            print("\nStopped.")
            return
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    print("\nUse the one you liked:  python3 brief.py --voice \"NAME\"")
    print("Then run install-greeting.command and enter that name.")


def speak(text: str, voice: str | None = None, rate: int = 185) -> None:
    """macOS built-in speech. Silently does nothing on other platforms."""
    if sys.platform != "darwin":
        return
    cmd = ["say", "-r", str(rate)]
    if voice:
        cmd += ["-v", voice]
    try:
        subprocess.run(cmd + [text], timeout=90, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description="Speak a short QuantLab briefing")
    ap.add_argument("--print", dest="print_only", action="store_true", help="don't speak")
    ap.add_argument("--voice", default=os.environ.get("QUANTLAB_VOICE") or None,
                    help="macOS voice name, e.g. Samantha. See: say -v '?'")
    ap.add_argument("--rate", type=int, default=int(os.environ.get("QUANTLAB_RATE", 185)))
    ap.add_argument("--name", default=os.environ.get("QUANTLAB_NAME", ""))
    ap.add_argument("--delay", type=int, default=0,
                    help="seconds to wait before starting (lets the network come up at login)")
    ap.add_argument("--list-voices", action="store_true", help="print installed voices and exit")
    ap.add_argument("--audition", action="store_true",
                    help="hear the real briefing read by each installed voice")
    ap.add_argument("--demo", action="store_true",
                    help="use a sample portfolio with an open position, to hear a fuller brief")
    args = ap.parse_args()

    if args.list_voices:
        vs = list_voices()
        if not vs:
            print("No voices found (macOS only).")
            return 0
        print(f"{len(vs)} English voices installed:\n")
        for name, loc, sample in vs:
            print(f"  {name:<28} {loc:<8} {sample[:52]}")
        print("\nMore voices: System Settings > Accessibility > Spoken Content")
        print("             > System Voice > Manage Voices")
        return 0

    if args.delay:
        time.sleep(args.delay)

    try:
        import paper
        state = paper.load()
    except Exception as e:
        print(f"couldn't read the portfolio: {e}", file=sys.stderr)
        return 1

    if args.demo:
        # A fuller brief to audition against — never touches your real portfolio.
        state = {**state, "positions": {
            "SOL": {"units": 13.5, "cost_basis": 148.0, "opened": int(time.time()) - 200_000,
                    "reason": "sample", "confidence": 4, "fees": 2.0, "adds": 0,
                    "stop_price": 139.0, "target_price": 166.0}}}
        prices = {"SOL": 141.2}
    else:
        prices = gather_prices(state)

    spoken, written = compose(state, prices, name=args.name)

    if args.audition:
        audition(spoken, args.rate)
        return 0

    if not args.demo:
        with open(os.path.join(HERE, "briefing.md"), "w") as f:
            f.write(written)

    print(written)
    print(f"\n--- spoken version ({len(spoken.split())} words) ---\n{spoken}\n")
    if not args.print_only:
        speak(spoken, args.voice, args.rate)
    return 0


if __name__ == "__main__":
    sys.exit(main())
