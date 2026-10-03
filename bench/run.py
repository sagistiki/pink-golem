#!/usr/bin/env python3
"""Run bench scenarios against a model and score what it built.

    python3 bench/run.py --model huihui_ai/gemma-4-abliterated:e4b --tag v0 --tier 1 --reps 3
    python3 bench/run.py --backend claude --model claude-opus-5-5 --tag v0 --scenarios hello,platform

Every run: reset the scenario's arena, put Tester in the middle, wipe the AI's memory files (map, zones, notes,
undo, people, chat) so runs can't help each other, prepare the scenario, let the model work, wait for its build
jobs, then scan the arena and score it. Results go to bench/results/<tag>/<model>/<scenario>-<rep>.json, a
screenshot next to it, and one line per run in bench/results/summary.jsonl.

Needs the test server running (python3 pinkgolem.py start --background). Never point it at a world people play in:
it wipes the arenas (x 4950-6400, z 4950-5050) and the AI memory files in data/ (backed up and restored).
"""
import argparse
import base64
import gzip
import json
import math
import os
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from agent import Agent, system_prompt  # noqa: E402
from mcpclient import MCP  # noqa: E402
from scenarios import BENCH_VERSION, BY_ID, SCENARIOS, TESTER, arena, bbox, inside, score  # noqa: E402
from world import GROUND, World  # noqa: E402

RESULTS = HERE / "results"
MEMORY_FILES = ["world_index.json", "zones.json", "people.json", "LEARNINGS.md", "undo.json", "chat-context.jsonl"]
BENCH_CFG = HERE / "state" / "pinkgolem.bench.json"


def bench_config():
    """pinkgolem.json + Tester as an owner + code allowed (a model without file access writes generators via `code`)."""
    cfg = json.loads((ROOT / "pinkgolem.json").read_text())
    sec = cfg.setdefault("security", {})
    sec["owners"] = sorted(set(sec.get("owners", [])) | {TESTER})
    sec["allow_code"] = True
    BENCH_CFG.parent.mkdir(parents=True, exist_ok=True)
    BENCH_CFG.write_text(json.dumps(cfg, indent=2))
    return str(BENCH_CFG)


