"""
Visualize the lookahead peek: two equity curves from the SAME signal.

The cheating (same-bar) fill compounds a smooth rocket; the honest (next-bar) fill wanders
around flat. Same strategy, same data, the only difference is whether you booked the
return that defined your signal. That divergence is the peek, drawn.

Output: lookahead_equity.png  (headless).
Design: two categorical hues (cheat vs honest), a flat reference at 1.0, log y so both
curves are legible together, recessive chrome, direct end-labels instead of a legend box.
"""
from __future__ import annotations

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from lookahead_detector import make_returns, pnl_next_bar, pnl_same_bar

INK, MUTED, GRID, SURFACE = "#1f2933", "#7b8794", "#e4e7eb", "#ffffff"
CHEAT = "#c0392b"    # red: the impossible curve
HONEST = "#3b82c4"   # blue: the truth
REF = "#7b8794"


def equity(pnl: np.ndarray) -> np.ndarray:
    return np.cumprod(1.0 + pnl)


def main() -> None:
    r = make_returns(1500, np.random.default_rng(20260806))
    eq_cheat = equity(pnl_same_bar(r)[:-1])   # trim to align lengths
    eq_honest = equity(pnl_next_bar(r))

    fig, ax = plt.subplots(figsize=(9, 5), dpi=130)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    x = np.arange(len(eq_honest))
    ax.plot(x, eq_cheat[:len(x)], color=CHEAT, linewidth=2, zorder=3)
    ax.plot(x, eq_honest, color=HONEST, linewidth=2, zorder=3)
    ax.axhline(1.0, color=REF, linewidth=1, linestyle=":", zorder=1)

    ax.set_yscale("log")
    ax.annotate("same-bar fill (peek)\nbooks the return it used",
                xy=(x[-1], eq_cheat[len(x) - 1]), xytext=(x[-1] * 0.60, eq_cheat[len(x) - 1]),
                ha="right", va="center", fontsize=9, color=CHEAT, fontweight="bold")
    # Sits below the honest curve, not on it. At its own level the text landed on both
    # the line and the 1.0 reference.
    ax.set_ylim(0.32, eq_cheat.max() * 3.2)
    ax.annotate("next-bar fill (honest)\nno edge, wanders near 1.0",
                xy=(x[-1], eq_honest[-1]), xytext=(x[-1] * 0.62, 0.46),
                ha="right", va="center", fontsize=9, color=HONEST, fontweight="bold")

    ax.set_title("Same signal, two fill rules: the peek is a rocket, the truth is flat",
                 fontsize=12.5, color=INK, fontweight="bold", loc="left", pad=12)
    ax.text(0, 1.015, "trailing-momentum signal on a random walk (true edge = zero); log scale",
            transform=ax.transAxes, fontsize=9, color=MUTED)
    ax.set_xlabel("bar", fontsize=10, color=MUTED)
    ax.set_ylabel("growth of $1 (log)", fontsize=10, color=MUTED)

    ax.grid(color=GRID, linewidth=1, zorder=0)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9)

    fig.tight_layout()
    out = "lookahead_equity.png"
    fig.savefig(out, facecolor=SURFACE, bbox_inches="tight")
    print(f"wrote {out}  (cheat end {eq_cheat[len(x)-1]:.2e}, honest end {eq_honest[-1]:.3f})")


if __name__ == "__main__":
    main()
