"""Bench scenarios: what the player asks, how the arena is prepared, and how the result is judged.

Every scenario gets its own arena on the flat test world (a 97×97 square far from anything else) with the player
"Tester" standing in the middle facing north. Checks look at the WORLD afterwards (the judge scan), never at what the
model says it did. Each check has a weight; the score is the weighted share of passed checks, 0-100.
"""
import json
import math
import re
from pathlib import Path

from world import GROUND, box_gap, dist_point_box

BENCH = "Pink Golem Bench"
BENCH_VERSION = "1"              # bump when tasks or checks change in a way that makes old scores incomparable
TIERS = {1: "Basics", 2: "Finding the site", 3: "Free-form"}
TESTER = "Tester"
R = 48                           # arena half size
DOORS = re.compile(r"_door$")
LIGHTS = re.compile(r"(lantern|torch|glowstone|froglight|sea_lantern|shroomlight|^light$|redstone_lamp|campfire|end_rod)")
STONE = {"stone", "smooth_stone", "stone_bricks", "cobblestone"}
PASSABLE = re.compile(r"(door|carpet|torch|lantern|flower|sapling|button|pressure_plate|sign|banner|rail|^light$|potted|"
                      r"candle|short_grass|fern|vine|ladder|tripwire|redstone_wire|chain$|end_rod|cobweb|^snow$|"
                      r"trapdoor|head$|skull$)")
CLIMB = re.compile(r"(_stairs|ladder|scaffolding|vine)")


def arena(k):
    cx, cz = 5000 + 256 * k, 5000
    return {"cx": cx, "cz": cz, "box": ((cx - R, cz - R), (cx + R, cz + R))}


def fmt(s, a):
    return s.format(cx=a["cx"], cz=a["cz"], **{k: v for k, v in a.items() if k not in ("cx", "cz")})


def cells_of(scan, pred):
    return [c for c in scan["cells"] if pred(c[3])]


def bbox(cells):
    if not cells:
        return None, None
    xs, ys, zs = zip(*[(c[0], c[1], c[2]) for c in cells])
    return [min(xs), min(ys), min(zs)], [max(xs), max(ys), max(zs)]


def inside(p, lo, hi, pad=0):
    return all(lo[i] - pad <= p[i] <= hi[i] + pad for i in range(3))


def count_overlap(a, b):
    """How alike two block-count maps are: shared blocks / blocks in the bigger build (0..1). Leaves are left out:
    blueprints plant trees with the game's random tree generator, so no two runs grow the same tree."""
    a = {k: v for k, v in (a or {}).items() if not k.endswith("_leaves")}
    b = {k: v for k, v in (b or {}).items() if not k.endswith("_leaves")}
    if not a or not b:
        return 0.0
    shared = sum(min(a.get(k, 0), b.get(k, 0)) for k in set(a) | set(b))
    return shared / max(sum(a.values()), sum(b.values()))


def room_columns(scan):
    """Columns with two blocks of headroom (air or passable) right above a floor and something overhead — the inside
    of a room. A solid block of stone has none; a furnished cottage has dozens."""
    if not scan["n"]:
        return 0
    occ = {(x, y, z): b for x, y, z, b in scan["cells"]}
    lo, hi = scan["lo"], scan["hi"]
    free = lambda q: q not in occ or PASSABLE.search(occ[q])  # noqa: E731
    n = 0
    for x in range(lo[0], hi[0] + 1):
        for z in range(lo[2], hi[2] + 1):
            for y0 in (GROUND, GROUND + 1):            # floor replacing the ground, or laid on top of it
                if free((x, y0 + 1, z)) and free((x, y0 + 2, z)) and any(
                        (x, y, z) in occ and not free((x, y, z)) for y in range(y0 + 3, hi[1] + 1)):
                    n += 1
                    break
    return n


