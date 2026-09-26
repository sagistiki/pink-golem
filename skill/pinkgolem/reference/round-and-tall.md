# Round and tall builds: circles, towers, domes, spirals and skyscrapers

Read this when a build is round (towers, fountains, domes, arenas) or very tall (skyscrapers, lighthouses, drop
towers). Round shapes in voxels need one consistent rule, and tall builds need a different way of producing commands
or the job gets huge. Worked examples: `blueprints/tower.py` (round lookout tower) and `blueprints/drop_tower.py`
(60-block glass tower with the clone trick, hidden lamps, a launch pad and a free-fall pool).

**G** = the ground block (flat world: y=-61); see `coordinates.md`.

## Circles in voxels

A cell belongs to a circle of radius r around (cx, cz) when **dx² + dz² ≤ (r + 0.5)²**. The same rule is used by
mclib, `parts` and Carpet's `/draw`, so shapes from all of them line up.

```python
from mclib import disk, ring
disk(cx, cz, r)    # filled circle: floors, basins, roofs
ring(cx, cz, r)    # 1-thick outline without diagonal gaps: walls (= disk(r) minus disk(r-1))
```

| r | Width (2r+1) | Good for |
|---|---|---|
| 2 | 5 | turret, well, small fountain |
| 3 | 7 | round tower with a spiral stair inside (the 3x3 spiral plus a ring of floor around it) |
| 4 | 9 | lookout tower (`tower.py`) |
| 6-8 | 13-17 | lighthouse, drop tower |
| 12+ | 25+ | arena, big dome |

Volumes on top of that:

```python
b.cylinder((cx, G + 1, cz), r, h, "stone_bricks", hollow=True)   # hollow = a ring wall h high
b.sphere((cx, y, cz), r, "glass", hollow=True, ry=None)          # ry = vertical radius for an ellipsoid
```

For a smooth ring of points at any radius (a helix, a spiral lining), sample angles instead:
`round(cx + R*cos(t))`, `round(cz + R*sin(t))` for t in small steps, keeping unique cells in order
(`drop_tower.py` does this for its shell).

## Round towers

```python
t = P.round_tower(b, cx, G, cz, r=4, height=24, wall="stone_bricks", floor="spruce_planks",
                  windows="glass_pane", window_every=4, floors_every=5, roof="cone",
                  roof_block="dark_prismarine", door_facing="south", stairs=True)
# t = {"top": y of the roof base, "door": (x, y, z) of the door's lower half}
```

- The floor disk replaces the ground at G; walls run G+1 .. G+height.
- A storey every `floors_every` blocks, each with a 3x3 hole in the middle for the spiral stair.
- Window slits (2 high) on every `window_every`-th cell of the ring, on every storey.
- A door on the `door_facing` side; roof `"cone"` or `"flat"` (battlements).
- `tower.py` shows the full pattern: a spiral from the ground to a walkable roof, an accent band that skips the door
  cell, lanterns on the battlements, invisible light in every storey, a gravel ring path at the foot.

**Towers attached to other buildings:** a ring wall can land on a stair landing or cut through a hall. In the
generator, carve (write air) the parts of the tower that sit inside the room, then walk the bot up every staircase —
a tower once sealed the top of both main flights of a building.

## Cones and domes

```python
P.cone_roof(b, cx, y, cz, r, block="dark_prismarine", tip="lightning_rod", taper=1.0)
P.dome(b, cx, y, cz, r, block="white_concrete", glass="light_blue_stained_glass")
```

- `cone_roof` stacks rings from radius r+1 (a 1-block overhang) inward by `taper` per level. `taper=1.0` = a
  45° stepped cone; `0.5` = twice as steep (fairy-tale spire); finish with `tip` (`lightning_rod`, `end_rod`,
  `gold_block`).
- `dome` is a hemisphere shell starting at level y; `glass` puts a glass band on every third ring for a lantern dome.
- A dome or cone needs something under it: a floor disk at the level below, or the tower's top storey.

## Spiral stairs

```python
P.spiral_stairs(b, cx, y1, y2, cz, core="quartz_pillar", stairs="oak_stairs", clear=True)
```

A 1-block core with steps on the 8 cells around it, clockwise, one step up per cell; each stair faces the next cell,
so every move is a straight step up (one full turn = 8 blocks of height). `y1` = the first step's level, `y2` = the
floor you arrive on. It carves 3 blocks of headroom; the arrival cell (returned as an offset) must stay solid while
the rest of the 3x3 around the core is cut out of the floor above (`tower.py` does exactly this).

