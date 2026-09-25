# Getting started

This page takes you from nothing to an AI building next to you in your own Minecraft world. Read it once from
top to bottom the first time. It takes about 15 minutes, and most of that is downloads. You don't need to know how
to program: you copy a few commands into a terminal and answer a few questions.

**What you end up with:** a Minecraft Java 26.2 server on your computer (Fabric, with the Carpet mod), an MCP
server that gives an AI 33 `minecraft_*` tools, and a building skill that teaches the AI how to use them well.

---

## 1. Prerequisites

You need three programs. The installer checks for all three and tells you what is missing, so you can also
start at step 2 and come back here if it complains.

| Program | Version | Why |
|---|---|---|
| Java | **25** or newer | Minecraft 26.x servers need Java 25 |
| Node.js | **20** or newer | runs the MCP server, which connects your AI to the game |
| Python | **3.9** or newer | runs the installer and the build generators (standard library only, nothing to `pip install`) |

You also need the **Minecraft: Java Edition** game, version **26.2**, to join the server yourself.

### macOS (Homebrew)

```bash
brew install --cask temurin@25
brew install node
brew install python        # macOS ships an older python3; this gets a current one
```

No Homebrew? Get it from https://brew.sh, or use the installers linked below.

### Windows (winget, in PowerShell or Command Prompt)

```bat
winget install EclipseAdoptium.Temurin.25.JDK
winget install OpenJS.NodeJS.LTS
winget install Python.Python.3.12
```

Close the terminal and open a new one afterwards: a terminal that was already open does not see newly installed
programs. If you use the python.org installer instead, tick **"Add python.exe to PATH"**.

### Linux (Debian / Ubuntu)

```bash
sudo apt install openjdk-25-jre-headless python3 nodejs npm
```

Older distributions may not have Java 25 in their package lists, and they often ship a Node.js older than 20.
Check with `node --version`. If it's too old, install Node from https://nodejs.org or with nvm instead.

### Official downloads (any system)

- Java 25 (Eclipse Temurin): https://adoptium.net/temurin/releases/?version=25
- Node.js LTS: https://nodejs.org
- Python: https://www.python.org/downloads/

### Check what you have

```bash
java -version       # should say "25" (or higher)
node --version      # v20 or higher
python3 --version   # 3.9 or higher (Windows: py --version)
```

---

## 2. Get ClawdBlock

With git:

```bash
git clone https://github.com/sagistiki/clawdblock.git
cd clawdblock
```

Without git: on the GitHub page choose **Code → Download ZIP**, unzip it somewhere you'll find again (for example
your Documents folder), and open a terminal in that folder.

> **Windows users:** throughout these docs, type `py` wherever you see `python3`. The `clawdblock.cmd` shortcut
> works too: in the ClawdBlock folder, `clawdblock start` (Command Prompt) or `.\clawdblock start` (PowerShell) is
> the same as `py clawdblock.py start`.

---

## 3. Install (three ways, same result)

All three ways run the same `setup` command. The first two only add a friendly check for missing programs first.

| You are on | Run | Notes |
|---|---|---|
| macOS / Linux | `./install.sh` | checks Python, Java, Node, then runs setup |
| Windows | double-click `install.cmd` | opens PowerShell and runs `install.ps1`. From a terminal: `powershell -ExecutionPolicy Bypass -File install.ps1` |
| anything | `python3 clawdblock.py setup` | the setup itself, without the checks |

Setup asks a few questions. Pressing Enter accepts the suggested answer (shown in `[brackets]`).

### What each setup step does

| Step | What happens |
|---|---|
| **1/7 Checking your computer** | Finds Java, Node and Python and counts your RAM. If Java is missing it tells you how to install it and asks whether to continue |
| **2/7 Server settings** | Asks for the server folder (`server`), the world type, the game port (`25565`) and your AI's in-game name (`Claude`). The RCON port (`25575`) moves to the next free port if that one is taken |
| **3/7 Minecraft server** | Downloads the Fabric server launcher for your Minecraft version, asks you to accept the Minecraft EULA, and writes `server.properties`: RCON on with a random 20-character password; for a new world also creative mode, peaceful, flight allowed, `online-mode=true` |
| **4/7 Mods** | Downloads mods from Modrinth. Fabric API and Carpet are required. It asks about the recommended ones (Lithium, WorldEdit, BlueMap, Essential Commands, spark), and in interactive mode also the optional ones |
| **5/7 Game-logic apps** | Copies the three scarpet apps the AI needs (`cu`, `helpers`, `bubble`) into the world's `scripts/` folder |
| **6/7 MCP server** | Runs `npm install` in `mcp-server/` and saves your answers in `clawdblock.json` |
| **7/7 Connect your AI** | Finds AI apps on this computer (Claude Code, Claude Desktop, Gemini CLI, Codex, LM Studio) and offers to connect each one. See [clients/](clients/claude-code.md) |

