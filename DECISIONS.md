# Decision Log

The decisions that still stand, oldest first. One entry per call that would be expensive
to reverse or that a future reader would otherwise have to re-derive.

Why this file exists: six weeks from now the *reasoning* behind a choice is gone even though
the choice remains. Logged during the session it costs almost nothing; reconstructed later
it is guesswork.

Entry format: decision, alternatives rejected, why, and how confident. Calls that were later
reversed have been cut; the audits that reversed them are kept, since the reasoning that
changed a decision is worth more than the decision it replaced.

---

## First deliverable is a harness, not a strategy

**Decision.** Phase 1 ships a backtest/validation harness whose gate is that it can
*reject* strategies, specifically, that it kills a strategy fit to pure noise and catches
a deliberately lookahead-biased one. Not a profitable strategy.

**Why.** Realistic net Sharpe for one robust retail futures strategy is 0.5 to 1.0, and
anything backtesting above ~2.0 on daily-or-slower index futures is an overfit, a
lookahead bug, or a cost bug. Confirming a true Sharpe of 0.5 takes roughly 15
years of data, so no live trial this year distinguishes skill from luck. Given that, the
scarce capability is not signal generation, it is honest rejection. A harness that cannot
kill a bad idea will bless one.

**Consequence.** The harness is also the portfolio piece and is asset-agnostic, so it gets
built once on MNQ rather than twice.

---

## Empirical probe of the NautilusTrader assumptions

**Method.** Not research, a direct install-and-import probe. Ran
`pip install "nautilus_trader[ib,databento]"` in a `python:3.12-slim` container and
imported the specific symbols the plan depends on. This is the difference between "an
the adapter is documented as mature" and "the adapter imports."

**Findings**:

- `nautilus_trader` latest is **1.231.0**, and it requires **Python >=3.12,<3.15** (per the
  PyPI metadata API).
- **The development environment predates that requirement**, so NautilusTrader cannot be
  installed against the system interpreter. Docker is the resolution, and it also pins the
  runtime to one version rather than leaving it to whatever a host happens to have.
- `FuturesContract` instrument type: **present.**
- Interactive Brokers adapter (`InteractiveBrokersDataClientConfig`,
  `InteractiveBrokersExecClientConfig`): **present**, but only after installing the `ib`
  extra. A bare `pip install nautilus_trader` fails with
  `ModuleNotFoundError: No module named 'ibapi'`. The extra pulls `nautilus_ibapi 10.45.1`
  (their vendored fork of the IB API, not the upstream `ibapi` package).
- Databento adapter (`DatabentoDataClientConfig`): **present** in the base install.
- `BacktestEngine`, `TradingNode`, `Strategy`, `TestClock`: **all present**, these are the
  concrete objects behind the one-code-path rule, so the invariant is structurally
  supported as claimed.
- Multi-timeframe support: `BarAggregation` exposes **18 members** including MILLISECOND,
  SECOND, MINUTE, HOUR, DAY, WEEK, MONTH, plus TICK/VOLUME/VALUE and their
  IMBALANCE/RUNS variants and RENKO. Comfortably covers the intraday-and-swing requirement.

**Consequences.**

1. Development must target **Python 3.12** (not the system 3.7) and run in Docker on this
   box. This makes the containerized deployment a requirement rather than a
   preference, which is fine, since it was already the plan.
2. Install spec is `nautilus_trader[ib,databento]`, not bare `nautilus_trader`. Pin the
   version.
3. Two of the three assumptions (IBKR adapter, multi-timeframe bars) are now **confirmed**.
   The third, **futures roll handling**, is only partly addressed: `FuturesContract`
   exists, but whether Nautilus performs continuous-contract stitching and back-adjustment,
   or expects us to supply an already-adjusted series, is **still open**. Given `CLAUDE.md`
   mandates volume/OI roll with ratio adjustment and P&L booked on real contract prices, we
   likely build that ourselves regardless. Keep the roll module in Phase 1 scope.

**Lesson worth generalizing.** A ten-minute install test settled what days of reading would
have answered less reliably. **For questions about tools you can execute, test rather than
read.** Reserve reading for judgment calls: markets, regulation, tradeoffs.

---

## Adversarial audit overturns five earlier calls

**Method.** The standing rules and the build plan were attacked along three hostile lines:
contradictions, hidden assumptions, and unstated omissions, and every load-bearing external
claim was then re-verified against its source before any finding was accepted. Full verdict
in the private audit record.

