# The QuantLab Playbook

How to use this app to find candidates, build strategies, test whether your ideas are any good,
and find out whether *you* can execute them.

Written for someone who can code but hasn't done finance. Every term is explained where it first
matters, and every term is also hoverable inside the app.

---

## Start here if you've never placed a trade

**Open the Shortlist tab and click "Rank the Market." Then open Guided Trade, pick the top coin,
and click "Plan the Trade."**

That's the whole first session. The first screen tells you what's worth looking at and why, with
every factor's contribution visible. The second hands you the four numbers a trade is made of.
It's paper money, so the only thing you can lose is a misconception.

The mechanics of trading are genuinely small. You have dollars in an exchange account. You place
an **order** — *market* (buy right now at whatever the price is) or *limit* (buy only if it
reaches $X). Now you own some fraction of a coin. To exit, you sell the same two ways. A
**stop-loss** is a standing instruction: "if it falls to $X, sell automatically." That's it.
Twenty minutes to learn, and the app simulates all of it.

**What's actually hard is that a trade needs four numbers, and most people can only produce one:**

| | The blank | Most people |
|---|---|---|
| 1 | **What** you're buying | ✓ have this |
| 2 | **How much**, in dollars, decided before you feel anything | ✗ guess |
| 3 | **Where you're wrong** — the price that disproves the idea | ✗ never decide |
| 4 | **Where you're done** — the exit rule, written in advance | ✗ improvise |

If you can't fill in all four, you don't have a trade. You have a hope with money attached.
Feeling clueless usually isn't a knowledge problem — it's an unfinished checklist, and #2 and #3
are pure arithmetic once you've picked a risk tolerance. Guided Trade does that arithmetic.

---

## Part 0 — The map

Nine working tabs. Roughly this order:

| Tab | Question it answers | When |
|---|---|---|
| **Shortlist** | Which coins score well right now, and exactly why? | Start of a session |
| **Guided Trade** | What do I do, and how much? | Every session, especially early on |
| **Radar** | What's happening, and what's being talked about? | Start of a session |
| **Scanner** | Quick condition sweep across coins | When you want a second view |
| **Backtest** | Would this idea have worked historically? | When you have a hypothesis |
| **Compare** | Is my idea better than the obvious alternatives? | After a promising backtest |
| **Optimize** | Are my settings real, or did I curve-fit them? | Before you believe anything |
| **Paper Trading** | Can *I* execute? Is my judgement worth anything? | Continuously, from day one |
| **Glossary** | What does that word mean? | Whenever — or just hover the term |

The one you'll be tempted to skip is Optimize. It's the one that saves you money.

---

## Part 1 — The Shortlist, and why it's built the way it is

Most "top coins to buy" lists are unfalsifiable. Someone asserts five tickers and there's no way
to check whether the method that produced them has ever worked. This app makes that impossible:

**The formula that ranks coins today is registered as a strategy you can backtest over years.**
Same function, same file (`rank.py`). If the shortlist likes a coin, you can immediately ask
"what would this rule have done over the last three years, with fees?" — and get a real answer.

### The six factors

Every coin is scored 0–100 from six measurable things, each normalised to 0–1 then weighted:

| Weight | Factor | What it checks |
|---|---|---|
| **30%** | Above long-term trend | Price above its 200-period EMA |
| **20%** | Momentum | 20-period EMA above the 50-period |
| **15%** | Short-term momentum | MACD histogram positive |
| **15%** | Healthy RSI zone | RSI 40–70 scores full; tapers outside |
| **10%** | Real trend, not chop | ADX above 15, full marks at 35 |
| **10%** | Participation | Volume z-score above normal |

Trend gets the largest weight because it's the most reliable single filter in trading — it keeps
you out of the periods that do the most damage.

**These weights are round numbers on purpose.** They were not tuned to make a backtest look good,
which is the only reason to trust them. Tune them yourself in Optimize and watch the
out-of-sample column — if your tuned weights beat these in-sample but not out-of-sample, the
round numbers were better.

### Two columns deliberately excluded from the score

The shortlist shows **relative strength vs BTC** and **news attention**, both marked *(not in
score)*. That isn't an oversight:

- **Relative strength** needs a second asset to compute, so it can't exist inside a single-asset
  backtest. Including it would break the guarantee that the ranking equals the backtest.
- **News attention** has no historical archive, so it can't be backtested at all.

Blending an unverifiable input into a verifiable score would make the whole thing unfalsifiable.
They're shown as information you can weigh yourself, not as part of the maths.

### Reading a shortlist card

Each coin shows every factor with points earned out of points available. A coin at 85 with four
factors passing tells you *which* four. A coin scoring 49 that's above its trend line but has no
momentum is a different situation from one at 49 with momentum but no trend — the breakdown makes
that visible instead of hiding it behind a number.

**A shortlist with nothing above 65 is a real answer.** It means the formula is telling you to
stay in cash. Most of the time, for most strategies, flat is correct.

---

## Part 2 — The vocabulary, in plain English

Every term below is hoverable in the app. This is the reference version.

**The unlocking idea:** every indicator here is just a function over a rolling window of numbers.
There's no hidden theory. RSI is about eight lines of pandas — read all of them in
`indicators.py` in ten minutes. The finance world gives these functions intimidating names; the
maths is not intimidating.

### The data

**Candle** — a time bucket summarised by four numbers: open, high, low, close. A "4h candle"
covers four hours. *In code terms:* a GROUP BY over time keeping first/max/min/last.

**Timeframe** — your bucket size. Bigger means less noise, fewer decisions, slower. Checking a
few times a day fits 1h or 4h, holding days to weeks. Short timeframes lose to fees.

### The indicators

| Term | What it computes | What it tells you |
|---|---|---|
| **SMA / EMA** | Rolling mean; EMA weights recent points more | A low-pass filter — strips noise to show direction |
| **RSI** | Share of recent moves that were upward, 0–100 | 70+ heavy buying, 30− heavy selling |
| **ATR** | Average size of a candle, in dollars | How jumpy this coin is |
| **ADX** | Signal-to-noise for direction | 25+ real trend, under 20 chop |
| **Bollinger Bands** | Rolling mean ± 2 standard deviations | How stretched price is vs its own range |
| **Volume z-score** | (volume − mean) / std | Above 2 means something actually happened |

**RSI is the most misused.** Treating 70 as a sell signal is the classic beginner error — in a
strong trend RSI sits above 70 for weeks while price keeps climbing. It's a condition, not a
signal, and only becomes useful with a trend filter attached.

**ATR is the most useful and least glamorous.** It's your unit of "normal movement." If the
average 4h candle is $600, a $600 move means nothing happened. It's how the app places stops.

### Making a trade

**Position size** — an *output*, not a choice. See Part 3.

**Stop-loss** — a pre-committed exit price. A circuit breaker installed before you have any
emotional stake. Its whole purpose is that present-you doesn't trust future-you at 2am.

**R** — 1R = the dollars you risked on that trade. Made $200 having risked $100? That's +2R.
*In code terms:* normalisation — divide out the scale so trades are comparable.

**Reward:risk** — at 2:1 you only need to be right 33% of the time to break even. This is why
win rate alone tells you nothing.

### Judging whether it works

**Buy & hold** — your benchmark. Beating it is the whole game. A strategy returning 40% while
holding returned 90% means you did more work, took more risk, paid more fees, and made less.

**Max drawdown** — worst peak-to-trough fall in account value. Predicts whether you'll still be
running a strategy in six months better than returns do.

**Win rate** — the most misleading stat here. Trend systems win 35% of the time and make money.
Check **profit factor** (gross wins ÷ gross losses; 1.5 decent, 2 strong) instead.

**Sharpe** — return per unit of bumpiness. Above 2 in a backtest usually means overfitting.

**Overfitting / in-sample / out-of-sample** — exactly the ML terms, meaning exactly the same
things. Train/test split. Training accuracy 99%, test accuracy 51%.

**bps** — basis point, 1/100th of a percent. 10 bps = 0.1%. Just a unit.

---

## Part 3 — Position sizing, which runs backwards

This is the highest-leverage idea in the document, and Guided Trade computes it for you.

Beginners pick a position size and then wonder where to put a stop. **Do it in reverse:**

1. Decide what you're willing to lose on one trade — say **2% of the account**.
2. Decide where the idea is disproven — the stop, at **2× ATR** below entry, far enough that
   ordinary noise can't reach it.