Test it for real: `minecraft_bot action:walk_to` plans an A* path that climbs spiral stairs (a manual `path` does
not). `minecraft_check_access` reports stairs that end in a wall or lack headroom. More in `stairs.md`.

## Very tall builds: the clone trick

A 186-block helix written as fills was 12,700 commands. Built as **one repeating period plus clones** it was about
2,000 commands and took 3 seconds.

1. Find the period: the smallest height after which the pattern repeats (in `drop_tower.py`: 6 colours × 4-block
   bands = 24 blocks).
2. Write the master period with normal voxels, starting above anything that does not repeat (entrance, lobby).
3. Clone it up the tower in boxes of **fewer than 32,768 blocks** each (the vanilla limit per command):

   ```python
   for dy in range(MASTER + PERIOD, TOP, PERIOD):
       h = min(PERIOD, TOP - dy)
       b.cmd(f"clone {x1} {MASTER} {z1} {x2} {MASTER + h - 1} {z2} {x1} {dy} {z1} masked")
   ```

   A wide tower may need the period split into half-tower boxes. Source and destination must not overlap.
4. **Scan the master period for foreign blocks first.** `masked` copies every non-air block in the box — an
   entrance frame or a tree in the bottom rows would be stamped all the way up. On an existing site, `occupied` the
   master box before the job.
5. **Random details go in a later job**, after the clones (window lamps, damage, plants). If they were in the master
   they would repeat every period and look copied.

`minecraft_preview` simulates `clone`, so the whole tower shows up in the preview before anything is placed.

## Night glow: hidden lamps behind tinted glass

Light-emitting blocks (`sea_lantern`, `ochre_froglight`, `pearlescent_froglight`, `glowstone`, `shroomlight`) render
full-bright through `tinted_glass`, while the glass itself looks dark by day. Put a lamp layer one block behind the
tinted-glass windows:

- Group the lamps in random 3-block "office floors", about 75% lit, with a mix of lamp types — at night it reads as a
  real tower with people working late.
- Keep the lamp layer in its own job after the clones (`drop_tower-2.json`).
- The facade does not change by day.

Tall hollow shafts are dark inside: add invisible `light[level=15]` blocks (no collision) every ~6 blocks up the
walls, or mobs spawn there.

## Free-fall shafts and landing pools

The drop tower pattern (`drop_tower.py` + `scarpet-apps/launchpad.sc`):

| Part | How |
|---|---|
| Ride up | a pressure plate; the app gives `effect give <player> minecraft:levitation 20 29 true` |
| Speed | levitation amplifier 29 lifts about **1.5 blocks per tick** (~30 blocks/s) |
| Arrive | near the top the app clears the effect and teleports the player onto the roof, facing the hole |
| Flying players | creative flyers ignore levitation, so the app teleports them after 2 s anyway |
| The hole | a round opening (r ≤ 2.5) in the roof over a clear shaft |
| Landing | a pool **2 deep** at the bottom, wider than the hole — a 187-block fall into 2-deep water left the player at full health |

The app also shows the fall height on the action bar and a "SPLASH" title with the fall time. See `game-logic.md`
for writing apps like this and `water.md` for the pool rules.

## Height, chunks and summons

- The overworld goes from y=-64 to y=319. On a flat world that is about 380 blocks above the grass.
- Commands (`setblock`, `fill`, `clone`, `summon`) only work in **loaded chunks**. A tall build is one column of
  chunks, so it loads when the bot is near it horizontally. For a far site, `minecraft_bot action:tp` the bot there
  first.
- `summon` for text displays and signs at the top works like anywhere else once the chunk is loaded.
- Screenshots of tall builds: frame the tower with `from`/`to` and use `mode:"iso"`; for the interior use `cut_y`.

## Common mistakes

- Circles drawn with a different radius rule than the floor disk → gaps between wall and floor.
- A spiral stair whose top cell is carved away → the stair ends in a hole.
- `masked` clone of a master that contains an entrance frame → the frame repeats up the whole tower.
- Random lamps inside the master period → identical lamp patterns every period.
- A landing pool 1 deep or narrower than the shaft.
- Round tower wall cutting through an existing staircase landing.

## See also

`stairs.md` · `roofs.md` · `water.md` · `game-logic.md` · `large-builds.md` · `displays.md` · `verification.md`
