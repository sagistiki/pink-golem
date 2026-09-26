"""mclib — build generators for Minecraft, no dependencies.

Describe a build as voxels, let mclib compress it into /fill commands, save job files, run them with the MCP.
City pieces (roads, junctions, footpaths, rail lines) live in city.py next to this file.

    import sys, os; sys.path.insert(0, os.path.join(os.environ.get("PINKGOLEM_ROOT", "."), "skill/pinkgolem/scripts"))
    from mclib import *
    b = Build()
    f = Frame(100, -61, 40, facing="south")     # front-left ground corner, the front faces south
    f.box(b, (0, 0, 0), (8, 0, 6), "oak_planks")            # floor ON the ground level (replaces the grass)
    f.walls(b, (0, 1, 0), (8, 4, 6), "stone_bricks")        # walls from ground+1
    f.set(b, (4, 1, 0), "oak_door[facing={back},half=lower,hinge=left]")   # {back} = into the house, in world terms
    b.save("my_house")                                       # -> jobs/my_house.json (+ -2, -3 … when long)

Conventions (see reference/coordinates.md):
  * world: north = -z, south = +z, east = +x, west = -x, up = +y.
  * Frame local coords (i, j, k): i = left→right along the FRONT as seen by someone standing in front of it,
    j = up from the ground level (j=0 is the ground layer: floors replace it), k = depth from the front (0) to the back.
  * Block strings may contain {front} {back} {left} {right} (world directions of the frame) and {axis_i} {axis_k}
    (x or z) — so one component works in all four orientations.
  * Later writes win. b.clear(...) writes air. b.cmd(...) adds raw commands after the voxels, b.before(...) before them.
"""
import json
import math
import os
import random
import sys

GROUND = -61          # ground level of the default superflat world (grass); players stand at -60
DIRS = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}
OPPOSITE = {"north": "south", "south": "north", "east": "west", "west": "east"}
ROOT = os.environ.get("PINKGOLEM_ROOT") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
JOBS = os.environ.get("PINKGOLEM_JOBS") or os.path.join(ROOT, "jobs")


def dir_name(dx, dz):
    for n, v in DIRS.items():
        if v == (dx, dz):
            return n
    raise ValueError((dx, dz))


