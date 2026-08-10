"""
Deflated Sharpe Ratio: rejecting strategies that are only lucky.

The demo that most retail trading projects should run and almost none do.

Premise
-------
If you try N strategies on noise and keep the best one, its in-sample Sharpe looks
great -- purely by selection. The Probabilistic Sharpe Ratio (PSR) tests one Sharpe
against a benchmark but knows nothing about how many you tried, so it happily blesses
the winner. The Deflated Sharpe Ratio (DSR, Bailey & Lopez de Prado 2014) haircuts the
observed Sharpe by the number of trials, the skew and kurtosis of returns, and the
sample length -- and correctly refuses to call the noise winner "real".

This script generates PURE NOISE (zero true edge), selects the best of N backtests,
and shows PSR passing it while DSR rejects it. Then it shows DSR does NOT reject a
genuinely-edged strategy -- i.e. it is a discriminator, not a blanket "no".

No market data, no dependencies beyond numpy. Deterministic (seeded).

Run:  python3 deflated_sharpe.py
"""
from __future__ import annotations

import math

import numpy as np

TRADING_DAYS = 252


def _norm_cdf(x: float) -> float:
    """Standard normal CDF via erf -- avoids a scipy dependency."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def sharpe_ratio(returns: np.ndarray) -> float:
    """Non-annualized Sharpe of a per-period return series."""
    sd = returns.std(ddof=1)
    if sd == 0:
        return 0.0
    return returns.mean() / sd


def _sample_skew(x: np.ndarray) -> float:
    m = x.mean()
    s = x.std(ddof=0)
    if s == 0:
        return 0.0
    return float(((x - m) ** 3).mean() / s ** 3)


def _sample_kurtosis(x: np.ndarray) -> float:
    """Non-excess kurtosis (a normal distribution scores 3)."""
    m = x.mean()
    s = x.std(ddof=0)
    if s == 0:
        return 3.0
    return float(((x - m) ** 4).mean() / s ** 4)


def probabilistic_sharpe_ratio(returns: np.ndarray, sr_benchmark: float = 0.0) -> float:
    """
    PSR: P(true SR > benchmark SR) given the observed SR and the return distribution's
    higher moments. Bailey & Lopez de Prado (2012). Returns a probability in [0, 1].
    Knows nothing about how many strategies were tried -- that is DSR's job.
    """
    n = len(returns)
    sr = sharpe_ratio(returns)
    skew = _sample_skew(returns)
    kurt = _sample_kurtosis(returns)
    denom = math.sqrt(1.0 - skew * sr + ((kurt - 1.0) / 4.0) * sr ** 2)
    if denom == 0:
        return float("nan")
    z = (sr - sr_benchmark) * math.sqrt(n - 1) / denom
    return _norm_cdf(z)


def _norm_ppf(p: float) -> float:
    """Inverse normal CDF (Acklam's rational approximation). Good to ~1e-9."""
    if not 0.0 < p < 1.0:
        raise ValueError("p must be in (0,1)")
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
           (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def deflated_sharpe_ratio(returns: np.ndarray, n_trials: int,
                          variance_of_trial_sharpes: float) -> float:
    """
    DSR = PSR evaluated against a benchmark SR that is NOT zero but the expected maximum
    Sharpe achievable from n_trials independent noise strategies. That expected-max is
    what selection bias hands you for free, so beating it is the bar a real edge must clear.

    sr_benchmark = sqrt(V) * ( (1-gamma)*Z^-1(1 - 1/N) + gamma*Z^-1(1 - 1/(N*e)) )
      V     = variance across the trial Sharpes
      gamma = Euler-Mascheroni constant
      N     = number of trials
    """
    gamma = 0.5772156649015329  # Euler-Mascheroni
    z1 = _norm_ppf(1.0 - 1.0 / n_trials)
    z2 = _norm_ppf(1.0 - 1.0 / (n_trials * math.e))
    sr0 = math.sqrt(variance_of_trial_sharpes) * ((1.0 - gamma) * z1 + gamma * z2)
    return probabilistic_sharpe_ratio(returns, sr_benchmark=sr0)


def best_of_n_noise(n_trials: int, n_obs: int,
                    rng: np.random.Generator) -> tuple[np.ndarray, float, float]:
    """
    Run n_trials strategies on PURE NOISE (mean-zero returns), return the one with the
    highest Sharpe plus the variance of all trial Sharpes. Selection bias in a bottle.
    """
    sharpes: list[float] = []
    series: list[np.ndarray] = []
    for _ in range(n_trials):
        r = rng.normal(0.0, 0.01, n_obs)  # 1% daily vol, ZERO true edge
        sharpes.append(sharpe_ratio(r))
        series.append(r)
    sharpe_arr = np.array(sharpes)
    best = int(sharpe_arr.argmax())
    return series[best], float(sharpe_arr[best]), float(sharpe_arr.var(ddof=1))


def genuine_edge(n_obs: int, daily_sharpe: float, rng: np.random.Generator) -> np.ndarray:
    """A strategy with a real (modest) edge: positive mean matched to a target daily Sharpe."""
    vol = 0.01
    mu = daily_sharpe * vol
    return rng.normal(mu, vol, n_obs)


def main() -> None:
    rng = np.random.default_rng(20260806)
    n_obs = 2 * TRADING_DAYS  # ~2 years of daily returns
    n_trials = 200
    cut = 0.95  # accept only if P(real) >= 95%

    print("=" * 72)
    print("  Deflated Sharpe Ratio -- rejecting a lucky noise strategy")
    print("=" * 72)
    print(f"  sample: {n_obs} daily obs (~2y)   trials searched: {n_trials}"
          f"   accept if >= {cut}\n")

    # Case 1: best-of-200 on pure noise
    best, best_sr, var_sr = best_of_n_noise(n_trials, n_obs, rng)
    ann = best_sr * math.sqrt(TRADING_DAYS)
    psr = probabilistic_sharpe_ratio(best, 0.0)
    dsr = deflated_sharpe_ratio(best, n_trials, var_sr)
    print("  CASE 1  best of 200 PURE-NOISE strategies (true edge = ZERO)")
    print(f"    winner daily Sharpe   : {best_sr:+.3f}  (annualized {ann:+.2f})")
    print(f"    PSR  (ignores trials) : {psr:6.3f}   -> {'ACCEPT (WRONG)' if psr >= cut else 'reject'}")
    print(f"    DSR  (haircuts trials): {dsr:6.3f}   -> {'accept' if dsr >= cut else 'REJECT (correct)'}")
    print()

    # Case 2: a genuinely-edged strategy, same trial count
    edged = genuine_edge(n_obs, daily_sharpe=0.16, rng=rng)
    ann2 = sharpe_ratio(edged) * math.sqrt(TRADING_DAYS)
    psr2 = probabilistic_sharpe_ratio(edged, 0.0)
    dsr2 = deflated_sharpe_ratio(edged, n_trials, var_sr)
    print("  CASE 2  a strategy with a REAL edge, judged against the same 200 trials")
    print(f"    daily Sharpe          : {sharpe_ratio(edged):+.3f}  (annualized {ann2:+.2f})")
    print(f"    PSR                   : {psr2:6.3f}   -> {'accept' if psr2 >= cut else 'reject'}")
    print(f"    DSR                   : {dsr2:6.3f}   -> {'ACCEPT (correct)' if dsr2 >= cut else 'reject'}")
    print()

    print("  Takeaway: PSR blesses the noise winner; DSR rejects it and still passes a")
    print("  real edge. The trial count is the difference between a discovery and an artifact.")
    print("=" * 72)


if __name__ == "__main__":
    main()
