"""
Visualize walk-forward decay: in-sample vs out-of-sample Sharpe per window.

Paired bars per split, the in-sample Sharpe the optimizer found, next to the
out-of-sample Sharpe it actually delivered. The systematic drop from the first bar to the
second, window after window, is overfitting made visible.

Output: walk_forward_efficiency.png  (headless).
Design: two categorical hues (in-sample vs out-of-sample) in FIXED order, a zero reference
line, recessive chrome, a WFE callout.
"""
from __future__ import annotations

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from walk_forward import make_returns, walk_forward

INK, MUTED, GRID, SURFACE = "#1f2933", "#7b8794", "#e4e7eb", "#ffffff"
IS_HUE = "#9aa5b1"    # muted: in-sample (the flattering number)
OOS_HUE = "#3b82c4"   # blue: out-of-sample (the honest number)
ZERO = "#c0392b"


def main() -> None:
    r = make_returns(3000, np.random.default_rng(20260806))
    rows = walk_forward(r, n_splits=8, grid=list(range(2, 61)))
    is_srs = np.array([x[1] for x in rows])
    oos_srs = np.array([x[2] for x in rows])
    wfe = oos_srs.mean() / is_srs.mean()

    fig, ax = plt.subplots(figsize=(9, 5), dpi=130)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    x = np.arange(len(rows))
    w = 0.4
    ax.bar(x - w / 2, is_srs, w, color=IS_HUE, edgecolor=SURFACE, linewidth=1, zorder=3, label="in-sample")
    ax.bar(x + w / 2, oos_srs, w, color=OOS_HUE, edgecolor=SURFACE, linewidth=1, zorder=3, label="out-of-sample")
    # Baseline sits above the bars. Below them it showed only in the gaps between
    # groups, which read as scattered marks rather than one zero line.
    ax.axhline(0.0, color=MUTED, linewidth=1.0, zorder=4)

    # Headroom so the tallest bar cannot reach the subtitle.
    ax.set_ylim(min(oos_srs.min(), 0) * 1.15, max(is_srs.max(), oos_srs.max()) * 1.28)

    ax.set_title("In-sample edge does not survive: walk-forward on pure noise",
                 fontsize=12.5, color=INK, fontweight="bold", loc="left", pad=12)
    ax.text(0, 1.015,
            f"59 lookbacks optimized per window; mean IS {is_srs.mean():+.2f} "
            f"versus OOS {oos_srs.mean():+.2f}; walk-forward efficiency {wfe:+.2f}",
            transform=ax.transAxes, fontsize=9, color=MUTED)
    ax.set_xlabel("walk-forward split", fontsize=10, color=MUTED)
    ax.set_ylabel("Sharpe ratio", fontsize=10, color=MUTED)
    ax.set_xticks(x)
    ax.set_xticklabels([str(i + 1) for i in x], fontsize=9, color=INK)

    # legend as direct swatches, top-left, no heavy box
    leg = ax.legend(loc="upper right", frameon=False, fontsize=9)
    for txt in leg.get_texts():
        txt.set_color(MUTED)

    ax.grid(axis="y", color=GRID, linewidth=1, zorder=0)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9)

    fig.tight_layout()
    out = "walk_forward_efficiency.png"
    fig.savefig(out, facecolor=SURFACE, bbox_inches="tight")
    print(f"wrote {out}  (IS {is_srs.mean():+.2f}, OOS {oos_srs.mean():+.2f}, WFE {wfe:+.2f})")


if __name__ == "__main__":
    main()
