"""
Tests for the walk-forward demo (plain-assert, no pytest).

Headline: on a zero-edge random walk, per-window optimization produces a positive mean
in-sample Sharpe that does NOT survive out-of-sample, walk-forward efficiency well below 1.
"""
from __future__ import annotations

import numpy as np
from walk_forward import best_lookback, make_returns, strategy_returns, walk_forward


def test_no_lookahead_in_strategy() -> None:
    """strategy_returns must never use a bar's own or future return for its position."""
    r = make_returns(200, np.random.default_rng(0))
    # zero out the tail; positions for the early bars must be unchanged
    r2 = r.copy()
    r2[100:] = 0.0
    a = strategy_returns(r, 10)[:90]
    b = strategy_returns(r2, 10)[:90]
    assert np.allclose(a, b), "early positions must not depend on future returns"


def test_optimizer_finds_positive_is_on_noise() -> None:
    r = make_returns(1000, np.random.default_rng(1))
    _, is_sr = best_lookback(r, list(range(2, 61)))
    assert is_sr > 0.3, f"searching 59 lookbacks should find spurious IS edge, got {is_sr:.2f}"


def test_THE_GATE_oos_collapses_below_is() -> None:
    """mean OOS Sharpe materially below mean IS Sharpe -> WFE well under 1 on pure noise."""
    r = make_returns(3000, np.random.default_rng(20260806))
    rows = walk_forward(r, n_splits=8, grid=list(range(2, 61)))
    is_m = np.mean([x[1] for x in rows])
    oos_m = np.mean([x[2] for x in rows])
    wfe = oos_m / is_m
    assert is_m > 0.3, f"mean IS should look skillful, got {is_m:.2f}"
    assert wfe < 0.6, f"WFE should show collapse on noise, got {wfe:.2f}"
    assert oos_m < is_m, "OOS must not exceed IS on a zero-edge series"


def test_losing_strategy_is_not_rescued_by_the_wfe_ratio() -> None:
    """
    Negative in-sample AND negative out-of-sample must FAIL. Their ratio is positive
    (here IS -11.35, OOS -11.81, WFE 1.04), so an unguarded WFE reads a strategy that
    lost money in both windows as its healthiest possible result.
    """
    from gate import Status, check_walk_forward

    # negative lag-2 autocorrelation: the momentum rule compares sign(r[i-1]) against
    # r[i+1], so this is structurally wrong for it and no grid choice escapes
    rng = np.random.default_rng(3)
    r = np.zeros(1600)
    for i in range(2, len(r)):
        r[i] = -0.7 * r[i - 2] + rng.normal(0, 0.01)

    res = check_walk_forward(r, 8, (1, 2))
    assert res.status is Status.FAIL, f"losing strategy must FAIL, got {res.status}: {res.detail}"


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  PASS  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} passed")


if __name__ == "__main__":
    _run_all()
