"""
Visualize why the best-of-N backtest is a lie.

Renders the distribution of Sharpe ratios from 200 pure-noise strategies and marks:
  - where the SELECTED winner lands (it's just the right tail of a noise pile),
  - the DSR benchmark (the expected-max Sharpe selection hands you for free),
  - the naive PSR benchmark (zero) that the winner clears and fools you with.

Output: noise_sharpe_distribution.png  (headless; no display needed)

Design follows a small, deliberate spec: one hue for the distribution, reserved
status colors (amber warn / red critical) used ONLY for the thresholds and never as
data series, thin marks, recessive grid/spines, direct labels instead of a legend box.

Run:  python3 plot_noise_distribution.py
"""
from __future__ import annotations

import math

import matplotlib
import numpy as np

matplotlib.use("Agg")  # headless render to file
import matplotlib.pyplot as plt
from deflated_sharpe import (
    _norm_ppf,
    sharpe_ratio,
)

TRADING_DAYS = 252

INK        = "#1f2933"   # primary text
MUTED      = "#7b8794"   # axis / secondary text
GRID       = "#e4e7eb"   # recessive gridline
SERIES     = "#3b82c4"   # the ONE categorical hue: the noise distribution
WARN       = "#d98a00"   # status: the naive PSR benchmark (misleading pass line)
CRITICAL   = "#c0392b"   # status: the selected winner + DSR threshold (the real bar)
SURFACE    = "#ffffff"


def expected_max_benchmark(n_trials: int, var_sr: float) -> float:
    gamma = 0.5772156649015329
    z1 = _norm_ppf(1.0 - 1.0 / n_trials)
    z2 = _norm_ppf(1.0 - 1.0 / (n_trials * math.e))
    return math.sqrt(var_sr) * ((1.0 - gamma) * z1 + gamma * z2)


def main() -> None:
    rng = np.random.default_rng(20260806)
    n_obs, n_trials = 504, 200

    # 200 pure-noise strategies; keep every Sharpe (annualized for readability)
    sharpes = np.array([
        sharpe_ratio(rng.normal(0.0, 0.01, n_obs)) for _ in range(n_trials)
    ]) * math.sqrt(TRADING_DAYS)
    var_daily = float((sharpes / math.sqrt(TRADING_DAYS)).var(ddof=1))
    winner = sharpes.max()
    dsr_bench = expected_max_benchmark(n_trials, var_daily) * math.sqrt(TRADING_DAYS)

    fig, ax = plt.subplots(figsize=(10, 5.4), dpi=130)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    # distribution: one hue, thin white separators between bars (2px surface gap feel)
    counts, _, _ = ax.hist(sharpes, bins=24, color=SERIES, alpha=0.85,
                           edgecolor=SURFACE, linewidth=1.2, zorder=2)

    # Reserve a band above the tallest bar for labels. The threshold lines stop at the
    # top of the data so they never run through their own text.
    bar_top = float(np.asarray(counts).max())
    line_top = bar_top * 1.03
    ax.set_ylim(0, bar_top * 1.44)
    ax.set_xlim(sharpes.min() - 0.35, dsr_bench + 1.35)

    # threshold 1: naive PSR benchmark (zero), the misleading "pass" line
    ax.vlines(0.0, 0, line_top, color=WARN, linewidth=2, linestyle=(0, (4, 2)), zorder=3)
    # threshold 2: DSR benchmark, the bar a real edge must clear
    ax.vlines(dsr_bench, 0, line_top, color=CRITICAL, linewidth=2,
              linestyle=(0, (4, 2)), zorder=3)
    # the selected winner
    ax.vlines(winner, 0, line_top, color=CRITICAL, linewidth=2.5, zorder=4)

    leader = {"arrowstyle": "-", "linewidth": 1, "shrinkA": 3, "shrinkB": 1}
    ax.text(0.0, line_top * 1.03, "naive benchmark (0)\nthe winner clears this: ACCEPT, wrongly",
            ha="center", va="bottom", fontsize=8.5, color=WARN, fontweight="bold")
    ax.annotate(f"selected winner {winner:.2f}\nbelow the bar: REJECT, correctly",
                xy=(winner, line_top), xytext=(winner - 0.30, bar_top * 1.30),
                ha="right", va="center", fontsize=8.5, color=CRITICAL, fontweight="bold",
                arrowprops={**leader, "color": CRITICAL})
    ax.annotate(f"DSR benchmark {dsr_bench:.2f}\nexpected max of 200 trials",
                xy=(dsr_bench, line_top), xytext=(dsr_bench + 0.22, bar_top * 1.14),
                ha="left", va="center", fontsize=8.5, color=CRITICAL,
                arrowprops={**leader, "color": CRITICAL})

    ax.set_title("200 strategies on pure noise: the winner is just the tail",
                 fontsize=13, color=INK, fontweight="bold", pad=14, loc="left")
    ax.text(0, 1.015, "annualized Sharpe of each mean-zero strategy; true edge is zero",
            transform=ax.transAxes, fontsize=9.5, color=MUTED)
    ax.set_xlabel("annualized Sharpe ratio", fontsize=10, color=MUTED)
    ax.set_ylabel("number of strategies", fontsize=10, color=MUTED)

    # recessive chrome
    ax.grid(axis="y", color=GRID, linewidth=1, zorder=0)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9)

    fig.tight_layout()
    out = "noise_sharpe_distribution.png"
    fig.savefig(out, facecolor=SURFACE, bbox_inches="tight")
    print(f"wrote {out}")
    print(f"  winner (annualized Sharpe): {winner:.2f}")
    print(f"  DSR benchmark:              {dsr_bench:.2f}")
    print(f"  winner is at the {100 * (sharpes < winner).mean():.1f}th percentile of noise")


if __name__ == "__main__":
    main()
