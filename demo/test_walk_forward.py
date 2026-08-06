"""
Tests for the walk-forward demo (plain-assert, no pytest).

Headline: on a zero-edge random walk, per-window optimization produces a positive mean
in-sample Sharpe that does NOT survive out-of-sample -- walk-forward efficiency well below 1.
"""
from __future__ import annotations
import numpy as np

from walk_forward_demo import make_returns, strategy_returns, best_lookback, walk_forward, sharpe


def test_no_lookahead_in_strategy():
    """strategy_returns must never use a bar's own or future return for its position."""
    r = make_returns(200, np.random.default_rng(0))
    # zero out the tail; positions for the early bars must be unchanged
    r2 = r.copy(); r2[100:] = 0.0
    a = strategy_returns(r, 10)[:90]
    b = strategy_returns(r2, 10)[:90]
    assert np.allclose(a, b), "early positions must not depend on future returns"


def test_optimizer_finds_positive_is_on_noise():
    r = make_returns(1000, np.random.default_rng(1))
    _, is_sr = best_lookback(r, list(range(2, 61)))
    assert is_sr > 0.3, f"searching 59 lookbacks should find spurious IS edge, got {is_sr:.2f}"


def test_THE_GATE_oos_collapses_below_is():
    """mean OOS Sharpe materially below mean IS Sharpe -> WFE well under 1 on pure noise."""
    r = make_returns(3000, np.random.default_rng(20260806))
    rows = walk_forward(r, n_splits=8, grid=list(range(2, 61)))
    is_m = np.mean([x[1] for x in rows])
    oos_m = np.mean([x[2] for x in rows])
    wfe = oos_m / is_m
    assert is_m > 0.3, f"mean IS should look skillful, got {is_m:.2f}"
    assert wfe < 0.6, f"WFE should show collapse on noise, got {wfe:.2f}"
    assert oos_m < is_m, "OOS must not exceed IS on a zero-edge series"


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  PASS  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} passed")


if __name__ == "__main__":
    _run_all()
