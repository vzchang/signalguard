# QuantDesk

Planning and research for an automated trading system on CME micro equity-index futures,
designed so the trading core can later become a product.

**Status: planning complete, zero application code written.** Everything here is documents.

> **This repo is PRIVATE and not ready to publish.** All commits are currently authored
> `vzc7636@gmail.com`. Complete
> [`docs/AUTHORSHIP-TODO.md`](docs/AUTHORSHIP-TODO.md) before any public push — publication
> is a one-way door and history rewrites do not un-fork a published repo.

## Read in this order

| File | What it is |
|---|---|
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
git clone quantdesk-FINAL-YYYYMMDD.bundle quantdesk
cd quantdesk && git log --oneline
```