class Build:
    def __init__(self):
        self.v = {}        # (x,y,z) -> block string
        self.raw = []      # raw commands appended after voxels
        self.pre = []      # raw commands run before voxels (e.g. kill old displays, clear bed halves)

    # ── voxel primitives (world coordinates) ─────────────────────────
    def set(self, p, blk):
        self.v[(int(p[0]), int(p[1]), int(p[2]))] = blk

    def get(self, p):
        return self.v.get((int(p[0]), int(p[1]), int(p[2])))

    def box(self, a, b, blk):
        for x in range(min(a[0], b[0]), max(a[0], b[0]) + 1):
            for y in range(min(a[1], b[1]), max(a[1], b[1]) + 1):
                for z in range(min(a[2], b[2]), max(a[2], b[2]) + 1):
                    self.v[(x, y, z)] = blk

    def clear(self, a, b):
        self.box(a, b, "air")

    def walls(self, a, b, blk):
        """Four walls of the box a..b (no floor/roof). NOT /fill hollow, which also fills floor and ceiling."""
        x1, x2 = sorted((a[0], b[0])); y1, y2 = sorted((a[1], b[1])); z1, z2 = sorted((a[2], b[2]))
        for y in range(y1, y2 + 1):
            for x in range(x1, x2 + 1):
                self.set((x, y, z1), blk); self.set((x, y, z2), blk)
            for z in range(z1, z2 + 1):
                self.set((x1, y, z), blk); self.set((x2, y, z), blk)

    def hollow_box(self, a, b, shell, inside="air"):
        self.box(a, b, shell)
        x1, x2 = sorted((a[0], b[0])); y1, y2 = sorted((a[1], b[1])); z1, z2 = sorted((a[2], b[2]))
        if x2 - x1 > 1 and y2 - y1 > 1 and z2 - z1 > 1:
            self.box((x1 + 1, y1 + 1, z1 + 1), (x2 - 1, y2 - 1, z2 - 1), inside)

    def sphere(self, c, r, blk, hollow=False, ry=None):
        """Sphere/ellipsoid (ry = vertical radius). Uses d² ≤ (r+0.5)² like /draw."""
        ry = ry or r
        R = int(math.ceil(max(r, ry)))
        for dx in range(-R, R + 1):
            for dy in range(-R, R + 1):
                for dz in range(-R, R + 1):
                    d = (dx / (r + .5)) ** 2 + (dy / (ry + .5)) ** 2 + (dz / (r + .5)) ** 2
                    if d <= 1:
                        if hollow:
                            di = (dx / max(r - .5, .1)) ** 2 + (dy / max(ry - .5, .1)) ** 2 + (dz / max(r - .5, .1)) ** 2
                            if di < 1:
                                continue
                        self.set((c[0] + dx, c[1] + dy, c[2] + dz), blk)

    def cylinder(self, c, r, h, blk, hollow=False):
        """Vertical cylinder from c (bottom centre) up h blocks. hollow = one-block ring."""
        for x, z in disk(c[0], c[2], r) if not hollow else ring(c[0], c[2], r):
            for y in range(h):
                self.set((x, c[1] + y, z), blk)

    def line(self, a, b, blk):
        n = max(abs(b[i] - a[i]) for i in range(3)) or 1
        for i in range(n + 1):
            t = i / n
            self.set(tuple(round(a[k] + (b[k] - a[k]) * t) for k in range(3)), blk)

    def fence_ring(self, cells, blk, gates=()):
        """Fences / walls / panes / iron bars with explicit connections (they don't auto-connect when placed by
        commands). cells: iterable of (x,y,z); gates: positions of gates (the fences connect to them)."""
        s = set(map(tuple, cells)) | set(map(tuple, gates))
        wall = blk.endswith("_wall")
        for (x, y, z) in cells:
            st = {}
            for d, (dx, dz) in DIRS.items():
                on = (x + dx, y, z + dz) in s
                st[d] = ("low" if on else "none") if wall else str(on).lower()
            if wall:
                st["up"] = "true"
            self.set((x, y, z), f"{blk}[{','.join(k + '=' + v for k, v in st.items())}]")

    def door(self, p, blk="oak_door", facing="south", hinge="left"):
        """Two-part door, lower half at p. `facing` = the direction a player walking IN through it faces; the closed
        panel then sits on the opposite edge of the block (flush with the outside of the wall)."""
        self.set(p, f"{blk}[half=lower,facing={facing},hinge={hinge}]")
        self.set((p[0], p[1] + 1, p[2]), f"{blk}[half=upper,facing={facing},hinge={hinge}]")

    def terrain(self, cx, cz, rx, rz, height, top="grass_block", under="dirt",
                stone=("stone", "andesite", "tuff", "cobblestone"), seed=1, rough=2.0, base=GROUND):
        """Natural hill: ellipse footprint, smooth dome + value noise. Returns {(x,z): top_y}."""
        noise = ValueNoise(seed)
        tops = {}
        rnd = random.Random(seed)
        for x in range(cx - rx, cx + rx + 1):
            for z in range(cz - rz, cz + rz + 1):
                d = ((x - cx) / rx) ** 2 + ((z - cz) / rz) ** 2
                if d > 1:
                    continue
                h = height * (1 - d) ** 1.2 + rough * noise.fbm(x / 9, z / 9) - rough * .3
                ty = base + int(round(h))
                if ty <= base:
                    continue
                tops[(x, z)] = ty
                st = rnd.choice(stone)
                for y in range(base, ty - 2):
                    self.set((x, y, z), st)
                steep = h > height * .75 and rnd.random() < .4
                for y in range(max(base, ty - 2), ty):
                    self.set((x, y, z), st if steep else under)
                self.set((x, ty, z), st if steep else top)
        return tops

    # ── more shapes ─────────────────────────────────────────────────
    def hcyl(self, a, axis, r, length, blk, hollow=False, thick=1, upper=False):
        """Horizontal cylinder (a barrel lying down, a tunnel, a pipe) along axis 'x' or 'z', starting at a = the axis
        centre of the first slice, `length` slices long. hollow → a shell `thick` blocks thick; upper → only the top half
        (y ≥ axis y: a barrel roof on walls). blk may be a function (x, y, z, angle_deg) → block, e.g. staves in bands.
        Returns the (u, v) offsets of the cross-section (u across, v up) so ends/rings can reuse them."""
        R = int(math.ceil(r)) + 1
        cells = []
        for u in range(-R, R + 1):
            for v in range(0 if upper else -R, R + 1):
                d = math.hypot(u, v)
                if d <= r + .5 and (not hollow or d > r + .5 - thick):
                    cells.append((u, v))
        for t in range(length):
            for u, v in cells:
                p = (a[0] + t, a[1] + v, a[2] + u) if axis == "x" else (a[0] + u, a[1] + v, a[2] + t)
                self.set(p, blk(*p, math.degrees(math.atan2(v, u))) if callable(blk) else blk)
        return cells

    def arch(self, a, b, rise, blk, thick=1, depth=1):
        """Elliptic arch standing on two feet a and b (same y, in a line along x or z): half-width = half the distance,
        height `rise` above the feet, band `thick` blocks, extruded `depth` blocks sideways (+x or +z)."""
        axis = 0 if a[2] == b[2] else 2
        lo, hi = min(a[axis], b[axis]), max(a[axis], b[axis])
        c, w = (lo + hi) / 2, (hi - lo) / 2 + .5
        for s in range(lo, hi + 1):
            for v in range(0, rise + 1):
                u = s - c
                e_out = (u / w) ** 2 + (v / (rise + .5)) ** 2
                e_in = (u / max(.5, w - thick)) ** 2 + (v / max(.5, rise + .5 - thick)) ** 2
                if e_out <= 1 and e_in > 1:
                    for d in range(depth):
                        p = [a[0], a[1] + v, a[2]]
                        p[axis] = s
                        p[2 - axis] += d
                        self.set(tuple(p), blk)

    def lattice(self, cells, frame, glass, step=3, diagonal=True):
        """Window with a grid over a flat set of cells (all same x, same z or same y): diagonal → a diamond lattice
        (leaded-glass look), else a square grid every `step`."""
        cells = list(cells)
        xs, ys, zs = {c[0] for c in cells}, {c[1] for c in cells}, {c[2] for c in cells}
        for (x, y, z) in cells:
            u, v = (z, y) if len(xs) == 1 else (x, y) if len(zs) == 1 else (x, z)
            on = ((u + v) % step == 0 or (u - v) % step == 0) if diagonal else (u % step == 0 or v % step == 0)
            self.set((x, y, z), frame if on else glass)

    def bunting(self, a, b, colors=("red_concrete", "yellow_concrete", "blue_concrete", "white_concrete"), tag="bunting", spacing=1.6, size=(0.45, 0.7)):
        """A string of little flags between a and b (same y, along x or z): a chain line + thin block_display flags
        hanging under it. Re-running replaces the flags (kill by tag first)."""
        axis = 0 if a[2] == b[2] else 2
        lo, hi = min(a[axis], b[axis]), max(a[axis], b[axis])
        for s in range(lo, hi + 1):
            p = list(a); p[axis] = s
            self.set(tuple(p), f"iron_chain[axis={'x' if axis == 0 else 'z'}]")
        self.before(f"kill @e[type=block_display,tag={tag}]")
        n = int((hi - lo) / spacing)
        for i in range(n):
            s = lo + 0.4 + i * spacing
            c = colors[i % len(colors)]
            w, h = size
            sx, sz = (w, 0.04) if axis == 0 else (0.04, w)
            p = [a[0] + 0.5, a[1] + 0.35 - h, a[2] + 0.5]; p[axis] = s
            self.cmd(f'summon block_display {p[0]:.2f} {p[1]:.2f} {p[2]:.2f} {{Tags:["{tag}"],block_state:{{Name:"minecraft:{c}"}},'
                     f'transformation:{{left_rotation:[0f,0f,0f,1f],right_rotation:[0f,0f,0f,1f],translation:[0f,0f,0f],scale:[{sx}f,{h}f,{sz}f]}}}}')

    def sign(self, p, text_json, facing="south", tag="sign", scale=1.0, bg=0, line_width=200):
        """Flat text on a wall (text_display, billboard fixed), readable from the `facing` side. p = the point just in
        front of the wall face. text_json: a JSON text component (see text_json / rainbow)."""
        yaw = {"south": 0, "west": 90, "north": 180, "east": -90}[facing]
        self.cmd(f'summon text_display {p[0]} {p[1]} {p[2]} {{billboard:"fixed",Rotation:[{yaw}f,0f],Tags:["{tag}"],background:{bg},line_width:{line_width},'
                 f'brightness:{{sky:15,block:15}},transformation:{{left_rotation:[0f,0f,0f,1f],right_rotation:[0f,0f,0f,1f],translation:[0f,0f,0f],'
                 f'scale:[{scale}f,{scale}f,{scale}f]}},text:{text_json}}}')

    def lamp_post(self, p, height=2, post="dark_oak_fence", top="lantern"):
        """A street lamp: `height` fence posts on p (the block above the ground) + a lantern on top."""
        for i in range(height):
            self.set((p[0], p[1] + i, p[2]), post)
        self.set((p[0], p[1] + height, p[2]), top)

    # ── raw commands ────────────────────────────────────────────────
    def cmd(self, c):
        self.raw.append(c)

    def before(self, c):
        self.pre.append(c)

    def text_display(self, p, text_json, tag, scale=1.0, billboard="center", bg=1073741824, yaw=0):
        self.raw.append(
            f'summon text_display {p[0]} {p[1]} {p[2]} {{billboard:"{billboard}",Tags:["{tag}"],alignment:"center",Rotation:[{yaw}f,0f],'
            f'background:{bg},brightness:{{sky:15,block:15}},transformation:{{left_rotation:[0f,0f,0f,1f],right_rotation:[0f,0f,0f,1f],'
            f'translation:[0f,0f,0f],scale:[{scale}f,{scale}f,{scale}f]}},text:{text_json}}}')

    def tree(self, p, kind="oak_bees_002"):
        """A vanilla tree grown from a feature at p = the block ABOVE the ground. Verified kinds: fancy_oak_bees_002,
        oak_bees_002, birch_bees_002, super_birch_bees_0002, cherry_bees_005, dark_oak, azalea_tree, spruce, fancy_oak,
        birch, pine, jungle_bush. Needs dirt/grass under it and air around it; a tree that does not fit silently fails."""
        self.raw.append(f"place feature minecraft:{kind} {p[0]} {p[1]} {p[2]}")

    # ── output ──────────────────────────────────────────────────────
    def commands(self):
        """Voxels → commands: per y layer (bottom first), same-block runs along x merged across z into fills."""
        out = list(self.pre)
        by_y = {}
        for (x, y, z), b in self.v.items():
            by_y.setdefault(y, {})[(x, z)] = b
        for y in sorted(by_y):
            layer = by_y[y]
            runs = {}
            for z in sorted({k[1] for k in layer}):
                xs = sorted(k[0] for k in layer if k[1] == z)
                i = 0
                while i < len(xs):
                    x1 = xs[i]; b = layer[(x1, z)]; j = i
                    while j + 1 < len(xs) and xs[j + 1] == xs[j] + 1 and layer[(xs[j + 1], z)] == b:
                        j += 1
                    runs.setdefault((x1, xs[j], b), []).append(z)
                    i = j + 1
            for (x1, x2, b), zs in runs.items():
                zs.sort(); i = 0
                while i < len(zs):
                    j = i
                    while j + 1 < len(zs) and zs[j + 1] == zs[j] + 1:
                        j += 1
                    z1, z2 = zs[i], zs[j]
                    out.append(f"setblock {x1} {y} {z1} {b}" if (x1 == x2 and z1 == z2) else f"fill {x1} {y} {z1} {x2} {y} {z2} {b}")
                    i = j + 1
        return out + self.raw

    def bounds(self):
        if not self.v:
            return None
        ks = list(self.v)
        return [min(k[i] for k in ks) for i in range(3)], [max(k[i] for k in ks) for i in range(3)]

    def counts(self):
        c = {}
        for b in self.v.values():
            k = b.split("[")[0]
            c[k] = c.get(k, 0) + 1
        return dict(sorted(c.items(), key=lambda kv: -kv[1]))

    def save(self, name, chunk=1200):
        """Write jobs/<name>.json (or <name>-1.json, -2 … when longer than chunk commands). Returns the file list
        relative to the repo, ready for minecraft_run_command commands_files:[...]. Deletes stale chunks of <name>."""
        cmds = self.commands()
        path = name if os.path.isabs(name) or os.sep in name else os.path.join(JOBS, name)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        base = os.path.basename(path)
        for f in os.listdir(os.path.dirname(path) or "."):
            if f.startswith(base + "-") and f[len(base) + 1:-5].isdigit() and f.endswith(".json"):
                os.remove(os.path.join(os.path.dirname(path), f))
        if len(cmds) <= chunk:
            files = [path + ".json"]
            json.dump(cmds, open(files[0], "w"), ensure_ascii=False)
        else:
            files = []
            for i in range(0, len(cmds), chunk):
                f = f"{path}-{i // chunk + 1}.json"
                json.dump(cmds[i:i + chunk], open(f, "w"), ensure_ascii=False)
                files.append(f)
        rel = [os.path.relpath(f, ROOT).replace(os.sep, "/") for f in files]
        print(f"{name}: {len(self.v)} voxels -> {len(cmds)} commands -> {rel}; bounds {self.bounds()}")
        return rel

    def save_cells(self, name):
        """Dump every planned non-air cell for the one-call pre-flight scan (reference/large-builds.md)."""
        d = os.environ.get("PINKGOLEM_CU_DATA")
        if not d:
            return None
        os.makedirs(d, exist_ok=True)
        cells = [[x, y, z, b] for (x, y, z), b in sorted(self.v.items()) if b != "air"]
        json.dump(cells, open(os.path.join(d, f"{name}_cells.json"), "w"))
        return f"script in cu run l=read_file('{name}_cells','json'); ..."


