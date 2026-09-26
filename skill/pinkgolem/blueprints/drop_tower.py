"""drop_tower.py — a round glass-and-concrete tower you ride UP on a launch pad and jump DOWN through a free-fall
shaft lined with a colour spiral, into a pool. At night lamps glow behind its windows. The reference example for
tall builds, the clone trick, hidden light layers and game logic (reference/round-and-tall.md, game-logic.md).

    python3 skill/pinkgolem/blueprints/drop_tower.py --at X,Y,Z --facing south [--style pride|ocean|sunset]
      X,Y,Z = the CENTRE of the tower at ground level; facing = the side with the entrance.
      --height 60 (roof above ground), radius 8 (17 wide). The site must be clear: the clone trick copies every
      non-air block of the first 24-block period up the tower.
    → jobs/drop_tower-1.json (shell + spiral), -2 (lamps), -3 (roof, pool, pad, signs) and launchpad.data/pads.json;
      installs + reloads the launchpad app. Walk in, step on the gold plate.
"""
import argparse
import json
import math
import os
import random
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from mclib import Build, DIRS, disk, rainbow, text_json      # noqa: E402

PALETTES = {"pride": ["red", "orange", "yellow", "lime", "blue", "purple"],
            "ocean": ["light_blue", "cyan", "blue", "white", "light_blue", "cyan"],
            "sunset": ["yellow", "orange", "red", "magenta", "purple", "pink"]}
LAMPS = ["sea_lantern"] * 7 + ["ochre_froglight"] * 5 + ["pearlescent_froglight"] * 3 + ["glowstone"] * 3 + ["shroomlight"] * 2

ap = argparse.ArgumentParser()
ap.add_argument("--at", required=True); ap.add_argument("--facing", default="south", choices=list(DIRS))
ap.add_argument("--style", default="pride", choices=list(PALETTES)); ap.add_argument("--height", type=int, default=60)
ap.add_argument("--radius", type=int, default=8); ap.add_argument("--name", default="drop_tower"); ap.add_argument("--seed", type=int, default=7)
a = ap.parse_args()
CX, Y0, CZ = (int(float(v)) for v in a.at.split(","))
R, TOP = a.radius, Y0 + a.height
COL = PALETTES[a.style]
BAND, PERIOD = 4, 24
fx, fz = DIRS[a.facing]
rnd = random.Random(a.seed)

# ── rings: shell (r), lamp layer (touching the shell), colour lining (touching the layer), the free shaft inside
pts = []
for t in range(3600):
    p = (int(round(CX + R * math.cos(math.radians(t / 10)))), int(round(CZ + R * math.sin(math.radians(t / 10)))))
    if p not in pts:
        pts.append(p)
shell = set(pts)
windows = [p for n, p in enumerate(pts) if n % 3 == 2]
inside = {(x, z) for (x, z) in disk(CX, CZ, R) if (x, z) not in shell and math.hypot(x - CX, z - CZ) < R}
near = lambda c, s: any((c[0] + dx, c[1] + dz) in s for dx in (-1, 0, 1) for dz in (-1, 0, 1))
layer = {c for c in inside if near(c, shell)}
lining = {c for c in inside - layer if near(c, layer)}
shaft = inside - layer - lining
dist = lambda x, z: math.hypot(x - CX, z - CZ)
# entrance: 3 wide, 3 high, straight through shell + layer + lining on the facing side
along = lambda x, z: (x - CX) * fx + (z - CZ) * fz
side = lambda x, z: (x - CX) * fz - (z - CZ) * fx if fx == 0 else (z - CZ) * fx
def entrance(x, y, z):
    return along(x, z) >= R - 4 and abs(side(x, z)) <= 1 and Y0 + 1 <= y <= Y0 + 3
def frame(x, y, z):
    return along(x, z) >= R - 4 and abs(side(x, z)) <= 2 and Y0 + 1 <= y <= Y0 + 4 and not entrance(x, y, z)

# ── 1. shell, ground floor, colour spiral (one 24-block period, then masked clones) ──
b = Build()
for (x, z) in disk(CX, CZ, R):
    b.set((x, Y0, z), "smooth_quartz")
MASTER = Y0 + 5
last = min(TOP - 1, MASTER + PERIOD - 1)
for y in range(Y0 + 1, last + 1):
    for (x, z) in shell | layer | lining:
        if entrance(x, y, z):
            b.set((x, y, z), "air"); continue
        if frame(x, y, z) and (x, z) in shell | layer | lining:
            b.set((x, y, z), "smooth_quartz"); continue
        if (x, z) in shell:
            b.set((x, y, z), "tinted_glass" if (x, z) in windows else "white_concrete")
        elif (x, z) in lining:
            frac = (math.degrees(math.atan2(z - CZ, x - CX)) % 360) / 360
            b.set((x, y, z), f"{COL[5 - int(math.floor(frac * 6 + (y - Y0) / BAND)) % 6]}_concrete")
