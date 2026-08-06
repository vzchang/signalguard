"""
Visualize the leak that purging removes.

Three bars: the no-skill majority baseline, plain shuffled K-Fold (inflated), and purged
K-Fold (honest). The gap between plain and purged, annotated, is the leaked "skill".

Output: purged_cv_leak.png  (headless).
Design: one hue for the honest bars, a reserved warning hue for the inflated one, a
baseline reference line, recessive chrome, direct value labels.
"""
from __future__ import annotations
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from purged_cv_demo import kfold_indices, make_leaky_dataset, run_cv

INK, MUTED, GRID, SURFACE = "#1f2933", "#7b8794", "#e4e7eb", "#ffffff"
HONEST = "#3b82c4"   # the one data hue: legitimate scores
INFLATED = "#d98a00" # reserved warning hue: the leaked score
BASELINE = "#c0392b" # reserved: the no-skill reference line


def main() -> None:
    rng = np.random.default_rng(20260806)
    n, k, h, emb = 1500, 6, 20, 5
    x, y = make_leaky_dataset(n, h, rng)
    base = max(y.mean(), 1 - y.mean())
    folds = kfold_indices(n, k, shuffle=True, rng=np.random.default_rng(1))
    plain = run_cv(x, y, folds, purge=False, label_horizon=h, embargo=emb, n=n)
    purged = run_cv(x, y, folds, purge=True, label_horizon=h, embargo=emb, n=n)

    labels = ["plain shuffled\nK-Fold", "purged\nK-Fold"]
    vals = [plain, purged]
    colors = [INFLATED, HONEST]

    fig, ax = plt.subplots(figsize=(8, 5), dpi=130)
    fig.patch.set_facecolor(SURFACE); ax.set_facecolor(SURFACE)

    xs = np.arange(len(labels))
    ax.bar(xs, vals, width=0.55, color=colors, edgecolor=SURFACE, linewidth=1.5, zorder=3)

    # no-skill baseline reference
    ax.axhline(base, color=BASELINE, linewidth=2, linestyle=(0, (4, 2)), zorder=2)
    ax.text(len(labels) - 0.5, base + 0.002, f"no-skill baseline {base:.3f}",
            ha="right", va="bottom", fontsize=8.5, color=BASELINE, fontweight="bold")

    for xi, v in zip(xs, vals):
        ax.text(xi, v + 0.002, f"{v:.3f}", ha="center", va="bottom",
                fontsize=11, color=INK, fontweight="bold")

    # annotate the leak as the drop from plain to purged
    ax.annotate("", xy=(1, purged), xytext=(1, plain),
                arrowprops=dict(arrowstyle="<->", color=MUTED, lw=1.3))
    ax.text(1.06, (plain + purged) / 2, f"leak\n{plain - purged:+.3f}",
            ha="left", va="center", fontsize=9, color=MUTED)

    ax.set_title("Purging removes the leak that made the backtest look skillful",
                 fontsize=12.5, color=INK, fontweight="bold", loc="left", pad=12)
    ax.text(0, 1.015, "1-NN on a whisper-of-signal feature; labels overlap 20 bars; folds shuffled",
            transform=ax.transAxes, fontsize=9, color=MUTED)
    ax.set_xticks(xs); ax.set_xticklabels(labels, fontsize=9.5, color=INK)
    ax.set_ylabel("cross-validated accuracy", fontsize=10, color=MUTED)
    # bars measure magnitude, so the axis MUST start at zero (a truncated bar axis lies).
    # 0.5 (coin-flip) is the meaningful floor for a binary classifier -- mark it, don't crop to it.
    ax.set_ylim(0.0, plain + 0.06)
    ax.axhline(0.5, color=MUTED, linewidth=1, linestyle=":", zorder=1)
    ax.text(-0.45, 0.5, "coin flip 0.5", ha="left", va="bottom", fontsize=8, color=MUTED)

    ax.grid(axis="y", color=GRID, linewidth=1, zorder=0); ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9)

    fig.tight_layout()
    out = "purged_cv_leak.png"
    fig.savefig(out, facecolor=SURFACE, bbox_inches="tight")
    print(f"wrote {out}  (plain {plain:.3f}, purged {purged:.3f}, baseline {base:.3f})")


if __name__ == "__main__":
    main()
