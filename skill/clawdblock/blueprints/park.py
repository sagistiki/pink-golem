"""park.py — a small town park: low stone wall with entrances on all four sides, a crossing gravel path with a loop,
a fountain in the middle, a pond with a shore, trees packed at random (not on a grid), flower beds, benches facing
the paths and lamp posts along them. The reference example for landscaping (reference/landscaping.md).

    python3 skill/clawdblock/blueprints/park.py --at X,Y,Z --facing south
      X,Y,Z = the front-left corner at ground level. Size 41 x 31 (i x k).
    → jobs/park-1.json (ground, paths, wall, water last) + jobs/park-2.json (trees, plants, furniture)
"""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from mclib import Build, Frame, parse_args           # noqa: E402
import parts as P                                     # noqa: E402

a = parse_args({"name": "park"})
rnd = random.Random(a.seed)
f = Frame(a.x, a.y, a.z, a.facing)
W, D = 40, 30
ci, ck = W // 2, D // 2
g = Build()           # ground + hard landscaping
v = Build()           # living things + furniture

# ground: fresh grass everywhere (levels old holes), low wall with 3-wide gaps in the middle of every side
f.box(g, (0, -2, 0), (W, -1, D), "dirt")
f.box(g, (0, 0, 0), (W, 0, D), "grass_block")
for i in range(W + 1):
    for k in range(D + 1):
        if i in (0, W) or k in (0, D):
            gap = (abs(i - ci) <= 1 and k in (0, D)) or (abs(k - ck) <= 1 and i in (0, W))
            if not gap:
                f.set(g, (i, 1, k), "mossy_stone_brick_wall")
# walls need connections: rebuild the ring with explicit states
ring_cells = [f.p(i, 1, k) for i in range(W + 1) for k in range(D + 1) if (i in (0, W) or k in (0, D)) and g.get(f.p(i, 1, k))]
g.fence_ring(ring_cells, "mossy_stone_brick_wall")

# paths (IN the ground): a cross through the entrances + a loop around the fountain
path = set()
for i in range(0, W + 1):
    for k in range(ck - 1, ck + 2):
        path.add((i, k))
for k in range(0, D + 1):
    for i in range(ci - 1, ci + 2):
        path.add((i, k))
for i in range(ci - 7, ci + 8):
    for k in range(ck - 6, ck + 7):
        d = ((i - ci) / 7.5) ** 2 + ((k - ck) / 6.5) ** 2
        if 0.62 <= d <= 1.0:
            path.add((i, k))
P.path(g, [f.p(i, 0, k)[0::2] for (i, k) in path], a.y, "gravel")
# fountain in the middle
x, y, z = f.p(ci, 1, ck)
P.fountain(g, x, y, z, r=3)
# pond in the back-left quarter (water in this job, after everything around it)
px, _, pz = f.p(9, 0, D - 8)
P.pond(g, px, a.y, pz, rx=5, rz=4, depth=2, seed=a.seed)
pond_cells = {(i, k) for i in range(2, 17) for k in range(D - 14, D - 1)}

# flower beds in the front quarters
for (i1, k1) in ((4, 3), (W - 12, 3)):
    c1, c2 = f.p(i1, 1, k1), f.p(i1 + 8, 1, k1 + 5)
    P.flower_bed(v, min(c1[0], c2[0]), a.y + 1, min(c1[2], c2[2]), max(c1[0], c2[0]), max(c1[2], c2[2]), seed=i1)
beds = {(i, k) for (i1, k1) in ((4, 3), (W - 12, 3)) for i in range(i1 - 1, i1 + 10) for k in range(k1 - 1, k1 + 7)}

# benches facing the loop, lamps along the cross path
for i in (5, 9, W - 10, W - 6):                       # both sides of the main path, facing it
    P.bench(v, f, i, 1, ck - 2, 2, "spruce", faces="back")
    P.bench(v, f, i, 1, ck + 2, 2, "spruce", faces="front")
for n in range(4, W, 8):
    for k in (ck - 3, ck + 3):
        x, y, z = f.p(n, 1, k); P.lamp_post(v, x, y, z, "classic")
for n in range(4, D, 8):
    for i in (ci - 3, ci + 3):
        x, y, z = f.p(i, 1, n)
        if abs(n - ck) > 7:
            P.lamp_post(v, x, y, z, "classic")

# trees: random packing on free grass (≥ 1 from paths and beds, clear of the pond, the wall and the fountain)
blocked = set(pond_cells)
for (i, k) in path | beds:
    for di in range(-1, 2):
        for dk in range(-1, 2):
            blocked.add((i + di, k + dk))
free = [(i, k) for i in range(3, W - 2) for k in range(3, D - 2) if (i, k) not in blocked and abs(i - ci) + abs(k - ck) > 9]
cells = [f.p(i, 1, k)[0::2] for (i, k) in free]
P.trees(v, cells, a.y + 1, kinds=("oak_bees_002", "birch_bees_002", "fancy_oak_bees_002", "cherry_bees_005"), seed=a.seed, spacing=4)
# undergrowth: a few bushes and ferns
for (i, k) in rnd.sample(free, min(30, len(free))):
    f.set(v, (i, 1, k), rnd.choice(["fern", "azalea", "flowering_azalea", "short_grass", "bush"]))

files = g.save(f"{a.name}-1") + v.save(f"{a.name}-2")
lo, hi = f.world_box((0, 0, 0), (W, 12, D))
ent = f.p(ci, 1, -1)
print(f"box {lo} -> {hi}; main entrance {[ent[0] + 0.5, ent[1], ent[2] + 0.5]}; files {files}")
