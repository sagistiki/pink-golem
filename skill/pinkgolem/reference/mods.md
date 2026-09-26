# Mods: what each one gives

Read this when a tool is missing, when a player asks what the server can do, or before you use a mod's blocks or
commands. Pink Golem runs Fabric; every mod below is server-side, so players join with a plain Minecraft client.
Mods are managed with `python3 pinkgolem.py mods …` in the Pink Golem folder.

## Overview

| Mod | Tier | For the players | For the AI | Without it |
|---|---|---|---|---|
| `fabric-api` | required | — (library other mods need) | — | most mods don't load |
| `carpet` | required | `/player`, `/script`, many rules | the bot body, helpers, scarpet, undo, vision, verify, access check, monitor | almost nothing works: no bot, no checks |
| `lithium` | recommended | less lag | faster big builds | fine, just slower |
| `worldedit` | recommended | `//set`, `//replace`, `//copy`, `//paste` … | `minecraft_worldedit` | the tool is hidden; use fills and generators |
| `bluemap` | recommended | 3D web map of the world at `http://localhost:8100` | `minecraft_screenshot mode:real` (real textures) | iso / top / pov renders still work |
| `essential-commands` | recommended | `/warp`, `/home`, `/spawn`, `/tpa`, `/back` | warps to finished builds, teleport buttons | players walk or use `/tp` (ops) |
| `spark` | recommended | — | `spark tps`, `spark profiler` when the server lags | guess the cause of lag |
| `chunky` | optional | smooth exploring | pre-generate land (only when asked, when nobody is online) | chunks generate while people explore |
| `polydecorations` (+ `polymer`) | optional | furniture blocks: benches, tables, baskets … | extra furniture ids (below) | vanilla furniture only |
| `ledger` | optional | block logging and rollback for multiplayer | find out who changed what | only your own undo stack |
| `carpet-extra` | optional | extra Carpet rules | — | — |

## Adding and removing mods

```
python3 pinkgolem.py mods list                  ✓ = installed, with what each one is for
python3 pinkgolem.py mods add bluemap spark     downloads the build for this Minecraft version from Modrinth
python3 pinkgolem.py mods remove ledger
python3 pinkgolem.py mods update                newest builds of everything installed
```

- **Restart the server after any change** — mods load only at startup. Only the user starts and stops the server;
  ask them.
- Dependencies come along: `polydecorations` adds `polymer`, `carpet-extra` needs `carpet`.
- `no build for Minecraft <version> on Modrinth yet — skipped` = that mod has not been updated for this game version.
  Wait, or leave it out.
- Any other Fabric mod: drop its `.jar` into the server's `mods/` folder (the command says where). The MCP only
  knows the mods in the table above.

## What the MCP does when a mod is missing

The MCP reads the server's `mods/` folder at startup:
- **Tools that need a missing mod are hidden** from the tool list: `minecraft_worldedit` needs WorldEdit,
  `minecraft_bot` and `minecraft_helpers` need Carpet. Calling one anyway (e.g. through `call_tool`) answers
  `<tool> needs the <mod> mod — install it with: python3 pinkgolem.py mods add <mod>`.
- **`minecraft_status`** lists the important mods (`carpet`, `worldedit`, `bluemap`, `polydecorations`,
  `essential_commands`), shows `PROBLEM: Carpet is not installed …` when Carpet is missing, and `could_add` with the
  recommended mods that are not there.
- Features inside other tools fail with a clear message: `mode:real` says `real screenshots need the BlueMap mod …`;
  any scarpet call says `Scarpet (/script) is not available — the Carpet mod is required`.
- When the MCP runs on another machine than the server (the mods folder cannot be read), everything is offered and
  `minecraft_status` says `mods: unknown`.

## Carpet (required)

Your body is a Carpet fake player (`/player <bot> …`, driven by `minecraft_bot`); the helper builders are more fake
players. Scarpet (`/script`) runs the `cu`, `helpers` and `bubble` apps, and through them undo snapshots,
verification, world scans, `dark()`, previews on site (`show`) and `minecraft_monitor`. Game logic apps
([game-logic.md](game-logic.md)) need it too. Fake players count as online players (see `max-players`).
`/draw sphere x y z r <block>` makes instant shapes, but like any command the MCP cannot parse, it gets no undo
snapshot and no verification.

## WorldEdit (recommended)

`minecraft_worldedit commands:["pos1 10,-61,5", "pos2 20,-50,15", "set stone", "replace dirt grass_block", "walls glass"]`
— commands WITHOUT slashes. Also `sphere glass 5`, `hcyl stone 8 20`, `copy`, `paste`, `rotate 90`, `stack 3 up`,
`move`, `undo`, `redo`.

