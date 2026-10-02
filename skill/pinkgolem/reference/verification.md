# Verification: knowing a build is right

Read this before you say "done". A build is done when the numbers say so, not when a picture looks fine: pictures
hide wrong stair facings, a door that opens into a wall, a room nobody can reach and dark corners where mobs will
spawn. This page explains every check the tools give you and ends with the checklist to run on every build.

## 1. Read the job result

`minecraft_jobs action:wait id:N` (and foreground `minecraft_run_command` / `minecraft_build`) return:

```
{ "status": "done", "done": 412, "total": 412, "errors": 0, "unchanged": "6 (already like that — harmless)",
  "failures": [], "undo": {"id": "u…", "blocks": 5400, "parts": 1},
  "verify": {"checked": 3810, "mismatches": 4, "by_type": {"grass_block>dirt": 4}, "examples": ["…"],
             "stray_fluids": 0, "ok": false, "hint": "…"},
  "zone": {"added": "Claude: cottage walls"},
  "access": {"ok": true, "reached": "212/212 indoor floor cells reachable from 10 -60 3", "problems": []} }
```

| Field | Meaning | Action |
|---|---|---|
| `status` | queued / running / checking / done / cancelled / failed | `wait` again until done (each wait ≤ 50 s) |
| `errors` + `failures` | commands the server rejected (first 10, with the reply) | read every one; fix the command in the generator |
| `unchanged` | "Could not set the block", "No blocks were filled", "No entity was found" | harmless: the block was already like that |
| `undo` | snapshot taken before the build (`skipped` = too big, no undo) | `minecraft_undo match:'<label>'` reverts it |
| `verify.mismatches` | blocks that are not what the commands placed | read `by_type` (below) |
| `verify.stray_fluids` | water/lava SOURCES in the box that the build did not place: a leak or spill | must be 0 |
| `verify.flowing_water` | flowing water/lava blocks in the box | fine for fountains and waterfalls, a leak if outside the basin |
| `zone` | the build became (or grew) your protected zone (builds ≥ 300 blocks) | nothing |
| `access` | the access check, when you passed `entrance` (or `check_access:true`) on the last phase | `ok` must be true — section 2 |

`verify` is on by default (foreground `run_command`: from 26 commands). It checks `setblock` and `fill` with absolute
coordinates (not `keep` or filtered `replace` fills, not clones, summons or trees) and compares **block names only —
never states**. A stair facing the wrong way passes verification; check states with `minecraft_inspect`. Re-check
any time later with `minecraft_verify commands_file:"jobs/x.json"`.

### Reading `by_type` (`wanted>got`)

| Key | Cause | Harmless? |
|---|---|---|
| `grass_block>dirt` | grass under a placed block turns to dirt | yes |
| `glass>oak_leaves`, `X>*_leaves` | a tree grew into the build | no — move the tree or clear the leaves |
| `X>air` for flowers, torches, lanterns, carpets, door halves | the block popped off: no soil, no support, or its other half is missing | no — give it support (moss planter, pot) or place both halves |
| `air>water`, `air>lava` | fluid flowed in | no — find the source (see `stray_fluids`) |
| `X>Y` on a whole area | a later phase overwrote an earlier one, or you built at the wrong y | no — compare with the generator |

`verify.ok` is false for any mismatch, so a result with only `grass_block>dirt` is still fine.

## 2. The access check

Walks virtually from the entrance with player rules (1-block jumps, stairs and slabs, drops ≤ 3, doors) to every
room, door and stair, and adds `cu dark()` for the build's box. Nobody moves. Three ways to run it:

- on the last phase of a build: `entrance:[x,y,z]` (feet position just outside the main door) or `check_access:true`
  (uses the entrance stored in `minecraft_map`); with `minecraft_generate build:true entrance:[…]` it covers
  everything the generator made, not just the last file;
- afterwards: `minecraft_check_access build:"<map name>"` or `from`/`to` + `entrance`;
- before building: `minecraft_check_access commands_file:… simulate:true entrance:…`, or `minecraft_preview … entrance:…`.

