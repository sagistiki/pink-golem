# Houses

Read this before you design or build any house, cabin or villa, and when someone asks you to critique or improve
one. It covers size, heights, walls with depth, windows, doors, roofs, interiors, light, and the two example
generators (`blueprints/cottage.py`, `blueprints/modern_villa.py`) you can copy.

## 1. Size and proportions

| House | Outer footprint | Storeys | Roof |
|---|---|---|---|
| Hut, shed, stand | 5×5 – 7×7 | 1 | gable or flat |
| Cottage | 7×9 – 9×11 | 1 + vaulted roof | gable, ridge front-to-back |
| Family house | 11×9 – 15×11 | 2 | gable or hip |
| Modern villa | 13×9 + offset upper box | 2 | flat with overhang |

- **Make it a rectangle, not a square**: a long side about 1.2–1.6× the short side reads as a house; a perfect
  cube reads as a box.
- **Odd widths** (7, 9, 11) give a real centre cell for the door and the roof ridge.
- **Break up big volumes**: a wing, a porch, an upper box that overhangs the lower one. One plain box of 15×15
  looks like a warehouse.

## 2. Heights — where everything goes

The floor **replaces** the ground block (flat world: y=-61). On normal terrain read the ground with
`standingOn.y` from `minecraft_get_players`, `script in cu run ytop(x,z)`, or `script in cu run surface(x1,z1,x2,z2)`
and flatten with `level(...)` first (see `coordinates.md`).

| Level (Frame `j`) | Flat world y | What |
|---|---|---|
| 0 | -61 | ground floor — replaces the grass; paths and door steps are here too |
| 1 | -60 | first wall row (base course), furniture, door lower half |
| 1 – 4 | -60 … -57 | ground-floor walls: 4 high = 4 blocks of air under the ceiling |
| 5 | -56 | ceiling = upper floor |
| 6 – 9 | -55 … -52 | upper walls |
| wall top + 1 | | first roof row |

- **A storey is 5 blocks from floor to floor** (floor + 4 wall rows). 3-high rooms feel cramped; a player
  jumping hits a 2-high ceiling.
- A floor laid at feet level makes the house float and puts a step at the door (the access check reports it as a
  "full-block step at a door").

## 3. Walls with depth and texture

A flat single-block wall is the most common reason a build looks amateur. Add at least two of these:

| Element | How | Example blocks |
|---|---|---|
| Base course | the first wall row (`j=1`) in a heavier block | `stone_bricks`, `cobblestone`, `mossy_cobblestone` |
| Log frame | corner posts `axis=y`, plus a post every 4–6 blocks | `stripped_spruce_log[axis=y]`, `dark_oak_log[axis=y]` |
| Beams | a log row under the roof, `axis` along the wall | `stripped_spruce_log[axis={axis_i}]` on front/back, `{axis_k}` on the sides |
| Pillars | columns one block in front of the wall | `quartz_pillar`, `stripped_oak_log` |
| Window depth | sill outside, shutters | `parts.window(..., sill=..., shutters=...)` |
| Band between storeys | a contrasting row at the floor level | `black_concrete` on a white villa |

The frame should be **darker or stronger than the infill** (logs on plaster, stone under planks): the eye reads the
structure first. For more depth put posts or pillars one block *outside* the wall line so they cast shadows.

## 4. Windows

- **Rhythm**: windows at even spacing, symmetric around the door. Leave the corners solid (posts go there).
- Standard window: 2 wide × 2 high at `j=2..3`. One-wide slits for towers and barns; full-height glass bands for
  modern houses.
- **Line up** upper-floor windows over the ground-floor ones.
- `parts.window(b, f, i, j, k, width=2, height=2, along="i", glass="glass_pane", sill=None, shutters=None)`:
  `along="i"` for a front/back wall, `"k"` for a side wall. Panes get explicit connections — **panes, fences and
  walls placed by commands never connect by themselves**; a lone pane is a thin post.
- In `minecraft_build_layers` use full `glass` (or panes with explicit states such as
  `glass_pane[east=true,west=true]`).

## 5. Doors and the door-cell rule

- Put the main door on the front, centred or on a clear axis, facing the street or path.
- `parts.doorway(b, f, i, j, k, material="oak", into="back", double=False, frame=None, step_block=None)` carves the
  opening, then places both halves. `j` = floor + 1. `into` = the direction you walk when you go in.
- Plain commands: `oak_door[facing=<direction you walk in>,half=lower,hinge=left]` plus the same with `half=upper`
  one block above. Both halves, same `facing` and `hinge`.
- **The door-cell rule**: the two door cells, the cell in front of the door and the cell behind it stay clear, and
  the ground outside is at the ground level (the path replaces the ground block). A top slab in the ground layer
  (`cobblestone_slab[type=top]`) makes a flush step.
