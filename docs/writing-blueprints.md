# Writing blueprints

This tutorial takes one idea, a market stall, and turns it into a **parametrised blueprint**: a Python generator
that builds the stall at any position, facing any direction, in several styles, with one tool call. Read it if you
want to add your own buildings to Pink Golem, or understand the generators your AI writes. You need a little
Python; you don't need to know Minecraft commands.

A blueprint is worth writing when a building will be built more than once, or when you want small models to build
it reliably: for them, a blueprint turns a whole building into a single `minecraft_generate` call.

---

## 1. Sketch the idea

Decide the footprint in blocks and what goes where. Our stall, seen from above, with the front (where the buyers
stand) at the bottom:

```
 k=4   P . . . . . P      P = corner post (3 high)
 k=3   . . . L . . .      L = hanging lantern
 k=2   . . . . . . .
 k=1   . C C C C C .      C = counter (barrels) with goods on top
 k=0   P . . . . . P
       ─────────────  front
 k=-1 … -4: a cobbled square with a bench facing the stall
       i=0 …… i=6
```

The floor is 7 × 5 blocks, the posts are 3 high, and a striped awning on top overhangs by one block on every side
except the back.

## 2. Think in local coordinates: the Frame

Don't write world coordinates (x, z) in a blueprint. Write **local** ones, and let a `Frame` turn them into world
coordinates for whichever way the building faces.

```python
f = Frame(x, y, z, facing)      # origin = the FRONT-LEFT corner at ground level
f.p(i, j, k)                    # local → world (x, y, z)
```

| Axis | Means | Runs |
|---|---|---|
| `i` | along the front | left → right, as seen by someone standing in front, looking at it |
| `j` | up | `j = 0` is the ground layer itself (floors **replace** it); walls start at `j = 1` |
| `k` | depth | `0` = the front wall, growing toward the back; negative `k` is in front of the building |

The origin's `y` is **the ground block** (flat world: y = -61). A floor at `j = 0` replaces the grass, so the
building doesn't float. On normal terrain, use the `standingOn.y` of a player from `minecraft_get_players`.

`--facing` is the direction the **front** faces. For `--facing south` the buyers stand south of the stall, looking
north. `i` runs east (their left to right) and `k` runs north.

## 3. Directions in block states: `{front}` tokens

Stairs, doors, barrels and logs have a direction in their block state. Write it with a token, and the Frame fills
in the world direction:

| Token | Becomes (for `--facing south`) | Use |
|---|---|---|
| `{front}` | `south` | things that face the viewer: a pumpkin's face, a barrel's lid, a sign |
| `{back}` | `north` | a door you walk *into* (`facing` = the way you walk in) |
| `{left}` / `{right}` | `west` / `east` | side-facing parts |
| `{axis_i}` / `{axis_k}` | `x` / `z` | logs, hay bales, pillars lying along `i` or `k` |

```python
f.set(b, (2, 1, 1), "carved_pumpkin[facing={front}]")
f.set(b, (3, 1, 1), "hay_block[axis={axis_i}]")
```

A literal `{` inside an f-string needs doubling: `f"{S['log']}[axis={{axis_i}}]"`.

## 4. Build in phases: one `Build()` per job file

Split the build into **phases**, each its own `Build()` and job file. The player sees it go up step by step (the
AI says one chat line per phase), and a bug in one phase can be fixed and undone without touching the others.

| Phase | Contents | File |
|---|---|---|
| 1 structure | floor, posts, awning, counter | `jobs/market_stall-1.json` |
| 2 details | goods, lantern, the name sign | `jobs/market_stall-2.json` |
| 3 outside | the square, bench, barrels | `jobs/market_stall-3.json` |

Within one `Build`, **later writes win**: carve openings after walls, lay decorations after the base.
`b.before(cmd)` adds a raw command that runs *first* (for example removing an old sign), and `b.cmd(cmd)` one that
runs *after* the blocks (summons, `place feature` trees).

