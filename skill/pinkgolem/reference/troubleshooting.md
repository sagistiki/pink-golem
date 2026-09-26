# Troubleshooting

Look up the message or symptom you see, then apply the fix. The messages are quoted as the tools print them.
General rule: read the message to the end — most of them already name the fix. When something in the world is
wrong, find the exact cause first (`minecraft_inspect`, a bot walk, `minecraft_server_log`), fix only that, and say
in one line what was wrong.

## First steps when anything is wrong

1. `minecraft_status` — connected? bot in the world? which mods? flat or normal world?
2. Read the whole reply of the failing call: `failures`, `verify.by_type`, `access.problems` ([verification.md](verification.md)).
3. `minecraft_server_log filter:"Exception|ERROR|WARN"` — crashed apps and mod errors show up here.
4. Look at the exact cells: `minecraft_inspect pos:[…]` beats any picture.
5. Reproduce once, with `minecraft_monitor` running if it involves timing (redstone, rides, apps).
6. Fix the cause in the generator or app, not with a one-off patch on top.

## Connection and server

| Symptom | Cause | Fix |
|---|---|---|
| `RCON error: connect ECONNREFUSED 127.0.0.1:25575 — nothing is listening …` | the Minecraft server is off (or still starting) | don't retry in a loop. Tell the user; the server starts with `python3 pinkgolem.py start` (only when they ask). Meanwhile plan, write generators and look at them with `minecraft_preview` — it works offline |
| same, plus `… and is enable-rcon=true in server.properties (it is false now)` | RCON is switched off | `python3 pinkgolem.py setup` (keeps the world), or set `enable-rcon=true` and restart the server |
| `RCON password is empty (…server.properties)` | setup never ran, or the file was replaced | `python3 pinkgolem.py setup`, or set `rcon.password=<something>` and restart the server |
| `RCON login failed: wrong rcon.password` | `pinkgolem.json` (`rcon_password`) or the env var `MC_RCON_PASSWORD` differs from server.properties | make them match, or remove the override |
| `RCON connection closed (server stopped or restarted?)` | the server went down mid-call | `minecraft_status`; wait for it to come back |
| `RCON timeout for: <command>` | the server is lagging or the command is very heavy | smaller boxes; see Performance below |
| `minecraft_status` shows `PROBLEM: Carpet is not installed` | no Carpet: no bot, no scarpet, no undo, no checks | `python3 pinkgolem.py mods add carpet`, restart the server |
| a tool is missing from your list | its mod is not installed (the MCP hides it), or your client cached an old tool list | `minecraft_status` → `could_add`; for a cached list see "Tools" below |

## Building

