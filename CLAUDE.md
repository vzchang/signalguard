# QuantDesk — Steering File

Automated trading system for CME micro equity-index futures, built so the trading core
can later become a product. Read this before writing any code in this repo.

Sources: every number here came from a 2026-08-04 8-track research fan-out plus an
adversarial critique pass. Where the critique corrected the research, the corrected
value is what appears below. Anything marked UNVERIFIED must be confirmed against a
primary source (CME spec page, broker fee schedule) before you rely on it.

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

## 2. Instrument decision

**Assumption: the operator is a US person.** [UNVERIFIED — inferred from the Section 1256,
NFA/CFTC, and FINRA PDT framing, not confirmed.] If false, Section 1256 60/40 does not
apply, the IBKR contracting entity and product eligibility change, and the entire §8
regulatory map is the wrong map and must be re-derived before going live.

**Primary at current capital: MES. MNQ is the graduation, not the starting point.**

*Revised 2026-08-04 by the adversarial audit, on arithmetic rather than preference.* The
original answer to "ES vs NQ vs MNQ" was MNQ. That was wrong at $8k, and it was wrong
because two rules in this file contradicted each other: §7 mandates 0.25-1% equity risk
per trade, while the table below sized contracts at 1-2%.

Run the arithmetic at $8k with a structure-based stop of roughly 0.25x the daily range:

| Contract | One-lot risk at that stop | As % of $8k equity | Inside the risk band? |
|---|---|---|---|
| MES | $62-100 | **0.8-1.25%** | yes |
| MNQ | $100-200 | **1.25-2.5%** | no, needs ~2% |

MES is the only one of the two whose single-contract structural stop lands inside a
defensible risk band at this capital. MNQ is the graduation once equity supports it.

| Contract | $/point | Tick | $/tick | Notional (approx) | Typical daily range | Sane capital for 1 contract @1-2% risk |
|---|---|---|---|---|---|---|
| ES  | $50 | 0.25 | $12.50 | ~$300k | ~50-80 pt = $2.5-4k | ~$50-100k+ |
| NQ  | $20 | 0.25 | $5.00  | ~$420k | ~200-400 pt = $4-8k | ~$75-150k |
| MNQ | $2  | 0.25 | $0.50  | ~$42k  | ~$400-800           | ~$8-15k (min ~$5k) |
| MES | $5  | 0.25 | $1.25  | ~$30k  | ~$250-400           | ~$5-10k (min ~$2-3k) |

Reasoning:

- A micro is *the same instrument* as its big sibling: same 0.25-pt tick, same price
  series, same session, same book. Only the multiplier differs (10x). So strategy code,
  data pipeline, and execution logic lift-and-shift to ES/NQ unchanged when the equity
  curve earns it, while every bug and drawdown during iteration costs 1/10 as much.
- **What "position-sizing granularity" actually means below $25k.** Not scaling lots —
  at this capital there is exactly one available position size, so fixed-fractional
  sizing is not expressible. It means *choosing an instrument whose one-lot structural
  stop lands inside the risk band.* MES does at ~1%; MNQ needs ~2%. ES/NQ are far outside
  any defensible band.
- MNQ's appeal is that Nasdaq moves roughly 2x the S&P in dollar terms, so momentum and
  breakout logic has more signal to trade. That is a reason to graduate to it, not a
  reason to start there.

**Ladder:** MES (primary now) → MNQ (on graduation) → *ES/NQ is aspirational only.* The
ES/NQ rung projects a capital trajectory this plan concedes elsewhere is unlikely; do not
treat it as planned work.

**Never size off day-trade margin.** Brokers will let you hold MNQ on ~$50-200 of
intraday margin. That is a leverage permission, not a survival threshold. One normal
adverse day is $400-800 on MNQ. Size off risk-per-trade against account equity.

Asset-class tailwinds: no FINRA pattern-day-trader rule applies to futures (no $25k
minimum, unlimited round-trips, so you can iterate on a small balance); CME Globex runs
~23h/day Sunday 18:00 ET to Friday 17:00 ET with a ~60-min daily halt at 17:00-18:00 ET;
index futures are Section 1256 contracts taxed 60/40 long/short regardless of holding
period, marked to market at year end. Confirm tax treatment with a CPA; it is
US-specific and you owe MTM on open positions.