**INSTRUMENT REVERSED: MES is primary, not MNQ.** The original call had made MNQ primary.
The cause was two rules in `CLAUDE.md` contradicting each other, §7 mandated
0.25-1% equity risk per trade while §2's table sized contracts at 1-2%. At $8k with a
structural stop of ~0.25x daily range: **MES = $62-100 = 0.8-1.25% of equity (inside the
band); MNQ = $100-200 = 1.25-2.5% (outside).** MES is the only one of the two that fits the
stated rule. Decided on arithmetic, not preference. The risk band itself is widened to
0.5-2%, and "position-sizing granularity" is restated honestly: below $25k there is exactly
one available position size, so fixed-fractional sizing is *not expressible*, the choice is
which instrument's one-lot stop lands inside the band. ES/NQ is now marked aspirational.

**The single most important finding: the noise ceiling was applied to crypto and withheld
from futures.** `SE(Sharpe) ≈ sqrt(1/T_years)`; expected best of N noise trials
`≈ SE·sqrt(2 ln N)`. On a 4-year window SE≈0.50, so the noise ceiling is ~0.90 at N=5 and
~1.22 at N=20, **the entire 0.5-1.0 target band sits below it.** An honestly applied DSR
gate must therefore reject every result in the band, including a real one, which makes the
pressure to weaken the statistics structural rather than a matter of discipline. Fix:
validate on the **longest available ES/NQ history** (1997/1999 onward) with 2022-onward as a
regime check only; cap the trial budget *before looking* (10 per hypothesis); seed the
counter above zero for published ideas; and rewrite the Phase 2 gate as **"fails to be
rejected"** rather than "clears."

**`ib_async` REJECTED, architectural, not maintenance.** The Nautilus IB adapter executes
TWS requests via `ibapi` and Nautilus repackages `ibapi` for PyPI; `ib_async` appears
nowhere in its docs. Driving IB through a second client library alongside Nautilus
creates a second execution path, violating prime directive 1. Noted for the record:
`ib_async` genuinely *is* the maintained fork and `ib_insync` is archived, so this rejection
is about architecture only. Use the Nautilus `interactive_brokers` adapter.

**Databento live is not on the usage-based tier**.
Usage-based is historical-only; live starts at **Standard, $199/mo = $2,388/yr**, which also
*caps* L1 history at 12 months and L2/L3 at 1 month, the tier that unlocks live gives less
research history. Against a corrected ~$700/yr expected gross, that inverts the economics.
Decision: **Databento usage-based for historical + IBKR for live** through Phase 3, treating
the schema mismatch as a named logged risk, and upgrading only if Phase 2.5 *measures* a
divergence that changes a decision.

**Continuous futures: the framework supplies arithmetic, not machinery**. "The engine does not discover rolls, choose contracts, or infer roll prices:
that is the caller's responsibility." The continuous root is synthetic and cannot be traded.
Also: ratio adjustment goes through float in the hot path and can shift the raw price by 1
ULP, conflicting with exact-replay determinism, so the traded series uses
**`BACKWARD_SPREAD`** and ratio is reserved for return-series research. Open interest is not
in OHLCV bars and `statistics` cannot stream through `BacktestNode`, so roll dates are
precomputed offline as a versioned artifact.

**Two adapters default in opposite directions, the named lookahead bug class,
pre-installed**. Databento's `bars_timestamp_on_close` defaults **True**
(close-stamped); the IB adapter's documented setting is **False** (open-stamped). Both must
be set explicitly and asserted at startup. Also `handle_revised_bars` defaults False on IB,
silently dropping revisions. And **there is no 5-minute Databento bar**, only 1s/1m/1h/1d ,
so the ORB candidate uses native `ohlcv-1m`.

**Structural fixes.** Added **Phase 0 (price the project)** as blocking, because non-display
classification and account permissions were scheduled *last* yet can redirect everything;
monthly ceiling $75 through Phase 2, abort above $150/mo. Added **Phase 2.5
(measured-cost plumbing run)** because prime directive 5 demanded measured costs *before* any
live trading existed, real money, no edge required. Phase 5 now gates on **Phase 2.5, not
Phase 3**, resolving a deadlock: the plan's modal outcome is "no edge found," which meant
Phase 3 never happens, which stranded Phase 5 forever. Go-live gate split into Gate A
(pre-live) and Gate B (Phase 2.5, blocking).

