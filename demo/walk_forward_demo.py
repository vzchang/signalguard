"""
Walk-forward efficiency: how much in-sample performance survives out-of-sample.

The third check in the harness. You optimize a parameter on a training window, then trade
that frozen parameter on the next (unseen) window, roll forward, and repeat. Walk-Forward
Efficiency (WFE) = out-of-sample Sharpe / in-sample Sharpe. WFE near 1 means the in-sample
performance was real; WFE near 0 (or negative) means it was curve-fit and evaporated.

This demo runs walk-forward on an OVERFIT-PRONE strategy (many parameters searched, little
real signal) and shows the OOS Sharpe collapsing far below the IS Sharpe across windows --
the visual signature of overfitting. Deterministic, numpy-only.

Run:  python3 walk_forward_demo.py
"""
from __future__ import annotations
import math
import numpy as np

TRADING_DAYS = 252


def sharpe(x: np.ndarray) -> float:
    sd = x.std(ddof=1)
    return 0.0 if sd == 0 else float(x.mean() / sd * math.sqrt(TRADING_DAYS))


def make_returns(n: int, rng: np.random.Generator) -> np.ndarray:
    """Random-walk daily returns: no persistent structure, so any 'best' lookback is luck."""
    return rng.normal(0.0, 0.01, n)


def strategy_returns(r: np.ndarray, lookback: int) -> np.ndarray:
    """
    A momentum rule parameterized by `lookback`: position = sign of the trailing sum over
    `lookback` bars, applied to the next bar. next-bar fill, no lookahead. The parameter is
    what gets optimized in-sample and frozen out-of-sample.
    """
    if lookback < 1:
        lookback = 1
    trail = np.array([r[max(0, i - lookback):i].sum() for i in range(len(r))])
    pos = np.sign(trail)
    return pos[:-1] * r[1:]


def best_lookback(r: np.ndarray, grid) -> tuple[int, float]:
    best_lb, best_sr = grid[0], -1e9
    for lb in grid:
        sr = sharpe(strategy_returns(r, lb))
        if sr > best_sr:
            best_sr, best_lb = sr, lb
    return best_lb, best_sr


def walk_forward(r: np.ndarray, n_splits: int, grid):
    """
    Anchored-rolling walk-forward. Each split: optimize lookback on the train window, apply
    it frozen to the immediately following test window. Return per-split (is_sr, oos_sr).
    """
    n = len(r)
    fold = n // (n_splits + 1)
    rows = []
    for i in range(n_splits):
        tr = r[: fold * (i + 1)]
        te = r[fold * (i + 1): fold * (i + 2)]
        lb, is_sr = best_lookback(tr, grid)
        oos_sr = sharpe(strategy_returns(te, lb))
        rows.append((lb, is_sr, oos_sr))
    return rows


def main() -> None:
    rng = np.random.default_rng(20260806)
    r = make_returns(3000, rng)          # ~12y daily, zero true edge
    grid = list(range(2, 61))            # 59 candidate lookbacks -> lots of room to overfit
    rows = walk_forward(r, n_splits=8, grid=grid)

    is_srs = np.array([x[1] for x in rows])
    oos_srs = np.array([x[2] for x in rows])
    wfe = oos_srs.mean() / is_srs.mean() if is_srs.mean() != 0 else float("nan")

    print("=" * 72)
    print("  Walk-forward efficiency -- how much in-sample edge survives out-of-sample")
    print("=" * 72)
    print(f"  {len(grid)} lookbacks searched per window; random walk (true edge = ZERO)\n")
    print("  split   chosen LB   in-sample SR   out-of-sample SR")
    for i, (lb, is_sr, oos_sr) in enumerate(rows, 1):
        print(f"    {i:>2}        {lb:>3}        {is_sr:+7.2f}        {oos_sr:+7.2f}")
    print()
    print(f"  mean in-sample Sharpe      : {is_srs.mean():+.2f}   <- optimization always finds 'edge'")
    print(f"  mean out-of-sample Sharpe  : {oos_srs.mean():+.2f}   <- it does not survive")
    print(f"  walk-forward efficiency    : {wfe:+.2f}   (OOS/IS; ~1 = real, ~0 = curve-fit)")
    print()
    print("  Takeaway: searching 59 lookbacks guarantees a great in-sample Sharpe on pure")
    print("  noise; walk-forward shows it collapse out-of-sample. WFE is the number that")
    print("  separates a discovered edge from an optimizer fitting the past.")
    print("=" * 72)


if __name__ == "__main__":
    main()
