# SignalGuard, steering file

Automated trading system for CME micro equity-index futures, built so the trading core can
later become a product. This file is the standing contract: how to work here, the six prime
directives, and the domain facts you may not contradict.

Scope note: the domain constitution, the phase plans, and the raw research syntheses are
kept private and are not part of this repository. What is public is the validation harness,
the decision log, and this file. Everything below stands on its own.

---

## 0. Operating protocol

### Compile the request before acting

Every task, however short, gets compiled into this before you touch anything. State it once
in four lines, then build. Do not wait for approval unless two readings of the request
produce materially different work.

```
Task:      <the concrete file or artifact>
Done when: <an observable that is allowed to come out FALSE, the gate, not a vibe>
Riskiest:  <the one assumption most likely to be wrong>
```

If `Done when:` cannot be written as something falsifiable, the task is underspecified. Ask
for that one line and nothing else. `/qd <rough ask>` prints the compiled prompt for review
instead of executing it.

### Read narrowly

Prefer `Grep` and `Glob` over `Read`. Read line ranges, not whole files. Cite a number as
`file.md:line` instead of restating it. Do not re-read what is already in context. Do not
spawn subagents unless asked; a cold agent re-reads everything you already paid for.

### Definition of done

A task is done when its gate passes, not when the code runs. Before saying done, fixed, or
passing: run the command, paste the output. Prime directive 6 governs your own claims about
your own work, not only trading numbers.

For anything touching risk, execution, or reconciliation, done additionally requires a test
that proves the failure path: the kill switch firing, the reconnect deduping, the sizer
refusing to arm. A component with only happy-path tests is not done.

### Skill routing

Load these when the trigger applies. Do not announce it, just do it. `.claude/hooks/route.sh`
fires the highest-value ones off the prompt text so they do not depend on you remembering.

| Trigger | Skill |
|---|---|
| About to claim done, fixed, or passing | `superpowers:verification-before-completion` |
| Any new module or behavior, before code | `superpowers:brainstorming`, then `superpowers:writing-plans` |
| Validation, risk, or continuous-contract math | `superpowers:test-driven-development`, falsifying test first |
| A bug, test failure, or surprising number | `superpowers:systematic-debugging`, never patch before reproducing |
| A module is complete | `superpowers:requesting-code-review`, then `pr-review-toolkit:silent-failure-hunter` |
| Anything with `except`, a fallback, or a default | `pr-review-toolkit:silent-failure-hunter` |
| A NautilusTrader, Databento, or IBKR API question | `context7`. Memory is not a tool that verified it |
| Generating or changing a chart | `dataviz` |
| A public-facing page or writeup | `artifact-design`, `artifact-diagramming` |
| Committing | `commit-commands:commit` |
| End of a working session | `remember:remember` |

Off-stack plugins are disabled in `.claude/settings.json` rather than merely discouraged
here, because a "do not load" instruction still costs the tokens of every skill description
it names. This is Python 3.12 plus numpy plus NautilusTrader.

### Standing constraints on your output

- **Never state a number as fact unless a tool produced it in this session.** Mark inferences
  as inferences. This is prime directive 6 and it applies to prose, comments, and commit
  messages.
- **Comments are terse and why-only.** One-line docstring on anything public. Inline comments
  only where the code would otherwise look wrong.
- **Never commit** account numbers, API keys, live config, real balances, or fitted
  parameters.

---

## 1. Prime directives

These override convenience, elegance, and speed of delivery. Violating one is a bug even if
the tests pass.

1. **One code path for backtest and live.** The strategy consumes an abstract event
   interface. Backtest and live differ ONLY by which `DataFeed`, `ExecutionHandler`, and
   `Clock` are injected. Two codebases drift and then lie to you. This is the number one
   killer of retail systems.
2. **The broker is the source of truth.** Never trust internal state. Reconcile positions and
   open orders on startup and on a timer.
3. **Every order carries a unique client order ID.** Re-submission after a reconnect must
   dedupe, not double-fill.
4. **The kill switch ships before the first strategy.** Daily loss limit, max drawdown halt,
   position cap, order-rate cap, stale-data dead-man's switch. It lives in code that runs
   independently of strategy logic.
5. **Costs are modeled from measured fills, not assumptions.** Assumed cost numbers decide
   whether an edge exists, so they are not allowed to stay assumed.
6. **No number in a commit message, comment, or report is stated as fact unless a tool
   verified it.** Mark inferences as inferences.

---

## 2. Facts you must not contradict

Tripwires, not reasoning. Each line is enough to stop you writing the wrong thing.

1. **Instrument: M2K or MES intraday.** MNQ sits outside the 0.5 to 2% risk band even
   intraday (2.72% at a 0.25x ATR stop). It is a graduation at roughly $22k, not a start.
2. **Futures swing is closed at $8k**, not merely gated. M2K's 2x ATR swing stop is 5.95% of
   equity. The swing sleeve runs in ETF shares until roughly $25k to $30k.
3. **The cost ceiling caps trade frequency at roughly 275 round turns per year**, about 1.09
   per day at $2.90 all-in. This kills every multi-entry intraday shape before a line is
   written.
4. **Micro exchange fees are roughly $0.20 to $0.40 per side plus about $0.02 NFA.** The
   widely quoted $1.15 to $1.45 is the E-mini number. Never reuse it for micros. Still
   unverified.
5. **The two adapters default in opposite directions.** Databento `bars_timestamp_on_close`
   defaults True; the IB adapter's defaults False. This is a pre-installed lookahead bug. Set
   both explicitly and assert at startup.
6. **There is no 5-minute Databento bar**, only `ohlcv-1s`, `-1m`, `-1h`, `-1d`.
7. **Continuous contracts use `BACKWARD_SPREAD` for the traded series**, ratio only for return
   research. Pick one mechanism, Databento `.c.0` or Nautilus tables, never both. Book P&L on
   real contract prices, never the adjusted series.
8. **The noise ceiling sits above the target band on short windows.** At 4 years, 20 pure
   noise trials reach Sharpe 1.22, above the entire 0.5 to 1.0 target. Validate on the longest
   available ES or NQ history, not on MNQ or MES native data.
9. **Backtested Sharpe above roughly 2.0 is a defect report, not a result.**
10. **Trial budget: hard cap 10 per hypothesis**, pre-registered before any fitting, seeded
    above zero for published ideas such as overnight, RTH, and ORB.
11. **At sub-$10k, fixed-fractional sizing is not expressible.** There is one available
    position size. The stop is set by market structure and the resulting percentage is
    recorded, not chosen. Band is 0.5 to 2%.
12. **Every open position needs a venue-resident protective order.** Locally emulated stops
    are prohibited in live trading; they die with the process.
13. **Never size off day-trade margin.** Monitor against full SPAN initial margin.