3. Size is then forced:

```
size = dollars_at_risk ÷ (distance_to_stop ÷ entry_price)
```

Worked example: $10,000 account, 2% risk = $200. Stop 8% below entry → position = $200 ÷ 0.08 =
**$2,500**. Not $10,000.

**The consequence is counterintuitive and correct: a more volatile coin needs a wider stop, which
makes the position smaller.** You size by volatility, not by enthusiasm. That single inversion is
most of professional risk management.

At 2% risk you can be wrong **50 times in a row** and still be trading. The goal isn't to be
right — it's to stay solvent long enough for being right to matter.

Keep any single position under ~25% of the portfolio regardless of what the maths says.

---

## Part 4 — Turning a vague idea into a testable one

**Most trading ideas are untestable as stated.** "Buy the dip" isn't a hypothesis — it's a vibe.
Before it can be tested it needs four things nailed down:

1. **Entry condition** — precisely what must be true. *"RSI(14) below 35"* not *"when it's cheap."*
2. **Exit condition** — precisely what makes you sell. Most people never define this, which is
   why they hold losers and sell winners.
3. **Universe and timeframe** — which coins, which candle size.
4. **Regime** — when you expect it to work and when you expect it to fail. If you can't name a
   condition where your idea should fail, you haven't thought about it.

### Worked example

> **Vibe:** "Buy the dip on Bitcoin."
>
> **Hypothesis:** On BTC 4h candles, buying when RSI(14) drops below 35 *while price is still
> above its 200-EMA*, and selling when RSI recovers above 65, beats buy-and-hold over 2 years.
> I expect it to work in bull markets and fail badly in sustained downtrends — which is why the
> 200-EMA filter is there.
>
> **How to test:** Backtest → BTC / 4h / 2 years → "Dip Buy + Trend Filter" → `oversold` 35,
> `exit_level` 65, `trend_len` 200. Run.

### Write the prediction down first

Before you hit Run, write your expected return and max drawdown somewhere. Then compare.

This is the highest-value habit in the document. It converts "huh, interesting" into calibration.
Over 20 hypotheses you'll discover whether your intuitions about markets track reality — which is
the actual skill you're building.

---

## Part 5 — The validation gauntlet

Five gates. Most ideas die at gate 1. That's the system working.

### Gate 1 — Does it beat buy-and-hold?

Look at **vs Buy & Hold**. Negative means stop. No amount of tuning fixes an idea that's
negative by a wide margin — you'd just be searching for the lucky parameter.

### Gate 2 — Is it better than the boring alternative?

Compare tab. If your carefully-reasoned idea ranks below plain EMA Crossover, either it's
redundant or the simpler thing is better. Simpler is usually better — fewer parameters means
fewer chances to fool yourself.

### Gate 3 — Does it survive out-of-sample?

**The gate that matters most.** Optimize tab splits history: tunes on the first 70%, then reports
how those exact settings did on the untouched 30%.

- **IS high, OOS high** → promising. Rare.
- **IS high, OOS near zero** → you fitted noise. The common case.
- **The warning at the top** tells you whether in-sample winners predicted out-of-sample winners
  at all across every combination tested.

And the subtle one: **prefer a broad region over a single spike.** If `oversold=32` returns 180%
but 30 and 34 both lose money, that 32 is a coincidence. If 28 through 38 all return 40–70%,
you've found something with a shape to it. Robust beats optimal, every time.

### Gate 4 — Does it survive being moved?

Change one thing at a time:

- **Different coin.** Works on BTC, dies on ETH? BTC-specific noise.
- **Different period.** 1 year vs 3 years. Bull-market-only edges are common and dangerous.
- **Different timeframe.** 4h works, 1h and 1d both fail? Suspicious.
- **Double the fees.** Set fee_bps to 20. If the edge vanishes, it was never an edge.

An idea that only works in one exact configuration isn't a strategy, it's a coincidence with good PR.

### Gate 5 — Can you live with it?

- **Max drawdown.** Imagine real money down that much. Be honest.
- **Max consecutive losses.** That's how many times you'd take a loss and still follow the rules.
- **Number of trades.** Under 15, the statistics are meaningless.

