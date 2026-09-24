"""parts — ready-made building components on top of mclib (furniture, roofs, stairs, windows, lamps, gardens, round
towers, pools, displays). Every function takes a Build `b` and, for oriented parts, a Frame `f`, and writes voxels
(or raw commands) — nothing is sent to the server until you save and run the job.

Local coordinates are Frame coordinates (i = left→right along the front, j = up from the ground level, k = depth).
"Faces" arguments are local directions: 'front' | 'back' | 'left' | 'right'.
See skill/clawdblock/reference/*.md for pictures in words, rules and pitfalls; catalog.py builds one of everything.
"""
import math
import random

from mclib import Build, Frame, DIRS, OPPOSITE, disk, ring, text_json

TURN_LEFT = {"front": "left", "left": "back", "back": "right", "right": "front"}
BACKWARD = {"front": "back", "back": "front", "left": "right", "right": "left"}


def step(f, loc, local_dir, n=1):
    """Move n cells from loc in a local direction."""
    i, j, k = loc
    di, dk = {"front": (0, -1), "back": (0, 1), "left": (-1, 0), "right": (1, 0)}[local_dir]
    return (i + di * n, j, k + dk * n)


# ══════════════════════════ walls, windows, doors ══════════════════════════
def room(b, f, i1, k1, i2, k2, floor_j, height, wall, floor="oak_planks", ceiling=None, corner=None):
    """A box room: floor at floor_j (usually 0 = the ground level), walls floor_j+1 .. floor_j+height,
    optional ceiling (floor_j+height+1) and corner pillars (e.g. 'stripped_oak_log')."""
    f.box(b, (i1, floor_j, k1), (i2, floor_j, k2), floor)
    f.walls(b, (i1, floor_j + 1, k1), (i2, floor_j + height, k2), wall)
    if corner:
        for (i, k) in ((i1, k1), (i2, k1), (i1, k2), (i2, k2)):
            f.box(b, (i, floor_j + 1, k), (i, floor_j + height, k), corner)
    if ceiling:
        f.box(b, (i1, floor_j + height + 1, k1), (i2, floor_j + height + 1, k2), ceiling)
    f.clear(b, (i1 + 1, floor_j + 1, k1 + 1), (i2 - 1, floor_j + height, k2 - 1))
    return {"inside": ((i1 + 1, k1 + 1), (i2 - 1, k2 - 1)), "floor": floor_j, "top": floor_j + height}


def window(b, f, i, j, k, width=2, height=2, along="i", glass="glass_pane", sill=None, shutters=None):
    """A window opening filled with glass. along='i' for a front/back wall, 'k' for a side wall.
    Panes are given explicit connections so they look like one sheet. sill = a block string under it (e.g.
    'spruce_trapdoor[half=top,facing={front}]' outside); shutters = a trapdoor block name (e.g. 'spruce_trapdoor'),
    placed open and flat against the wall on both sides of a front/back window."""
    pane = glass.endswith("_pane")
    for w in range(width):
        for h in range(height):
            loc = (i + w, j + h, k) if along == "i" else (i, j + h, k + w)
            if pane:
                a, c = ("{left}", "{right}") if along == "i" else ("{front}", "{back}")
                f.set(b, loc, f"{glass}[{a}=true,{c}=true]")
            else:
                f.set(b, loc, glass)
    if sill:
        for w in range(width):
            f.set(b, (i + w, j - 1, k - 1) if along == "i" else (i - 1, j - 1, k + w), sill)
    if shutters and along == "i":   # open trapdoors flat against the outside of the wall, left and right of the window
        for h in range(height):
            for ii in (i - 1, i + width):
                f.set(b, (ii, j + h, k - 1), f"{shutters}[facing={{front}},open=true,half=bottom]")


