# Upgrading Minecraft and mods

This page covers moving your server to a newer Minecraft version and keeping its mods up to date. ClawdBlock is
tested on **Minecraft 26.2**. Newer versions usually work, because the MCP server talks to Minecraft through server
commands and the log rather than the network protocol. The mods and a few block names are what can lag behind.

**Before any upgrade:** `python3 clawdblock.py backup`, and copy `data/` too. A world opened in a newer version
**cannot go back** to an older one.

---

## Updating mods (same Minecraft version)

```bash
python3 clawdblock.py stop
python3 clawdblock.py mods update
python3 clawdblock.py start
```

`mods update` asks Modrinth for the newest **release** build of every managed mod you have installed, for your
Minecraft version, and swaps the jar if it changed. Mods you dropped into `server/mods/` yourself are not touched;
update those by hand. `mods list` shows what's installed. Mods added or updated while the server runs take effect
after a restart.

Running `python3 clawdblock.py setup` again does the same for the mods it manages, and also updates the Fabric
launcher and the core scarpet apps.

---

## Moving to a newer Minecraft version

### 1. Check that everything you need exists for it

| Needed | Where to check | If it's missing |
|---|---|---|
| **Fabric loader** for the version | https://fabricmc.net/develop/ or just try setup; it says `Fabric has no loader for Minecraft X` | wait |
| **Fabric API** and **Carpet** (both required) | their Modrinth pages, *Versions* tab, filtered by game version and the Fabric loader | wait. Without Carpet the AI has no body, no scarpet, no undo and no checks |
| Your other mods (WorldEdit, BlueMap, Lithium…) | their Modrinth pages | decide: wait, or upgrade without them and remove them (below) |
| **Java** version | the Minecraft release notes | install the newer Java first. 26.x needs Java 25; a future version may need more |
| Your players' clients | the Minecraft Launcher | everyone must switch to the new version to join |

Carpet often ships its build for a new Minecraft version a little later than Fabric itself. Checking first saves
you a broken server.

### 2. Run setup with the new version

```bash
python3 clawdblock.py stop
python3 clawdblock.py backup
python3 clawdblock.py setup --mc-version 26.3
```

Setup downloads the Fabric launcher for that version, fetches every mod's build for it, re-copies the core apps
and saves the version in `clawdblock.json`. Your world, port and RCON password stay.

Watch the mod step. A line like

```
! worldedit: no build for Minecraft 26.3 on Modrinth yet — skipped
```

means the **old jar for the old version is still in `server/mods/`**, and an old mod can stop a new server from
starting. Remove it until a new build is out:

```bash
python3 clawdblock.py mods remove worldedit
```

Later, `python3 clawdblock.py mods add worldedit` brings it back. The `minecraft_worldedit` tool hides itself while
WorldEdit is missing, and the rest of ClawdBlock keeps working.

### 3. Start and check

```bash
python3 clawdblock.py start
python3 clawdblock.py doctor
```

`doctor` confirms that Carpet answers scarpet (`script run 1+1`) and that the `cu` app is loaded. Then, in the
game, run a real build.

---

## What to check after a version change

### Block and item renames

Mojang sometimes renames blocks. In 26.x, for example, `chain` became **`iron_chain`**. Old names in a generator
or blueprint then fail with `Unknown block` or `Invalid …` errors, and the job reports them in `failures`.

The fastest full test is the **catalog**: it places one of every component from `parts.py` on labelled tiles, so
it's a regression test for the whole library.

```
minecraft_generate script:"skill/clawdblock/blueprints/catalog.py" args:["--at","0,-61,40","--facing","south"] build:true
minecraft_jobs action:wait
```

Every job must finish with `errors: 0`. For each failing command, look up the new name (the release notes or the
Minecraft Wiki's version history), fix it in `parts.py`, `mclib.py` or the blueprint, and run the catalog again.
Build all the blueprints once too.

### Block states and command syntax

Less common, but it happens: a block gains or loses a state (`facing`, `half`, `type`…), or a command's syntax
changes. The job's `failures` show the exact command and the server's answer. Also check
`skill/clawdblock/reference/block-states.md` and fix any examples that changed.

### Scarpet changes

Carpet updates can change scarpet functions or event names. Signs:

- `doctor` says `cu app not loaded`, or `script load cu` prints an error;
- undo, vision or verification tools return scarpet errors;
- the helpers stop swinging, or speech bubbles stop appearing (`helpers.sc`, `bubble.sc`);
- a game app (race, vendor…) stops reacting.

Read the server log (`minecraft_server_log filter:"scarpet"`, or search `server/logs/latest.log`). Carpet's
changelog lists scarpet changes. Fix the app in `skill/clawdblock/scripts/` or `scarpet-apps/`, then
`python3 clawdblock.py apps add <name>` to copy and reload it.

### Server log format

The MCP server reads chat, joins and leaves from `latest.log`. If a new version changes those lines, the AI stops
hearing chat while everything else works. The patterns are at the top of the log-watcher section in
`mcp-server/index.js`.

### Superflat defaults

ClawdBlock assumes the default superflat ground at y = -61 on flat worlds (players stand at -60). `minecraft_status`
reports the ground level it detects. If it's different on the new version, the skill already tells the AI to read
the ground (`standingOn.y`) rather than assume it.

---

## Going back

A world that has been opened by a newer Minecraft version isn't safe to open with an older one. To go back,
restore the backup you made before upgrading:

```bash
python3 clawdblock.py stop
python3 clawdblock.py setup --mc-version 26.2     # back to the tested version and its mods
```

Then move `server/world` away, unzip the backup inside `server/`, restore your copy of `data/`, and start.

## Telling others

Found that a new version works, or fixed a rename? Open a pull request: update `MC_VERSION` in `clawdblock.py`
only once a version has been tested with every blueprint and the catalog. See [contributing.md](contributing.md).

## See also

[Getting started](getting-started.md) · [Troubleshooting](troubleshooting.md) · [Architecture](architecture.md)
