"""tnt_run.py — a TNT Run arena with its game: four round floors of coloured blocks, each over a layer of TNT, inside a
glass wall with quartz columns, and a water pit at the bottom. Every block you step on turns red and vanishes; fall
through all four floors and you are out. On the north side: a lobby plaza with a gold JOIN pad under a striped canopy,
two giant TNT blocks, a rules board and the records board, plus stairs up to a viewing gallery above the lobby.
The game itself is scarpet-apps/tntrun.sc (join by standing on the pad, 10 s countdown, last one standing wins).

    python3 skill/pinkgolem/blueprints/tnt_run.py --at X,Y,Z
      X,Y,Z = the CENTRE of the arena on the ground block (Y = the ground level, -61 on the default flat world).
      --facing is accepted but ignored: the lobby is always on the NORTH side (-z).
      Footprint: x X-19..X+19, z Z-36..Z+18 (the plaza reaches 36 blocks north of the centre); up to Y+40.
      The floors are at Y+30, Y+23, Y+16 and Y+9; the pit is 2 blocks deep below the ground.
    → jobs/tnt_run-1-site.json (plaza, pad, canopy, stairs, gallery), -2-arena (pit, wall, lights), -3-floors,
      -4-deco (giant TNT, signs); the last job loads the tntrun app and calls setup(X, Y, Z) so the game knows
      where the arena is. Step on the gold pad to play.

Keep pattern() in sync with _pat() in scarpet-apps/tntrun.sc: the app rebuilds the floors after every game.
"""
import json
import math
import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from mclib import Build, parse_args      # noqa: E402

a = parse_args({"name": "tnt_run"})
CX, G, CZ = a.x, a.y, a.z
R_FLOOR, R_WALL = 16.4, 17
FLOORS = [G + 30, G + 23, G + 16, G + 9]      # top → bottom
TOP = G + 36                                  # top rim of the glass wall
GY = G + 16                                   # the viewing gallery deck
TAG = "tr_static"


def pattern(k, dx, dz):
    """Top block of floor k at offset (dx, dz) — the same formulas live in tntrun.sc (_pat)."""
    r = math.hypot(dx, dz)
    ang = math.degrees(math.atan2(dz, dx)) % 360
    if k == 0:
        return "pink_concrete" if int(r) % 4 < 2 else "white_concrete"
    if k == 1:
        return "yellow_concrete" if (math.floor(dx / 2) + math.floor(dz / 2)) % 2 == 0 else "orange_concrete"
    if k == 2:
        return "lime_concrete" if int((ang + r * 14) / 30) % 2 == 0 else "light_blue_concrete"
    return "purple_concrete" if int(ang / 22.5) % 2 == 0 else "magenta_concrete"


def label(b, p, text, scale=0.6, bb="center", bg=1426063360):
    b.cmd(f'summon text_display {p[0]} {p[1]} {p[2]} {{billboard:"{bb}",Tags:["{TAG}"],alignment:"center",background:{bg},shadow:1b,line_width:240,'
          f'brightness:{{sky:15,block:15}},transformation:{{left_rotation:[0f,0f,0f,1f],right_rotation:[0f,0f,0f,1f],translation:[0f,0f,0f],'
          f'scale:[{scale}f,{scale}f,{scale}f]}},text:{text}}}')


# ═══════════════════════════ 1. SITE: lobby plaza, JOIN pad, canopy, stairs, gallery ═══════════════════════════
site = Build()
site.before(f"kill @e[tag={TAG}]")
# lobby plaza (dx -14..14, dz -36..-24): quartz with a red/white checker border
for dx in range(-14, 15):
    for dz in range(-36, -23):
        edge = dx in (-14, 14) or dz in (-36, -24)
        site.set((CX + dx, G, CZ + dz), ("red_concrete" if (dx + dz) % 2 else "white_concrete") if edge
                 else ("smooth_quartz" if (dx + dz) % 4 else "quartz_bricks"))
# JOIN pad 5x5 centred on (CX, CZ-30), under a striped canopy on four quartz pillars
for dx in range(-2, 3):
    for dz in range(-32, -27):
        site.set((CX + dx, G, CZ + dz), "gold_block" if dx in (-2, 2) or dz in (-32, -28) else "yellow_glazed_terracotta")