- Selection, clipboard and history belong to the bot's WorldEdit session; `copy`/`paste` are relative to where the
  bot stands — `tp` it first.
- WorldEdit's replies go to the bot, not to you: always check with `minecraft_inspect` or a screenshot.
- WorldEdit edits are NOT in `minecraft_undo`; use its own `undo`. The zone guard applies when `pos1` and `pos2` are
  in the same call.
- Quotes and backslashes are refused (no NBT); use `minecraft_run_command` for those.

## BlueMap (recommended)

A 3D map of the world in a web browser, at `http://localhost:8100` on the server machine (the port comes from
`config/bluemap/webserver.conf`). For you: `minecraft_screenshot mode:real` photographs it with real textures. It
needs Chrome or Edge on the machine running the MCP (and Node 22+). `update:true` re-renders the area first (+8 s);
without it BlueMap can lag about a minute behind fresh builds. Use `iso`/`top`/`pov` for checking, `real` for showing
a finished build.

## Essential Commands (recommended)

- **Warp to every finished build:** stand the bot at the entrance (`minecraft_bot action:tp`), then
  `execute as <bot> at @s run warp set <name>`. List: `execute as <bot> run warp list`. Store it in the world map:
  `minecraft_map action:update name:"…" warps:["<name>"]`.
- **Teleport buttons:** a scarpet app or command runs `execute as <player> run warp tp <name>` — it runs with console
  permission, so it works for every player.
- Tell players about `/warp <name>`, `/home`, `/spawn`, `/tpa <player>`, `/back`.

## Spark, Lithium, Chunky, Ledger, Carpet Extra

- **Spark:** `spark tps` (is the server keeping up?), `spark profiler start` … `spark profiler stop` (what is slow).
  Pair with entity counts ([troubleshooting.md](troubleshooting.md), Performance).
- **Lithium:** nothing to do; it just makes the server faster.
- **Chunky:** pre-generates terrain around a centre and radius. It is heavy: only when the user asks, and when
  nobody is online.
- **Ledger:** logs who placed and broke which block, with rollback (`/ledger` commands). Read its documentation
  before a rollback; your own builds are better undone with `minecraft_undo`.
- **Carpet Extra:** extra Carpet rules (`/carpet` settings). Only change rules the user asked for.

## Polydecorations (optional, with Polymer)

Furniture blocks that vanilla clients see without any mod. Tested ids:

| Id | Notes |
|---|---|
| `polydecorations:dark_oak_bench`, `polydecorations:cherry_bench` | states `facing`, `type`, `has_rest` |
| `polydecorations:dark_oak_table`, `polydecorations:cherry_table` | tables |
| `polydecorations:dark_oak_stump` | a stool / side table |
| `polydecorations:basket` | `open=true` makes a pet bed; not solid |
| `polydecorations:cardboard_box` | `open=true`; SOLID — a mob summoned inside it suffocates: summon pets on top (y+1) |
| `polydecorations:<color>_sleeping_bag` | two parts, like a bed |
| `polydecorations:globe`, `polydecorations:display_case` | print "unexpected error" but ARE placed — check with `minecraft_inspect`. For display cases a `glass` block with an `item_display` inside is more reliable |

Also named in the mod (test before use): `wall_lantern`, `brazier`, `rope`, `wind_chime`, `long_flower_pot`,
mailboxes. For any id you have not used: one `setblock` + `minecraft_inspect` first. Furniture next to doors does
not trip the access check's "raised step" rule. See [furniture.md](furniture.md).

## Client-side mods (players' choice)

Nothing is needed on the players' computers to join. Some players like extra client mods; you can advise, but you
don't install or rely on them:
- **Axiom** — a visual in-game editor for building by hand. It has to be installed on the player's client AND on the
  server (drop the jar into `mods/`, restart), and it is meant for ops. `pinkgolem.py` does not manage it.
- BlueMap needs no client mod: players open the map in a browser.

## Common mistakes

- Promising a mod's feature without checking `minecraft_status` first.
- Forgetting the server restart after `mods add`.
- Trusting WorldEdit without looking: its output never reaches you.
- Summoning a pet into a `cardboard_box` (solid) instead of on top of it.

## See also
[troubleshooting.md](troubleshooting.md) · [furniture.md](furniture.md) · [verification.md](verification.md) ·
[game-logic.md](game-logic.md) · [scarpet.md](scarpet.md)