Character note for the graduation step: NQ trends harder but whipsaws more and needs
roughly 2x the stop distance of ES. ES is smoother, mean-reverts more, and has the
deepest book with ~1-tick spreads, which means the best algo fills.

---

## 3. Architecture

Canonical pipeline. Do not deviate from this decomposition.

```
DataFeed -> Strategy/Alpha (signals) -> Portfolio/Risk (sizing + limits)
         -> OMS/ExecutionHandler -> State store -> Monitoring
```
driven by an event loop plus a `Clock` abstraction.

### Stage 0, MVP, one person

- **Engine:** adopt **NautilusTrader** (Rust core, Python strategy API, event-driven,
  Databento and IBKR adapters). Lead with it rather than hand-rolling the loop; it gives
  you years of plumbing and structurally encourages the same-code-path invariant.
  Caveat from the critique: its backtest/live parity is *strong, not absolute*. Fill
  models, latency simulation, and partial-fill behavior still differ from live. The
  framework claim does not replace a live-tiny reconciliation phase.
- **Research funnel:** vectorbt (or VectorBT PRO) for wide, fast parameter screening.
  Survivors get re-validated in Nautilus. Two tiers: fast vectorized funnel, then
  high-fidelity event-driven validator. Neither alone is sufficient. Vectorized engines
  silently ignore path dependence (intrabar stop-outs, partial fills, queue priority).
- **Storage:** Parquet + DuckDB for research. SQLite or Postgres for operational state
  (orders, positions, P&L).
- **Config/secrets:** pydantic-settings + YAML. Secrets via env plus a secrets manager.
  Separate credentials for paper and live, never one set with a flag.
- **Deploy:** one Dockerized cloud VM, structured logs, kill switch. Pin the container by
  **image digest, not tag**; committed lockfile with hashes is the source of truth. An
  engine or fill-model version bump requires re-running the Phase 1 gates plus a
  stored-vs-new replay comparison before it reaches live. `pip-audit` in CI.
- **Framework constraint, not a preference:** multiple `TradingNode` or `BacktestNode`
  instances **in one process are unsupported** due to global singleton state (`_FORCE_STOP`,
  logger state, Tokio/OnceLock) [verified via Nautilus docs]. Parallelism requires separate
  **processes**. So Stage 1's "one process per strategy" is *required, not chosen*, and the
  Phase 2 validation tier needs process orchestration budgeted for it.

### Stage 1, multi-strategy

> **Stages 1 and 2 are REFERENCE ARCHITECTURE, not planned work.** Prometheus/Grafana
> beyond the Phase 2.5 alerting minimum, the message bus, TimescaleDB/ClickHouse,
> multi-strategy sleeves, and the ES/NQ ladder are all deferred to an "only if the equity
> curve earns it" list. They are written here so the Stage 0 design does not paint itself
> into a corner, not because they are scheduled.

Keep the same code, run one process per strategy for fault isolation. Add a light bus
(Redis Streams or NATS JetStream) for market-data fan-out and order/fill events. Add a
central risk/OMS service enforcing portfolio-level limits and netting. State to
Postgres/TimescaleDB, ticks to ClickHouse or ArcticDB. IaC via Terraform or CDK.

### Stage 2, multi-user / product

Event-driven services over a durable log (Kafka or NATS JetStream), where the same event
log replays as your backtest. Split into market-data ingestion, feature, per-tenant
strategy runners, portfolio/risk, OMS gateway, reconciliation, monitoring. Event
sourcing + CQRS. Per-tenant isolation, RBAC, per-account API keys.

**Do not start at Stage 2.** Microservices and Kafka early destroy solo velocity for
benefits you cannot yet use. Python at millisecond latency is fine for minute and
second frequency. Do not buy kdb+, colocation, or a Rust rewrite before profiling.

### Latency reality

You are not doing sub-millisecond HFT and must not design as if you are. CME's match
engine is in **Aurora, Illinois**. No AWS region is in Chicago; us-east-2 is Ohio, about
10-15ms away, which is entirely adequate here. If latency ever genuinely matters the
answer is Equinix CH1/CH2 colocation or an AWS Local Zone, not a region label.