class Memory:
    """Back up the AI memory files once, wipe them before every run, restore them at the end."""

    def __init__(self):
        self.dir = HERE / "state" / ("backup-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
        self.dir.mkdir(parents=True, exist_ok=True)
        for f in MEMORY_FILES:
            if (ROOT / "data" / f).exists():
                shutil.copy2(ROOT / "data" / f, self.dir / f)

    def wipe(self):
        for f in MEMORY_FILES:
            (ROOT / "data" / f).unlink(missing_ok=True)

    def restore(self):
        self.wipe()
        for f in self.dir.iterdir():
            shutil.copy2(f, ROOT / "data" / f.name)


# ── backends: each returns a normalised record {calls:[{name,args,error,issues,result}], turns, final, stop, …} ──
def run_ollama(a, sc_prompt, bot, cfg_path, extra_system=""):
    ag = Agent(model=a.model, prompt=a.prompt, ctx=a.ctx, temperature=a.temperature, think=a.think, bot=bot,
               mcp_env={"PINKGOLEM_CONFIG": cfg_path, **({"PINKGOLEM_TOOLS": a.tools} if a.tools else {})}, max_turns=a.max_turns, max_seconds=a.max_seconds,
               echo=not a.quiet, extra_system=extra_system, nudges=a.nudge)
    rec = ag.run(sc_prompt)
    rec["calls"] = [c for t in rec["turns"] for c in t["calls"]]
    rec["max_prompt_tokens"] = max([t["prompt_tokens"] for t in rec["turns"]] or [0])
    rec["ctx_full"] = any(t.get("ctx_full") for t in rec["turns"])
    rec["text_call"] = any(t.get("text_call") for t in rec["turns"])
    return rec, ag.mcp, ag


def run_claude(a, sc_prompt, bot, cfg_path):
    mcp_cfg = HERE / "state" / f"mcp-{bot}.json"
    mcp_cfg.write_text(json.dumps({"mcpServers": {"pinkgolem": {
        "command": shutil.which("node") or "node", "args": [str(ROOT / "mcp-server" / "index.js")],
        "env": {"MC_BOT_NAME": bot, "PINKGOLEM_CONFIG": cfg_path, **({"PINKGOLEM_TOOLS": a.tools} if a.tools else {})}}}}))
    skill_file = HERE / "state" / "skill-prompt.md"
    skill_file.write_text(system_prompt(a.prompt if a.prompt != "condensed" else "full"))
    claude = os.path.expanduser("~/.claude/local/claude")
    claude = claude if os.path.exists(claude) else (shutil.which("claude") or "claude")
    cmd = [claude, "-p", sc_prompt, "--model", a.model, "--output-format", "stream-json", "--verbose",
           "--mcp-config", str(mcp_cfg), "--strict-mcp-config", "--setting-sources", "project",
           "--disable-slash-commands", "--append-system-prompt-file", str(skill_file),
           "--permission-mode", "bypassPermissions",
           "--allowedTools", "mcp__pinkgolem", "Read", "Glob", "Grep", "Write", "Edit",
           "--disallowedTools", "Bash", "WebFetch", "WebSearch", "Task", "Agent"]
    t0 = time.time()
    p = subprocess.Popen(cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    calls, pending, final, usage, turns = [], {}, "", {}, 0
    try:
        out, err = p.communicate(timeout=a.max_seconds + 300)
    except subprocess.TimeoutExpired:
        p.kill()
        out, err = p.communicate()
    for line in out.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("type") == "assistant":
            turns += 1
            for b in ev["message"].get("content", []):
                if b.get("type") == "tool_use":
                    name = b["name"].split("__")[-1] if b["name"].startswith("mcp__") else b["name"]
                    c = {"name": name, "args": b.get("input", {}), "error": False, "issues": [], "result": ""}
                    pending[b["id"]] = c
                    calls.append(c)
                    if not a.quiet:
                        print(f"  → {name} {json.dumps(b.get('input', {}))[:300]}", file=sys.stderr)
                elif b.get("type") == "text" and not a.quiet:
                    print(f"[{a.model}] {b['text'][:400]}", file=sys.stderr)
        elif ev.get("type") == "user":
            for b in (ev.get("message", {}).get("content") or []):
                if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("tool_use_id") in pending:
                    c = pending[b["tool_use_id"]]
                    cont = b.get("content")
                    c["result"] = (cont if isinstance(cont, str) else
                                   "\n".join(x.get("text", "") for x in (cont or []) if isinstance(x, dict)))[:20000]
                    c["error"] = bool(b.get("is_error"))
        elif ev.get("type") == "result":
            final = ev.get("result", "")
            usage = ev.get("usage", {})
            usage["cost_usd"] = ev.get("total_cost_usd")
    rec = {"model": a.model, "user": sc_prompt, "calls": calls, "final": final, "stop": "answer" if final else "error",
           "seconds": round(time.time() - t0, 1), "turns": [{} for _ in range(turns)], "usage": usage,
           "stderr": err[-2000:], "max_prompt_tokens": 0, "ctx_full": False, "text_call": False}
    return rec, None, None


# ── metrics from the transcript ───────────────────────────────────────────────
def process_metrics(rec):
    calls = rec["calls"]
    names = [c["name"] for c in calls]
    gen_build = [i for i, c in enumerate(calls) if c["name"] == "minecraft_generate" and c["args"].get("build") in (True, "true")]
    waited = any(n == "minecraft_jobs" and (calls[i]["args"].get("action") == "wait")
                 for i, n in enumerate(names) if gen_build and i > gen_build[0])
    return {
        "calls": len(calls),
        "errors": sum(1 for c in calls if c["error"]),
        "bad_args": sum(1 for c in calls if c.get("issues")),
        "unknown_tool": sum(1 for c in calls if "unknown tool" in (c.get("issues") or [])),
        "status_first": bool(names) and names[0] == "minecraft_status",
        "checked_site": "minecraft_vision" in names or "minecraft_survey" in names,
        "waited_for_jobs": waited if gen_build else None,
        "map_add": any(c["name"] == "minecraft_map" and c["args"].get("action") == "add" for c in calls),
        "notes_add": any(c["name"] == "minecraft_notes" and c["args"].get("action") == "add" for c in calls),
        "chats": names.count("minecraft_chat"),
        "turns": len(rec.get("turns", [])),
        "seconds": rec.get("seconds"),
        "stop": rec.get("stop"),
        "max_prompt_tokens": rec.get("max_prompt_tokens", 0),
        "ctx_full": rec.get("ctx_full", False),
        "text_call": rec.get("text_call", False),
    }


def roof_coverage(scan):
    """Share of the inside of the walls that has something overhead (walls = blocks 1-3 above the ground)."""
    walls = [c for c in scan["cells"] if GROUND + 1 <= c[1] <= GROUND + 3]
    lo, hi = bbox(walls)
    if not lo or hi[0] - lo[0] < 2 or hi[2] - lo[2] < 2:
        return 0.0
    over = {(c[0], c[2]) for c in scan["cells"] if c[1] >= GROUND + 3}
    inner = [(x, z) for x in range(lo[0] + 1, hi[0]) for z in range(lo[2] + 1, hi[2])]
    return sum(1 for q in inner if q in over) / len(inner)


def score_run(sc, c):
    return score(sc, c)


def wait_jobs(mcp, limit=600):
    t0 = time.time()
    jobs = []
    while time.time() - t0 < limit:
        txt, err, _ = mcp.call("minecraft_jobs", {"action": "list"})
        try:
            jobs = json.loads(txt)
        except ValueError:
            jobs = []
        if not any(j.get("status") in ("queued", "running", "checking") for j in jobs):
            break
        time.sleep(3)
    return jobs


def calibrate():
    """Build every scenario's reference (the blueprint with the right arguments) as the Judge, and save its counts."""
    w = World()
    w.load_judge()
    cfg_path = bench_config()
    mem = Memory()
    judge = MCP(env={"MC_BOT_NAME": "Judge", "PINKGOLEM_CONFIG": cfg_path})
    try:
        for sc in SCENARIOS:
            if not sc.get("reference"):
                continue
            ar = arena(sc["arena"])
            w.forceload(ar["box"])
            w.reset(ar["box"])
            mem.wipe()
            ref = sc["reference"]
            txt, err, _ = judge.call("minecraft_generate", {"script": ref["script"], "args": ref["args"](ar), "build": True})
            print(txt[:600], file=sys.stderr)
            wait_jobs(judge)
            scan = w.scan(ar["box"])
            (HERE / "state" / f"ref-{sc['id']}.json").write_text(json.dumps({k: scan[k] for k in ("n", "lo", "hi", "counts")}))
            print(f"reference {sc['id']}: {scan['n']} blocks, box {scan['lo']}..{scan['hi']}", file=sys.stderr)
            w.reset(ar["box"])
            w.forceload(ar["box"], on=False)
    finally:
        judge.close()
        mem.restore()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backend", choices=["ollama", "claude"], default="ollama")
    ap.add_argument("--model", required=True)
    ap.add_argument("--tag", required=True, help="the version under test, e.g. v0-baseline")
    ap.add_argument("--note", default="")
    ap.add_argument("--scenarios", help="comma-separated ids")
    ap.add_argument("--tier", type=int, help="run every scenario up to this tier")
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--prompt", default="condensed", help="condensed | full | path (claude: always the full skill unless a path)")
    ap.add_argument("--ctx", type=int, default=32768)
    ap.add_argument("--temperature", type=float, default=0.3)
    ap.add_argument("--think", action="store_true")
    ap.add_argument("--max-turns", type=int, default=30)
    ap.add_argument("--max-seconds", type=int, default=900)
    ap.add_argument("--bot", help="bot name (default: from the model)")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--nudge", action="store_true", help="ollama: let the client nudge a model that stops early")
    ap.add_argument("--tools", help="PINKGOLEM_TOOLS for the MCP: core | comma-separated names (default: all)")
    ap.add_argument("--calibrate", action="store_true", help="build each scenario's reference blueprint and save its block counts")
    a = ap.parse_args()
    if a.calibrate:
        return calibrate()
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))     # so `finally` restores the memory files

    if a.scenarios:
        todo = [BY_ID[s] for s in a.scenarios.split(",")]
    else:
        todo = [s for s in SCENARIOS if s["tier"] <= (a.tier or 9)]
    short = a.model.split("/")[-1].replace(":", "-")
    bot = a.bot or ("Opus" if "opus" in a.model else "Sonnet" if "sonnet" in a.model else "Gemma" if "gemma" in a.model else "Buddy")
    w = World()
    if not w.up():
        sys.exit("The test server is not running: python3 pinkgolem.py start --background")
    w.load_judge()
    cfg_path = bench_config()
    mem = Memory()
    judge = MCP(env={"MC_BOT_NAME": "Judge", "PINKGOLEM_CONFIG": cfg_path})
    outdir = RESULTS / a.tag / short
    outdir.mkdir(parents=True, exist_ok=True)
    git = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "mcp-server", "skill"], cwd=ROOT,
                                capture_output=True, text=True).stdout.strip())
    try:
        for sc in todo:
            ar = arena(sc["arena"])
            av = dict(ar, **(sc.get("vars", lambda _a: {})(ar)))
            prompt = sc["prompt"].format(**av)
            ref = None
            if sc.get("reference"):
                ref_file = HERE / "state" / f"ref-{sc['id']}.json"
                if ref_file.exists():
                    ref = json.loads(ref_file.read_text())
            for rep in range(1, a.reps + 1):
                print(f"\n=== {a.tag} · {short} · {sc['id']} #{rep} ===\n{prompt}", file=sys.stderr)
                w.forceload(ar["box"])
                w.kill_bots([bot, "Judge"] + w.crew)
                w.reset(ar["box"])
                mem.wipe()
                w.place_tester(TESTER, ar["cx"], GROUND + 1, ar["cz"], yaw=180)
                time.sleep(1)
                c = {"arena": ar, "world": w, "judge": judge}
                if sc.get("setup"):
                    sc["setup"](c)
                if c.get("library"):
                    c["lib_before"] = w.scan(((c["library"][0][0], c["library"][0][2]), (c["library"][1][0], c["library"][1][2])), name="lib")["counts"]
                t_run = time.time()
                if a.backend == "ollama":
                    rec, mcp, ag = run_ollama(a, prompt, bot, cfg_path)
                    OPEN.append(ag)
                    jobs = wait_jobs(mcp)
                else:
                    rec, mcp, ag = run_claude(a, prompt, bot, cfg_path)
                    jobs = [json.loads(x["result"]) for x in rec["calls"] if x["name"] == "minecraft_jobs" and x["result"].strip().startswith("{")]
                time.sleep(1)
                bot_now = w.find(bot)
                scan = w.scan(ar["box"], max_cells=60000)
                tp = w.pos(TESTER) or [ar["cx"] + .5, GROUND + 1, ar["cz"] + .5]
                feet = [math.floor(tp[0]), math.floor(tp[1]), math.floor(tp[2])]
                c.update(scan=scan, tester=tp, calls=rec["calls"], jobs=jobs, bot_online=bool(bot_now),
                         bot_pos=w.pos(bot_now) if bot_now else None, reference=ref,
                         tester_free=not any(p[:3] in (feet, [feet[0], feet[1] + 1, feet[2]]) for p in scan["cells"]),
                         roofed=roof_coverage(scan))
                if c.get("library"):
                    lo, hi = c["library"]
                    c["lib_scan"] = w.scan(((lo[0], lo[2]), (hi[0], hi[2])), name="lib")
                checks, score = score_run(sc, c)
                # everything the checks read, so every run can be re-scored later with the final rules (rescore.py)
                keep = {k: c[k] for k in ("arena", "scan", "tester", "calls", "jobs", "bot_online", "bot_pos", "reference",
                                          "tester_free", "roofed", "library", "lib_before", "lib_scan") if k in c}
                keep["calls"] = [{"name": x["name"], "args": x["args"], "error": x["error"], "result": x["result"][:3000]} for x in keep["calls"]]
                with gzip.open(outdir / f"{sc['id']}-{rep}.ctx.json.gz", "wt", encoding="utf-8") as f:
                    json.dump(keep, f, default=str)
                pm = process_metrics(rec)
                # builds the model put outside its arena (wrong coordinates): count, then clear them
                undo = json.loads((ROOT / "data" / "undo.json").read_text()) if (ROOT / "data" / "undo.json").exists() else []
                (x1, z1), (x2, z2) = ar["box"]
                outside = [u for u in undo if u.get("owner") == bot and not (x1 <= u["lo"][0] and u["hi"][0] <= x2 and z1 <= u["lo"][2] and u["hi"][2] <= z2)]
                for u in reversed(outside):     # undo restores exactly what was there (flattening would erase villages)
                    txt, err, _ = judge.call("minecraft_undo", {"match": u["id"], "any_owner": True, "force": True})
                    if err:
                        print("  could not undo an outside build:", txt[:200], file=sys.stderr)
                pm["builds_outside_arena"] = len(outside)
                shot = None
                if scan["n"]:
                    lo, hi = scan["lo"], scan["hi"]
                    txt, err, imgs = judge.call("minecraft_screenshot", {"from": [lo[0] - 2, GROUND, lo[2] - 2], "to": [hi[0] + 2, hi[1] + 1, hi[2] + 2], "mode": "iso", "view": "se", "entities": True})
                    if imgs:
                        shot = outdir / f"{sc['id']}-{rep}.png"
                        shot.write_bytes(base64.b64decode(imgs[0][1]))
                if ag:
                    ag.close()
                    OPEN.remove(ag)
                result = {"bench": BENCH_VERSION, "tag": a.tag, "note": a.note, "git": git + ("+dirty" if dirty else ""), "backend": a.backend,
                          "model": a.model, "prompt_variant": a.prompt, "ctx": a.ctx, "think": a.think, "nudge": a.nudge, "tools": a.tools,
                          "temperature": a.temperature, "scenario": sc["id"], "tier": sc["tier"], "rep": rep,
                          "prompt": prompt, "score": score,
                          "checks": [{"name": n, "weight": wt, "ok": bool(ok), "detail": d} for n, wt, ok, d in checks],
                          "metrics": pm, "jobs": jobs, "scan": {k: scan[k] for k in ("n", "lo", "hi", "counts")},
                          "time": datetime.now().isoformat(timespec="seconds"), "screenshot": str(shot) if shot else None,
                          "record": rec}
                (outdir / f"{sc['id']}-{rep}.json").write_text(json.dumps(result, indent=1, ensure_ascii=False, default=str))
                with open(RESULTS / "summary.jsonl", "a", encoding="utf-8") as f:
                    f.write(json.dumps({k: result[k] for k in ("tag", "note", "git", "backend", "model", "prompt_variant", "ctx", "think", "nudge", "scenario", "tier", "rep", "score", "metrics", "time")}
                                       | {"checks": {ch["name"]: ch["ok"] for ch in result["checks"]}}, ensure_ascii=False) + "\n")
                fails = [f"{n} ({d})" for n, _, ok, d in checks if not ok]
                print(f"--- score {score}  ·  {pm['calls']} calls, {pm['errors']} errors, {pm['bad_args']} bad args, "
                      f"{pm['seconds']}s, stop={pm['stop']}" + (f"\n    failed: {'; '.join(fails)}" if fails else ""), file=sys.stderr)
                w.kill_bots([bot] + w.crew)
                w.forceload(ar["box"], on=False)
    finally:
        for ag in OPEN:            # a run that crashed: don't leave its MCP server behind
            ag.close()
        judge.close()
        mem.restore()


OPEN = []

if __name__ == "__main__":
    main()