# ── generic building checks, shared by the "build me X" scenarios ─────────────
def building_checks(c, min_blocks, w, near=20):
    """w = weights: built, near, buried, ground, door, room."""
    s, tp = c["scan"], c["tester"]
    rooms = room_columns(s)
    exists = s["n"] >= min_blocks and rooms >= 6    # placement only counts for a real building (a room inside)
    out = [("built", w["built"], s["n"] >= min_blocks, f"{s['n']} blocks changed")]
    if exists:
        d = dist_point_box(tp, s["lo"], s["hi"])
        out.append(("near the player", w["near"], d <= near, f"{d:.0f} blocks from Tester"))
        out.append(("player not buried", w["buried"], c["tester_free"],
                    "Tester stands in open air" if c["tester_free"] else "Tester is inside blocks"))
        out.append(("on the ground", w["ground"], s["lo"][1] <= GROUND, f"lowest block y={s['lo'][1]}"))
    else:
        out += [("near the player", w["near"], False, "not a real building (no room inside)"),
                ("player not buried", w["buried"], c["tester_free"] and s["n"] > 0,
                 "nothing built" if not s["n"] else "Tester stands in open air" if c["tester_free"] else "Tester is inside blocks"),
                ("on the ground", w["ground"], False, "not a real building (no room inside)")]
    doors = sum(v for k, v in s["counts"].items() if DOORS.search(k))
    out.append(("has a door", w["door"], doors >= 2, f"{doors} door halves"))
    out.append(("a room inside (headroom under a roof)", w["room"], rooms >= 6, f"{rooms} room columns"))
    return out


# ── the scenarios ─────────────────────────────────────────────────────────────
def chk_hello(c):
    on = c["bot_online"]
    d = math.dist(c["bot_pos"][:3], c["tester"][:3]) if (on and c["bot_pos"]) else 999
    chats = [x for x in c["calls"] if x["name"] == "minecraft_chat" and not x["error"]]
    return [("bot in the world", 40, on, "online" if on else "not online"),
            ("bot next to the player", 30, d <= 12, f"{d:.1f} blocks away"),
            ("said hi in chat", 30, bool(chats), f"{len(chats)} chat lines")]


def chk_cottage_at(c):
    s, a, ref = c["scan"], c["arena"], c.get("reference")
    corner = [a["cx"] - 4, GROUND, a["cz"] - 12]
    out = [("built", 30, s["n"] >= 300, f"{s['n']} blocks changed")]
    if s["n"] >= 300:
        out.append(("at the given corner", 25, inside(corner, s["lo"], s["hi"], pad=1),
                    f"box {s['lo']}..{s['hi']}, corner {corner}"))
        out.append(("on the ground", 15, s["lo"][1] <= GROUND, f"lowest block y={s['lo'][1]}"))
    else:
        out += [("at the given corner", 25, False, "nothing built"), ("on the ground", 15, False, "nothing built")]
    sim = count_overlap(s["counts"], ref["counts"]) if ref else 0
    out.append(("same as the blueprint", 30, sim >= 0.9, f"{sim:.0%} of blocks match the reference cottage"))
    return out


def chk_platform(c):
    s, tp = c["scan"], c["tester"]
    stone = cells_of(s, lambda b: b in STONE)
    lanterns = cells_of(s, lambda b: b in ("lantern", "soul_lantern"))
    out = []
    lo, hi = bbox(stone)
    layer_ok, square = False, False
    if stone:
        ys = {p[1] for p in stone}
        layer_ok = len(ys) == 1 and ys.pop() in (GROUND, GROUND + 1)
        square = (hi[0] - lo[0] == 4 and hi[2] - lo[2] == 4 and len(stone) == 25)
    out.append(("a 5x5 stone floor", 30, square, f"{len(stone)} stone blocks, box {lo}..{hi}"))
    out.append(("flat on the ground", 15, layer_ok, "one layer at y=-61 or -60" if layer_ok else "not one ground layer"))
    corners_hit = 0
    if stone:
        y_top = hi[1]
        corners = [(lo[0], lo[2]), (lo[0], hi[2]), (hi[0], lo[2]), (hi[0], hi[2])]
        for (x, z) in corners:
            if any(p[0] == x and p[2] == z and p[1] in (y_top + 1, y_top) for p in lanterns):
                corners_hit += 1
    out.append(("a lantern on each corner", 30, corners_hit == 4 and len(lanterns) == 4,
                f"{len(lanterns)} lanterns, {corners_hit}/4 on corners"))
    if stone:
        cxz = ((lo[0] + hi[0]) / 2, (lo[2] + hi[2]) / 2)
        ahead = tp[2] - cxz[1]                    # Tester faces north (-z): in front = smaller z
        side = abs(cxz[0] - tp[0])
        out.append(("in front of the player", 25, 1.5 <= ahead <= 10 and side <= 4,
                    f"centre {ahead:.1f} ahead, {side:.1f} to the side"))
    else:
        out.append(("in front of the player", 25, False, "no floor"))
    return out


