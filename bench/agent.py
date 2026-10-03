#!/usr/bin/env python3
"""Pink Golem with a local model in Ollama: an agent loop that gives the model the minecraft_* tools.

Ollama runs models but is not an MCP client, so this script is the client: it starts the Pink Golem MCP server,
hands its tools to the model, runs every tool call the model makes and feeds the results back, until the model
answers in plain text.

    python3 bench/agent.py "build me a cottage next to me"           one request
    python3 bench/agent.py -i                                        a conversation (empty line or Ctrl+D quits)
    python3 bench/agent.py --model gemma4:e4b --prompt full "…"      SKILL.md instead of the condensed SYSTEM_PROMPT.md

Settings: --model (or PINKGOLEM_OLLAMA_MODEL), --ctx (context window, default 32768: the tools alone take ~14k
tokens and Ollama silently drops the start of a longer conversation), --temperature, --think, --bot (the body's
name, default Buddy). Standard library only.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mcpclient import MCP  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skill" / "pinkgolem"
DEFAULT_MODEL = os.environ.get("PINKGOLEM_OLLAMA_MODEL", "gemma4:e4b")
OLLAMA = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
if not OLLAMA.startswith("http"):
    OLLAMA = "http://" + OLLAMA


def system_prompt(which="condensed"):
    """condensed = SYSTEM_PROMPT.md below its '---' line; full = SKILL.md without front matter; or a file path."""
    if which == "condensed":
        t = (SKILL / "SYSTEM_PROMPT.md").read_text(encoding="utf-8")
        return t.split("\n---\n", 1)[1].strip() if "\n---\n" in t else t
    if which == "full":
        t = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        return re.sub(r"^---\n.*?\n---\n", "", t, flags=re.S).strip()
    return Path(which).read_text(encoding="utf-8")


def ollama_tools(mcp_tools):
    return [{"type": "function", "function": {"name": t["name"], "description": t.get("description", ""),
                                               "parameters": t.get("inputSchema") or {"type": "object", "properties": {}}}}
            for t in mcp_tools]


def schema_issues(schema, args):
    """Cheap argument check against the tool's JSON schema: missing required keys, unknown keys, wrong basic types."""
    out = []
    props = (schema or {}).get("properties", {})
    for k in (schema or {}).get("required", []):
        if k not in args:
            out.append(f"missing {k}")
    for k, v in args.items():
        if k not in props:
            out.append(f"unknown {k}")
            continue
        t = props[k].get("type")
        ok = {"string": isinstance(v, str), "number": isinstance(v, (int, float)) and not isinstance(v, bool),
              "integer": isinstance(v, int) and not isinstance(v, bool), "boolean": isinstance(v, bool),
              "array": isinstance(v, list), "object": isinstance(v, dict)}.get(t, True)
        if not ok:
            out.append(f"{k} should be {t}")
        elif "enum" in props[k] and v not in props[k]["enum"]:
            out.append(f"{k}={v!r} not in enum")
    return out


