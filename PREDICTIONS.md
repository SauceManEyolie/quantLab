# Calibration Worksheet

**Setup:** Backtest tab · Symbol **BTC** · Timeframe **4h** · Range **2 years** · defaults for
everything else (fee 10 bps, slippage 5 bps, size 100%, no stop).

**The rule:** fill in your guess, *then* click Run, *then* fill in the actual. No peeking, no
editing your guess afterward. A guess you revised isn't a guess.

Work down the list in order. Buy & Hold first — it's your benchmark for every row below it.

---

## The predictions

| # | Strategy | My guess: Return | My guess: Max DD | Actual: Return | Actual: Max DD | Actual: Trades | Beat B&H? |
|---|---|---|---|---|---|---|---|
| 1 | Buy & Hold (baseline) | | | | | | — |
| 2 | RSI Mean Reversion | | | | | | |
| 3 | EMA Crossover (trend) | | | | | | |
| 4 | MACD Momentum | | | | | | |
| 5 | Bollinger Band Reversion | | | | | | |
| 6 | Donchian Breakout (Turtle) | | | | | | |
| 7 | Dip Buy + Trend Filter | | | | | | |
| 8 | ADX-Gated Trend | | | | | | |
| 9 | Volume Spike Breakout | | | | | | |
| 10 | Volatility Squeeze Breakout | | | | | | |
| 11 | Quality Score (shortlist formula) | | | | | | |
| 12 | Composite Score (ensemble) | | | | | | |

---

## Scoring yourself

Once the table is full, answer these. This is the actual output of the exercise — the table is
just how you get here.

**1. How many did you get within 20 percentage points of the real return?**

> ___ / 12

- **9+** — your instincts are unusually good. Trust them a little, verify anyway.
- **5–8** — normal. You have rough intuition and it needs sharpening.
- **0–4** — normal for a beginner, and worth knowing before you risk anything. Your sense of
  "this looks like it works" is currently not connected to whether it works.

**2. Did you predict the direction right — profit vs loss?**

> ___ / 12

Getting direction right but magnitude wrong is fine and common. Getting direction wrong means
you can't yet tell a working idea from a broken one by looking at it.

**3. How many beat Buy & Hold?**

> ___ / 12   ·   How many did you *expect* to?  ___ / 12

If you expected far more than reality delivered, you were carrying the most expensive assumption
in retail trading: that activity beats patience.

**4. Which single result surprised you most, and why?**

> 

Write a real sentence. This is the one that sticks.

**5. Were your guesses biased high or low overall?**

> 

Almost everyone guesses high — because the strategies you've heard of are the ones that get
talked about, and people talk about the winners. Knowing your own bias direction is worth more
than knowing any individual number.

---

## After the table

Pick the **two** strategies that surprised you most and take them through gates 3 and 4 in the
playbook:

- **Gate 3** — Optimize tab. Does it survive out-of-sample?
- **Gate 4** — Re-run on ETH, on SOL, on a 1-year window, at 20 bps fees. Does it survive
  being moved?

That's the next session. This one ends when the table is full.

---

*Date completed: ____________*
