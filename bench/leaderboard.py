#!/usr/bin/env python3
"""Pink Golem Bench leaderboard: one score out of 100 per model, like the big model benchmarks.

    bench/.venv/bin/python bench/leaderboard.py                       each model on its newest Pink Golem version
    bench/.venv/bin/python bench/leaderboard.py --tag v4-core         every model on the same version (fair comparison)
    bench/.venv/bin/python bench/leaderboard.py --entries "gemma@v0-baseline,gemma@v4-core,opus@v0-baseline"

Score = the mean of the task scores (each task's score = the mean of its runs), every task weighted the same.
Sub-scores per tier. Only complete entries (every task run) get a total; others are listed as incomplete.
Writes results/charts/leaderboard.png, results/charts/leaderboard-tasks.png and prints a Markdown table.
"""
import argparse
import json
import statistics as st
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

import rescore  # noqa: E402
from report import BLUE, GRID, INK, INK2, MUTED, SCEN_NAME, SURFACE, style  # noqa: E402
from scenarios import BENCH, BENCH_VERSION, SCENARIOS, TIERS  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE / "results" / "charts"
NAMES = HERE / "models.json"         # optional: {"model id or substring": "Display name"}
SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]   # sequential blue, light → dark


def display(model):
    names = json.loads(NAMES.read_text()) if NAMES.exists() else {}
    for k, v in names.items():
        if k == model or k in model:
            return v
    return model.split("/")[-1]


def entries(rows, a):
    """[(model, tag)] to show."""
    have = sorted({(r["model"], r["tag"]) for r in rows})
    if a.entries:
        out = []
        for e in a.entries.split(","):
            m, t = e.split("@")
            out += [(mm, tt) for mm, tt in have if m in mm and tt == t]
        return out
    if a.tag:
        return [(m, t) for m, t in have if t == a.tag]
    newest = {}
    for r in sorted(rows, key=lambda r: r.get("time") or ""):
        newest[r["model"]] = r["tag"]
    return sorted(newest.items())


def table(rows, ents):
    scen = [s["id"] for s in SCENARIOS]
    tier_of = {s["id"]: s["tier"] for s in SCENARIOS}
    out = []
    for m, t in ents:
        rs = [r for r in rows if r["model"] == m and r["tag"] == t]
        by = defaultdict(list)
        for r in rs:
            by[r["scenario"]].append(r)
        task = {s: st.mean(r["score"] for r in by[s]) for s in scen if by[s]}
        complete = len(task) == len(scen)
        tiers = {k: st.mean(task[s] for s in scen if tier_of[s] == k and s in task) for k in TIERS
                 if any(tier_of[s] == k and s in task for s in scen)}
        out.append({"model": m, "tag": t, "name": display(m), "task": task, "tiers": tiers, "complete": complete,
                    "total": st.mean(task.values()) if complete else None, "runs": len(rs),
                    "reps": min((len(by[s]) for s in scen if by[s]), default=0),
                    "fail_calls": st.mean(r["metrics"]["errors"] + r["metrics"]["bad_args"] for r in rs) if rs else 0,
                    "seconds": st.mean(r["metrics"]["seconds"] or 0 for r in rs) if rs else 0})
    return sorted(out, key=lambda e: (e["total"] is None, -(e["total"] or 0)))


