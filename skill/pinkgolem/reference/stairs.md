# Stairs, ladders and stairwells

Read this whenever a build has more than one level: houses with an upper floor, towers, galleries, lookouts. Stairs
are the part players test first and the part that most often breaks — a staircase that ends in a wall makes the
whole upper floor useless. Always verify with a real walk.

## Rules for every staircase

| Rule | Why |
|---|---|
| Stair `facing` = the direction you walk **up** | the tall half is on the far side; a reversed stair is a wall |
| One step up per cell | players climb stairs and slabs without jumping; a full block needs a jump |
| Rise = floor-to-floor height | a standard storey (floor + 4 walls) needs **5 steps** |
| Run = rise + 1 cells (+1 to step on) | the last cell is the landing on the upper floor |
| 3 blocks of air above every step | the player's head passes the ceiling of the floor below |
| A railing around every stair hole | people fall into holes they don't see |
| Keep stair cells and the landing free of furniture and plants | a lantern or vine on a step blocks it |

## Straight flights

```python
landing = P.straight_stairs(b, f, i, j, k, rise, going="back", stairs="oak_stairs", width=1,
                            support="oak_planks", headroom=3)
```

- `(i, j, k)` = the first step; `j` = floor + 1 (the level you stand at).
- `going` = the local direction you walk up (`front|back|left|right`); every stair faces that way.
- `width` adds parallel steps to the **right** of the walking direction.
- `headroom` carves that many blocks of air above every step. On a flight between storeys this also **cuts the
  stairwell hole** in the upper floor above the lower steps — you do not have to carve it separately.
- `support` fills under each step down to the first step's level (a solid flight); `support=None` = open stairs
  (modern look).
- Returns the **landing cell**: where you stand after the last step. Keep it free and use it as a target for
  `minecraft_reach`.

Example from `modern_villa.py` (ground floor walls `j=1..4`, upper floor at `j=5`):

```python
land = P.straight_stairs(i_, f, 11, 1, 1, H + 1, going="back", stairs="quartz_stairs", support=None)
# 5 steps at k=1..5, j=1..5; you arrive at (11, 6, 6) on the upper floor
```

## Stairwells between storeys

1. Put the flight along a wall, starting near the entrance, so the hall stays a walkway.
2. Let `straight_stairs` carve the headroom; it opens the upper floor above the steps that need it.
3. **Railing** on the upper floor around the hole's open sides. Glass panes need explicit connections:
   ```python
   rail = [(i, k) for i in (10, 12) for k in range(2, 5)]          # both sides of the hole (villa)
   b.fence_ring([f.p(i, H + 2, k) for (i, k) in rail], "glass_pane")
   ```
   Fences (`oak_fence`) or walls (`stone_brick_wall`) work the same way with `fence_ring`.
4. Leave the landing and the cell in front of the top step open — no rail, bed or wardrobe there.
5. Light the stairwell: a hanging lantern over the hole or a flush ceiling light.

## Spiral stairs

```python
arrive = P.spiral_stairs(b, cx, y1, y2, cz, core="quartz_pillar", stairs="oak_stairs", clear=True)
```

- World coordinates. A 1-block core at `(cx, cz)` from `y1` to `y2`, and one stair per cell on the **8 cells around
  it, clockwise** from north: N, NE, E, SE, S, SW, W, NW, then around again.
- Each stair faces the **next** cell, so every move is a straight step up. `y1` = the first step's level (floor +
  1), `y2` = the level of the floor you arrive on; there are `y2 - y1` steps.
- It returns `arrive` = the `(dx, dz)` offset of the **arrival cell**: the cell after the last step, at level
  `y2`. That cell must stay **solid** — it is the floor you step onto.
- `clear=True` carves 3 blocks of air above the steps. It does **not** open the floor you arrive on. Cut the stair
  hole yourself: every cell of the 3×3 at level `y2` except the core and the arrival cell (from
  `blueprints/tower.py`):

```python
arrive = P.spiral_stairs(b, cx, y + 1, top, cz, core="stripped_spruce_log[axis=y]", stairs="spruce_stairs")
for dx in (-1, 0, 1):
    for dz in (-1, 0, 1):
        if (dx, dz) not in ((0, 0), tuple(arrive)):
            b.set((cx + dx, top, cz + dz), "air")
```

- A spiral needs a 3×3 shaft through every floor it passes. At a middle floor, you step off from the stair that
  sits at that floor's level onto the floor around the shaft.
- `round_tower(..., stairs=True)` builds a spiral through all its storeys with 3×3 holes in every floor.
- Put a railing (or walls) around the shaft on each floor except the side you step off.

## Ladders

```python
P.ladder(b, x, y1, y2, z, facing)      # world coords, one ladder per level from y1 to y2
```

- `facing` = the **open side**, away from the wall it hangs on: a ladder on the north face of a wall (the wall is
  south of it) is `ladder[facing=north]`.
- Every ladder cell needs a solid block behind it, or it pops off.
- Through a floor: a 1×1 hole, and the ladder continues **up into the hole** to the upper floor's level, so the
  climber can step off.
- Ladders are for towers, lookouts, lofts and service shafts. For the main route between storeys use real stairs:
  players walk them without stopping, and the access check and `walk_to` follow them like normal floors.

## Verify every staircase

1. **Access check** — `entrance` on the last build phase, or
   `minecraft_check_access build:<name>` / `from` + `to` + `entrance`. Its `bad_stairs` lists stairs that end in a
   wall or lack headroom (`stair x y z: <problem>`). It must say ok.
2. **Reach** — nobody moves, it answers "can a player get there?":
   ```
   minecraft_reach from:[<entrance>] targets:[[<upper landing>], [<tower top>]]
   ```
   The blueprints print the entrance (and the villa its upper landing) for exactly this.
3. **A real walk** — `minecraft_bot action:walk_to pos:[<upper landing>]`. `walk_to` plans an A* path through doors
   and up stairs, spiral stairs included (range about ±60 blocks; `tp` closer first). A manual `path:[...]` walks
   straight and does **not** climb stairs — do not use it for this test.
4. In a plan that is not built yet: `minecraft_preview commands_files:[...] entrance:[...]` runs the same check on
   the virtual build.

The access check can report a false "closed room" once in a while. Confirm with a bot walk before changing the
build.

## Common mistakes

| Mistake | Symptom | Fix |
|---|---|---|
| A tower or wall generated after the stairs lands on the top step or landing | "stairs end in a wall", upper floor unreachable | carve the landing **after** placing towers in the generator; walk every staircase |
| Ceiling not cut above the lower steps | head bumps, check says no headroom | `headroom=3` (default) or carve 3 blocks above each step |
| Flight one cell too short for the storey | the last step is a full block high | rise = floor-to-floor height, run = rise + 1 |
| Stairs facing the wrong way | a wall of stair backs | `facing` = walking direction up |
| Spiral arrival cell carved away | you arrive over a hole | keep `arrive` solid when cutting the 3×3 |
| Spiral stair hole never cut | the last steps end under the ceiling | clear the 3×3 at `y2` except core + arrival |
| Plants, lamps or furniture on stair cells | blocked steps | keep-clear set for stair cells and their headroom |
| No railing around the hole | players fall through | `fence_ring` glass panes or fences |
| Ladder without a wall behind | ladder missing after build | solid block behind every ladder cell |
| Tested with a straight `path` walk | "the bot can't climb" | `walk_to` with pathfinding |

See also: `houses.md` · `round-and-tall.md` · `verification.md` · `block-states.md` · `interiors.md`
