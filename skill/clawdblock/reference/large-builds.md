# Large builds: plan like a contractor, generate, build in phases

Read this before anything bigger than a house: a castle, a park, a campus, a street, an upgrade of an existing big
build. Big builds fail in predictable ways: they collide with something already there, a room ends up sealed, a later
change silently undoes an earlier fix. The workflow below avoids all three and keeps the players informed while it
runs.

## The workflow at a glance

| Step | What | Tools |
|---|---|---|
| 1. Survey | what is there, where it is free, what is empty inside | `minecraft_map`, `minecraft_screenshot mode:"top"`, `minecraft_vision`, `cu occupied / count` |
| 2. Plan | one line in chat listing the parts | `minecraft_chat` |
| 3. Generate | one Python generator, one job file per area / height band | `minecraft_generate` |
| 4. Pre-flight | one call that lists every solid block in your planned cells | `minecraft_run_command` + `save_cells` |
| 5. Preview | pictures of the plan on top of the real world, access check on the plan | `minecraft_preview` |
| 6. Build | phases as background jobs with helpers; write game logic meanwhile | `minecraft_run_command` / `minecraft_generate build:true`, `minecraft_jobs` |
| 7. Verify | verification, access check, screenshots, a real walk | job result, `minecraft_check_access`, `minecraft_bot` |
| 8. Register | map entry, zone, notes | `minecraft_map`, `minecraft_zones`, `minecraft_notes` |

## 1. Survey with numbers, not guesses

- `minecraft_map action:list` / `near` / `get name:"..."` — every indexed build with its box, entrances and owner.
- `minecraft_map action:find_space size:[60,40] near:"..." margin:3` — free buildable ground nobody uses.
- `minecraft_screenshot mode:"top"` over the area (keep the Y range narrow for big areas) — the best map.
- `minecraft_vision mode:"check" target:"box"` or `script in cu run occupied(x1,y1,z1,x2,y2,z2)` — `count:0` = free.
  Include a margin of 2+ blocks around your footprint, and scan G+1..G+6 wherever a path or road will run (older
  decor such as lamp posts hides there). **G** = the ground block (flat world: y=-61).
- Upgrading an existing build: `script in cu run count(...)` **per room** shows which rooms are empty;
  `minecraft_check_access build:"<name>"` lists sealed rooms (free space for new features); and **read the original
  generator** — wall, door, stair and tower coordinates come straight from it.
- `minecraft_people action:suggest name:"..."` when the build is for someone: their likes and style.

Four or five calls give everything a plan needs.

## 2. Plan in one line

Say the plan in chat before you start: *"Plan: stone wall ring with 3 gates, keep with a great hall, 2 round towers,
courtyard garden, moat on the north side — 5 phases."* Show the site with
`script in cu run show(x1,y1,z1,x2,y2,z2,'castle',30)` (a glowing box everyone sees). Then one chat line per phase.
How to talk while you work: `behaving-naturally.md`.

## 3. One generator per project

Everything about the project lives in **one** Python file: coordinates, materials, every area. One `Build` per
area or height band, saved as its own job file, in build order:

| Typical areas, in order | Why this order |
|---|---|
| ground (levelling, foundations, paths in the ground) | everything stands on it |
| shell per wing / floor (walls, floors, stairs, doors) | height bands keep each job small |
| roofs | need the walls |
| interiors / furniture | need finished rooms (`interiors.md`) |
| gardens, trees, plants | trees grow into anything built after them |
| water | always last (`water.md`) |
| entities, displays, NPCs | need the finished space (`entities.md`) |

`Build.save()` splits a long area into `-1`, `-2`, … files (1200 commands each) and deletes stale chunks of the same
name. If you rename an area, delete its old file from `jobs/`.

### Skeleton generator

```python
"""gen_castle.py — stone castle with a keep, two towers and a garden.
    minecraft_generate script:"jobs/gen_castle.py" args:["--at","200,-61,40","--facing","south"]
One job file per area (jobs/castle-<area>.json) + a cells file per area for the pre-flight scan."""
import os, sys
sys.path.insert(0, os.path.join(os.environ.get("CLAWDBLOCK_ROOT", "."), "skill/clawdblock/scripts"))
from mclib import Build, Frame, parse_args
import parts as P

a = parse_args({"name": "castle"})
f = Frame(a.x, a.y, a.z, a.facing)          # origin = front-left corner at ground level
W, D = 40, 30                                # local width (i) and depth (k)
AREAS = {}                                   # area name -> Build, in build order

def area(name):
    AREAS[name] = Build()
    return AREAS[name]

# 1. ground: fresh grass (fills old pits), paths IN the ground
g = area("ground")
f.box(g, (0, -2, 0), (W, -1, D), "dirt")
f.box(g, (0, 0, 0), (W, 0, D), "grass_block")
P.path(g, [f.p(i, 0, k)[0::2] for i in range(18, 21) for k in range(0, 7)], a.y, "gravel")

# 2. keep: walls, floor, ceiling, door (later writes win inside one Build)
h = area("keep")
P.room(h, f, 8, 6, 30, 20, 0, 6, "stone_bricks", floor="spruce_planks", ceiling="spruce_planks")
P.doorway(h, f, 18, 1, 6, "spruce", double=True)

# 3. roof on top of the walls (walls end at 6, ceiling at 7)
r = area("roof")
P.gable_roof(r, f, 8, 6, 30, 20, 8, stairs="dark_oak_stairs", full="dark_oak_planks", ridge="i")

# 4. garden after the buildings
v = area("garden")
# ... P.flower_bed, P.trees, P.lamp_post ...

# 5. water last
w = area("water")
# ... P.pond / P.pool / P.fountain ...

files = []
for name, b in AREAS.items():
    if b.v or b.raw:
        files += b.save(f"{a.name}-{name}")
        b.save_cells(f"{a.name}_{name}")
lo, hi = f.world_box((0, 0, 0), (W, 16, D))
ent = f.p(18, 1, 2)
print(f"box {lo} -> {hi}; entrance {[ent[0] + 0.5, ent[1], ent[2] + 0.5]}; files {files}")
```