def label(e, show_tag):
    return f"{e['name']}  ·  {e['tag']}" if show_tag else e["name"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tag", help="only this Pink Golem version")
    ap.add_argument("--entries", help="model-substring@tag, comma-separated")
    ap.add_argument("--name", default="leaderboard")
    ap.add_argument("--subtitle", default="")
    a = ap.parse_args()
    rows = [r for r in rescore.rows() if r.get("bench", "1") == BENCH_VERSION]
    ents = table(rows, entries(rows, a))
    show_tag = len({e["tag"] for e in ents}) > 1
    OUT.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "Arial", "text.color": INK, "axes.labelcolor": INK2})
    done = [e for e in ents if e["complete"]]

    # 1 — the leaderboard: one bar per entry, sorted, the total as a percentage
    fig, ax = plt.subplots(figsize=(10, 0.62 * len(done) + 1.6), facecolor=SURFACE)
    style(ax)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.grid(axis="y", visible=False)
    ys = list(range(len(done)))[::-1]
    ax.barh(ys, [e["total"] for e in done], height=0.56, color=BLUE, edgecolor=SURFACE, linewidth=2)
    for y, e in zip(ys, done):
        ax.text(e["total"] + 1.2, y, f"{e['total']:.1f}%", va="center", fontsize=11, color=INK, fontweight="bold")
    ax.set_yticks(ys, [label(e, show_tag) for e in done], fontsize=10.5, color=INK)
    ax.set_xlim(0, 108)
    ax.set_xticks([0, 20, 40, 60, 80, 100], ["0", "20", "40", "60", "80", "100%"], fontsize=9)
    ax.set_title(f"{BENCH} v{BENCH_VERSION}" + (f" — {a.subtitle}" if a.subtitle else ""), loc="left", fontsize=13, color=INK, pad=26)
    ax.text(0, 1.012, f"{len(SCENARIOS)} building tasks, scored by scanning the world afterwards · mean of runs per task",
            transform=ax.transAxes, fontsize=8.5, color=MUTED, va="bottom")
    fig.tight_layout()
    f1 = OUT / f"{a.name}.png"
    fig.savefig(f1, dpi=160, facecolor=SURFACE)
    plt.close(fig)

    # 2 — model × task grid (sequential blue; the number in every cell, so colour never carries it alone)
    scen = [s["id"] for s in SCENARIOS]
    cm = LinearSegmentedColormap.from_list("seq", SEQ)
    fig, ax = plt.subplots(figsize=(1.35 * len(scen) + 3.6, 0.55 * len(ents) + 1.9), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    for i, e in enumerate(ents):
        for j, s in enumerate(scen):
            v = e["task"].get(s)
            if v is None:
                ax.text(j, i, "–", ha="center", va="center", color=MUTED)
                continue
            ax.add_patch(plt.Rectangle((j - 0.5 + 0.03, i - 0.5 + 0.04), 0.94, 0.92, color=cm(v / 100), lw=0))
            ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=10, color="#ffffff" if v >= 55 else INK)
        tot = f"{e['total']:.1f}" if e["total"] is not None else "incomplete"
        ax.text(len(scen) - 0.35, i, tot, ha="left", va="center", fontsize=10.5, color=INK, fontweight="bold")
    ax.set_xlim(-0.5, len(scen) + 0.6)
    ax.set_ylim(len(ents) - 0.5, -0.5)
    ax.set_xticks(list(range(len(scen))) + [len(scen) + 0.05], [SCEN_NAME[s].replace(" + ", "\n+ ").replace(" next", "\nnext").replace(" at ", "\nat ").replace(" by ", "\nby ").replace("-form ", "-form\n") for s in scen] + ["Total"],
                  fontsize=8.5, color=INK2)
    ax.xaxis.tick_top()
    ax.set_yticks(range(len(ents)), [label(e, show_tag) for e in ents], fontsize=9.5, color=INK)
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.tick_params(length=0)
    ax.set_title(f"{BENCH} v{BENCH_VERSION}: score per task (0-100)", loc="left", fontsize=12, color=INK, pad=34)
    fig.tight_layout()
    f2 = OUT / f"{a.name}-tasks.png"
    fig.savefig(f2, dpi=160, facecolor=SURFACE)
    plt.close(fig)

    # machine-readable copy, published with the charts
    (HERE / "results" / f"{a.name}.json").write_text(json.dumps({"bench": BENCH, "version": BENCH_VERSION, "entries": [
        {k: (round(v, 1) if isinstance(v, float) else v) for k, v in e.items() if k != "task"}
        | {"tasks": {s: round(v, 1) for s, v in e["task"].items()}, "tiers": {TIERS[k]: round(v, 1) for k, v in e["tiers"].items()}}
        for e in ents]}, indent=1))

    # table
    head = "| # | model | Pink Golem | score | " + " | ".join(TIERS.values()) + " | runs/task | failed calls/run | s/run |"
    print(head)
    print("|" + "---|" * (head.count("|") - 1))
    for i, e in enumerate(ents, 1):
        tot = f"**{e['total']:.1f}**" if e["total"] is not None else "incomplete"
        tiers = " | ".join(f"{e['tiers'][k]:.0f}" if k in e["tiers"] else "–" for k in TIERS)
        print(f"| {i} | {e['name']} | {e['tag']} | {tot} | {tiers} | {e['reps']} | {e['fail_calls']:.1f} | {e['seconds']:.0f} |")
    print(f"\n{f1}\n{f2}")


if __name__ == "__main__":
    main()
