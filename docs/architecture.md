# How Pink Golem works

This page explains what happens between "build me a cottage" and the blocks appearing: the pieces, how they
talk to each other, the safety rails, and the limits. Read it if you want to change the code, if you're
curious, or if you're debugging something the [troubleshooting](troubleshooting.md) page doesn't cover.

---

## The big picture

```
 ┌──────────────────────────┐
 │ AI client                │  Claude Code · Claude Desktop · Gemini CLI · Codex · LM Studio · any MCP client
 │  + skill (SKILL.md /     │  the skill teaches it HOW to build; the tools let it act
 │    SYSTEM_PROMPT.md)     │
 └────────────┬─────────────┘
              │ MCP over stdio (JSON-RPC on stdin/stdout; the client starts `node mcp-server/index.js`)
 ┌────────────▼─────────────┐
 │ Pink Golem MCP server    │  index.js  : RCON client, log watcher, tool loader (hot reload)
 │ (Node, one per client)   │  lib/*.js  : shared helpers (safety, world reads, bot, crew, jobs, sight)
 │                          │  tools/*.js: 37 minecraft_* tools in 11 groups
 └──┬──────────────┬────────┘
    │ RCON (TCP,   │ reads server/logs/latest.log every 0.4 s (chat, joins, leaves)
    │ 127.0.0.1)   │ reads server/mods/ (which mods → which tools)
 ┌──▼──────────────▼────────────────────────────────────────────┐
 │ Minecraft Java server (Fabric)                               │
 │  Carpet: fake players (the AI's body, helper builders),      │
 │          scarpet scripting                                   │
 │  scarpet apps: cu (reads, undo snapshots, checks),           │
 │    helpers (swinging builders), bubble (speech bubbles),     │
 │    + optional game apps (race, vendor, launchpad…)           │
 │  optional mods: WorldEdit, BlueMap, Lithium, spark…          │
 └──────────────────────────────────────────────────────────────┘

 Big builds:
   generator (Python, mclib + parts) ──writes──► jobs/<name>-1.json, -2.json, -3.json
        ▲ run by minecraft_generate                     │ queued as background jobs
        │                                               ▼
   the AI picks a blueprint / writes a generator    job runner: boss bar, helper crew, undo snapshot,
                                                    commands one by one over RCON, then verify,
                                                    access check, auto-zone
```

Every AI client starts **its own** MCP server process. Several processes can share one Minecraft server: a
cross-process lock (`data/.rcon.lock`) makes sure only one RCON command runs at a time, because vanilla RCON
shares one output buffer between connections and two commands at once would get each other's answers. Shared JSON
files in `data/` are updated under the same kind of lock.

---

## Why RCON + Carpet, and not a bot that logs in

Many Minecraft AI projects use a *protocol bot*, a program that pretends to be a Minecraft client and logs in over
the network. Pink Golem doesn't, and that choice is on purpose:

| | Protocol bot | Pink Golem (RCON + Carpet) |
|---|---|---|
| New Minecraft version | the bot library must learn the new network protocol first; this can take weeks | RCON and server commands barely change between versions; works as soon as Fabric and Carpet are out |
| Building | places blocks one by one like a player, or needs op commands anyway | `/fill`, `/setblock`, `/clone` as the console: thousands of blocks per second |
| Reading the world | only what the bot's client has loaded, near the bot | scarpet reads any loaded block anywhere, with full block states |
| The visible body | the bot itself | a Carpet fake player: a real server-side player that walks, looks, swings and chats |
| Chat | the bot's chat connection | `tellraw` out, `latest.log` in |

The result is **version-proof**: the MCP server depends on the command language and the log format, not on the
network protocol.

---

## Inside the MCP server

