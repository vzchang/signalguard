"""
Visualize the cost ceiling: gross vs net Sharpe across the turnover a strategy chooses.

One price series, one strategy family, the holding period swept from 1 bar to 160. Gross
Sharpe wanders without trend, because holding longer neither helps nor hurts the edge much.
Net Sharpe falls off a cliff as turnover rises, and crosses zero close to the round-turn
budget the account can actually afford.

The sweep is DESCRIPTIVE, not a search: no parameter is selected from it and no result is
carried forward. It exists to show the shape of the cost constraint.

Output: cost_survival_curve.png  (headless).
Design: two categorical hues in FIXED order (gross = the flattering number, net = the
honest one), a zero reference, a vertical budget marker, direct end labels.
"""
from __future__ import annotations

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from cost_survival import (
    ANNUAL_COST_BUDGET,
    EQUITY,
    N_BARS,
    ROUND_TURN_USD,
    cost_fraction,
    make_returns,
    net_returns,
    round_turns_per_year,
    sharpe,
    strategy_returns,
)

INK, MUTED, GRID, SURFACE = "#1f2933", "#7b8794", "#e4e7eb", "#ffffff"
GROSS_HUE = "#b05c3e"   # terracotta: gross, the number that does not pay for itself
NET_HUE = "#3b82c4"     # blue: net, the honest number
ZERO = "#c0392b"

LOOKBACKS = [1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24, 32, 40, 48, 64, 80, 96, 128, 160]


def main() -> None:
    r = make_returns(N_BARS, np.random.default_rng(20260818))
    cf = cost_fraction(ROUND_TURN_USD, EQUITY)
    ceiling = ANNUAL_COST_BUDGET / cf

    rows = []
    for k in LOOKBACKS:
        g, t = strategy_returns(r, k)
        rows.append((round_turns_per_year(t), sharpe(g), sharpe(net_returns(g, t, cf))))
    rows.sort()
    rty = np.array([x[0] for x in rows])
    gross_sr = np.array([x[1] for x in rows])
    net_sr = np.array([x[2] for x in rows])

    fig, ax = plt.subplots(figsize=(9, 5), dpi=130)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    ax.axvspan(ceiling, rty.max() * 1.15, color=GRID, alpha=0.55, zorder=0)
    ax.axhline(0.0, color=ZERO, linewidth=1.0, linestyle=(0, (4, 3)), zorder=2)
    ax.axvline(ceiling, color=MUTED, linewidth=1.2, zorder=2)

    ax.plot(rty, gross_sr, color=GROSS_HUE, linewidth=2, marker="o", markersize=4,
            markeredgecolor=SURFACE, markeredgewidth=1.2, zorder=4, label="gross Sharpe")
    ax.plot(rty, net_sr, color=NET_HUE, linewidth=2, marker="o", markersize=4,
            markeredgecolor=SURFACE, markeredgewidth=1.2, zorder=5, label="net Sharpe")

    ax.set_xscale("log")
    ax.set_xlim(rty.min() * 0.85, rty.max() * 1.15)
    ax.set_ylim(min(net_sr.min(), 0) * 1.25, max(gross_sr.max(), 0) * 1.45)

    # direct labels at the fast end, where the two lines are furthest apart
    ax.annotate("gross", (rty[-1], gross_sr[-1]), textcoords="offset points",
                xytext=(-6, 10), ha="right", fontsize=9.5, color=GROSS_HUE, fontweight="bold")
    ax.annotate("net", (rty[-1], net_sr[-1]), textcoords="offset points",
                xytext=(-6, -14), ha="right", fontsize=9.5, color=NET_HUE, fontweight="bold")
    ax.annotate(f"{ANNUAL_COST_BUDGET:.0%}-of-equity budget\n{ceiling:.0f} round turns/yr",
                (ceiling, ax.get_ylim()[1]), textcoords="offset points",
                xytext=(8, -26), ha="left", fontsize=8.5, color=MUTED)

    ax.set_title("Past the cost ceiling, a positive gross Sharpe is a negative net one",
                 fontsize=12.5, color=INK, fontweight="bold", loc="left", pad=12)
    ax.text(0, 1.015,
            f"one series, holding period swept 1 to {LOOKBACKS[-1]} bars; "
            rf"\${ROUND_TURN_USD:.2f} per round turn on \${EQUITY:,.0f}",
            transform=ax.transAxes, fontsize=9, color=MUTED)
    ax.set_xlabel("round turns per year (log scale)", fontsize=10, color=MUTED)
    ax.set_ylabel("annualized Sharpe ratio", fontsize=10, color=MUTED)

    leg = ax.legend(loc="lower left", frameon=False, fontsize=9)
    for txt in leg.get_texts():
        txt.set_color(MUTED)

    ax.grid(axis="y", color=GRID, linewidth=1, zorder=1)
    ax.set_axisbelow(False)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.set_xticks([50, 100, 200, 400, 800])
    ax.set_xticklabels(["50", "100", "200", "400", "800"])

    fig.tight_layout()
    out = "cost_survival_curve.png"
    fig.savefig(out, facecolor=SURFACE, bbox_inches="tight")
    crossing = rty[np.argmin(np.abs(net_sr))]
    print(f"wrote {out}  (budget ceiling {ceiling:.0f} RT/yr, net crosses zero near {crossing:.0f} RT/yr)")


if __name__ == "__main__":
    main()
