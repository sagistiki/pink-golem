#!/usr/bin/env python3
"""Side-by-side screenshots of what each version built, one row per task.

    bench/.venv/bin/python bench/gallery.py --scenarios house_near,bakery \
        --columns "gemma@v0-baseline,gemma@v3-blueprint,opus@v0-baseline"

Each cell is the run with the median score for that task (ties → the first), captioned with its score.
"""
import argparse
import statistics as st
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.image as mpimg  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

import rescore  # noqa: E402
from report import INK, INK2, SCEN_NAME, SURFACE  # noqa: E402

OUT = Path(__file__).resolve().parent / "results" / "charts"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", required=True)
    ap.add_argument("--columns", required=True, help="model-substring@tag, comma-separated")
    ap.add_argument("--labels", help="column titles, comma-separated")
    ap.add_argument("--name", default="gallery")
    a = ap.parse_args()
    rows = rescore.rows()
    scen = a.scenarios.split(",")
    cols = [c.split("@") for c in a.columns.split(",")]
    labels = a.labels.split(",") if a.labels else [f"{m} · {t}" for m, t in cols]
    fig, axes = plt.subplots(len(scen), len(cols), figsize=(3.6 * len(cols), 3.0 * len(scen)), squeeze=False, facecolor=SURFACE)
    for i, s in enumerate(scen):
        for j, (m, t) in enumerate(cols):
            ax = axes[i][j]
            ax.set_facecolor(SURFACE)
            ax.set_xticks([])
            ax.set_yticks([])
            for sp in ax.spines.values():
                sp.set_visible(False)
            runs = sorted([r for r in rows if m in r["model"] and r["tag"] == t and r["scenario"] == s], key=lambda r: r["score"])
            if not runs:
                ax.text(0.5, 0.5, "not run", ha="center", va="center", color=INK2, transform=ax.transAxes)
            else:
                med = runs[(len(runs) - 1) // 2]
                png = Path(med["file"]).with_suffix(".png")
                if png.exists():
                    ax.imshow(mpimg.imread(png))
                else:
                    ax.text(0.5, 0.5, "nothing built", ha="center", va="center", color=INK2, fontsize=11, transform=ax.transAxes)
                mean = st.mean(r["score"] for r in runs)
                ax.set_xlabel(f"score {med['score']}  (mean of {len(runs)}: {mean:.0f})", fontsize=9, color=INK2)
            if i == 0:
                ax.set_title(labels[j], fontsize=11, color=INK, pad=8)
            if j == 0:
                ax.set_ylabel(SCEN_NAME.get(s, s), fontsize=11, color=INK)
    fig.tight_layout()
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / f"{a.name}.png"
    fig.savefig(f, dpi=150, facecolor=SURFACE)
    print(f)


if __name__ == "__main__":
    main()