| File | Role |
|---|---|
| `index.js` | Reads the config, runs the RCON client (with the 1400-byte guard), watches `latest.log` for chat, loads the tools and answers MCP requests. Logs go to stderr; stdout is reserved for MCP |
| `tools/index.js` | Builds the shared helper object `K` from `lib/*.js`, collects the tool groups from `tools/*.js`, hides tools whose mod is missing, converts string arguments (`"3"`, `"true"`, `"[1,2,3]"`) for clients that send everything as text |
| `tools/connection.js` | `minecraft_status`, `minecraft_server_log` |
| `tools/chat.js` | `minecraft_chat`, `minecraft_get_chat`, `minecraft_wait_for_chat`, `minecraft_wait`, `minecraft_get_players` |
| `tools/build.js` | `minecraft_run_command`, `minecraft_build`, `minecraft_build_layers`, `minecraft_generate`, `minecraft_worldedit`, `minecraft_jobs`, `minecraft_undo`, `minecraft_verify` |
| `tools/look.js` | `minecraft_inspect`, `minecraft_vision`, `minecraft_scarpet`, `minecraft_screenshot`, `minecraft_preview`, `minecraft_check_access`, `minecraft_reach`, `minecraft_monitor` |
| `tools/survey.js` | `minecraft_survey`, `minecraft_section` |
| `tools/rails.js` | `minecraft_rails` (trace / path / ride) |
| `tools/body.js` | `minecraft_bot`, `minecraft_helpers` |
| `tools/memory.js` | `minecraft_map`, `minecraft_zones`, `minecraft_people`, `minecraft_notes`, `minecraft_cleanup` |
| `tools/dev.js` | `minecraft_app` (lint / status / reload / patch / errors), `minecraft_playtest` (scripted tests with fake players) |
| `tools/pack.js` | `minecraft_pack` (build / deploy / status of the server resource pack) |
| `tools/entities.js` | `minecraft_entities` (census / duplicates / ghosts / remove of loaded entities) |
| `lib/core.js` | paths, the locked RCON call, JSON files, chat, players, geometry, scarpet calls |
| `lib/features.js` | which mods are installed (see *Feature detection*) |
| `lib/world.js` | reads the world as a voxel grid; tells natural terrain from builds |
| `lib/safety.js` | zone guard, overwrite guard, undo snapshots, auto-zones, verification |
| `lib/bot.js` | the AI's body: walking, A* paths through doors and up stairs, following |
| `lib/crew.js` | the helper builders (hard hats, hi-vis vests) and speech bubbles |
| `lib/jobs.js` | background jobs, boss bar, after-build checks, running Python generators |
| `lib/sight.js` | screenshots, previews, BlueMap photos, the access check, free-space search |
| `lib/context.js` | where each chat line was written from, big-box reads, area arguments, the preflight (server-side syntax check without running anything) |
| `lib/devkit.js` | pure helpers of the dev tools: the scarpet linter, zip read/write, resource-pack merge and validation, finding what a test left in app records |
| `render.js`, `display.js`, `pathfind.js`, `sim.js`, `analyze.js`, `worldmap.js` | pure modules: PNG renderer, display entities for it (models, block states and fonts from the resource pack and the optional client jar), A* pathfinder, command simulator (previews), accessibility analysis, world-map index |

### Hot reload

`index.js` watches the modification times of every `.js` file in `lib/`, `tools/` and the top-level helper modules.
When one changes, the **next tool call** re-imports the whole tool layer with a fresh version tag and tells the
client that the tool list changed. You can edit a tool while an AI session runs, with no restart. Two exceptions:

- changes to `index.js` itself need the AI client to restart the MCP server;
- some clients cache the tool list. For a brand-new tool they don't show yet, the AI can call it through
  `minecraft_run_command` with `call_tool:"minecraft_new_tool"` and `tool_args:{…}`.

### Feature detection

At load time `lib/features.js` lists the `.jar` files in `server/mods/`. A tool can declare `requires: ["worldedit"]`.
If that mod is missing, the tool is **hidden** from the tool list, and a direct call explains how to install it.
Today: `minecraft_worldedit` needs WorldEdit; `minecraft_bot` and `minecraft_helpers` need Carpet; the `real`
screenshot mode needs BlueMap and a Chrome or Edge browser. `minecraft_status` reports missing mods and suggests
recommended ones. If the mods folder can't be read (the MCP server runs on another machine than the Minecraft
server), every tool is offered.

---

## The safety rails

