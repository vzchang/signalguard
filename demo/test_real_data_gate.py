"""
Tests for the real-data gate (plain-assert, no pytest).

Headline: on cached real S&P 500 data, buy-and-hold over the full 155 years is ACCEPTED and
the best-of-many MA search on a short window is REJECTED. Proves the gate discriminates on
real prices, not just synthetic. Requires demo/data/sp500.csv to be present.
"""
from __future__ import annotations
import math
from pathlib import Path

import numpy as np

from real_data_gate import load_sp500_returns, ma_crossover_search, DATA
from gate import evaluate, Status


def test_data_file_present_and_sane():
    assert DATA.exists(), "demo/data/sp500.csv must be committed for offline runs"
    r = load_sp500_returns()
    assert len(r) > 1500, f"expected 150+ years of monthly data, got {len(r)}"
    assert 0.05 < r.std(ddof=1) * math.sqrt(12) < 0.30, "annualized vol should be equity-like"


def test_buy_and_hold_full_sample_accepted():
    r = load_sp500_returns()
    v = evaluate(returns=r, n_trials=1, var_trial_sharpes=1e-6,
                 wf_series=r, wf_splits=8, wf_grid=list(range(2, 25)))
    assert v.accepted, "buy-and-hold over 155y should PASS (real equity premium, a priori)"


def test_short_window_search_rejected():
    r = load_sp500_returns()
    short = r[-72:]
    best, n_trials, var_sr = ma_crossover_search(short, list(range(2, 13)), list(range(6, 49, 3)))
    v = evaluate(returns=best, n_trials=n_trials, var_trial_sharpes=max(var_sr, 1e-6),
                 wf_series=short, wf_splits=6, wf_grid=list(range(2, 25)))
    assert not v.accepted, "a big search on a short window should be REJECTED"
    names = {c.name for c in v.failed}
    assert "walk_forward" in names, "walk-forward should flag the OOS collapse"


def test_n1_deflated_sharpe_does_not_crash():
    """Regression: DSR with n_trials=1 must not raise (expected-max benchmark is undefined)."""
    from gate import check_deflated_sharpe
    r = load_sp500_returns()
    res = check_deflated_sharpe(r, 1, 1e-6)
    assert res.status in (Status.PASS, Status.FAIL), "N=1 must resolve to a real verdict, not crash"


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  PASS  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} passed")


if __name__ == "__main__":
    _run_all()
