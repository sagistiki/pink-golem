# Gemini CLI

This page connects Google's **Gemini CLI** to your Pink Golem server. Gemini CLI works in a terminal like Claude
Code: it can read the skill's reference pages, write its own build generators into `jobs/`, and use all 37 tools.
Its body in the game is called **Gemini**, so it can build alongside Claude.

| | |
|---|---|
| Connect | `python3 pinkgolem.py connect gemini` |
| MCP config | `~/.gemini/settings.json` (Windows: `%USERPROFILE%\.gemini\settings.json`) |
| Skill | `GEMINI.md` in the Pink Golem folder, loaded automatically |
| Bot name | **Gemini** |
| Start it | `gemini`, run inside the Pink Golem folder |

---

## Connect

Setup offers this when it finds the `gemini` command or a `~/.gemini` folder. To do it later, or again:

```bash
python3 pinkgolem.py connect gemini
```

## What it writes

The entry is merged into `~/.gemini/settings.json`. Your other settings and servers stay as they are, and a
`settings.json.bak` copy is saved first:

```json
{
  "mcpServers": {
    "pinkgolem": {
      "command": "/usr/local/bin/node",
      "args": ["/home/you/pinkgolem/mcp-server/index.js"],
      "env": { "MC_BOT_NAME": "Gemini" },
      "cwd": "/home/you/pinkgolem"
    }
  }
}
```

`command` and `args` are absolute paths. `cwd` starts the server in the Pink Golem folder. `MC_BOT_NAME` gives
Gemini its own body.

This is a **user-level** setting, so the tools show up in every folder. The skill, though, only loads inside the
Pink Golem folder (next section), so always start `gemini` there.

## How the skill loads

Gemini CLI reads `GEMINI.md` from the folder you start it in. Pink Golem's `GEMINI.md` tells Gemini to follow the
skill and **imports `skill/pinkgolem/SKILL.md` in full** (the `@./skill/pinkgolem/SKILL.md` line). The rules, the
build recipe and the tool table are therefore in context from the first message. Gemini opens the deeper reference
pages in `skill/pinkgolem/reference/` with its file tools when a task needs them.

## Bot name: Gemini

Every client gets its own name so that **two AIs never fight over one body**. The bot name is:

- the fake player the AI walks and builds with,
- the name on its chat lines,
- the owner of its builds. Undo only touches the AI's own builds, and the builds of other bots count as
  protected zones.

So Claude and Gemini can work on the same server at the same time, each with its own body and undo stack. Their
commands take turns over one connection lock, so the server never mixes up their answers. To pick another name,
change `MC_BOT_NAME` in the entry above and restart Gemini CLI.

## Manual setup

1. Find the paths: `which node` (Windows: `where node`) and the full path of your Pink Golem folder.
2. Open `~/.gemini/settings.json` (create it with `{}` if it doesn't exist) and add the `pinkgolem` entry
   inside `"mcpServers"` as shown above. On Windows, write backslashes twice in JSON.
3. Start `gemini` in the Pink Golem folder.

---

## First-session checklist

1. The Minecraft server is running (`python3 pinkgolem.py status`), and you are in the game.
2. `cd` into the Pink Golem folder, run `gemini`.
3. Type `/mcp`: `pinkgolem` should be listed as connected, with its `minecraft_*` tools.
4. Optional: `/memory show` shows the loaded context. `GEMINI.md` and the skill should be in it.
5. Ask: *"Check the Minecraft server and spawn in next to me."* Gemini should call `minecraft_status` first, then
   spawn a body called Gemini beside you.
6. Ask for a first build: *"Build me a round lookout tower 20 blocks east of me."*

## Tips

- **Confirmations.** Gemini CLI asks before running each tool. Once you trust the setup, you can add
  `"trust": true` to the `pinkgolem` entry to skip those prompts for this server only.
- **Custom buildings.** Gemini can write generators (`jobs/gen_<name>.py`) with the `mclib` and `parts` libraries
  and run them with `minecraft_generate`. Ask it to preview first: *"write a generator for a bakery, show me a
  preview picture before you build"*.
- **Big jobs.** Builds run in the background with a boss bar. Gemini polls them with `minecraft_jobs action:wait`,
  up to 50 seconds per call.
- **Working next to Claude.** Give each AI its own area, or tell one of them to help with the other's build. A
  build by another bot is protected until its owner asks, or until the AI uses `minecraft_zones action:claim`.

## Common problems

| Symptom | Fix |
|---|---|
| `/mcp` shows no pinkgolem | the settings file has a JSON error (Gemini then ignores it), or Gemini was started before `connect`. Restart it |
| pinkgolem shows *disconnected* | `python3 pinkgolem.py doctor`: usually `npm install` in `mcp-server/` is missing |
| Gemini ignores the build rules | you started `gemini` outside the Pink Golem folder, so `GEMINI.md` wasn't loaded |
| Tools answer `ECONNREFUSED` | the Minecraft server is off: `python3 pinkgolem.py start` |

More in [troubleshooting.md](../troubleshooting.md).

## See also

[Claude Code](claude-code.md) · [Claude Desktop](claude-desktop.md) · [Codex](codex.md) · [Local models](local-models.md)
· [Getting started](../getting-started.md) · [Architecture](../architecture.md)