---

## 4. Data

- **Historical/research: Databento.** Pull `trades`, `mbp-10`, and `ohlcv`. Buy `mbo`
  (full per-order book) only for the narrow windows where you actually model queue
  position. **Usage-based pricing covers HISTORICAL ONLY** [verified 2026-08-04,
  databento.com/pricing]. Live data starts at the **Standard tier, $199/mo**, which also
  *caps* L1 history at 12 months and L2/L3 at 1 month — so the tier that unlocks live gives
  you *less* research history. Standard advertises bundled license fees for personal use up
  to 2 devices; **whether that covers non-display for an automated account is UNVERIFIED**
  and must be settled via the licensing questionnaire.
- **Schema matching is the highest-leverage anti-skew move** — *and it costs $2,388/yr,
  against a ~$700/yr expected gross return.* So the **default architecture through Phase 3
  is Databento usage-based for historical research plus IBKR for live data**, accepting the
  schema mismatch as a named, logged risk. Upgrade to Databento Live only if Phase 2.5
  *measures* a divergence that changes a decision.
- **Granularity ladder:** OHLCV bars < trades < L1/BBO < MBP-N (aggregated depth) < MBO
  (every add/modify/cancel with order IDs). Bars for daily/swing. Tick + L1 to validate
  fills. MBO only for genuine microstructure work. Most retail vendors give aggregated
  MBP, not MBO, so you cannot infer true queue position from them.
- **CME market-data fees are the budget item to price first.** The ~$11-15/mo
  non-professional device fee is a trap for automated systems: CME charges a separate
  and much larger **non-display license** (hundreds+/mo) when data drives automated
  decisions with no human viewing it. Many retail algo setups technically fall under it.
  Misclassification is retroactively reclaimable at roughly 10x. Per the critique, this
  classification applies **via the data vendor too**, not only via the broker.
- Adding MNQ/MES costs no extra CME data fee; micros ride the same equity-index license
  as the E-minis.
- **Continuous contracts are a modeling choice you own, not ground truth.** Per-contract
  data (e.g. ESZ5) is unambiguous; the stitched series is not. Roll on volume/open-interest
  crossover. **Adjustment default: `BACKWARD_SPREAD` for the traded series** (exact, works
  directly on `PriceRaw`); **ratio only for return-series research** where percentage
  continuity matters. Ratio goes through float in the hot path and can shift the resulting
  raw price by 1 ULP [verified via Nautilus continuous-futures docs], which conflicts with
  exact-replay determinism.
- **The framework gives you the arithmetic and none of the machinery.** Per Nautilus docs:
  *"The engine does not discover rolls, choose contracts, or infer roll prices: that is the
  caller's responsibility."* The continuous root is *"a synthetic id with no market data of
  its own"* and cannot be traded — you must map root → front contract yourself, identically
  in backtest and live. Open interest is **not** in OHLCV bars and the `statistics` schema
  cannot stream through `BacktestNode`, so roll dates are precomputed offline as a
  **versioned research artifact**.
- **Pick one continuous mechanism and write it down:** Databento `.c.0` symbology **or**
  Nautilus transition tables. Never both — mixing them double-adjusts silently.
- **There is no 5-minute Databento bar** [verified]: `subscribe_bars()` supports only
  `ohlcv-1s`, `-1m`, `-1h`, `-1d`. Prefer native `ohlcv-1m`; anything else stacks a second
  aggregation layer on an already-aggregated continuous target.
- **Book P&L on actual traded-contract prices, never the adjusted series.** Adjusted
  series manufacture phantom roll-gap P&L.
- Standardize on exchange nanosecond matching-engine timestamps. Know which timestamp
  each field is. Mixing exchange, gateway-send, and local-capture timestamps creates
  look-ahead or phantom latency. Verify each vendor's bar-labeling convention (timestamp
  = bar open vs bar close); an off-by-one there leaks the future into your signal.
