"""
Tests for the lookahead-bias detector demo (plain-assert, no pytest).

Headline test: the same-bar (cheating) strategy prints a huge Sharpe from a zero-edge
random walk, the next-bar (honest) strategy sits near zero, and the fill-timing audit's
gap is enormous -- i.e. the detector catches the peek. That is half the Phase 1 gate.
"""
from __future__ import annotations
import numpy as np

from lookahead_detector_demo import (
    make_returns, momentum_signal, pnl_same_bar, pnl_next_bar, sharpe, fill_timing_audit,
)


def test_random_walk_has_no_autocorrelation():
    r = make_returns(5000, np.random.default_rng(0))
    ac1 = np.corrcoef(r[:-1], r[1:])[0, 1]
    assert abs(ac1) < 0.05, f"random walk should have ~0 lag-1 autocorr, got {ac1:.3f}"


def test_same_bar_pnl_is_absolute_value():
    """The cheat books sign(r)*r == |r| every bar -- the algebraic proof it peeks."""
    r = make_returns(500, np.random.default_rng(1))
    assert np.allclose(pnl_same_bar(r), np.abs(r)), "same-bar pnl must equal |r|"
    assert (pnl_same_bar(r) >= 0).all(), "the cheat is never negative -- that's the tell"


def test_honest_momentum_has_no_edge_on_random_walk():
    r = make_returns(5000, np.random.default_rng(2))
    assert abs(sharpe(pnl_next_bar(r))) < 1.5, "next-bar momentum on a random walk ~ 0 Sharpe"


def test_THE_GATE_audit_flags_the_peek():
    """
    cheat Sharpe huge, honest Sharpe small, gap enormous.
    A real daily strategy never shows a same-bar/next-bar gap anywhere near this size,
    so the gap itself is the detector.
    """
    r = make_returns(1500, np.random.default_rng(20260806))
    cheat, honest, gap = fill_timing_audit(r)
    assert cheat > 10.0, f"the cheat should print an absurd Sharpe, got {cheat:.2f}"
    assert abs(honest) < 1.5, f"the honest strategy should be near zero, got {honest:.2f}"
    assert gap > 10.0, f"the fill-timing gap is the signature; got {gap:.2f}"


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  PASS  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} passed")


if __name__ == "__main__":
    _run_all()
