# The Training Program

A strict, repeatable practice. Built around the one finding that matters: **the bottleneck
is not knowledge, it's rule-following under stimulus.**

So this program grades **compliance, not profit.** At your sample size P&L is noise;
compliance is the only thing you can actually control and the only thing that compounds.

---

## PART 0 — The rules

Non-negotiable. Breaking one voids the batch and you restart the count.

| # | Rule | Why |
|---|---|---|
| 1 | **Max 1 new position per day** | You made 113 trades in weeks. This is the governor. |
| 2 | **Max 3 open positions at once** | Forces you to choose. Concentration of attention, not capital. |
| 3 | **Every trade goes through Guided Trade** | The manual box has no stop field and no size rule. Never use it. |
| 4 | **No trade without a written reason** | Must be falsifiable. "Feels good" is not a reason. "EMA says LONG, RSI 48, above trend" is. |
| 5 | **Never add to a losing position** | This is the one that killed the FOMO account. BOLLOCKS ×10, GUNICORN ×7. |
| 6 | **Never change strategy or parameters mid-batch** | You'd be reacting to noise. Changes happen at review only. |
| 7 | **Exit when the rule says exit** | Not when you feel like it. Not "one more candle." |
| 8 | **Review only at 10-trade boundaries** | No exceptions, no peeking at the scorecard early. |

**If you break a rule, log it.** Don't hide it — the broken-rule count is a metric, and watching
it fall is the actual progress.

---

## PART 1 — The weekly lab (45 min, no trading)

Separate from execution. This is where strategies earn a place on the shelf.

**The validation checklist.** A strategy is "shelf-ready" only when it passes all five:

- [ ] **Gate 1 — Beats buy & hold** on the primary coin
- [ ] **Gate 2 — Beats the simpler alternative** (Compare tab)
- [ ] **Gate 3 — Survives out-of-sample** (Optimize tab; check the overfit warning)
- [ ] **Gate 4 — Survives being moved**: different coin, different period, double fees
- [ ] **Gate 5 — Survivable**: max drawdown you could sit through, 30+ trades, worst streak you could take

**Record every run in a table.** Coin, timeframe, period, strategy, return, vs B&H, max DD,
win rate, payoff, trades. Build the shelf slowly.

**The one calculation that matters:**

```
break-even payoff = (1 − win rate) ÷ win rate
```

If achieved payoff isn't clearly above that line, the strategy has no edge — no matter how
good the return looks on one run.

---

## PART 2 — The regime read (2 min, before any trade)

**How you judge a market objectively.** Three readings, no interpretation:

| Reading | Where | Meaning |
|---|---|---|
| **Price vs 200-EMA** | Trend column | Above = trend strategies allowed. Below = stay out. |
| **ADX** | Scanner / signals | >25 trending, <20 chop |
| **ATR %** | Vol column | How wide your stop must sit |

**The decision table — memorise this:**

| Trend | ADX | What's allowed |
|---|---|---|
| Up | >25 | **Trend strategies.** Best conditions. |
| Up | <20 | Mean reversion only, small size |
| Down | >25 | **Nothing.** Cash. |
| Down | <20 | **Nothing.** Cash. |

Two of four rows are "do nothing." That's correct, and it's the row you'll most want to argue with.

---

## PART 3 — The daily loop (10 min)

1. **Check Signals** on your watchlist (max 5 coins)
2. **Regime read** on anything showing LONG
3. If regime allows → **Guided Trade → Plan the Trade → read all four numbers**
4. Take it or skip it. **Write the reason. Rate conviction honestly.**
5. **Check open positions against their stops.** Breached = sell, no renegotiation.
6. Close the laptop.

**Most days you will do nothing. That is the job, not a failure of it.**

---

## PART 4 — The review (every 10 closed trades)

### Section A — Compliance scorecard (the real grade)

| | Count |
|---|---|
| Trades taken through Guided Trade | __ / 10 |
| Trades with a written falsifiable reason | __ / 10 |
| Trades with a stop recorded | __ / 10 |
| Exits taken on the rule, not on feeling | __ / 10 |
| **Rules broken this batch** | __ |

**Target: 10/10 on all four, 0 broken.** Hit that twice in a row before you care about P&L.

### Section B — The numbers

- Win rate · payoff · **break-even payoff needed** · did you clear it?
- Average hold: winners vs losers *(losers held longer = disposition effect)*
- Conviction edge: avg return on 4–5 rated minus avg on 1–2 rated
- vs buy & hold over the same window

### Section C — Three written answers

1. **Which trade would I take again, knowing only what I knew then?** *(judge decisions, not outcomes)*
2. **Which rule was hardest to follow, and what was the trigger?**
3. **What single change do I make for the next batch?** *(exactly one — more than one and you can't attribute the effect)*

---

## PART 5 — Progression gates

You do not advance until the gate is cleared. No shortcuts.

**LEVEL 1 — Compliance** *(you are here)*
> 10 closed trades at 10/10 compliance, 0 rules broken.
> **P&L is irrelevant at this level. Do not look at it as a measure of success.**

**LEVEL 2 — Sample**
> 30 closed trades, compliance maintained. Read the scorecard for the first time.
> Target: conviction edge positive, or honest acknowledgement that it isn't.

**LEVEL 3 — Edge**
> 30+ trades beating buy & hold over the same window, with a drawdown you actually sat through.

**LEVEL 4 — Capital**
> Only now does real money enter the discussion — funded by paychecks set aside for it,
> never from savings, at a size where total loss is annoying rather than damaging.

Most people never clear Level 2. Clearing it honestly is the whole game.

---

## The one-line version

> **Validate in the lab. Classify the market. Execute the rule. Review in batches. Grade the process.**

---

*You cannot control whether a trade wins. You can control whether you followed the rule. Only
one of those is a skill, and only one of them compounds.*