class Frame:
    """A local coordinate system for one building: write it once, place it facing any direction.
    origin = the front-left corner at ground level (as seen standing in front of the building, looking at it)."""

    def __init__(self, x, y, z, facing="south"):
        self.o = (x, y, z)
        self.facing = facing
        nx, nz = DIRS[facing]                  # outward normal of the front
        self.r = (nz, -nx)                     # viewer's right when looking at the front
        self.back = (-nx, -nz)                 # depth direction (into the building)
        self.names = {"front": facing, "back": OPPOSITE[facing], "right": dir_name(*self.r), "left": dir_name(-self.r[0], -self.r[1])}
        self.names["axis_i"] = "x" if self.r[0] else "z"
        self.names["axis_k"] = "z" if self.r[0] else "x"

    def p(self, i, j, k):
        """Local (i, j, k) → world (x, y, z)."""
        return (self.o[0] + i * self.r[0] + k * self.back[0], self.o[1] + j, self.o[2] + i * self.r[1] + k * self.back[1])

    def d(self, local):
        """'front' | 'back' | 'left' | 'right' → 'north' | 'south' | 'east' | 'west'."""
        return self.names[local]

    def blk(self, s):
        """Fill {front}/{back}/{left}/{right}/{axis_i}/{axis_k} in a block string."""
        for k, v in self.names.items():
            s = s.replace("{" + k + "}", v)
        return s

    def set(self, b, loc, blk):
        b.set(self.p(*loc), self.blk(blk))

    def box(self, b, a, c, blk):
        b.box(self.p(*a), self.p(*c), self.blk(blk))

    def clear(self, b, a, c):
        b.box(self.p(*a), self.p(*c), "air")

    def walls(self, b, a, c, blk):
        b.walls(self.p(*a), self.p(*c), self.blk(blk))

    def door(self, b, loc, blk="oak_door", into="back", hinge="left"):
        """Door whose lower half is at loc. into = the local direction you walk when you go IN ('back' for a front
        door: its panel ends up flush with the outside of the front wall)."""
        b.door(self.p(*loc), blk, facing=self.d(into), hinge=hinge)

    def sub(self, i, j, k, facing="front"):
        """A frame for a group of parts along a wall: origin at local (i, j, k), its front facing the local direction
        `facing`. E.g. a counter along the RIGHT wall, facing into the room: f.sub(i_wall - 1, 0, k_last, "left") —
        the sub-frame's i then runs from k_last toward the front. Check the result with a preview."""
        return Frame(*self.p(i, j, k), self.d(facing))

    def world_box(self, a, c):
        pa, pc = self.p(*a), self.p(*c)
        return [min(pa[i], pc[i]) for i in range(3)], [max(pa[i], pc[i]) for i in range(3)]