**Expected outcome corrected, ~2x optimistic before.** $1,600 on $8k is 20%, implying ~40%
annualized vol at Sharpe 0.5, and the quoted $4,800 drawdown is 60% of the account, the
mandated drawdown halt would trip first. At a 17.5% vol target: **~+$700/yr with a ~$2,400
(30%) drawdown**, halt threshold 35% set *above* expected drawdown by construction.

**Blank parameters filled.** The audit's sharpest process finding was that every control
against the self-diagnosed dominant failure mode was unset. Now: weekly budget 8 hours; phase
budgets 10/80/40/20 hours; abort after **3** failed candidates; Phase 3 has an explicit
3-month calendar floor with a deferral clause if that horizon is unavailable.

**What the audit said the plan gets right**, worth preserving verbatim as calibration:
harness-before-strategy with a gate that is testable rather than a slogan, and the crypto
section actually proving the machinery is not decorative, it measured a 3.22 bps breakeven
against +1.14 bps gross, computed the noise ceiling for its own search, found its results
below it, and killed the idea. "Nearly every retail plan of this kind has no falsification
step at all. Do not dilute this in the revision."

---

## Fact verification against primary sources: one figure I published was wrong

**Method.** Primary sources read directly, not summarized: 17 CFR 4.41, NFA Rule
2-29 full text, 17 CFR 4.14, the CME Fee List (eff. 2026-01-01), the CME Non-Display
Licensing FAQ (Jan 2025), CME Derived Data License Fees, AMP Futures' margin table, IBKR
commissions, and Nautilus continuous-futures docs. Every claim below is labeled by the
document it came out of, and seven of those source captures are preserved verbatim in
the private research archive so the reading can be checked rather than trusted.

**CORRECTION, SPAN margin was understated ~2x in my own plan.** I had written ~$1.6 to 2.2k
MNQ / ~$1.3 to 1.6k MES and labeled it on the strength of a research pass. Actual
published maintenance margin: **MES $2,754, MNQ $4,217** (ES $27,548, NQ $42,174). One
overnight MNQ contract is **~53% of an $8k account, not ~25%.** The plan's conclusion ,
swing is capital-gated, survives and strengthens, but the number was wrong and it was wrong
in the direction of making the plan look more feasible than it is. Caveats retained: these
are one FCM's *maintenance* figures, initial is what gates entry and remains unverified.
Newly surfaced: AMP applies **25% overnight equity-index margin** from 5pm CST until shortly
after scheduled econ releases, which the sizing layer and kill switch must know about.

**NFA 2-29 does NOT bind me; CFTC 4.41 very likely DOES.** Read in full: every operative
subsection of NFA 2-29 scopes to "No FCM, IB, CPO or CTA **Member** or Associate," so
non-members are outside it, and its all-caps disclaimer is written to be signed by "(THE
MEMBER)," so **using it would falsely self-identify me as an NFA member.** By contrast 17 CFR
4.41(b)(1) reads "**No person** may present the performance of any simulated or hypothetical
commodity interest account...", 4.41(c)(1) expressly reaches internet publication, and
4.41(c)(2) applies "**regardless of whether** the CPO or CTA **is exempt from registration**."
So exemption is no defense; the live question is *status*. Action: ship the 4.41(b)(1)(i)
statement verbatim on any page showing hypothetical results. Open for counsel: whether a
public portfolio site constitutes "holding itself out generally to the public as a commodity
trading advisor" under 4.14(a)(10), a judgment about site copy, not a rule lookup.

**CME non-display does NOT flow through the vendor.** "All Non-Display Use must be licensed
**directly with CME Group under an ILA**," and non-display expressly includes use within
automated trading systems. But there is a solo tier: **User Non-Display Category A $457/yr**,
**Managed User Non-Display Category A $208/yr**, versus Category A1 Basic $609, not the
$29,280 distributor figure. Critically: **"Use of only Historical Information in Non-Display
Applications is licensed discreetly and is not reportable at this time."** So backtest-only
phases are the cheap phase and the license spend begins when live data does. Budget
$208 to 609/yr per exchange once live, and get the tier assigned in writing via
marketdata@cmegroup.com.

**Publishing data-derived artifacts is a Derived Data License question, and the only waiver
does not cover a portfolio project.** CME requires verifying whether a Derived Data License
Agreement is needed for derivative works; the sole waiver is for accredited academic
institutions and government agencies. Databento's binding redistribution terms were **never
read**, the User Agreement, license-manager, and pricing pages were all JS-gated. The plan's
existing posture is now *supported* rather than assumed, and it is scoped precisely: **never
redistribute exchange- or vendor-licensed market data** (CME, Databento), and publish
normalized metrics only. Public-domain series carrying no such terms are outside the rule ,
the demo suite ships Shiller's monthly S&P 500 series for that reason. **Use synthetic or
public-domain data for any runnable demo**, never a vendor extract.

