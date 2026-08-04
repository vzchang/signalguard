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

**Primary: MNQ (Micro E-mini Nasdaq-100). First live deployment: MES.**

The question was ES vs NQ vs MNQ. MNQ wins, and it is not close, because of account size.

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
- **Position-sizing granularity is the real win.** Micros let you scale 1, 2, 3
  contracts and hold a clean fixed-fractional risk. ES/NQ force coarse jumps that make
  sane risk arithmetically impossible under $10k.
- MNQ over MES as the primary: Nasdaq moves roughly 2x the S&P in dollar terms, so
  momentum and breakout logic has more signal to trade, at still-small per-trade risk.
- MES for the very first live deploy: it is the least punishing contract available for
  shaking out plumbing and risk controls.

**Ladder:** MES (plumbing) → MNQ (primary) → NQ or ES (only when equity justifies it).

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
- **Deploy:** one Dockerized cloud VM, Prometheus + Grafana, structured logs, kill switch.

### Stage 1, multi-strategy

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
  position. Usage-based pricing means you buy exactly the ES/NQ/MNQ windows you need.
- **Schema matching is the highest-leverage anti-skew move.** Databento uses the same
  DBN schema for historical and live. Matching research and live schemas removes a whole
  class of backtest-vs-live divergence.
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
  data (e.g. ESZ5) is unambiguous; the stitched series is not. Default: volume/open-
  interest crossover roll with **ratio** back-adjustment (preserves percentage returns,
  avoids negative historical prices, unlike Panama/difference adjustment).
- **Book P&L on actual traded-contract prices, never the adjusted series.** Adjusted
  series manufacture phantom roll-gap P&L.
- Standardize on exchange nanosecond matching-engine timestamps. Know which timestamp
  each field is. Mixing exchange, gateway-send, and local-capture timestamps creates
  look-ahead or phantom latency. Verify each vendor's bar-labeling convention (timestamp
  = bar open vs bar close); an off-by-one there leaks the future into your signal.
- CME trades on Central Time with a session spanning the calendar day. Naive UTC or
  local bucketing misaligns sessions and daily bars. DST transitions are a live bug class.

---

## 5. Broker and execution

- **Start: Interactive Brokers** via **`ib_async`** (the maintained fork; original
  `ib_insync` is legacy). Mature API, a paper account on the identical interface, full
  automation explicitly allowed. Run IB Gateway headless with IBC because it force-
  restarts daily.
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

---

## 7. Risk and operations

Survival here is a risk-control and reliability problem, not an alpha problem.

- **Sizing:** fixed-fractional or ATR-based at **0.25-1% equity risk per trade**.
  Volatility-target the portfolio to a fixed annualized vol. Kelly is a *ceiling only*,
  used fractionally (1/4 to 1/2). Never full Kelly.
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

All of these must pass before real money. The last one blocks; it is not a nice-to-have.

1. Re-validate the chosen edge on **futures specifically**, on recent data (2022 onward),
   net of realistic **micro** costs. Do not accept a ported cash-equity result.
2. Run paper plus live-tiny across **at least one full roll cycle and one major macro
   event** (FOMC, CPI, or NFP) to shake out roll, DST, and halt bugs.
3. Measure all-in round-turn cost **from actual fills**: commission, exchange, NFA,
   realized slippage. Do not ship on assumed figures.
4. Get non-display market-data classification and Section 1256 / entity treatment
   confirmed in writing.
5. **Live fault-injection drill in a production-like environment:** pull the connection
   mid-position, force a partial fill, feed a stale tick, and confirm the kill switch
   and reconciliation behave. This gates go-live.

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
