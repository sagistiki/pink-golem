# Codex

This page connects OpenAI's **Codex CLI** to your ClawdBlock server. Codex is a terminal agent: it reads the skill,
writes build generators into `jobs/`, and uses all 33 tools. Its body in the game is called **Codex**, so it can
build next to other AIs.

| | |
|---|---|
| Connect | `python3 clawdblock.py connect codex` |
| MCP config | `~/.codex/config.toml` (Windows: `%USERPROFILE%\.codex\config.toml`) |
| Skill | `AGENTS.md` in the ClawdBlock folder, loaded automatically |
| Bot name | **Codex** |
| Start it | `codex`, run inside the ClawdBlock folder |

---

## Connect

Setup offers this when it finds the `codex` command or a `~/.codex` folder. To do it later, or again:

```bash
python3 clawdblock.py connect codex
```

## What it writes

A `[mcp_servers.clawdblock]` table in `~/.codex/config.toml`. If the file already has one, it is replaced. The
rest of the file is kept.

```toml
[mcp_servers.clawdblock]
command = "/usr/local/bin/node"
args = ["/home/you/clawdblock/mcp-server/index.js"]
env = { MC_BOT_NAME = "Codex" }
startup_timeout_sec = 20
tool_timeout_sec = 120
```

| Key | Why |
|---|---|
| `command`, `args` | absolute paths to `node` and the MCP server, so it starts from any folder |
| `env.MC_BOT_NAME` | Codex's own body in the game |
| `startup_timeout_sec = 20` | the first start loads the whole tool layer; gives it time |
| `tool_timeout_sec = 120` | some tools wait on purpose: `minecraft_wait_for_chat` up to 110 s, `minecraft_jobs action:wait` and `minecraft_monitor` up to 50 s. A shorter timeout cuts them off |

## How the skill loads

Codex reads `AGENTS.md` from the folder you start it in. ClawdBlock's `AGENTS.md` tells it to read
`skill/clawdblock/SKILL.md` before doing anything in the world, and to open the matching page in
`skill/clawdblock/reference/` before each kind of task. It also describes the repository layout and says never to
start, stop or reset the server unless you ask. Codex opens these files itself with its file tools, so start it in
the ClawdBlock folder.

## Bot name: Codex

Each client gets its own name so that **two AIs never fight over one body**. The bot name is the AI's fake player,
its chat name and the owner of its builds. Undo only reverts the AI's own builds, and every other bot's finished
builds are protected zones. Codex can share a server with Claude and Gemini; their commands take turns through one
lock. To choose another name, edit `MC_BOT_NAME` in `config.toml` and restart Codex.

## Manual setup

1. Find the paths: `which node` (Windows: `where node`) and the full path of your ClawdBlock folder.
2. Open (or create) `~/.codex/config.toml` and paste the table above with your paths. On Windows, TOML strings
   in double quotes need doubled backslashes: `"C:\\Users\\you\\clawdblock\\mcp-server\\index.js"`.
3. Start `codex` in the ClawdBlock folder.

---

## First-session checklist

1. The Minecraft server is running (`python3 clawdblock.py status`), and you are in the game.
2. `cd` into the ClawdBlock folder and run `codex`.
3. Type `/mcp`: the `clawdblock` server and its `minecraft_*` tools should be listed.
4. Ask: *"Read the skill, check the Minecraft server and spawn in next to me."*
5. Check that it called `minecraft_status` first and that a player called Codex appeared next to you.
6. Ask for a first build: *"Build me a cottage facing the road, just east of me."*

## Tips

- **Approvals.** Codex asks before tool calls and file writes, depending on its approval mode. When it writes a
  generator it only needs write access to `jobs/` inside the ClawdBlock folder.
- **Ask it to read first.** Codex follows `AGENTS.md`, but a request that names the page helps: *"read
  reference/landscaping.md, then build a garden around my house"*.
- **Preview before building.** *"Generate it, show me a preview, then build."* `minecraft_preview` renders the
  plan without placing a block.
- **Codex sees pictures** returned by the screenshot and preview tools. Ask it to look at its build from two
  sides before calling it done.

## Common problems

| Symptom | Fix |
|---|---|
| No clawdblock server | a TOML syntax error in `config.toml`, or Codex was already running during `connect`. Restart Codex |
| Tool calls time out | raise `tool_timeout_sec`; long waits are normal for chat and job tools |
| Codex skips the build rules | it wasn't started in the ClawdBlock folder (no `AGENTS.md`), or ask it to read `SKILL.md` |
| Tools answer `ECONNREFUSED` | the Minecraft server is off: `python3 clawdblock.py start` |

More in [troubleshooting.md](../troubleshooting.md).

## See also

[Claude Code](claude-code.md) · [Claude Desktop](claude-desktop.md) · [Gemini CLI](gemini-cli.md) · [Local models](local-models.md)
· [Getting started](../getting-started.md)