## 5. Use the parts library

`skill/pinkgolem/scripts/parts.py` has tested components, so you don't have to work out chair stairs or lantern
chains yourself. A few of them:

| Part | Call |
|---|---|
| a hanging lantern on a chain | `P.lamp(b, f, i, j, k, "hanging", ceiling_j=…, chain=1)` |
| a bench (stairs + trapdoor arms) | `P.bench(b, f, i, j, k, length=2, wood="spruce", faces="back")` |
| a path IN the ground | `P.path(b, cells, y, "cobblestone")`, where cells are world `(x, z)` pairs |
| floating text | `P.label(b, x, y, z, "text", tag=…, color="gold", facing=f.d("front"))` |
| rooms, windows, doors, roofs, stairs, furniture, gardens, towers | see the docstrings in `parts.py`; `catalog.py` builds one of each |

Part functions take **local** coordinates and a Frame, except the outdoor ones that take world coordinates
(`path`, `lamp_post`, `label`); use `f.p(...)` to get those.

## 6. Finish: save, then print the box and the entrance

```python
files = frame.save(f"{a.name}-1") + goods.save(f"{a.name}-2") + square.save(f"{a.name}-3")
lo, hi = f.world_box((-1, 0, -4), (W + 1, H + 2, D))
ent = f.p(W // 2, 1, -2)
print(f"box {lo} -> {hi}; entrance … {[ent[0] + 0.5, ent[1], ent[2] + 0.5]}; files {files}")
```

- `save(name)` compresses the voxels into `/fill` commands and writes `jobs/<name>.json`. Past 1200 commands it
  writes `<name>-1.json`, `<name>-2.json` … (so a phase called `stall-1` can become `stall-1-1`, `stall-1-2`).
- The **box** is what the AI puts in the world map (`minecraft_map action:add`).
- The **entrance** is a feet position just outside the way in, at block centre (`+ 0.5`). The AI passes it as
  `entrance:[…]` so the access check walks the build after the last phase.

---

## The complete example

Save this as **`jobs/gen_market_stall.py`** (generators you write for your own world go in `jobs/`, which git
ignores):

