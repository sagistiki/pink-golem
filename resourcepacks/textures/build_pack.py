"""build_pack.py — procedural block textures in a natural, near-vanilla look, at any resolution (16, 32, 64 …).

No image is drawn by hand. Every surface is a value field in [0, 1] mapped through a material ramp (dark → light)
whose tones are sampled from the vanilla textures, so the result sits well next to vanilla blocks:
  wood    planks with warped grain that bends around knots, worn edges; bark in vertical plates; log tops with rings
  stone   stone, smooth stone, cobblestone (tileable Voronoi cells lit as domes), stone bricks, bricks
  ground  dirt with clods and pebbles, sand with ripples, gravel, grass (grey + tinted by the game per biome)
  other   glass with a frame and glints, oak leaves (grey + tinted, see-through gaps)
Every texture tiles seamlessly. Feature sizes are tuned at 64 px and scale with K = res / 64.

    python3 build_pack.py [res] [--pixel=N] [--out DIR]
      res        texture size in pixels (default 32)
      --pixel=N  pixel-art shading: each texture keeps only N tones (8 looks clearly pixel-art, 12 softer)
      --out DIR  output folder (default natural_<res>[_p<N>] next to this file); a .zip of it is written too

Needs numpy, scipy and Pillow (pip install numpy scipy pillow). Resource pack format 88 = Minecraft 26.2.
"""
import json
import os
import sys
import zipfile

import numpy as np
from PIL import Image
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
R = int(ARGS[0]) if ARGS else 32
PIXEL = next((int(a.split("=")[1]) for a in sys.argv if a.startswith("--pixel=")), 0)
_out = next((sys.argv[i + 1] for i, a in enumerate(sys.argv[:-1]) if a == "--out"), None)
OUT = _out or os.path.join(HERE, f"natural_{R}" + (f"_p{PIXEL}" if PIXEL else ""))
K = R / 64.0
PACK_FORMAT = 88


def hx(c):
    return np.array([int(c[i:i + 2], 16) for i in (1, 3, 5)], dtype=float)


RAMP = {                                           # dark → light, sampled from the vanilla textures' own tones
    "wood":   [hx("#5a4326"), hx("#826539"), hx("#a3834f"), hx("#bd9c63"), hx("#d4b278")],
    "stone":  [hx("#4b4b4d"), hx("#666668"), hx("#7c7c7e"), hx("#929294"), hx("#aaaaac")],
    "mortar": [hx("#46464a"), hx("#5a5a5e"), hx("#6c6c70")],
    "grass":  [hx("#2f4f22"), hx("#43692e"), hx("#57803a"), hx("#6c9746"), hx("#86b058")],
    "dirt":   [hx("#4e3322"), hx("#6d4a31"), hx("#8b6143"), hx("#a57652"), hx("#bc8c63")],
    "pebble": [hx("#5e5b58"), hx("#7a7773"), hx("#98958f")],
    "spruce": [hx("#3a2a1a"), hx("#5a4027"), hx("#6f5133"), hx("#86633e"), hx("#9b754b")],
    "birch":  [hx("#9c8a60"), hx("#bba878"), hx("#cfbd8c"), hx("#dccb9a"), hx("#e8d9ab")],
    "dark_oak": [hx("#2a1a0c"), hx("#3e2913"), hx("#4f371d"), hx("#614526"), hx("#735330")],
    "oak_bark": [hx("#33261a"), hx("#4a3924"), hx("#614c30"), hx("#76603e"), hx("#8a734d")],
    "spruce_bark": [hx("#1f160e"), hx("#2f2215"), hx("#3f2f1d"), hx("#503d27"), hx("#614a31")],
    "birch_bark": [hx("#b8b5aa"), hx("#d2cfc5"), hx("#e3e1d9"), hx("#efede7"), hx("#f9f8f4")],
    "dark_oak_bark": [hx("#1a130b"), hx("#271c11"), hx("#352618"), hx("#443220"), hx("#523d28")],
    "brick":  [hx("#5a271d"), hx("#7c3829"), hx("#95503f"), hx("#a8624f"), hx("#ba7662")],
    "brick_mortar": [hx("#7f7b76"), hx("#9a9690"), hx("#b3afa8")],
    "sand":   [hx("#b3a174"), hx("#cbbb8b"), hx("#d9cc9f"), hx("#e3d8ae"), hx("#ede4c1")],
    "gravel": [hx("#4a4542"), hx("#645e59"), hx("#7c7570"), hx("#948c86"), hx("#aba39c")],
    "grey":   [hx("#5a5a5a"), hx("#777777"), hx("#909090"), hx("#a8a8a8"), hx("#c2c2c2")],
    "leaf":   [hx("#4a4a4a"), hx("#6c6c6c"), hx("#8c8c8c"), hx("#aaaaaa"), hx("#c8c8c8")],
    "smooth": [hx("#8a8a8c"), hx("#9c9c9e"), hx("#a9a9ab"), hx("#b4b4b6"), hx("#bfbfc1")],
}


