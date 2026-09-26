# Troubleshooting

When something doesn't work, start here. Each section begins with the message you're likely to see, then gives
the cause and the fix. If you only remember one thing, remember this command:

```bash
python3 pinkgolem.py doctor
```

It checks everything below in a few seconds and tells you what to run to fix each problem.

---

## What `doctor` checks

| Check | If it fails |
|---|---|
| Java 25+, Node 20+ | install or update them (commands in [getting-started.md](getting-started.md#1-prerequisites)) |
| `pinkgolem.json` exists | run `python3 pinkgolem.py setup` |
| server launcher in `server/`, EULA accepted, RCON enabled with a password | run setup again. It keeps your world |
| mods `fabric-api` and `carpet` present | `python3 pinkgolem.py mods add carpet` |
| scarpet apps `cu`, `helpers`, `bubble` present | `python3 pinkgolem.py apps add cu helpers bubble` |
| MCP dependencies installed | `cd mcp-server && npm install` |
| server running; scarpet answers; `cu` loaded | start the server; in its console `script load cu` |
| MCP tools load | shows the error from the tool code (after an edit, see [contributing.md](contributing.md)) |
| AI clients found | `python3 pinkgolem.py connect` |

---

## Installing and starting

### Java is missing or the wrong version

*Seen as:* `Java 25+ is needed (found: 21)` during setup, or the server stops at once with
`UnsupportedClassVersionError … class file version 69.0` (69 = Java 25).

Minecraft 26.x needs **Java 25**. Install it (macOS `brew install --cask temurin@25`, Windows
`winget install EclipseAdoptium.Temurin.25.JDK`, or https://adoptium.net/temurin/releases/?version=25), then open a
new terminal.

If you have several Java versions, Pink Golem uses **`JAVA_HOME`** first, then the `java` on your `PATH`. Point it
at Java 25:

- macOS: `export JAVA_HOME=$(/usr/libexec/java_home -v 25)` (add it to `~/.zshrc` to keep it)
- Windows: *System → Advanced system settings → Environment Variables*, set `JAVA_HOME` to the Java 25 folder
  (e.g. `C:\Program Files\Eclipse Adoptium\jdk-25…`), or uninstall the old Java
- Linux: `sudo update-alternatives --config java`

### Downloads fail (SSL / certificate errors)

*Seen as:* `download failed: https://… (… CERTIFICATE_VERIFY_FAILED …)`.

Setup downloads with Python first. When that fails, it retries with `curl`, and on Windows with PowerShell. If
you still see the error:

- **macOS with Python from python.org:** run *Install Certificates.command* in `/Applications/Python 3.x/`, then
  run setup again.
- Or `python3 -m pip install certifi`; setup uses it automatically when it's there.
- Behind a company proxy or firewall: set `HTTPS_PROXY`, or try another network.

### "Fabric has no loader" / "no build for Minecraft X on Modrinth yet"

The Minecraft version you asked for is too new (or mistyped). Fabric and the mods need time to catch up after a
release. Use the tested version (`setup` without `--mc-version`), or see [upgrading.md](upgrading.md).

### The port is in use

*Seen as:* `port 25565 is in use (another server?)` during setup, or `FAILED TO BIND TO PORT` /
`Address already in use` in the server log.

1. Is it your own server, already running in the background? `python3 pinkgolem.py status`, then `stop`.
2. Another Minecraft server or app on that port: stop it, or give Pink Golem another port. For a new install use
   `setup --port 25570`. For an existing one, stop the server, change `server-port=` in `server/server.properties`,
   and start again. Friends then connect to `localhost:25570`.
3. The same applies to `rcon.port` (25575). Setup picks a free RCON port for new installs.

### The EULA is not accepted

*Seen as:* `The Minecraft EULA is not accepted`. Read https://aka.ms/MinecraftEULA, then open
`server/eula.txt` and change the line to `eula=true` (or run `setup --accept-eula`).

### The server stops right after starting

Look at the last lines of the log (see [Reading the logs](#reading-the-logs)). Common causes:

| Log says | Fix |
|---|---|
| `OutOfMemoryError` | give it more RAM: `setup --memory 6144`, or set `"memory_mb"` in `pinkgolem.json` |
| a mod "requires" another mod, or a version mismatch | `python3 pinkgolem.py mods update`; remove the mod named in the message with `mods remove <name>` (or delete its jar from `server/mods/`) |
| `Failed to bind to port` | see [The port is in use](#the-port-is-in-use) |
| `Session lock` / `session.lock` | another server process still has the world open: stop it, or restart the computer |

---

## The AI can't reach the server

| Message from a tool | Meaning | Fix |
|---|---|---|
| `ECONNREFUSED … nothing is listening on 127.0.0.1:25575` | the Minecraft server isn't running, or is still starting | `python3 pinkgolem.py start`, wait for `Done`, ask again |
| `… and is enable-rcon=true in server.properties (it is false now)` | RCON is switched off | run `setup` again, or set `enable-rcon=true` and restart the server |
| `RCON login failed: wrong rcon.password` | the password changed while the server was running (the server reads it only at start), or `MC_RCON_PASSWORD` is set to an old value | restart the server; remove the stale variable |
| `RCON password is empty` | `server.properties` has no `rcon.password` | run `setup` again |
| `RCON connection closed (server stopped or restarted?)` | the server went down during a command | start it; the next call reconnects |
| `Command too long for RCON (… bytes, max 1400)` | one command was too long | the AI should split it; generators do this for you |

---

## Carpet and scarpet

*Seen as:* `minecraft_status` shows `PROBLEM: Carpet is not installed`, or the bot tools are missing.

Carpet gives the AI its body, scarpet, undo snapshots, vision and most checks. Install it and restart:

```bash
python3 pinkgolem.py mods add carpet
python3 pinkgolem.py stop && python3 pinkgolem.py start
```

If Carpet is installed but `doctor` says **"cu app not loaded"**, type `script load cu` in the server console (or
`python3 pinkgolem.py apps add cu` while the server runs). If it fails to load, the reason is in the server log:
search it for `scarpet` (the AI can use `minecraft_server_log filter:"scarpet"`).

---

## The AI client doesn't show the tools

1. **Restart the client completely.** Desktop apps must be *quit* (menu bar or system tray → Quit), not just closed.
   Terminal clients (Claude Code, Gemini CLI, Codex) need a new session.
2. **Start terminal clients in the Pink Golem folder.** Claude Code's `.mcp.json`, `GEMINI.md` and `AGENTS.md` are
   found only there.
3. **Check the config file** listed on your client's page in [clients/](clients/claude-code.md). A single JSON or
   TOML typo makes some clients ignore the whole file. If `connect` said `… is not valid JSON — leaving it alone`,
   fix that file first, then run `connect` again.
4. **Node not found by a GUI app.** Desktop apps don't see your terminal's `PATH`. Setup writes the **absolute path**
   of `node` for this reason. If you installed or moved Node afterwards (a new version, or nvm switching versions),
   run `python3 pinkgolem.py connect <client>` again to write the new path.
5. **Test the MCP server by hand:**

   ```bash
   node mcp-server/index.js
   ```

   It should print `[pinkgolem] tools loaded (29)` and `[pinkgolem] running…`, then wait silently. That's
   correct, because it waits for a client. Press Ctrl+C. An error here (for example `Cannot find package
   '@modelcontextprotocol/sdk'`) means `cd mcp-server && npm install`.
6. **Client logs.** Claude Code: `/mcp`. Claude Desktop: *Settings → Developer*, and its log folder (macOS
   `~/Library/Logs/Claude/`, Windows `%APPDATA%\Claude\logs\`). Gemini CLI and Codex: `/mcp`.

### Windows: "skill copied" instead of linked

Creating symbolic links on Windows needs **Developer Mode** (*Settings → For developers*) or an administrator
terminal. Without them, `connect claude-code` copies the skill folder instead. That works fine, but the copy
doesn't follow updates: run `connect claude-code` again after each `git pull`. Or switch on Developer Mode and
connect once more to get a link.

---

## Things the AI reports

| The AI says | Meaning |
|---|---|
| `PROTECTED — nothing was changed` | the build touches someone's protected zone. It will ask the owner, or you can say it may (`allow_protected`) |
| `STOPPED — nothing was built. N existing block(s) are in the way` | the overwrite guard found built blocks in the target area. Move the build, or confirm the change is wanted |
| `verify … grass_block>dirt` | harmless: grass under a placed block turns to dirt |
| `Could not set the block` / `No blocks were filled` | harmless: the block was already like that (`unchanged`) |
| `Failed to place feature` | a tree didn't fit at that spot; nothing is broken |
| `no undo snapshot (box is … blocks, max 4000000)` | the build was too big to snapshot. Make a backup before builds that size |

**The bot doesn't appear:** Carpet missing, or the server is full. Fake players count toward `max-players`
(20). If the whitelist is on, see [exposing-to-friends.md](exposing-to-friends.md#4-whitelist-only-invited-players).

**The AI doesn't see chat:** it reads `server/logs/latest.log`. If the MCP server runs on another machine, or
`MC_SERVER_DIR` points elsewhere, it can't. Some chat mods change the log format; join and leave detection still
works.

---

## Lag

1. **Measure it.** `python3 pinkgolem.py status` shows recent tick times in ms (below 50 is healthy). Ask the AI
   *"why is the server laggy?"*: `minecraft_watchdog action:heavy` names the culprit (entity piles, leaks, hot
   chunks, busy threads) — see [the watchdog guide](../skill/pinkgolem/reference/watchdog.md). With spark:
   `/spark tps` in game, and `/spark profiler` to find the cause.
2. **Big builds** are the usual cause. They run as background jobs; the AI can slow a job down with `pace_ms`.
   Clutter slows things too: ask the AI to clean up dropped items and stray entities (`minecraft_cleanup`).
3. **More RAM:** `"memory_mb": 6144` in `pinkgolem.json` (the default is half your RAM, 2-8 GB). Restart.
4. **Less to simulate:** lower `view-distance` (12) and `simulation-distance` (8) in `server.properties`.
5. **Mods that help:** Lithium (setup recommends it). Chunky pre-generates terrain so exploring doesn't lag:
   `/chunky radius 500`, then `/chunky start`.
6. **The computer sleeps.** On macOS a foreground `start` keeps the Mac awake; a `--background` start doesn't.
   Adjust your energy settings if the server stops responding when you walk away.

---

## Reading the logs

| File | What's in it |
|---|---|
| `server/logs/latest.log` | the current server log: startup, chat, errors, mod messages |
| `server/logs/*.log.gz` | older logs, one per start (gzip) |
| `server/logs/console.log` | everything a `--background` server printed, including crashes before logging starts |
| `server/crash-reports/` | full crash reports, if the server crashed |
| your AI client's MCP log | the MCP server's own messages (`[pinkgolem] …`), see *Client logs* above |

Search for `ERROR`, `Exception` or the mod's name. The AI can read the log too: *"check the server log for
errors"* (`minecraft_server_log`).

---

## Backups and a fresh world

**Back up** (works while the server runs; the world is flushed to disk first):

```bash
python3 pinkgolem.py backup             # → backups/world-YYYYMMDD-HHMMSS.zip, keeps the newest 3
python3 pinkgolem.py backup --dry-run   # sizes, free space, what rotation would remove
python3 pinkgolem.py backup --keep 7 --dest /Volumes/USB/mc-backups
```

Saving is paused only while the world is copied and always switched back on. The backup refuses to run when the
destination has less than 3× the world's size free, so the running server can always save. The Ledger database is
left out unless you add `--include-ledger`. Also copy `data/` if you want the AI's map, zones and journal to match
that backup.

**Restore** a backup: `python3 pinkgolem.py stop`, move `server/world` away, unzip the backup inside `server/` (the
zip contains the `world/` folder), start again.

**Start over with a new world:**

```bash
python3 pinkgolem.py stop
python3 pinkgolem.py new-world     # moves the old world to backups/ (not deleted), reinstalls the apps
python3 pinkgolem.py start
```

The world map, zones and undo stack are cleared because they describe the old world. People and the journal stay.
To change the world type, edit `level-type` in `server/server.properties` before starting
(`minecraft:flat` or `minecraft:normal`), and set `level-seed` if you want a particular seed.

## See also

- [Getting started](getting-started.md) · [Upgrading](upgrading.md) · [Architecture](architecture.md)
- For the AI's own troubleshooting while building: [the skill](../skill/pinkgolem/SKILL.md)