- **THE TWO ADAPTERS DEFAULT IN OPPOSITE DIRECTIONS — this is the named lookahead bug class,
  pre-installed** [verified]: Databento's `bars_timestamp_on_close` **defaults True**
  (close-stamped), while the IB adapter's documented setting is `False` (open-stamped, "IB
  standard"). **Set both explicitly in config, never by default, and assert the setting at
  startup.** Also: IB's `handle_revised_bars` **defaults False**, so bar revisions are
  silently discarded — decide which you want and record it.
- CME trades on Central Time with a session spanning the calendar day. Naive UTC or
  local bucketing misaligns sessions and daily bars. DST transitions are a live bug class.

---

## 5. Broker and execution

- **Start: Interactive Brokers via the NautilusTrader `interactive_brokers` adapter**
  (`ibapi` under the hood; Nautilus repackages it for PyPI). **Not `ib_async`** — that was
  the original pick and it was wrong: driving IB through a second client library alongside
  Nautilus creates a second execution path, which violates prime directive 1. The rejection
  is architectural, not about maintenance (`ib_async` *is* the maintained fork and
  `ib_insync` is archived). Mature API, paper account on the identical interface, automation
  allowed. Run IB Gateway headless with IBC because it force-restarts daily.
- **Verify the paper-vs-live parity claim rather than assuming it.** "Paper on the identical
  interface" is load-bearing for prime directive 1, so diff paper vs live market-data
  entitlements and order-type support explicitly; any difference is a named parity gap
  recorded here.
- **Alternative: Tradovate** (REST/WebSocket, modern API). Pricing tiers and per-contract
  rates are exactly the numbers that drift; treat any figure as UNVERIFIED until checked.
  Note the ownership chain: Tradovate sits under NinjaTrader Group, and NinjaTrader was
  acquired by Kraken (~2025), which also touches "NinjaTrader Brokerage" as an FCM option.
- **Scale: a real FCM (AMP, Ironbeam, Optimus) fronting a Rithmic feed** for better
  fills, more consistent latency, and server-side brackets. CQG if the FCM standardizes
  on it. Rithmic's RithmicProto is language-agnostic including Python.
- **Prop firms (Apex, Topstep) are a capital layer, not execution infrastructure.** The
  existence of an API (ProjectX/TopstepX) does not mean unattended automation is
  permitted; automating an evaluation can void the account. The landscape is actively
  unstable, not merely changeable: the CFTC brought an action against My Forex
  Funds/Traders Global in 2023 and multiple futures props have since changed or closed
  rules. Read the current written rules before automating anything there.
- **Cost accounting rule: always compute all-in round-turn cost.** Broker commission is
  per side and excludes exchange and NFA fees. Critique correction that matters here:
  the frequently quoted ~$1.15-1.45/side CME+NFA figure is the **E-mini** number.
  **Micro** equity-index exchange fees are roughly **$0.20-0.40/side plus ~$0.02 NFA**
  (UNVERIFIED, confirm against current CME and broker schedules). Quote micro and mini
  schedules separately and never reuse the mini figure for micros.
- Cost drag is the whole thesis on micros: roughly $1-2 commission plus ~1 tick slippage
  per round turn, against a ~10-20 pt MNQ move worth $20-40. Costs eat 5-15% of gross
  edge, and that fraction rises with trade frequency.
- **Broker auto-liquidation is a real risk the strategy must respect.** IBKR can force-
  close on intraday margin at bad prices, especially overnight in a thin book. A
  drawdown you consider survivable can still be liquidated at the worst tick.
- Overnight Globex micro liquidity is thinner than RTH depth. Slippage assumptions built
  on RTH books understate the cost of any overnight-hold strategy.

---

## 6. Strategy policy

### Honest edge landscape

- **HFT owns:** sub-second prediction, queue position, order-book imbalance, latency
  arbitrage, passive market-making rebate capture. ES and NQ are among the most
  efficient markets on earth intraday. Do not compete here. Explicitly out of scope for
  this project: market making, scalping, tick-level stat arb, and RL for execution.
- **Realistic target:** net Sharpe ~0.5-1.0 for a single robust retail futures strategy,
  often lower after live decay. **Anything backtesting above ~2.0 on daily-or-slower
  index futures is an overfit, a look-ahead bug, or a cost bug.** Treat a high Sharpe as
  a defect report, not a result.
