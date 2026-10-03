#!/usr/bin/env python3
"""Charts and a table from bench/results/summary.jsonl.

    bench/.venv/bin/python bench/report.py --model gemma --tags v0-baseline,v1,v2 [--ref-model opus --ref-tag v0-baseline]

Writes PNGs to bench/results/charts/ and prints a Markdown table. Needs matplotlib
(python3 -m venv bench/.venv && bench/.venv/bin/pip install matplotlib).
"""
import argparse
import json
import statistics as st
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE / "results" / "charts"

# reference palette (dataviz skill, light mode)
SURFACE, INK, INK2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8984", "#e6e5e0"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
SCEN_ORDER = ["hello", "cottage_at", "platform", "house_near", "tower_by_library", "bakery"]
SCEN_NAME = {"hello": "Spawn + say hi", "cottage_at": "Cottage at coordinates", "platform": "5×5 floor + lanterns",
             "house_near": "House next to me", "tower_by_library": "Tower by the library", "bakery": "Free-form bakery"}


def load(path):
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            pass
    return rows


def style(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=9, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def label_of(tag, notes):
    n = notes.get(tag, "")
    return tag if not n else f"{tag}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="substring of the model under test")
    ap.add_argument("--tags", required=True, help="versions in order, comma-separated")
    ap.add_argument("--ref-model", help="substring of a reference model (drawn as a dashed line)")
    ap.add_argument("--ref-tag")
    ap.add_argument("--title", default="Pink Golem Bench")
    a = ap.parse_args()
    tags = a.tags.split(",")
    import rescore
    rows = rescore.rows()
    mine = [r for r in rows if a.model in r["model"] and r["tag"] in tags]
    ref = [r for r in rows if a.ref_model and a.ref_model in r["model"] and (not a.ref_tag or r["tag"] == a.ref_tag)]
    notes = {r["tag"]: r.get("note", "") for r in mine}
    by = defaultdict(list)
    for r in mine:
        by[(r["scenario"], r["tag"])].append(r)
    ref_by = defaultdict(list)
    for r in ref:
        ref_by[r["scenario"]].append(r["score"])
    scen = [s for s in SCEN_ORDER if any((s, t) in by for t in tags)]
    OUT.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "Arial", "text.color": INK, "axes.labelcolor": INK2})
    x = list(range(len(tags)))

    # 1 — score per scenario across versions: small multiples, one line each (+ the reference model dashed)
    cols = 3
    rows_n = (len(scen) + cols - 1) // cols
    fig, axes = plt.subplots(rows_n, cols, figsize=(4.2 * cols, 3.1 * rows_n), squeeze=False, facecolor=SURFACE)
    for i, s in enumerate(scen):
        ax = axes[i // cols][i % cols]
        style(ax)
        means = [st.mean([r["score"] for r in by[(s, t)]]) if by[(s, t)] else None for t in tags]
        pts = [(xi, m) for xi, m in zip(x, means) if m is not None]
        for xi, t in zip(x, tags):
            for r in by[(s, t)]:
                ax.plot(xi, r["score"], "o", ms=4, color=BLUE, alpha=0.28, mec="none")
        rv = st.mean(ref_by[s]) if ref_by.get(s) else None
        if rv is not None:
            ax.axhline(rv, color=ORANGE, lw=1.6, ls=(0, (4, 3)), zorder=1)
            ax.text(-0.35, rv + 2.5, f"Opus 5.5: {rv:.0f}", color=INK2, fontsize=8, va="bottom", ha="left")
        if pts:
            ax.plot([p[0] for p in pts], [p[1] for p in pts], "-o", color=BLUE, lw=2, ms=7, mec=SURFACE, mew=2, zorder=3)
            for k, (px, py) in enumerate(pts):          # every point labelled, below it when it sits on the reference line
                dy = -13 if (rv is not None and abs(py - rv) < 8) or py > 92 else 9
                ax.annotate(f"{py:.0f}", (px, py), xytext=(0, dy), textcoords="offset points", ha="center",
                            va="center", fontsize=9, color=INK if k == len(pts) - 1 else INK2, zorder=4,
                            bbox=dict(boxstyle="round,pad=0.15", fc=SURFACE, ec="none"))
        ax.set_title(SCEN_NAME.get(s, s), fontsize=11, color=INK, loc="left", pad=8)
        ax.set_ylim(-5, 108)
        ax.set_xticks(x, [t.replace("-", "\n", 1) for t in tags], rotation=0, fontsize=8)
        ax.set_xlim(-0.4, len(tags) - 0.6 + 0.4)
        if i % cols == 0:
            ax.set_ylabel("score (0-100)", fontsize=9)
    for j in range(len(scen), rows_n * cols):
        axes[j // cols][j % cols].axis("off")
    fig.suptitle(f"{a.title}: score per task, {a.model} (mean of runs; faint dots = single runs)",
                 x=0.01, ha="left", fontsize=12, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    f1 = OUT / f"scores-by-task-{a.model.replace(':', '-')}.png"
    fig.savefig(f1, dpi=160, facecolor=SURFACE)
    plt.close(fig)

    # 2 — overall: mean score, then process costs, each its own panel (never two y-scales)
    def per_tag(fn):
        out = []
        for t in tags:
            rs = [r for r in mine if r["tag"] == t]
            out.append(fn(rs) if rs else None)
        return out

    panels = [
        ("Mean score, all tasks", per_tag(lambda rs: st.mean(r["score"] for r in rs)), BLUE, "{:.0f}", (0, 105)),
        ("Failed tool calls per run", per_tag(lambda rs: st.mean(r["metrics"]["errors"] + r["metrics"]["bad_args"] for r in rs)), ORANGE, "{:.1f}", None),
        ("Tasks fully solved (score 100)", per_tag(lambda rs: 100 * sum(r["score"] == 100 for r in rs) / len(rs)), AQUA, "{:.0f}%", (0, 105)),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(12.6, 3.3), facecolor=SURFACE)
    for ax, (title, vals, colr, fmtv, ylim) in zip(axes, panels):
        style(ax)
        pts = [(xi, v) for xi, v in zip(x, vals) if v is not None]
        ax.plot([p[0] for p in pts], [p[1] for p in pts], "-o", color=colr, lw=2, ms=7, mec=SURFACE, mew=2)
        for xi, v in pts:
            ax.annotate(fmtv.format(v), (xi, v), xytext=(0, 8), textcoords="offset points", ha="center", fontsize=9, color=INK)
        ax.set_title(title, fontsize=11, color=INK, loc="left", pad=8)
        ax.set_xticks(x, [t.replace("-", "\n", 1) for t in tags], fontsize=8)
        ax.set_xlim(-0.4, len(tags) - 0.6 + 0.4)
        if ylim:
            ax.set_ylim(*ylim)
        else:
            ax.set_ylim(0, max([p[1] for p in pts] + [1]) * 1.25)
    fig.suptitle(f"{a.title}: overall, {a.model}", x=0.01, ha="left", fontsize=12, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    f2 = OUT / f"overall-{a.model.replace(':', '-')}.png"
    fig.savefig(f2, dpi=160, facecolor=SURFACE)
    plt.close(fig)

    # table
    print("| task | " + " | ".join(tags) + (" | Opus |" if ref else " |"))
    print("|---|" + "---|" * (len(tags) + (1 if ref else 0)))
    for s in scen:
        cells = []
        for t in tags:
            sc = [r["score"] for r in by[(s, t)]]
            cells.append(f"{st.mean(sc):.0f} ({len(sc)})" if sc else "–")
        line = f"| {SCEN_NAME.get(s, s)} | " + " | ".join(cells)
        if ref:
            line += f" | {st.mean(ref_by[s]):.0f}" if ref_by.get(s) else " | –"
        print(line + " |")
    for t in tags:
        print(f"- {t}: {notes.get(t, '')}")
    print(f"\n{f1}\n{f2}")


if __name__ == "__main__":
    main()
