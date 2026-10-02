# Local models (LM Studio and other MCP clients)

This page is for running Pink Golem with a model on your own computer, or with any MCP client that isn't covered
by its own page. It explains how to connect LM Studio, how to connect anything else, and what to expect from
models of different sizes.

| | |
|---|---|
| Connect LM Studio | `python3 pinkgolem.py connect lmstudio` |
| MCP config | `~/.lmstudio/mcp.json` (Windows: `%USERPROFILE%\.lmstudio\mcp.json`) |
| Skill | paste `skill/pinkgolem/SYSTEM_PROMPT.md` into the system prompt |
| Bot name | **Buddy** |
| Any other client | `python3 pinkgolem.py connect print` |

---

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

Pink Golem gives the model **38 tools**. Their descriptions and argument schemas take about **12,000 tokens**
before you say a word, and tool results (a structure read as text, a job report) can be a few thousand tokens more.

**Requirements**

1. The model must support **tool calling** (function calling). LM Studio shows which downloaded models do. A model
   without it will only talk about building.
2. **Context of at least 16k tokens, better 32k.** With less, the tool list alone crowds out the conversation.
3. **Bigger is better.** Choosing the right tool among 29 and filling nested arguments (lists of `[x, y, z]`) is
   exactly what small models find hard. Heavy quantization (below about 4-bit) makes it worse.

**What to expect** (rough guidance; models vary a lot)

| Model size | Realistic result |
|---|---|
| under ~7B | often calls the wrong tool or invents arguments. Fine for chatting in game, unreliable for building |
| ~7-14B with good tool calling | follows `SYSTEM_PROMPT.md` step by step: checks the site, runs blueprints, waits for the job, reports |
| ~20-35B | reliable with blueprints and small custom builds with `minecraft_build`, reads vision output sensibly |
| 70B and up / frontier models | can handle `SKILL.md` and plan multi-phase builds |

**There is no "small tool list" mode.** All tools are always offered; only the tools for mods you don't have are
hidden. Small models succeed through two things instead:

- **`SYSTEM_PROMPT.md`** turns building into a fixed script: status → spawn → check the site → run a blueprint
  → wait → report. The model doesn't have to discover the workflow; it only fills in coordinates.
- **Blueprints** do the hard part. `cottage.py`, `modern_villa.py`, `tower.py`, `park.py`, `drop_tower.py` and `tnt_run.py`
  already solve the geometry, block states, doors, stairs, light and furniture. The model only picks a blueprint,
  a position (`--at X,Y,Z`) and a direction (`--facing`). A furnished house is **one tool call**:

```json
minecraft_generate {"script": "skill/pinkgolem/blueprints/cottage.py",
                    "args": ["--at", "14,-61,5", "--facing", "south"], "build": true, "helpers": 3}
```

The server also forgives common small-model mistakes: numbers, booleans and lists sent as strings (`"3"`,
`"true"`, `"[1,2,3]"`) are converted, and every tool that changes blocks has undo, protected zones and verification
behind it.

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
