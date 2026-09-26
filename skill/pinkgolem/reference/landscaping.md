# Landscaping: paths, trees, gardens, parks and zoos

Read this before you put anything outdoors: a path to a door, a garden, a row of trees, a park, a zoo. Outdoor work
looks easy and is where most "it looks broken" reports come from: raised paths, trees that grow into walls, flowers
that pop off, animals that escape. The worked example is `blueprints/park.py`.

In this page **G** = the ground block (flat world: y=-61). On normal terrain read it per spot: `standingOn.y` from
`minecraft_get_players`, `script in cu run ytop(x, z)` for one column, `script in cu run surface(x1, z1, x2, z2)`
for an area (see `coordinates.md`).

## Paths go INTO the ground

| Rule | Why |
|---|---|
| Paths, patios, sidewalks and plazas **replace** the ground block at G | a path one block up (G+1) is a step at every door |
| Things **on** the ground (flowers, fences, lamps, benches, trees) go at G+1 | they need the ground under them |
| Scan the whole footprint at G+1..G+6 before laying a path | a new path once ran straight through an older lamp post |
| Road markings run along the direction of travel | dashes by `floor_mod(coord, 3)` along the road; continue the existing phase |

Useful path blocks: `dirt_path` (slightly lower than a full block — reads as a trodden path), `gravel`, `coarse_dirt`,
`polished_andesite`, `stone_bricks`, `mud_bricks`. Vanilla behaviour to know:
- `dirt_path` turns back into dirt when a solid block is placed on top of it.
- `gravel` and `sand` fall if there is air under them — fill holes with dirt first.

```python
import parts as P
cells = P.path_line(x1, z1, x2, z2, width=3)            # straight path of any width between two points
P.path(b, cells, G, "gravel")                            # replaces the ground at G
P.path(b, cells, G, "dirt_path", edge="coarse_dirt")    # with a border ring at the same level
P.path(b, cells, G, "stone_bricks", edge="oak_fence", edge_y=G + 1)   # fence along both sides
```

Curved paths: collect cells yourself, e.g. an ellipse ring `0.62 <= ((i-ci)/7.5)**2 + ((k-ck)/6.5)**2 <= 1`
(the loop around the fountain in `park.py`). A path must meet each door at the door's floor level; check it with
`minecraft_check_access` (it reports "full-block step at door").

## Trees

Trees come from vanilla features: `place feature minecraft:<id> x y z` with y = G+1 (the block above the soil).
In a generator: `b.tree((x, G + 1, z), "fancy_oak_bees_002")`.

| Verified feature ids | Look |
|---|---|
| `oak_bees_002`, `fancy_oak_bees_002`, `fancy_oak` | small / large round oaks |
| `birch_bees_002`, `birch`, `super_birch_bees_0002` | birches, the last one tall |
| `cherry_bees_005` | cherry blossom |
| `dark_oak` | wide 2x2 trunk |
| `spruce`, `pine` | conifers |
| `jungle_bush` | low bush |
| `azalea_tree` | **large**: hanging canopy and roots spread 6+ blocks — keep it far from anything built |

Plain `oak` and `cherry` failed in tests; use the ids above.

- **Needs soil and space.** Dirt or grass under the trunk, air around the crown. "Failed to place feature" means it
  did not fit — harmless, nothing was placed. Count logs before and after (`script in cu run count(...)`) to see
  how many grew.
- **Run it as a plain command,** never wrapped in `execute at`.
- **Trees grow into builds.** A crown spreads several blocks around the trunk. Keep trunks well clear of walls and
  doors and ≥ 1 block from paths, put trees in a job after the buildings, and read the verification: a mismatch like
  `glass>oak_leaves` means a tree grew into a window.
- Test an unfamiliar feature once on empty land before placing it next to a build.

### Random packing, not a grid

```python
free = [(x, z) for (x, z) in candidate_cells if (x, z) not in blocked]    # blocked = paths, beds, water + 1 margin
P.trees(b, free, G + 1, kinds=("oak_bees_002", "birch_bees_002", "fancy_oak_bees_002"), seed=1, spacing=4)
```

`parts.trees` shuffles the free cells and keeps each trunk at least `spacing` blocks from the others. Random packing
looks natural; a grid looks planted. A 4-block grid with 2-block margins looked sparse in practice.

| Wanted | spacing | Density |
|---|---|---|
| Dense forest | 3 | about 1 tree per 12-16 m² |
| Park with lawns between trees | 4-6 | |
| Avenue along a path | fixed step, same kind | here a regular row is right |

### Undergrowth

A forest floor without undergrowth looks bare. Scatter on free grass at G+1: `fern`, `short_grass`, `bush`, `azalea`,
`flowering_azalea`, and a few `oak_leaves[persistent=true]` blobs. On ground that is already there, guard each
plant: `execute if block x G+1 z air run setblock x G+1 z fern`.

## Flowers, flower beds and hedges

- **Plants need soil.** Flowers, azaleas and bushes pop off quartz, planks, terracotta and stone. Indoors use
  `potted_*` blocks or replace one floor block with `moss_block` as a planter (`interiors.md`).
- `P.flower_bed(b, x1, G + 1, z1, x2, z2, seed=1, density=0.7, soil="grass_block")` fills a rectangle with mixed
  flowers and puts `soil` under every one; about 20% are tall flowers with both halves.