- **THE NOISE CEILING, APPLIED TO FUTURES.** This project built the noise-ceiling test,
  used it to kill crypto, and originally never pointed it at its own futures plan. Pointed
  there, it returns the same kind of verdict. `SE(Sharpe) ≈ sqrt(1/T_years)`, and the
  expected best of N pure-noise trials is `≈ SE · sqrt(2 ln N)`:

  | Sample | SE | N=5 | N=10 | N=20 | N=100 |
  |---|---|---|---|---|---|
  | 4 years | 0.50 | 0.90 | 1.07 | 1.22 | 1.52 |
  | 20 years | 0.22 | 0.40 | 0.47 | 0.55 | 0.67 |

  **On a 4-year window the entire target band (0.5-1.0) sits below the ceiling of even a
  small honest search, so an honestly applied DSR gate must reject every result in the
  band — including a genuinely real one.** The structural consequence: the only way to
  ever "pass" on a short window is to weaken the statistics. So validation runs on the
  **longest available ES/NQ history**, and the trial budget is capped *before looking*.
  At 20 years the N=20 ceiling falls to ~0.55, which makes a true 0.5-1.0 edge detectable.
- Capacity is a non-issue at your size on daily-timeframe index strategies. ES trades
  millions of contracts daily; you are invisible.
- **ML reality:** LightGBM/XGBoost on engineered features can modestly improve signal
  combination or regime filtering. Sequence models rarely beat GBMs on tabular financial
  features at retail data scale and overfit readily. ML is allowed only as a
  **meta-model for sizing/filtering** via triple-barrier meta-labeling, never to
  generate the directional signal from scratch, and never before a rule-based base
  strategy has a clean out-of-sample record.
- VWAP is an execution benchmark, not alpha. Institutions trade *to* VWAP. Use it as a
  same-day reference or filter, not a standalone edge.

### Candidate strategies, with the critique's downgrade applied

The research recommended an overnight-vs-RTH seasonality edge as the starter. **The
critique substantially downgraded this and the downgrade is what governs.** The
overnight-vs-RTH anomaly is documented for *cash equities and ETFs* (close-to-open).
CME equity futures trade ~23h with only a 60-min halt, so there is **no true
close-to-open gap to harvest**; you are holding through Globex and the term structure
already prices financing. The effect has also decayed or partially reversed in
literature since roughly 2021-2022, and it is so heavily published that DSR and PBO
should penalize it hard.

So: **treat it as a candidate hypothesis to be re-tested on futures specifically, net of
realistic micro costs, on recent data. Do not port the ETF result on faith and do not
describe it as capacity-unlimited, latency-irrelevant, or Sharpe 0.5-0.9 until your own
out-of-sample says so.**

Opening-range breakout on MNQ is the intraday complement (strictly mechanical, hard
stop, EOD exit, volatility-gated). It is also heavily crowded and publicized, so it is
unproven until your own OOS confirms it, not a co-equal starter.

The first real deliverable is therefore **not a profitable strategy. It is the harness
that can honestly reject one.**

### Validation protocol, mandatory

1. State an economic hypothesis before any fitting.
2. Build continuous contracts with an explicit roll rule; book P&L on real contract prices.
3. Point-in-time data. Trade **next-bar open**, never same-bar close/high/low, never
   assume fills at the exact high or low. Charge commission plus at least 1 tick plus spread.
4. Hold out a true OOS set you never look at.
5. Anchored and rolling walk-forward; report walk-forward efficiency.
6. Combinatorial Purged Cross-Validation with purge and embargo, producing a Sharpe
   **distribution**, not a point estimate. Plain k-fold leaks via overlapping labels and
   serial correlation.
7. Gate on Deflated Sharpe Ratio and Probability of Backtest Overfitting. **Track your
   trial count**; the max of many runs is upward biased by construction.
8. Require a parameter plateau, not a knife-edge optimum. Require consistency across
   related markets (MES and MNQ should not disagree wildly).
9. Paper-trade on the same engine before any real capital.
10. **Pre-register the total trial budget before any fitting. Hard cap: 10 trials per
    hypothesis.** The DSR penalty scales with `sqrt(log N)`; a large search cannot be
    rescued by statistics after the fact.
