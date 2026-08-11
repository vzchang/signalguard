"""
The SignalGuard validation gate: run all four overfitting checks, return one verdict.

This is the thesis of the whole project in one function, "a harness that can honestly
reject a strategy." Each of the four demo modules contributes one check; this composes them
into a single ACCEPT / REJECT decision with a reason per check.

A strategy is represented as its realized per-bar returns plus the metadata the checks need
(how many trials were searched to find it, and, for the lookahead audit, the raw price
series so the same-bar-vs-next-bar comparison can be made). Not every check
applies to every strategy; a check that lacks its inputs reports SKIP, never a false PASS.

    from gate import evaluate, CheckResult
    verdict = evaluate(returns, n_trials=200, prices=...)
    print(verdict.render())
    assert verdict.accepted is False

numpy-only. Deterministic given seeded inputs.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum

import numpy as np
from deflated_sharpe import deflated_sharpe_ratio
from lookahead_detector import pnl_next_bar, pnl_same_bar
from lookahead_detector import sharpe as ann_sharpe
from walk_forward import walk_forward


class Status(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: Status
    detail: str


@dataclass
class Verdict:
    checks: list = field(default_factory=list)

    @property
    def failed(self) -> list[CheckResult]:
        return [c for c in self.checks if c.status is Status.FAIL]

    @property
    def ran(self) -> list[CheckResult]:
        return [c for c in self.checks if c.status is not Status.SKIP]

    @property
    def accepted(self) -> bool:
        """ACCEPT only if at least one check ran and none failed. Silence is not consent."""
        return len(self.ran) > 0 and len(self.failed) == 0

    def render(self) -> str:
        w = max(len(c.name) for c in self.checks)
        lines = ["SignalGuard validation gate"]
        for c in self.checks:
            lines.append(f"  [{c.status.value}] {c.name.ljust(w)}   {c.detail}")
        if self.accepted:
            lines.append(f"  VERDICT: ACCEPT ({len(self.ran)}/{len(self.ran)} checks passed)")
        else:
            n = len(self.failed)
            lines.append(f"  VERDICT: REJECT ({n}/{len(self.ran)} checks failed)")
        return "\n".join(lines)



def check_deflated_sharpe(returns: np.ndarray | None,
                          n_trials: int | None,
                          var_trial_sharpes: float | None,
                          cut: float = 0.95) -> CheckResult:
    if n_trials is None or var_trial_sharpes is None:
        return CheckResult("deflated_sharpe", Status.SKIP,
                           "no trial count supplied; cannot correct for selection")
    if n_trials < 2:
        # a single a-priori strategy: there is no selection to deflate, so the honest test
        # is the plain PSR vs zero (the expected-max benchmark is undefined for N=1).
        from deflated_sharpe import probabilistic_sharpe_ratio
        psr = probabilistic_sharpe_ratio(np.asarray(returns), 0.0)
        status = Status.PASS if psr >= cut else Status.FAIL
        return CheckResult("deflated_sharpe", status,
                           f"PSR {psr:.2f} (N=1, a priori: no selection to deflate) "
                           f"{'>=' if status is Status.PASS else '<'} {cut}")
    dsr = deflated_sharpe_ratio(np.asarray(returns), n_trials, var_trial_sharpes)
    if dsr >= cut:
        return CheckResult("deflated_sharpe", Status.PASS,
                           f"DSR {dsr:.2f} >= {cut}  (survives {n_trials}-trial deflation)")
    return CheckResult("deflated_sharpe", Status.FAIL,
                       f"DSR {dsr:.2f} < {cut}  (edge indistinguishable from {n_trials}-trial noise)")


def check_lookahead(prices: np.ndarray | None, max_gap: float = 2.0) -> CheckResult:
    """
    Compare same-bar vs next-bar fills on the given price series. A large favorable gap
    means the strategy is booking information from the bar it traded on. Without a price
    series there is nothing to compare, so the check reports SKIP.
    """
    if prices is None:
        return CheckResult("lookahead_audit", Status.SKIP,
                           "no price series supplied; cannot audit fill timing")
    r = np.asarray(prices)
    cheat = ann_sharpe(pnl_same_bar(r))
    honest = ann_sharpe(pnl_next_bar(r))
    gap = cheat - honest
    if abs(gap) <= max_gap:
        return CheckResult("lookahead_audit", Status.PASS,
                           f"same-bar/next-bar gap {gap:+.2f}  (within tolerance)")
    return CheckResult("lookahead_audit", Status.FAIL,
                       f"same-bar/next-bar gap {gap:+.2f}  (books the bar it traded on)")


def check_purged_cv(plain_acc: float | None, purged_acc: float | None,
                    baseline: float, margin: float = 0.03) -> CheckResult:
    if plain_acc is None or purged_acc is None:
        return CheckResult("purged_cv", Status.SKIP,
                           "no cross-validation scores supplied")
    if math.isnan(plain_acc) or math.isnan(purged_acc):
        # a nan score is undefined, not a pass. Fail loud (prime directive: no silent PASS).
        return CheckResult("purged_cv", Status.FAIL,
                           "CV score undefined (nan), purge left no training data; "
                           "cannot certify the fold is leak-free")
    leak = plain_acc - purged_acc
    if purged_acc <= baseline + 0.02 and leak > margin:
        return CheckResult("purged_cv", Status.FAIL,
                           f"purged {purged_acc:.2f} at baseline, leak {leak:+.2f}  (score was leakage)")
    if leak > margin:
        return CheckResult("purged_cv", Status.FAIL,
                           f"leak {leak:+.2f} between plain and purged CV  (fold leakage present)")
    return CheckResult("purged_cv", Status.PASS,
                       f"purged {purged_acc:.2f}, leak {leak:+.2f}  (no material leakage)")


def check_walk_forward(returns_series: np.ndarray | None, n_splits: int,
                       grid: Sequence[int] | None, min_wfe: float = 0.5) -> CheckResult:
    if returns_series is None or grid is None:
        return CheckResult("walk_forward", Status.SKIP,
                           "no return series / parameter grid supplied")
    rows = walk_forward(np.asarray(returns_series), n_splits=n_splits, grid=grid)
    is_m = float(np.mean([x[1] for x in rows]))
    oos_m = float(np.mean([x[2] for x in rows]))
    # two negatives divide into a healthy-looking ratio, so a strategy that lost money in
    # and out of sample would otherwise pass on arithmetic alone
    if is_m <= 0:
        return CheckResult("walk_forward", Status.FAIL,
                           f"no in-sample edge to carry forward (IS {is_m:+.2f} -> OOS {oos_m:+.2f})")
    wfe = oos_m / is_m
    if wfe >= min_wfe:
        return CheckResult("walk_forward", Status.PASS,
                           f"WFE {wfe:.2f} >= {min_wfe}  (IS {is_m:+.2f} -> OOS {oos_m:+.2f})")
    return CheckResult("walk_forward", Status.FAIL,
                       f"WFE {wfe:.2f} < {min_wfe}  (IS {is_m:+.2f} -> OOS {oos_m:+.2f}, edge did not survive)")


def evaluate(returns: np.ndarray | None = None, *,
             n_trials: int | None = None,
             var_trial_sharpes: float | None = None,
             prices: np.ndarray | None = None,
             cv_plain: float | None = None,
             cv_purged: float | None = None,
             cv_baseline: float = 0.5,
             wf_series: np.ndarray | None = None,
             wf_splits: int = 8,
             wf_grid: Sequence[int] | None = None) -> Verdict:
    """
    Compose the four checks into one verdict. Every argument is optional; a check whose
    inputs are missing reports SKIP (never a silent PASS), and ACCEPT requires >=1 ran and
    0 failed. This is the single entry point the whole project points at.
    """
    checks = [
        check_deflated_sharpe(returns if returns is not None else np.array([0.0]),
                              n_trials, var_trial_sharpes),
        check_lookahead(prices),
        check_purged_cv(cv_plain, cv_purged, cv_baseline),
        check_walk_forward(wf_series, wf_splits, wf_grid),
    ]
    return Verdict(checks)
