# Furniture

Read this when you furnish a room: every furniture function in `scripts/parts.py` with the blocks it places, the
"faces" convention, how to put furniture along side walls with `Frame.sub`, and recipes for pieces `parts.py` does
not have. Room planning, light and plants are in `interiors.md`.

## Conventions

- Every function takes the `Build` `b` and a `Frame` `f`; `j` = **floor + 1** (the level you stand at).
- Local directions: `'front' | 'back' | 'left' | 'right'` (see `coordinates.md`).
- **`faces` = the direction the person using it looks.** A sitter facing `front` has the backrest behind them, so
  the stair faces the opposite way (`back`) — a stair faces the side it rises toward, which is the backrest.
- Furniture goes **inside the interior range** (footprint minus the wall ring), never on the wall line.
- `blueprints/catalog.py` builds one of everything on labelled tiles — generate it once to see them.

## Seating and tables

| Function | Builds | Blocks |
|---|---|---|
| `chair(b, f, i, j, k, wood="oak", faces="front")` | one seat | `{wood}_stairs[facing=<opposite of faces>,half=bottom]` |
| `table(b, f, i, j, k, wood="oak", style="post")` | 1-block table | `post`: `{wood}_fence` + `{wood}_pressure_plate` on top · `slab`: `{wood}_slab[type=top]` · `glass`: `end_rod[facing=up]` + `smooth_quartz_slab[type=bottom]` on top |
| `dining_set(b, f, i, j, k, length=3, wood="dark_oak", chairs="spruce")` | table along `i` with chairs on both long sides | top: `{wood}_slab[type=top]`; chairs at `k-1` (face back) and `k+1` (face front) |
| `sofa(b, f, i, j, k, length=3, wood="oak", color="white", faces="front", arms="spruce_trapdoor")` | a row of seats with arm rests | chairs + `{arms}[facing=...,open=true,half=bottom]` at `i-1` and `i+length` (`arms=None` = none) |
| `bench(b, f, i, j, k, length=2, wood="oak", faces="front")` | outdoor bench | `sofa` with `{wood}_trapdoor` arms — `wood` must be a real wood here (stone has no trapdoors) |

Two chairs at a table: `P.table(b, f, 3, 1, 3); P.chair(b, f, 2, 1, 3, faces="right"); P.chair(b, f, 4, 1, 3,
faces="left")` — each sitter looks at the table.

**Sofa colour = the stair material** (concrete and wool have no stairs). The `color` argument does not change the
blocks — choose `wood`:

| Colour | `wood` (stair material) |
|---|---|
| white | `quartz`, `smooth_quartz` |
| red | `crimson`, `mangrove`, `red_nether_brick` |
| teal | `warped`, `prismarine` |
| pink | `cherry` |
| brown | `dark_oak`, `spruce` |
| pale yellow | `birch`, `bamboo` |
| orange | `acacia` |
| black / dark grey | `polished_blackstone`, `polished_deepslate` |
| purple | `purpur` |

## Beds, storage, shelves

| Function | Builds | Blocks |
|---|---|---|
| `bed(b, f, i, j, k, color="red", head="back")` | a bed, foot at `(i,j,k)`, head one cell toward `head` | `{color}_bed[part=foot,facing=<head>]` + `[part=head,...]`; both cells set to air first |
| `wardrobe(b, f, i, j, k, wood="spruce", faces="front")` | 2-high cabinet | two `barrel[facing=<faces>]` stacked + two open `{wood}_trapdoor` door fronts in the cell toward `faces` |
| `bookshelf_wall(b, f, i, j, k, width=3, height=2, wood="oak")` | shelf wall | `bookshelf` box + a `{wood}_slab[type=bottom]` row on top |
| `kitchen(b, f, i, j, k, length=4, faces="front")` | counter run along `i` against a wall | cycles `smoker`, `barrel[facing=up]`, `water_cauldron[level=3]` (sink), `barrel`, `furnace`, `barrel`; wall cabinets `barrel[facing=<faces>]` at `j+2`; a `lantern` on the counter. `faces` = where the cook stands |
| `tv_wall(b, f, i, j, k, width=3)` | flat TV | `black_concrete` panel at `j+1..j+2` over a `smooth_quartz_slab[type=top]` stand row |

**Recolouring a bed:** set both old halves to air first, then place foot and head. Replacing half by half breaks it
(the new head updates the old foot, which pops, which pops the new head). `bed()` does this for you with
`b.before(...)`. A bed needs its head cell free: check the cell toward `head`.

## Light and fire

| Function | Builds | Blocks |
|---|---|---|
| `lamp(b, f, i, j, k, kind="lantern", ceiling_j=None, chain=1)` | `lantern`: floor lamp | `spruce_fence` + `lantern[hanging=false]` |
| | `hanging`: from the ceiling at level `ceiling_j` (default `j+3`) | `chain` × `iron_chain[axis=y]` down from `ceiling_j-1`, then `lantern[hanging=true]` |
| | `modern` | `end_rod[facing=up]` |
| | `table` (any other kind) | `white_candle[candles=3,lit=true]` — needs a block under it |
| `chandelier(b, f, i, j_ceiling, k, arms=True)` | chain + lantern cross | 2 × `iron_chain[axis=y]`, `lantern[hanging=true]`; arms: `iron_bars` on 4 sides at `j_ceiling-2` with a hanging lantern under each |
| `fireplace(b, f, i, j, k, width=3, brick="bricks", chimney_to=None)` | fireplace against the wall behind depth `k` | `brick` surround 3 high, `campfire[lit=true,signal_fire=false]` in the middle with air above, `stone_brick_slab[type=bottom]` mantel at `j+3` |
| | `chimney_to=level` | a 3-wide `brick` chimney in the wall behind (`k+1`) up to that level, with a lit campfire on top (smoke above the roof) |