def chat(model, messages, tools, opts, think, timeout=900):
    body = {"model": model, "messages": messages, "tools": tools, "stream": False, "keep_alive": "30m",
            "options": opts}
    if think is not None:
        body["think"] = think
    req = urllib.request.Request(OLLAMA + "/api/chat", json.dumps(body).encode(), {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Ollama {e.code}: {e.read().decode(errors='replace')[:400]}")


class Agent:
    """One model + one MCP connection. run() handles one user message and returns a record of everything."""

    def __init__(self, model=DEFAULT_MODEL, prompt="condensed", ctx=32768, temperature=0.3, think=False,
                 bot="Buddy", mcp_env=None, result_chars=6000, max_turns=30, max_seconds=900, echo=True,
                 extra_system="", nudges=True):
        self.model, self.ctx, self.think = model, ctx, think
        self.opts = {"num_ctx": ctx, "temperature": temperature, "num_predict": 2048}
        self.result_chars, self.max_turns, self.max_seconds, self.echo = result_chars, max_turns, max_seconds, echo
        self.nudges = nudges
        env = {"MC_BOT_NAME": bot}
        env.update(mcp_env or {})
        self.mcp = MCP(env=env)
        self.mcp_tools = self.mcp.tools()
        self.schemas = {t["name"]: t.get("inputSchema") or {} for t in self.mcp_tools}
        self.tools = ollama_tools(self.mcp_tools)
        sp = system_prompt(prompt) + (("\n\n" + extra_system) if extra_system else "")
        self.messages = [{"role": "system", "content": sp}]
        self.system_chars = len(sp)
        self.tool_chars = len(json.dumps(self.tools))

    def say(self, *a):
        if self.echo:
            print(*a, file=sys.stderr, flush=True)

    def run(self, user_text):
        self.messages.append({"role": "user", "content": user_text})
        rec = {"model": self.model, "user": user_text, "turns": [], "stop": None, "ctx": self.ctx,
               "system_chars": self.system_chars, "tool_chars": self.tool_chars, "final": ""}
        t_start = time.time()
        last_sig, same = None, 0
        nudged = {"empty": 0, "jobs": 0}
        failed = {}                     # call signature → times it failed
        hot = False                     # one hotter turn to break a repetition loop
        rec["nudges"] = []
        for turn in range(self.max_turns):
            if time.time() - t_start > self.max_seconds:
                rec["stop"] = "time"
                break
            t0 = time.time()
            opts = dict(self.opts, temperature=max(self.opts["temperature"], 0.9)) if hot else self.opts
            hot = False
            try:
                r = chat(self.model, self.messages, self.tools, opts, self.think)
            except Exception as e:  # noqa: BLE001
                rec["stop"] = f"ollama error: {e}"
                break
            msg = r.get("message", {})
            calls = msg.get("tool_calls") or []
            pt, et = r.get("prompt_eval_count", 0), r.get("eval_count", 0)
            t = {"i": turn, "prompt_tokens": pt, "gen_tokens": et, "seconds": round(time.time() - t0, 1),
                 "content": msg.get("content", ""), "thinking": msg.get("thinking", ""), "calls": [],
                 "ctx_full": pt + et >= self.ctx * 0.92}
            if t["ctx_full"]:
                self.say(f"  ! context nearly full: {pt + et}/{self.ctx} tokens — Ollama drops the oldest messages")
            keep = {"role": "assistant", "content": msg.get("content", "")}
            if calls:
                keep["tool_calls"] = calls
            self.messages.append(keep)
            if msg.get("content"):
                self.say(f"[{self.model}] {msg['content'].strip()[:400]}")
            if not calls:
                nudge = self.nudge(msg.get("content", ""), nudged) if self.nudges else None
                if nudge:
                    rec["turns"].append(t)
                    rec["nudges"].append(nudge)
                    self.say(f"  ↺ nudge: {nudge}")
                    self.messages.append({"role": "user", "content": nudge})
                    continue
                rec["turns"].append(t)
                rec["final"] = msg.get("content", "")
                # a call written as text instead of a real tool call (a classic small-model failure)
                t["text_call"] = bool(re.search(r"minecraft_\w+\s*[({]|\"name\"\s*:\s*\"minecraft_", rec["final"]))
                rec["stop"] = "answer"
                break
            for c in calls:
                fn = c.get("function", {})
                name, args = fn.get("name", ""), fn.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except ValueError:
                        args = {"_raw": args}
                known = name in self.schemas
                issues = schema_issues(self.schemas.get(name), args) if known else ["unknown tool"]
                c0 = time.time()
                csig = json.dumps([name, args], sort_keys=True)
                if self.nudges and failed.get(csig, 0) >= 2:
                    # small models repeat a failing call word for word; don't run it a third time
                    text, is_err = ("NOT RUN — you already made this exact call twice and it failed both times. It will fail "
                                    "again. Write DIFFERENT arguments (read the first error: it says what to change), "
                                    "or use another tool."), True
                    hot = True
                elif known:
                    text, is_err, _imgs = self.mcp.call(name, args)
                else:
                    text, is_err = f"Error: there is no tool called {name}. Tools: {', '.join(self.schemas)}", True
                if is_err:
                    failed[csig] = failed.get(csig, 0) + 1
                    if failed[csig] >= 2:
                        hot = True
                cs = round(time.time() - c0, 1)
                self.say(f"  → {name} {json.dumps(args, ensure_ascii=False)[:300]}" + (f"  ⚠ {issues}" if issues else "")
                         + f"\n    ← {'ERROR ' if is_err else ''}{text.strip()[:240]!r} ({cs}s)")
                shown = text if len(text) <= self.result_chars else (
                    text[: self.result_chars] + f"\n…[{len(text) - self.result_chars} more characters cut]")
                self.messages.append({"role": "tool", "tool_name": name, "content": shown})
                t["calls"].append({"name": name, "args": args, "error": is_err, "issues": issues, "seconds": cs,
                                   "result": text[:20000], "result_chars": len(text)})
                sig = json.dumps([name, args], sort_keys=True)
                same = same + 1 if sig == last_sig else 1
                last_sig = sig
            rec["turns"].append(t)
            if same >= (6 if self.nudges else 4):
                rec["stop"] = "loop"
                break
            # a run of failures (often two calls alternating): make the model stop and rethink instead of burning turns
            streak = 0
            for tt in reversed(rec["turns"]):
                for cc in reversed(tt["calls"]):
                    if not cc["error"]:
                        break
                    streak += 1
                else:
                    continue
                break
            if self.nudges and streak >= 5 and nudged.get("fails", 0) < 2 and streak // 5 > nudged.get("fails", 0):
                nudged["fails"] = nudged.get("fails", 0) + 1
                msg = (f"(Your last {streak} tool calls all failed. Stop repeating them. Read the last error: it says what to "
                       "change. Use different arguments or another tool — or tell the player in one line what's wrong.)")
                rec["nudges"].append(msg)
                self.say(f"  ↺ nudge: {msg}")
                self.messages.append({"role": "user", "content": msg})
        else:
            rec["stop"] = "max_turns"
        rec["seconds"] = round(time.time() - t_start, 1)
        return rec

    def nudge(self, text, nudged):
        """What a good client says when the model stops too early (None = let it stop)."""
        if not text.strip() and nudged["empty"] < 2:
            nudged["empty"] += 1
            return ("(You stopped without a word. Continue the task with the tools — or, if it can't be done, "
                    "tell the player in one line what went wrong.)")
        if nudged["jobs"] < 3:
            txt, err, _ = self.mcp.call("minecraft_jobs", {"action": "list"})
            try:
                busy = [j for j in json.loads(txt) if j.get("status") in ("queued", "running", "checking")]
            except ValueError:
                busy = []
            if busy:
                nudged["jobs"] += 1
                return (f"(Build job {busy[-1].get('id')} is still {busy[-1].get('status')}. Call minecraft_jobs "
                        f"with {{\"action\":\"wait\",\"id\":{busy[-1].get('id')}}} until it is done, check errors, then report.)")
        return None

    def close(self):
        self.mcp.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("request", nargs="*")
    ap.add_argument("-i", "--interactive", action="store_true")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--prompt", default="condensed", help="condensed | full | a file path")
    ap.add_argument("--ctx", type=int, default=32768)
    ap.add_argument("--temperature", type=float, default=0.3)
    ap.add_argument("--think", action="store_true")
    ap.add_argument("--bot", default=os.environ.get("MC_BOT_NAME", "Buddy"))
    ap.add_argument("--log", help="write every turn to this JSONL file")
    ap.add_argument("--no-nudge", action="store_true", help="never prompt the model to continue when it stops early")
    a = ap.parse_args()
    ag = Agent(model=a.model, prompt=a.prompt, ctx=a.ctx, temperature=a.temperature, think=a.think, bot=a.bot,
               nudges=not a.no_nudge)
    print(f"{a.model} · context {a.ctx} · {len(ag.tools)} tools (~{ag.tool_chars // 4} tokens) · bot {a.bot}",
          file=sys.stderr)
    try:
        reqs = [" ".join(a.request)] if a.request else []
        while True:
            if not reqs:
                if not a.interactive and a.request:
                    break
                try:
                    line = input("you> ").strip()
                except EOFError:
                    break
                if not line:
                    break
                reqs = [line]
            rec = ag.run(reqs.pop(0))
            if a.log:
                with open(a.log, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(rec["final"].strip() or f"(stopped: {rec['stop']})")
            if not a.interactive:
                break
    finally:
        ag.close()


if __name__ == "__main__":
    main()
