"""modern_villa.py — a two-storey modern villa: white box on the ground floor with a full-height glass wall toward a
pool, a darker upper box cantilevered over the entrance, lights set into the ceilings, a straight staircase, a roof
terrace with a glass railing. The reference example for multi-storey builds (reference/houses.md, stairs.md).

    python3 skill/clawdblock/blueprints/modern_villa.py --at X,Y,Z --facing south [--style white|dark|wood]
      X,Y,Z = front-left corner at ground level. The pool deck extends 8 blocks in front, the upper floor 2 blocks
      to the right of the ground floor.
    → jobs/villa-1.json (structure), jobs/villa-2.json (interior), jobs/villa-3.json (pool + deck; water last)
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from mclib import Build, Frame, parse_args          # noqa: E402
import parts as P                                    # noqa: E402

STYLES = {
    "white": dict(wall="white_concrete", upper="light_gray_concrete", trim="black_concrete", floor="smooth_quartz", deck="dark_oak_planks", glass="glass", accent="dark_oak"),
    "dark":  dict(wall="black_concrete", upper="gray_concrete", trim="white_concrete", floor="polished_deepslate", deck="spruce_planks", glass="tinted_glass", accent="spruce"),
    "wood":  dict(wall="white_concrete", upper="stripped_dark_oak_wood", trim="black_concrete", floor="birch_planks", deck="stripped_oak_wood", glass="glass", accent="birch"),
}
a = parse_args({"name": "villa", "style": "white"})
S = STYLES.get(a.style, STYLES["white"])
f = Frame(a.x, a.y, a.z, a.facing)
GW, GD, H = 12, 8, 4          # ground floor i 0..12, k 0..8, walls j 1..4, slab j 5
UI1, UI2, UK1, UK2 = 4, 14, 1, 8   # upper floor box (cantilevers past i=12), walls j 6..9, roof j 10
LIGHT = "pearlescent_froglight"

# ── 1. structure ──────────────────────────────────────────────
s = Build()
f.box(s, (0, 0, 0), (GW, 0, GD), S["floor"])
f.walls(s, (0, 1, 0), (GW, H, GD), S["wall"])
f.clear(s, (1, 1, 1), (GW - 1, H, GD - 1))
f.box(s, (1, 1, 0), (7, H, 0), S["glass"])                                  # full-height glass wall toward the pool
f.box(s, (0, 1, 3), (0, 3, 5), S["glass"])                                  # side window
f.box(s, (0, H + 1, 0), (GW, H + 1, GD), S["floor"])                         # ceiling = upper floor
f.box(s, (UI1, H + 1, UK1), (UI2, H + 1, UK2), S["floor"])                   # upper floor also over the cantilever
f.walls(s, (UI1, H + 2, UK1), (UI2, H + 5, UK2), S["upper"])
f.clear(s, (UI1 + 1, H + 2, UK1 + 1), (UI2 - 1, H + 5, UK2 - 1))
f.box(s, (UI1 + 2, H + 3, UK1), (UI2 - 2, H + 4, UK1), S["glass"])          # upper glass band, front
f.box(s, (UI2, H + 3, UK1 + 2), (UI2, H + 4, UK2 - 2), S["glass"])          # … and side
P.flat_roof(s, f, UI1, UK1, UI2, UK2, H + 6, roof=S["upper"], overhang=1, trim=S["trim"])
f.walls(s, (0, H + 1, 0), (GW, H + 1, GD), S["trim"])                        # black band between the storeys
f.box(s, (UI1, H + 1, UK1), (UI2, H + 1, UK1), S["trim"])
rail = [(i, k) for i in range(0, UI1) for k in range(0, GD + 1) if i == 0 or k in (0, GD)] + [(i, 0) for i in range(UI1, GW + 1)]
rail += [(i, k) for i in (10, 12) for k in range(2, 5)]                     # around the stairwell upstairs
s.fence_ring([f.p(i, H + 2, k) for (i, k) in rail], "glass_pane")           # panes need explicit connections
P.doorway(s, f, 10, 1, 0, "dark_oak")                                        # front door under the cantilever
P.doorway(s, f, UI1, H + 2, 4, "dark_oak", into="right")                     # upper floor → roof terrace
# ceiling lights (flush) and lights under the cantilever
for (i, k) in ((3, 2), (3, 6), (9, 2), (9, 6), (6, 4)):
    f.set(s, (i, H + 1, k), LIGHT)
for (i, k) in ((7, 3), (11, 3), (7, 6), (11, 6)):
    f.set(s, (i, H + 6, k), LIGHT)
f.set(s, (13, H + 1, 1), LIGHT)

# ── 2. interior ───────────────────────────────────────────────
i_ = Build()
land = P.straight_stairs(i_, f, 11, 1, 1, H + 1, going="back", stairs="quartz_stairs", support=None)   # entrance hall → upstairs
P.sofa(i_, f, 2, 1, 3, 4, "quartz", faces="front")                           # looking out at the pool
P.rug(i_, f, 2, 1, 1, 5, 2, "light_gray")
P.table(i_, f, 3, 1, 1, style="glass")
P.kitchen(i_, f, 5, 1, GD - 1, 5, faces="front")
f.box(i_, (6, 1, 4), (8, 1, 4), "smooth_quartz")                             # kitchen island
P.plant(i_, f, 1, 1, 1, "potted_bamboo"); P.plant(i_, f, 1, 1, GD - 1, "potted_flowering_azalea_bush")
# upper floor: bedroom + study (the stairs arrive at i=11, k=6)
P.bed(i_, f, 6, H + 2, 6, "light_gray", head="back")
P.bed(i_, f, 7, H + 2, 6, "light_gray", head="back")
P.lamp(i_, f, 5, H + 2, 7, "table"); P.lamp(i_, f, 8, H + 2, 7, "table")
P.wardrobe(i_, f, 9, H + 2, 7, faces="front")
P.table(i_, f, 7, H + 2, 3, S["accent"], style="slab"); P.chair(i_, f, 7, H + 2, 4, S["accent"], faces="front")
P.plant(i_, f, 13, H + 2, 2, "potted_fern")
P.rug(i_, f, 5, H + 2, 3, 6, 4, "white")

# ── 3. pool deck + pool (water last) ──────────────────────────
p = Build()
f.box(p, (-1, 0, -8), (GW, 0, -1), S["deck"])                                # deck replaces the ground
lo, hi = f.world_box((1, 0, -6), (8, 0, -3))
P.pool(p, lo[0], lo[2], hi[0], hi[2], a.y, depth=3, rim="smooth_quartz", lining="light_blue_terracotta")
for i in (10, 11):
    P.chair(p, f, i, 1, -5, "quartz", faces="front")                         # sun loungers
for (i, k) in ((-1, -8), (GW, -8), (GW, -1)):
    x, y, z = f.p(i, 1, k); P.lamp_post(p, x, y, z, "modern")

files = s.save(f"{a.name}-1") + i_.save(f"{a.name}-2") + p.save(f"{a.name}-3")
blo, bhi = f.world_box((-1, 0, -8), (UI2 + 1, H + 7, GD))
ent = f.p(10, 1, -2)
print(f"box {blo} -> {bhi}; entrance (feet, outside the front door) {[ent[0] + 0.5, ent[1], ent[2] + 0.5]}; upper landing {f.p(*land)}; files {files}")