**Nautilus roll handling is better than I assumed, and still shifts real work onto me.**
`ContinuousFutureAdjustmentType` covers BACKWARD/FORWARD × SPREAD/RATIO with documented
cumulative-adjustment formulas, a validated strictly-increasing transition chain, and
auto-synthesis of the continuous root. But **I supply the roll table**, transition times,
pre/post instrument ids, and pre/post prices for every roll, and "the continuous target bar
type must be internally aggregated." Also: `ts_init` must be the interval **close** "to
prevent the complete bar from becoming visible before it formed," which means Nautilus hands
me the lookahead guard only if the timestamps are set right. Roll-table generation is a Phase
1 deliverable, not a library call.

**MBT/MET remains UNVERIFIED and the block is total.** CME's spec page returned "This IP
address is blocked due to suspected web scraping activity"; Barchart returned N/A for contract
size, tick size, trading hours, volume, and open interest. Only point values came through
(MBT $100, MET $50) and IBKR confirms both are tradable. **Contract size is precisely the
field nobody could read, and sizing granularity is the whole objection to the MBT path**, so
spend no engineering effort on the crypto option until a human opens the CME product page in
a browser. Five minutes of human browsing closes this.

**Micro round-turn cost: still NOT verified**, and it is the highest-leverage remaining gap.
The captured IBKR page has a full worked ES example (execution $0.85 + exchange $1.38 +
clearing $0.00 + regulatory $0.00 = **$2.24**) but **no micro row**. The crypto rejection in
The crypto comparison turns on a 0.36 bps MNQ round-turn figure that is therefore unverified. Do not
treat it as fact; measure it from a real fill in Phase 2.5.

---

## Phase 1 module designs collide with the Phase 1 budget by roughly 5x

Five module designs were drafted independently for `data/`, `data/continuous/`, `engine/`,
`risk/`, and `validation/`, 333 interface definitions in all. They were never reconciled
against each other and no adversarial pass ran over them, which matters because the plan
audit found real errors in exactly this kind of unreviewed design work. They are superseded
by the reconciled and buildable Phase 1 plan, which is held privately.

**The scope problem they exposed, which outlived them.** Their own effort estimates sum to roughly **10-14 focused
weeks** (continuous 3-5 days, data 3-5 days, engine 2-3 weeks, risk 4-6 sessions, validation
3-4 weeks). §9 budgets **80 hours** for Phase 1. At 8 hours/week that is 10 weeks, so the
designs assume something closer to full-time. **Reconcile by cutting scope, not by silently
extending the budget**, this is exactly the "infinite infrastructure polish" failure mode
the plan names as dominant.

**Two design findings worth keeping at the top level:**
- The **highest-value single test in Phase 1** is the paired check that a noise strategy is
  rejected at its true N=200 and accepted at an understated N=5. It demonstrates both that
  the harness works and why the trial counter must be tamper-evident, and it is the
  strongest artifact the phase can produce.
- Write the continuous-contract **proportional-recovery property test first**; it is the only
  single invariant catching both major roll-bug classes.

Independently confirmed here as well: neither `databento` nor `nautilus_trader` installs
against the system interpreter, the same environment constraint the direct probe found
earlier, which is why the runtime is pinned in Docker.

---

## Horizon research: MNQ fails INTRADAY too, and futures swing is closed at $8k

**Third revision of the instrument decision in one day.** MNQ → MES → now **M2K or MES
intraday, ETF shares for swing**. Each revision was forced by arithmetic, and each time the
prior number was wrong in the direction of making the plan look more feasible. I recomputed
this one independently before applying it; the figures reproduce exactly.

**MNQ is outside the risk band even intraday.** Using measured ATR multiples rather than the
hand-set "0.25x daily range" I used earlier:

| Instrument | 0.25xATR intraday | % of $8k | 2xATR swing | % of $8k |
|---|---|---|---|---|
| MNQ | $217 | **2.72%** ✗ | $1,738 | **21.7%** ✗ |
| MES | $107 | 1.33% ✓ | $854 | **10.7%** ✗ |
| **M2K** | **$60** | **0.74%** ✓ | $476 | 5.95% ✗ |
| MYM | $75 | 0.93% ✓ | $598 | 7.47% ✗ |