def chk_house_near(c):
    out = building_checks(c, 250, {"built": 20, "near": 15, "buried": 10, "ground": 10, "door": 10, "room": 25})
    acc = [j.get("access") for j in c["jobs"] if j.get("access")]
    ok = bool(acc) and all((x or {}).get("ok") for x in acc)
    out.append(("rooms reachable (access check)", 10, ok, "access ok" if ok else ("no access check run" if not acc else "access failed")))
    return out


def setup_library(c):
    """A small library 9 blocks east of Tester, on the map and as a protected zone owned by Tester."""
    a = c["arena"]
    x1, z1 = a["cx"] + 8, a["cz"] - 4
    x2, z2 = x1 + 8, z1 + 8
    cmds = [f"fill {x1} {GROUND} {z1} {x2} {GROUND} {z2} oak_planks",
            f"fill {x1} {GROUND + 1} {z1} {x2} {GROUND + 5} {z2} bookshelf hollow",
            f"fill {x1} {GROUND + 6} {z1} {x2} {GROUND + 6} {z2} dark_oak_planks",
            f"fill {x1 + 1} {GROUND + 1} {z1 + 1} {x2 - 1} {GROUND + 5} {z2 - 1} air",
            f"setblock {x1 + 4} {GROUND + 5} {z1 + 4} lantern[hanging=true]",
            f"setblock {x1} {GROUND + 1} {z1 + 4} oak_door[facing=east,half=lower]",
            f"setblock {x1} {GROUND + 2} {z1 + 4} oak_door[facing=east,half=upper]"]
    for cmd in cmds:
        c["world"].cmd(cmd)
    lo, hi = [x1, GROUND, z1], [x2, GROUND + 6, z2]
    c["judge"].call("minecraft_map", {"action": "add", "name": "Library", "from": lo, "to": hi, "owner": TESTER,
                                      "entrances": [[x1 - 1, GROUND + 1, z1 + 4, "door, west side"]],
                                      "notes": "Tester's library"})
    c["judge"].call("minecraft_zones", {"action": "add", "name": "Library", "from": lo, "to": hi, "owner": TESTER,
                                        "note": "Tester's library"})
    c["library"] = (lo, hi)


def chk_tower_by_library(c):
    s, (llo, lhi) = c["scan"], c["library"]
    lib_now = {k: v for k, v in c["lib_scan"]["counts"].items()}
    intact = lib_now == c["lib_before"]
    c["_library_damaged"] = not intact
    new = [p for p in s["cells"] if not inside(p, llo, lhi)]
    nlo, nhi = bbox(new)
    climb = sum(1 for p in new if CLIMB.search(p[3]))
    exists = len(new) >= 150 and nhi is not None and nhi[1] - nlo[1] >= 10 and climb >= 8   # a lookout needs a way up
    out = [("library untouched", 25, intact and exists, ("same blocks as before" if intact else "library blocks changed")
            + ("" if exists else " (no tower built, so no credit)")),
           ("a tower was built", 20, exists, f"{len(new)} new blocks" + (f", {nhi[1] - nlo[1] + 1} high" if nhi else "")),
           ("can be climbed (stairs/ladder)", 10, climb >= 8, f"{climb} stair/ladder blocks")]
    if exists:
        gap = box_gap(nlo, nhi, llo, lhi)
        out.append(("right next to the library", 25, gap <= 12, f"{gap:.0f} blocks from the library"))
        out.append(("on the ground", 10, nlo[1] <= GROUND, f"lowest new block y={nlo[1]}"))
        out.append(("not overlapping it", 10, gap > 0, "separate" if gap > 0 else "touches/overlaps the library box"))
    else:
        out += [("right next to the library", 25, False, "no real tower"), ("on the ground", 10, False, "no real tower"),
                ("not overlapping it", 10, False, "no real tower")]
    return out