| Symptom | Cause | Fix |
|---|---|---|
| `PROTECTED — nothing was changed. This touches protected zone(s): "…" (owner …)` | the box overlaps someone's protected zone | build elsewhere. Only if the owner asked: `allow_protected:true`, or `minecraft_zones action:claim name:"…"` once for a multi-phase job for them |
| `PROTECTED` on your own follow-up phase | the zone was made for someone else with you as builder, and 6 h passed | `minecraft_zones action:claim` again |
| `STOPPED — nothing was built. N existing block(s) are in the way: …` | `minecraft_build` / `build_layers` would overwrite a build | look with `minecraft_vision`, move the build, or `allow_overwrite:true` if you really mean to change it |
| `Could not set the block` / `No blocks were filled` | already exactly like that | harmless — counted as `unchanged` in jobs. If a fill you expected to change things reports 0, re-check the y |
| `Too many blocks in the specified area (maximum 32768 …)` | one vanilla `fill` is limited to 32768 blocks | split the box. `minecraft_build` splits fills itself; generator fills are one layer high, so only a raw `cmd("fill …")` or a layer over 32768 blocks hits it |
| `Command too long for RCON (N bytes, max 1400). Split it up.` | one command over 1400 bytes | move the logic into a generator (many short commands) or into a scarpet app; shorten long text |
| `Failed to place feature` | the tree did not fit: not enough air around it or no dirt/grass under it | another spot or a smaller tree; run `place feature` as a plain command (never inside `execute at`) and confirm with a `count` of logs before/after. Features that worked: `fancy_oak_bees_002`, `oak_bees_002`, `birch_bees_002`, `super_birch_bees_0002`, `cherry_bees_005`, `dark_oak`, `azalea_tree`, `spruce`, `fancy_oak`, `birch` |
| `Unknown block type` / `Incorrect argument` / `<--[HERE]` | wrong id or state name | check the id; renamed in 26.x: `iron_chain` (not `chain`). Test one `setblock` + `minecraft_inspect` first |
| verify `by_type` shows `glass>oak_leaves` (or any `X>*_leaves`) | a tree grew into the build | move the tree away, put the blocks back, `minecraft_verify` again |
| a fix is gone after rebuilding | the regenerated generator overwrote a separate fix job | put fixes INTO the generator; re-run the access check after every regeneration |
| a furniture fill replaced a door | furniture placed on the wall line | furniture only inside the walls; inspect door columns after furnishing |
| undo: `refused: newer builds overlap this one …` | restoring the old snapshot would wipe newer builds too | undo the newer ones first, or `force:true` if that is intended |
| undo: `nothing_undone: no build label has all of: …` | the words don't match any label | use one of the `closest` labels, or `minecraft_undo list:true` |
| `undo: {skipped: "no undo snapshot (box is N blocks, max 4000000)"}` | the build box is too big to snapshot | build in smaller phases, or `script in cu run snap(...)` parts yourself |
| job result `access: {error: "no entrance stored in the world map for this area …"}` | `check_access:true` without a map entry | pass `entrance:[x,y,z]` |

## Scarpet and apps

| Symptom | Cause | Fix |
|---|---|---|
| `= null` from `minecraft_scarpet` | the last statement returns nothing (`for`, `print`, trailing `;`), or the function exists only in an app | end with the value (`…; l`); use `app:"cu"` for cu functions |
| unknown app / app not loaded (`script in cu run …` fails) | the app is not loaded, or its file is missing | `script load cu`; if the file is missing: `python3 pinkgolem.py apps add cu` (same for `helpers`, `bubble`) |
| `Scarpet (/script) is not available — the Carpet mod is required` | no Carpet | `python3 pinkgolem.py mods add carpet` |
| `read_file` returns nothing | run outside the app | `script in <app> run …` or `minecraft_scarpet app:"<app>"` |
| an app does nothing after you edited its JSON | the app still has the old data | `script in <app> run reload()` |
| an app misbehaves after `script load` | a reload forgets every global (who was switched to adventure, which door is open) | keep state in player tags / files; check the state before reloading ([game-logic.md](game-logic.md)) |
| a button fires on every reload | a test left it `powered=true` | `setblock … powered=false` |
| an app error | a crashed scarpet function | `minecraft_server_log filter:"script|scarpet|Exception"` |

## Bot and helpers

| Symptom | Cause | Fix |
|---|---|---|
| `Bot "X" is not in the world — spawn it first` / `botInWorld: false` | the bot was never spawned or was killed | `minecraft_bot action:spawn player:<name>` (or `pos:[x,y,z]`) |
| `Player "X" not found / not online.` | wrong name or the player left | `minecraft_get_players` |
| walk result `No path (…) — walked straight instead` / legs with ✗ | walls, a missing door, or too far (`too far for pathfinding`) | `minecraft_bot action:tp` near the goal, then `walk_to` the last part |
| the bot keeps walking | `/player <bot> stop` stops actions, not walking | `minecraft_bot action:stop` (does both) |
| the bot breaks blocks when it swings | someone put it in creative | `minecraft_bot action:gamemode mode:adventure` (swing switches it back itself) |
| helpers don't appear; result says `server has room for N more players` | the server is full: bot and helpers are players too, and count against `max-players` in server.properties | raise `max-players` and restart, or use fewer helpers |
| helpers stand still without swinging | `helpers.sc` is not loaded | `script load helpers` (or `python3 pinkgolem.py apps add helpers`) |
| helpers never leave | `keep_helpers:true` | `minecraft_helpers action:dismiss` |

## Tools and jobs