Every tool that changes blocks goes through the same steps. Together they make careless builds recoverable.

| Rail | What it does | Where |
|---|---|---|
| **Zone guard** | Refuses commands that touch a protected zone (someone's build) unless `allow_protected:true`. An AI's own finished builds don't block it; a zone it claimed (`minecraft_zones action:claim`) stays open for 6 hours after its last build there | `lib/safety.js` |
| **Overwrite guard** | `minecraft_build` and `minecraft_build_layers` refuse to place blocks where built blocks already are, and list what's in the way, unless `allow_overwrite:true`. Natural ground and wild plants don't count | `lib/safety.js`, `lib/world.js` |
| **Undo snapshots** | Before a build, the `cu` app saves every block in the target box (with states) to `server/world/scripts/cu.data/`. The last 30 builds per server are on the undo stack (`data/undo.json`); `minecraft_undo` restores them by steps or by label | `lib/safety.js`, `cu.sc` |
| **Verification** | After a job, the MCP recomputes what every block should be from the commands and compares with the world: mismatches by type (e.g. `glass>oak_leaves` = a tree grew into it), plus stray water or lava | `lib/safety.js`, `cu.sc` |
| **Access check** | With `entrance:[x,y,z]` on the last phase, a virtual walk from the door with real player rules (1-block jumps, stairs, drops of up to 3, doors) reports unreachable rooms, blocked doors, stairs into walls, steps at doors and dark spots | `analyze.js`, `lib/sight.js` |
| **Auto-zone** | A finished build of 300+ blocks becomes a protected zone owned by the bot that built it (`data/zones.json`) | `lib/safety.js` |
| **Preview** | `minecraft_preview` runs the commands in a simulated copy of the world and returns pictures, so problems can be fixed before anything is placed | `sim.js`, `render.js` |

Undo snapshots skip container and sign contents, and WorldEdit edits have their own undo (WorldEdit's `undo`).

---

## Generators and jobs

Big builds are **generators**: Python scripts that describe a build as voxels with `skill/pinkgolem/scripts/mclib.py`
(and ready parts from `parts.py`). `Build.commands()` compresses the voxels into `/fill` runs, layer by layer, and
`Build.save()` writes them to `jobs/<name>.json`, split into `-1`, `-2`, … files past 1200 commands.

`minecraft_generate` runs a generator (only files inside the Pink Golem folder) with `PINKGOLEM_ROOT`,
`PINKGOLEM_JOBS` and `PINKGOLEM_CU_DATA` set, collects the job files it wrote, and with `build:true` queues each
file as a **background job**. A job:

1. snapshots the area (undo), and brings helper builders to the site (`helpers:N`, up to 4);
2. shows a boss bar to every player and runs the commands one by one over RCON;
3. when done, verifies the build, runs the access check if an entrance was given, and registers the zone;
4. leaves the helpers on site for the next job; they go home after 10 idle minutes.

The AI follows with `minecraft_jobs action:wait` (up to 50 s per call). See [writing-blueprints.md](writing-blueprints.md).

---

## The scarpet apps

Scarpet is Carpet's scripting language. Apps live in the world's `scripts/` folder, and Pink Golem needs three
of them (setup installs them from `skill/pinkgolem/scripts/`):

| App | Job |
|---|---|
| `cu` | the MCP's hands inside the server: `count`, `occupied`, `surface`, `level`, `snap`/`restore` (undo), `dark` (mob-spawn spots), `find`, `show` (glowing site outline), `mark`, `ytop`, `bstr`, and the verification and monitor helpers |
| `helpers` | makes helper builders really swing their arms while they work, and finds standing spots near the work |
| `bubble` | speech bubbles (text displays) that float above the AI's head and the builders' |

The optional apps in `scarpet-apps/` (fireworks, launch pads, races, secret doors, TNT Run, vendor stands, welcome) are
game logic for players: `python3 pinkgolem.py apps add race`. Each reads its settings from
`server/world/scripts/<app>.data/*.json` and has a `reload()` function.

---

## Data files

Everything the AI remembers is plain JSON or Markdown in `data/`. You can read it, back it up and, when no AI is
running, edit it by hand.

| File | Contents |
|---|---|
| `world_index.json` | the world map: every build's name, box, entrances, warps, owner, builder, notes |
| `zones.json` | protected zones (auto-zones and zones added by hand) |
| `undo.json` | the undo stack (up to 30 entries; the block data itself is in the world's `scripts/cu.data/`) |
| `people.json` | players: roles, likes, style, notes |
| `LEARNINGS.md` | the shared, append-only journal every AI reads at the start of a session |
| `screenshots/` | every picture the tools took |

`new-world` deletes `zones.json`, `undo.json` and `world_index.json`, because they describe the old world; people
and learnings stay.

---

## Configuration

The MCP server reads `pinkgolem.json` (or the file in `PINKGOLEM_CONFIG`), then environment variables, which
override it: `MC_BOT_NAME`, `MC_CHAT_COLOR`, `MC_SERVER_DIR`, `MC_RCON_HOST`, `MC_RCON_PORT`, `MC_RCON_PASSWORD`. The
RCON port and password come from `server.properties` unless overridden. `pinkgolem.json` also holds `bot_aliases`
(names players can use to address the AI) and `crew` (`names` of up to 4 helpers, optional `lines` they say).

**Screenshots and the resource pack.** `resource_pack` configures `minecraft_pack` (parts, output, and where deploy
uploads: `upload.hosts` (opt-in, e.g. `["mcpacks", "catbox"]`; nothing goes to a third party unless listed), or `upload.command`, or `publish_dir` + `public_url`;
[testing-apps.md](../skill/pinkgolem/reference/testing-apps.md)). Screenshots draw display entities with the built
pack (or its parts) and, if it finds one, the vanilla client jar of a local Minecraft launcher (the `mc_version`
first, else the newest). `client_jar` sets the jar's path, or `false` to never read it; the environment variable
`MC_CLIENT_JAR` (a path, or `off`) overrides both. The jar is only read, never copied or uploaded.

**The bot's look.** The default body is the player `Golem` with the team prefix `Pink `, so players see **Pink Golem**
over its head, in the player list and in chat (a player name can't contain a space). It wears pink leather armor with a
gold trim and a shimmer, and holds a pink block and a pink tulip, so nobody mistakes it for a player. `bot_prefix`
changes the prefix (another `bot_name` gets none unless you set one), `chat_color` colours it, `bot_outfit: "none"`
skips the outfit.

---

## Limits (and how the tools work around them)

| Limit | Value | Handling |
|---|---|---|
| One RCON command | ~1400 bytes (vanilla RCON drops packets over 1460) | longer commands are refused with "Split it up"; generators emit short `/fill` lines |
| One `/fill` | 32768 blocks (vanilla) | `minecraft_build` splits big fills automatically |
| One world scan | ~120k blocks per scarpet call; up to 700k by slabs | vision, checks and pictures scan in slabs |
| One iso/top screenshot | ~118k blocks | the area is trimmed; use a smaller box or `cut_y` |
| `minecraft_inspect` box | 8000 blocks | use `minecraft_vision` or `count` for more |
| Overwrite guard | checks boxes up to 120k blocks | bigger: check with `minecraft_vision mode:check` first |
| Undo snapshot | up to 4M blocks per build, in 250k slabs | bigger builds get no snapshot (the result says so) |
| Undo stack | 30 builds | the oldest snapshot is deleted |
| Job file | 1200 commands | `Build.save()` splits into numbered files |
| Waiting tools | `minecraft_jobs wait` / `minecraft_monitor` 50 s, `minecraft_wait_for_chat` 110 s, `minecraft_wait` 300 s | call again to keep waiting |
| Survey / section | 480k blocks (footprint ≤ 118k columns) / 160 wide | smaller box |

## See also

- [Contributing](contributing.md): add a tool, a lib helper, a blueprint, an app
- [Writing blueprints](writing-blueprints.md)
- [Upgrading](upgrading.md): newer Minecraft versions
- [The skill](../skill/pinkgolem/SKILL.md): how the AI is told to use all this
