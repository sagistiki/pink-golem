# Claude Code

This page connects **Claude Code** (Anthropic's terminal coding agent) to your Pink Golem server. Claude Code is
the most capable client for Pink Golem: besides using the 37 tools, it can write its own build generators into
`jobs/`, read the reference pages as it needs them, and even improve the tools themselves.

| | |
|---|---|
| Connect | `python3 pinkgolem.py connect claude-code` |
| MCP config | `.mcp.json` in the Pink Golem folder (project scope) |
| Skill | `.claude/skills/pinkgolem` → a link to `skill/pinkgolem/` |
| Bot name | the one in `pinkgolem.json` (default **Claude**) |
| Start it | `claude`, run inside the Pink Golem folder |

---

## Connect

Setup offers this automatically when it finds the `claude` command. To do it later, or again:

```bash
python3 pinkgolem.py connect claude-code
```

It then asks whether to also make Pink Golem available **in every folder** (user scope). The default is no, which
keeps Pink Golem tied to this folder. That is usually what you want.

## What it writes

**1. `.mcp.json` in the Pink Golem folder.** It merges this entry into the file (other servers already in it
stay as they are, and a `.mcp.json.bak` copy is saved first):

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

Both paths are **absolute**: the full path of your `node` and of the MCP server. Absolute paths work no matter
which folder the client starts in.

**2. The skill link.** `.claude/skills/pinkgolem` becomes a symbolic link to `skill/pinkgolem/`, so the skill
always matches the code. On Windows without Developer Mode, links are not allowed and the folder is **copied**
instead. Run `connect claude-code` again after every update to refresh the copy.

**3. User scope (only if you said yes):** a second link at `~/.claude/skills/pinkgolem`, and

```bash
claude mcp add pinkgolem --scope user -- <node path> <Pink Golem folder>/mcp-server/index.js
```

## How the skill loads

Claude Code finds skills in `.claude/skills/` and loads `pinkgolem` whenever `minecraft_*` tools are available or
you ask for something in Minecraft. `CLAUDE.md` in the folder is read at the start of every session and points to
the same skill, so Claude follows `SKILL.md` from the first message.

## Bot name

Claude Code uses the `bot_name` from `pinkgolem.json` (**Golem**, shown as **Pink Golem**, unless you chose another name at setup).
Claude Desktop uses the same name by default. If you run both at the same time, give one of them its own name
(see below). Otherwise two AIs drive one body and undo each other's walking.

Why names matter: the bot name is the AI's body (a Carpet fake player), its chat name, and the owner of its builds.
Undo and protected zones are per owner, so with separate names each AI undoes only its own work and never builds
over the other's.

To use another name for Claude Code only, add an `env` block to its entry in `.mcp.json`:

```json
"pinkgolem": { "command": "…", "args": ["…"], "env": { "MC_BOT_NAME": "Golem" } }
```

## Manual setup

If `connect` failed or you want to do it by hand, run these in the Pink Golem folder:

```bash
claude mcp add pinkgolem --scope project -- "$(command -v node)" "$PWD/mcp-server/index.js"
mkdir -p .claude/skills && ln -s ../../skill/pinkgolem .claude/skills/pinkgolem
```

On Windows (PowerShell), write `.mcp.json` yourself with the shape above (use `where node` for the node path and
double backslashes in JSON, e.g. `"C:\\Program Files\\nodejs\\node.exe"`), and copy `skill\pinkgolem` to
`.claude\skills\pinkgolem`.

---

## First-session checklist

1. The Minecraft server is running: `python3 pinkgolem.py status`.
2. You are in the game (the AI spawns next to a player).
3. Run `claude` **inside the Pink Golem folder**. The first time, Claude Code asks whether to trust the project's
   MCP server `pinkgolem`. Approve it.
4. Type `/mcp`: `pinkgolem` should be *connected*. 37 tools with every recommended mod; fewer if WorldEdit is not
   installed (its tool is hidden) or Carpet is missing (the bot and helper tools are hidden).
5. Ask: *"Check the server and spawn in next to me."* Claude should call `minecraft_status`, read its notes and the
   world map, then spawn its body beside you.
6. Ask for a first build: *"Build me a cottage next to me."*

## Tips

- **Tool permissions.** Claude Code asks before each new tool. To allow every Pink Golem tool at once, add
  `"mcp__pinkgolem"` to `permissions.allow` in `.claude/settings.json` (or pick "don't ask again" when prompted).
- **Let it write generators.** For anything custom ("a bakery with a shop window and an apartment upstairs"), Claude
  writes `jobs/gen_bakery.py` with `mclib` and `parts`, previews it, then builds it. You can read and keep that file.
  Good ones can become blueprints ([writing-blueprints.md](../writing-blueprints.md)).
- **Long builds run in the background.** Claude keeps talking while a job runs; ask it for progress, or watch the
  boss bar in game.
- **Improving the tools.** Edits to `mcp-server/lib/*.js` and `mcp-server/tools/*.js` take effect on the next tool
  call. There is no restart. Changes to `mcp-server/index.js` need `/mcp` → reconnect, or a new `claude` session.
  See [contributing.md](../contributing.md).
- **Server control.** `CLAUDE.md` tells Claude never to start, stop or reset the server unless you ask. Ask plainly
  ("start the server") when you want it to.
- **Context.** A long build session fills the context. Start a fresh session between big projects. The AI's
  journal (`data/LEARNINGS.md`) and world map carry over.

## Common problems

| Symptom | Fix |
|---|---|
| No `minecraft_*` tools | You started `claude` in another folder, or declined the project server. Run it in the Pink Golem folder; `/mcp` shows the state |
| `/mcp` shows *failed* | `python3 pinkgolem.py doctor`; usually `npm install` did not run in `mcp-server/` |
| Tools answer `ECONNREFUSED` | the Minecraft server is not running: `python3 pinkgolem.py start` |
| The skill seems unknown | check that `.claude/skills/pinkgolem/SKILL.md` exists; run `connect claude-code` again |

More in [troubleshooting.md](../troubleshooting.md).

## See also

[Claude Desktop](claude-desktop.md) · [Gemini CLI](gemini-cli.md) · [Codex](codex.md) · [Local models](local-models.md)
· [Getting started](../getting-started.md) · [Architecture](../architecture.md)