Only after all five does an idea earn paper trading. Not real money — paper.

---

## Part 6 — What actually tends to survive

Verify all of it yourself; that's the point.

**Holds up reasonably well:**

- **Trend filters.** Adding "only buy above the 200-EMA" improves almost any strategy. Usually
  worth more than any amount of parameter tuning. This is why it's the heaviest weight in the
  shortlist formula.
- **Volatility-scaled stops (ATR).** Adapting risk to conditions beats fixed percentages.
- **Ensembles.** Requiring several independent conditions to agree — the Quality Score and
  Composite strategies — is harder to overfit, because you'd have to be lucky in several
  dimensions at once.
- **Doing less.** Fewer, higher-conviction trades usually beat frequent trading, mostly because
  fees compound viciously.

**Rarely survives contact with fees:**

- Any single indicator alone — RSI thresholds, MACD crossovers, band touches.
- Short-timeframe strategies for retail. On 5m candles you compete with firms whose entire
  advantage is being 2ms closer to the exchange. Your edge cannot be speed.
- Anything with more than about four tuned parameters.

**The uncomfortable one:** for most people, most of the time, buy-and-hold on a major asset beats
their active trading after fees, taxes, and mistakes. The value of this tool isn't finding a
magic strategy. It's proving which ideas don't work before they cost you, and building the
judgement to recognise the rare thing that does.

---

## Part 7 — Information edge: what's real and what isn't

Half of "being plugged in" is true, and it's not the half most people chase.

### The real version

Narratives rotate. A sector heats up over weeks — restaking, DePIN, an L2 ecosystem, an ETF
decision — and people who read widely notice while it's building. That edge is measured in **days
and weeks**, applies to assets that already have liquidity and price history, and is free.

That's the **Radar** tab. The narrative tracker is the useful part: it counts which names appear
across your feeds, weights recent mentions higher, and ranks by *how many different outlets*
mention something rather than how loudly one does. A name you don't recognise appearing in five
places in a day is worth ten minutes of reading. You won't be first. You'll be earlier than
price, which is the only "early" that pays.

Then take the candidate to the Backtest tab. A narrative gives you a name; the backtest tells you
whether there's a tradeable pattern. Neither works alone.

### The version that eats people

"Get into new tokens before they run" is a different activity wearing the same clothes:

- **98.6%** of 7M+ Pump.fun tokens studied fell below $1,000 in liquidity.
- **~1%** of daily launches ever graduate to a real pool with locked liquidity.
- In April 2026 — one of the *better* months — **96% of wallets** either lost money or made under
  $500.

The structural problem no diligence fixes: **the launch window is contested by bots operating in
the same block.** By the time a token is visible on a feed, the people who were actually early
are deciding when to sell to you. You aren't competing on information — you're competing on
latency, against software.

The app shows these tokens with liquidity, age, volume-to-liquidity ratio and buy/sell skew
attached, because refusing to show them would just send you somewhere with worse information. The
lowest risk label that table can display is HIGH, and there's no paper-trading integration for
them on purpose — a token forty minutes old has no price history to model.

**A workable rule:** if you want exposure to this category, treat it as entertainment spending.
Size it at what you'd pay for a concert ticket, expect zero back, and never let it touch the
capital you're running strategies with.

### On X/Twitter

No free programmatic access exists any more — the API is paid and public mirrors are mostly dead.
Radar uses Google News and Reddit instead, which index crypto media quickly. If you want X, read
it in a browser and treat every account you follow as someone with a position they'd like you to
take off their hands.

---

## Part 8 — Paper trading: testing yourself, not the strategy

A backtest asks *"does this strategy work?"* Paper trading asks *"do I work?"* — will you take
the signal, hold through a 15% drawdown, resist doubling down after a loss. Different question,
and the one people fail.

### The two things that make it more than a toy

**1. Every trade requires a written reason and a conviction rating (1–5)**, recorded before you
know the outcome. The scorecard computes your **Conviction Edge**: average return on 4–5 rated
trades minus average on 1–2 rated ones.

- **Clearly positive** → your read carries real information. Size up on conviction.
- **Near zero** → your confidence is noise. Size everything the same.
- **Negative** → your confidence is *anti-correlated* with being right. Common, fixable, and
  impossible to discover without writing it down first.

