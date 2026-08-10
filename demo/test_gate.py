"""
Tests for the unified validation gate (plain-assert, no pytest).

Headline tests: the gate REJECTS an overfitting artifact and ACCEPTS a clean strategy, and
-- the property that matters most -- it never returns a silent PASS. A missing input is SKIP;
an undefined (nan) score is FAIL, not PASS.
"""
from __future__ import annotations
import math
import numpy as np

from gate import (
    evaluate, Status,
    check_deflated_sharpe, check_lookahead, check_purged_cv, check_walk_forward,
)
from gate_demo import scenario_overfit_artifact, scenario_clean_strategy


def test_THE_GATE_rejects_artifact_accepts_clean():
    v_bad = scenario_overfit_artifact()
    v_good = scenario_clean_strategy()
    assert v_bad.accepted is False, "an overfitting artifact must be REJECTED"
    assert v_good.accepted is True, "a clean strategy must be ACCEPTED"
    assert len(v_bad.failed) >= 3, "the artifact should fail on multiple independent grounds"


def test_accept_requires_at_least_one_check_ran():
    """A verdict where everything SKIPped is NOT an accept -- silence is not consent."""
    v = evaluate()  # no inputs at all -> all SKIP
    assert all(c.status is Status.SKIP for c in v.checks)
    assert v.accepted is False, "all-SKIP must not count as ACCEPT"


def test_nan_cv_score_fails_not_passes():
    """The bug that this gate must not have: an undefined CV score is FAIL, never PASS."""
    r = check_purged_cv(float("nan"), float("nan"), 0.5)
    assert r.status is Status.FAIL, "nan CV score must fail loud"


def test_missing_inputs_skip_not_fail():
    assert check_lookahead(None, None).status is Status.SKIP
    assert check_deflated_sharpe(np.zeros(10), None, None).status is Status.SKIP
    assert check_walk_forward(None, 8, None).status is Status.SKIP


def test_deflated_sharpe_check_directions():
    # a strong return stream vs a tiny honest trial count -> PASS
    rng = np.random.default_rng(3)
    good = rng.normal(0.003, 0.01, 500)
    assert check_deflated_sharpe(good, 3, 0.02 ** 2).status is Status.PASS
    # the same stream against a huge trial search -> the bar rises, FAIL
    assert check_deflated_sharpe(good, 5000, 0.5 ** 2).status is Status.FAIL


def test_lookahead_check_catches_same_bar():
    r = np.random.default_rng(4).normal(0, 0.01, 1000)
    assert check_lookahead(r, None).status is Status.FAIL  # random walk -> big same-bar gap


def test_render_is_stable_text():
    v = scenario_clean_strategy()
    out = v.render()
    assert "SignalGuard validation gate" in out
    assert "VERDICT:" in out


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  PASS  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} passed")


if __name__ == "__main__":
    _run_all()