# ── shapes on the ground plane ──────────────────────────────────────
def disk(cx, cz, r):
    """Cells of a filled circle, radius r (d² ≤ (r+0.5)²)."""
    R = int(math.ceil(r)) + 1
    return [(cx + dx, cz + dz) for dx in range(-R, R + 1) for dz in range(-R, R + 1) if dx * dx + dz * dz <= (r + .5) ** 2]


def ring(cx, cz, r):
    """Cells of a 1-thick circle outline (no diagonal gaps)."""
    inner = set(disk(cx, cz, r - 1))
    return [c for c in disk(cx, cz, r) if c not in inner]


def rect_ring(x1, z1, x2, z2):
    return [(x, z) for x in range(x1, x2 + 1) for z in range(z1, z2 + 1) if x in (x1, x2) or z in (z1, z2)]


class ValueNoise:
    """Deterministic 2D value noise, fbm() in about [-1, 1]."""

    def __init__(self, seed=1):
        self.seed = seed

    def _h(self, x, z):
        n = (x * 374761393 + z * 668265263 + self.seed * 1442695040888963407) & 0xFFFFFFFF
        n = ((n ^ (n >> 13)) * 1274126177) & 0xFFFFFFFF
        return ((n ^ (n >> 16)) & 0xFFFF) / 32767.5 - 1

    def noise(self, x, z):
        x0, z0 = math.floor(x), math.floor(z)
        fx, fz = x - x0, z - z0
        sx, sz = fx * fx * (3 - 2 * fx), fz * fz * (3 - 2 * fz)
        a = self._h(x0, z0) + (self._h(x0 + 1, z0) - self._h(x0, z0)) * sx
        b = self._h(x0, z0 + 1) + (self._h(x0 + 1, z0 + 1) - self._h(x0, z0 + 1)) * sx
        return a + (b - a) * sz

    def fbm(self, x, z, octaves=3):
        t, a, f, norm = 0, 1, 1, 0
        for _ in range(octaves):
            t += a * self.noise(x * f, z * f)
            norm += a
            a *= .5
            f *= 2
        return t / norm