**2. Every trade is stamped with what the systematic strategy said at that moment**, so you can
separate "my discretion beat the system" from "I got lucky agreeing with it."

### Your session routine (~10 minutes, a few times a day)

1. **Shortlist → Rank the Market.** See what scores well and why.
2. **Radar → narrative tracker.** Anything unfamiliar appearing across many outlets?
3. **Guided Trade** on anything interesting. Read the four numbers. Take it or skip it.
4. **Paper Trading → Check Signals** for what you already hold. If something says CLOSE, either
   close it or write down why you're overriding.
5. **Note the 2×ATR stop** for everything you hold. If price reaches it, the reason you bought is
   gone — sell without renegotiating with yourself.

### What "done" looks like

**30 closed paper trades with honest notes.** Then read the scorecard. Not before — below 30
every number there is noise, and the app will tell you so.

---

## Part 9 — A concrete four-week plan

**Week 1 — Calibrate.** Use Shortlist and Guided Trade for every position. Separately, for each
of the 12 built-in strategies, write down what you *predict* it returns on BTC 4h over 2 years,
then run the backtest. You're measuring how wrong your intuitions are. Goal: 10 paper trades,
all journaled.

**Week 2 — Falsify.** Take your three best ideas through gates 3 and 4. Also backtest the
**Quality Score** strategy — the shortlist formula itself — on three different coins and two
different periods. Expect at least two ideas to die. Goal: 20 total paper trades.

**Week 3 — Build.** Whatever survived, write it as a custom strategy in `strategies.py` (one
function plus a registry entry; the UI generates the controls). Run all five gates. Goal: 30
total paper trades, then read your scorecard for the first time.

**Week 4 — Decide.** Compare three things: your paper results, the backtest of the strategy you
were following, and buy-and-hold over the same weeks. If you underperformed the strategy you were
nominally following, **the gap is you** — execution, not analysis. That gap is the most useful
thing you'll learn, and the one that would have cost real money.

Only then should real money enter the conversation, at a size where a total loss is annoying
rather than damaging.

---

## Part 10 — The five ways you will fool yourself

1. **Running 50 parameter combinations and reporting the best.** With 50 random strategies the
   best looks great by chance alone. This is why the out-of-sample split exists.
2. **Testing only bull markets.** Nearly everything works in 2020–21 or 2023–24. Include a bear
   period or your results are fiction.
3. **Forgetting fees.** 200 trades/year at 0.1% per side burns ~40% of gross. Some "profitable"
   systems are just fee generators.
4. **Ignoring drawdown because the return looks good.** You will not sit through −60%. Design for
   the drawdown you'll tolerate, then see what return that permits.
5. **Moving the goalposts after the fact.** "It would have worked if I'd exited two days earlier"
   is not a finding. Write the rule, test it, keep the result.

---

## Quick reference

| Setting | Value | Why |
|---|---|---|
| Timeframe | **4h** (1h if impatient) | Matches checking a few times a day |
| Test period | **2 years minimum** | Must include at least one bad stretch |
| Fee | **10 bps** (stress-test at 20) | Realistic retail taker fee |
| Slippage | **5 bps** on BTC/ETH, 15+ on small coins | Thin books cost more |
| Risk per trade | **1–2%** | Survive 50 straight losses |
| Max position | **25%** | One bet can't dominate |
| Stop loss | **2×ATR** | Volatility-scaled beats fixed |
| Shortlist entry threshold | **65** | Most factors must agree |
| Min trades to believe a backtest | **30+** | Below that it's luck |
| Min paper trades before conclusions | **30** | Same reason |

### Verify everything

```bash
python3 run.py --test     # 179 Python + 41 JavaScript correctness tests
```

The engine's honesty rules — signals fill at the *next* candle's open, fees on both sides,
stops checked against real highs and lows, stop wins over target on ambiguous bars — each have a
regression test. The ranking formula has tests proving the shortlist and the backtest use
identical maths, and that the score is causal.

---

*Nothing here is financial advice. Every claim in Part 6 is one you should verify with the tool
rather than take on faith — that's what it's for. Past performance does not predict future
returns, and crypto is volatile enough to lose the entire position.*
