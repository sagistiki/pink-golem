# What ClawdBlock can do

The long version of the README's list, with a link to the page that explains each part.

## Build

- **An MCP server with 37 tools.**
  - The AI's body: walks with pathfinding, opens doors, swings.
  - Hands: commands, generators, background jobs, helper builders.
  - Eyes: text vision; isometric, top-down and first-person renders; previews of builds that don't exist yet.
  - Memory: a world map, people, a shared learning journal.
  - [How it works](architecture.md)
- **Safety rails:** automatic undo for every build, protected zones for other people's builds, an overwrite guard,
  verification after every job, and an access check that walks every room from the entrance.
  [The safety rails](architecture.md#the-safety-rails)
- **A building skill:** golden rules and a step-by-step recipe a small model can follow, plus 32 reference pages
  (houses, roofs, stairs, furniture, interiors, styles, landscaping, water, towers, big projects, NPCs, game logic,
  redstone, verification, troubleshooting…) and hard-won lessons from real builds.
  [SKILL.md](../skill/clawdblock/SKILL.md)
- **A building library and blueprints:** `mclib` + `parts` (furniture, roofs, stairs, windows, lamps, gardens, round
  towers, pools, flags), which work facing any direction, and nine ready blueprints: cottage, modern villa, tower,
  park, drop tower, TNT Run arena, Ferris wheel, roller coaster, catalog. [Writing blueprints](writing-blueprints.md)

## Play

- **Game-logic apps:** launch pads, free-fall drops, timed races with record boards, a TNT Run arena, vendor stands,
  secret doors, welcome shows, fireworks. [Game logic](../skill/clawdblock/reference/game-logic.md)
- **A game kit for round-based minigames:** a join zone with a countdown, save/restore, eliminations, spectating, end
  screens and records (demo: Shrinking Ring). [gamekit](../skill/clawdblock/reference/gamekit.md)
- **Rides:**
  - A rideable Ferris wheel.
  - A roller coaster on a smooth display-entity track, with real gravity, loops and a first-person ride.
  - [Rides](../skill/clawdblock/reference/rides.md) · [the case study](case-study-roller-coaster.md)
- **Drivable cars:** drift physics, a chase camera, models from a resource pack.
  [Vehicles](../skill/clawdblock/reference/vehicles.md)
- **On-screen graphics with no client mods:**
  - a live round minimap in the corner that turns with your view;
  - a HUD toolkit (speedometer, compass, timer, text) that shares one shader with the minimap.
  - [Minimap](../skill/clawdblock/reference/minimap.md) · [HUD](../skill/clawdblock/reference/hud.md)
- **Block textures made by code:** 111 natural 32x textures (nine woods, stone and deepslate, concrete / wool /
  terracotta in 16 colours, quartz, ground, all leaves) at any resolution, optional pixel-art shading, and a renderer
  that shows blocks in 3D before they go live.
  [Textures](../skill/clawdblock/reference/textures.md) · [resourcepacks/textures](../resourcepacks/textures)

## Run a live server

- **Developer tools:**
  - `minecraft_app` lints scarpet apps for the traps that break them, patches a function live without a reload, and
    reloads only when nobody is using the app.
  - `minecraft_playtest` runs a scripted test with fake players in one call and cleans up after itself.
  - `minecraft_pack` merges, validates and deploys the server resource pack.
  - [Testing apps](../skill/clawdblock/reference/testing-apps.md)
- **A watchdog:**
  - It finds what makes the server slow: entity piles, leaking apps that re-create the same entity, hot chunks, busy
    threads.
  - It tells the ops once, cleans only obvious junk, warns before the disk fills up, and makes safe rotating backups.
  - [Watchdog](../skill/clawdblock/reference/watchdog.md)
- **Key Bridge**, a tiny server-side Fabric mod:
  - movement keys to a scoreboard for scarpet vehicles;
  - `/packpush` to send a new resource pack to everyone live;
  - a flip camera for upside-down rides.
  - [mods-src/keybridge](../mods-src/keybridge)

## What's in the box

| Path | What |
|---|---|
| [`clawdblock.py`](../clawdblock.py) | setup · start · stop · status · doctor · mods · apps · connect · new-world · backup (stdlib Python) |
| [`install.sh`](../install.sh) / [`install.cmd`](../install.cmd) / [`install.ps1`](../install.ps1) | installers that check prerequisites and run setup |
| [`mcp-server/`](../mcp-server) | the MCP server: `index.js` core, `lib/` shared helpers, `tools/` tool groups, renderer, pathfinder, simulator |
| [`skill/clawdblock/`](../skill/clawdblock) | the skill: `SKILL.md`, 32 reference pages, `scripts/` (`mclib.py`, `parts.py`, `city.py`), `blueprints/`, `SYSTEM_PROMPT.md` for small models |
| [`scarpet-apps/`](../scarpet-apps) | launchpad, race, tntrun, ferris, minimap, vendor, secret_door, welcome, fireworks, cars, ring, watchdog (+ the `gamekit` and `hud` libraries) |
| [`resourcepacks/`](../resourcepacks) | minimap, HUD toolkit, car models, generated block textures, and `tools/` (`model_preview.py` for item models, `block_render.py` for blocks, both to PNG without a game client) |
| [`mods-src/keybridge/`](../mods-src/keybridge) | the Key Bridge mod's source and build script |
| [`docs/`](.) | these pages |

## Mods

| Mod | | Why |
|---|---|---|
| Fabric API, **Carpet** | required | Carpet gives the AI its body (fake players) and scarpet (fast world reads, undo, checks) |
| Lithium, WorldEdit, BlueMap, Essential Commands, spark | recommended | performance · big edits · a 3D web map + real-texture screenshots · warps · lag profiling |
| Chunky, Polydecorations (+Polymer), Ledger, Carpet Extra | optional | pre-generation · server-side furniture · rollback logs · extra rules |
| Key Bridge (built from `mods-src/keybridge`) | optional | movement keys for vehicles and rides; live resource-pack push; the flip camera |

The installer downloads everything from Modrinth for your Minecraft version, and `python3 clawdblock.py mods` adds or
removes mods later. Tools that need a missing mod hide themselves. Players need **no** client mods.
