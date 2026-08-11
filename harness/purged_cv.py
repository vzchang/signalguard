"""
Purged K-Fold cross-validation: why plain k-fold lies on time series.

The second pillar of an honest backtest, alongside the Deflated Sharpe Ratio.

Premise
Financial labels span time. If a label at time t is computed over the next h bars
(a forward return, a triple-barrier outcome), then a training sample near a test-fold
boundary shares information with the test set, its label window OVERLAPS the test
window. Standard K-Fold ignores this, so the model effectively sees the answer, and the
cross-validated score is inflated. This is leakage, and it is the most common reason a
"validated" strategy dies live.

Purging (drop training samples whose label window overlaps any test sample) plus an
embargo (drop a few samples immediately after each test block, to kill serial-correlation
bleed) removes the leak. Lopez de Prado, Advances in Financial Machine Learning, ch. 7.

This demo builds a deliberately leak-prone setup, overlapping labels plus a feature that
is mildly autocorrelated with its own label horizon, and shows plain K-Fold reporting a
falsely high score that purged K-Fold corrects downward toward the honest (near-random)
truth. No market data, numpy-only, deterministic.

Run:  python3 purged_cv.py
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Fold:
    train_idx: np.ndarray
    test_idx: np.ndarray


def kfold_indices(n: int, k: int, shuffle: bool, rng: np.random.Generator) -> list[Fold]:
    """
    K-Fold. shuffle=True is the COMMON SIN on time series: samples are assigned to folds at
    random, so a test sample's immediate time-neighbors almost all land in the training set,
    and their overlapping labels leak straight in. shuffle=False is contiguous blocks.
    """
    all_idx = np.arange(n)
    order = rng.permutation(n) if shuffle else all_idx
    fold_of = np.array_split(order, k)
    folds = []
    for i in range(k):
        test = np.sort(fold_of[i])
        train = np.sort(np.setdiff1d(all_idx, test))
        folds.append(Fold(train, test))
    return folds


def purge_and_embargo(fold: Fold, label_horizon: int, embargo: int, n: int) -> Fold:
    """
    Remove every training sample within `label_horizon` (+`embargo` on the forward side) of
    ANY test sample, i.e. whose label window overlaps, or is adjacent to, a test label
    window. This is the general purge (works for shuffled or contiguous folds), not just a
    single-boundary trim.
    """
    test = fold.test_idx
    forbidden = np.zeros(n, dtype=bool)
    for t in test:
        lo = max(0, t - label_horizon)
        hi = min(n, t + label_horizon + embargo + 1)
        forbidden[lo:hi] = True
    keep = fold.train_idx[~forbidden[fold.train_idx]]
    return Fold(keep, test)


def make_leaky_dataset(n: int, label_horizon: int,
                       rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """
    Feature x is pure noise. Label y is the sign of a FORWARD-looking sum over the next
    `label_horizon` bars of a series that x is only weakly tied to, so the TRUE
    predictive power of x for y is near zero. But because consecutive labels share
    overlapping forward windows, adjacent samples' labels are highly correlated; a model
    that memorizes a neighbor's label (leaked via an un-purged fold) scores far above
    chance. That gap is the leak this demo exposes.
    """
    driver = rng.normal(0, 1, n + label_horizon)
    # forward-looking label: sign of the sum of the next `label_horizon` driver values
    fwd = np.array([driver[i + 1:i + 1 + label_horizon].sum() for i in range(n)])
    y = (fwd > 0).astype(int)
    # feature carries only a whisper of genuine signal (weight 0.15) + noise
    x = 0.15 * fwd + rng.normal(0, 1, n)
    return x.reshape(-1, 1), y


def score_fold(x_tr: np.ndarray, y_tr: np.ndarray,
               x_te: np.ndarray, y_te: np.ndarray) -> float:
    """
    A memorizing-prone 1-NN in index-adjacent feature space. Accuracy on the test fold.
    1-NN is deliberately chosen: it is exactly the model that benefits from a neighbor
    whose label leaked across an un-purged boundary.
    """
    # nearest-neighbor by feature distance
    preds = []
    for xt in x_te:
        j = np.argmin(np.abs(x_tr[:, 0] - xt[0]))
        preds.append(y_tr[j])
    return float((np.array(preds) == y_te).mean())


def run_cv(x: np.ndarray, y: np.ndarray, folds: list[Fold], purge: bool,
           label_horizon: int, embargo: int, n: int) -> float:
    accs = []
    for f in folds:
        ff = purge_and_embargo(f, label_horizon, embargo, n) if purge else f
        if len(ff.train_idx) == 0:
            continue
        accs.append(score_fold(x[ff.train_idx], y[ff.train_idx],
                               x[ff.test_idx], y[ff.test_idx]))
    return float(np.mean(accs)) if accs else float("nan")  # nan iff every fold was empty


def main() -> None:
    rng = np.random.default_rng(20260806)
    n, k, label_horizon, embargo = 1500, 6, 20, 5

    x, y = make_leaky_dataset(n, label_horizon, rng)
    base_rate = max(y.mean(), 1 - y.mean())  # accuracy of always guessing the majority

    shuf = kfold_indices(n, k, shuffle=True, rng=np.random.default_rng(1))
    plain = run_cv(x, y, shuf, purge=False, label_horizon=label_horizon, embargo=embargo, n=n)
    purged = run_cv(x, y, shuf, purge=True, label_horizon=label_horizon, embargo=embargo, n=n)

    print("=" * 72)
    print("  Purged K-Fold, removing the leak that inflates a backtest")
    print("=" * 72)
    print(f"  samples: {n}   folds: {k}   label horizon: {label_horizon} bars   embargo: {embargo}")
    print(f"  feature has only a whisper of true signal; labels overlap by {label_horizon} bars")
    print("  folds are SHUFFLED, the common sin on time series\n")
    print(f"  majority-class baseline (no skill)     : {base_rate:6.3f}")
    print(f"  plain  shuffled K-Fold accuracy        : {plain:6.3f}   <- inflated by leakage")
    print(f"  purged shuffled K-Fold accuracy        : {purged:6.3f}   <- honest, collapses to coin-flip")
    print(f"  leak (plain - purged)                  : {plain - purged:+6.3f}")
    print()
    print("  Takeaway: the un-purged score looks skillful; purging shows most of that")
    print("  'skill' was the model reading a neighbor's overlapping label. Same failure")
    print("  a real strategy hits live, where the neighbor's future is not available.")
    print("=" * 72)


if __name__ == "__main__":
    main()
