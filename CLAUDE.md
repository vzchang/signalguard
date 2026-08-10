# SignalGuard — Steering File

Automated trading system for CME micro equity-index futures, built so the trading core
can later become a product. This file is the **router**: the process, the six directives,
and the facts you must not contradict. It is the only file loaded automatically.

**The domain constitution lives in `docs/constitution.md`, §2–§9, verbatim and with the
original section numbers.** A cross-reference anywhere in this repo that reads "`CLAUDE.md`
§5" means `docs/constitution.md` §5. `CLAUDE.md` + `docs/constitution.md` *is* the original
single file, unedited.

---

## 0. Operating protocol

How to work in this repo. §1 and the constitution are what is true; this section is how you
work. When they conflict, §1 wins.

### Compile the request before acting

Every task, however short the ask, gets compiled into this before you touch anything.
State it once in four lines, then build. Do not wait for approval unless two readings of
the request produce materially different work.

```
Task:      <the concrete file or artifact>
Phase:     <0 | 1 | 2 | 2.5 | 3 | 4 | 5, from PLAN.md §2>
Done when: <an observable that is allowed to come out FALSE — the gate, not a vibe>
Riskiest:  <the one assumption most likely to be wrong>
```

If `Done when:` cannot be written as something falsifiable, the task is underspecified —
ask for that one line and nothing else. `/qd <rough ask>` prints the compiled prompt for
review instead of executing it.

### Context discipline — read narrowly, on demand

This file is loaded. That is enough to start; **read nothing else by default.** Pull in more
only when the task needs it, and only the part you need:

| Need | Open |
|---|---|
| Domain facts and their reasoning | `docs/constitution.md` §2–§9 — **grep it**, its header has the index |
| What's next, what's blocked | `PLAN.md` §2 (phases) |
| A module's interfaces | `docs/phase1-implementation.md` — the reconciled, buildable Phase 1 plan |
| Why a decision is what it is | `DECISIONS.md` (append-only; grep, don't read) |
| Paging/alerting rules | `docs/observability-design.md` §1 |
| Provenance for a claim | `docs/research/` — 5 curated syntheses. Raw agent output lives in the separate private `signalguard-research` repo. |

Rules: prefer `Grep`/`Glob` over `Read` on anything in `docs/`; read line ranges, not whole
files. Cite a number as `file.md:line` instead of restating the table. Don't re-read what's
already in context. Don't spawn subagents unless asked — this repo's docs are large and a
cold agent re-reads all of them.

**Before writing code that touches a constitution topic, grep that section first.** Sizing →
§2. Module layout → §3. Bars, timestamps, rolls → §4. Adapters and cost → §5. Validation and
scoring → §6. `risk/`, kill switches, margin → §7. The tripwires in §2 below tell you *that*
a rule exists; the constitution tells you what it says.

### Definition of done

A task is done when **its gate passes**, not when the code runs. Before saying done, fixed,
or passing: run the command, paste the output. Prime directive 6 governs your own claims
about your own work, not only trading numbers.

For anything touching `risk/`, `execution/`, or reconciliation, "done" additionally requires
a test that proves the **failure** path — the kill switch firing, the reconnect deduping, the
sizer *refusing to arm*. A component that only has happy-path tests is not done.

### Skill routing

Load these when the trigger applies; don't announce it, just do it. `.claude/hooks/route.sh`
fires the highest-value ones off the prompt text so they don't depend on you remembering.

| Trigger | Skill |
|---|---|
| About to claim done / fixed / passing | `superpowers:verification-before-completion` |
| Any new module or behavior, before code | `superpowers:brainstorming` → `superpowers:writing-plans` |
| Writing validation, risk, or continuous-contract math | `superpowers:test-driven-development` — the falsifying test first |
| A bug, test failure, or surprising number | `superpowers:systematic-debugging` — never patch before reproducing |
| A module is complete | `superpowers:requesting-code-review`, then `pr-review-toolkit:silent-failure-hunter` |
| Anything with `except`, a fallback, or a default | `pr-review-toolkit:silent-failure-hunter` — a silent fallback here is a live incident |
| A NautilusTrader / Databento / IBKR API question | `context7` — read the real docs; **memory is not a tool that verified it** (§1.6) |
| Generating or changing a demo chart | `dataviz` |
| A phase writeup or public-facing page | `artifact-design`, `artifact-diagramming` |
| Committing | `commit-commands:commit` |
| This file has drifted from reality | `claude-md-management:revise-claude-md` |
| End of a working session | `remember:remember` |

**Off-stack plugins are disabled for this project** in `.claude/settings.json` rather than
merely discouraged here — a "do not load" instruction still costs the tokens of every skill
description it names. This is Python 3.12 + numpy + NautilusTrader. The one browser-shaped
task in the plan (reading CME MBT/MET specs, `PLAN.md` §10) is explicitly **a human in a
browser**, because every automated attempt was blocked.

### Standing constraints on your output

- **Budget is a gate, not a guideline.** Phase hour budgets are in `PLAN.md` §9. Exceeding 2x
  requires a written decision in `DECISIONS.md` — say so rather than quietly continuing.
- **Obey the `Skip:` lists.** Every phase has one. Dashboards, multi-venue abstraction, and
  performance tuning are skipped in Phase 1 by decision, not by oversight.
- **Don't re-litigate `PLAN.md` §0.** Instrument, engine, data, broker, and crypto are
  decided. New *arithmetic* can reopen one; preference cannot.
- **Never state a number as fact unless a tool produced it in this session.** Mark inferences
  as inferences. This is §1.6 and it applies to your prose, comments, and commit messages.

---

## 1. Prime directives

These override convenience, elegance, and speed of delivery. Violating one is a bug
even if the tests pass.

1. **One code path for backtest and live.** The strategy consumes an abstract event
   interface. Backtest vs live differ ONLY by which `DataFeed`, `ExecutionHandler`, and
   `Clock` are injected. Two codebases drift and then lie to you. This is the number
   one killer of retail systems.
2. **The broker is the source of truth.** Never trust internal state. Reconcile
   positions and open orders on startup and on a timer.
3. **Every order carries a unique client order ID.** Re-submission after a reconnect
   must dedupe, not double-fill.
4. **The kill switch ships before the first strategy.** Daily loss limit, max drawdown
   halt, position cap, order-rate cap, and a stale-data dead-man's switch. It lives in
   code that runs independently of strategy logic.
5. **Costs are modeled from measured fills, not assumptions.** Assumed cost numbers
   decide whether an edge exists, so they are not allowed to stay assumed.
6. **No number in a commit message, comment, or report is stated as fact unless a tool
   verified it.** Mark inferences as inferences.

---

## 2. Facts you must not contradict

Tripwires, not reasoning. Each line is enough to stop you from writing the wrong thing and
tells you where the arithmetic is. **When a task touches one of these, grep that section
before writing code.** All § refs are `docs/constitution.md`.

1. **Instrument: M2K or MES intraday.** MNQ is *outside* the 0.5–2% risk band even intraday
   (2.72% at a 0.25xATR stop) — it is a graduation at ~$22k, not a start. → §2
2. **Futures swing is CLOSED at $8k**, not merely gated: M2K's 2xATR swing stop is 5.95% of
   equity. The swing sleeve runs in **ETF shares** until ~$25–30k. → §2
3. **The cost ceiling caps trade frequency at ~275 round turns/yr ≈ 1.09/day** (M2K/MNQ at
   $2.90 all-in). This kills every multi-entry intraday shape before a line is written. → §2
4. **Micro exchange fees are ~$0.20–0.40/side + ~$0.02 NFA.** The widely quoted $1.15–1.45
   is the **E-mini** number; never reuse it for micros. Still UNVERIFIED. → §5
5. **The two adapters default in opposite directions.** Databento `bars_timestamp_on_close`
   defaults **True**; the IB adapter's is **False**. This is a pre-installed lookahead bug —
   set both explicitly and assert at startup. → §4
6. **There is no 5-minute Databento bar** — only `ohlcv-1s/-1m/-1h/-1d`. → §4
7. **Continuous contracts: `BACKWARD_SPREAD` for the traded series, ratio only for return
   research.** Pick one mechanism (Databento `.c.0` *or* Nautilus tables), never both. Book
   P&L on real contract prices, never the adjusted series. → §4
8. **The noise ceiling sits above the target band on short windows.** At 4 years, N=20 pure
   noise trials reach Sharpe 1.22 — above the entire 0.5–1.0 target. So validate on the
   **longest available ES/NQ history**, not on MNQ/MES-native data. → §6
9. **Backtested Sharpe above ~2.0 is a defect report, not a result.** → §6
10. **Trial budget: hard cap 10 per hypothesis, pre-registered before any fitting, seeded
    above zero for published ideas** (overnight/RTH, ORB). → §6
11. **At sub-$10k, fixed-fractional sizing is not expressible.** There is one available
    position size; the stop is set by market structure and the resulting % is *recorded, not
    chosen*. Band is 0.5–2%. → §7
12. **Every open position needs a venue-resident protective order.** Locally-emulated stops
    are prohibited in live trading — they die with the process. → §7
13. **Never size off day-trade margin.** Monitor against full SPAN initial margin. → §2, §7

**Operational, and it governs every commit:** publication is a **one-way door**. Before any
public push, `docs/NEXT-STEPS.md` §1 must be complete — full Apache-2.0 license text, a
`detect-secrets` baseline, and `pre-commit install`. Never commit account numbers, API keys,
live config, or real balances (`docs/constitution.md` §5, `PLAN.md` §5).
