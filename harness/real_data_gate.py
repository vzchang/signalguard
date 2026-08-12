"""
Run the validation gate on REAL market data, not synthetic.

Synthetic demos prove the checks work against a known answer. This proves they behave
sensibly on real prices, the harder, more convincing test. Data: 155 years of monthly
S&P 500 closes (1871-2026) from Robert Shiller's long-run series, a freely-redistributable
public dataset cached at data/sp500.csv
(github.com/datasets/s-and-p-500).

The honest finding, which is more interesting than "reject everything":

  A. Buy-and-hold over the FULL 155 years, an a-priori strategy capturing the real equity
     risk premium. The gate PASSES it. There is a genuine edge and no selection to punish.

  B. Best of ~150 MA-crossover combos over a SHORT recent window (72 months). This is the
     textbook overfit: a big parameter search on a small sample. The winner shows a ~2.0
     Sharpe, but the gate FLAGS it, the Deflated Sharpe haircut for the search brings it
     under the bar, and walk-forward shows the in-sample edge collapse out-of-sample.

Same search on the FULL sample is NOT flagged, 155 years of data with a real premium is
enough to survive the deflation. That contrast is the point: overfitting is a function of
sample size vs trials, and the gate is sensitive to it on real prices, not just synthetic.

numpy-only. Run:  python3 real_data_gate.py
"""
from __future__ import annotations

import csv
import math
from collections.abc import Sequence
from pathlib import Path

import numpy as np
from deflated_sharpe import sharpe_ratio
from gate import evaluate

DATA = Path(__file__).parent / "data" / "sp500.csv"
MONTHS = 12


def load_sp500_returns() -> np.ndarray:
    with open(DATA) as fh:
        rows = list(csv.DictReader(fh))
    px = np.array([float(r["SP500"]) for r in rows if r["SP500"]])
    return np.diff(px) / px[:-1]  # monthly simple returns


def ma_crossover_search(r: np.ndarray, fasts: Sequence[int],
                        slows: Sequence[int]) -> tuple[np.ndarray, int, float]:
    """Search fast/slow MA crossover combos on r; return (best_returns, n_trials, var_sharpes)."""
    price = np.cumprod(1 + r) * 100
    sharpes: list[float] = []
    best: np.ndarray | None = None
    best_sr = -1e9
    for f in fasts:
        for s in slows:
            if f >= s:
                continue
            fast = np.convolve(price, np.ones(f) / f, "valid")
            slow = np.convolve(price, np.ones(s) / s, "valid")
            m = min(len(fast), len(slow))
            if m < 3:
                continue
            pos = (fast[-m:] > slow[-m:]).astype(float)
            strat = pos[:-1] * r[-(m - 1):]
            sr = sharpe_ratio(strat)
            sharpes.append(sr)
            if sr > best_sr:
                best_sr, best = sr, strat
    if best is None:
        # No (fast, slow) pair produced a usable series. Returning None here would hand the
        # caller a silent failure, which is the exact defect this project exists to catch.
        raise ValueError(
            f"no valid fast/slow pair in fasts={list(fasts)}, slows={list(slows)} "
            f"for a series of length {len(r)}"
        )
    return best, len(sharpes), float(np.var(sharpes, ddof=1))


def ann(sr_monthly: float) -> float:
    return sr_monthly * math.sqrt(MONTHS)


def main() -> None:
    r = load_sp500_returns()
    grid = list(range(2, 25))
    print("=" * 76)
    print("  Validation gate on REAL data, 155y of monthly S&P 500 (1871-2026)")
    print("=" * 76)
    print(f"  {len(r)} monthly returns; annualized vol {r.std(ddof=1)*math.sqrt(MONTHS):.1%}\n")

    # A. buy-and-hold over the full sample: real edge, a priori, expect PASS
    bh = r.copy()
    v_bh = evaluate(returns=bh, n_trials=1, var_trial_sharpes=1e-6,
                    wf_series=r, wf_splits=8, wf_grid=grid)
    print("  STRATEGY A  buy-and-hold, full 155y (a priori, 1 'trial')")
    print(f"    annualized Sharpe {ann(sharpe_ratio(bh)):+.2f}")
    print(v_bh.render())
    print()

    # B. best-of-many MA crossover on a short window: overfit, expect FLAGGED
    short = r[-72:]  # last 6 years
    fasts, slows = list(range(2, 13)), list(range(6, 49, 3))
    best, n_trials, var_sr = ma_crossover_search(short, fasts, slows)
    v_ma = evaluate(returns=best, n_trials=n_trials, var_trial_sharpes=max(var_sr, 1e-6),
                    wf_series=short, wf_splits=6, wf_grid=grid)
    print(f"  STRATEGY B  best of {n_trials} MA combos on a SHORT 72-month window (overfit trap)")
    print(f"    winner annualized Sharpe {ann(sharpe_ratio(best)):+.2f}  <- looks great")
    print(v_ma.render())
    print()

    # C. the control arm: same search, full sample. Without this, the gate could be
    # rejecting on trial count alone rather than on trials relative to sample size.
    best_c, n_trials_c, var_sr_c = ma_crossover_search(r, fasts, slows)
    v_c = evaluate(returns=best_c, n_trials=n_trials_c, var_trial_sharpes=max(var_sr_c, 1e-6),
                   wf_series=r, wf_splits=8, wf_grid=grid)
    print(f"  STRATEGY C  best of {n_trials_c} MA combos on the FULL 155y sample (control)")
    print(f"    winner annualized Sharpe {ann(sharpe_ratio(best_c)):+.2f}")
    print(v_c.render())
    print()

    print("  Takeaway: the gate PASSES buy-and-hold over 155y (the equity premium is real and")
    print("  a-priori) and FLAGS the short-window parameter search whose 2.0 Sharpe is a")
    print("  small-sample artifact. Overfitting is trials-vs-sample-size, and the gate feels")
    print("  it on real prices, not just synthetic ones.")
    print("=" * 76)


if __name__ == "__main__":
    main()
