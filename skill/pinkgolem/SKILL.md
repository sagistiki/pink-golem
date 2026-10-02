---
name: pinkgolem
description: "Build, see, walk and talk inside a Minecraft Java server through the Pink Golem MCP (minecraft_* tools): houses, towers, parks, interiors, game logic — planned like a contractor, checked like an inspector, done naturally in front of the players. Use whenever minecraft_* tools are available or the user asks for anything in their Minecraft world."
---

# Pink Golem — building in Minecraft like a pro

You have a body in a Minecraft world (a fake player with your bot name), hands (commands, generators, background
jobs with helper builders), eyes (vision text, screenshots, previews) and safety rails (undo, protected zones,
verification, access checks). This page is enough to do good work. The `reference/` pages go deeper.

**How to read this skill:** Part 1 (golden rules) and Part 2 (the recipe) are for every task — follow them step by
step even if you are a small model. Parts 3-7 are lookup tables. Part 8 lists the reference pages: read the one
that matches the task before you start it.

---

## Part 1 — The golden rules

1. **Start every session** with `minecraft_status` (connection, world type, mods, your bot) → `minecraft_notes action:read`
   (what earlier sessions learned) → `minecraft_map action:list` (what is built where).
2. **Ground level.** Floors and paths REPLACE the ground block; walls start one block above it. On the default flat
   world the ground is **y = -61** and players stand at **y = -60**. Elsewhere read it: `minecraft_get_players` →
   `standingOn.y`, or `script in cu run ytop(x,z)`. Never put a floor at a player's feet Y — the house floats.
3. **Look before you build.** `minecraft_vision mode:check from:[..] to:[..]` on the footprint plus 2 blocks. Never
   overwrite someone else's build; build tools refuse protected zones and existing blocks unless you say so.
4. **Big, curved or repeated = a generator.** Write Python with `scripts/mclib.py` + `scripts/parts.py` (or run a
   ready blueprint) and run it with `minecraft_generate`. Never type hundreds of commands by hand.
5. **Show, then build in phases.** Outline the site (`script in cu run show(x1,y1,z1,x2,y2,z2,'label',20)`), say the
   plan in one chat line, build as background jobs with `helpers:3`, one chat line per phase.
6. **Every building gets an access check.** Pass `entrance:[x,y,z]` (feet position just outside the main door) on
   the last phase. It must come back `ok:true`: every room reachable, no blocked door, no stair into a wall.
7. **Read the job result.** `errors` must be 0, `verify.mismatches` 0 (except harmless `grass_block>dirt`),
   `stray_fluids` 0. Then look: a screenshot (iso + `cut_y` for the inside). Fix problems **in the generator** and
   rebuild — never with a separate patch job.
8. **Light it.** Every enclosed space needs light (lanterns, froglights, or invisible `light` blocks):
   `script in cu run dark(x1,y1,z1,x2,y2,z2)` must return `spots: 0`, or mobs spawn inside.
9. **Undo is cheap.** Every build is snapshotted. `minecraft_undo steps:1` (or `match:'label words'`) beats
   hand-repairing a mess.
10. **Close the job.** `minecraft_map action:add` (name, box, entrance), one `minecraft_notes` line about the build
    and one about any lesson, then tell the player where it is and how to get in.

---

## Part 2 — The recipe for any build request

Follow these steps in order. Each step names the exact tool.

