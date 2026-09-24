"""cottage.py — a cosy 9x11 cottage with a front garden. The reference example for a small house: every rule of
reference/houses.md is in here (floor replaces the ground, stone base course, log frame, windows with depth, gable
facing the street, fireplace + chimney smoke, furnished rooms, lit so no mob can spawn, a path that goes INTO the
ground).

    python3 skill/clawdblock/blueprints/cottage.py --at X,Y,Z --facing south [--style oak|birch|dark]
      X,Y,Z = front-left corner of the house at ground level (Y = the ground block, -61 on the default flat world)
      the garden (path, flower beds, lamps) extends 7 blocks in FRONT of it; trees 5 blocks to each side.
    → jobs/cottage-1.json (house), jobs/cottage-2.json (interior), jobs/cottage-3.json (garden)
Entrance for the access check: printed at the end.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from mclib import Build, Frame, parse_args          # noqa: E402
import parts as P                                    # noqa: E402

STYLES = {
    "oak":   dict(log="stripped_spruce_log", wall="white_terracotta", base="stone_bricks", floor="oak_planks", roof="spruce", door="spruce", rug="red", bed="red", sofa="oak"),
    "birch": dict(log="stripped_birch_log", wall="birch_planks", base="mossy_cobblestone", floor="birch_planks", roof="cherry", door="cherry", rug="pink", bed="pink", sofa="cherry"),
    "dark":  dict(log="dark_oak_log", wall="stone_bricks", base="cobblestone", floor="dark_oak_planks", roof="deepslate_tile", door="dark_oak", rug="gray", bed="black", sofa="dark_oak"),
}
a = parse_args({"name": "cottage", "style": "oak"})
S = STYLES.get(a.style, STYLES["oak"])
roof_stairs = f"{S['roof']}_stairs"
roof_full = f"{S['roof']}_planks" if S["roof"] != "deepslate_tile" else "deepslate_tiles"
roof_slab = f"{S['roof']}_slab"
f = Frame(a.x, a.y, a.z, a.facing)
W, D, H = 8, 10, 4           # outer walls i 0..8, k 0..10, walls j 1..4

# ── 1. shell ───────────────────────────────────────────────────
house = Build()
f.box(house, (0, 0, 0), (W, 0, D), S["floor"])                               # the floor replaces the ground
f.walls(house, (0, 1, 0), (W, H, D), S["wall"])
f.walls(house, (0, 1, 0), (W, 1, D), S["base"])                              # base course
for i in range(0, W + 1):                                                    # log beam under the roof, front + back
    f.set(house, (i, H, 0), f"{S['log']}[axis={{axis_i}}]"); f.set(house, (i, H, D), f"{S['log']}[axis={{axis_i}}]")
for k in range(0, D + 1):                                                    # … and the sides
    f.set(house, (0, H, k), f"{S['log']}[axis={{axis_k}}]"); f.set(house, (W, H, k), f"{S['log']}[axis={{axis_k}}]")
for (i, k) in ((0, 0), (W, 0), (0, D), (W, D), (0, 5), (W, 5)):              # corner + middle posts
    f.box(house, (i, 1, k), (i, H, k), f"{S['log']}[axis=y]")
f.clear(house, (1, 1, 1), (W - 1, H + 5, D - 1))                             # hollow inside (vaulted: the roof is the ceiling)
P.window(house, f, 1, 2, 0, 2, 2)                                            # front windows
P.window(house, f, 6, 2, 0, 2, 2)
P.window(house, f, 0, 2, 6, 2, 2, along="k")                                 # left wall
P.window(house, f, W, 2, 7, 2, 2, along="k")                                 # right wall
P.window(house, f, 1, 2, D, 2, 2)                                            # back, above the bed
P.doorway(house, f, 4, 1, 0, S["door"], frame=None)
top = P.gable_roof(house, f, 0, 0, W, D, H + 1, stairs=roof_stairs, full=roof_full, slab=roof_slab, ridge="k", gable_fill=S["wall"])
f.box(house, (3, H + 1, -1), (5, H + 1, -1), f"{roof_stairs}[facing={{back}},half=top]")   # little canopy over the door

# ── 2. interior ────────────────────────────────────────────────
inside = Build()
P.fireplace(inside, f, 3, 1, D - 1, 3, chimney_to=top + 2)                   # back wall, chimney through the gable
P.sofa(inside, f, 3, 1, 6, 3, S["sofa"], faces="back")                       # facing the fire
P.rug(inside, f, 2, 1, 7, 6, 8, S["rug"])
P.bed(inside, f, 1, 1, D - 2, S["bed"], head="back")                         # back-left corner
P.lamp(inside, f, 2, 1, D - 1, "table")                                      # bedside candles
P.wardrobe(inside, f, 6, 1, D - 1, faces="front")
P.kitchen(inside, f.sub(W - 1, 0, 5, "left"), 0, 1, 0, length=4)             # along the right wall
P.dining_set(inside, f, 2, 1, 3, 2, "spruce", "oak")                         # left of the entry, path at i=4 stays free
P.bookshelf_wall(inside, f.sub(1, 0, 2, "right"), 0, 1, 0, width=2, height=2)   # left wall by the door
P.plant(inside, f, 7, 1, 1); P.plant(inside, f, 1, 1, 1, "potted_fern")
P.lamp(inside, f, 4, 1, 5, "hanging", ceiling_j=top, chain=top - H - 1)      # long chain from the ridge
P.lamp(inside, f, 4, 1, 2, "hanging", ceiling_j=top, chain=top - H - 1)

# ── 3. garden ──────────────────────────────────────────────────
garden = Build()
cells = [(i, k) for i in range(3, 6) for k in range(-7, 0)]
P.path(garden, [f.p(i, 0, k)[0::2] for (i, k) in cells], a.y, "dirt_path")    # paths go INTO the ground
f.set(garden, (4, 0, -1), "cobblestone_slab[type=top]")                     # door step flush with the path
for i in (2, 6):
    x, y, z = f.p(i, 1, -6); P.lamp_post(garden, x, y, z, "classic")
for (i1, i2) in ((0, 1), (7, 8)):
    c1, c2 = f.p(i1, 1, -5), f.p(i2, 1, -1)
    P.flower_bed(garden, min(c1[0], c2[0]), a.y + 1, min(c1[2], c2[2]), max(c1[0], c2[0]), max(c1[2], c2[2]), seed=i1)
for (i, k, kind) in ((-5, 3, "fancy_oak_bees_002"), (W + 5, 8, "birch_bees_002")):
    x, y, z = f.p(i, 1, k); garden.set((x, a.y, z), "grass_block"); garden.tree((x, y, z), kind)

files = house.save(f"{a.name}-1") + inside.save(f"{a.name}-2") + garden.save(f"{a.name}-3")
lo, hi = f.world_box((-6, 0, -7), (W + 6, top + 3, D + 1))
ent = f.p(4, 1, -2)
print(f"box {lo} -> {hi}; entrance (feet, outside the door) {[ent[0] + 0.5, ent[1], ent[2] + 0.5]}; files {files}")
