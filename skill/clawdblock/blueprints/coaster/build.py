"""build.py — a steel roller coaster that really runs, with no client mods: the track is block_display boxes stretched
and turned along a smooth curve (not voxels), the train is 5 item_display cars from a small resource pack (pack.py),
and coaster.sc drives it with real physics, first-person camera, loop and all. Read README.md in this folder first.

    python3 skill/clawdblock/blueprints/coaster/build.py --at X,Y,Z --facing east
      X,Y,Z  = the ground block under the START of the station track (Y = the ground level, -61 on a flat world).
               The station track runs at Y+3 (level with the platform top) from there, toward --facing.
      --facing  the direction the train leaves the station. The demo layout then turns RIGHT; the platform is on
               the LEFT of the track. The demo ride needs flat ground, 46 × 213 blocks (it prints its box).
      --name coaster      app name, tag prefix and job-file prefix (a second ride: --name coaster2)
      --title INFERNO     the name on the sign and the ride screens
      --cars 5            1..8 single-seat cars (fewer = lighter and a little slower over the hills)
      --platform 5        platform depth in blocks (3..8)       --no-roof   no station roof
      --layout FILE.py    your own layout(t) (README.md → "Your own layout"; check it with track.py first)
      --rails red_concrete --spine black_concrete   track colours (any block)
      --no-models         the train as plain coloured blocks, until the train pack (pack.py) is live for players
      --data DIR          where track.json goes (default: <world>/scripts/<name>.data when run by minecraft_generate)
      --update-app        overwrite an installed <name>.sc with this folder's coaster.sc
      --force             build even if the design check reports a problem

    → jobs/<name>-1-station.json (platform, railing with one gate per car, stairs, roof, signs),
      <name>-2-track(-N).json (≈1,170 displays), <name>-3-supports.json (≈220 displays + footings),
      <name>.data/track.json (the path, one sample every 0.5 block, and every position the app needs).
      Run with minecraft_generate … build:true helpers:3 — summons only work in loaded chunks and the helpers walk
      the track. The first job (re)loads the app: check nobody is riding first (script in <name> run status()).
"""
import argparse
import json
import math
import os
import random
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "scripts"))
from mclib import Build, DIRS, OPPOSITE, JOBS, dir_name   # noqa: E402
import track as CT                                         # noqa: E402

ap = argparse.ArgumentParser(description="A roller coaster on display entities (see the module docstring).")
ap.add_argument("--at", required=True, help="x,y,z of the ground block under the start of the station track")
ap.add_argument("--facing", default="east", choices=list(DIRS), help="the direction the train leaves the station")
ap.add_argument("--name", default="coaster")
ap.add_argument("--title", default="INFERNO")
ap.add_argument("--cars", type=int, default=CT.N_CARS)
ap.add_argument("--platform", type=int, default=5)
ap.add_argument("--no-roof", action="store_true")
ap.add_argument("--layout")
ap.add_argument("--rails", default="red_concrete")
ap.add_argument("--spine", default="black_concrete")
ap.add_argument("--no-models", action="store_true")
ap.add_argument("--data")
ap.add_argument("--update-app", action="store_true")
ap.add_argument("--force", action="store_true")
argv, k = list(sys.argv[1:]), 0
while k < len(argv) - 1:                    # "--at -116,-61,280" → one option (the value starts with "-")
    if argv[k] == "--at" and argv[k + 1].startswith("-"):
        argv[k:k + 2] = ["--at=" + argv[k + 1]]
    k += 1
a = ap.parse_args(argv)
X, G, Z = (int(float(v)) for v in a.at.split(","))
NAME = a.name
if not re.fullmatch(r"[a-z][a-z0-9_]{0,23}", NAME):
    raise SystemExit("--name: lowercase letters, digits and _ (it becomes the app name and the tag prefix)")
W = max(3, min(8, a.platform))

# ───────────────────────────── the track ─────────────────────────────
T = CT.Track((float(X), G + 3.0, float(Z)), CT.YAW[a.facing], CT.load_layout(a.layout) if a.layout else CT.layout, n_cars=a.cars)
S, FR, Q, L, N, DS = T.S, T.F, T.Q, T.L, len(T.S), CT.DS
lines, problems, notes = T.report()
print("\n".join(lines[:5] + ["note: " + n for n in notes]))
if problems and not a.force:
    raise SystemExit("design check failed:\n  " + "\n  ".join(problems) + "\nfix the layout (python3 track.py --layout …) or pass --force")