for (dx, dz) in ((-3, -33), (3, -33), (-3, -27), (3, -27)):
    for y in range(G + 1, G + 5):
        site.set((CX + dx, y, CZ + dz), "quartz_pillar")
    site.set((CX + dx, G + 5, CZ + dz), "sea_lantern")
for dx in range(-4, 5):
    for dz in range(-34, -25):
        site.set((CX + dx, G + 6, CZ + dz), "red_wool" if (dx // 2) % 2 else "white_wool")
# stairs (dx 16..17) from the plaza's north-east corner up to the gallery landing: a solid quartz ramp, glass rail
for k in range(1, 16):
    z, y = CZ - 37 + k, G + k
    for dx in (16, 17):
        for yy in range(G + 1, y):
            site.set((CX + dx, yy, z), "smooth_quartz")
        site.set((CX + dx, y, z), "quartz_stairs[facing=south,half=bottom]")
    site.set((CX + 18, y, z), "smooth_quartz")
    site.set((CX + 18, y + 1, z), "white_stained_glass")
# viewing gallery (dx -12..14, dz -23..-18) at GY + a landing (dx 15..17, dz -21..-18); 2-high glass rail; pillars
deck = lambda dx, dz: (-12 <= dx <= 14 and -23 <= dz <= -18) or (15 <= dx <= 17 and -21 <= dz <= -18)
for dx in range(-13, 19):
    for dz in range(-24, -16):
        if deck(dx, dz):
            site.set((CX + dx, GY, CZ + dz), "smooth_quartz" if (dx + dz) % 3 else "quartz_bricks")
            continue
        if 16 <= dx <= 17 and dz <= -22:
            continue                                  # the stairs come up here
        if math.hypot(dx, dz) <= R_WALL + 0.5:
            continue                                  # the arena wall is the rail there
        site.set((CX + dx, GY, CZ + dz), "smooth_quartz")
        for y in (GY + 1, GY + 2):
            site.set((CX + dx, y, CZ + dz), "white_stained_glass")
for k in range(2, 16):                                # rail on the open side of the stairs
    site.set((CX + 15, G + k + 1, CZ - 37 + k), "white_stained_glass")
for (dx, dz) in ((-12, -23), (-12, -18), (1, -23), (14, -23), (14, -18), (17, -18)):
    for y in range(G + 1, GY):
        site.set((CX + dx, y, CZ + dz), "quartz_pillar")
for dx in range(-10, 17, 6):
    site.set((CX + dx, GY + 1, CZ - 23), "lantern")

# ═══════════════════════════ 2. ARENA: pit, glass wall, columns, rim, lights ═══════════════════════════
arena = Build()
glass_by_level = [(FLOORS[0], TOP, "pink_stained_glass"), (FLOORS[1], FLOORS[0], "yellow_stained_glass"),
                  (FLOORS[2], FLOORS[1], "lime_stained_glass"), (FLOORS[3], FLOORS[2], "purple_stained_glass"),
                  (G, FLOORS[3], "light_blue_stained_glass")]
for dx in range(-19, 20):
    for dz in range(-19, 20):
        d = math.hypot(dx, dz)
        x, z = CX + dx, CZ + dz
        if d <= R_FLOOR + 0.1:
            arena.set((x, G - 2, z), "sand")
            arena.set((x, G - 1, z), "water")
            arena.set((x, G, z), "water")
        elif d <= R_WALL + 0.5:
            ang = math.degrees(math.atan2(dz, dx)) % 360
            column = min(ang % 45, 45 - ang % 45) < 3.2
            for y in range(G - 2, TOP + 1):
                if y <= G:
                    blk = "smooth_quartz"
                elif column:
                    blk = "sea_lantern" if y in [f + 1 for f in FLOORS] else "quartz_pillar"
                elif y in FLOORS or y in [f - 1 for f in FLOORS] or y == TOP:
                    blk = "smooth_quartz"
                else:
                    blk = next(g for (lo, hi, g) in glass_by_level if lo < y < hi)
                arena.set((x, y, z), blk)
            if column:
                arena.set((x, TOP + 1, z), "lantern")
# hidden light over every floor and in the pit (no dark spots, no mobs)
for f in FLOORS + [G + 2]:
    for (dx, dz) in [(0, 0)] + [(round(10 * math.cos(math.radians(t))), round(10 * math.sin(math.radians(t)))) for t in range(0, 360, 45)]:
        arena.set((CX + dx, f + 3, CZ + dz), "light[level=15]")

# ═══════════════════════════ 3. FLOORS: coloured blocks over TNT ═══════════════════════════
floors = Build()
for k, y in enumerate(FLOORS):
    for dx in range(-17, 18):
        for dz in range(-17, 18):
            if math.hypot(dx, dz) <= R_FLOOR:
                floors.set((CX + dx, y, CZ + dz), pattern(k, dx, dz))
                floors.set((CX + dx, y - 1, CZ + dz), "tnt")

# ═══════════════════════════ 4. DECO: giant TNT, signs, the game app ═══════════════════════════
deco = Build()
for x0 in (CX - 14, CX + 12):                         # two giant TNT blocks on the plaza's north corners
    for x in range(x0, x0 + 3):
        for y in range(G + 1, G + 4):
            for z in range(CZ - 36, CZ - 33):
                deco.set((x, y, z), "tnt")
    deco.set((x0 + 1, G + 4, CZ - 35), "lightning_rod")
red_white = lambda t1, t2: json.dumps([{"text": t1, "color": "red", "bold": True}, {"text": t2, "color": "white", "bold": True}])
deco.cmd(f'summon text_display {CX + 0.5} {G + 40} {CZ - 17.5} {{billboard:"vertical",Tags:["{TAG}"],alignment:"center",background:0,shadow:1b,'
         f'brightness:{{sky:15,block:15}},transformation:{{left_rotation:[0f,0f,0f,1f],right_rotation:[0f,0f,0f,1f],translation:[0f,0f,0f],scale:[8f,8f,8f]}},'
         f'text:{red_white("TNT", " RUN")}}}')
label(deco, (CX + 0.5, G + 7.0, CZ - 29.5), red_white("STAND HERE ", "TO JOIN"), 0.7)
rules = json.dumps([{"text": "TNT RUN\n", "color": "red", "bold": True},
                    {"text": "Every block you step on vanishes!\n", "color": "white"},
                    {"text": "Fall below the last floor and you're out\n", "color": "white"},
                    {"text": "Shift in the air = double jump (3 per game)\n", "color": "yellow"},
                    {"text": "Solo: beat your time · Together: last one standing wins", "color": "gold"}], ensure_ascii=False)
label(deco, (CX - 9.5, G + 4.0, CZ - 29.5), rules, 0.55)
# the records board (tag tr_board) is summoned by the app at (CX + 10.5, G + 3.8, CZ - 29.5), mirroring the rules
label(deco, (CX + 15.5, GY + 1.0, CZ - 20.5), json.dumps({"text": "VIEWING GALLERY", "color": "aqua", "bold": True}), 0.5)
deco.cmd("script load tntrun")
deco.cmd(f"script in tntrun run setup({CX}, {G}, {CZ})")

files = site.save(f"{a.name}-1-site") + arena.save(f"{a.name}-2-arena") + floors.save(f"{a.name}-3-floors") + deco.save(f"{a.name}-4-deco")

# install the game app into the world's scripts folder (the MCP sets PINKGOLEM_CU_DATA to <world>/scripts/cu.data)
cu = os.environ.get("PINKGOLEM_CU_DATA")
if cu:
    scripts = os.path.dirname(cu)
    src = os.path.join(os.path.dirname(__file__), "..", "..", "..", "scarpet-apps", "tntrun.sc")
    if os.path.exists(src) and not os.path.exists(os.path.join(scripts, "tntrun.sc")):
        os.makedirs(scripts, exist_ok=True)
        shutil.copy(src, os.path.join(scripts, "tntrun.sc"))

lo, hi = [CX - 19, G - 2, CZ - 36], [CX + 19, G + 41, CZ + 18]
print(f"box {lo} -> {hi}; entrance {[CX + 0.5, G + 1, CZ - 37.5]}; join pad {[CX - 2, G, CZ - 32]} -> {[CX + 2, G, CZ - 28]}; files {files}")