- Tall flowers (`rose_bush`, `peony`, `lilac`, `sunflower`) need `[half=lower]` and `[half=upper]`.
- **Hedges:** `P.hedge(b, cells, G + 1, height=1, leaves="oak_leaves")` — persistent leaves. Leaves placed by
  commands without `persistent=true` decay when no log is near.

## Lamp posts and benches

```python
P.lamp_post(b, x, G + 1, z, "classic")   # 2 polished_blackstone_wall + lantern
P.lamp_post(b, x, G + 1, z, "modern")    # 3 end rods
P.lamp_post(b, x, G + 1, z, "garden")    # dark_oak_fence + lantern
P.bench(b, f, i, 1, k, length=2, wood="spruce", faces="back")   # stairs + trapdoor ends; faces = where sitters look
```

Put lamps along paths every ~8 blocks, benches facing a path or a view. Lamps also keep mobs from spawning; under
dense trees add invisible light: `P.light_grid(b, x1, z1, x2, z2, G + 2, step=7)` and check
`script in cu run dark(...)` is 0 for enclosed spots.

## Water features

Fountains (`P.fountain`), ponds (`P.pond`) and pools (`P.pool`) are covered in `water.md`. Short version: water goes
in the LAST job, the basin must be closed on every side, and you count the water afterwards.

## Natural hills

```python
tops = b.terrain(cx, cz, rx=14, rz=10, height=9, seed=3, rough=2.0, base=G)   # returns {(x, z): top_y}
```

An elliptical dome with value noise: grass on top, dirt under it, stone inside, bare stone on steep upper parts.
Use `tops` to place trees and paths on the slope (`tops[(x, z)] + 1`). For your own shapes, `ValueNoise(seed).fbm(x/9,
z/9)` gives smooth noise in about [-1, 1]. Change materials in large noise patches, not per random column: the
generator merges equal neighbours into fills, so patches compress about 2x better. A flat world has only 3 blocks
under the grass: "underground" rooms go inside a hill you build and hollow out.

## Levelling a site

| World | How |
|---|---|
| Flat | fill old pits: `fill x1 -63 z1 x2 -62 z2 dirt replace air`, then `fill x1 -61 z1 x2 -61 z2 grass_block replace air` |
| Normal terrain | `script in cu run surface(x1, z1, x2, z2)` → `{min, max, avg}`; pick a height (usually `avg`); `script in cu run level(x1, z1, x2, z2, y)` → grass at y, dirt below, air up to y+40 (max 40000 columns) |

`level` removes everything above y in the box, trees and builds included — run `occupied` on the box first.

## Parks

`blueprints/park.py` (41 x 31) is the recipe: `minecraft_generate script:"skill/pinkgolem/blueprints/park.py"
args:["--at","X,G,Z","--facing","south"]`. It writes two jobs: ground + hard landscaping + water, then living things
and furniture.

1. Fresh ground over the whole box (dirt + grass), which also fills old holes.
2. A low wall ring (`mossy_stone_brick_wall`, connections from `fence_ring`) with 3-wide gaps that meet existing
   roads and sidewalks.
3. Paths in the ground: a cross through the entrances plus a loop around the centrepiece.
4. A fountain in the middle, a pond with a sand/gravel shore in one quarter.
5. Flower beds, benches facing the paths, lamps along them.
6. Trees packed at random on the free grass (≥ 1 from paths and beds), then undergrowth.

Bigger parks add a loop drive, a lake with a bridge, an open lawn, and a dense forest in everything else.

## Zoos and animal enclosures (no escapes)

| Rule | Why |
|---|---|
| Floor themed at G; a curb block at G+1 plus **≥ 2 full glass blocks** above it | 3 blocks total stops every walking animal; panes leave gaps |
| **Glass roof** for flyers (parrots) and jumpers (goats: 4 glass high + roof) | they escape over any open top |
| Aquatic animals: a sealed glass tank with a lid | |
| No gates — visitors look through the glass | a gate left open is an escape |
| **Scan for holes before summoning**: any air in the wall ring from G+1 to the top, and a `count` of each roof | one missing block is an exit |
| **Water last**, then count it | see `water.md` |
| After summoning, list every animal with its position and check each is inside its box | |

Hole scan for a rectangular pen x1..x2, z1..z2, walls G+1..G+3 (flat world shown):

```
minecraft_scarpet expression:"l=[]; for(range(-60,-57), y=_; for(range(x1,x2+1), x=_; for(range(z1,z2+1), z=_; if((x==x1||x==x2||z==z1||z==z2) && air(x,y,z), l+=[x,y,z])))); l"
```

Theme each enclosure (bamboo + podzol for pandas, snow + an ice pool for polar bears, sand + cactus for camels,
moss + torchflowers for sniffers, spruce + berry bushes for foxes) and put a plaque (a fixed text_display on the
glass, facing the path, with the animals' names — `displays.md`). Summon NBT, names and cleanup tags are in
`entities.md`. Keep the count modest (about 25 animals is fine) and never summon in a loop.

## Common mistakes

- Path at G+1 instead of G → a step in front of the door.
- `azalea_tree` or a fancy oak next to a door → the entrance is blocked by leaves and roots.
- Flowers on stone or planks → they drop as items (clean up with `minecraft_cleanup`).
- Leaves without `persistent=true` → the hedge decays.
- Trees placed before the building → leaves inside the walls.
- Summoning animals before the hole scan → escapes.

## See also

`water.md` · `entities.md` · `displays.md` · `coordinates.md` · `block-states.md` · `large-builds.md` ·
`verification.md` · `styles.md`