def doorway(b, f, i, j, k, material="oak", into="back", double=False, frame=None, step_block=None):
    """A door (or double door) at (i, j, k) — j is the lower half's level (floor + 1). Carves the opening first.
    frame = block for a 1-block surround (e.g. 'stripped_oak_log'); step_block = a slab/stair outside the door."""
    width = 2 if double else 1
    f.clear(b, (i, j, k), (i + width - 1, j + 1, k))
    f.door(b, (i, j, k), f"{material}_door", into=into, hinge="left")
    if double:
        f.door(b, (i + 1, j, k), f"{material}_door", into=into, hinge="right")
    if frame:
        for h in range(3):
            f.set(b, (i - 1, j + h, k), frame)
            f.set(b, (i + width, j + h, k), frame)
        f.box(b, (i, j + 2, k), (i + width - 1, j + 2, k), frame)
    if step_block:
        f.box(b, (i, j - 1, k - 1), (i + width - 1, j - 1, k - 1), step_block)


# ══════════════════════════ roofs ══════════════════════════
def gable_roof(b, f, i1, k1, i2, k2, j, stairs="spruce_stairs", full="spruce_planks", ridge="i", overhang=1,
               gable_fill=None, slab=None):
    """Pitched roof over the rectangle i1..i2 × k1..k2 (the outer walls), first row at level j (one above the wall
    top). ridge='i': the ridge runs left-right (slopes face front and back, gable walls on the sides);
    ridge='k': the ridge runs front-back (the gable faces the front — the classic cottage look).
    Every row is one higher and one further in; stairs face the ridge (they rise toward it). An odd span gets a ridge
    row of slabs. gable_fill = the block that closes the triangle under the roof at both gable ends.
    Returns the level of the ridge."""
    slab = slab or full.replace("_planks", "_slab")
    if ridge == "i":      # slope rows along i, stepping in along k
        lo, hi, a, c = k1 - overhang, k2 + overhang, i1 - overhang, i2 + overhang
        up, down = "back", "front"
        cell = lambda along, across, y: (along, y, across)
        ends, span_lo, span_hi = (i1, i2), k1, k2
    else:                 # slope rows along k, stepping in along i
        lo, hi, a, c = i1 - overhang, i2 + overhang, k1 - overhang, k2 + overhang
        up, down = "right", "left"
        cell = lambda along, across, y: (across, y, along)
        ends, span_lo, span_hi = (k1, k2), i1, i2
    span = hi - lo + 1
    for n in range((span + 1) // 2):
        y = j + n
        x1, x2 = lo + n, hi - n
        for t in range(a, c + 1):
            if x1 == x2:
                f.set(b, cell(t, x1, y), f"{slab}[type=bottom]")
            else:
                f.set(b, cell(t, x1, y), f"{stairs}[facing={{{up}}},half=bottom]")
                f.set(b, cell(t, x2, y), f"{stairs}[facing={{{down}}},half=bottom]")
        if gable_fill:
            for across in range(max(x1 + 1, span_lo), min(x2 - 1, span_hi) + 1):
                for e in ends:
                    f.set(b, cell(e, across, y), gable_fill)
    return j + (span + 1) // 2 - 1


def hip_roof(b, f, i1, k1, i2, k2, j, stairs="dark_oak_stairs", full="dark_oak_planks", overhang=1):
    """Four-sided roof: each layer is a ring of stairs facing inward, one smaller per level; corners are full blocks
    (stairs placed by commands don't round their corners), the top is filled."""
    a1, c1, a2, c2 = i1 - overhang, k1 - overhang, i2 + overhang, k2 + overhang
    y = j
    while a1 <= a2 and c1 <= c2:
        if a2 - a1 < 2 or c2 - c1 < 2:
            f.box(b, (a1, y, c1), (a2, y, c2), full)
            return y
        for i in range(a1 + 1, a2):
            f.set(b, (i, y, c1), f"{stairs}[facing={{back}}]")
            f.set(b, (i, y, c2), f"{stairs}[facing={{front}}]")
        for k in range(c1 + 1, c2):
            f.set(b, (a1, y, k), f"{stairs}[facing={{right}}]")
            f.set(b, (a2, y, k), f"{stairs}[facing={{left}}]")
        for (i, k) in ((a1, c1), (a2, c1), (a1, c2), (a2, c2)):
            f.set(b, (i, y, k), full)
        a1, c1, a2, c2, y = a1 + 1, c1 + 1, a2 - 1, c2 - 1, y + 1
    return y


def flat_roof(b, f, i1, k1, i2, k2, j, roof="smooth_stone_slab[type=bottom]", parapet=None, overhang=0, trim=None):
    """Flat roof at level j (+ optional overhang), parapet = a wall ring one block high on top (e.g. 'white_concrete'),
    trim = a ring under the overhang edge (e.g. 'quartz_slab[type=top]'). Modern houses: overhang 1, trim black."""
    f.box(b, (i1 - overhang, j, k1 - overhang), (i2 + overhang, j, k2 + overhang), roof)
    if parapet:
        f.walls(b, (i1 - overhang, j + 1, k1 - overhang), (i2 + overhang, j + 1, k2 + overhang), parapet)
    if trim and overhang:
        f.walls(b, (i1 - overhang, j, k1 - overhang), (i2 + overhang, j, k2 + overhang), trim)
    return j


def cone_roof(b, cx, y, cz, r, block="dark_prismarine", tip="lightning_rod", taper=1.0, cap_slab=None):
    """Stepped cone for a round tower (world coords): one ring per level, radius shrinking by `taper`, then a tip."""
    rr = r + 1
    while rr >= 0.5:
        for (x, z) in ring(cx, cz, int(round(rr))):
            b.set((x, y, z), block)
        if cap_slab and rr < 1.5:
            b.set((cx, y, cz), cap_slab)
        rr -= taper
        y += 1
    b.set((cx, y - 1, cz), block)
    if tip:
        b.set((cx, y, cz), tip)
    return y


def dome(b, cx, y, cz, r, block="white_concrete", glass=None):
    """Hemisphere shell on level y (world coords); glass = every 3rd ring of a glass block for a lantern dome."""
    for dx in range(-r - 1, r + 2):
        for dz in range(-r - 1, r + 2):
            for dy in range(0, r + 2):
                d = dx * dx + dy * dy + dz * dz
                if (r - .5) ** 2 < d <= (r + .5) ** 2:
                    b.set((cx + dx, y + dy, cz + dz), glass if glass and dy % 3 == 1 and dy < r - 1 else block)


# ══════════════════════════ stairs and ladders ══════════════════════════
def straight_stairs(b, f, i, j, k, rise, going="back", stairs="oak_stairs", width=1, support="oak_planks", headroom=3):
    """A flight going `rise` steps up in a local direction, starting at (i, j, k) = the first step (j = floor+1).
    Carves headroom above every step and fills under the steps with `support` (None = open). Returns the landing
    cell (where you stand after the last step)."""
    loc = (i, j, k)
    side = TURN_LEFT[TURN_LEFT[TURN_LEFT[going]]]   # to the right of the walking direction
    for n in range(rise):
        for w in range(width):
            c = step(f, loc, side, w)
            f.set(b, c, f"{stairs}[facing={{{going}}},half=bottom]")
            for h in range(1, headroom + 1):
                f.set(b, (c[0], c[1] + h, c[2]), "air")
            if support:
                for s in range(j, c[1]):
                    f.set(b, (c[0], s, c[2]), support)
        loc = step(f, (loc[0], loc[1] + 1, loc[2]), going)
    return loc


def spiral_stairs(b, cx, y1, y2, cz, core="quartz_pillar", stairs="oak_stairs", clear=True):
    """Tight spiral around a 1-block core (world coords): the 8 cells around (cx, cz) in clockwise order, one step
    up per cell, each stair facing the next cell (so every move is a straight step). y1 = first step level, y2 = the
    level of the floor you arrive on. clear=True carves 3 blocks of headroom above every step (never through the
    arrival floor). Floors the spiral passes through need a hole: open the 3x3 around the core except the returned
    arrival cell (see blueprints/tower.py). Returns the (dx, dz) offset of the arrival cell."""
    order = [(0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)]
    for y in range(y1, y2 + 1):
        b.set((cx, y, cz), core)
    y = y1
    n = 0
    while y < y2:
        dx, dz = order[n % 8]
        nx, nz = order[(n + 1) % 8]
        facing = {(1, 0): "east", (-1, 0): "west", (0, 1): "south", (0, -1): "north"}[(nx - dx, nz - dz)]
        b.set((cx + dx, y, cz + dz), f"{stairs}[facing={facing},half=bottom]")
        if clear:
            for h in range(1, 4):
                if y + h < y2 or n < 5:          # never punch through the floor you arrive on, except the stair hole
                    b.set((cx + dx, y + h, cz + dz), "air")
        y += 1
        n += 1
    return order[n % 8]


def ladder(b, x, y1, y2, z, facing):
    """Ladder column in world coords. facing = the direction a climber faces AWAY from — i.e. the open side: a ladder
    on the north side of a wall block (the wall is south of it) has facing=north."""
    for y in range(y1, y2 + 1):
        b.set((x, y, z), f"ladder[facing={facing}]")


# ══════════════════════════ furniture (j = floor + 1) ══════════════════════════
def bed(b, f, i, j, k, color="red", head="back"):
    """A bed: foot at (i, j, k), head one cell toward `head`. Both halves are cleared first (placing half over an old
    bed pops it)."""
    hc = step(f, (i, j, k), head)
    for c in ((i, j, k), hc):
        b.before(f"setblock {' '.join(map(str, f.p(*c)))} air")
    f.set(b, (i, j, k), f"{color}_bed[part=foot,facing={{{head}}}]")
    f.set(b, hc, f"{color}_bed[part=head,facing={{{head}}}]")


def chair(b, f, i, j, k, wood="oak", faces="front"):
    """A chair = a stair whose back is behind the sitter: a sitter facing `faces` → stairs facing the opposite way."""
    f.set(b, (i, j, k), f"{wood}_stairs[facing={{{BACKWARD[faces]}}},half=bottom]")


def table(b, f, i, j, k, wood="oak", style="post"):
    """1-block table. style 'post' = fence + pressure plate (classic), 'slab' = top slab on a fence, 'glass' = a
    top slab of quartz on an end rod (modern)."""
    if style == "post":
        f.set(b, (i, j, k), f"{wood}_fence"); f.set(b, (i, j + 1, k), f"{wood}_pressure_plate")
    elif style == "slab":
        f.set(b, (i, j, k), f"{wood}_slab[type=top]")
    else:
        f.set(b, (i, j, k), "end_rod[facing=up]"); f.set(b, (i, j + 1, k), "smooth_quartz_slab[type=bottom]")


def dining_set(b, f, i, j, k, length=3, wood="dark_oak", chairs="spruce"):
    """A table `length` long along i with chairs on both long sides (front row faces back, back row faces front)."""
    for n in range(length):
        f.set(b, (i + n, j, k), f"{wood}_slab[type=top]")
        chair(b, f, i + n, j, k - 1, chairs, faces="back")
        chair(b, f, i + n, j, k + 1, chairs, faces="front")


def sofa(b, f, i, j, k, length=3, wood="oak", faces="front", arms="spruce_trapdoor"):
    """A sofa along i: a row of stairs (backrest behind the sitter) with open trapdoors as arm rests at both ends.
    The stair material is the colour: quartz = white, crimson = red, warped = teal, dark_oak = brown, cherry = pink
    (concrete and wool have no stairs)."""
    for n in range(length):
        chair(b, f, i + n, j, k, wood, faces)
    if arms:
        f.set(b, (i - 1, j, k), f"{arms}[facing={{left}},open=true,half=bottom]")
        f.set(b, (i + length, j, k), f"{arms}[facing={{right}},open=true,half=bottom]")


def bookshelf_wall(b, f, i, j, k, width=3, height=2, wood="oak"):
    """Bookshelves with a slab shelf on top."""
    f.box(b, (i, j, k), (i + width - 1, j + height - 1, k), "bookshelf")
    f.box(b, (i, j + height, k), (i + width - 1, j + height, k), f"{wood}_slab[type=bottom]")


def kitchen(b, f, i, j, k, length=4, faces="front"):
    """A counter run along i against a wall: smoker, cabinets (barrels), a sink (water cauldron), a furnace, wall
    cabinets (barrels) above and a lantern on the counter. faces = where the cook stands (appliances face that way)."""
    items = ["smoker[facing={%s},lit=false]" % faces, "barrel[facing=up]", "water_cauldron[level=3]", "barrel[facing=up]",
             "furnace[facing={%s},lit=false]" % faces, "barrel[facing=up]"]
    for n in range(length):
        f.set(b, (i + n, j, k), items[n % len(items)])
        f.set(b, (i + n, j + 2, k), "barrel[facing={%s}]" % faces)          # wall cabinets above the counter
    f.set(b, (i + length // 2, j + 1, k), "lantern[hanging=false]")


def lamp(b, f, i, j, k, kind="lantern", ceiling_j=None, chain=1):
    """kind 'lantern' (floor: fence + lantern), 'hanging' (chain(s) from the ceiling at ceiling_j + lantern),
    'modern' (end rod), 'table' (a candle on a slab — lit)."""
    if kind == "lantern":
        f.set(b, (i, j, k), "spruce_fence"); f.set(b, (i, j + 1, k), "lantern[hanging=false]")
    elif kind == "hanging":
        top = ceiling_j if ceiling_j is not None else j + 3
        for c in range(chain):
            f.set(b, (i, top - 1 - c, k), "iron_chain[axis=y]")
        f.set(b, (i, top - 1 - chain, k), "lantern[hanging=true]")
    elif kind == "modern":
        f.set(b, (i, j, k), "end_rod[facing=up]")
    else:
        f.set(b, (i, j, k), "white_candle[candles=3,lit=true]")


def chandelier(b, f, i, j_ceiling, k, arms=True):
    """A chain from the ceiling with a lantern cross: lanterns hanging from fences around a central chain."""
    f.set(b, (i, j_ceiling - 1, k), "iron_chain[axis=y]")
    f.set(b, (i, j_ceiling - 2, k), "iron_chain[axis=y]")
    f.set(b, (i, j_ceiling - 3, k), "lantern[hanging=true]")
    if arms:
        for d in ("front", "back", "left", "right"):
            c = step(f, (i, j_ceiling - 2, k), d)
            f.set(b, c, "iron_bars")
            f.set(b, (c[0], c[1] - 1, c[2]), "lantern[hanging=true]")


def fireplace(b, f, i, j, k, width=3, brick="bricks", chimney_to=None):
    """A fireplace against the wall behind depth k: brick surround with a lit campfire inside and a mantel shelf.
    chimney_to = build a 3-wide brick chimney in the wall behind it (k+1) up to that level, with a smoking campfire
    on top (smoke above the roof is the tell-tale of a warm house)."""
    f.box(b, (i, j, k), (i + width - 1, j + 2, k), brick)
    mid = i + width // 2
    f.set(b, (mid, j, k), "campfire[lit=true,signal_fire=false]")
    f.set(b, (mid, j + 1, k), "air")
    f.box(b, (i, j + 3, k), (i + width - 1, j + 3, k), "stone_brick_slab[type=bottom]")
    if chimney_to:
        f.box(b, (mid - 1, j, k + 1), (mid + 1, chimney_to, k + 1), brick)
        f.set(b, (mid, chimney_to + 1, k + 1), "campfire[lit=true,signal_fire=false]")


def rug(b, f, i1, j, k1, i2, k2, color="red", border=None):
    """Carpet area (on the floor level j = floor + 1), optional border colour."""
    f.box(b, (i1, j, k1), (i2, j, k2), f"{color}_carpet")
    if border:
        f.walls(b, (i1, j, k1), (i2, j, k2), f"{border}_carpet")


def plant(b, f, i, j, k, kind="potted_flowering_azalea_bush"):
    """Indoor plants must be potted (flowers on quartz/planks pop off): potted_* blocks, or a moss_block planter
    replacing the floor under a flower."""
    f.set(b, (i, j, k), kind)


def wardrobe(b, f, i, j, k, wood="spruce", faces="front"):
    """Two tall cabinet: two barrels stacked, door fronts = closed trapdoors on the room side."""
    f.set(b, (i, j, k), f"barrel[facing={{{faces}}}]")
    f.set(b, (i, j + 1, k), f"barrel[facing={{{faces}}}]")
    c = step(f, (i, j, k), faces)
    # an open trapdoor stands against the edge OPPOSITE its facing → facing = faces puts the doors flat on the barrels
    f.set(b, c, f"{wood}_trapdoor[facing={{{faces}}},open=true,half=bottom]")
    f.set(b, (c[0], c[1] + 1, c[2]), f"{wood}_trapdoor[facing={{{faces}}},open=true,half=bottom]")


def tv_wall(b, f, i, j, k, width=3):
    """A flat TV on a wall: black concrete panel on a quartz stand line."""
    f.box(b, (i, j + 1, k), (i + width - 1, j + 2, k), "black_concrete")
    f.box(b, (i, j, k), (i + width - 1, j, k), "smooth_quartz_slab[type=top]")


# ══════════════════════════ outdoors ══════════════════════════
def lamp_post(b, x, y, z, style="classic"):
    """World coords, y = the level above the ground. classic: 2 blackstone walls + lantern; modern: 3 end rods;
    garden: fence + lantern."""
    if style == "classic":
        b.set((x, y, z), "polished_blackstone_wall[up=true]"); b.set((x, y + 1, z), "polished_blackstone_wall[up=true]")
        b.set((x, y + 2, z), "lantern[hanging=false]")
    elif style == "modern":
        for h in range(3):
            b.set((x, y + h, z), "end_rod[facing=up]")
    else:
        b.set((x, y, z), "dark_oak_fence"); b.set((x, y + 1, z), "lantern[hanging=false]")


def bench(b, f, i, j, k, length=2, wood="oak", faces="front"):
    """Outdoor bench: stairs facing away from the view + trapdoor ends."""
    sofa(b, f, i, j, k, length, wood, faces=faces, arms=f"{wood}_trapdoor")


def path(b, cells, y, block="dirt_path", edge=None, edge_y=None):
    """A path replacing the ground at level y (paths go IN the ground, not on it). cells = [(x, z)]; edge = a block
    for the cells around it (e.g. 'coarse_dirt' at y, or 'oak_fence' at y+1 via edge_y)."""
    s = set(cells)
    for (x, z) in s:
        b.set((x, y, z), block)
    if edge:
        for (x, z) in s:
            for dx, dz in DIRS.values():
                n = (x + dx, z + dz)
                if n not in s:
                    b.set((n[0], edge_y if edge_y is not None else y, n[1]), edge)


def path_line(x1, z1, x2, z2, width=3):
    """Cells of a straight path of a given width between two points (world x/z)."""
    cells = set()
    n = max(abs(x2 - x1), abs(z2 - z1)) or 1
    for t in range(n + 1):
        x = round(x1 + (x2 - x1) * t / n); z = round(z1 + (z2 - z1) * t / n)
        for dx in range(-(width // 2), width - width // 2):
            for dz in range(-(width // 2), width - width // 2):
                cells.add((x + dx, z + dz))
    return cells


def flower_bed(b, x1, y, z1, x2, z2, seed=1, density=0.7, soil="grass_block"):
    """Flowers in a rectangle (y = the level above the ground). Flowers pop off anything but soil, so the block under
    each flower becomes `soil` (grass_block, dirt, moss_block; None = trust what is there). Tall flowers get both halves."""
    rnd = random.Random(seed)
    short = ["poppy", "dandelion", "blue_orchid", "allium", "azure_bluet", "red_tulip", "orange_tulip", "white_tulip", "pink_tulip",
             "oxeye_daisy", "cornflower", "lily_of_the_valley"]
    tall = ["rose_bush", "peony", "lilac", "sunflower"]
    for x in range(x1, x2 + 1):
        for z in range(z1, z2 + 1):
            if soil:
                b.set((x, y - 1, z), soil)
            if rnd.random() > density:
                continue
            if rnd.random() < 0.2:
                t = rnd.choice(tall)
                b.set((x, y, z), f"{t}[half=lower]"); b.set((x, y + 1, z), f"{t}[half=upper]")
            else:
                b.set((x, y, z), rnd.choice(short))


def hedge(b, cells, y, height=1, leaves="oak_leaves"):
    """Hedge row of persistent leaves (they never decay)."""
    for (x, z) in cells:
        for h in range(height):
            b.set((x, y + h, z), f"{leaves}[persistent=true]")


def fountain(b, cx, y, cz, r=3, rim="smooth_quartz", water=True, jet="quartz_pillar"):
    """Round fountain: basin (floor at the ground level y-1 replaced by the rim block), rim ring 1 high, water inside,
    a centre pillar with a water source on top (it flows down the pillar into the basin)."""
    for (x, z) in disk(cx, cz, r):
        b.set((x, y - 1, z), rim)
    for (x, z) in ring(cx, cz, r):
        b.set((x, y, z), rim)
    if water:
        for (x, z) in disk(cx, cz, r - 1):
            b.set((x, y, z), "water")
    b.set((cx, y, cz), jet); b.set((cx, y + 1, cz), jet)
    b.set((cx, y + 2, cz), "water" if water else jet)


def pond(b, cx, y, cz, rx=5, rz=4, depth=2, seed=1, lilies=4):
    """A natural pond dug into the ground at level y (the ground block): sand/gravel shore, water `depth` deep,
    lily pads and sea grass. Put water in the LAST job and count it afterwards."""
    rnd = random.Random(seed)
    cells = [(x, z) for x in range(cx - rx - 1, cx + rx + 2) for z in range(cz - rz - 1, cz + rz + 2)
             if ((x - cx) / (rx + .5)) ** 2 + ((z - cz) / (rz + .5)) ** 2 <= 1]
    s = set(cells)
    for (x, z) in cells:
        edge = any((x + dx, z + dz) not in s for dx, dz in DIRS.values())
        d = 1 if edge else depth
        for h in range(d):
            b.set((x, y - h, z), "water")
        b.set((x, y - d, z), rnd.choice(["sand", "sand", "gravel", "clay"]))
    for (x, z) in cells:
        for dx, dz in DIRS.values():
            n = (x + dx, z + dz)
            if n not in s and rnd.random() < 0.5:
                b.set((n[0], y, n[1]), rnd.choice(["sand", "gravel", "coarse_dirt"]))
    inner = [c for c in cells if all((c[0] + dx, c[1] + dz) in s for dx, dz in DIRS.values())]
    for (x, z) in rnd.sample(inner, min(lilies, len(inner))):
        b.set((x, y + 1, z), "lily_pad")
    for (x, z) in rnd.sample(inner, min(len(inner) // 4, 12)):
        b.set((x, y - 1, z), "seagrass")


def pool(b, x1, z1, x2, z2, y, depth=2, rim="smooth_quartz", lining="light_blue_concrete", lights=True):
    """Swimming pool dug in at ground level y: lining on the floor and walls, water, a rim flush with the ground,
    sea lanterns in the walls. Water goes in last."""
    b.box((x1 - 1, y - depth, z1 - 1), (x2 + 1, y, z2 + 1), lining)
    b.box((x1, y - depth + 1, z1), (x2, y, z2), "water")
    for (x, z) in [(x, z) for x in range(x1 - 1, x2 + 2) for z in range(z1 - 1, z2 + 2) if x in (x1 - 1, x2 + 1) or z in (z1 - 1, z2 + 1)]:
        b.set((x, y, z), rim)
    if lights:
        for x in range(x1 + 1, x2, 3):
            b.set((x, y - 1, z1 - 1), "sea_lantern"); b.set((x, y - 1, z2 + 1), "sea_lantern")


def trees(b, cells, y, kinds=("oak_bees_002", "birch_bees_002", "fancy_oak_bees_002"), seed=1, spacing=4):
    """Scatter trees over candidate cells with at least `spacing` blocks between trunks (random packing looks
    natural; a grid looks planted). y = the level above the ground."""
    rnd = random.Random(seed)
    cells = list(cells)
    rnd.shuffle(cells)
    placed = []
    for (x, z) in cells:
        if all((x - px) ** 2 + (z - pz) ** 2 >= spacing ** 2 for px, pz in placed):
            placed.append((x, z))
            b.tree((x, y, z), rnd.choice(kinds))
    return placed


# ══════════════════════════ round towers ══════════════════════════
def round_tower(b, cx, y, cz, r, height, wall="stone_bricks", floor="spruce_planks", windows="glass_pane",
                window_every=4, floors_every=5, roof="cone", roof_block="dark_prismarine", door_facing="south", stairs=True):
    """A round tower (world coords). y = the ground level (floor replaces it). Walls from y+1 to y+height, window
    slits every `window_every` cells of the ring at each storey, floors every `floors_every` blocks with a spiral
    stair through a hole in each floor, a door on the `door_facing` side, a cone (or 'flat' with battlements) roof.
    Returns {'top': y of the roof base, 'door': (x, y+1, z)}."""
    rim = ring(cx, cz, r)
    for (x, z) in disk(cx, cz, r):
        b.set((x, y, z), floor)
    for h in range(1, height + 1):
        for (x, z) in rim:
            b.set((x, y + h, z), wall)
    storeys = list(range(y + floors_every, y + height, floors_every))
    for fy in storeys:
        for (x, z) in disk(cx, cz, r - 1):
            b.set((x, fy, z), floor)
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                b.set((cx + dx, fy, cz + dz), "air")
    # windows: every storey at 2 blocks above its floor
    for fy in [y] + storeys:
        pts = sorted(rim, key=lambda p: math.atan2(p[1] - cz, p[0] - cx))
        for n, (x, z) in enumerate(pts):
            if n % window_every == 0:
                b.set((x, fy + 2, z), windows); b.set((x, fy + 3, z), windows)
    # door
    dx, dz = DIRS[door_facing]
    door = (cx + dx * r, y + 1, cz + dz * r)
    b.door(door, "spruce_door", facing=OPPOSITE[door_facing])
    if stairs and height > floors_every:
        spiral_stairs(b, cx, y + 1, storeys[-1] if storeys else y + height, cz)
    top = y + height + 1
    if roof == "cone":
        for (x, z) in disk(cx, cz, r):
            b.set((x, top - 1, z), floor)
        cone_roof(b, cx, top, cz, r, roof_block)
    else:
        for (x, z) in disk(cx, cz, r):
            b.set((x, top - 1, z), wall)
        for n, (x, z) in enumerate(sorted(rim, key=lambda p: math.atan2(p[1] - cz, p[0] - cx))):
            if n % 2 == 0:
                b.set((x, top, z), wall)
    return {"top": top, "door": door}


# ══════════════════════════ light and displays ══════════════════════════
def light_grid(b, x1, z1, x2, z2, y, step=7, level=15):
    """Invisible light blocks (no collision) on a grid at head height y — stops mobs spawning in dark rooms,
    attics and under trees. Guard with `execute if block ... air` when adding to an existing build."""
    for x in range(x1, x2 + 1, step):
        for z in range(z1, z2 + 1, step):
            b.cmd(f"execute if block {x} {y} {z} air run setblock {x} {y} {z} light[level={level}]")


def stripe_display(b, x, y, z, facing, colors, width=1.2, stripe=0.15, tag="flag", pole="stripped_dark_oak_log"):
    """A precise striped flag/sign made of block_display slivers (banners can't do clean stripes). (x, y, z) = the
    top-left corner on the wall face, facing = the direction the flag faces (out of the wall). colors top→bottom,
    e.g. ['red','orange','yellow','lime','blue','purple'] (concrete colours)."""
    yaw = {"south": 0, "west": 90, "north": 180, "east": -90}[facing]
    for n, col in enumerate(colors):
        b.cmd(f'summon block_display {x} {y - (n + 1) * stripe:.3f} {z} {{Tags:["{tag}"],Rotation:[{yaw}f,0f],block_state:{{Name:"minecraft:{col}_concrete"}},'
              f'transformation:{{left_rotation:[0f,0f,0f,1f],right_rotation:[0f,0f,0f,1f],translation:[0f,0f,0f],scale:[{width}f,{stripe}f,0.03f]}}}}')
    if pole:
        b.cmd(f'summon block_display {x} {y} {z} {{Tags:["{tag}"],Rotation:[{yaw}f,0f],block_state:{{Name:"minecraft:{pole}"}},'
              f'transformation:{{left_rotation:[0f,0f,0.7071f,0.7071f],right_rotation:[0f,0f,0f,1f],translation:[{width + 0.1}f,0f,0f],scale:[0.08f,{width + 0.2}f,0.08f]}}}}')


def label(b, x, y, z, text, tag="label", color="white", scale=0.8, facing=None):
    """Floating text: billboard (turns to the viewer) unless facing is given (fixed, readable from that side)."""
    if facing:
        yaw = {"south": 0, "west": 90, "north": 180, "east": -90}[facing]
        b.text_display((x, y, z), text_json(text, color, True), tag, scale, billboard="fixed", yaw=yaw)
    else:
        b.text_display((x, y, z), text_json(text, color, True), tag, scale)
