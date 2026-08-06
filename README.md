# QuantDesk

An automated-trading system for CME micro equity-index futures, built around one thesis:

> **The first deliverable is not a profitable strategy. It is a harness that can honestly
> reject one.**

Most retail trading projects show a single flattering equity curve. This one leads with the
opposite instinct — the machinery that *kills* a strategy that only looks good — because
that is the part that separates someone who has understood backtest overfitting from someone
who has not.

## See it in 60 seconds — runnable demos

```bash
pip install -r requirements.txt
cd demo && python3 gate_demo.py     # the validation gate: ACCEPT/REJECT with a reason per check
python3 run_all.py                  # or: every demo + all 23 tests + every chart, one command
```

The four checks below compose into a single **validation gate** (`demo/gate.py`) that takes a
strategy and returns ACCEPT or REJECT with a reason per check — the thesis as a working tool,
not four separate examples. It rejects an overfitting artifact (4/4 checks fail) and accepts a
clean one, and it never returns a silent pass: a missing input is SKIP, an undefined score is
FAIL.

Each check is also its own self-contained demo. numpy for the logic, matplotlib for the
charts, deterministic, no market data or broker needed.

| Demo | Shows | Chart |
|---|---|---|
| [`deflated_sharpe_demo.py`](demo/) | Best-of-200 pure noise "finds" a 1.9 Sharpe; the **Deflated Sharpe Ratio** rejects it, and still passes a real edge | `noise_sharpe_distribution.png` |
| [`purged_cv_demo.py`](demo/) | Shuffled k-fold leaks (0.60 accuracy); **purge + embargo** collapses it to the honest 0.50 | `purged_cv_leak.png` |
| [`lookahead_detector_demo.py`](demo/) | A same-bar-fill **lookahead peek** prints a +20 Sharpe from zero edge; two detectors catch it | `lookahead_equity.png` |
| [`walk_forward_demo.py`](demo/) | In-sample edge (+0.87) evaporates out-of-sample (+0.16); **walk-forward efficiency 0.18** | `walk_forward_efficiency.png` |

Each has a test file (`test_*.py`, plain-assert, run directly) with a headline test that
encodes the point. See [`demo/README.md`](demo/README.md).

## The plan behind the demos

The demos are runnable slices of Phase 1 of a fully specified build. Status: **planning and
research complete, the harness specified to the file level, zero production code written.**

> **This repo is PRIVATE and not ready to publish.** All commits are authored
> `vzc7636@gmail.com`. Complete
> [`docs/AUTHORSHIP-TODO.md`](docs/AUTHORSHIP-TODO.md) before any public push — publication
> is a one-way door and a history rewrite does not un-fork a published repo.

## Read in this order

| File | What it is |
|---|---|
| [`docs/NEXT-STEPS.md`](docs/NEXT-STEPS.md) | **Start here.** Ordered next actions: complete repo hygiene, then Phase 0. |
| [`CLAUDE.md`](CLAUDE.md) | **Standing rules.** Prime directives, instrument decision, architecture, data, broker, strategy policy, risk. The constitution — rarely changes. |
| [`PLAN.md`](PLAN.md) | **The ordered sequence.** Phases 0–5 with gates, effort budgets, and explicit skip lists. Changes as decisions land. |
| [`DECISIONS.md`](DECISIONS.md) | **Append-only decision log.** Records what was decided, what was rejected, and `[verified]` vs `[inference]`. |
| [`docs/observability-design.md`](docs/observability-design.md) | Ops monitoring + public dashboard, 89 checkboxes. |
| [`docs/phase1-module-designs.md`](docs/phase1-module-designs.md) | Module-level designs. *Unreconciled and unreviewed — input, not settled design.* |
| [`docs/research/`](docs/research/) | Six curated syntheses + preserved primary-source captures. |
| [`docs/research/raw/INDEX.md`](docs/research/raw/INDEX.md) | All 51 raw agent results, 1.53 MB. Provenance for every claim. |

## The three things that matter most

**1. One code path for backtest and live.** The strategy consumes an abstract event
interface; backtest and live differ only by which `DataFeed`, `ExecutionHandler`, and `Clock`
are injected. Divergent codebases drift and then lie to you — named the number-one killer of
retail systems.

**2. The first deliverable is a harness that can honestly *reject* a strategy, not a
profitable strategy.** Its gate: feed it a strategy fit to pure noise and confirm rejection;
feed it a deliberately lookahead-biased strategy and confirm it is caught. The single
highest-value test in the whole phase is the paired check that a noise strategy is rejected
at its true trial count (N=200) and accepted at an understated one (N=5) — that proves both
that the harness works and why the trial counter must be tamper-evident.

**3. Realistic net Sharpe is 0.5–1.0, and anything above ~2.0 backtested is a bug report.**
On a 4-year window the noise ceiling for a small honest search is ~0.90–1.22, which sits
*above* the entire target band — so validation runs on the longest available ES/NQ history and
the trial budget is capped before looking.

## Current decisions, in brief

- **Instrument:** M2K or MES intraday (0.74% / 1.33% one-lot risk at $8k). MNQ is **outside**
  the risk band even intraday at 2.72%. Futures swing is **closed** at this capital — the
  swing sleeve runs in ETF shares until ~$25–30k.
- **Stack:** NautilusTrader + Databento (historical) + IBKR live, via the Nautilus
  `interactive_brokers` adapter. Python 3.12 in Docker.
- **Crypto:** deferred. If ever, CME MBT only — measured intraday crypto edge sits below
  transaction cost.
- **Product:** an execution/automation bridge, gated on Phase 2.5 rather than on finding an
  edge, because it sells plumbing reliability.

Full reasoning, including five decisions that adversarial review overturned, is in
`DECISIONS.md`.

## Honest framing

At under $10k, a genuine Sharpe 0.5 is roughly **+$700/yr with a ~$2,400 (30%) drawdown en
route**, and confirming a true Sharpe of 0.5 takes on the order of 15 years of data.
**Profitability at this capital is proof-of-concept, not income.** The engineering, the
falsification record, and the eventual product are the durable assets — and they survive the
strategy not working.

## Restoring from a bundle

```bash
git clone quantdesk-FINAL.bundle quantdesk
cd quantdesk && git log --oneline
```
