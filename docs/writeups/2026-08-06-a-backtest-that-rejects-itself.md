# I built a backtest that rejects itself

*2026-08-06*

Most trading-strategy projects you see online share a shape: a clever signal, a backtest, an
equity curve sloping up and to the right, a headline Sharpe of 2-point-something. I set out
to build the opposite, a system whose first deliverable is not a profitable strategy but a
**harness that can honestly reject one.** This post walks through four small, runnable pieces
of that harness, each of which takes data with *zero true edge* and shows a standard method
being fooled by it while a rigorous method is not.

The reason for the inversion is simple: on liquid index futures, a genuinely robust retail
strategy realistically nets a Sharpe around 0.5 to 1.0. Anything a backtest reports much above
that is almost always an artifact, of selection, leakage, lookahead, or overfitting, not a
discovery. So the skill that matters is not finding high numbers. It is being able to tell a
real number from a fake one, and being willing to throw the fake ones away. Here are the four
ways a backtest lies, and how to catch each.

## 1. Selection: the best of many noise strategies looks brilliant

Generate 200 strategies whose true edge is exactly zero, random, mean-zero returns, and
keep the one with the highest Sharpe. Its annualized Sharpe comes out near **1.9**. Nothing
was learned; you simply selected the right tail of a distribution centered on zero.

The Probabilistic Sharpe Ratio (PSR) asks "is this Sharpe distinguishable from zero given the
sample?" and answers 0.996, accept. But PSR never asked how many strategies you tried. The
**Deflated Sharpe Ratio** does: it benchmarks the winner not against zero but against the
*expected maximum* Sharpe that 200 noise trials hand you for free. Against that bar, the
winner scores 0.436, rejected. Crucially, when I feed DSR a genuinely-edged strategy in the
same 200-trial context, it passes it (0.993). It discriminates; it does not blanket-reject.

*(`harness/deflated_sharpe.py`. The winner sits at the 99.5th percentile of the noise pile ,
see `noise_sharpe_distribution.png`.)*

## 2. Leakage: shuffled cross-validation reads tomorrow's answer

Financial labels span time, a label is often a return over the *next* h bars. Split such
data with ordinary **shuffled** k-fold and a test point's immediate time-neighbors scatter
into the training set, carrying overlapping label windows with them. The model effectively
sees the answer. On my leak-prone synthetic set, shuffled k-fold reports 0.60 accuracy
against a 0.586 no-skill baseline, "skill." Apply **purging** (drop training samples whose
label window overlaps a test sample) plus an **embargo**, and it collapses to 0.504, a coin
flip, which is the truth. The 0.096 gap was pure leakage.

*(`harness/purged_cv.py`.)*

## 3. Lookahead: booking the bar you traded on

The most common retail bug is the same-bar fill: compute a signal from bar *t*'s close, then
"execute" at that same close, a price you do not know until the bar is over. I built it on
purpose. A trailing-momentum rule on a random walk, filled same-bar, prints a Sharpe of
**+20.9**, because `sign(r)·r` equals `|r|`, positive every single bar. Fill the identical
signal at the *next* bar's open, as you actually could live, and the Sharpe is +0.28: momentum
has no edge on a random walk, which is correct. Two detectors flag the cheat, a fill-timing
audit (the +20-point gap is the signature) and a shuffle test. The equity curves say it best:
same signal, one grows \$1 into \$125,000, the other wanders around \$1.

*(`harness/lookahead_detector.py`, `lookahead_equity.png`.)*

## 4. Overfitting: in-sample edge that does not survive

Give an optimizer 59 lookback parameters to choose from and it will always "find" a good one
in-sample, even on noise. Walk-forward analysis freezes each window's chosen parameter and
trades it on the next, unseen window. Across 8 splits, mean in-sample Sharpe was +0.87; mean
out-of-sample Sharpe was +0.16. Walk-Forward Efficiency (OOS/IS) of **0.18**, most of the
apparent edge was the optimizer fitting the past, and it evaporated.

*(`harness/walk_forward.py`, `walk_forward_efficiency.png`.)*

## What ties them together

Selection, leakage, lookahead, overfitting. Each demo starts from data whose true edge is
*provably* zero, so the naive result is provably wrong, which is exactly what makes them a
fair test of the harness rather than a story I tuned to a conclusion. Every demo ships with a
test whose headline case asserts the rejection.

This is Phase 1 of a larger, fully-specified build (a live-parity trading engine on CME micro
futures). But the four ideas above are the load-bearing part, and they are the part I would
want to be judged on. A project that can produce a beautiful equity curve proves very little.
A project that can look at its own beautiful equity curve and correctly call it noise, that
is the one worth trusting with real money, later, if any of it survives.

## Honest status

No production trading code yet, and no claim of a profitable strategy, deliberately. At the
capital this is designed for, a real edge would earn a few hundred dollars a year against a
multi-thousand-dollar drawdown; profitability here is proof-of-concept, not income. The
engineering and the falsification discipline are the durable assets, and they are what these
demos show.

*Code: `harness/`. Standing rules: `CLAUDE.md`. Reasoning: `DECISIONS.md`.*
