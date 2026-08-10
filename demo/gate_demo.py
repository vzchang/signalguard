"""
Run the SignalGuard validation gate on two strategies: one that cheats, one that is clean.

The point of the whole project in one screen: the gate REJECTS a strategy that is an
overfitting artifact (it fails multiple independent checks) and ACCEPTS one that survives
every check it can run. A tool, not four tutorials.

Run:  python3 gate_demo.py
"""
from __future__ import annotations
import math
import numpy as np

from gate import evaluate
from deflated_sharpe_demo import sharpe_ratio, best_of_n_noise
from lookahead_detector_demo import make_returns
from purged_cv_demo import make_leaky_dataset, kfold_indices, run_cv
from walk_forward_demo import make_returns as wf_make_returns


def scenario_overfit_artifact():
    """
    A strategy assembled from every red flag: selected as best-of-200 noise, audited on a
    random walk where a same-bar peek inflates it, cross-validated with shuffled folds that
    leak, and optimized over 59 lookbacks that do not survive walk-forward. The gate should
    REJECT on multiple independent grounds.
    """
    rng = np.random.default_rng(20260806)
    best, _, var_sr = best_of_n_noise(200, 504, rng)

    prices = make_returns(1500, np.random.default_rng(1))  # random-walk returns for the audit

    x, y = make_leaky_dataset(1500, 20, np.random.default_rng(20260806))
    base = max(y.mean(), 1 - y.mean())
    folds = kfold_indices(1500, 6, shuffle=True, rng=np.random.default_rng(1))
    plain = run_cv(x, y, folds, purge=False, label_horizon=20, embargo=5, n=1500)
    purged = run_cv(x, y, folds, purge=True, label_horizon=20, embargo=5, n=1500)

    wf = wf_make_returns(3000, np.random.default_rng(4))

    return evaluate(
        returns=best, n_trials=200, var_trial_sharpes=var_sr,
        prices=prices,
        cv_plain=plain, cv_purged=purged, cv_baseline=base,
        wf_series=wf, wf_splits=8, wf_grid=list(range(2, 61)),
    )


def scenario_clean_strategy():
    """
    A strategy that passes what it can: a return stream with a genuine, modest edge judged
    against a SMALL honest trial count, no lookahead (a real forward-return series), no CV
    leak, and a walk-forward that holds up because the edge is real. The gate should ACCEPT.
    """
    rng = np.random.default_rng(11)
    n = 504
    # genuine edge: positive-mean returns; small honest search (3 trials, low trial variance)
    edged = rng.normal(0.16 * 0.01, 0.01, n)
    var_small = 0.02 ** 2  # 3 honest trials -> tiny dispersion in trial Sharpes

    # a clean CV: plain and purged agree (no leakage) and sit above baseline honestly
    plain, purged, base = 0.63, 0.62, 0.55

    # a walk-forward with a REAL edge that survives: bias the series so momentum persists
    m = rng.normal(0.0004, 0.01, 3000)  # small positive drift -> long-momentum survives OOS

    return evaluate(
        returns=edged, n_trials=3, var_trial_sharpes=var_small,
        prices=None,  # no price series to audit -> lookahead check SKIPs, honestly
        cv_plain=plain, cv_purged=purged, cv_baseline=base,
        wf_series=m, wf_splits=8, wf_grid=list(range(2, 61)),
    )


def main() -> None:
    print("#" * 72)
    print("#  Scenario 1: an overfitting artifact (should be REJECTED)")
    print("#" * 72)
    v1 = scenario_overfit_artifact()
    print(v1.render())
    print()
    print("#" * 72)
    print("#  Scenario 2: a clean strategy (should be ACCEPTED)")
    print("#" * 72)
    v2 = scenario_clean_strategy()
    print(v2.render())
    print()
    print(f"gate discriminates: scenario1 accepted={v1.accepted}, scenario2 accepted={v2.accepted}")


if __name__ == "__main__":
    main()
