# Interiors

Read this when you plan the inside of a building: where rooms go, how people walk through them, how to light them
so no mob spawns, how to add plants that stay put, and how to decorate. The individual furniture pieces are in
`furniture.md`.

## 1. Plan before you place

1. **Interior range** = footprint minus the wall ring. Walls at `i=0` and `i=W` → furniture at `i=1 … W-1`. Write
   it down per room and per storey.
2. **Door cells**: every door's two cells plus the cell in front of it and the cell behind it.
3. **Walking lines**: a clear line (1 wide at least, 2 in halls) from the entrance to every room, every door, and
   the bottom and top of every staircase.
4. **Stair cells** and the 3 blocks of headroom above each step, plus the landing (`stairs.md`).
5. Everything in 2–4 is the **keep-clear set**. Nothing goes there — no chair, lamp, plant, vine or carpet edge
   that blocks.

```python
keep = set()
for (i, k) in doors:                       # front door at (4, 0) → keep (4, -1), (4, 0), (4, 1)
    keep |= {(i, k - 1), (i, k), (i, k + 1)}
keep |= {(4, k) for k in range(1, 6)}     # the walking line from the door to the back room
keep |= set(stair_cells)
def free(i, k): return (i, k) not in keep
```

## 2. Where rooms go

| Room | Place | Why |
|---|---|---|
| Entrance hall / living room | behind the front door | the first thing people see; the stairs start here |
| Kitchen + dining | next to each other, near the living room | they read as one zone |
| Bedrooms | at the back or upstairs | quiet and private |
| Bathroom | next to the bedrooms | |
| Study / library | a corner with a window | light for the desk |
| Stairs | along a wall near the entrance | the hall stays a walkway |

- Minimum useful room: 3×3 interior; 4×5 or more feels like a room.
- Separate zones without walls in small houses: a rug under the sofa, a dining set across the room, a different
  floor block in the kitchen.
- Tall pieces (wardrobes, bookshelves, kitchens with wall cabinets) go against **blank** wall, not in front of
  windows or doors.
- Face seating toward something: a fireplace, a TV, a window with a view (the cottage sofa faces the fire).

## 3. Lighting plan

Mobs spawn on floor cells where **block light and sky light are both 0**. Every room, attic, tower top and closed
space needs a light source; outdoor light does not reach far inside.

| Source | Light | Use |
|---|---|---|
| `lantern[hanging=true]` under an `iron_chain[axis=y]` | 15 | from the ridge of a vaulted roof, over tables and stairwells |
| `pearlescent_froglight`, `ochre_froglight`, `verdant_froglight`, `sea_lantern`, `glowstone`, `shroomlight` | 15 | **flush in the ceiling** (replace a ceiling block) — clean modern light |
| `end_rod` | 14 | modern lamps, strip lights |
| `white_candle[candles=3,lit=true]` | 3 per candle | bedside, tables, mood only — not enough alone |
| `glow_lichen[<side>=true]` | 7 | soft glow on walls, caves, greenery |
| `light[level=15]` | as set | **invisible**, no collision: attics, closed rooms, under trees |

- Hanging lamps in a vaulted cottage: `P.lamp(b, f, i, 1, k, "hanging", ceiling_j=top, chain=top - H - 1)` hangs
  the lantern from the ridge on a long chain.
- Invisible grid: `P.light_grid(b, x1, z1, x2, z2, y, step=7, level=15)` at head height (floor + 2), guarded with
  `execute if block ... air` so it never replaces anything.
- Night glow without changing a facade: emissive blocks right behind tinted glass render full-bright from outside.
- **Check**: `script in cu run dark(x1,y1,z1,x2,y2,z2)` returns `{spots, examples}` — `spots` must be **0** for the
  whole building. The access check also lists dark spots.

## 4. Plants indoors

Flowers, saplings and azaleas pop off anything that is not soil. On planks, quartz or terracotta floors:

- **Pots**: `potted_fern`, `potted_bamboo`, `potted_flowering_azalea_bush`, `potted_azalea_bush`, `potted_cactus`,
  `potted_red_tulip`, `potted_lily_of_the_valley` … (`P.plant(...)`).
- **Planter**: replace the floor block with `moss_block` (or `grass_block`, `dirt`) and put the flower, `azalea` or
  `flowering_azalea` on it. Tall flowers (`peony`, `lilac`, `rose_bush`) need both halves (`half=lower` +
  `half=upper`).

### Lots of greenery ("climbing plants inside")

For every room, on **air** cells only:

| Where | Block |
|---|---|
| Next to a wall, hanging 1–3 blocks down from the ceiling | `vine[<side of the wall>=true]` — a wall north of the cell → `vine[north=true]` |
| Along the ceiling edge, as garlands | `flowering_azalea_leaves[persistent=true]` |
| Patches on walls | `glow_lichen[<side of the wall>=true]` (also lights the room) |
| Under an open ceiling | `spore_blossom` (hangs under a solid block) |
| Glow berries from the ceiling | `cave_vines_plant[berries=true]` above `cave_vines[berries=true]` (the tip) |
| Floor planters | `moss_block` in the floor + flowers / azalea / tall flowers |

- **Guard every placement**: `execute if block x y z air run setblock x y z vine[north=true]` — never replace
  furniture or doors.
- **Skip the keep-clear set**: door fronts, carpets and runners, daises, stair cells **and their headroom**, spiral
  shafts. A vine on a stair cell blocks it.
- Leaves need `persistent=true`, or they decay.
- Afterwards run the access check and walk the bot up every staircase again.

## 5. Rugs, walls, details

- `P.rug(b, f, i1, 1, k1, i2, k2, color, border=...)`: a rug under the sofa group or the dining table; a runner
  (1–3 wide) from the front door to the main room. Carpets are flat — they never block walking.
- Break up long blank walls: a bookshelf wall, a fireplace, a window, a painting-like `item_display`, a shelf with
  pots (`furniture.md` recipes).
- Show things: an `item_display` on a shelf or pedestal, a `glass` block around one = a display case, a spinning
  showpiece, `P.label(...)` text above it (`displays.md`).
- Repeat the house's accent colour inside (rug, bed, cushions) — the 60-30-10 rule in `styles.md`.

## 6. Checklist after furnishing

1. `minecraft_inspect from:[door x, y, z] to:[door x, y+1, z] mode:list` for **every** door — both halves present,
   same `facing` and `hinge`.
2. Access check ok (no unreachable rooms, no blocked doors, no bad stairs).
3. `dark(...)` = 0.
4. Screenshot with `cut_y` at each floor + 2 and look at it: every room has a purpose, a light and a way in.

## Common mistakes

| Mistake | Symptom | Fix |
|---|---|---|
| A furniture fill on the wall line | a door disappeared | furnish inside the interior range; re-inspect door cells |
| Flowers on a plank or quartz floor | they pop off and drop as items | pots or a `moss_block` planter |
| Vines or lamps on stair cells or door fronts | blocked stairs / door | keep-clear set, `execute if block ... air` guard |
| Hanging lantern with nothing above | it pops on the next block update | chain or block above |
| Only candles | dark spots, mobs at night | a real source per room, `dark()` = 0 |
| Wardrobe in front of the only window | dark, closed-in room | tall pieces against blank wall |
| Everything pushed against walls, empty middle | looks like a warehouse | a rug + table group in the middle |
| Upstairs furniture on the stair landing | the stairs end in a bed | keep the landing free |

See also: `furniture.md` · `houses.md` · `stairs.md` · `styles.md` · `displays.md` · `verification.md`