Print the box and the entrance: you need them for the preview, the access check and the map entry. Frames and local
coordinates are explained in `coordinates.md`; `houses.md`, `roofs.md` and `stairs.md` cover the parts.

## 4. The one-call pre-flight collision scan

`b.save_cells(name)` writes every planned non-air cell as `[x, y, z, block]` to the `cu` app's data folder
(`cu.data/<name>_cells.json`). It only writes when the generator runs through `minecraft_generate`, which tells it
where that folder is. Then one call lists every solid block already standing in your planned cells, grouped:

```
minecraft_run_command command:"script in cu run nat(b) -> str(b)~'^(grass_block|dirt|coarse_dirt|sand|gravel|short_grass|tall_grass|fern|bush|dandelion|poppy|snow)$'; l=read_file('castle_keep_cells','json'); m={}; for(l, b=block(_:0,_:1,_:2); if(b!='air' && !nat(b), k=str('%s>%s',_:3,b); m:k=if(m:k,m:k+1,1))); m"
```

The result reads `planned>existing: count`. Intentional overlaps (your window in an existing wall, a ladder through
a ceiling) are easy to tell apart from real collisions (a turret wall inside your planned library). Run it with
**`minecraft_run_command`** (`script in cu run …`): `read_file` only works inside the `cu` app, and a plain
`minecraft_scarpet` expression runs outside it and reads nothing.

## 5. Preview the plan

```
minecraft_preview commands_files:["jobs/castle-ground.json","jobs/castle-keep.json","jobs/castle-roof.json"] mode:"all"
minecraft_preview commands_files:[...] cut_y:-58          # a cutaway through the ground floor
minecraft_preview commands_files:[...] entrance:[x,y,z]    # + access check on the plan
```

Nothing is placed. `overlay` (on by default) draws the plan on top of what really stands there. Fix the generator
until the pictures look right and the access check is clean. For a brand-new large build on empty land, show the
preview picture to the people who asked for it once, before the first block.

## 6. Build in phases

```
minecraft_run_command commands_files:["jobs/castle-ground.json","jobs/castle-keep.json"] background:true
    label:"castle ground + keep" helpers:3 keep_helpers:true
minecraft_jobs action:wait id:<id> timeout_seconds:50
```

- 2-3 files per background job with `helpers:3` — roughly ten seconds per phase, one chat line per phase.
- Or let the generator queue everything: `minecraft_generate script:"jobs/gen_castle.py" args:[...] build:true
  files:["castle-*"] helpers:3 entrance:[x,y,z]`.
- Pass `entrance:[x,y,z]` (feet position just outside the main door) on the **last** phase: the access report comes
  back in the job result.
- **While a job runs, write the game logic** (scarpet app, NPC dialogue, buttons — `game-logic.md`), then wait.
- Inside someone else's protected zone: `minecraft_zones action:claim name:"..."` first (only when they asked).
- Every job is undoable: `minecraft_undo match:"castle keep"`.

## 7. Verify

The job result carries the verification and the access check. Read both:

| Field | Meaning |
|---|---|
| `mismatches`, `by_type` | `want>got` pairs; `grass_block>dirt` (grass under a placed block) and "Could not set" on air are harmless |
| `stray_fluids`, `flowing_water` | see `water.md` |
| `access.problems` | unreachable rooms, doors blocked on one side, stairs into walls, full-block steps at doors, dark spots |

Then: an iso screenshot plus `cut_y` per floor, `script in cu run dark(...)` = 0 for enclosed spaces, entity positions,
and a real walk: `minecraft_bot action:walk_to` up every main staircase. If the access check reports a "closed room"
that looks open, confirm with a bot walk before changing anything. Full checklist: `verification.md`.

## Fixes go INTO the generator

A fix written as a separate "fix" job gets silently undone the next time the generator runs — a set of towers was
sealed again exactly this way. Change the generator, regenerate, rebuild the affected area, and run
`minecraft_check_access` again after every regeneration.

## 8. Register the build

1. `minecraft_map action:add name:"Castle" aliases:[...] from:[...] to:[...] entrances:[[x,y,z,"main gate"]]
   owner:"<player>" builder:"<your bot>" notes:"generator jobs/gen_castle.py"`.
2. Finished builds become zones automatically; for a build made for someone, add a named zone with them as owner:
   `minecraft_zones action:add name:"Castle" owner:"<player>" builder:"<your bot>" from:[...] to:[...] note:"..."`.
3. `minecraft_notes action:add section:"build" text:"..."` (what, where, how to get in, generator, apps) and one line
   per lesson (`section:"lesson"`).
4. `minecraft_helpers action:dismiss`, then tell the players where it is.

## Common mistakes

- Building from memory instead of surveying → a new road through an old lamp post.
- Several generators for one project → coordinates drift apart; fixes get lost.
- One giant job file → slow, no progress per phase, hard to undo one part.
- Trees before walls, water before basins, NPCs before rooms.
- A separate fix job → undone by the next regeneration.
- Saying "done" before the access check is ok and the bot has walked the stairs.

## See also

`coordinates.md` · `houses.md` · `interiors.md` · `landscaping.md` · `water.md` · `round-and-tall.md` ·
`verification.md` · `game-logic.md` · `behaving-naturally.md` · `troubleshooting.md`