| Symptom | Cause | Fix |
|---|---|---|
| a new tool is not in your tool list | your client cached the tool list at startup | `minecraft_run_command call_tool:"minecraft_monitor" tool_args:{…}` runs any tool by name |
| `<tool> needs the <mod> mod — install it with: python3 pinkgolem.py mods add <mod>` | its mod is missing | install it (see [mods.md](mods.md)) or use another way |
| `minecraft_jobs` says `No jobs.` after the MCP restarted | jobs live in the MCP's memory | the partial build stays; undo snapshots survive (`minecraft_undo list:true`). Re-run the command file (finished parts come back as `unchanged`) or undo it by label. A leftover progress bar: `bossbar remove pinkgolem:job<N>` |
| `Box is N blocks; max 8000 per inspect` | box too big | split it, or `script in cu run count(…)` for totals |
| `area too big (N blocks) — use a smaller box (max ~118k blocks)` | screenshot box too big | narrow the y range, or use `mode:top` of a thin slice |
| `real screenshots need the BlueMap mod` / `Google Chrome or Microsoft Edge was not found` / `needs Node 22+` | `mode:real` requirements missing | `mode:iso`/`top`/`pov` instead, or install what is missing |
| `monitor did not finish in time (server lagging?)` | the server fell behind | shorter `seconds`, check Performance |
| `files must be inside the Pink Golem folder` | a command file or generator path outside the repo | put generators and job files in `jobs/` |
| WorldEdit: nothing happened | its replies go to the bot, not to you; quotes and backslashes are refused | verify with `minecraft_inspect` or a screenshot |

## Creatures

| Symptom | Cause | Fix |
|---|---|---|
| pets frozen in place | a tamed pet whose owner is offline sits and waits | an invisible marker `armor_stand` can be the owner while the player is away; switch `Owner` back when they arrive. Give pets `Invulnerable:1b` |
| animals died right after summoning | summoned inside a solid block (some decoration blocks, e.g. a cardboard box, are solid) | summon on top (y+1); list the entities again ~5 s later, not right after |
| villagers don't take their jobs or homes | summoned in unloaded chunks, or level 1 without a job site | tp the bot to the site first; summon with `VillagerData:{profession:"minecraft:farmer",level:2,type:"minecraft:plains"},Xp:10,PersistenceRequired:1b`; after ~5 s check `str(query(v,'nbt','Brain')) ~ 'home'` / `'job_site'` |
| mobs spawn inside builds | dark floor spots (only on easy or harder: peaceful spawns no hostile mobs) | `script in cu run dark(…)` → lanterns or `light[level=15]` on a ~7-block grid until 0 spots |
| animals or NPCs not where you left them | they wander, or they are in unloaded chunks | `entity_selector` only sees loaded chunks; tag everything you summon |

## Performance

| Symptom | Cause | Fix |
|---|---|---|
| lag, rubber-banding, `RCON timeout` | too many entities, clocks, huge edits while people play | `spark tps` and `spark profiler start` / `stop` (spark mod); entity counts: `minecraft_cleanup dry_run:true`, `execute if entity @e[type=item]` |
| thousands of items / arrows / fireworks lying around | drops from edits and shows | `minecraft_cleanup` (area with `from`/`to` or `pos` + `radius`) |
| server crashed with a watchdog timeout | an entity-spawning loop (e.g. a repeating command block that summons) | remove the loop; spawn once, tag it, move it with `modify` |
| lag while exploring new land | chunk generation | pre-generate with Chunky when nobody is online |

## Common mistakes

- Retrying a refused connection in a loop instead of telling the user the server is off.
- Passing `allow_protected:true` or `allow_overwrite:true` just to make an error go away: those guards protect
  other people's builds. Use them only when the owner asked.
- Treating `unchanged` / "Could not set the block" as a failure and rebuilding.
- Reloading an app to "fix" it while a player is inside the game.
- Guessing a cause from a screenshot; the answer is almost always in `minecraft_inspect` or the log.

## See also
[verification.md](verification.md) · [mods.md](mods.md) · [scarpet.md](scarpet.md) · [game-logic.md](game-logic.md) ·
[entities.md](entities.md) · [lessons.md](lessons.md)