REF_COTTAGE = Path(__file__).resolve().parent / "state" / "ref-cottage_at.json"


def chk_bakery(c):
    """Free-form: the point is building something of its own. The stock cottage (it has a kitchen with a furnace)
    passes every functional check, so a near-copy of it loses the 'own design' share."""
    s = c["scan"]
    out = building_checks(c, 120, {"built": 15, "near": 10, "buried": 5, "ground": 5, "door": 10, "room": 20})
    furn = sum(v for k, v in s["counts"].items() if k in ("furnace", "smoker", "blast_furnace"))
    lights = sum(v for k, v in s["counts"].items() if LIGHTS.search(k))
    out.append(("an oven (furnace/smoker)", 10, furn >= 1, f"{furn} furnaces"))
    out.append(("lights", 5, lights >= 1, f"{lights} light blocks"))
    sim = count_overlap(s["counts"], json.loads(REF_COTTAGE.read_text())["counts"]) if REF_COTTAGE.exists() and s["n"] else 0
    out.append(("its own design, not a stock blueprint", 20, s["n"] >= 120 and sim < 0.75,
                f"{sim:.0%} like the stock cottage" if s["n"] else "nothing built"))
    return out


SCENARIOS = [
    # tier 1: basics
    {"id": "hello", "tier": 1, "arena": 0,
     "prompt": "I'm Tester, the player in the game. Come into the world next to me and say hi in the chat.",
     "check": chk_hello},
    {"id": "cottage_at", "tier": 1, "arena": 1,
     "prompt": "Build a cottage at {x}, -61, {z} facing south.", "vars": lambda a: {"x": a["cx"] - 4, "z": a["cz"] - 12},
     "check": chk_cottage_at, "reference": {"script": "skill/pinkgolem/blueprints/cottage.py",
                                            "args": lambda a: ["--at", f"{a['cx'] - 4},-61,{a['cz'] - 12}", "--facing", "south"]}},
    {"id": "platform", "tier": 1, "arena": 2,
     "prompt": "I'm Tester, the player in the game. Put a 5x5 stone floor right in front of me, with a lantern on each corner.",
     "check": chk_platform},
    # tier 2: find the site yourself
    {"id": "house_near", "tier": 2, "arena": 3,
     "prompt": "I'm Tester, the player in the game. Build me a house next to me.",
     "check": chk_house_near},
    {"id": "tower_by_library", "tier": 2, "arena": 4,
     "prompt": "I'm Tester, the player in the game. Build a lookout tower right next to my library.",
     "setup": setup_library, "check": chk_tower_by_library},
    # tier 3: no blueprint
    {"id": "bakery", "tier": 3, "arena": 5,
     "prompt": "I'm Tester, the player in the game. Build me a small bakery next to me: walls, a roof, a door, "
               "a counter and an oven inside, and some lights.",
     "check": chk_bakery},
]

BY_ID = {s["id"]: s for s in SCENARIOS}

# failing one of these makes the whole result bad, however much else went right
CRITICAL = {"player not buried": 25}


def score(sc, c):
    """(checks, score 0-100): the weighted share of passed checks, capped when a critical check failed."""
    checks = sc["check"](c)
    total = sum(wt for _, wt, _, _ in checks)
    s = round(100 * sum(wt for _, wt, ok, _ in checks if ok) / total) if total else 0
    for name, _, ok, _ in checks:
        if not ok and name in CRITICAL:
            s = min(s, CRITICAL[name])
    if c.get("_library_damaged") or c.get("tester_free") is False:      # broke someone's build / buried the player
        s = min(s, 25)
    return checks, s