```python
"""gen_market_stall.py — a market stall with a striped awning, a counter full of goods, a hanging lantern, a name
sign and a small cobbled square in front.

    python3 jobs/gen_market_stall.py --at X,Y,Z --facing south [--style red|blue|green] [--name market_stall]
      X,Y,Z = front-left corner at ground level (Y = the ground block, -61 on the default flat world).
      The square extends 4 blocks in FRONT of the stall.
    → jobs/<name>-1.json (structure), -2 (goods, lamp, sign), -3 (square, bench, barrels)
"""
import os
import sys

sys.path.insert(0, os.path.join(os.environ.get("PINKGOLEM_ROOT", "."), "skill/pinkgolem/scripts"))
from mclib import Build, Frame, parse_args          # noqa: E402
import parts as P                                    # noqa: E402

STYLES = {
    "red":   dict(stripe="red_wool", wood="spruce", post="stripped_spruce_log"),
    "blue":  dict(stripe="blue_wool", wood="birch", post="stripped_birch_log"),
    "green": dict(stripe="green_wool", wood="dark_oak", post="stripped_dark_oak_log"),
}
a = parse_args({"name": "market_stall", "style": "red"})
S = STYLES.get(a.style, STYLES["red"])
f = Frame(a.x, a.y, a.z, a.facing)
W, D, H = 6, 4, 3            # stall i 0..6, k 0..4, posts j 1..3, awning at j 4

# ── 1. structure ───────────────────────────────────────────────
frame = Build()
f.box(frame, (0, 0, 0), (W, 0, D), f"{S['wood']}_planks")              # floor REPLACES the ground block
for (i, k) in ((0, 0), (W, 0), (0, D), (W, D)):                          # four corner posts
    f.box(frame, (i, 1, k), (i, H, k), f"{S['post']}[axis=y]")
for i in range(-1, W + 2):                                               # striped awning, one block of overhang
    stripe = S["stripe"] if i % 2 == 0 else "white_wool"
    f.box(frame, (i, H + 1, -1), (i, H + 1, D), stripe)
for i in range(1, W):                                                    # counter along the front, facing the buyers
    f.set(frame, (i, 1, 1), f"barrel[facing={{front}}]")

# ── 2. goods, light, sign ──────────────────────────────────────
goods = Build()
wares = ["melon", "carved_pumpkin[facing={front}]", "hay_block[axis={axis_i}]", "potted_red_tulip", "cake"]
for n, i in enumerate(range(1, W)):
    f.set(goods, (i, 2, 1), wares[n % len(wares)])
P.lamp(goods, f, W // 2, 1, 3, "hanging", ceiling_j=H + 1, chain=1)     # chain under the awning, lantern below
sx, sy, sz = f.p(W // 2, H + 2, -1)
goods.before("kill @e[type=text_display,tag=%s]" % a.name)             # rebuilding never doubles the sign
P.label(goods, sx + 0.5, sy + 0.3, sz + 0.5, "Fresh Market", tag=a.name, color="gold", facing=f.d("front"))

# ── 3. the square in front ─────────────────────────────────────
square = Build()
cells = [f.p(i, 0, k)[0::2] for i in range(-1, W + 2) for k in range(-4, 0)]
P.path(square, cells, a.y, "cobblestone")                                # paths go INTO the ground
P.bench(square, f, 1, 1, -4, length=2, wood=S["wood"], faces="back")     # a bench looking at the stall
f.set(square, (W + 1, 1, 0), "barrel[facing=up]")
f.set(square, (W + 1, 2, 0), "potted_fern")

files = frame.save(f"{a.name}-1") + goods.save(f"{a.name}-2") + square.save(f"{a.name}-3")
lo, hi = f.world_box((-1, 0, -4), (W + 1, H + 2, D))
ent = f.p(W // 2, 1, -2)
print(f"box {lo} -> {hi}; entrance (feet, in front of the counter) {[ent[0] + 0.5, ent[1], ent[2] + 0.5]}; files {files}")
```

What to notice:

- **Nothing here is a world coordinate** except what the Frame computes. The same file works facing all four ways.
- The floor is at `j = 0` and the square's path is at `a.y`, both *in* the ground. A path one block too high
  becomes a step.
- `goods.before("kill …")` removes the old sign first, so running the blueprint twice doesn't stack two signs.
- Styles are a dictionary of block names, which is the cheapest way to parametrise a design.
- `faces="back"` on the bench: the sitter looks toward the back, at the stall.

---

## Run it by hand

From the Pink Golem folder (no server needed; this only writes job files):

```bash
python3 jobs/gen_market_stall.py --at 0,-61,0 --facing east
```

```
market_stall-1: 106 voxels -> 23 commands -> ['jobs/market_stall-1.json']; bounds ([-4, -61, -7], [1, -57, 1])
market_stall-2: 7 voxels -> 9 commands -> ['jobs/market_stall-2.json']; bounds ([-3, -59, -5], [-1, -58, -1])
market_stall-3: 42 voxels -> 6 commands -> ['jobs/market_stall-3.json']; bounds ([0, -61, -7], [4, -59, 1])
box [-4, -61, -7] -> [4, -56, 1]; entrance (feet, in front of the counter) [2.5, -60, -2.5]; files [...]
```

Try all four facings and a style (`--facing north --style blue`). Each must run without errors. Open a job file
to see the commands: `fill` lines for runs of blocks, `setblock` for single ones.

## Run it in the game

Ask your AI, or call the tools yourself:

1. **Generate only**, then **preview**. Nothing is placed yet:

   ```
   minecraft_generate script:"jobs/gen_market_stall.py" args:["--at","100,-61,40","--facing","south"]
   minecraft_preview commands_files:["jobs/market_stall-1.json","jobs/market_stall-2.json","jobs/market_stall-3.json"] mode:all
   ```

