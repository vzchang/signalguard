"""
Tests for the cost-survival demo (plain-assert, no pytest).

Headline: two strategies post ordinary, indistinguishable gross Sharpes; one of them
spends more than its whole edge on commissions, and only the retention ratio says so.
"""
from __future__ import annotations

import numpy as np
from cost_survival import (
    ANNUAL_COST_BUDGET,
    EQUITY,
    FAST_LOOKBACK,
    N_BARS,
    ROUND_TURN_USD,
    SLOW_LOOKBACK,
    breakeven_cost_fraction,
    cost_fraction,
    make_returns,
    net_returns,
    positions,
    round_turns_per_year,
    sharpe,
    strategy_returns,
)


def test_breakeven_cost_zeroes_the_edge() -> None:
    """Charging exactly the break-even cost must leave a mean net return of zero."""
    r = make_returns(4000, np.random.default_rng(0))
    gross, turns = strategy_returns(r, FAST_LOOKBACK)
    be = breakeven_cost_fraction(gross, turns)
    assert np.isclose(net_returns(gross, turns, be).mean(), 0.0, atol=1e-12), \
        "break-even cost must zero the mean net return by construction"


def test_net_sharpe_falls_monotonically_with_cost() -> None:
    r = make_returns(4000, np.random.default_rng(1))
    gross, turns = strategy_returns(r, FAST_LOOKBACK)
    srs = [sharpe(net_returns(gross, turns, c)) for c in (0.0, 1e-4, 2e-4, 4e-4)]
    assert srs == sorted(srs, reverse=True), f"net Sharpe must decay with cost, got {srs}"


def test_THE_GATE_cost_separates_two_believable_gross_sharpes() -> None:
    """
    Both variants look ordinary gross, inside the band a retail system can honestly target
    and nowhere near the ~2.0 that is itself a defect report. No other check in this
    harness distinguishes them. Net of turnover, one is dead and the other keeps most of
    what it made.
    """
    r = make_returns(N_BARS, np.random.default_rng(20260818))
    fast_g, fast_t = strategy_returns(r, FAST_LOOKBACK)
    slow_g, slow_t = strategy_returns(r, SLOW_LOOKBACK)
    cf = cost_fraction(ROUND_TURN_USD, EQUITY)
    fg, sg = sharpe(fast_g), sharpe(slow_g)
    fn = sharpe(net_returns(fast_g, fast_t, cf))
    sn = sharpe(net_returns(slow_g, slow_t, cf))

    assert 0.3 < fg < 2.0, f"fast gross must look ordinary, got {fg:+.2f}"
    assert 0.3 < sg < 2.0, f"slow gross must look ordinary, got {sg:+.2f}"
    assert fn < 0.0, f"fast must be dead net of cost, got {fn:+.2f}"
    assert sn > 0.5, f"slow must survive cost, got {sn:+.2f}"
    assert fn / fg < 0.5 <= sn / sg, \
        f"retention must separate them: fast {fn / fg:+.2f} vs slow {sn / sg:+.2f}"


def test_no_lookahead_in_positions() -> None:
    """A position must never depend on a return from its own bar or later."""
    r = make_returns(400, np.random.default_rng(2))
    r2 = r.copy()
    r2[200:] = 0.0
    assert np.array_equal(positions(r, SLOW_LOOKBACK)[:199],
                          positions(r2, SLOW_LOOKBACK)[:199]), \
        "early positions must not depend on future returns"


def test_cost_ceiling_arithmetic_reproduces_the_documented_275() -> None:
    """The ~275 round turns/year ceiling is arithmetic, so the harness should compute it."""
    ceiling = ANNUAL_COST_BUDGET / cost_fraction(ROUND_TURN_USD, EQUITY)
    assert 270 <= ceiling <= 280, f"expected ~275 round turns/year, got {ceiling:.0f}"


def test_zero_turnover_cannot_be_killed_by_cost() -> None:
    """Buy-and-hold pays no round turns, so its break-even cost is unbounded, not zero."""
    gross = np.full(500, 1e-4)
    turns = np.zeros(500, dtype=bool)
    assert breakeven_cost_fraction(gross, turns) == float("inf")
    assert np.array_equal(net_returns(gross, turns, 1.0), gross)


def test_negative_gross_is_not_rescued_by_the_retention_ratio() -> None:
    """
    A strategy that loses money before costs must FAIL. Net/gross is positive when both
    are negative (costs make the numerator MORE negative, so the ratio exceeds 1), which
    would read a losing strategy as its healthiest possible result.
    """
    from gate import Status, check_cost_survival

    rng = np.random.default_rng(4)
    gross = rng.normal(-2e-4, 0.004, 3000)
    turns = np.zeros(3000, dtype=bool)
    turns[::3] = True
    res = check_cost_survival(gross, turns, 1e-4)
    assert res.status is Status.FAIL, f"losing strategy must FAIL, got {res.status}: {res.detail}"


def test_nan_gross_fails_rather_than_passing() -> None:
    from gate import Status, check_cost_survival

    gross = np.full(100, np.nan)
    turns = np.zeros(100, dtype=bool)
    res = check_cost_survival(gross, turns, 1e-4)
    assert res.status is Status.FAIL, f"nan must FAIL, got {res.status}"


def test_missing_cost_inputs_skip() -> None:
    from gate import Status, check_cost_survival

    assert check_cost_survival(None, None, None).status is Status.SKIP


def test_round_turns_per_year_matches_a_hand_count() -> None:
    turns = np.zeros(1512, dtype=bool)   # exactly one year of bars
    turns[:100] = True
    assert round_turns_per_year(turns) == 100.0


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  PASS  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} passed")


if __name__ == "__main__":
    _run_all()
