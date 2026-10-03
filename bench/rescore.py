#!/usr/bin/env python3
"""Score every saved run again with the CURRENT checks in scenarios.py, so versions tested weeks apart are judged by
the same rules. Runs saved without a context file (*.ctx.json.gz) keep their original score.

    python3 bench/rescore.py            print what changed
"""
import gzip
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from scenarios import BY_ID, count_overlap, score  # noqa: E402

RESULTS = HERE / "results"
REF_COTTAGE = HERE / "state" / "ref-cottage_at.json"


def rows():
    """One dict per run (like a summary.jsonl line), with score/checks recomputed where possible."""
    out = []
    for f in sorted(RESULTS.glob("*/*/*.json")):
        if f.name.endswith(".ctx.json"):
            continue
        r = json.loads(f.read_text())
        ctxf = f.with_name(f.stem + ".ctx.json.gz")
        sc = BY_ID.get(r["scenario"])
        row = {k: r.get(k) for k in ("bench", "tag", "note", "git", "backend", "model", "prompt_variant", "ctx", "think", "nudge",
                                     "scenario", "tier", "rep", "score", "metrics", "time")}
        row["bench"] = row["bench"] or "1"
        row["checks"] = {ch["name"]: ch["ok"] for ch in r["checks"]}
        row["file"] = str(f)
        row["original_score"] = r["score"]
        if ctxf.exists() and sc:
            with gzip.open(ctxf, "rt", encoding="utf-8") as g:
                c = json.load(g)
            c.setdefault("scan", {}).setdefault("cells", [])
            if c.get("library"):
                c["library"] = (c["library"][0], c["library"][1])
            checks, s = score(sc, c)
            row["score"], row["checks"] = s, {n: bool(ok) for n, _, ok, _ in checks}
            row["details"] = {n: d for n, _, _, d in checks}
            # not scored, only reported: did a "no blueprint" task get a stock blueprint (the cottage) instead?
            if r["scenario"] == "bakery" and REF_COTTAGE.exists() and c["scan"].get("counts"):
                row["stock_blueprint"] = count_overlap(c["scan"]["counts"], json.loads(REF_COTTAGE.read_text())["counts"]) >= 0.75
        out.append(row)
    return out


if __name__ == "__main__":
    for r in rows():
        mark = "" if r["score"] == r["original_score"] else f"   (was {r['original_score']})"
        print(f"{r['tag']:<22} {r['model'][-28:]:<28} {r['scenario']:<17} #{r['rep']}  {r['score']:>3}{mark}")
