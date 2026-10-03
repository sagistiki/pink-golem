# Pink Golem Bench: how well does a model build in Minecraft?

A repeatable test of the whole stack (model + skill + MCP tools) on the test server. Each scenario is a request a
player would make; a judge then scans the world and scores what was really built, not what the model said.
It is how Pink Golem was tuned for small local models (see [the results](results.md)).

| File | What it does |
|---|---|
| `agent.py` | Pink Golem for **Ollama**: an MCP client + agent loop. Also usable on its own as a chat with a local model |
| `mcpclient.py` | a tiny stdio MCP client (standard library only) |
| `scenarios.py` | the tasks, from "spawn and say hi" to "a bakery with no blueprint", and their checks |
| `run.py` | runs scenarios on a model (Ollama, or Claude through `claude -p`) and saves everything |
| `world.py`, `bench.sc` | the bench's RCON hands and the judge scan (every block that differs from flat ground) |
| `rescore.py` | scores every saved run again with the current checks, so all versions share one set of rules |
| `report.py` | one model across Pink Golem versions: score per task, failed calls (PNG + table) |
| `leaderboard.py` | the leaderboard: one score out of 100 per model, sub-scores per tier, a model × task grid |
| `gallery.py` | side-by-side screenshots of what each model/version built |
| `models.json` | display names for model ids |

## Use Pink Golem with Ollama

```bash
ollama pull gemma4:e4b                          # any model with tool calling
python3 bench/agent.py --model gemma4:e4b -i    # chat; the model gets the minecraft_* tools
```

- `--ctx 32768` is the default: the tools take ~14k tokens (~5k with `PINKGOLEM_TOOLS=core`), and Ollama silently
  drops the start of a conversation that doesn't fit. The agent warns when a turn gets close.
- `--prompt condensed` (default) loads `skill/pinkgolem/SYSTEM_PROMPT.md`; `--prompt full` loads `SKILL.md`.
- `PINKGOLEM_TOOLS=core python3 bench/agent.py …` offers only the 17 tools a build needs.
- The client nudges a model that stops with an empty answer or reports while a build is still running
  (`--no-nudge` to turn it off).

## Run the bench

Only on a test server nobody plays on: it wipes the arenas (x 4950-6400, z 4950-5050) and, for each run, the AI's
memory files in `data/` (backed up first and restored at the end).

```bash
python3 pinkgolem.py start --background
python3 bench/run.py --calibrate --model x --tag cal       # once: build the reference cottage
python3 bench/run.py --model gemma4:e4b --tag v1 --reps 3 --nudge --tools core
python3 bench/run.py --backend claude --model claude-opus-5-5 --tag v1      # same tasks through Claude Code
python3 -m venv bench/.venv && bench/.venv/bin/pip install matplotlib
bench/.venv/bin/python bench/report.py --model gemma --tags v0-baseline,v1 --ref-model opus
```

Every run saves its transcript, checks, a screenshot and the judge's full scan under `bench/results/<tag>/<model>/`.

## Scoring and the leaderboard

**Pink Golem Bench v1** = the 6 tasks in `scenarios.py` with their checks, frozen. A model's score is the mean of
its task scores (a task's score = the mean of its runs), every task weighted the same, so 100 = every task fully
solved. Sub-scores per tier: Basics (spawn, a blueprint at given coordinates, a small floor), Finding the site (a
house next to the player, a tower next to a named build), Free-form (a bakery with no blueprint). When tasks or
checks change in a way that moves scores, `BENCH_VERSION` goes up and old scores stay in their own table.

A score belongs to a model **on a Pink Golem version** (the `--tag`): compare models on the same tag; compare tags
to see what a change to the skill or tools did for one model.

```bash
bench/.venv/bin/python bench/leaderboard.py --tag v4-core     # every model on the same version
bench/.venv/bin/python bench/leaderboard.py                   # each model on its newest version
```

Adding a model: `python3 bench/run.py --model <ollama model> --tag <current version> --reps 3 --nudge --tools core`
(any Ollama model with tool calling, local or `:cloud`), or `--backend claude --model <claude model>`.

### How a run is scored

Each check has a weight; the score is the share of passed weight. Two rules keep it honest:
- placement checks (near the player, on the ground, next to the library) only count for a real build: a house needs
  a room inside (headroom under a roof), a lookout tower needs a way up;
- burying the player or damaging someone else's build caps the score at 25.
