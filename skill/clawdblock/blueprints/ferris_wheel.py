"""ferris_wheel.py — a classic colourful Ferris wheel that really turns and that players ride, with no mods.
The static part: white A-frame legs with red braces and an iron axle, a red/white fairground plaza with a yellow ring,
the boarding station (gold BOARD pad west of the bottom cabin, emerald EXIT pad east of it, glass queue rails), a
ticket booth, a cotton-candy stand, benches, flower beds, lamps and a big sign over the wheel.
The moving wheel, the 8 cabins and the chasing lights are display entities run by scarpet-apps/ferris.sc
(reference/displays.md, "Rotating assemblies").

    python3 skill/clawdblock/blueprints/ferris_wheel.py --at X,Y,Z
      X,Y,Z = the ground block UNDER THE AXLE (Y = the ground level, -61 on the default flat world).
      --facing is accepted but ignored: the wheel always turns in the x-y plane (you see it face-on from north/south),
      boarding on the west side of the bottom cabin, exit on the east side.
      Footprint: x X-14..X+15, z Z-9..Z+10; up to Y+30 (axle at Y+14, wheel radius 11, sign at Y+29).
      The site must be clear up to Y+27 within 12 blocks of the axle in x-y: the cabins swing through it.
    → jobs/ferris_wheel-1-ground.json (plaza, pads, booths, benches, lamps), -2-frame (legs, axle, sign); the last job
      loads the ferris app and calls setup(X, Y, Z). Stand on the gold pad and wait for the next stop.
"""
import os
import random
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from mclib import Build, parse_args      # noqa: E402
import parts as P                        # noqa: E402

a = parse_args({"name": "ferris_wheel"})
X, G, Z = a.x, a.y, a.z
AY = G + 14                               # the axle block (centre X+0.5, G+14.5, Z+0.5)
TAG = "fw_static"
rnd = random.Random(a.seed)

# ───────────── ground: plaza, station, stands ─────────────
ground = Build()
ground.before(f"kill @e[tag={TAG}]")
for x in range(X - 14, X + 16):
    for z in range(Z - 9, Z + 11):
        ring = abs(x - X) <= 13 and abs(z - Z) <= 5 and not (abs(x - X) <= 12 and abs(z - Z) <= 4)
        ground.set((x, G, z), "yellow_concrete" if ring else ("red_concrete" if (x + z) % 2 else "white_concrete"))
# boarding station: gold BOARD pad (west of the bottom cabin), emerald EXIT pad (east), queue rails
for z in (Z - 1, Z, Z + 1):
    for x in (X - 3, X - 2):
        ground.set((x, G, z), "gold_block")
    for x in (X + 3, X + 4):
        ground.set((x, G, z), "emerald_block")
ground.fence_ring([(x, G + 1, z) for x in range(X - 8, X - 1) for z in (Z - 2, Z + 2)], "white_stained_glass_pane")
P.label(ground, X - 2.0, G + 2.6, Z + 0.5, "★ BOARD ★", tag=TAG, color="gold", scale=0.55)
P.label(ground, X + 4.0, G + 2.6, Z + 0.5, "EXIT", tag=TAG, color="green", scale=0.5)
# ticket booth (north-west) and cotton-candy stand (north-east): striped walls, a window, an awning
for (x0, z0, awn, name, col) in ((X - 12, Z - 7, "red", "TICKETS", "gold"), (X + 12, Z - 7, "pink", "COTTON CANDY", "light_purple")):
    for x in range(x0, x0 + 3):
        for z in range(z0, z0 + 3):
            if x in (x0, x0 + 2) or z in (z0, z0 + 2):
                stripe = "white_concrete" if (x + z) % 2 else f"{awn}_concrete"
                ground.set((x, G + 1, z), stripe)
                ground.set((x, G + 2, z), "glass" if (z == z0 + 2 and x == x0 + 1) else stripe)
        for z in range(z0 - 1, z0 + 4):
            ground.set((x, G + 3, z), f"{awn}_wool" if (x + z) % 2 else "white_wool")
    for x in range(x0 - 1, x0 + 4):
        ground.set((x, G + 3, z0 + 3), f"{awn}_wool" if x % 2 else "white_wool")
    ground.set((x0 + 1, G + 1, z0 + 2), "air")
    ground.set((x0 + 1, G + 1, z0 + 3), "spruce_trapdoor[half=top,facing=north]")   # the counter
    P.label(ground, x0 + 1.5, G + 4.2, z0 + 1.5, name, tag=TAG, color=col, scale=0.6)