2. **Build** as background jobs, with helpers and the access check on the last phase:

   ```
   minecraft_generate script:"jobs/gen_market_stall.py" args:["--at","100,-61,40","--facing","south","--style","green"]
                      build:true helpers:2 entrance:[<the printed entrance>]
   minecraft_jobs action:wait          (repeat until every job is done)
   ```

3. **Check** the result: `errors: 0`, `verify.mismatches: 0` (a `grass_block>dirt` mismatch is harmless), then a
   screenshot from two sides. When something is wrong, **fix the generator** and rebuild (`minecraft_undo`, then
   generate again). Don't patch it with a separate job: the next regeneration would silently undo the patch.

Or script the whole test with `mcp-server/test/run.mjs` ([contributing.md](contributing.md#testing)).

## Adding your own options

`parse_args` knows `--at`, `--facing`, `--name`, `--style` and `--seed` (for `random.Random(a.seed)`, so "random"
layouts can be repeated). For other options, such as a length or a height, use `argparse` yourself, as
`drop_tower.py` does:

```python
import argparse
from mclib import DIRS
ap = argparse.ArgumentParser()
ap.add_argument("--at", required=True); ap.add_argument("--facing", default="south", choices=list(DIRS))
ap.add_argument("--name", default="market_stall"); ap.add_argument("--style", default="red")
ap.add_argument("--stalls", type=int, default=1, help="stalls side by side")
a = ap.parse_args()
a.x, a.y, a.z = (int(float(v)) for v in a.at.split(","))
```

A row of stalls is then a loop over `f.sub(n * (W + 2), 0, 0)`, a new Frame for each stall, shifted along `i`.

## Common mistakes

| Mistake | Result | Fix |
|---|---|---|
| Floor at the player's feet level (`j = 1`) | the building floats one block up, with a step at the door | floors and paths at `j = 0` (they replace the ground) |
| World directions in block states (`facing=south`) | right in one orientation, wrong in the other three | `{front}`, `{back}`, `{left}`, `{right}` |
| Walls with one `fill … hollow` | also fills the floor and ceiling | `f.walls(...)` or `P.room(...)` |
| Fences and panes by plain name | they don't connect when placed by commands | `b.fence_ring(...)`; `P.window` sets pane connections |
| Flowers on planks or quartz | they pop off as items | `potted_*`, or soil under them (`P.flower_bed` lays it) |
| Decoration over a door cell | the door loses a half and becomes a wall | skip door cells; the access check catches it |
| Everything in one Build | one huge job, and one bug means redoing it all | one Build per phase |
| No box or entrance printed | the AI can't register the build or check access | print both, like the example |
| An unlit enclosed room | mobs spawn inside | lamps, or `light` blocks (`P.light_grid`) |

## From `jobs/` to a shared blueprint

When your generator is good enough to share, move it to `skill/pinkgolem/blueprints/<name>.py` and change the
import path to be relative to the file, as the other blueprints do:

```python
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
```

Then follow the blueprint checklist in [contributing.md](contributing.md#add-a-blueprint): header docstring, all
four facings, a real-server test with screenshots, and a row in the blueprint table of `SKILL.md`.

## See also

- The ready blueprints, to read and copy: `skill/pinkgolem/blueprints/cottage.py` (a small house),
  `modern_villa.py` (two storeys), `tower.py` (round), `park.py` (landscaping), `drop_tower.py` (tall + game logic), `tnt_run.py` (an arena + a full game), `ferris_wheel.py` (a moving ride made of display entities)
- [Contributing](contributing.md) · [Architecture](architecture.md#generators-and-jobs)
- For the AI's side: [the skill](../skill/pinkgolem/SKILL.md), Part 4, and the reference pages on
  [coordinates](../skill/pinkgolem/reference/coordinates.md) and [block states](../skill/pinkgolem/reference/block-states.md)
