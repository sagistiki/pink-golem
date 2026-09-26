# Coordinates, directions and ground levels

Read this before your first build in a new world, and whenever something ends up one block too high, rotated the
wrong way, or on the wrong side of a wall. Almost every "the build looks broken" report comes from one of the
mistakes on this page.

## The axes

| Axis | Direction | Words in block states |
|---|---|---|
| +x | east | `east` |
| -x | west | `west` |
| +z | south | `south` |
| -z | north | `north` |
| +y | up | `up` |

- **Yaw** (where a player or entity looks): `0` = south, `90` = west, `180` (or `-180`) = north, `-90` (or `270`) = east.
  `minecraft_get_players` also gives `facing.direction` in words.
- **Pitch**: `0` = horizontal, `90` = straight down, `-90` = straight up.
- A block at integer coordinates `(x, y, z)` fills the cube from `(x, y, z)` to `(x+1, y+1, z+1)`. Its centre is at
  `x+0.5, y+0.5, z+0.5` — use `.5` when teleporting or summoning onto the middle of a block.

## Ground level — the rule that matters most

| World | Ground block (floors replace it) | Feet level (walls start here) | Below |
|---|---|---|---|
| Default superflat | **y = -61** (grass) | **y = -60** | dirt -62, -63; bedrock -64 |
| Normal terrain | varies per column | ground + 1 | stone, caves |

- **Floors, paths, patios, pool decks and sidewalks REPLACE the ground block.** A path laid at feet level is a
  one-block step in front of every door.
- **Walls, furniture, fences, lamps, flowers and trees stand ON the ground**, at ground + 1.
- A player standing on the ground has `position.y = ground + 1`; `minecraft_get_players` gives `standingOn`, the
  block under their feet — that is the ground (or floor) level.
- `minecraft_status` tells you the world type and, for flat worlds, the ground Y.

### Reading the ground in a normal world

| Need | Call |
|---|---|
| Height of one column | `script in cu run ytop(x, z)` → y of the highest non-air block (stand at ytop+1) |
| Natural ground over an area (ignores builds on top) | `script in cu run surface(x1, z1, x2, z2)` → `{min, max, avg}` |
| Flatten a site | `script in cu run level(x1, z1, x2, z2, y)` → grass at `y`, dirt below, air above (≤ 40000 columns) |
| Free building land | `minecraft_map action:find_space size:[w, d]` → spots with their height range |

Level the site before you build on hills (or design the build to follow the slope on purpose — terraces, stilts).
The world is shallow on a superflat map: there are only 3 blocks under the grass. For "underground" rooms build a
hill with `Build.terrain(...)` and hollow it.

## Relative building (`relative_to_player`)

`minecraft_build` and `minecraft_build_layers` accept `relative_to_player:<name>`: the origin becomes the ground block
the player stands on, so `y = 0` is the ground layer and `y = 1` the first block above. The result returns the
absolute `origin` — reuse absolute coordinates for follow-up edits, because the player will move.

## Frames: local coordinates for generators

`mclib.Frame(x, y, z, facing)` puts a building's local coordinate system into the world, so you design it once and
place it facing any direction:

- origin `(x, y, z)` = the **front-left corner at ground level**, as seen by someone standing in front of the
  building looking at it;
- `i` = along the front, left → right; `j` = up from the ground level (`j = 0` is the ground layer: floors);
  `k` = depth, from the front wall (`k = 0`) toward the back.

```
facing="south" (the front looks south, you stand south of it looking north):
        north (back, k grows)
    +-----------------------+
    |                       |
    |        building       |
    |                       |
    +-----------------------+  ← k = 0: the front wall
  (0,0,0)  i →  west … east
        south (front)
```

| Frame method | Does |
|---|---|
| `f.p(i, j, k)` | local → world `(x, y, z)` |
| `f.d('front'/'back'/'left'/'right')` | → world direction word |
| `f.set / f.box / f.walls / f.clear (b, …)` | like Build's, in local coordinates |
| `f.door(b, (i, j, k), "oak_door", into="back")` | a two-part door you walk into toward `into` |
| `f.sub(i, j, k, facing)` | a new Frame at a local point, its front facing a local direction — for furniture along side walls |
| `f.world_box(a, c)` | local corners → world `[lo, hi]` for map entries |

Block strings can contain `{front} {back} {left} {right}` (world direction words) and `{axis_i} {axis_k}` (`x` or `z`):
`"oak_stairs[facing={back}]"`, `"stripped_oak_log[axis={axis_i}]"`. The frame replaces them when you call `f.set`.

**Check a new frame with a preview** (`minecraft_preview`) the first time you use `f.sub`: its `i` axis runs along the
wall, and which end is "left" depends on the direction it faces.

## Boxes

- `fill x1 y1 z1 x2 y2 z2` includes both corners: `fill 0 0 0 4 0 4` is 5 × 5 = 25 blocks.
- The interior of a room with walls at `x1` and `x2` is `x1+1 … x2-1`. Write the interior range down before you
  furnish: a furniture fill on the wall line once replaced a door.
- A `/fill` changes at most 32768 blocks; `minecraft_build` splits bigger boxes for you.

## Common mistakes

| Mistake | Symptom | Fix |
|---|---|---|
| Floor at the player's feet Y | the house floats, the door has a step | floor at `standingOn.y` |
| Path at feet level | a step in front of the door (access check: "full-block step at a door") | paths replace the ground block |
| Yaw treated like math angles | NPC looks the wrong way | yaw 0 = south, 90 = west |
| Reusing `relative_to_player` for a second phase | the second part lands somewhere else | use the absolute `origin` from the first result |
| Designing in world coordinates for one direction | "now rotate it" is a rewrite | design with a `Frame` |

See also: `block-states.md` (which way stairs, doors and beds face), `houses.md`, `large-builds.md`.
