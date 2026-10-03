# Local models (Ollama, LM Studio and other MCP clients)

This page is for running Pink Golem with a model on your own computer, or with any MCP client that isn't covered
by its own page. It explains how to connect Ollama and LM Studio, how to connect anything else, and what to expect
from models of different sizes.

| | |
|---|---|
| Ollama | `python3 bench/agent.py --model gemma4:e4b -i` (Pink Golem's own client for Ollama) |
| Connect LM Studio | `python3 pinkgolem.py connect lmstudio` |
| MCP config | `~/.lmstudio/mcp.json` (Windows: `%USERPROFILE%\.lmstudio\mcp.json`) |
| Skill | paste `skill/pinkgolem/SYSTEM_PROMPT.md` into the system prompt |
| Bot name | **Buddy** |
| Any other client | `python3 pinkgolem.py connect print` |

---

## Ollama

Ollama runs the model but is not an MCP client, so Pink Golem ships one: `bench/agent.py` starts the MCP server,
gives the model the `minecraft_*` tools, runs every call it makes and feeds the results back.

```bash
ollama pull gemma4:e4b                                   # any model with tool calling
python3 bench/agent.py --model gemma4:e4b -i             # a conversation; empty line quits
python3 bench/agent.py --model gemma4:e4b "build me a cottage next to me"
```

- **Context:** the agent asks Ollama for a 32k-token window (`--ctx`). Ollama's default is much smaller, and it
  silently drops the start of a conversation that doesn't fit: the instructions and tools go first. The agent warns
  when a turn gets close to the limit.
- **Fewer tools:** `PINKGOLEM_TOOLS=core` offers only the core tools a build needs, 17 of the 39 (~5k tokens of descriptions
  instead of ~14k). Faster, and small models pick the right tool more often.
- **Instructions:** `SYSTEM_PROMPT.md` by default; `--prompt full` loads `SKILL.md` for bigger models.
- **Nudges:** when the model stops with an empty answer, or reports while its build is still running, the client
  tells it to continue (`--no-nudge` turns this off).
- The body is called **Buddy** (`--bot` to rename it).

How well this works was measured with the bench in `bench/` (scenarios scored by scanning the world afterwards):
see [bench/results.md](../../bench/results.md).

## LM Studio

### Connect

Setup offers this when it finds a `~/.lmstudio` folder. To do it later, or again:

```bash
python3 pinkgolem.py connect lmstudio
```

It merges this entry into `~/.lmstudio/mcp.json`, keeping your other servers and saving a `.bak` copy first:

```json
{
  "mcpServers": {
    "pinkgolem": {
      "command": "/usr/local/bin/node",
      "args": ["/home/you/pinkgolem/mcp-server/index.js"],
      "env": { "MC_BOT_NAME": "Buddy" }
    }
  }
}
```

Use a version of LM Studio with MCP support. Restart it (or reload its MCP settings) after connecting, then enable
the `pinkgolem` tools for your chat.

### Load the skill: SYSTEM_PROMPT.md

A local chat app can't load a skill folder, so Pink Golem ships a condensed version of it:
**`skill/pinkgolem/SYSTEM_PROMPT.md`**. Open it and copy **everything below the `---` line** into the chat's
**system prompt**. It holds:

- the start of every session (`minecraft_status`, then spawn the body),
- ten rules: the ground level, checking the site, blueprints first, waiting for jobs, small builds, undo, chat
  style, directions, recording the build, what `ECONNREFUSED` means,
- a complete worked example, "build me a house next to me", as exact tool calls with JSON arguments.

It is about 750 tokens. The full `SKILL.md` is about 4,000 tokens, plus reference pages. Bigger models with a
large context can take `SKILL.md` instead.

### Bot name: Buddy

Every client gets its own name so that **two AIs never fight over one body**. The name is the AI's fake player,
its chat name and the owner of its builds (undo and protected zones are per owner). With "Buddy" your local model
can play next to Claude or Gemini on the same server. To rename it, edit `MC_BOT_NAME`.

---

## Any other MCP client

Print the entry to paste:

```bash
python3 pinkgolem.py connect print
```

```json
{
  "mcpServers": {
    "pinkgolem": {
      "command": "/usr/local/bin/node",
      "args": ["/home/you/pinkgolem/mcp-server/index.js"]
    }
  }
}
```

The MCP server speaks MCP over **stdio**: the client starts `node …/index.js` itself and talks to it through
standard input/output. Any client that can launch a stdio server works. Clients that only accept HTTP servers need
a stdio-to-HTTP bridge; see their docs.

Add `"env": { "MC_BOT_NAME": "SomeName" }` to give that client its own body. For the instructions, use `SKILL.md`
if the client supports skills or long system prompts, or `SYSTEM_PROMPT.md` if it doesn't.

Other settings the MCP server reads (all optional, in `env` or in `pinkgolem.json`):

| Variable | Default | Use |
|---|---|---|
| `MC_BOT_NAME` | `bot_name` in `pinkgolem.json`, else `Golem` (shown as "Pink Golem") | the AI's name and body |
| `MC_CHAT_COLOR` | `light_purple` | colour of its chat name |
| `MC_SERVER_DIR` | `server` (relative to the Pink Golem folder) | where `server.properties`, `mods/` and `logs/latest.log` are |
| `MC_RCON_HOST` / `MC_RCON_PORT` / `MC_RCON_PASSWORD` | `127.0.0.1` / from `server.properties` | the console connection |
| `PINKGOLEM_CONFIG` | `pinkgolem.json` in the Pink Golem folder | another settings file |

---

## Which model? An honest guide

Pink Golem gives the model **39 tools**. Their descriptions and argument schemas take about **12,500 tokens**
before you say a word (about 5,000 with `PINKGOLEM_TOOLS=core`), and tool results can be a few thousand more.

**Requirements**

1. The model must support **tool calling** (function calling). A model without it will only talk about building.
2. **Context of at least 16k tokens, better 32k.** With less, the tool list alone crowds out the conversation.
3. **Bigger is better**, but less than you'd think: the tools now do most of the hard parts (see below).

**Measured** with [Pink Golem Bench](../../bench/README.md) (six building tasks, scored by scanning the world):

| Model | Pink Golem 1.1.2 | Pink Golem 1.2 |
|---|---|---|
| Gemma 4 E4B (8B, 4-bit, Ollama) | 22 / 100 | 84 / 100 |
| Claude Opus 5.5 | 100 / 100 | not measured yet |

What an ~8B model does reliably on 1.2: spawning and talking, any blueprint at given coordinates, a house next to
the player, a tower next to a named build (all through `minecraft_blueprint` in three to five calls). What it still
gets wrong: arithmetic for custom shapes ("5x5 in front of me" can come out 5x1 or behind them), and buildings with no
blueprint, where it gives up or reuses a cottage. Free-form architecture needs a strong model.

**How small models succeed** (each point fixed a failure the bench recorded; the stories are lessons 66-75 in
[lessons.md](../../skill/pinkgolem/reference/lessons.md)):

- **One call per build:** `minecraft_blueprint {"name":"cottage"}` finds free ground next to the player, turns the
  door toward them, builds, waits and adds it to the map. Next to a build: `{"name":"tower","near":"library"}`.
- **`SYSTEM_PROMPT.md`** is a short script of rules, each from a real mistake, with worked examples.
- **The tools forgive the usual mistakes** (arguments in one string, junk in optional parameters, a player's name
  where a build was expected) and **say failures on the first line** ("FAILED — NOTHING was built"), so the model
  doesn't announce a build that never happened.
- **Errors teach:** when a build would land on a player, the refusal says where the ground in front of them is.
- **Fewer tools:** `PINKGOLEM_TOOLS=core` offers 17 of the 39.
- **The Ollama client** (`bench/agent.py`) nudges a model that stops early and won't run the same failing call a
  third time.

## Tips

- **Stick to blueprints first.** A local model can write its own generators (`minecraft_generate` takes Python
  source in `code`), but blueprints, `minecraft_build` and `minecraft_build_layers` are the range small models do
  reliably.
- **Start a new chat per build.** Short conversations keep small contexts healthy.
- **Say coordinates when it struggles.** "Build a cottage at 100, -61, 40 facing south" removes the hardest step.
- **Temperature low** (0.2-0.5) gives steadier tool arguments.
- Try a prompt that works for Claude first. If your model fails at it, the problem is the model, not the setup.

## Common problems

| Symptom | Fix |
|---|---|
| The model describes tool calls instead of making them | it has no tool-calling support, or the tools aren't enabled for this chat |
| Wrong coordinates, floating houses | the system prompt is missing; paste `SYSTEM_PROMPT.md` |
| Answers get cut off or forget the start | context too small: raise it to 32k if your memory allows |
| Tools answer `ECONNREFUSED` | the Minecraft server is off: `python3 pinkgolem.py start` |

More in [troubleshooting.md](../troubleshooting.md).

## See also

[Claude Code](claude-code.md) · [Claude Desktop](claude-desktop.md) · [Gemini CLI](gemini-cli.md) · [Codex](codex.md)
· [Writing blueprints](../writing-blueprints.md): give small models more one-call builds
