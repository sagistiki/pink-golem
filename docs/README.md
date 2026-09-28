# Pink Golem documentation

These pages are for **people**: players setting up a server for the first time, parents and teachers running one
for kids, and developers who want to extend it. The AI has its own documentation, the skill in
[`skill/pinkgolem/`](../skill/pinkgolem/SKILL.md), written for models to act on.

New here? Read **[Getting started](getting-started.md)**, then the page for your AI client.

---

## Set up and play

| Page | Read it when |
|---|---|
| [Getting started](getting-started.md) | you're installing Pink Golem: prerequisites, the installer, first start, joining, first prompts, updating, uninstalling |
| [Playing with friends](exposing-to-friends.md) | others should join: LAN, port forwarding, tunnel services, whitelist, security |
| [Troubleshooting](troubleshooting.md) | something doesn't work: Java, ports, RCON, Carpet, the MCP not showing up, lag, logs, backups, a fresh world |
| [Upgrading](upgrading.md) | a new Minecraft version is out, or you want newer mods |

## Connect your AI

Each page shows what `python3 pinkgolem.py connect <client>` writes, how the skill loads, the bot's in-game
name, manual setup, and a first-session checklist.

| Client | Bot name | Page |
|---|---|---|
| Claude Code | Claude (from `pinkgolem.json`) | [clients/claude-code.md](clients/claude-code.md) |
| Claude Desktop | Claude (from `pinkgolem.json`) | [clients/claude-desktop.md](clients/claude-desktop.md) |
| Gemini CLI | Gemini | [clients/gemini-cli.md](clients/gemini-cli.md) |
| Codex CLI | Codex | [clients/codex.md](clients/codex.md) |
| LM Studio, local models, any other MCP client | Buddy | [clients/local-models.md](clients/local-models.md) |

Every AI gets its own name, and with it its own body, undo stack and protected builds. Several AIs can then work
on one server without fighting over one body.

## See what it can do

| Page | Read it when |
|---|---|
| [Features, layout and mods](features.md) | you want the full list of what Pink Golem does, what's in each folder and which mods it uses |
| [Case study: a roller coaster that really runs](case-study-roller-coaster.md) | you want to see a big project end to end: design, physics, a display-entity track, a custom train, the camera, testing on a live server |
| [Case study: a tower of floors people actually use](case-study-tower.md) | you want to see how a hotel, registration, an arcade, a club, a museum and a roof bar were built floor by floor with a live owner, and what each correction taught |
| [Case study: a character studio: real clothes and a wall where you paint your own skin](case-study-character-studio.md) | you want to see how clothes come from equipment assets, how a text-display pixel canvas, a paint toolbar and one ray per click make an in-game paint program, and how a painting becomes a signed player skin |
| [Case study: a cinema and an art gallery, with no client mods](case-study-cinema.md) | you want to see how a screen (item-model frames vs. map art vs. a block wall), an original synthesised score, and RTL-safe text all come together, plus the bugs found building it |

## Build and extend

| Page | Read it when |
|---|---|
| [How it works](architecture.md) | you want the big picture: MCP ⇄ RCON ⇄ Minecraft + Carpet, the safety rails, hot reload, data files, limits |
| [Writing blueprints](writing-blueprints.md) | you want a new kind of building that anyone (and any model) can build with one call: a full tutorial with a working example |
| [Contributing](contributing.md) | you want to add a tool, a lib helper, a blueprint, a scarpet app, a reference page or a lesson, and send a pull request |

## Quick reference

```bash
python3 pinkgolem.py setup                 # install or repair (keeps your world)
python3 pinkgolem.py start [--background]  # start the server
python3 pinkgolem.py stop | status | doctor
python3 pinkgolem.py mods [list|add|remove|update] [names…]
python3 pinkgolem.py apps [list|add|remove] [names…]
python3 pinkgolem.py connect [claude-code|claude-desktop|gemini|codex|lmstudio|all|print]
python3 pinkgolem.py backup | new-world
```

On Windows, type `py` instead of `python3`, or use the `pinkgolem.cmd` shortcut in the Pink Golem folder
(`pinkgolem start` in Command Prompt, `.\pinkgolem start` in PowerShell).

Pink Golem is open source under the MIT license: https://github.com/sagistiki/pink-golem