- A long chain from a vaulted roof: `P.lamp(b, f, 4, 1, 5, "hanging", ceiling_j=top, chain=top - H - 1)` (cottage).
- A lit campfire hurts whoever steps on it — keep the fireplace opening out of the walking line.

## Rugs, plants, outdoor pieces

| Function | Builds | Blocks |
|---|---|---|
| `rug(b, f, i1, j, k1, i2, k2, color="red", border=None)` | carpet area on the floor | `{color}_carpet`, border ring `{border}_carpet` |
| `plant(b, f, i, j, k, kind="potted_flowering_azalea_bush")` | indoor plant | any `potted_*` block (`potted_fern`, `potted_bamboo`, ...) |
| `lamp_post(b, x, y, z, style="classic")` | world coords, `y` = level above the ground | `classic`: 2 × `polished_blackstone_wall[up=true]` + `lantern` · `modern`: 3 × `end_rod[facing=up]` · `garden`: `dark_oak_fence` + `lantern` |

## Furniture along side walls: `Frame.sub`

Functions lay furniture out along the frame's `i` axis. For a side wall, make a sub-frame whose front faces into the
room:

```python
P.kitchen(b, f.sub(W - 1, 0, 5, "left"), 0, 1, 0, length=4)          # along the RIGHT wall, facing into the room
P.bookshelf_wall(b, f.sub(1, 0, 2, "right"), 0, 1, 0, width=2, height=2)   # along the LEFT wall
```

- `f.sub(i, j, k, facing)` puts the new origin at local `(i, j, k)` — the first interior cell next to the wall —
  and its front toward `facing`. Use `j=0` for the origin and pass `j=1` to the function, as with the main frame.
- The sub-frame's `i` runs **left → right as seen from inside the room looking at that wall**: along the right wall
  it runs toward the front of the house, along the left wall toward the back.
- `faces="front"` in a sub-frame = into the room.
- Check the first use with `minecraft_preview` (`cut_y` one above the floor).

## Recipes `parts.py` does not have

Write them with `f.set(b, (i, j, k), "...")` in a generator, or as `setblock` operations in `minecraft_build`.

| Piece | Blocks |
|---|---|
| Desk | 2 × `spruce_slab[type=top]` against a wall (or upside-down stairs), a `chair` facing the desk, a candle or `lantern[hanging=false]` on top, a `bookshelf` beside it |
| Bathroom sink | `water_cauldron[level=3]` (or an empty `cauldron`) on the floor against the wall |
| Toilet | `hopper` with a closed `birch_trapdoor[half=bottom,open=false]` on top as the lid |
| Shower | `iron_trapdoor[half=top,open=false]` in the ceiling cell as the head, glass panes (explicit connections) as the screen |
| Bath | a row of `water_cauldron[level=3]` framed by `smooth_quartz` — no loose water indoors (`water.md`) |
| Bar counter | upside-down stairs `dark_oak_stairs[half=top,facing=<bartender side>]` — the recess is on the guests' side for their knees; stools = chairs facing the counter |
| Back bar | a wall of `barrel`s, shelves of `*_slab[type=top]` with `flower_pot`, `potted_*`, `brewing_stand`, `decorated_pot`, lanterns |
| Wall shelf | `*_slab[type=top]` or a closed `*_trapdoor[half=top]` one cell out from the wall; pots, candles or `decorated_pot` on it |
| Item on a shelf or display | an `item_display` entity (`displays.md`); a `glass` block around it = a display case |
| Nightstand | `barrel[facing=up]` or `*_slab[type=top]` with `white_candle[candles=3,lit=true]` |

Pot plants and candles sit **in the cell above** a top slab — the slab only fills the upper half of its own cell.

## Optional: Polydecorations mod blocks

Only when the server has the Polydecorations mod (Polymer). Verified ids:

| Block | Notes |
|---|---|
| `polydecorations:dark_oak_bench`, `polydecorations:cherry_bench` | states `facing`, `type`, `has_rest` |
| `polydecorations:dark_oak_table`, `polydecorations:cherry_table` | |
| `polydecorations:dark_oak_stump` | a stool |
| `polydecorations:basket` | not solid — a pet bed |
| `polydecorations:cardboard_box` | **SOLID** (`open=true` looks like a pet bed). Never summon a mob in it: it suffocates. Summon on top (y+1) and list the entities again about 5 s later |
| `polydecorations:<color>_sleeping_bag` | two parts like a bed |
| `polydecorations:globe`, `polydecorations:display_case` | print "unexpected error" but are placed — check with `bstr` |
| also `wall_lantern`, `brazier`, `rope`, `wind_chime`, `long_flower_pot`, mailboxes | |

Test an unknown id with one `setblock` and `script in cu run bstr(block(x,y,z))` before using it in a job.

## Common mistakes

| Mistake | Fix |
|---|---|
| Chair or sofa facing the wall | `faces` = where the sitter looks; the stair faces the other way |
| Furniture fill on the wall line replaced a door | interior range only; inspect door cells afterwards |
| Bed recoloured half by half, both halves gone | clear both halves first (`bed()` does it) |
| Hanging lantern with nothing above it | a chain or a block above; it pops on the next update |
| Kitchen on a side wall built along the wrong axis | `f.sub(...)` + preview |
| Mob summoned into a cardboard box | it is solid — summon on top |
| Wardrobe or bookshelf blocking a window or the stair landing | plan tall pieces against blank wall |

See also: `interiors.md` · `houses.md` · `displays.md` · `block-states.md` · `mods.md` · `entities.md`