| Problem line | What it means | Fix |
|---|---|---|
| `room around … — a N-block climb from … — no stairs/ladder` | the nearest reachable floor is 2+ blocks higher (sunken room) | stairs, ladder or a ramp |
| `room around … — N blocks higher than … — needs stairs up` | the room's floor is 2+ blocks above anything reachable | a staircase that really lands on it |
| `room around … — next to reachable … but blocked (X / headroom)` | a wall block or a low ceiling between the room and a reachable cell | carve a doorway 2 high |
| `room around … — no reachable cell next to it` | sealed room: door or stairs missing | add the door / carve the opening |
| `door …: no floor under …` | the door opens onto a hole | put the floor back |
| `door …: … is <block> — a raised step right at the door` | a path or floor one block too high in front of the door | paths REPLACE the ground block (flat world: y=-61) |
| `door …: … is <block>` | the door opens straight into a wall or furniture | clear the cell in front and behind |
| `door …: not reachable from the entrance` | the door is in an unreachable part | fix the route to it |
| `stair …: blocked: <block> sits on the step` | something stands on a step of a flight | remove it |
| `stair …: no headroom: <block> at …` | ceiling too low above a step (needs 2 air) | carve the ceiling above the last 2-3 steps |
| `full-block step at a door: <block> at … (a path/floor one block too high?)` | a full block to jump onto next to a door | lower it into the ground |
| `N dark spots (mobs can spawn), e.g. …` | enclosed floor with block and sky light 0 | lights (section 4) |

Also in the result: `reached` = reachable/total indoor floor cells, `closed_empty_spaces` = sealed pockets with
nothing inside (attics, voids in thick walls; fine if intended), `details` with every room's contents. Pockets
smaller than `min_room` (default 6 floor cells) are ignored. `ok` must be true before you call a building done.

The check can report a false "closed room" (a wide doorway it did not follow). Confirm with `minecraft_reach` or a
bot walk before changing anything.

## 3. Reachability and a real walk

- `minecraft_reach from:[x,y,z] targets:[[…],[…]]` (or `player:` as the start): can a player walk to each target
  through doors and up stairs? Returns `reachable`, `steps`, `doors` used, and the closest point when not. Nobody
  moves; the whole area must fit ~118k blocks.
- **Real bot walk:** `minecraft_bot action:walk_to pos:[x,y,z]` plans an A* path (around walls, through doors it opens
  and closes, up stairs including spiral ones, drops ≤ 3) within about 60 blocks and walks it. The result lists
  `reached`, the final `position` and each leg (✓ / ✗). A hand-made `path:[…]` is walked in straight lines and does
  NOT climb stairs. Walk the bot up the main staircase of every multi-floor build: a tower wall landing on a stair
  top is the classic bug the picture never shows.

## 4. Numbers that must match

| Check | Call | Expect |
|---|---|---|
| No mob spawns | `script in cu run dark(x1,y1,z1,x2,y2,z2)` | `spots: 0` |
| Nothing left in the way | `script in cu run occupied(x1,y1,z1,x2,y2,z2)` | `count: 0` over a road or a new site |
| Identical copies identical | `script in cu run count(…)` per house | the same counts; a difference = a hole or an extra |
| Water stayed in | `count` of the pool box | water = what you placed |
| A tree really grew | `count` of `*_log` before and after `place feature` | more logs after |
| Entities in place | `l=[]; for(entity_selector('@e[tag=x]'), l+=pos(_)); l` about 5 s after summoning | each inside its box |

Dark spots: add lanterns where they fit the style, or invisible `light[level=15]` blocks on a ~7-block grid at head
height (`execute if block X Y Z air run setblock X Y Z light[level=15]`), then run `dark()` again.

## 5. Pictures (look, but don't trust details)

