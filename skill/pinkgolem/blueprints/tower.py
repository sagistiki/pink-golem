"""tower.py — a round stone lookout tower: storeys with window slits, a spiral staircase through every floor, a
walkable crenellated roof with lanterns and a flag. The reference example for round builds and spiral stairs
(reference/round-and-tall.md, stairs.md).

    python3 skill/pinkgolem/blueprints/tower.py --at X,Y,Z --facing south [--style stone|sandstone|brick]
      X,Y,Z = the CENTRE of the tower at ground level; facing = the side with the door.
      options via --name; radius 4 (9 wide), 4 storeys, roof at +25.
    → jobs/tower.json
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from mclib import Build, DIRS, disk, ring, parse_args     # noqa: E402
import parts as P                                          # noqa: E402

STYLES = {"stone": ("stone_bricks", "spruce_planks", "mossy_stone_bricks"), "sandstone": ("cut_sandstone", "birch_planks", "chiseled_sandstone"),
          "brick": ("bricks", "dark_oak_planks", "stone_bricks")}
a = parse_args({"name": "tower", "style": "stone"})
wall, floor, accent = STYLES.get(a.style, STYLES["stone"])
cx, y, cz = a.x, a.y, a.z
R, STOREY, N = 4, 6, 4
b = Build()
t = P.round_tower(b, cx, y, cz, R, STOREY * N, wall=wall, floor=floor, window_every=5, floors_every=STOREY, roof="flat", door_facing=a.facing, stairs=False)
top = t["top"] - 1                                   # the roof floor level
# spiral from the ground all the way to the roof; its arrival cell stays solid, the rest of the 3x3 is a stair hole
arrive = P.spiral_stairs(b, cx, y + 1, top, cz, core="stripped_spruce_log[axis=y]", stairs="spruce_stairs")
for dx in (-1, 0, 1):
    for dz in (-1, 0, 1):
        if (dx, dz) not in ((0, 0), tuple(arrive)):
            b.set((cx + dx, top, cz + dz), "air")
b.set((cx, top, cz), "stripped_spruce_log[axis=y]")
# a base course and a band under the roof in the accent block (never over the door!)
door = t["door"]
for (x, z) in ring(cx, cz, R):
    if (x, z) != (door[0], door[2]):
        b.set((x, y + 1, z), accent)
    b.set((x, top - 1, z), accent)
# lanterns on the battlements, a flag
for (x, z) in ring(cx, cz, R):
    if b.get((x, top + 1, z)) and (x == cx or z == cz):
        b.set((x, top + 2, z), "lantern[hanging=false]")
fx, fz = cx - 2, cz - 2
for h in range(1, 6):
    b.set((fx, top + h, fz), "spruce_fence")
for dx in range(1, 4):
    for h in (4, 5):
        b.set((fx + dx, top + h, fz), "red_wool" if h == 5 else "white_wool")
# light: invisible light blocks in every storey (no mobs inside)
for fy in range(y, top, STOREY):
    for (dx, dz) in ((2, 0), (-2, 0), (0, 2), (0, -2)):
        b.set((cx + dx, fy + 3, cz + dz), "light[level=15]")
# a round path of gravel around the foot, the door step
for (x, z) in ring(cx, cz, R + 1):
    b.set((x, y, z), "gravel")
dx, dz = DIRS[a.facing]
b.set((cx + dx * (R + 1), y, cz + dz * (R + 1)), "cobblestone")
files = b.save(a.name)
print(f"box {[cx - R - 1, y, cz - R - 1]} -> {[cx + R + 1, top + 6, cz + R + 1]}; entrance (feet, outside the door) "
      f"{[door[0] + dx + 0.5, door[1], door[2] + dz + 0.5]}; roof at y {top + 1}; files {files}")
