"""
Cost survival: the edge that exists gross and does not exist net.

The fifth check in the harness, and the only one that asks whether a validated return
series can actually be traded. The other four ask whether a number is real. This one asks
whether a real number is large enough to pay for itself.

Two strategies on the SAME price series, differing only in holding period:

  FAST  position = sign of the last bar's return. Turns over ~2.9 round turns/day.
  SLOW  position = sign of the trailing 48-bar sum. Turns over ~0.35 round turns/day.

Both post an ordinary, believable gross Sharpe, inside the 0.5 to 1.0 band a retail futures
system can honestly target, and nowhere near the ~2.0 that would itself be a defect report.
Gross, neither looks wrong. Net of a round-turn cost, the fast one is decisively negative
and the slow one keeps most of what it made. Gross Sharpe cannot separate them; the
net/gross retention ratio separates them immediately.

What this deliberately does NOT claim: that trading faster makes a strategy look better
gross. It usually does not, and 40 seeds say so. The tempting demo, "the fast variant wins
on gross and dies on net", held on one lucky draw and evaporated on the rest, so it is not
the claim here. Picking the seed that tells the better story is the exact failure the rest
of this harness exists to reject.

The cost input is sourced from published schedules, not from measured fills. A micro round
turn is $2.43 in fees and commission: per side, $0.85 IBKR execution at up to 1,000
contracts/month, $0.353 CME exchange fee, $0.01 NFA. Add one tick of spread and M2K comes
to $2.93, MES to $3.68, because the MES tick is $1.25 against M2K's $0.50. The $2.90 used
below is the M2K figure. Prime directive 5 asks for measured fills, so this is a floor on
what you will actually pay, not the final answer.

That is why the number this module reports is `breakeven_cost_fraction`, the round-turn cost
at which the edge reaches zero. It is measured from the return series and needs no cost
assumption at all. Compare it to whatever you really pay.

Bars are RTH hourly (6/day), because a daily-bar strategy cannot exceed the ~275 round
turns/year cost ceiling even if it flips every single day, and the ceiling is the point.

Deterministic, numpy-only. Run:  python3 cost_survival.py
"""
from __future__ import annotations

import math

import numpy as np

BARS_PER_DAY = 6                      # RTH hourly bars; there is no 5-minute bar to use
PERIODS_PER_YEAR = 252 * BARS_PER_DAY

FAST_LOOKBACK = 1
SLOW_LOOKBACK = 48                    # 8 sessions
N_BARS = 30000                        # ~20 years of RTH hourly bars

EQUITY = 8000.0                       # the account the domain constitution sizes against
ROUND_TURN_USD = 2.90                 # M2K all-in: $2.43 fees/commission + one $0.50 tick
ANNUAL_COST_BUDGET = 0.10             # 10% of equity per year spent on commissions


def sharpe(x: np.ndarray, periods_per_year: int = PERIODS_PER_YEAR) -> float:
    sd = x.std(ddof=1)
    return 0.0 if sd == 0 else float(x.mean() / sd * math.sqrt(periods_per_year))


def cost_fraction(dollars_per_round_turn: float, equity: float) -> float:
    """One round turn expressed as a fraction of equity, so the core stays unit-free."""
    return dollars_per_round_turn / equity


def make_returns(n: int, rng: np.random.Generator, rho: float = 0.98,
                 slow_vol: float = 6e-05, phi: float = 0.022,
                 noise: float = 0.0035) -> np.ndarray:
    """
    Per-bar returns carrying TWO genuine edges: a persistent drift (`rho`, half-life ~34
    bars) that only a long lookback can see, and a one-bar echo (`phi`) that only the
    shortest lookback can see. Both are real, so neither strategy below is a strawman;
    the question the module asks is which one survives its own turnover.
    """
    mu = np.zeros(n)
    w = rng.normal(0.0, slow_vol, n)
    for i in range(1, n):
        mu[i] = rho * mu[i - 1] + w[i]
    e = rng.normal(0.0, noise, n)
    r = mu.copy()
    r[0] += e[0]
    r[1:] += e[1:] + phi * e[:-1]
    return r