11. **Seed the trial counter above zero for published ideas.** The overnight/RTH effect
    and the opening-range breakout are both heavily published, which *is* prior trials on
    the same hypothesis. Apply the published-literature penalty as arithmetic in the DSR
    gate, not as an intention in prose. Pre-register the ORB range length and bar interval
    from the published specification; deviating counts as a logged trial, and any sweep
    must be declared up front as a plateau check over a stated grid, with the whole grid
    counted.

---

## 7. Risk and operations

Survival here is a risk-control and reliability problem, not an alpha problem.

- **Sizing: 0.5-2% equity risk per trade.** *(Revised from 0.25-1%, which contradicted §2.)*
  At sub-$10k there is exactly one available position size, so **fixed-fractional sizing is
  not expressible** — the stop is set by market structure and the resulting percentage is
  *recorded, not chosen*. Volatility-target the portfolio to a fixed annualized vol. Kelly
  is a *ceiling only*, used fractionally (1/4 to 1/2). Never full Kelly.
- **Protective orders.** Every open position must have a **venue-resident** protective
  order at all times. Nautilus can locally emulate order types a venue does not support;
  emulated orders exist only while the process does. **Locally-emulated protective orders
  are prohibited in live trading.** Verify which bracket structures the IB adapter supports
  natively. Assert on startup and on a timer that every open position has a live
  venue-side stop, and page if not.
- **Margin control.** Monitor excess liquidity against **full SPAN initial margin**, not
  day-trade margin. Soft threshold blocks new entries and pages; hard threshold flattens on
  your own terms before the broker does. Size overnight positions so a 2x-typical-range
  adverse gap still leaves the account above maintenance. Read IBKR's actual liquidation
  disclosure from inside the account and write down what it does — the §5 assertion about
  auto-liquidation is currently unsourced.
- **Disaster recovery.** RTO 15 minutes to flat-or-recovered. **Auto-restart is disabled
  while a position is open** until reconciliation is proven. If an outage exceeds the
  reconciliation lookback, or any position discrepancy is unresolved, **flatten manually and
  restart flat** rather than letting the engine synthesize fills — Nautilus infers
  `OrderFilled` events and can fall back to a MARKET order when no price data exists, which
  corrupts the P&L record. **Page (never merely log)** on any synthetic or inferred fill and
  on any order returned under strategy ID `EXTERNAL`. Persist all events to the cache
  database; set `flush_on_start=False` and assert it at startup.
- **Config change control.** Mandatory diff-and-confirm before any live config takes
  effect, printing old vs new. **Live config changes are forbidden while a position is
  open**, enforced in code. Any risk-parameter change carries a 24-hour cool-off or a
  written justification in `DECISIONS.md` — with no second reviewer, time and text are the
  substitute.
- **Layered kill switches, independent of strategy code:** per-trade stop, daily loss
  limit, max-drawdown halt, position cap, order-rate cap, stale-data dead-man's switch,
  and a hard flatten-and-halt path.
- **Operational failure modes are what actually blow up bots**, not bad signals:
  disconnections, duplicate and orphan orders, partial fills, stale or gapped data,
  timezone and DST bugs, roll-date bugs, fat-finger config, exchange halts. Defenses:
  idempotent client order IDs, broker reconciliation, heartbeats, circuit breakers.
- Skip the maintenance break and thin overnight liquidity in your model and live will
  not match the backtest.
- Automation both helps discipline and hides risk: it removes the impulse to override,
  and it removes the human who would have noticed something was wrong at 3am.
  Monitoring is the compensating control.

### Go-live gate

Split into two gates, because the original single list required measured live costs before
any live trading had happened — an unsatisfiable ordering.

**Gate A — before any live trading (backtest and paperwork only)**

1. Re-validate the chosen edge on **futures specifically**, on the **longest available
   ES/NQ history (1997/1999 onward)**, net of realistic **micro** costs, with 2022-onward
   held as a *regime-consistency check, not the primary sample*. MNQ/MES-native history
   (2019+) is too short to validate anything: **validate on the mini series, trade the
   micro.** Do not accept a ported cash-equity result.