**World type:** *flat* (recommended) is an endless creative plain. The ground is at y = -61 and players stand at
y = -60, so the AI never has to guess where the ground is. *Normal* gives you hills, trees and caves; the AI reads
the ground height wherever it builds.

**Running setup again is safe.** It keeps your world, your RCON password and your port, updates the Fabric launcher
and mods when newer builds exist, and re-copies the core apps.

### Non-interactive install

For scripts, remote machines, or when you just want the defaults:

```bash
python3 clawdblock.py setup --yes --accept-eula
```

| Flag | Meaning |
|---|---|
| `--yes`, `-y` | accept every recommended answer: flat world, port 25565, recommended mods yes, optional mods no, connect every AI client found. If Java is missing, setup stops instead of continuing |
| `--accept-eula` | you accept the Minecraft EULA (https://aka.ms/MinecraftEULA). Read it first |
| `--port N` | game port (default 25565) |
| `--rcon-port N` | RCON port (default 25575, or the next free one) |
| `--memory MB` | server RAM in MB (default: half your computer's RAM, at least 2048 and at most 8192) |
| `--world flat\|normal` | world type for a new server (ignored when a world already exists) |
| `--bot-name NAME` | the AI's in-game name (default `Claude`) |
| `--no-connect` | don't touch any AI client now; do it later with `python3 clawdblock.py connect` |
| `--mc-version X` | Minecraft version (default 26.2, the tested one). See [upgrading.md](upgrading.md) |

Example: a normal-terrain world on port 25570 with 6 GB of RAM and no client changes:

```bash
python3 clawdblock.py setup --yes --accept-eula --world normal --port 25570 --memory 6144 --no-connect
```

---

## 4. Start the server

```bash
python3 clawdblock.py start
```

The first start creates the world and takes about a minute. It is ready when the console prints a line with
`Done (…)`. This terminal is now the **server console**: you can type server commands into it (`list`, `op <name>`,
`say hi`). Type `stop` to shut the server down cleanly. On macOS the computer stays awake while the server runs.

To run it without keeping a terminal open:

```bash
python3 clawdblock.py start --background    # or -b; waits up to 180 s for "Done" (change with --wait N)
python3 clawdblock.py status                # running? who is online? which mods?
python3 clawdblock.py stop                  # saves the world, then stops
```

In the background, console output goes to `server/logs/console.log`. There is no console to type into, so use the
AI or a foreground start for console commands.

---

## 5. Join the game

1. Open the Minecraft Launcher and play **Java Edition 26.2** (under *Installations* you can create an
   installation pinned to 26.2 if the newest release is different).
2. **Multiplayer → Add Server.** Server address: `localhost` (or `localhost:25570` if you chose another port).
3. Join. You arrive in creative mode.

You don't need any client mods. Everything ClawdBlock adds works on the server side.

### Make yourself an operator

Operators can use commands like `/gamemode`, `/tp` and WorldEdit. In the server console (a foreground start):

```
op YourMinecraftName
```

If the server runs in the background, ask your AI instead: *"Make me an operator, my name is YourMinecraftName"*.
It runs `op` through its console connection.

---

## 6. Talk to your AI

Open your AI client in the ClawdBlock folder (or restart the desktop app you connected) and ask it to build. The
per-client pages explain the details: [Claude Code](clients/claude-code.md) · [Claude Desktop](clients/claude-desktop.md)
· [Gemini CLI](clients/gemini-cli.md) · [Codex](clients/codex.md) · [local models](clients/local-models.md).

First prompts that work well (be in the game, standing where you want things):

| Try | What you'll see |
|---|---|
| *"Check the server and spawn in next to me."* | the AI's body appears beside you |
| *"Build me a cottage next to me."* | a site outline, a chat line with the plan, a progress bar, helper builders at work, then a furnished cottage with a garden |
| *"Look at the house I'm looking at and tell me what you think."* | it reads the structure as text and gives concrete suggestions |
| *"Build a round lookout tower 30 blocks north of me."* | a stone tower with spiral stairs and a walkable roof |
| *"Build a small park with a fountain."* | paths, a pond, trees, benches and lamps |
| *"Undo that."* | the last build disappears (every build is snapshotted first) |
| *"Take a screenshot of what you built."* | a picture of the build, returned to the AI and saved in `data/screenshots/` |

Say what you want in plain words; the AI picks a blueprint or writes its own generator. When a request is vague, it
offers a few numbered options to choose from.

---

## 7. Where things live

| Path | What | Committed to git? |
|---|---|---|
| `clawdblock.py` | the command-line tool: setup, start, stop, status, doctor, mods, apps, connect, new-world, backup | yes |
| `clawdblock.json` | your settings: server folder, Minecraft version, memory, bot name, chat colour, helper names, installed mods | no |
| `server/` | the Minecraft server: launcher jar, `mods/`, `world/`, `logs/`, `server.properties`, `ops.json`, `whitelist.json` | no |
| `server/world/scripts/` | installed scarpet apps (`cu.sc`, …) and their `<app>.data/` folders | no |
| `data/` | what the AI remembers: `world_index.json` (map of builds), `zones.json` (protected builds), `undo.json`, `people.json`, `LEARNINGS.md` (shared journal), `screenshots/` | no |
| `jobs/` | generated build files (`*.json`) and generators the AI writes (`gen_*.py`) | no |
| `backups/` | world backups and archived worlds | no |
| `dist/` | the skill as a zip, for Claude Desktop | no |
| `mcp-server/` | the MCP server (Node) | yes |
| `skill/clawdblock/` | the building skill: `SKILL.md`, `SYSTEM_PROMPT.md`, `reference/`, `scripts/`, `blueprints/` | yes |
| `scarpet-apps/` | optional game-logic apps: fireworks, launch pads, races, secret doors, TNT Run, vendor stands, welcome | yes |

Everything the tools write stays inside this folder. Don't hand-edit files in `data/` while an AI session is running.

---

## 8. Everyday commands

```bash
python3 clawdblock.py status              # is it running, who is online
python3 clawdblock.py doctor              # find and explain problems (see troubleshooting.md)
python3 clawdblock.py mods list           # which mods are installed; mods add|remove|update <names>
python3 clawdblock.py apps list           # scarpet apps; apps add race vendor
python3 clawdblock.py backup              # zip the world into backups/
python3 clawdblock.py connect             # (re)connect AI clients
python3 clawdblock.py new-world           # archive this world; the next start makes a fresh one
```

On macOS and Linux, `./clawdblock <command>` is a shortcut for `python3 clawdblock.py <command>`.

---

## 9. Updating

```bash
python3 clawdblock.py stop
git pull                                   # or download the new ZIP and copy your server/, data/, jobs/, clawdblock.json over
python3 clawdblock.py setup                # keeps your world; updates dependencies and the core apps
python3 clawdblock.py start
```

Then restart your AI client so it loads the new MCP server. Claude Desktop users: upload the new
`dist/clawdblock-skill.zip` (see [clients/claude-desktop.md](clients/claude-desktop.md)). On Windows, where the
skill is copied rather than linked, run `connect` again.

---

## 10. Uninstall

1. `python3 clawdblock.py stop`, and `python3 clawdblock.py backup` if you want to keep the world. Copy
   `backups/` somewhere safe.
2. Remove the `clawdblock` entry from each AI client you connected (the file for each client is listed on its
   page under [clients/](clients/claude-code.md)). Setup saved a `.bak` copy next to each config file it changed.
   If you registered Claude Code in user scope: `claude mcp remove clawdblock --scope user` and delete
   `~/.claude/skills/clawdblock`.
3. Delete the ClawdBlock folder. Nothing was installed anywhere else, apart from Java, Node and Python, which
   you can keep or remove with the tool you installed them with.

---

## See also

- [Troubleshooting](troubleshooting.md): when something above didn't work
- [Playing with friends](exposing-to-friends.md): LAN, port forwarding, tunnels, whitelist
- [How it works](architecture.md): what happens between your prompt and the blocks
- [Writing blueprints](writing-blueprints.md): teach it a new kind of building