def rainbow(text, bold=True, colors=("#FF5555", "#FFAA00", "#FFFF55", "#55FF55", "#55FFFF", "#5599FF", "#AA55FF", "#FF55FF")):
    """JSON text component list with one colour per character (for text_display / tellraw / title)."""
    return "[" + ",".join('{"text":%s,"color":"%s","bold":%s}' % (json.dumps(ch, ensure_ascii=False), colors[i % len(colors)], str(bold).lower())
                          for i, ch in enumerate(text)) + "]"


def text_json(s, color="white", bold=False):
    return json.dumps({"text": s, "color": color, "bold": bold}, ensure_ascii=False)


def parse_args(defaults=None):
    """Standard blueprint arguments: --at x,y,z (front-left ground corner; y = the ground block), --facing, --name,
    --style. Example: python3 cottage.py --at 100,-61,40 --facing south"""
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--at", required=True, help="x,y,z of the front-left corner at ground level (y = the ground block, e.g. -61 on a flat world)")
    ap.add_argument("--facing", default="south", choices=list(DIRS), help="the side the front/door faces")
    ap.add_argument("--name", default=(defaults or {}).get("name"))
    ap.add_argument("--style", default=(defaults or {}).get("style", "default"))
    ap.add_argument("--seed", type=int, default=1)
    # argparse reads "--at -116,-61,280" as two options (the value starts with "-") — join them first
    argv, i = list(sys.argv[1:]), 0
    while i < len(argv) - 1:
        if argv[i] == "--at" and argv[i + 1].startswith("-"):
            argv[i:i + 2] = ["--at=" + argv[i + 1]]
        i += 1
    a = ap.parse_args(argv)
    a.x, a.y, a.z = (int(float(v)) for v in a.at.split(","))
    return a


if __name__ == "__main__":
    b = Build()
    f = Frame(0, GROUND, 0, "east")
    f.box(b, (0, 0, 0), (6, 0, 4), "oak_planks")
    f.walls(b, (0, 1, 0), (6, 3, 4), "stone_bricks")
    f.door(b, (3, 1, 0))
    print(len(b.commands()), b.counts(), f.names)