- After furnishing, **inspect the door column** (`minecraft_inspect from:[x,y,z] to:[x,y+1,z] mode:list`). A
  furniture fill on the wall line once replaced a door. Pictures draw doors unreliably — check the block states.

## 6. Roofs

| Plan | Roof | Function |
|---|---|---|
| Cottage, gable toward the street | gable, `ridge="k"` | `parts.gable_roof` |
| Long house, eaves toward the street | gable, `ridge="i"` | `parts.gable_roof` |
| Square house | hip | `parts.hip_roof` |
| Modern | flat + overhang + trim | `parts.flat_roof` |
| Round tower | stepped cone | `parts.cone_roof` |

The roof starts **one level above the wall top**, with an overhang of 1. Details, pitch and pitfalls: `roofs.md`.

## 7. Interior = footprint minus the wall ring

Walls at `i=0` and `i=W` → the room is `i=1 … W-1`. Write the interior range down **before** any furniture fill,
and keep a walking line from the door to every room (`interiors.md`). Furniture functions: `furniture.md`.

## 8. Light

Mobs spawn where block light and sky light are both 0. Every closed room, attic and tower top needs light:
hanging lanterns from the ridge, flush ceiling lights (`pearlescent_froglight`, `sea_lantern`), or invisible
`light[level=15]` blocks. Check with `script in cu run dark(x1,y1,z1,x2,y2,z2)` — `spots` must be 0.

## 9. The example generators

Both take `--at X,Y,Z` (front-left ground corner; Y = the ground block) and `--facing` (the side the front faces),
and write three job files so each phase can be previewed and built on its own.

```
minecraft_generate script:"skill/pinkgolem/blueprints/cottage.py" args:["--at","100,-61,40","--facing","south"]
minecraft_preview commands_files:["jobs/cottage-1.json","jobs/cottage-2.json","jobs/cottage-3.json"] entrance:[...]
minecraft_generate script:"skill/pinkgolem/blueprints/cottage.py" args:[...] build:true helpers:3 entrance:[...]
```

**`cottage.py`** (9×11 outer walls, `W, D, H = 8, 10, 4`, styles `oak | birch | dark`):

1. **`cottage-1` shell** — `f = Frame(x, y, z, facing)`; floor box at `j=0`; walls `j=1..4`; base course over
   `j=1`; log beams at `j=4` on all four walls (axis via `{axis_i}`/`{axis_k}`); posts at the corners and mid-sides;
   `f.clear` of the inside up to `H+5` (vaulted: the roof is the ceiling); five `P.window` calls; `P.doorway` at
   `i=4`; `P.gable_roof(..., ridge="k", gable_fill=wall)` which returns the ridge level `top`; a row of upside-down
   stairs over the door as a canopy.
2. **`cottage-2` interior** — fireplace on the back wall with a chimney to `top+2`, a sofa facing the fire, rug, bed
   in a back corner, candles, wardrobe, a kitchen along the right wall via `f.sub(W-1, 0, 5, "left")`, bookshelves
   along the left wall via `f.sub(1, 0, 2, "right")`, a dining set left of the entry **so the line `i=4` from the
   door stays free**, potted plants, two hanging lanterns with chains down from the ridge.
3. **`cottage-3` garden** — a 3-wide `dirt_path` replacing the ground in front, a flush slab step, lamp posts,
   flower beds, two trees.
4. It prints the build box and the **entrance** (feet position two blocks outside the door) for the access check.

**`modern_villa.py`** (ground floor 13×9, upper box `i=4..14` cantilevered 2 blocks past the right wall):

1. **`villa-1` structure** — white box, a full-height glass wall toward the pool, the ceiling slab at `j=5` that is
   also the upper floor, upper walls `j=6..9` with glass bands, `P.flat_roof(..., overhang=1, trim=...)`, a black
   band between the storeys, a glass-pane railing on the roof terrace made with `fence_ring` (explicit
   connections), a railing around the stairwell, the front door under the cantilever, a door from the upper floor
   to the terrace, froglights set flush into the ceilings.
2. **`villa-2` interior** — `P.straight_stairs(..., rise=H+1, going="back", support=None)` from the entrance hall
   (its headroom carving opens the stairwell in the upper floor); sofa, rug, glass table, kitchen, island,
   plants; upstairs two beds, candles, wardrobe, desk and chair.
3. **`villa-3` pool + deck** — the deck replaces the ground, the pool is dug in, loungers, modern lamp posts.
   **Water is in the last job.**
4. It prints the entrance and the upper landing — use both for `minecraft_reach` (`stairs.md`).

