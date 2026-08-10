"""
Tests for the purged K-Fold demo (plain-assert, no pytest dependency).

Headline test: on the leaky dataset, plain shuffled K-Fold scores materially above the
majority baseline, and purged K-Fold collapses back toward it -- i.e. purging removes the
leak. That single comparison is the point of the module.
"""
from __future__ import annotations

import numpy as np
from purged_cv import (
    kfold_indices,
    make_leaky_dataset,
    purge_and_embargo,
    run_cv,
)


def test_folds_partition_the_data() -> None:
    for shuffle in (False, True):
        folds = kfold_indices(300, 5, shuffle=shuffle, rng=np.random.default_rng(0))
        seen = np.concatenate([f.test_idx for f in folds])
        assert np.array_equal(np.sort(seen), np.arange(300)), "test folds must partition [0,n)"
        for f in folds:
            assert np.intersect1d(f.train_idx, f.test_idx).size == 0, "train/test must be disjoint"


def test_purge_removes_neighbors_of_test() -> None:
    folds = kfold_indices(300, 5, shuffle=True, rng=np.random.default_rng(1))
    h, emb = 20, 5
    for f in folds:
        pf = purge_and_embargo(f, label_horizon=h, embargo=emb, n=300)
        # no surviving training index may lie within the forbidden band of any test index
        for t in f.test_idx:
            band = set(range(max(0, t - h), min(300, t + h + emb + 1)))
            assert not (set(pf.train_idx.tolist()) & band - {t}), "purge left a neighbor in train"
        assert pf.train_idx.size <= f.train_idx.size, "purge can only shrink train"


def test_THE_LEAK_plain_inflates_purged_corrects() -> None:
    """
    plain shuffled K-Fold > baseline + margin  (it leaks)
    purged shuffled K-Fold ~ baseline          (leak removed)
    and purged < plain by a clear margin.
    """
    rng = np.random.default_rng(20260806)
    n, k, h, emb = 1500, 6, 20, 5
    x, y = make_leaky_dataset(n, h, rng)
    base = max(y.mean(), 1 - y.mean())

    folds = kfold_indices(n, k, shuffle=True, rng=np.random.default_rng(1))
    plain = run_cv(x, y, folds, purge=False, label_horizon=h, embargo=emb, n=n)
    purged = run_cv(x, y, folds, purge=True, label_horizon=h, embargo=emb, n=n)

    assert plain - purged > 0.03, f"expected a visible leak, got {plain - purged:+.3f}"
    assert purged <= base + 0.02, f"purged should collapse to baseline, got {purged:.3f} vs {base:.3f}"
    assert plain > base + 0.005, f"plain should look skillful, got {plain:.3f} vs {base:.3f}"


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  PASS  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} passed")


if __name__ == "__main__":
    _run_all()