def positions(r: np.ndarray, lookback: int) -> np.ndarray:
    """Position held for bar i+1, decided from returns through bar i. No lookahead."""
    trail = np.convolve(r, np.ones(max(lookback, 1)), mode="full")[:len(r)]
    return np.sign(trail)


def strategy_returns(r: np.ndarray, lookback: int) -> tuple[np.ndarray, np.ndarray]:
    """
    Return (gross per-bar returns, round-turn flags). A flag marks a bar whose position
    differs from the one before it: in steady state each such change closes one contract
    and opens another, which completes exactly one round turn.
    """
    pos = positions(r, lookback)
    gross = pos[:-1] * r[1:]
    turns = np.empty(len(gross), dtype=bool)
    turns[0] = pos[0] != 0
    turns[1:] = pos[1:-1] != pos[:-2]
    return gross, turns


def net_returns(gross: np.ndarray, turns: np.ndarray, cost_frac: float) -> np.ndarray:
    return gross - turns * cost_frac


def breakeven_cost_fraction(gross: np.ndarray, turns: np.ndarray) -> float:
    """
    The per-round-turn cost that drives the total return to zero. Measured from the series,
    so it is the one cost number here that assumes nothing. Infinite when nothing traded.
    """
    n_turns = int(turns.sum())
    if n_turns == 0:
        return float("inf")
    return float(gross.sum() / n_turns)


def round_turns_per_year(turns: np.ndarray,
                         periods_per_year: int = PERIODS_PER_YEAR) -> float:
    return float(turns.mean() * periods_per_year)


def _report(name: str, gross: np.ndarray, turns: np.ndarray, cost_frac: float) -> None:
    net = net_returns(gross, turns, cost_frac)
    g, nsr = sharpe(gross), sharpe(net)
    rty = round_turns_per_year(turns)
    be = breakeven_cost_fraction(gross, turns)
    print(f"  {name}")
    print(f"    gross Sharpe            : {g:+7.2f}   <- believable either way")
    print(f"    net Sharpe              : {nsr:+7.2f}")
    print(f"    net / gross retention   : {nsr / g:+7.2f}")
    print(f"    round turns per year    : {rty:7.0f}   ({rty / 252:.2f}/day)")
    print(f"    annual commission bill  : {rty * cost_frac:7.1%} of equity")
    print(f"    break-even cost per RT  : ${be * EQUITY:6.2f}   vs ${ROUND_TURN_USD:.2f} assumed paid")
    print()


def main() -> None:
    rng = np.random.default_rng(20260818)
    r = make_returns(N_BARS, rng)
    cf = cost_fraction(ROUND_TURN_USD, EQUITY)
    ceiling = ANNUAL_COST_BUDGET / cf

    print("=" * 72)
    print("  Cost survival, the edge that exists gross and does not exist net")
    print("=" * 72)
    print(f"  {N_BARS} RTH hourly bars (~{N_BARS / PERIODS_PER_YEAR:.0f}y), one price series, two holding periods")
    print(f"  ${ROUND_TURN_USD:.2f}/round turn on ${EQUITY:,.0f} = {cf:.4%} of equity per turn")
    print(f"  at a {ANNUAL_COST_BUDGET:.0%} annual cost budget that buys {ceiling:.0f} round turns/year "
          f"({ceiling / 252:.2f}/day)\n")

    fast_g, fast_t = strategy_returns(r, FAST_LOOKBACK)
    slow_g, slow_t = strategy_returns(r, SLOW_LOOKBACK)
    _report(f"FAST  lookback {FAST_LOOKBACK} bar", fast_g, fast_t, cf)
    _report(f"SLOW  lookback {SLOW_LOOKBACK} bars", slow_g, slow_t, cf)

    print("  Takeaway: both gross Sharpes are ordinary and neither is flagged by any other")
    print("  check in this harness. The fast variant spends more than its whole edge on")
    print("  commissions, and only the retention ratio says so. The break-even cost is the")
    print("  number to carry forward: it is measured, not assumed.")
    print("=" * 72)


if __name__ == "__main__":
    main()