The original "MNQ: sane capital ~$8-15k" was optimistic by **~3x for intraday and ~20x for
swing**, the most load-bearing wrong number the steering file contained. **M2K (Micro Russell
2000) has the best risk fit** at 0.74%, with MNQ's cheaper $0.50 tick. Caveat: thinner
overnight liquidity makes its 1-tick slippage assumption the least trustworthy, measure it.

**Swing in futures is CLOSED, not "largely gated."** Three gates, and the one everybody quotes
is the weakest: margin utilization 52.7% (passes), **risk budget 21.7% of equity (fails by
11-43x)**, carry $1,504/yr = 18.8% (fails). Even M2K's swing stop is 5.95%, triple the ceiling.
No micro contract can hold a multi-day position at this capital.

**The workaround is ETF shares, and it is strictly better on arithmetic, not a compromise.**
4 shares of QQQ at $723.85 with a 2xATR ($20.27/share) stop = $81 = **1.01% of $8k**, on target
within 25 bp. MNQ's only reachable non-zero size overshoots by 21x. Shares restore the
granularity one indivisible micro contract destroys. Tradeoffs accepted explicitly: **Section
1256 60/40 does not apply to ETF shares** (the main thing given up), **PDT applies to ETF day
trades** so that sleeve must be structurally swing-only, and ETFs have a real close-to-open gap
where futures largely do not.

**Two cost findings that constrain strategy shape before any code is written.**
1. **~1.09 round turns per trading day is the ceiling** at a 10%-of-equity annual cost budget
   ($2.90/RT on MNQ/M2K → 275 RT/yr). Not 3, not 5. This kills every multi-entry intraday shape
   in advance. **MES is worse despite the deeper book**, its $1.25 tick makes a round turn
   $4.40, so only 181 RT/yr (0.72/day) and 13.9% of equity at 252 RT.
2. **Cost per calendar day is roughly EQUAL across horizons**, contradicting the usual framing:
   intraday $2.90/day vs swing $5.98/day (carry-dominated). Swing is not cheaper; the cost
   migrates to the financing line where it is easy to forget to model. And **IBKR pays zero
   interest on the first $10,000 of cash**, so the textbook T-bill offset does not exist here.

**Architecture decision.** Horizon is not a Strategy parameter, it is a label selecting five
injected policies (BarPlan, SessionPolicy, ExitPolicy, SizingPolicy, ExecutionPolicy), and the
strategy is constructed with none of them. The strategy returns **intent** (`TargetPosition`
with `stop_atr_mult` in **ATR units, never points or dollars**), never orders, because a
strategy that submits orders must know its TIF, hence its session, hence its horizon, and the
abstraction has already leaked. Rejected: `Strategy(horizon=...)` (an `if` in the hot path) and
separate Day/Swing base classes (duplicated logic that drifts, alpha welded to horizon).

**The design consequence I most want to keep:** *the sizer must be able to refuse.* When a
strategy's stop cannot be expressed inside the risk band, the correct behavior is to decline to
arm it and say why, not to round to 1 contract. That single behavior would have caught the
original MNQ decision automatically, without three rounds of human-noticed arithmetic.

---

## Observability designed; its own critique overturned 30 items

The full design (89 checkboxes across 12 sections) is held privately until the phase it
covers is underway; it is split into private ops and a public surface with an enforced
sanitization boundary. Its
claims were settled by execution rather than assertion: the palette validator was run under
node 16, Lo's Sharpe confidence intervals and days-to-significance were reproduced in Python,
a 20k-run Monte Carlo was run, and a timezone dispute was settled arithmetically.

**Decision: the Phase 2.5 observability minimum is 13-15 hours with ZERO containers**, fitting
inside the 20-hour budget and running on a 2GB VM. Prometheus/Grafana stay in Phase 4 because
they buy *diagnosis, not safety*, consistent with the earlier reclassification. The full
bespoke static-site build defers to Phase 5 at ~10% of the cost via Quarto.

**The alerting corrections that would have burned me.** Its critique found six ways the
proposed alerts would have caused fatigue and then been muted:
- **Page on the kill-switch TRANSITION, not the latched level.** The kill switch stays engaged
  until manually reset, so alerting on the level with a 30-minute repeat sirens all night after
  you already acked. Called "the single most certain mute-inducing alert" in the designs.