ST_END = T.ranges("station")[0][1]
SL = int(round(ST_END))                     # station length in blocks
if any(abs(S[i][1] - S[0][1]) > 0.01 for i in range(int(ST_END / DS))):
    raise SystemExit("the station section must be flat: start the layout with t.seg(L, tag='station')")
if not 1 <= a.cars <= 8 or T.stop - (a.cars - 1) * T.gap < 1.0:
    raise SystemExit(f"{a.cars} cars do not fit in the station (stop at s {T.stop}, {T.gap} blocks per car)")

BUILD_ID = "%06x" % random.SystemRandom().randrange(16 ** 6)     # a new id per generation (see coaster.sc, _stale_static)
BTAG = f"{NAME}_b{BUILD_ID}"
TRACK_TAGS = f'"{NAME}","{NAME}_static","{NAME}_track","{BTAG}"'
SUP_TAGS = f'"{NAME}","{NAME}_static","{NAME}_sup","{BTAG}"'


class Site:
    """The station's own frame: u = metres along the station (toward --facing), v = metres to the right of the track."""

    def __init__(self, x, z, facing):
        self.x, self.z = x, z
        self.f = DIRS[facing]
        self.r = (-self.f[1], self.f[0])
        self.names = {"forward": facing, "back": OPPOSITE[facing], "right": dir_name(*self.r), "left": dir_name(-self.r[0], -self.r[1])}

    def pt(self, u, v):
        return (self.x + u * self.f[0] + v * self.r[0], self.z + u * self.f[1] + v * self.r[1])

    def cell(self, i, j):
        """The block that covers local cell (i, j) (the square u i..i+1, v j..j+1)."""
        x, z = self.pt(i + 0.5, j + 0.5)
        return (math.floor(x), math.floor(z))

    def local(self, x, z):
        return ((x - self.x) * self.f[0] + (z - self.z) * self.f[1], (x - self.x) * self.r[0] + (z - self.z) * self.r[1])