Copy one of them into `jobs/` for a new design: keep the structure (styles dict, `Frame`, one `Build` per phase,
`parts` calls, three saves, entrance print) and change the numbers.

## 10. Without a generator: a 7×7 gabled house for `minecraft_build_layers`

9×9 grid including a 1-block roof overhang. `origin` = `[west wall x - 1, ground y, north wall z - 1]`
(flat world: y=-61). The door is on the north wall; the ridge runs east–west.

```json
{"layers": [
 [".........",".BBBBBBB.",".BPPPPPB.",".BPPPPPB.",".BPPPPPB.",".BPPPPPB.",".BPPPPPB.",".BBBBBBB.","........."],
 [".........",".LWWDWWL.",".W.....W.",".W.....W.",".W.....W.",".W.....W.",".W.....W.",".LWWWWWL.","........."],
 [".........",".LGWUWGL.",".W.....W.",".G.....G.",".W.....W.",".G.....G.",".W.....W.",".LWGWGWL.","........."],
 [".........",".LWWWWWL.",".W.....W.",".W.....W.",".W.....W.",".W.....W.",".W.....W.",".LWWWWWL.","........."],
 ["nnnnnnnnn",".RRRRRRR.",".W.....W.",".W.....W.",".W.....W.",".W.....W.",".W.....W.",".RRRRRRR.","vvvvvvvvv"],
 [".........","nnnnnnnnn",".RRRRRRR.",".W.....W.",".G.....G.",".W.....W.",".RRRRRRR.","vvvvvvvvv","........."],
 [".........",".........","nnnnnnnnn",".RRRRRRR.",".W.....W.",".RRRRRRR.","vvvvvvvvv",".........","........."],
 [".........",".........",".........","nnnnnnnnn",".RRRRRRR.","vvvvvvvvv",".........",".........","........."],
 [".........",".........",".........",".........","hhhhhhhhh",".........",".........",".........","........."]],
 "legend": {"B":"cobblestone","P":"oak_planks","L":"stripped_spruce_log","W":"white_terracotta","G":"glass",
  "D":"oak_door[facing=south,half=lower,hinge=left]","U":"oak_door[facing=south,half=upper,hinge=left]",
  "R":"spruce_planks","n":"spruce_stairs[facing=south,half=bottom]","v":"spruce_stairs[facing=north,half=bottom]",
  "h":"spruce_slab[type=bottom]"}}
```

- Rows run north → south (+z), characters west → east (+x). `.` leaves the block untouched.
- Legend letters must be unique **ignoring case** — that is why the door halves are `D` and `U`.
- Porch: make row 0 of layer 0 `.PPPPPPP.` and add `"F":"oak_fence"` posts `.F.....F.` in row 0 of layers 1–3.
- Door on the south instead: reverse the row order of every layer, swap `n`/`v`, and use `facing=north` doors.
- Then add a hanging lantern at grid (x4, z4) in layer 6 (under the `R` of layer 7) and furniture on layer 1
  inside x2..6 / z2..6. Swap the legend for other styles (`styles.md`).

## 11. Checklists

**Before building**
1. Site free? `minecraft_vision mode:check` or `script in cu run occupied(...)` on the footprint plus 2 blocks.
2. Ground level known and flat (§2).
3. Plan written: outer box, interior range, door cells, storey levels, roof type.
4. Palette of 2–3 main blocks + 1 accent (`styles.md`).
5. `minecraft_preview` the job files with `entrance` — fix the generator until the check is clean.

**After building**
1. `minecraft_jobs action:wait` shows no errors; the auto-verify has no real mismatches.
2. Access check ok (`entrance` on the last phase, or `minecraft_check_access`).
3. Door columns inspected; every stair walked (`minecraft_bot action:walk_to` to the upper floor).
4. `dark(...)` = 0 inside.
5. Screenshot iso + `cut_y` per floor and look at it.
6. Add it to the world map (`minecraft_map action:add` with its entrance).

## Common mistakes

| Mistake | Fix |
|---|---|
| Floor at feet level, house floats, step at the door | floor at the ground block |
| Path laid on top of the grass | paths replace the ground block |
| One flat wall material | base course + frame + window depth |
| Furniture fill on the wall line replaced the door | furnish inside the interior range, inspect door cells |
| Roof starts at the wall top and eats the beam row | first roof row = wall top + 1 |
| Stairs overlap the upper floor with no hole | `straight_stairs` carves headroom; add a railing (`stairs.md`) |
| Vaulted roof space left dark | lanterns from the ridge, `dark()` = 0 |

See also: `coordinates.md` · `roofs.md` · `stairs.md` · `furniture.md` · `interiors.md` · `styles.md` ·
`landscaping.md` · `verification.md`