for x in range(X + 12, X + 15):
    ground.set((x, G + 4, Z - 6), "pink_wool")                                     # the candy-floss "cloud"
# benches, flowers, lamps
for (dx, dz, face) in ((-11, 4, "west"), (-11, 7, "west"), (12, 4, "east"), (12, 7, "east")):
    ground.set((X + dx, G + 1, Z + dz), f"dark_oak_stairs[facing={face}]")
for (x1, z1, x2, z2) in ((-14, 8, -10, 10), (11, 8, 15, 10), (-14, -9, -13, -8), (14, -9, 15, -8)):
    P.flower_bed(ground, X + x1, G + 1, Z + z1, X + x2, Z + z2, seed=rnd.randint(1, 99), soil="grass_block")
for (dx, dz) in ((-14, -2), (-14, 3), (15, -2), (15, 3), (-3, -9), (4, -9), (-3, 10), (4, 10)):
    P.lamp_post(ground, X + dx, G + 1, Z + dz, "classic")

# ───────────── frame: A-frame legs on both sides of the wheel, the axle, the sign ─────────────
frame = Build()
for z in (Z - 3, Z + 4):
    for x0 in (X - 7, X + 7):
        frame.line((x0, G + 1, z), (X, AY, z), "white_concrete")
        frame.set((x0, G, z), "polished_blackstone")
    frame.line((X - 4, G + 7, z), (X + 4, G + 7, z), "red_concrete")                # cross brace
for z in range(Z - 3, Z + 5):
    frame.set((X, AY, z), "gold_block" if z in (Z - 3, Z + 4) else "iron_block")
frame.cmd(f'summon text_display {X + 0.5} {G + 28.8} {Z + 0.5} {{billboard:"vertical",Tags:["{TAG}"],alignment:"center",background:0,shadow:1b,'
          'brightness:{sky:15,block:15},transformation:{left_rotation:[0f,0f,0f,1f],right_rotation:[0f,0f,0f,1f],translation:[0f,0f,0f],scale:[4f,4f,4f]},'
          'text:[{"text":"★ ","color":"yellow","bold":true},{"text":"FERRIS WHEEL","color":"red","bold":true},{"text":" ★","color":"yellow","bold":true}]}')
frame.cmd("script load ferris")
frame.cmd(f"script in ferris run setup({X}, {G}, {Z})")

files = ground.save(f"{a.name}-1-ground") + frame.save(f"{a.name}-2-frame")

# install the app into the world's scripts folder (the MCP sets CLAWDBLOCK_CU_DATA to <world>/scripts/cu.data)
cu = os.environ.get("CLAWDBLOCK_CU_DATA")
if cu:
    scripts = os.path.dirname(cu)
    src = os.path.join(os.path.dirname(__file__), "..", "..", "..", "scarpet-apps", "ferris.sc")
    if os.path.exists(src) and not os.path.exists(os.path.join(scripts, "ferris.sc")):
        os.makedirs(scripts, exist_ok=True)
        shutil.copy(src, os.path.join(scripts, "ferris.sc"))

lo, hi = [X - 14, G, Z - 9], [X + 15, G + 30, Z + 10]
print(f"box {lo} -> {hi}; board pad {[X - 3, G, Z - 1]} -> {[X - 2, G, Z + 1]}; exit {[X + 3.5, G + 1, Z + 0.5]}; files {files}")