- **The session gate must fail OPEN.** Gating staleness alerts on a venue-session series means
  that if the session subscription dies, the `and` yields empty and **every staleness page
  silently stops firing**, reintroducing the exact failure class the design existed to prevent.
- **Six paging rules, not seventeen.** One design budgeted six in prose and shipped 17.
- `inhibit_rules` with `equal: [instance]` never match an `absent_over_time` source (its output
  carries only equality-matcher labels), so process death would have delivered 4-5 simultaneous
  pages instead of one.
- Margin freshness must **not** gate the margin page, that polarity makes the alert vanish
  exactly when the account feed breaks, leaving IBKR auto-liquidation unmonitored. Ship a
  separate `AccountStateStale` page.
- **Slippage never pages.** Cost drift means "distrust today's fills and investigate," which is
  a daily-summary item.

**Statistical-honesty corrections**, all reproduced numerically: Wilson interval half-widths
were **2x too large** (±20.1pp at n=20, not ±40); there is **no "Measured" tier at n=100** ,
profit factor gates at **n≥400** (a 400-rep bootstrap put 76.7% of samples excluding 1.0); use
an **iid** bootstrap rather than block (15% wider on an interval spanning [-3.17, 4.67]); and
the hero number prints the Sharpe **band**, never a point estimate. Also measured: **23.1% of
30-trade runs show profit factor below 1.0 on a genuinely profitable strategy**, which is the
whole argument for minimum-sample gating.

**Leak corrections on the public surface:** "R + ticks" is the same leak as "R + dollars" ,
**one normalization per trade, ever**, or the account size is recoverable. Margin utilization is
ops-private because SPAN maintenance is public, so publishing the fraction inverts to equity.
The numeric-range sanitization gate **failed to catch its own $8,123.45 canary**, so gate 2
became a field-name allow-list instead.

**Two open items it could not close**, both flagged rather than guessed:
1. Whether CME encodes the daily maintenance break as `Halt`, `Pause` or `Close`, the two
   outcomes are "pages every night" or "the flagship inverse alert is dead code."
2. **Nautilus's IB docs recommend `DockerizedIBGateway` and never mention IBC**, while
   The standing rules and the budget both specify IBC. Resolve before building restart
   instrumentation around the wrong mechanism.

It also **deleted one design's centerpiece** (Databento `status`-schema session truth) on three
grounds: unpriced entitlement against the verified $75/mo ceiling, unverified halt encoding, and
a fail-closed mode that disarms every staleness page. `exchange_calendars` plus a hardcoded
16:00-17:00 CT window gets ~95% of the value for $0.

---

## Costs move inside the validator, reversing a documented scope boundary

**Decision.** The gate gets a fifth check, `cost_survival`, which charges a per-round-turn
cost against turnover and gates on net/gross Sharpe retention. The README previously stated
the opposite as a deliberate limit: "the gate validates a return series, not a trading
system, costs enter this project as a constraint on strategy shape, not as a term in the
validator."

**Why the reversal.** The boundary was defensible for the other four checks, which all ask
whether a number is real. It was not defensible for the gate as a whole, because the gate
returns ACCEPT. A strategy can pass selection, leakage, lookahead, and walk-forward and
still be worthless, and the four-check gate had no way to say so. Prime directive 5 says
costs are not allowed to stay assumed; leaving them outside the only component that renders
a verdict is how an assumption stays unexamined.

**Alternatives rejected.** Gating on break-even cost against a safety multiple of what you
pay was more directly decision-useful but introduced a threshold shape used nowhere else in
the gate; retention mirrors walk-forward efficiency, so the gate reads consistently and has
one fewer convention to defend. Break-even is still reported, just not gated on.

**What is measured and what is assumed.** The break-even cost per round turn is computed
from the return series and assumes nothing. The $2.90 all-in micro round turn it gets
compared against is still the unverified inference it always was, so the check's hard output
is the break-even and its soft output is the comparison. This is deliberate: the check is
useful before the cost figure is ever verified.

**A demo that was cut for being untrue.** The intended illustration was that higher trade
frequency flatters the gross Sharpe while destroying the net one. It held on one seed and
failed on the other 39, so the claim was dropped rather than seeded into existence. What
survives is weaker and true: two variants post ordinary, indistinguishable gross Sharpes,
and only the retention ratio separates them.

**Confidence.** High on the arithmetic, which is now run rather than asserted, and the
10%-of-equity budget ceiling reproduces at 276 round turns/year. Low on the $2.90.