2. Non-display market-data classification and Section 1256 / entity treatment **confirmed
   in writing** — moved into Phase 0, since the individual-vs-LLC answer affects how the
   account is opened.
3. Monthly run rate is within the stated ceiling (`PLAN.md` Phase 0).

**Gate B — the Phase 2.5 plumbing run, blocking, real money but no edge required**

4. Run paper plus live-tiny across **at least one full roll cycle and one major macro
   event** (FOMC, CPI, or NFP) to shake out roll, DST, and halt bugs.
5. Measure all-in round-turn cost **from actual fills**: commission, exchange, NFA,
   realized slippage. Do not ship on assumed figures.
6. **Live fault-injection drill in a production-like environment:** pull the connection
   mid-position, force a partial fill, feed a stale tick, **SIGKILL the container
   mid-position, and terminate the VM mid-position.** Confirm the kill switch and
   reconciliation behave, and confirm **from the broker UI** that the protective stop is
   still resting at the venue after process death.
7. Off-VM heartbeat watcher and the 3am runbook are in place (`PLAN.md` Phase 2.5).

---

## 8. Product path, the "besides a bot" answer

Build the trading core as a **headless, API-first engine**. Every product form is then a
different head on the same core, and you dogfood it on your own capital first, which is
the only path that needs zero registration.

Regulatory line to stay on the safe side of, which is narrower than people assume. You
become regulated when you (a) handle other people's money, (b) give personalized
investment advice for compensation, or (c) execute/broker trades. Stay on the
tools-plus-bring-your-own-broker-keys plus general non-personalized information side and
you are a software vendor. Futures advice or pooling triggers NFA registration under the
CFTC: CTA for advising others on futures, CPO for pooling. Relevant named provisions the
critique flagged: **CTA de minimis exemption CFTC 4.14(a)(10)** (fewer than 15 clients,
no holding out), Rule 4.13(a)(3) small-pool exemption, Rule 4.7 QEP relief, and the
**bona fide publisher's exclusion** (Lowe v. SEC 1985), which covers general-circulation
non-personalized newsletters but *not* personalized advice or discretionary trading.
None of this is legal advice; it is a map of where to ask counsel.

Product forms, ranked for this situation:

1. **Execution/automation bridge** (alerts or signals to broker orders, users supply
   their own broker keys). Lowest regulatory drag, no custody, no personalized advice,
   demand proven by TradersPost, and it reuses your execution-adapter and risk layers
   directly. **This is the recommended first commercial surface.**
2. **Monitoring/analytics dashboard.** A thin head on the same core. Good upsell tier
   and lead-generation wedge, not a whole business.
3. **Human-in-the-loop copilot.** The most fashionable prosumer wedge; keeps the human
   as decision-maker, which keeps you off the adviser line. Evolve toward this.
4. **Research/backtest platform.** Long build, big prize, crowded (QuantConnect).
5. **Signals-as-a-service.** Only with strict non-personalized framing, or register.
6. **Data/tooling.** A byproduct to spin out later. The moat and the cost are exchange
   data licensing, not software.
7. **Prop/funded then CTA/CPO or a fund.** Deliberately last. Requires audited
   performance and real inbound demand; heavy compliance and capital.

Open-core is a proven indie pattern in this niche (vectorbt free plus vectorbtpro paid;
LEAN open source plus paid cloud/live). Monetize compute, hosting, live trading, and
support, not the core library.

**Consequence for how you write code today:** keep strategy logic pure and free of I/O,
keep broker specifics behind an adapter interface, and keep the risk layer independent
and reusable. Those three boundaries are what make a dashboard, a bridge, or a copilot a
few weeks of work each instead of a rewrite.

---

## 9. Verified vs unverified

Verified this session via the research fan-out and critique: contract specs and
multipliers, margin ranges, session hours, framework capabilities and maintenance
status, the methodology stack, the regulatory map.

**Confirm before relying on:** all broker commission and platform pricing (drifts
constantly), micro exchange and NFA fee schedule, current CME non-display fee levels and
whether your setup triggers it, current prop-firm automation rules, current SPAN margin
levels, and anything tax-related.