def ramp(name, v):
    r = RAMP[name]
    v = np.clip(v, 0, 1) * (len(r) - 1)
    i = np.minimum(len(r) - 2, v.astype(int))
    t = (v - i)[..., None]
    a = np.stack(r)[i]
    b = np.stack(r)[i + 1]
    return a + (b - a) * t


def noise(g, cycles, aniso=(1, 1)):
    """Seamless smooth noise in [-1, 1] with about `cycles` features across the tile."""
    w = g.standard_normal((R, R))
    fy = np.fft.fftfreq(R)[:, None] * R / aniso[1]
    fx = np.fft.fftfreq(R)[None, :] * R / aniso[0]
    spec = np.fft.fft2(w) * np.exp(-(np.sqrt(fx * fx + fy * fy) / cycles) ** 2)
    n = np.real(np.fft.ifft2(spec))
    return n / (np.abs(n).max() + 1e-9)


def fbm(g, base, octaves=4, gain=0.5):
    v, amp, tot = np.zeros((R, R)), 1.0, 0.0
    for o in range(octaves):
        v += noise(g, base * 2 ** o) * amp
        tot += amp
        amp *= gain
    return v / tot


def wrap_warp(field, dx, dy):
    yy, xx = np.mgrid[0:R, 0:R]
    return ndimage.map_coordinates(field, [(yy + dy) % R, (xx + dx) % R], order=1, mode="grid-wrap")


def bevel(mask, width, light=(-0.7, -0.7)):
    d = ndimage.distance_transform_edt(mask)
    e = np.clip(1 - d / width, 0, 1) * mask
    gy, gx = np.gradient(ndimage.gaussian_filter(d, 0.8))
    f = -(gx * light[0] + gy * light[1])
    return e * np.clip(f * 3, -1, 1)


def pixelate(rgb, solid, groups=None):
    """Pixel-art shading: k-means the texture down to PIXEL tones, then let a lone pixel that is only one tone away from
    its neighbours join them (keeps real specks like pebble highlights, removes soft noise). Tiles stay seamless.
    `groups` (int per pixel) quantises each material on its own: the biggest keeps PIXEL tones, the others 3, so mortar
    never borrows a brick colour."""
    from scipy.cluster.vq import kmeans2
    groups = np.zeros(solid.shape, int) if groups is None else groups
    ids = [i for i in np.unique(groups[solid])]
    main = max(ids, key=lambda i: (groups[solid] == i).sum())
    luma = np.array([0.299, 0.587, 0.114])
    tone = np.full(solid.shape, -1)
    pal, grp = [], []
    for i in ids:
        m = solid & (groups == i)
        px = rgb[m].astype(float)
        k = min(PIXEL if i == main else 3, len(np.unique(px.round(), axis=0)))
        cent, lab = kmeans2(px, k, minit="++", seed=np.random.default_rng(7))
        order = np.argsort(cent @ luma)                               # tone index: per group, dark → light
        rank = np.empty(k, int)
        rank[order] = np.arange(k)
        tone[m] = len(pal) + rank[lab]
        pal += list(cent[order])
        grp += [i] * k
    pal, grp = np.array(pal), np.array(grp)
    nb = np.stack([np.roll(tone, s, a) for s, a in ((1, 0), (-1, 0), (1, 1), (-1, 1))])
    lone = solid & (nb != tone).all(0) & (nb >= 0).all(0)
    med = np.median(nb, 0).round().astype(int)
    fix = lone & (np.abs(med - tone) == 1) & (grp[np.clip(med, 0, len(grp) - 1)] == grp[np.clip(tone, 0, len(grp) - 1)])
    tone[fix] = med[fix]
    out = rgb.astype(float).copy()
    out[solid] = pal[tone[solid]]
    return out