for dy in range(MASTER + PERIOD, TOP, PERIOD):
    h = min(PERIOD, TOP - dy)
    b.cmd(f"clone {CX - R} {MASTER} {CZ - R} {CX + R} {MASTER + h - 1} {CZ + R} {CX - R} {dy} {CZ - R} masked")

# ── 2. lamps behind the windows: "office floors" of 3 blocks, ~75% lit, random lamp colours (placed after the clones)
lamps = Build()
owner = {}
for w in windows:
    for c in sorted(layer):
        if c not in owner and near(c, {w}):
            owner[c] = w
for w in windows:
    pattern = [(fy, rnd.choice(LAMPS) if rnd.random() < 0.75 else None) for fy in range(Y0 + 1, TOP, 3)]
    for (x, z), o in owner.items():
        if o != w:
            continue
        for fy, lamp in pattern:
            for y in range(fy, min(fy + 3, TOP)):
                if lamp and not entrance(x, y, z) and not frame(x, y, z):
                    lamps.set((x, y, z), lamp)
for n, y in enumerate(range(Y0 + 3, TOP - 1, 6)):                      # invisible light in the shaft
    for j in range(6):
        ang = math.radians(j * 60 + (30 if n % 2 else 0))
        lamps.set((int(round(CX + (R - 3) * math.cos(ang))), y, int(round(CZ + (R - 3) * math.sin(ang)))), "light[level=15]")

# ── 3. roof with a hole and colour rings, the pool, the pad, signs ──
t = Build()
for (x, z) in disk(CX, CZ, R):
    d = dist(x, z)
    t.set((x, TOP, z), "air" if d <= 2.5 else f"{COL[min(5, int(d - 2.5))]}_concrete" if d <= 8.5 and d < R - 0.5 else "gray_concrete")
t.fence_ring([(x, TOP + 1, z) for (x, z) in shell], "iron_bars")
pool_r = R - 4.5
for (x, z) in disk(CX, CZ, R):
    d = dist(x, z)
    if d <= pool_r:
        t.set((x, Y0 - 2, z), f"{COL[min(5, int(d // 1.5))]}_concrete")
        t.set((x, Y0 - 1, z), "water"); t.set((x, Y0, z), "water")
    elif d <= pool_r + 1:
        t.set((x, Y0 - 2, z), "smooth_quartz"); t.set((x, Y0 - 1, z), "smooth_quartz")
pad = (CX + fx * (R - 4), Y0 + 1, CZ + fz * (R - 4))
t.set(pad, "light_weighted_pressure_plate")
t.before("kill @e[type=text_display,tag=%s]" % a.name)
t.text_display((pad[0] + 0.5 - fx * 0.5, Y0 + 3.4, pad[2] + 0.5 - fz * 0.5), rainbow("DROP TOWER"), a.name, 1.1)
t.text_display((pad[0] + 0.5 - fx * 0.5, Y0 + 2.8, pad[2] + 0.5 - fz * 0.5), text_json("step on the gold plate"), a.name, 0.7)
t.text_display((CX + 0.5, TOP + 3.5, CZ + 0.5), rainbow("JUMP!"), a.name, 2.5)
yaw = {"south": 180, "north": 0, "east": 90, "west": -90}[a.facing]      # face the centre from the entrance side
top_spot = [CX + fx * (R - 2) + 0.5, TOP + 1, CZ + fz * (R - 2) + 0.5, yaw, 35]
t.cmd("script load launchpad")

files = b.save(f"{a.name}-1") + lamps.save(f"{a.name}-2") + t.save(f"{a.name}-3")

# the launch pad app + its config live in the world's scripts folder
cu = os.environ.get("PINKGOLEM_CU_DATA")
if cu:
    scripts = os.path.dirname(cu)
    src = os.path.join(os.path.dirname(__file__), "..", "..", "..", "scarpet-apps", "launchpad.sc")
    if os.path.exists(src) and not os.path.exists(os.path.join(scripts, "launchpad.sc")):
        shutil.copy(src, os.path.join(scripts, "launchpad.sc"))
    dd = os.path.join(scripts, "launchpad.data")
    os.makedirs(dd, exist_ok=True)
    pf = os.path.join(dd, "pads.json")
    pads = [p for p in (json.load(open(pf)) if os.path.exists(pf) else []) if p.get("name") != a.name]
    pads.append({"name": a.name, "pad": list(pad), "top": top_spot, "top_y": TOP + 1, "hole": [CX, CZ, 2.5], "pool": [CX, CZ, pool_r, Y0]})
    json.dump(pads, open(pf, "w"), indent=1)
print(f"box {[CX - R, Y0 - 2, CZ - R]} -> {[CX + R, TOP + 4, CZ + R]}; entrance {[pad[0] + fx * 5 + 0.5, Y0 + 1, pad[2] + fz * 5 + 0.5]}; pad {pad}; files {files}")