| `minecraft_screenshot mode:` | Use |
|---|---|
| `iso` (default), `view: se / sw / nw / ne` | 3D overview; box ≤ ~118k blocks (the height is trimmed first) |
| `top` | a map; 6-8 px/block maps a large area |
| `cut_y: <y>` (with iso or top) | cutaway: hides everything above y — use floor + 2 to look into rooms |
| `fpv` | first person from a player's eyes (or `pos` + `yaw`/`pitch`), near range |
| `pov` | far first person (up to 110 blocks) + which builds are in view and under the crosshair |
| `real` | BlueMap render with real textures (needs the BlueMap mod and Chrome or Edge; `update:true` re-renders first; BlueMap can lag ~1 min) |

Renders draw blocks in flat colours without textures: stairs and slabs are drawn as cubes, doors and gates as
see-through panels, fences and panes thin. Display entities are drawn the way players see them: item displays with
their models, block displays with block models, text displays with their text (also right-to-left), using the server
pack (the one `minecraft_pack` built, else its parts) and, when this machine has the Minecraft launcher, the vanilla
client jar for vanilla items, blocks and the font (`client_jar` in `pinkgolem.json`: a path, or `false` = never;
`MC_CLIENT_JAR=off` too). Without the jar, vanilla items become markers and text uses placeholder glyphs. Other
entities are bright cubes (red NPC, blue player, purple painting); markers and interaction boxes are not drawn. So a
picture shows shape, colour and what the displays show; states, door halves and stair directions come from
`minecraft_inspect`. Mobs with models from a server-side model library show as their base mob (lesson 60).

- `minecraft_inspect pos:[x,y,z]` gives the full state (`oak_door[facing=north,half=lower,hinge=left,open=false,…]`).
- `minecraft_inspect from to mode:list` (≤ 8000 blocks) lists every non-air block; `mode:counts` gives totals.
- **Door cells:** inspect the door column: both halves present (`half=lower` / `upper`, same `facing` and `hinge`),
  air in front of and behind the door, the ground in front at ground level (not a block higher).

## 6. Logic, redstone and rides

`minecraft_monitor` records a timeline for up to 50 s: `track` (players with position and vehicle; default your bot),
`blocks: [[x,y,z,'label']]` (full states: a bulb's `lit`, a door's `open`, a rail's `powered`) and
`entities: [['@e[type=minecart,distance=..20,x=0,y=-60,z=0]','carts']]` (count + first position). `changes_only`
(default) keeps only samples where something changed. Start it, then trigger the thing (a redstone-block swap, a
button set to `powered=true`), and read whether the door opened when the cart passed. See [redstone.md](redstone.md)
and [game-logic.md](game-logic.md).

## Final checklist before "done"

1. Every job `done`, `errors: 0` (or each failure understood); `unchanged` ignored.
2. `verify`: only harmless mismatch types; `stray_fluids: 0`.
3. `access.ok: true` (entrance on the last phase, or `minecraft_check_access build:<name>`).
4. `dark()` = 0 for every enclosed space.
5. Screenshots looked at: iso from two sides, plus `cut_y` per floor for interiors.
6. `minecraft_inspect` the door columns and one stair per flight.
7. The bot walked in through the main door and up the main staircase.
8. Water counts match; entities are inside their boxes ~5 s after summoning.
9. Any logic tested once end to end (swap test / fake press + `minecraft_monitor`), test switches reset.
10. `minecraft_map action:add` with the entrance and warps, one `minecraft_notes` line.

## Common mistakes

- Trusting a picture for doors and stairs — verify states with `minecraft_inspect`.
- Reading `verify.ok: false` as failure when every mismatch is `grass_block>dirt`.
- Passing `entrance` on the first phase: the rooms are not finished yet; pass it on the LAST phase.
- "Fixing" a closed room the check reported without a bot walk first.
- A separate fix job after a generator: the next regeneration silently undoes it — put fixes in the generator and
  run the access check again after every regeneration.

## See also
[troubleshooting.md](troubleshooting.md) · [large-builds.md](large-builds.md) · [houses.md](houses.md) ·
[stairs.md](stairs.md) · [water.md](water.md) · [redstone.md](redstone.md) · [coordinates.md](coordinates.md)