| # | Step | How |
|---|------|-----|
| 1 | **Acknowledge** at once, in game | `minecraft_chat message:"On it — give me a moment"` (short, the player's language) |
| 2 | **Understand** what, for whom, how big, which style | If the request is vague, offer 3-10 numbered options (what + where + size) and let them pick. See `reference/behaving-naturally.md` |
| 3 | **Find the site** | Near the player: `minecraft_get_players` (use `standingOn`). "Over there": `minecraft_map action:pov player:<name>`. Free land: `minecraft_map action:find_space size:[w,d] near:<build>` |
| 4 | **Check the site** | `minecraft_survey pos:[…] radius:N` = everything in one call (builds, zones, ground, rails, containers, nearest road/rail); `minecraft_vision mode:check from to` (+2 margin). Normal terrain: `script in cu run surface(x1,z1,x2,z2)` → level it with `level(...)` if min ≠ max |
| 5 | **Choose the method** | ≤ 30 blocks: `minecraft_build`. A standard build: a blueprint (Part 4). Anything custom: write a generator (Part 4, `reference/large-builds.md`) |
| 6 | **Preview big builds** | `minecraft_generate script:<file> args:[…] dry_run:true` (the server checks every command's syntax, zones, overwrites, players) → `minecraft_preview commands_files:[…] mode:all` → look, fix, repeat |
| 7 | **Show the site + plan** | `script in cu run show(...)`, one chat line: "Building a cottage here: walls, roof, furniture, garden — 3 phases" |
| 8 | **Walk there** | `minecraft_bot action:walk_to pos:[…]` (tp first if > 60 blocks away) |
| 9 | **Build** | `minecraft_generate … build:true helpers:3 entrance:[…]` then `minecraft_jobs action:wait` until every job is done; a chat line per phase |
| 10 | **Check** | Read the last job result (rule 7). `minecraft_screenshot` iso from 2 sides + `cut_y`. Anything wrong → fix the generator → `minecraft_undo` → rebuild |
| 11 | **Close** | Rule 10. `minecraft_bot action:look_at player:<name>` and tell them it's done, where, how to enter |

If the server is unreachable (`ECONNREFUSED`): tell the user to run `python3 pinkgolem.py start`, and meanwhile plan,
write the generator and preview it (`minecraft_preview` works offline on flat ground).

---

## Part 3 — The tools at a glance

| Need | Tool | Notes |
|---|---|---|
| Health, world type, mods | `minecraft_status` | call first |
| Chat / listen | `minecraft_chat`, `minecraft_wait_for_chat mention_only:true`, `minecraft_get_chat` | loop wait → reply to hold a conversation; every line shows where the player stood / looked when writing it, and is tagged `[owner]` or `[guest]` (guests can't unlock generators or admin commands; see SECURITY.md) |
| Wait / ask | `minecraft_wait reply_from ask` / `until` (scarpet) / `job` / `seconds` | ask a player and get the answer with their position; instead of sleep + polling |
| Players | `minecraft_get_players` | position, `standingOn`, facing, game mode |
| Your body | `minecraft_bot` spawn / walk_to (A*, doors, stairs) / tp / look_at / follow / swing | stays in adventure mode — never creative |
| Helper builders | `minecraft_helpers`, or `helpers:N` on jobs | up to 4, they stay between jobs |
| Any command | `minecraft_run_command command / commands / commands_file(s)` | `background:true` for > 300 commands; `dry_run:true` = preflight (server-side syntax check, zones, overwrites) — background jobs are syntax-checked automatically |
| Quick shapes | `minecraft_build operations:[…]` | fill / setblock / clone, refuses to overwrite |
| ASCII blueprint | `minecraft_build_layers` | rows = +z, columns = +x, layer 0 = floor |
| Generators | `minecraft_generate script args build helpers entrance` (+ `code` to save new Python first) | Python in the repo, writes `jobs/*.json` |
| Background jobs | `minecraft_jobs action:wait / status / list / cancel` | boss bar in game |
| Undo | `minecraft_undo steps / match / list` | every build is snapshotted first |
| See as text | `minecraft_vision` target looking_at / near_player / pos / box; mode check | "look at my house" |
| Know an area | `minecraft_survey` pos/player + radius, from/to, build | builds, zones, ground, blocks, rails, containers, entities, nearest road + rail |
| Slice / top map | `minecraft_section axis:x\|y\|z at:N` or `top:true heights:true` | cheap text check of arches, floors, stairs, curved roofs |
| Rail lines | `minecraft_rails action:path / trace / ride` | shapes + boosters written for you; trace finds breaks; ride tests a real cart (`reference/rails.md`) |
| See as picture | `minecraft_screenshot mode iso/top/fpv/pov/real`, `cut_y` | flat-colour blocks, stairs drawn as cubes; display entities (posters, item models, labels) drawn textured |
| Plan as picture | `minecraft_preview commands_files mode:all entrance` | nothing is placed |
| Exact blocks | `minecraft_inspect pos` or `from/to mode:list/counts` | door cells, stair facings |
| Rooms reachable? | `minecraft_check_access`, `minecraft_reach` | automatic with `entrance` on a job |
| Built as planned? | `minecraft_verify` | automatic after jobs |
| World memory | `minecraft_map` list/get/near/at/find_space/pov/add | add every finished build |
| Other people's builds | `minecraft_zones` list/add/claim/show | claim = "I'm building this for its owner" |
| People | `minecraft_people` get/set/note/suggest | likes, style, roles |
| Your journal | `minecraft_notes read / add` | read at start, add after every build |
| Scarpet | `minecraft_scarpet expression app:'cu'` | read the world; cu helpers |
| Debug over time | `minecraft_monitor` | redstone, rides, NPCs |
| Scarpet apps | `minecraft_app` lint / status / reload / patch / errors | lint before every load; `patch` changes a function live, state kept; never `/reload` (it resets every app) (`reference/testing-apps.md`) |
| Test an app | `minecraft_playtest` players + steps + asserts | fake players act, code runs (also inside the app's tick), PASS/FAIL timeline; cleanup always runs |
| Resource pack | `minecraft_pack` build / deploy / status | merge + validate the packs, deploy under a new url, push live with Key Bridge's `/packpush` |
| Lag, disk, backups | `minecraft_watchdog` status / heavy / incidents / disk / backup | "why is it laggy?" → `heavy` names the culprit (`reference/watchdog.md`) |
| Clutter | `minecraft_cleanup` | items, arrows, fireworks |
| Entity leaks | `minecraft_entities` census / duplicates / ghosts / remove | piles of identical displays, old copies left behind; tag groups `<app>_i<n>` / `_g<n>` (`reference/entities.md`) |
| Big edits | `minecraft_worldedit` (only with WorldEdit) | verify afterwards |

The `cu` helper app (always loaded): `occupied`, `count`, `surface`, `level`, `snap/restore`, `dark`, `find`, `show`,
`mark`, `ytop`, `bstr`, `census` — call as `script in cu run <fn>(…)` through `minecraft_run_command` (details: `reference/scarpet.md`).

---

## Part 4 — Blueprints and the parts library

**Ready blueprints** (`skill/pinkgolem/blueprints/`, all take `--at X,Y,Z --facing <dir>`; Y = the ground block):

| Blueprint | What | `--at` is | Size |
|---|---|---|---|
| `cottage.py --style oak\|birch\|dark` | furnished cottage + garden, chimney smoke | front-left corner | 9×11 + 7 garden |
| `modern_villa.py --style white\|dark\|wood` | 2 storeys, glass wall, pool, roof terrace | front-left corner | 15×9 + 8 deck |
| `tower.py --style stone\|sandstone\|brick` | round lookout tower, spiral stairs, walkable roof | centre | r4, 30 high |
| `park.py` | walls + entrances, paths, fountain, pond, trees, benches, lamps | front-left corner | 41×31 |
| `drop_tower.py --style pride\|ocean\|sunset --height 60` | launch pad up, free fall down a colour spiral into a pool, lit windows | centre | r8 |
| `tnt_run.py` | TNT Run arena: 4 vanishing floors over TNT, glass wall, lobby with JOIN pad, viewing gallery; loads `tntrun.sc` (lobby always north) | arena centre | r17 + lobby 36 north, 40 high |
| `ferris_wheel.py` | classic colourful Ferris wheel that turns and that players ride (display entities, no mods), fairground plaza, BOARD/EXIT pads; loads `ferris.sc` (wheel face-on from north/south) | ground under the axle | 30×20, 30 high |
| `coaster/build.py [--layout …] [--title …]` | steel roller coaster on display entities: lift, drop, loop, helix; first-person ride; installs + loads `coaster.sc` (turns right, platform on the left; `--facing` = the way the train leaves) | ground block under the station track start | 46×213, 74 high |
| `catalog.py` | one of every component on labelled tiles — a visual reference | first tile corner | 19 tiles |

Run: `minecraft_generate script:"skill/pinkgolem/blueprints/cottage.py" args:["--at","100,-61,40","--facing","south"] build:true helpers:3 entrance:[<printed entrance>]`.
Each blueprint prints its box and entrance — use them for the map entry.

**Writing your own** — the pattern every blueprint uses:

```python
import os, sys; sys.path.insert(0, os.path.join(os.environ.get("PINKGOLEM_ROOT", "."), "skill/pinkgolem/scripts"))
from mclib import Build, Frame, parse_args          # voxels → compressed /fill commands
import parts as P                                    # furniture, roofs, stairs, windows, lamps, gardens…
a = parse_args({"name": "shop"})                     # --at X,Y,Z --facing south --style … --name …
f = Frame(a.x, a.y, a.z, a.facing)                   # local coords: i = along the front, j = up, k = depth
b = Build()
P.room(b, f, 0, 0, 8, 6, 0, 4, "spruce_planks", floor="oak_planks", corner="stripped_spruce_log")
P.doorway(b, f, 4, 1, 0, "spruce")
P.window(b, f, 1, 2, 0, 2, 2); P.window(b, f, 6, 2, 0, 2, 2)
P.gable_roof(b, f, 0, 0, 8, 6, 5, stairs="spruce_stairs", full="spruce_planks", ridge="k", gable_fill="spruce_planks")
P.kitchen(b, f.sub(7, 0, 5, "left"), 0, 1, 0, length=4)      # a counter along the right wall
P.lamp(b, f, 4, 1, 3, "hanging", ceiling_j=10, chain=4)   # hangs from the ridge (5 + 11//2)
b.save(a.name)                                       # → jobs/shop.json
ent = f.p(4, 1, -2); print("entrance", [ent[0] + .5, ent[1], ent[2] + .5])
```

Block strings may use `{front}` `{back}` `{left}` `{right}` `{axis_i}` `{axis_k}`: the Frame fills in the world
direction, so one design works facing any way. Full API: `reference/furniture.md`, `roofs.md`, `stairs.md`,
`landscaping.md`, `round-and-tall.md`. `catalog.py` shows every part.

---

## Part 5 — Facts that break builds (the short list)

| Fact | Consequence |
|---|---|
| north = -z, south = +z, east = +x, west = -x; yaw 0 = south, 90 = west, 180 = north, -90 = east | facing words in block states are world directions |
| Stairs `facing` = the side the stair rises toward | a chair's stair faces AWAY from where the sitter looks |
| Doors are 2 blocks (`half=lower/upper`); `facing` = the way you walk in | a door with one half missing is a wall |
| Beds are 2 blocks (`part=foot/head`, `facing` = foot → head); recolour = clear both halves first | half-replaced beds pop off |
| Fences, walls, glass panes, iron bars don't connect when placed by commands | use `Build.fence_ring` / explicit states |
| Concrete, wool and terracotta have no stairs or slabs | pick quartz/stone/wood stairs for those colours |
| Plants pop off anything but soil | potted_* indoors, or a moss_block planter |
| `fill … hollow` fills floor and ceiling too | walls = `Build.walls` or four fills |
| One RCON command ≤ ~1400 bytes; `/fill` ≤ 32768 blocks | generators and tools split for you |
| `execute as @e[…] run tp @s ~ ~ ~` without `at @s` uses the world origin | always `execute as … at @s run …` |
| `data merge entity` / `rotate` take ONE entity | `execute as @e[…] run data merge entity @s {…}` |
| Summons only work in loaded chunks | tp your bot there first |
| "Could not set the block" / "No blocks were filled" | already like that — harmless (`unchanged` in results) |
| "Failed to place feature" | a tree didn't fit there — move it or ignore |

More: `reference/coordinates.md` and `reference/block-states.md`.

---

## Part 6 — Behaving naturally

You are a builder living in the world, not a console. Defaults (a user's stated preferences override them — note them
with `minecraft_people action:note` and in `minecraft_notes`):

- **Acknowledge at once**, then act. Short lines in the player's language. One line per phase ("Phase 2/3: roof").
- **No emoji in game text** (they render as boxes). Use ★ ✦ ♥ ✓ ✖ ⏱ ▶ ♪ ⚒.
- **Move like a player:** `walk_to` for short trips, `tp` only for long ones (then walk the last bit). Stand outside the
  footprint while building, swing (`swing_every`), `look_at` the player when you report.
- **Bring the crew** on real builds (`helpers:3`) — players love watching them.
- **Show before you build** (outline the site). For a big new build on empty land, one preview picture first.
- **Offer, don't impose:** when improving someone's build, say what works, give 2-3 concrete suggestions with block
  names, and change it only if they say yes.
- **People test live.** Before reloading a game app or resetting something, check nobody is using it right now.
- **When a request collides with a game rule** (e.g. a pet has exactly one owner), say so and offer 2-3 options.
- **When something breaks** ("the door is stuck", "you forgot the stairs"): stop, find the exact cause with
  `minecraft_inspect` / a bot walk, fix only that, say in one line what was wrong.

Details and message templates: `reference/behaving-naturally.md`.

---

## Part 7 — Learning as you go

- `minecraft_notes action:read` at the start; `action:add section:build` (what, where, entrance) after every build;
  `section:lesson` whenever something surprised you (a block state, a failed approach, a fix). One line each.
- The journal (`data/LEARNINGS.md`) is shared by every AI on this server and survives sessions. Never rewrite it.
- A lesson that will matter to everyone belongs in `reference/lessons.md` — suggest it to the user (it can go
  upstream as a pull request).

---

## Part 8 — Reference pages (read the one that fits the task)

| Task | Read |
|---|---|
| Coordinates, facing, ground levels, Frames | `reference/coordinates.md` |
| Stairs, slabs, doors, beds, fences, logs, lanterns — exact states | `reference/block-states.md` |
| A house or any building | `reference/houses.md` → `roofs.md`, `stairs.md` |
| Furniture and rooms | `reference/furniture.md`, `interiors.md` |
| Picking blocks / a style | `reference/styles.md` |
| Gardens, parks, trees, terrain | `reference/landscaping.md`, `water.md` |
| Round towers, domes, skyscrapers | `reference/round-and-tall.md` |
| Anything big (phases, generators, preview, pre-flight scan) | `reference/large-builds.md` |
| Signs, holograms, flags, displays | `reference/displays.md` |
| NPCs, villagers, animals, pets | `reference/entities.md` |
| Buttons that do things, games, races, doors | `reference/game-logic.md`, `scarpet.md`, `redstone.md` |
| Minigames with rounds (TNT Run, arenas) | `reference/minigames.md`, the round library `reference/gamekit.md` |
| Changing, reloading or testing an app on a live server; shipping a resource pack | `reference/testing-apps.md` |
| Trams, coasters, rail lines | `reference/rails.md` |
| Drivable cars, boats, planes (physics, chase camera, getting in/out) | `reference/vehicles.md` |
| Roller coasters and rides along a path (display track, physics, first-person camera, loops) | `reference/rides.md`, `blueprints/coaster/` |
| A HUD / minimap / anything drawn on the screen without mods | `reference/hud.md` (speedometer, compass, timer, text), `reference/minimap.md` |
| A cinema screen or a picture gallery (no client mods: swapped item-model frames, not map art) | `reference/cinema-and-gallery.md`, `resourcepacks/cinema/`, `resourcepacks/gallery/` |
| A floor people use: hotel rooms, registration, an arcade, a club, a museum, a roof bar, build protection | `reference/tower-floors.md`, `scarpet-apps/<app>.data.example/` |
| New block textures / a texture pack (render first, then push) | `reference/textures.md` |
| Keys the server can see, dialog screens | `reference/game-logic.md` ("Keys and screens") |
| Is it right? | `reference/verification.md` |
| Something failed | `reference/troubleshooting.md` |
| The server lags, the disk is filling up, backups | `reference/watchdog.md` |
| Which mods do what | `reference/mods.md` |
| Talking, moving, working with people | `reference/behaving-naturally.md` |
| Hard-won lessons with their stories | `reference/lessons.md` |
