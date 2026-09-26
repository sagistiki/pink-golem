# Roofs

Read this when a build needs a roof: which shape to choose, how the `parts.py` roof functions work, which way the
stairs must face, and what commands cannot do. A good roof is most of what makes a house look finished.

## The one rule: stairs face uphill

A stair's `facing` is the direction it **rises toward** — the side with the tall half. On a roof, every stair faces
the ridge.

| Slope | Stair `facing` |
|---|---|
| north slope of a ridge running east–west | `south` |
| south slope of that ridge | `north` |
| east slope of a ridge running north–south | `west` |
| west slope of that ridge | `east` |

- `half=bottom` (default) for the roof surface. `half=top` = upside-down stair: the step is underneath. Use it for
  **eaves** under the overhang edge and for canopies over doors, with `facing` toward the wall.
- In a `Frame`, write `{front}/{back}/{left}/{right}` instead of world directions and the roof rotates with the
  house.

## Choosing a shape

| Build | Roof | Why |
|---|---|---|
| Cottage, gable toward the street | gable `ridge="k"` | the triangle on the front is the classic cottage face |
| Long house, barn, hall | gable `ridge="i"` | the long eaves face the street |
| Square house, pavilion | hip | no gable walls, looks the same from all sides |
| Modern house, terrace | flat + overhang + trim | clean lines, walkable |
| Round tower | stepped cone | a gable cannot sit on a circle |
| Observatory, great hall, temple | dome | round and tall |
| Greenhouse, conservatory | glass steps | no glass stairs exist |

## Gable roof

```python
top = P.gable_roof(b, f, i1, k1, i2, k2, j, stairs="spruce_stairs", full="spruce_planks", ridge="i",
                   overhang=1, gable_fill=None, slab=None)
```

- `i1..i2 × k1..k2` = the **outer walls**; `j` = the first roof row = **wall top + 1**.
- `ridge="i"`: the ridge runs left–right, the slopes face front and back, the gable walls are on the sides.
  `ridge="k"`: the ridge runs front–back, the gable faces the front.
- Every row is one higher and one further in; the stairs face the ridge.
- `overhang=1` extends the roof one block past the walls on **all** sides, including past the gable ends.
- `gable_fill` = the block that closes the triangle under the roof at both gable ends (usually the wall block).
  Without it the gable ends stay open.
- `slab` defaults to `full` with `_planks` → `_slab`. For other materials pass it: `deepslate_tile_stairs` /
  `deepslate_tiles` / `deepslate_tile_slab`.
- Returns the ridge level — use it for chimneys (`fireplace(..., chimney_to=top + 2)`) and hanging lamps.

**Odd and even spans.** The span is the roof width across the slopes, overhang included (outer width + 2 ×
overhang).

| Span | Top of the roof |
|---|---|
| odd (e.g. 9-wide house + 2 overhang = 11) | a ridge row of **bottom slabs** in the middle |
| even | the two top stair rows meet back to back, no slab |

Odd spans look neater: prefer odd house widths. Roof height ≈ half the span, so a 9-wide house gets a roof about
6 levels high.

**Pitch.** Stairs give 45°. Steeper: put a full block under each stair (two levels per step). Shallower: alternate
`*_slab[type=bottom]` and `*_slab[type=top]` in neighbouring cells (half a level per step).

## Hip roof

```python
top = P.hip_roof(b, f, i1, k1, i2, k2, j, stairs="dark_oak_stairs", full="dark_oak_planks", overhang=1)
```

Each level is a ring of stairs facing inward, one smaller per level; the four corners are **full blocks** (see
below); when the remaining width is under 3 the top is filled with `full`. On a long rectangle this leaves a flat
strip of full blocks along the top — that is the hip roof's ridge. Returns the top level.

## Flat roof

```python
P.flat_roof(b, f, i1, k1, i2, k2, j, roof="smooth_stone_slab[type=bottom]", parapet=None, overhang=0, trim=None)
```

- `roof` covers the rectangle (+ overhang) at level `j`.
- `parapet` = a 1-high wall ring on top (`white_concrete`) — also a safety rail on a walkable roof.
- `trim` = a ring at the overhang edge, replacing the roof's outer ring (only with `overhang`). Modern houses:
  `overhang=1`, black trim (`modern_villa.py` uses its `trim` block from the style).
- A flat roof on a plain box looks unfinished — give it an overhang with trim, a parapet, or a second box on top.

## Stepped cone (round towers)

```python
tip_y = P.cone_roof(b, cx, y, cz, r, block="dark_prismarine", tip="lightning_rod", taper=1.0, cap_slab=None)
```

World coordinates. Starts at radius `r + 1` (a 1-block overhang over a tower of radius `r`), one ring per level,
the radius shrinking by `taper` each level; `taper=0.5` makes a cone twice as steep. `tip` goes on top
(`lightning_rod`, `end_rod`, `gold_block`), `cap_slab` fills the centre near the top. `round_tower(...,
roof="cone")` calls it for you. Stepped rings of a strong colour (`dark_prismarine`, `pink_concrete`,
`deepslate_tiles`) read best from far away.

## Dome

```python
P.dome(b, cx, y, cz, r, block="white_concrete", glass=None)
```

A hemisphere shell starting at level `y` (world coordinates). `glass="glass"` turns every third ring into a glass
band — a lantern dome that lets light in. Put it on a round or square drum a few blocks tall, not straight on the
ground.

## Greenhouse and glass roofs

There are **no glass stairs or slabs** (plain or stained). Build a glass roof as steps of solid `glass` strips: each
row one block higher and one further in, like a gable made of full blocks. Frame it with thin posts
(`*_fence`, `iron_bars` — both need explicit connections) or a log ridge beam.

## What commands cannot do

| Vanilla placement does | Commands do not | Do this instead |
|---|---|---|
| stairs curve at corners (`shape=inner_*`/`outer_*`) | a stair placed by `setblock`/`fill` keeps `shape=straight` | full blocks at corners (as `hip_roof` does), or set `shape=` yourself and check a picture |
| fences, panes, walls, bars connect | they stay unconnected posts | `Build.fence_ring(cells, blk)` or explicit `north=true,...` states |
| leaves stay | leaves placed away from logs decay | `*_leaves[persistent=true]` for leafy roofs and hedges |

## Finishing details

- Overhang 1 on every side; an eave line of upside-down stairs under it.
- A ridge in a contrasting slab or a log beam.
- A chimney with a lit campfire on top — smoke above the roof says someone lives here (`fireplace(...,
  chimney_to=...)`).
- A window in the gable to light the attic.
- A canopy over the door: a row of `*_stairs[facing=<toward the wall>,half=top]` one block out.

## Common mistakes

| Mistake | Symptom | Fix |
|---|---|---|
| Stairs facing downhill | the roof looks like a saw | `facing` = toward the ridge |
| First roof row at the wall top | it overwrites the beam row, eaves sit too low | `j` = wall top + 1 |
| No `gable_fill` | open triangles at both ends | pass the wall block |
| Even span with a slab in mind | no ridge slab appears | make the span odd |
| Hip roof on a long rectangle expecting a point | a flat strip on top | that is correct; use a gable for a point |
| Glass stairs in the job | an unknown-block error | steps of solid glass |
| Vaulted roof space dark | mobs spawn under the ridge | hanging lanterns from the ridge, `dark()` = 0 |
| Roof hides the upper windows | no light upstairs | raise the walls one row or put windows in the gables |

See also: `houses.md` · `round-and-tall.md` · `styles.md` · `block-states.md` · `interiors.md`
