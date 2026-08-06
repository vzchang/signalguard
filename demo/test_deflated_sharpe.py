"""
Tests for the Deflated Sharpe Ratio demo.

Plain-assert tests (no pytest dependency) so they run with `python3 test_deflated_sharpe.py`
on any box. The load-bearing test is the paired one: DSR must REJECT a best-of-N noise
winner and ACCEPT a genuinely-edged strategy at the same trial count. That single
comparison is what proves the gate discriminates rather than blanket-rejecting.
"""
from __future__ import annotations
import math
import numpy as np

from deflated_sharpe_demo import (
    sharpe_ratio, probabilistic_sharpe_ratio, deflated_sharpe_ratio,
    best_of_n_noise, genuine_edge, _norm_ppf, _norm_cdf,
)

CUT = 0.95


def test_norm_ppf_cdf_roundtrip():
    for p in (0.01, 0.1, 0.5, 0.9, 0.975, 0.999):
        assert abs(_norm_cdf(_norm_ppf(p)) - p) < 1e-6, p


def test_norm_ppf_known_quantiles():
    assert abs(_norm_ppf(0.975) - 1.959963985) < 1e-5
    assert abs(_norm_ppf(0.5)) < 1e-9


def test_sharpe_zero_on_flat_series():
    assert sharpe_ratio(np.zeros(100)) == 0.0


def test_psr_rises_with_sharpe():
    rng = np.random.default_rng(1)
    weak = rng.normal(0.0002, 0.01, 500)
    strong = rng.normal(0.004, 0.01, 500)
    assert probabilistic_sharpe_ratio(strong) > probabilistic_sharpe_ratio(weak)


def test_dsr_is_never_greater_than_psr():
    """DSR benchmarks against a positive expected-max SR, so it can only be <= PSR-vs-0."""
    rng = np.random.default_rng(2)
    r = rng.normal(0.001, 0.01, 500)
    _, _, var_sr = best_of_n_noise(50, 500, np.random.default_rng(3))
    assert deflated_sharpe_ratio(r, 50, var_sr) <= probabilistic_sharpe_ratio(r, 0.0) + 1e-9


def test_THE_GATE_rejects_noise_accepts_edge():
    """
    The headline test. Same 200-trial selection context for both:
      - best-of-200 pure noise  -> DSR must REJECT (< CUT)
      - a genuine edge          -> DSR must ACCEPT (>= CUT)
    and PSR (trial-blind) must ACCEPT the noise winner, proving why the deflation matters.
    """
    rng = np.random.default_rng(20260806)
    n_obs, n_trials = 504, 200

    noise, _, var_sr = best_of_n_noise(n_trials, n_obs, rng)
    edge = genuine_edge(n_obs, daily_sharpe=0.16, rng=rng)

    psr_noise = probabilistic_sharpe_ratio(noise, 0.0)
    dsr_noise = deflated_sharpe_ratio(noise, n_trials, var_sr)
    dsr_edge = deflated_sharpe_ratio(edge, n_trials, var_sr)

    assert psr_noise >= CUT, "PSR should be fooled by the noise winner (that's the point)"
    assert dsr_noise < CUT, f"DSR must REJECT noise, got {dsr_noise:.3f}"
    assert dsr_edge >= CUT, f"DSR must ACCEPT the real edge, got {dsr_edge:.3f}"


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {fn.__name__}: {e}")
            raise
    print(f"\n{passed}/{len(fns)} passed")


if __name__ == "__main__":
    _run_all()