site = Site(X, Z, a.facing)
J0 = -2 - W                                  # the row behind the platform (lower stair steps)
I0, I1 = -2, SL + 2                          # station footprint along the track
EXIT_UV = (SL - 0.5, -(2 + (W - 1) // 2) + 0.5)
GATE_I = [math.floor(T.stop - k * T.gap - 0.19) for k in range(a.cars)]   # one gate per car, at its seat
OUT = []


def save(b, part, chunk=1100):
    OUT.extend(b.save(f"{NAME}-{part}", chunk=chunk))


# ───────────────────────────── display boxes along the curve ─────────────────────────────
def v_add(p, q, k=1.0):
    return tuple(p[i] + q[i] * k for i in range(3))


def v_sub(p, q):
    return tuple(p[i] - q[i] for i in range(3))


def P(i, al=0.0, bu=0.0):
    """Point on the track frame: along left by al, along up by bu."""
    f, u, l = FR[i % N]
    s = S[i % N]
    return (s[0] + l[0] * al + u[0] * bu, s[1] + l[1] * al + u[1] * bu, s[2] + l[2] * al + u[2] * bu)


def box(b, p0, p1, up, w, h, block, bright=8, pad=0.0, tag=TRACK_TAGS):
    """A block_display box from point p0 to point p1 (its length axis), `w` wide, `h` high, top toward `up`."""
    f = CT.norm(v_sub(p1, p0))
    ln = math.dist(p0, p1) + 2 * pad
    u = CT.norm(tuple(up[k] - f[k] * CT.dot(up, f) for k in range(3)))
    if abs(CT.dot(up, f)) > 0.999:
        u = CT.norm(tuple((0, 0, 1)[k] - f[k] * f[2] for k in range(3)))
    l = CT.cross(u, f)
    q = CT.quat(l, u, f)
    mid = tuple((p0[k] + p1[k]) / 2 for k in range(3))
    tr = tuple(-(l[k] * w / 2 + u[k] * h / 2 + f[k] * ln / 2) for k in range(3))
    b.cmd(f'summon block_display {mid[0]:.3f} {mid[1]:.3f} {mid[2]:.3f} {{block_state:{{Name:"minecraft:{block}"}},'
          f'transformation:{{left_rotation:[{q[0]:.5f}f,{q[1]:.5f}f,{q[2]:.5f}f,{q[3]:.5f}f],right_rotation:[0f,0f,0f,1f],'
          f'translation:[{tr[0]:.4f}f,{tr[1]:.4f}f,{tr[2]:.4f}f],scale:[{w:.3f}f,{h:.3f}f,{ln:.3f}f]}},'
          f'brightness:{{sky:15,block:{bright}}},view_range:2.5f,Tags:[{tag}]}}')


def dist_to_line(p, p0, p1):
    ac = v_sub(p1, p0)
    L2 = CT.dot(ac, ac) or 1e-9
    k = max(0.0, min(1.0, CT.dot(v_sub(p, p0), ac) / L2))
    return math.dist(p, v_add(p0, ac, k))


def line(b, a_off, b_off, w, h, block, bright=8, maxlen=6.0, tol=0.035):
    """A continuous member along the whole track (offset a_off left, b_off up), cut into straight boxes where the
    curve allows (chord error ≤ tol, ≤ maxlen long, the up vector turns < 7°)."""
    pts = [P(i, a_off, b_off) for i in range(N)]
    i0, count = 0, 0
    while i0 < N:
        j = i0 + 1
        while True:
            k = j + 1
            if (k - i0) * DS > maxlen or k > N:
                break
            A, C = pts[i0], pts[k % N]
            if any(dist_to_line(pts[m % N], A, C) > tol for m in range(i0 + 1, k)):
                break
            if CT.dot(FR[i0][1], FR[k % N][1]) < math.cos(math.radians(7)) and (k - i0) * DS > 1.0:
                break
            j = k
        mid = (i0 + j) // 2
        box(b, pts[i0], pts[j % N], FR[mid % N][1], w, h, block, bright, pad=0.03)
        count += 1
        i0 = j
    return count


# ───────────────────────────── 1. station ─────────────────────────────
def text_display(b, u, v, y, text, kind, scale, billboard="center", bg=1426063360):
    x, z = site.pt(u, v)
    b.cmd(f'summon text_display {x:.2f} {y:.2f} {z:.2f} {{billboard:"{billboard}",alignment:"center",shadow:1b,background:{bg},'
          f'Tags:["{NAME}","{NAME}_static","{NAME}_{kind}","{BTAG}"],brightness:{{sky:15,block:15}},view_range:2f,'
          f'transformation:{{left_rotation:[0f,0f,0f,1f],right_rotation:[0f,0f,0f,1f],translation:[0f,0f,0f],scale:[{scale}f,{scale}f,{scale}f]}},'
          f'text:{json.dumps(text, ensure_ascii=False)}}}')


def station(app_installed):
    b = Build()
    if app_installed:
        b.before(f"script load {NAME}")                  # the app knows this build id before any new part can unload
    b.before(f"kill @e[tag={NAME}_sign]")
    b.before(f"kill @e[tag={NAME}_board]")
    right, left = site.names["right"], site.names["left"]
    roof = not a.no_roof
    stairs = set(range(1, 4)) | set(range(SL - 4, SL - 1))
    n_p = max(1, round((SL + 2) / 6))
    pillars = sorted({round(-1 + k * (SL + 2) / n_p) for k in range(n_p + 1)} - stairs)
    for i in range(I0, I1 + 1):
        for j in range(J0, 4):
            x, z = site.cell(i, j)
            b.set((x, G, z), "polished_blackstone_bricks")
            for y in range(G + 1, G + 9):
                b.set((x, y, z), "air")
            if -1 <= j <= 1:
                b.set((x, G + 1, z), "black_concrete")                                  # the pit
            elif j <= -2 and j >= -1 - W and -1 <= i <= SL + 1:                          # the platform, top at G+3
                b.set((x, G + 1, z), "polished_blackstone")
                b.set((x, G + 2, z), "orange_concrete" if j == -2 else "polished_blackstone_bricks")
    # stairs up from the ground at the back, near both ends (in = near the start, out = near the exit)
    for i in stairs:
        x, z = site.cell(i, -1 - W)
        b.set((x, G + 2, z), f"polished_blackstone_brick_stairs[facing={right}]")
        x, z = site.cell(i, J0)
        b.set((x, G + 1, z), f"polished_blackstone_brick_stairs[facing={right}]")
    # railing on the platform edge with one gate per car (coaster.sc opens and closes them), closed at both ends
    gates = [(*site.cell(i, -2),) for i in GATE_I]
    gate_cells = [(x, G + 3, z) for (x, z) in gates]
    fence = [site.cell(i, -2) for i in range(-1, SL + 2) if i not in GATE_I]
    fence += [site.cell(i, j) for i in (-1, SL + 1) for j in range(-1 - W, -2) if not (j == -1 - W and i in pillars)]
    b.fence_ring([(x, G + 3, z) for (x, z) in fence], "crimson_fence", gates=gate_cells)
    for c in gate_cells:
        b.set(c, f"crimson_fence_gate[facing={right},open=true]")
    # roof on pillars (or lamp posts without one); hanging lanterns light the platform and the pit
    lamps_i = list(range(2, SL + 1, 6))
    if roof:
        for i in pillars:
            x, z = site.cell(i, -1 - W)
            for y in range(G + 3, G + 8):
                b.set((x, y, z), "polished_blackstone")
            x, z = site.cell(i, 3)
            for y in range(G + 1, G + 8):
                b.set((x, y, z), "polished_blackstone")
        for i in range(I0, I1 + 1):
            for j in range(J0, 4):
                x, z = site.cell(i, j)
                edge = i in (I0, I1) or j in (J0, 3)
                b.set((x, G + 8, z), "red_concrete" if edge else "orange_stained_glass" if -1 <= j <= 1 else "black_concrete")
        for i in lamps_i:
            for j in (-1 - (W + 1) // 2, 2):
                x, z = site.cell(i, j)
                b.set((x, G + 7, z), "lantern[hanging=true]")
    else:
        for i in lamps_i:
            x, z = site.cell(i, -1 - W)
            b.set((x, G + 3, z), "polished_blackstone_wall"); b.set((x, G + 4, z), "polished_blackstone_wall"); b.set((x, G + 5, z), "lantern")
            x, z = site.cell(i, 3)
            b.set((x, G + 1, z), "polished_blackstone_wall"); b.set((x, G + 2, z), "lantern")
    # the sign, the rules at the entrance stairs, the ride board (coaster.sc writes it) at the exit stairs
    text_display(b, SL / 2, (J0 + 4) / 2, G + (11.5 if roof else 8.5), [{"text": a.title, "color": "#FF5A1F", "bold": True}],
                 "sign", 4.0, billboard="vertical", bg=0)
    text_display(b, 2.5, J0 - 0.6, G + 3.2, [{"text": "★ HOW TO RIDE ★\n", "color": "gold", "bold": True},
                                             {"text": "Right-click a seat\nThe train leaves 8 s after the first rider\n", "color": "white"},
                                             {"text": "Shift in the station = get out\n", "color": "#FFD166"},
                                             {"text": "No getting off mid-ride", "color": "gray"}], "sign", 0.55)
    text_display(b, SL - 2.5, J0 - 0.6, G + 3.4, [{"text": a.title, "color": "#FF5A1F", "bold": True}], "board", 0.55)
    save(b, "1-station")


# ───────────────────────────── 2. track ─────────────────────────────
def track():
    b = Build()
    b.before(f"kill @e[tag={NAME}_track]")
    n = 0
    n += line(b, 0.6, -0.1, 0.2, 0.2, a.rails, bright=10)
    n += line(b, -0.6, -0.1, 0.2, 0.2, a.rails, bright=10)
    n += line(b, 0.0, -0.5, 0.36, 0.4, a.spine, bright=6)
    for i in range(0, N, 5):                                  # ties every 2.5 blocks
        f, u, l = FR[i]
        box(b, P(i, 0.72, -0.25), P(i, -0.72, -0.25), u, 0.22, 0.1, a.spine, bright=6)
        n += 1
    for (s0, s1) in T.ranges("lift"):                         # the chain on the lift: a dark strip between the rails
        i, j = int(s0 / DS), int(s1 / DS)
        box(b, P(i, 0, -0.17), P(j, 0, -0.17), FR[(i + j) // 2][1], 0.14, 0.06, "gray_concrete", bright=4)
        n += 1
    save(b, "2-track")
    return n


# ───────────────────────────── 3. supports ─────────────────────────────
def clear_below(i, top, r=1.7):
    """No other part of the track under this column (within r horizontally, from the ground up to the top)."""
    x, z = top[0], top[2]
    for j in range(N):
        if abs(j - i) < 14 or abs(j - i) > N - 14:
            continue
        p = S[j]
        if p[1] < top[1] + 0.5 and math.hypot(p[0] - x, p[2] - z) < r:
            return False
    return True


def in_station(p):
    u, v = site.local(p[0], p[2])
    return I0 - 1 <= u <= I1 + 1 and J0 <= v <= 4


def supports():
    b = Build()
    b.before(f"kill @e[tag={NAME}_sup]")
    count = 0
    lift = T.ranges("lift")
    on_lift = lambda s: any(p <= s <= q for (p, q) in lift)
    for i in range(0, N, 8):                                  # every 4 blocks
        f, u, l = FR[i]
        if u[1] < 0.35:
            continue
        top = P(i, 0, -0.66)
        hgt = top[1] - (G + 1)
        if hgt < 0.8 or in_station(top) or not clear_below(i, top):
            continue
        if on_lift(i * DS) and hgt > 6 and i % 16 == 0:
            # A-frame trestle: two legs splayed to the ground, cross ties every 8 blocks
            lh = CT.norm((l[0], 0, l[2]))
            spread = 1.0 + hgt * 0.06
            feet = []
            for sgn in (1, -1):
                p0 = P(i, 0.35 * sgn, -0.66)
                g = (top[0] + lh[0] * spread * sgn, G + 1, top[2] + lh[2] * spread * sgn)
                box(b, g, p0, f, 0.4, 0.4, a.spine, bright=4, pad=0.1, tag=SUP_TAGS)
                feet.append((g, p0)); count += 1
                b.set((math.floor(g[0]), G, math.floor(g[2])), "polished_blackstone")
            for yy in range(int(G + 8), int(top[1]) - 2, 8):
                k = (yy - (G + 1)) / hgt
                pa = v_add(feet[0][0], v_sub(feet[0][1], feet[0][0]), k)
                pb = v_add(feet[1][0], v_sub(feet[1][1], feet[1][0]), k)
                box(b, pa, pb, (0, 1, 0), 0.25, 0.25, a.spine, bright=4, pad=0.15, tag=SUP_TAGS)
                count += 1
        else:
            w = 0.5 if hgt > 12 else 0.4
            box(b, (top[0], G + 1, top[2]), top, f if abs(f[1]) < 0.9 else (1, 0, 0), w, w, a.spine, bright=4, pad=0.05, tag=SUP_TAGS)
            count += 1
            b.set((math.floor(top[0]), G, math.floor(top[2])), "polished_blackstone")
    save(b, "3-supports")
    return count


# ───────────────────────────── track.json for the app ─────────────────────────────
def fx_points():
    """Arc-length positions (and centres) where the app fires effects; only for the sections the layout has."""
    fx = {}
    lift = T.ranges("lift")
    if lift:
        fx["crest"] = round(max(c for (_, c) in lift), 1)
    loops = T.ranges("loop")
    if loops:
        s0, s1 = loops[0]
        i = int(s0 / DS) - 1
        y_in = S[int(s0 / DS)][1]
        while S[i - 1][1] < y_in + 0.7 and i > int(s0 / DS) - 200:     # the low run into the loop
            i -= 1
        top = S[int((s0 + s1) / 2 / DS)]
        fx.update({"tunnel": [round(i * DS, 1), round(s0 - 0.5, 1)], "loop": [round(s0, 1), round(s1, 1)],
                   "loop_top": round((s0 + s1) / 2, 1), "loop_c": [round(top[0], 1), round((top[1] + y_in) / 2, 1), round(top[2], 1)]})
    helix = T.ranges("helix")
    if helix:
        s0, s1 = helix[0]
        hs = S[int(s0 / DS):int(s1 / DS)]
        fx["helix"] = [round(s0, 1), round(s1, 1)]
        fx["helix_c"] = [round(sum(p[k] for p in hs) / len(hs), 1) for k in range(3)]
    air = T.ranges("air")
    if air:
        fx["air"] = [[round(p, 1), round(q, 1)] for (p, q) in air]
    return fx


def track_json(path):
    rows = []
    for i in range(N):
        f, u, l = FR[i]
        rows.append([round(S[i][0], 3), round(S[i][1], 3), round(S[i][2], 3)] + [round(c, 4) for c in Q[i]]
                    + [round(c, 3) for c in u] + [round(c, 3) for c in l])
    xs = [p[0] for p in S]; zs = [p[2] for p in S]
    area = [math.floor(min(xs)) - 2, math.floor(min(zs)) - 2, math.ceil(max(xs)) + 2, math.ceil(max(zs)) + 2]
    chunks = (area[2] // 16 - area[0] // 16 + 1) * (area[3] // 16 - area[1] // 16 + 1)
    cx, cz = site.pt(SL / 2, 0)
    ex, ez = site.pt(*EXIT_UV)
    data = {"name": NAME, "title": a.title, "build": BUILD_ID, "models": not a.no_models,
            "ds": DS, "n": N, "len": round(L, 3), "p": rows, "tags": [[tg, round(p, 2), round(q, 2)] for (tg, p, q) in T.tags],
            "stop": T.stop, "cars": a.cars, "gap": T.gap, "seats_per_car": 1,
            "gates": [[x, G + 3, z] for (x, z) in (site.cell(i, -2) for i in GATE_I)],
            "gate_block": "crimson_fence_gate", "gate_facing": site.names["right"],
            "g": CT.G, "drag": CT.DRAG, "roll": CT.ROLL, "lift_v": CT.LIFT_V, "tyre_v": CT.TYRE_V, "brake_v": CT.BRAKE_V,
            "exit": [round(ex, 2), G + 3.0, round(ez, 2), CT.YAW[site.names["left"]]],
            "center": [round(cx, 1), G + 3.0, round(cz, 1)], "area": area, "fx": fx_points()}
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, "track.json"), "w") as fh:
        json.dump(data, fh, separators=(",", ":"))
    stale = os.path.join(path, "removed.json")                   # an earlier remove() — this is a new build
    if os.path.exists(stale):
        os.remove(stale)
    return chunks


def install():
    """Where track.json goes, and copy the app next to it when we know the world's scripts folder."""
    cu = os.environ.get("CLAWDBLOCK_CU_DATA")                   # set by minecraft_generate: <world>/scripts/cu.data
    scripts = os.path.dirname(cu) if cu else None
    data = a.data or (os.path.join(scripts, f"{NAME}.data") if scripts else os.path.join(JOBS, f"{NAME}.data"))
    app = None
    if scripts:
        app = os.path.join(scripts, f"{NAME}.sc")
        if a.update_app or not os.path.exists(app):
            os.makedirs(scripts, exist_ok=True)
            shutil.copy(os.path.join(HERE, "coaster.sc"), app)
    return data, app


if __name__ == "__main__":
    data_dir, app_file = install()
    chunks = track_json(data_dir)
    station(app_file is not None)
    nt = track()
    ns = supports()
    xs = [p[0] for p in S] + [site.pt(u, v)[0] for u in (I0, I1 + 1) for v in (J0, 4)]
    zs = [p[2] for p in S] + [site.pt(u, v)[1] for u in (I0, I1 + 1) for v in (J0, 4)]
    lo = [math.floor(min(xs)) - 1, G, math.floor(min(zs)) - 1]
    hi = [math.ceil(max(xs)) + 1, math.ceil(max(p[1] for p in S)) + 2, math.ceil(max(zs)) + 1]
    stairs = site.pt(2.5, J0 - 1.5)
    ex = site.pt(*EXIT_UV)
    print(f"box {lo} -> {hi}; stairs up at {[round(stairs[0], 1), G + 1, round(stairs[1], 1)]}; exit {[round(ex[0], 1), G + 3, round(ex[1], 1)]}")
    print(f"entities: {nt} track + {ns} supports + 3 signs = {nt + ns + 3} static displays; train {a.cars} cars, build {BUILD_ID}")
    print(f"track data: {os.path.join(data_dir, 'track.json')} ({chunks} chunks force-loaded while the train runs"
          + (", MORE THAN forceload's 256: a show run far from players may pause" if chunks > 256 else "") + ")")
    if app_file:
        print(f"app: {app_file} (loaded by the first job; ride: right-click a seat in the station)")
    else:
        print(f"app: copy {os.path.join(HERE, 'coaster.sc')} to <world>/scripts/{NAME}.sc and {data_dir}/track.json to "
              f"<world>/scripts/{NAME}.data/track.json, then: script load {NAME}")
    print("files", OUT)