def save(rgb, name):
    """rgb, or (rgb, groups) for textures made of several materials (see pixelate)."""
    rgb, groups = rgb if isinstance(rgb, tuple) else (rgb, None)
    p = os.path.join(OUT, "assets/minecraft/textures/block", name + ".png")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    if PIXEL:
        rgb = pixelate(np.clip(rgb, 0, 255), np.ones(rgb.shape[:2], bool), groups)
    Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8)).save(p)
    return p


# ─────────────────────────────── wood ───────────────────────────────
def oak_planks(seed=11, wood="wood"):
    g = np.random.default_rng(seed)
    boards, bh = 4, R // 4
    yy, xx = np.mgrid[0:R, 0:R].astype(float)
    seams = np.zeros((R, R), bool)
    board_id = (yy // bh).astype(int)
    v = np.zeros((R, R))
    for b in range(boards):
        y0 = b * bh
        seams[y0, :] = True
        cut = int((b * 23 + 7) * K) % R                           # one end joint per board, staggered
        seams[y0:y0 + bh, cut] = True
        # grain: bands along the board, warped by low noise, bending around one knot
        warp = noise(g, 3, aniso=(4, 1)) * 2.5 * K + noise(g, 8, aniso=(3, 1)) * 0.8 * K
        kx, ky = g.uniform(0, R), y0 + bh * g.uniform(0.3, 0.7)
        dxk = ((xx - kx + R / 2) % R - R / 2) / (4.5 * K)
        dyk = (yy - ky) / (2.2 * K)
        rk = np.sqrt(dxk ** 2 + dyk ** 2)
        around = np.exp(-rk ** 2 / 3) * np.sign(dyk) * 2.2 * K     # grain pushed apart around the knot
        freq = g.uniform(0.35, 0.55) / K
        phase = noise(g, 4, aniso=(5, 1)) * 3.0                      # bands drift in and out, not a fixed wave
        bands = np.abs(np.sin((yy + warp + around) * freq * np.pi + phase))
        lines = np.clip(1 - bands / 0.18, 0, 1)                      # thin late-wood lines where the band crosses 0
        fade = np.clip(noise(g, 6, aniso=(6, 1)) * 0.8 + 0.6, 0, 1)   # lines come and go along the board
        fibre = noise(g, 30, aniso=(14, 1)) * 0.5 + 0.5
        tone = g.uniform(0.5, 0.62) + noise(g, 2, aniso=(3, 1)) * 0.06
        vb = tone - lines * fade * 0.26 - (1 - bands) * 0.05 - fibre * 0.10
        vb -= np.exp(-rk ** 2 * 1.2) * 0.30 * (rk < 2.5)            # the knot itself, darker
        vb += np.where((rk > 0.9) & (rk < 1.4), -0.08, 0)           # its ring
        m = board_id == b
        v[m] = vb[m]
    solid = ~seams
    v += bevel(solid, 1.4 * K) * 0.10
    v -= ndimage.gaussian_filter(seams.astype(float), 0.9 * K, mode="wrap") * 0.35   # worn, darker edges
    v[seams] = 0.05
    return ramp(wood, v)


# ─────────────────────────────── stone ───────────────────────────────
def stone_bricks(seed=12):
    g = np.random.default_rng(seed)
    rows, rh = 4, R // 4
    mw = max(2, int(round(2 * K)))
    yy, xx = np.mgrid[0:R, 0:R]
    joint = np.zeros((R, R), bool)
    for r in range(rows):
        y0 = r * rh
        joint[y0:y0 + mw, :] = True
        off = 0 if r % 2 == 0 else R // 4
        for x in range(off, R + off, R // 2):
            joint[y0:y0 + rh, x % R:x % R + mw] = True
    # chipped, irregular brick edges: grow the joints where edge noise says so
    edge = ndimage.binary_dilation(joint, iterations=max(1, int(K)), border_value=0)
    chip = noise(g, 14) > 0.45
    joint = joint | (edge & chip)
    brick = ~joint
    lab, n = ndimage.label(brick)
    mottled = fbm(g, 5, 5) * 0.5 + 0.5
    pores = (noise(g, 48) > 0.55).astype(float) * (g.random((R, R)) > 0.3)
    grain = (g.random((R, R)) - 0.5) * 0.10
    v = 0.56 + (mottled - 0.5) * 0.62 - pores * 0.16 + grain
    for k in range(1, n + 1):
        m = lab == k
        v[m] += g.normal(0, 0.06)                                  # each brick a slightly different stone
        ys = np.where(m)[0]
        if len(ys):
            v[m] -= (ys - ys.min()) / max(1, ys.max() - ys.min()) * 0.06   # a touch darker toward the bottom
    v += bevel(brick, 2.4 * K) * 0.26
    ao = ndimage.gaussian_filter(joint.astype(float), 1.3 * K, mode="wrap")
    v -= ao * 0.25
    img = ramp("stone", v)
    # sandy recessed mortar
    mv = 0.45 + noise(g, 45) * 0.25 + (g.random((R, R)) - 0.5) * 0.2
    img[joint] = ramp("mortar", mv)[joint]
    return img, joint.astype(int)


# ─────────────────────────────── grass & dirt ───────────────────────────────
def grass_top(seed=13):
    g = np.random.default_rng(seed)
    clump = noise(g, 5) * 0.5 + 0.5
    v = 0.25 + clump * 0.15 + noise(g, 20) * 0.05
    # three layers of blades: long dark ones underneath, lighter and shorter on top
    for layer, (count, lmin, lmax, val) in enumerate(((1.1, 3, 6, 0.38), (1.0, 2, 5, 0.58), (0.7, 1, 3, 0.8))):
        for _ in range(int(count * R * R / 4)):
            x, y = g.integers(0, R), g.integers(0, R)
            if g.random() > 0.35 + clump[y, x] * 0.6:
                continue
            ln = g.integers(lmin, lmax + 1) * max(1, int(K))
            lean = g.choice([-1, 0, 0, 1])
            for i in range(ln):
                yy_, xx_ = (y - i) % R, (x + (lean if i > ln // 2 else 0)) % R
                v[yy_, xx_] = val + i / ln * 0.12 + g.normal(0, 0.03)
    return ramp("grass", v)


def dirt(seed=14):
    g = np.random.default_rng(seed)
    clods = fbm(g, 6, 4) * 0.5 + 0.5
    lumps = noise(g, 14) * 0.5 + 0.5                               # small clods: light tops, dark undersides
    grit = (g.random((R, R)) - 0.5) * 0.22
    v = 0.46 + (clods - 0.5) * 0.45 + (lumps - 0.5) * 0.42 + grit
    v -= (np.roll(lumps, -1, axis=0) - lumps) * 0.35                 # lit from above
    dark = g.random((R, R)) < 0.05
    v[dark] -= 0.22                                                 # dark grains
    light = g.random((R, R)) < 0.03
    v[light] += 0.18
    yy, xx = np.mgrid[0:R, 0:R]
    stones = np.zeros((R, R), bool)
    for _ in range(int(14 * K) + 6):
        cx, cy = g.integers(0, R), g.integers(0, R)
        rx, ry = max(1.0, g.uniform(0.9, 2.2) * K), max(0.8, g.uniform(0.7, 1.6) * K)
        dx = ((xx - cx + R // 2) % R - R // 2) / rx
        dy = ((yy - cy + R // 2) % R - R // 2) / ry
        stones |= dx * dx + dy * dy < 1
    v -= ndimage.gaussian_filter(stones.astype(float), 0.8 * K, mode="wrap") * 0.10 * (~stones)
    img = ramp("dirt", v)
    pv = 0.55 + (g.random((R, R)) - 0.5) * 0.3 + bevel(stones, 1.2 * K) * 0.35
    img[stones] = ramp("pebble", pv)[stones]                         # small grey pebbles
    return img


# ─────────────────────────────── logs, the stone family, ground, glass, leaves ───────────────────────────────
def voronoi(g, n):
    """Tileable Voronoi: distance to the nearest and second-nearest site, and the nearest site's id."""
    from scipy.spatial import cKDTree
    pts = g.random((n, 2)) * R
    offs = np.array([(dx, dy) for dx in (-R, 0, R) for dy in (-R, 0, R)], dtype=float)
    allp = (pts[None, :, :] + offs[:, None, :]).reshape(-1, 2)
    ids = np.tile(np.arange(n), 9)
    yy, xx = np.mgrid[0:R, 0:R]
    q = np.stack([xx.ravel() + 0.5, yy.ravel() + 0.5], axis=1)
    d, i = cKDTree(allp).query(q, k=2)
    return d[:, 0].reshape(R, R), d[:, 1].reshape(R, R), ids[i[:, 0]].reshape(R, R)


def bump_light(h, strength):
    """Light a height field from the top-left: brighter where it rises toward the light."""
    gy, gx = np.gradient(h)
    return -(gx * 0.7 + gy * 0.7) * strength


def log_side(seed, bark, birch=False):
    g = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:R, 0:R]
    if birch:
        v = 0.66 + noise(g, 10, aniso=(3, 1)) * 0.08 + (g.random((R, R)) - 0.5) * 0.07
        img = ramp(bark, v)
        dark = hx("#2f2b27")
        for _ in range(int(14 * K * K) + 6):                         # horizontal lenticels
            x, y = g.integers(0, R), g.integers(0, R)
            ln = int(g.integers(2, 7) * K) + 1
            for i in range(ln):
                img[y % R, (x + i) % R] = dark * g.uniform(0.9, 1.2)
                if g.random() < 0.3:
                    img[(y + 1) % R, (x + i) % R] = dark * 1.3
        for _ in range(3):                                           # big dark patches
            cx, cy = g.integers(0, R), g.integers(0, R)
            rx, ry = g.uniform(2.5, 5) * K, g.uniform(1.2, 2.2) * K
            dx = ((xx - cx + R // 2) % R - R // 2) / rx
            dy = ((yy - cy + R // 2) % R - R // 2) / ry
            m = dx * dx + dy * dy < 1 + noise(g, 10) * 0.4
            img[m] = dark * 1.15 + (g.random((int(m.sum()), 1)) - 0.5) * 20
        return img
    # vertical bark plates: columns of varying width, split by dark fissures that wander a little
    v = np.zeros((R, R))
    x = 0.0
    cols = []
    while x < R:
        w = g.uniform(6.0, 11.0) * K                                  # 3-5 px plates at 32
        cols.append((x, w)); x += w
    wander = noise(g, 4, aniso=(1, 6)) * 1.2 * K
    xs = (xx + wander) % R
    plate = np.zeros((R, R))
    fiss = np.zeros((R, R), bool)
    for (x0, w) in cols:
        inside = (xs >= x0) & (xs < x0 + w)
        u = (xs - x0) / w                                            # 0..1 across the plate
        plate[inside] = (np.clip(np.sin(u * np.pi), 0, 1) ** 0.6)[inside]   # rounded plate
        fiss |= inside & (u < 0.12)
    breaks = noise(g, 12, aniso=(1, 3)) > 0.55                       # plates break horizontally now and then
    v = 0.34 + plate * 0.34 + noise(g, 24, aniso=(1, 5)) * 0.08 + (g.random((R, R)) - 0.5) * 0.06
    v += bump_light(ndimage.gaussian_filter(plate, 0.6, mode="wrap"), 1.2 * K)
    v[fiss] = 0.10 + (g.random(int(fiss.sum())) - 0.5) * 0.08
    v[breaks & ~fiss] -= 0.12
    return ramp(bark, v)

def log_top(seed, wood, bark):
    g = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:R, 0:R].astype(float) + 0.5
    c = R / 2 + g.uniform(-0.8, 0.8) * K
    r = np.sqrt((xx - c) ** 2 + (yy - c) ** 2) + noise(g, 4) * 0.9 * K
    spacing = 7.0 * K                                                # a ring every ~3.5 px at 32
    ring = (r % spacing) / spacing
    late = np.clip(1 - np.abs(ring - 0.82) / 0.2, 0, 1)              # a dark late-wood band per ring
    v = 0.68 - late * 0.32 + noise(g, 14) * 0.04 - (r / R) * 0.08
    v[r < 1.3 * K] = 0.25                                            # pith
    ang = np.arctan2(yy - c, xx - c)
    for _ in range(2):                                               # radial drying cracks
        a = g.uniform(-np.pi, np.pi)
        crack = (np.abs(((ang - a + np.pi) % (2 * np.pi)) - np.pi) < 0.05) & (r > R * 0.15) & (r < R * 0.43)
        v[crack] = 0.18
    img = ramp(wood, v)
    edge = np.minimum.reduce([xx, yy, R - xx, R - yy])
    rim = edge < 2.0 * K
    img[rim] = ramp(bark, 0.40 + noise(g, 12)[rim] * 0.25)
    groups = rim.astype(int)
    cam = (edge >= 2.0 * K) & (edge < 2.8 * K)
    img[cam] = img[cam] * 0.8
    return img, groups

def stone(seed=21):
    g = np.random.default_rng(seed)
    m = fbm(g, 4, 5) * 0.5 + 0.5
    v = 0.54 + (m - 0.5) * 0.7 + (g.random((R, R)) - 0.5) * 0.12
    patches = noise(g, 7) > 0.35                                     # darker patches, like vanilla stone
    v[patches] -= 0.10
    specks = (noise(g, 40) > 0.5) & (g.random((R, R)) > 0.4)
    v[specks] -= 0.14
    light = (noise(g, 30) > 0.62)
    v[light] += 0.08
    return ramp("stone", v)

def smooth_stone(seed=22):
    g = np.random.default_rng(seed)
    v = 0.6 + noise(g, 6) * 0.05 + (g.random((R, R)) - 0.5) * 0.05
    img = ramp("smooth", v)
    b = max(1, int(round(K)))
    img[:b, :] *= 0.78; img[-b:, :] *= 0.78; img[:, :b] *= 0.78; img[:, -b:] *= 0.78
    return img


def cobblestone(seed=23):
    g = np.random.default_rng(seed)
    f1, f2, cell = voronoi(g, int(40 * K * K) + 4)
    edge = f2 - f1
    gap = edge < 2.2 * K
    tone = g.normal(0, 0.10, cell.max() + 1)[cell]
    radius = 9.0 * K
    dome = np.clip(1 - f1 / radius, 0, 1)                            # each stone a soft dome
    shade = bump_light(ndimage.gaussian_filter(dome, 1.0, mode="wrap"), 3.0 * K)
    v = 0.48 + tone + dome * 0.12 + shade + (fbm(g, 10, 3) * 0.08) + (g.random((R, R)) - 0.5) * 0.08
    v -= np.clip(1 - edge / (4.5 * K), 0, 1) * 0.14                  # darker toward the joints
    v[gap] = 0.10 + (g.random(int(gap.sum())) - 0.5) * 0.06
    return ramp("stone", v)

def bricks(seed=24):
    g = np.random.default_rng(seed)
    rows, rh = 4, R // 4
    mw = max(1, int(round(1.5 * K)))
    joint = np.zeros((R, R), bool)
    for r in range(rows):
        y0 = r * rh
        joint[y0:y0 + mw, :] = True
        off = 0 if r % 2 == 0 else R // 4
        for x in range(off, R + off, R // 2):
            joint[y0:y0 + rh, x % R:x % R + mw] = True
    brick = ~joint
    lab, n = ndimage.label(brick)
    v = 0.52 + fbm(g, 6, 4) * 0.18 + (g.random((R, R)) - 0.5) * 0.12
    for k in range(1, n + 1):
        v[lab == k] += g.normal(0, 0.07)
    v += bevel(brick, 1.6 * K) * 0.2
    img = ramp("brick", v)
    mv = 0.5 + (g.random((R, R)) - 0.5) * 0.35
    img[joint] = ramp("brick_mortar", mv)[joint]
    return img, joint.astype(int)


def sand(seed=25):
    g = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:R, 0:R]
    ripple = np.sin((yy + noise(g, 3) * 3 * K) * np.pi / (4 * K)) * 0.03
    v = 0.56 + noise(g, 10) * 0.08 + ripple + (g.random((R, R)) - 0.5) * 0.24
    grains = g.random((R, R))
    v[grains < 0.06] -= 0.18                                         # darker grains
    v[grains > 0.96] += 0.16                                         # bright grains
    return ramp("sand", v)

def gravel(seed=26):
    g = np.random.default_rng(seed)
    f1, f2, cell = voronoi(g, int(200 * K * K) + 10)
    edge = f2 - f1
    tone = g.normal(0, 0.15, cell.max() + 1)[cell]
    dome = np.clip(1 - f1 / (5.5 * K), 0, 1)
    v = 0.50 + tone + dome * 0.14 + bump_light(ndimage.gaussian_filter(dome, 0.7, mode="wrap"), 2.0 * K)
    v += (g.random((R, R)) - 0.5) * 0.06
    v[edge < 1.8 * K] -= 0.28
    return ramp("gravel", v)

def glass(seed=27):
    img = np.zeros((R, R, 4))
    b = max(2, int(round(1.5 * K)))
    frame = np.zeros((R, R), bool)
    frame[:b, :] = frame[-b:, :] = frame[:, :b] = frame[:, -b:] = True
    img[frame] = [214, 233, 238, 255]
    img[:1, :, :3] = [236, 246, 248]; img[:, :1, :3] = [236, 246, 248]            # lit outer edge
    img[-1:, :, :3] = [170, 196, 204]; img[:, -1:, :3] = [170, 196, 204]          # shaded outer edge
    yy, xx = np.mgrid[0:R, 0:R]
    for (x0, y0, ln, al) in ((0.18, 0.12, 5, 170), (0.12, 0.26, 3, 140), (0.74, 0.70, 4, 120)):   # short glints, like vanilla
        for t in range(int(ln * K * 2)):
            x, y = int(x0 * R) + t, int(y0 * R) + t
            if 0 < x < R - 1 and 0 < y < R - 1:
                img[y, x] = [246, 251, 252, al]
    return img

def oak_leaves(seed=28):
    """Grey, like vanilla (the game tints it by biome), with see-through gaps."""
    g = np.random.default_rng(seed)
    v = np.full((R, R), 0.30) + noise(g, 6) * 0.05
    alpha = np.zeros((R, R))
    yy, xx = np.mgrid[0:R, 0:R]
    for _ in range(int(60 * K * K) + 12):                           # leaves: lit ellipses, darker underneath
        cx, cy = g.uniform(0, R), g.uniform(0, R)
        a = g.uniform(0, np.pi)
        rl, rw = g.uniform(4.5, 7.0) * K, g.uniform(2.4, 3.6) * K
        dx = ((xx - cx + R / 2) % R - R / 2)
        dy = ((yy - cy + R / 2) % R - R / 2)
        u = (dx * np.cos(a) + dy * np.sin(a)) / rl
        w = (-dx * np.sin(a) + dy * np.cos(a)) / rw
        m = u * u + w * w < 1
        v[m] = g.uniform(0.55, 0.85) - (dy[m] / (rl + 1e-9)) * 0.15
        v[m & (np.abs(w) < 0.18)] -= 0.08                           # the midrib
        alpha[m] = 255
    alpha[(alpha == 0) & (noise(g, 10) > -0.25)] = 255               # dark foliage behind fills most gaps
    return np.dstack([ramp("leaf", v), alpha])

def grass_top_grey(seed=13):
    """The same blades as grass_top, in grey: the game multiplies it by the biome's grass colour."""
    global RAMP
    keep = RAMP["grass"]
    RAMP = dict(RAMP); RAMP["grass"] = RAMP["grey"]
    img = grass_top(seed)
    RAMP["grass"] = keep
    return img


def grass_side_parts(seed=15):
    """Side = dirt with a green fringe (fast graphics); overlay = the fringe in grey + alpha (tinted by biome)."""
    g = np.random.default_rng(seed)
    side = dirt(seed + 1)
    top = grass_top_grey(seed + 2)
    over = np.zeros((R, R, 4))
    fringe = np.zeros((R, R), int)
    depth = (6 + noise(g, 6)[0] * 3) * K
    for x in range(R):
        d = int(max(3 * K, depth[x]))
        ext = d + (int(g.integers(1, 4) * K) if g.random() < 0.6 else 0)
        over[:ext, x, :3] = top[:ext, x]
        over[d:ext, x, :3] = ramp("grey", np.array([0.3]))[0]
        over[:ext, x, 3] = 255
        side[:ext, x] = ramp("grass", np.array([0.55]))[0] * (top[:ext, x] / 170.0)
        fringe[:ext, x] = 1
        if ext < R:
            side[ext, x] *= 0.82
    return (side, fringe), over


def save_rgba(rgba, name):
    p = os.path.join(OUT, "assets/minecraft/textures/block", name + ".png")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    if PIXEL:
        rgba = rgba.astype(float).copy()
        solid = rgba[..., 3] > 0
        if solid.sum() > PIXEL:
            rgba[..., :3] = pixelate(np.clip(rgba[..., :3], 0, 255), solid)
    Image.fromarray(np.clip(rgba, 0, 255).astype(np.uint8), "RGBA").save(p)
    return p


def build():
    out = []
    for i, (sp, wood, bark) in enumerate((("oak", "wood", "oak_bark"), ("spruce", "spruce", "spruce_bark"),
                                          ("birch", "birch", "birch_bark"), ("dark_oak", "dark_oak", "dark_oak_bark"))):
        out.append(save(oak_planks(11 + i * 10, wood), f"{sp}_planks"))
        out.append(save(log_side(12 + i * 10, bark, birch=(sp == "birch")), f"{sp}_log"))
        out.append(save(log_top(13 + i * 10, wood, bark), f"{sp}_log_top"))
    for name, fn in (("stone", stone), ("smooth_stone", smooth_stone), ("cobblestone", cobblestone), ("stone_bricks", stone_bricks),
                     ("bricks", bricks), ("dirt", dirt), ("sand", sand), ("gravel", gravel)):
        out.append(save(fn(), name))
    out.append(save(grass_top_grey(), "grass_block_top"))
    side, over = grass_side_parts()
    out.append(save(side, "grass_block_side"))
    out.append(save_rgba(over, "grass_block_side_overlay"))
    out.append(save_rgba(glass(), "glass"))
    out.append(save_rgba(oak_leaves(), "oak_leaves"))
    desc = f"Natural blocks {R}x" + (f", {PIXEL} tones" if PIXEL else "")
    json.dump({"pack": {"description": desc, "min_format": PACK_FORMAT, "max_format": PACK_FORMAT}},
              open(os.path.join(OUT, "pack.mcmeta"), "w"))
    z = OUT.rstrip("/") + ".zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(OUT):
            for f in sorted(files):
                p = os.path.join(root, f)
                zf.write(p, os.path.relpath(p, OUT))
    return out, z


if __name__ == "__main__":
    files, z = build()
    print(f"{len(files)} textures → {OUT}\n{z}")
