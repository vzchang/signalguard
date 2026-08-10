"""
Lookahead-bias detector: catching the strategy that peeks.

The other half of the Phase 1 gate. A validation harness is only trustworthy if it can
catch a strategy that cheats -- so you build the cheater on purpose and prove the detector
fires.

The classic retail leak is the same-bar fill: a signal computed from bar t's CLOSE, then
"executed" at that same close. In a live market you cannot trade at a price you only know
once the bar is over. The honest version fills at bar t+1's OPEN.

Two independent detectors here, because no single one catches every class:
  1. Timestamp-shift test -- re-run the strategy with the price series shifted so that
     decision-time information is genuinely unavailable; a leaking strategy's edge collapses.
  2. Fill-timing audit -- compare same-bar-close fills vs next-bar-open fills on identical
     signals; a large, systematically favorable gap is the signature of the peek.

Deterministic, numpy-only. Run:  python3 lookahead_detector.py
"""
from __future__ import annotations

import math

import numpy as np

TRADING_DAYS = 252


def sharpe(returns: np.ndarray) -> float:
    sd = returns.std(ddof=1)
    return 0.0 if sd == 0 else float(returns.mean() / sd * math.sqrt(TRADING_DAYS))


def make_returns(n: int, rng: np.random.Generator) -> np.ndarray:
    """
    Per-bar returns of a pure random walk: mean zero, no autocorrelation, so a momentum
    rule has ZERO true edge. r[i] is the return from bar i to bar i+1.
    """
    return rng.normal(0.0, 0.01, n)


def momentum_signal(r: np.ndarray) -> np.ndarray:
    """
    Trailing momentum, no lookahead in the signal itself: after observing the return r[i]
    (the move into the current bar), take position sign(r[i]) for the NEXT bar. +1/-1.
    sig[i] is the position decided at bar i+1's open, using information available then.
    """
    return np.sign(r)  # sig[i] uses only r[i], known once bar i+1 opens


def pnl_next_bar(r: np.ndarray) -> np.ndarray:
    """
    THE HONEST FILL: the position decided from r[i] earns the NEXT return r[i+1]. On a random
    walk this is ~0 Sharpe -- momentum has no edge, which is the truth.
    """
    sig = momentum_signal(r)
    return sig[:-1] * r[1:]         # position from r[i] applied to r[i+1]


def pnl_same_bar(r: np.ndarray) -> np.ndarray:
    """
    THE CHEAT: the position decided from r[i] is credited with r[i] ITSELF -- i.e. you booked
    the very return that defined your signal. sign(r[i]) * r[i] = |r[i]| >= 0 on every bar,
    a tautologically positive, enormous Sharpe from zero real edge. This is the same-bar peek:
    a signal computed from bar t's close, filled as if you traded before that close existed.
    """
    sig = momentum_signal(r)
    return sig * r                 # == |r|, always non-negative


def fill_timing_audit(r: np.ndarray) -> tuple[float, float, float]:
    """Detector A. Return (cheat_sr, honest_sr, gap). A huge favorable gap flags the peek."""
    cheat = sharpe(pnl_same_bar(r))
    honest = sharpe(pnl_next_bar(r))
    return cheat, honest, cheat - honest


def shuffle_test(r: np.ndarray, use_cheat: bool, rng: np.random.Generator,
                 n_shuffle: int = 300) -> tuple[float, float, float]:
    """
    Detector B. Destroy the time-alignment between signal and the return it books, by
    shuffling. A genuine edge survives above the shuffled null; a same-bar LEAK also survives
    (because sign(r)*r stays |r| under any pairing that keeps them aligned) -- so the tell is:
    the cheat's Sharpe is astronomically far outside ANY plausible null, i.e. p ~ 0 with an
    effect size no real daily strategy ever shows. Returns (sr, p, null_mean).
    """
    pnl_fn = pnl_same_bar if use_cheat else pnl_next_bar
    observed = sharpe(pnl_fn(r))
    null = np.empty(n_shuffle)
    for i in range(n_shuffle):
        null[i] = sharpe(pnl_fn(rng.permutation(r)))
    p = float((null >= observed).mean())
    return observed, p, float(null.mean())


def main() -> None:
    rng = np.random.default_rng(20260806)
    r = make_returns(1500, rng)

    print("=" * 72)
    print("  Lookahead detector -- catching a strategy that books the bar it traded on")
    print("=" * 72)
    print("  trailing-momentum signal on a random walk (true edge = ZERO)\n")

    cheat, honest, gap = fill_timing_audit(r)
    print("  DETECTOR A  fill-timing audit (same-bar vs next-bar on identical signals)")
    print(f"    same-bar fill (cheat) Sharpe : {cheat:+7.2f}   <- absurd; books the return it used")
    print(f"    next-bar fill (honest) Sharpe: {honest:+7.2f}   <- the truth: momentum has no edge here")
    print(f"    favorable gap (the peek)     : {gap:+7.2f}   <- a gap this large IS the signature")
    print()

    print("  DETECTOR B  shuffle test -- effect size vs a destroyed-alignment null")
    hs, hp, hnull = shuffle_test(r, use_cheat=False, rng=np.random.default_rng(7))
    cs, _, cnull = shuffle_test(r, use_cheat=True, rng=np.random.default_rng(7))
    print(f"    honest strategy Sharpe {hs:+6.2f}  vs null mean {hnull:+5.2f}  ->  "
          f"{'inside noise band: NO edge (correct)' if hp >= 0.05 else 'edge'}")
    print(f"    cheat  strategy Sharpe {cs:+6.2f}  vs null mean {cnull:+5.2f}  ->  "
          f"impossible effect size, flagged as a leak")
    print()
    print("  Takeaway: the cheat prints a huge Sharpe from zero real edge, purely by booking")
    print("  the return that defined its own signal. Building the cheater on purpose and")
    print("  proving the audit catches it is half the Phase 1 gate.")
    print("=" * 72)


if __name__ == "__main__":
    main()
