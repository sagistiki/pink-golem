"""city.py — city infrastructure for mclib: a standard road, junctions, footpaths and rail lines.

    import os, sys; sys.path.insert(0, os.path.join(os.environ.get("PINKGOLEM_ROOT", "."), "skill/pinkgolem/scripts"))
    from mclib import Build
    from city import road, junction, footpath, rail_path

A classic city road, 13 wide, cross-section from one edge:
    3-block sidewalks (stone_bricks, smooth_stone, stone_bricks) | a 7-wide black_terracotta carriageway | sidewalks
    white_concrete dashes on the centre line (where coord % 3 != 2), lamps (2 dark_oak_fence + lantern) every 16
    blocks on the outer sidewalk block, alternating sides. Optional tram: a rail in the middle of each lane
    (centre ± 2), boosters (powered rail on a redstone block) every 5.

CLI (used by the MCP tool minecraft_rails action:path, and by your scripts):
    python3 city.py rails '{"points": [[x,y,z], ...], "name": "my-line", "boost_every": 5, "curve_boost": 2,
                            "support": "smooth_stone", "closed": false}'
    → writes jobs/<name>.json (PINKGOLEM_JOBS overrides the folder) and prints ONE JSON line
      {files, rails, boosters, corners, slopes, bounds, ends}
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mclib import Build, GROUND  # noqa: E402

SIDEWALK = ("stone_bricks", "smooth_stone", "stone_bricks")      # outer → inner
ROAD = "black_terracotta"
DASH = "white_concrete"
DIRS = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}
OPP = {"north": "south", "south": "north", "east": "west", "west": "east"}


def _dir(dx, dz):
    for k, v in DIRS.items():
        if v == (dx, dz):
            return k
    raise ValueError(f"not a unit step: {dx},{dz}")


def _sign(v):
    return (v > 0) - (v < 0)


# ═══════════════════════════ roads ═══════════════════════════
def road(b, a, c, y=GROUND, lamps=True, dashes=True, tram=False, boost_every=5, lamp_every=16, sidewalks=True):
    """A straight city road whose CENTRE LINE runs from a to c ((x, z) or (x, y, z); along x or along z).
    tram=True adds a rail in each lane (centre ± 2) with boosters every boost_every — connect the ends with
    rail_path (curves / U-turns) and ride the line to check it."""
    ax, az = a[0], a[-1]
    cx, cz = c[0], c[-1]
    if ax != cx and az != cz:
        raise ValueError("road(): a and c must share x or z (straight road) — use two roads + junction for a turn")
    along_x = az == cz
    lo, hi = (min(ax, cx), max(ax, cx)) if along_x else (min(az, cz), max(az, cz))
    centre = az if along_x else ax
    lamp_side = 1
    for s in range(lo, hi + 1):
        for off in range(-6, 7):
            a_ = abs(off)
            if a_ >= 4:
                if not sidewalks:
                    continue
                blk = SIDEWALK[6 - a_]
            elif off == 0 and dashes and s % 3 != 2:
                blk = DASH
            else:
                blk = ROAD
            p = (s, y, centre + off) if along_x else (centre + off, y, s)
            b.set(p, blk)
        if lamps and sidewalks and (s - lo) % lamp_every == 0:
            off = 6 * lamp_side
            b.lamp_post((s, y + 1, centre + off) if along_x else (centre + off, y + 1, s))
            lamp_side = -lamp_side
        if tram:
            for lane in (-2, 2):
                p = (s, y + 1, centre + lane) if along_x else (centre + lane, y + 1, s)
                shape = "east_west" if along_x else "north_south"
                if boost_every and (s - lo) % boost_every == 0:
                    b.set((p[0], y, p[2]), "redstone_block")
                    b.set(p, f"powered_rail[shape={shape},powered=true]")
                else:
                    b.set(p, f"rail[shape={shape}]")


def junction(b, x, z, y=GROUND):
    """Crossing of two city roads centred on (x, z): the 13×13 square becomes plain road (no dashes) with sidewalk
    corners. Call it AFTER both road() calls."""
    for dx in range(-6, 7):
        for dz in range(-6, 7):
            corner = abs(dx) >= 4 and abs(dz) >= 4
            if b.get((x + dx, y, z + dz)) == "redstone_block":      # keeps the tram boosters powered
                continue
            b.set((x + dx, y, z + dz), SIDEWALK[6 - max(abs(dx), abs(dz))] if corner else ROAD)
            if not corner and b.get((x + dx, y + 1, z + dz)) in ("dark_oak_fence", "lantern"):
                b.set((x + dx, y + 1, z + dz), "air")


def footpath(b, a, c, width=3, surface="gravel", edge=None, y=GROUND, x_first=True):
    """L-shaped path from a to c ((x, z) or (x, y, z)): first along x then z (x_first) or the other way.
    edge = optional border block on both sides (e.g. 'stone_bricks')."""
    ax, az = a[0], a[-1]
    cx, cz = c[0], c[-1]
    h = width // 2
    corner = (cx, az) if x_first else (ax, cz)
    legs = [((ax, az), corner), (corner, (cx, cz))]
    for (p, q) in legs:
        for x in range(min(p[0], q[0]) - h, max(p[0], q[0]) + h + 1):
            for z in range(min(p[1], q[1]) - h, max(p[1], q[1]) + h + 1):
                b.set((x, y, z), surface)
    if edge:
        cells = {k for k, v in b.v.items() if v == surface and k[1] == y}
        for (x, _, z) in list(cells):
            for dx, dz in DIRS.values():
                n = (x + dx, y, z + dz)
                if n not in cells and b.get(n) is None:
                    b.set(n, edge)


# ═══════════════════════════ rails ═══════════════════════════
def rail_path(b, points, boost_every=5, curve_boost=2, support="smooth_stone", closed=False):
    """Lay a rail line through corner points [(x, y, z), ...]. Each leg must be straight along x or z; y may change
    along a leg (one block per step, at most leg length − 2) → ascending rails. Corners get the right curve shape,
    boosters (powered rail on a redstone block) go every boost_every rails and on the curve_boost rails after each
    corner (powered rails cannot curve). `support` is placed under every rail where there is air (setblock … keep;
    skipped on the flat world's ground level, which is solid already). Returns stats. The ends are straight — join
    them to an existing line by hand or make closed=True."""
    pts = [tuple(int(v) for v in p) for p in points]
    if closed and pts[0] != pts[-1]:
        pts.append(pts[0])
    cells = []            # [x, y, z, dir_in, dir_out, slope]  slope: None | 'up' (this rail rises toward dir_out) | 'down'
    for i in range(len(pts) - 1):
        (x0, y0, z0), (x1, y1, z1) = pts[i], pts[i + 1]
        if x0 != x1 and z0 != z1:
            raise ValueError(f"leg {i}: {pts[i]} → {pts[i + 1]} is not straight along x or z")
        n = abs(x1 - x0) + abs(z1 - z0)
        dy = y1 - y0
        if n == 0:
            continue
        if dy and abs(dy) > n - 2:
            raise ValueError(f"leg {i}: rises {dy} over {n} blocks — at most {n - 2} (corners must stay flat)")
        d = (_sign(x1 - x0), _sign(z1 - z0))
        y = y0
        for k in range(0 if i == 0 else 1, n + 1):
            x, z = x0 + d[0] * k, z0 + d[1] * k
            # heights: flat first cell, then one step per cell until the target, then flat
            if dy > 0:
                y = y0 + max(0, min(dy, k - 1))
            elif dy < 0:
                y = y0 - max(0, min(-dy, k - 1))
            cells.append([x, y, z, _dir(*d), _dir(*d), None])
    if closed and cells and cells[0][:3] == cells[-1][:3]:
        cells.pop()
    # corners: a cell's dir_out is the direction to the next cell
    for j in range(len(cells) - 1):
        nx, nz = cells[j + 1][0] - cells[j][0], cells[j + 1][2] - cells[j][2]
        cells[j][4] = _dir(nx, nz)
        cells[j + 1][3] = _dir(nx, nz)
    if closed and len(cells) > 2:
        nx, nz = cells[0][0] - cells[-1][0], cells[0][2] - cells[-1][2]
        cells[-1][4] = _dir(_sign(nx), _sign(nz))
        cells[0][3] = cells[-1][4]
    # slopes: the rail at the LOWER end of a step is 'ascending toward the higher cell'
    N = len(cells)
    shapes = []
    for j, (x, y, z, din, dout, _) in enumerate(cells):
        nxt = cells[(j + 1) % N] if (j + 1 < N or closed) else None
        prv = cells[j - 1] if (j > 0 or closed) else None
        if nxt and nxt[1] == y + 1:
            shape = f"ascending_{dout}"
        elif prv and prv[1] == y + 1:
            shape = f"ascending_{OPP[din]}"
        elif din != dout and not (j == 0 and not closed) and not (j == N - 1 and not closed):
            ns = [k for k in (OPP[din], dout) if k in ("north", "south")][0]
            ew = [k for k in (OPP[din], dout) if k in ("east", "west")][0]
            shape = f"{ns}_{ew}"
        else:
            shape = "east_west" if (dout if j < N - 1 else din) in ("east", "west") else "north_south"
        shapes.append(shape)
    # boosters
    boost = set()
    since_corner = 99
    for j, sh in enumerate(shapes):
        curve = "_" in sh and not sh.startswith("ascending") and sh not in ("east_west", "north_south")
        if curve:
            since_corner = 0
            continue
        since_corner += 1
        if (boost_every and j % boost_every == 0) or since_corner <= curve_boost:
            boost.add(j)
    for j, ((x, y, z, *_), sh) in enumerate(zip(cells, shapes)):
        if j in boost:
            b.set((x, y - 1, z), "redstone_block")
            b.set((x, y, z), f"powered_rail[shape={sh},powered=true]")
        else:
            if support and y - 1 != GROUND:              # on the flat world the ground is already there
                b.before(f"setblock {x} {y - 1} {z} {support} keep")
            b.set((x, y, z), f"rail[shape={sh}]")
    xs, ys, zs = [c[0] for c in cells], [c[1] for c in cells], [c[2] for c in cells]
    return {"rails": N, "boosters": len(boost), "corners": sum(1 for s in shapes if s.count("_") == 1 and not s.startswith("ascending") and s not in ("east_west", "north_south")),
            "slopes": sum(1 for s in shapes if s.startswith("ascending")), "bounds": [[min(xs), min(ys), min(zs)], [max(xs), max(ys), max(zs)]],
            "ends": None if closed else {"first": cells[0][:3] + [shapes[0]], "last": cells[-1][:3] + [shapes[-1]]}}


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "rails":
        spec = json.loads(sys.argv[2])
        b = Build()
        st = rail_path(b, spec["points"], spec.get("boost_every", 5), spec.get("curve_boost", 2), spec.get("support", "smooth_stone"), spec.get("closed", False))
        import io, contextlib
        with contextlib.redirect_stdout(io.StringIO()):
            files = b.save(spec.get("name", "rails"))
        print(json.dumps({"files": files, **st}))
    else:
        print(__doc__)
