"""pack.py — the coaster train as item models in a resource pack (Minecraft 26.2, pack format 88). No dependencies.

Two models: coaster:front (the lead car: a long flame-painted hood, a flame crest, headlights) and coaster:car (the
others: a cowl, twin flame fins). Textures are drawn here: glossy red paint, flame decals that start at the nose and
lick backwards (dark outline → orange → yellow core), black bucket seats with orange stitching, brushed steel lap bars,
charcoal bogies with glowing hubs.

Model space (the app shows the models at scale 2): 16 units = 2 blocks, so 1 unit = 1/8 block. The track point (rail
top, centre) is (8, 8, 8) — the item renderer puts the model's (8, 8, 8) on the entity. The nose points to -z because
item_display turns item models 180° (the app maps display +z → forward). Seat (one per car): (8, 12.5, 9.5), which is
the app's seat offset up 0.5625, forward -0.19 (coaster.sc global_SEAT). Car length ≈ 2.45 blocks (track.py CAR_GAP).

    python3 skill/pinkgolem/blueprints/coaster/pack.py [--out DIR] [--preview PNG]
      → DIR/build/ + DIR/coaster.zip (sha1 printed). Default DIR = resourcepacks/coaster, where minecraft_pack finds it
        (every resourcepacks/<name>/<name>.zip is merged into the server pack). --preview renders both cars with
        resourcepacks/tools/model_preview.py, no game client needed.
"""
import argparse
import hashlib
import json
import math
import os
import shutil
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, HERE)
from canvas import Canvas   # noqa: E402

NS = "coaster"
T = f"{NS}:item/"

RED = (196, 20, 26)
RED_HI = (236, 58, 44)
RED_LO = (120, 8, 14)
ORANGE = (255, 122, 0)
YELLOW = (255, 214, 64)
OUTLINE = (70, 6, 6)


# ─────────────────────────────── textures ───────────────────────────────
def paint_base(w, h):
    im = Canvas(w, h)
    for y in range(h):
        k = y / max(1, h - 1)
        c = tuple(int(RED_HI[i] * (1 - k) * 0.55 + RED[i] * 0.45 + RED_LO[i] * k * 0.55) for i in range(3))
        for x in range(w):
            im.put(x, y, c + (255,))
    return im


def flame_side(w=64, h=16):
    """Front at u = 0. Five tongues licking backwards with a wavy centre line."""
    im = paint_base(w, h)
    tongues = [(0.86, 0.50, 0.17, 0.0), (0.66, 0.28, 0.12, 1.7), (0.60, 0.72, 0.12, 3.1), (0.44, 0.40, 0.08, 4.4), (0.38, 0.62, 0.08, 5.9)]
    for x in range(w):
        u = (x + 0.5) / w
        for y in range(h):
            v = (y + 0.5) / h
            best = 9.0
            for (Lk, ck, wk, ph) in tongues:
                if u > Lk:
                    continue
                c = ck + 0.10 * math.sin(u * math.pi * 2.2 + ph) * (u / Lk)
                t = wk * (1 - u / Lk) ** 0.7
                if t <= 0:
                    continue
                best = min(best, abs(v - c) / t)
            if best < 0.45:
                col = YELLOW
            elif best < 0.85:
                col = ORANGE
            elif best < 1.05:
                col = OUTLINE
            else:
                continue
            im.put(x, y, col + (255,))
    im.line(0, 0, w, 0, (220, 220, 225, 255))                # chrome strip on top
    im.line(0, h - 1, w, h - 1, (40, 4, 6, 255))
    return im


def plain(col, w=16, h=16, noise=6, grad=0.25):
    im = Canvas(w, h)
    for y in range(h):
        for x in range(w):
            k = 1 + grad * (0.5 - y / h)
            n = ((x * 7 + y * 13) % 5 - 2) * noise / 4
            im.put(x, y, tuple(max(0, min(255, int(c * k + n))) for c in col) + (255,))
    return im


def seat():
    im = plain((26, 22, 24), noise=4, grad=0.3)
    for x in (3, 8, 12):
        im.line(x, 1, x, 14, (235, 110, 20, 255))
    im.rect(0, 0, 15, 15, outline=(10, 8, 8, 255))
    return im


def metal():
    im = Canvas(16, 16)
    for y in range(16):
        for x in range(16):
            v = 170 + int(30 * math.sin(x * 0.9 + y * 0.2)) + (y % 3) * 4
            im.put(x, y, (v, v, v + 8, 255))
    return im


def dark():
    im = plain((38, 34, 36), noise=5, grad=0.2)
    for (x, y) in ((2, 2), (13, 2), (2, 13), (13, 13)):
        im.put(x, y, (120, 120, 125, 255))
    return im


def nose():
    """The hood seen from the front: red with a big flame emblem."""
    im = paint_base(16, 16)
    for y in range(16):
        for x in range(16):
            u, v = (x + 0.5) / 16 - 0.5, (y + 0.5) / 16
            r = abs(u) / max(0.05, 0.42 * (v ** 0.8))
            if v > 0.12 and r < 1.0:
                col = YELLOW if r < 0.45 and v > 0.45 else ORANGE if r < 0.85 else OUTLINE
                im.put(x, y, col + (255,))
    return im


def lamp(col):
    im = plain(col, noise=3, grad=0.4)
    im.rect(0, 0, 15, 15, outline=(60, 60, 60, 255))
    return im


def flame_up():
    """A flame tongue standing up: red at the root, orange, a yellow tip (v = 0 is the top)."""
    im = Canvas(16, 16)
    for y in range(16):
        for x in range(16):
            v = y / 15
            c = YELLOW if v < 0.18 else ORANGE if v < 0.62 else RED_HI
            im.put(x, y, c + (255,))
    return im


def hood():
    """Top of the hood / cowl: red paint with a flame stripe running down the middle."""
    im = paint_base(16, 16)
    for y in range(16):
        for x in range(16):
            u = abs((x + 0.5) / 16 - 0.5)
            w = 0.04 + 0.08 * (1 - y / 16)
            if u < w:
                im.put(x, y, (YELLOW if u < w * 0.45 else ORANGE) + (255,))
            elif u < w + 0.05:
                im.put(x, y, OUTLINE + (255,))
    return im


TEXTURES = {"flame": flame_up, "hood": hood, "side": flame_side, "red": lambda: plain(RED, grad=0.35), "seat": seat, "metal": metal, "dark": dark,
            "nose": nose, "light": lambda: lamp((255, 236, 150)), "tail": lambda: lamp((255, 90, 20))}


# ─────────────────────────────── models ───────────────────────────────
def box(x1, y1, z1, x2, y2, z2, tex, faces=None, uv=None, rot=None):
    fs = {}
    for f in ("north", "south", "east", "west", "up", "down"):
        t = (faces or {}).get(f, tex)
        if t is None:
            continue
        d = {"texture": "#" + t}
        if uv and f in uv:
            d["uv"] = uv[f]
        fs[f] = d
    e = {"from": [x1, y1, z1], "to": [x2, y2, z2], "faces": fs}
    if rot:
        e["rotation"] = rot
    return e


def body(z1, z2, front=False):
    """The common tub (one rider per car): bogies with glowing hubs on the rails, flame-painted sides with side skirts
    and chrome rims, one bucket seat with bolsters and a head rest, an over-the-lap bar."""
    e = []
    for zc in (z1 + 2.5, z2 - 2.5):                                             # bogies on the rails (x 3.2 / 12.8)
        for (xa, xb) in ((1.9, 4.5), (11.5, 14.1)):
            e.append(box(xa, 8.0, zc - 1.6, xb, 10.0, zc + 1.6, "dark"))
        e.append(box(1.5, 8.5, zc - 0.7, 1.9, 9.5, zc + 0.7, "tail"))          # glowing hubs
        e.append(box(14.1, 8.5, zc - 0.7, 14.5, 9.5, zc + 0.7, "tail"))
    e.append(box(2.5, 9.6, z1 + 0.5, 13.5, 10.6, z2 - 0.5, "dark"))            # chassis
    e.append(box(2.0, 10.4, z1, 3.0, 16.2, z2, "red", faces={"west": "side", "east": "red"}, uv={"west": [0, 0, 16, 16]}))
    e.append(box(13.0, 10.4, z1, 14.0, 16.2, z2, "red", faces={"east": "side", "west": "red"}, uv={"east": [16, 0, 0, 16]}))
    e.append(box(1.6, 10.0, z1 + 1.0, 2.0, 11.4, z2 - 1.0, "dark"))            # side skirts
    e.append(box(14.0, 10.0, z1 + 1.0, 14.4, 11.4, z2 - 1.0, "dark"))
    e.append(box(1.8, 16.2, z1, 3.1, 16.7, z2, "metal"))                       # chrome rims
    e.append(box(12.9, 16.2, z1, 14.2, 16.7, z2, "metal"))
    e.append(box(3.0, 10.4, z1, 13.0, 11.0, z2, "dark"))                       # floor
    e.append(box(3.0, 10.4, z2 - 1.0, 13.0, 15.0, z2, "red"))                  # rear wall
    e.append(box(3.5, 14.2, z2 - 0.1, 12.5, 15.0, z2 + 0.15, "tail"))          # tail light strip
    for x in (4.0, 11.0):                                                      # twin exhausts with a hot tip
        e.append(box(x, 10.8, z2 - 0.2, x + 1.0, 11.8, z2 + 0.9, "metal"))
        e.append(box(x + 0.15, 10.95, z2 + 0.9, x + 0.85, 11.65, z2 + 1.1, "tail"))
    # one bucket seat in the middle
    e.append(box(5.0, 11.0, 6.5, 11.0, 12.5, 12.2, "seat"))                    # cushion
    e.append(box(5.0, 11.0, 12.2, 11.0, 18.0, 13.8, "seat"))                   # back
    e.append(box(6.0, 18.0, 12.4, 10.0, 20.0, 13.6, "seat"))                   # head rest
    e.append(box(4.4, 11.5, 7.0, 5.0, 15.5, 13.8, "seat"))                     # bolsters
    e.append(box(11.0, 11.5, 7.0, 11.6, 15.5, 13.8, "seat"))
    e.append(box(5.4, 15.2, 6.8, 10.6, 16.1, 8.0, "metal"))                    # lap bar
    e.append(box(5.2, 12.5, 7.1, 5.9, 15.2, 7.8, "metal"))
    e.append(box(10.1, 12.5, 7.1, 10.8, 15.2, 7.8, "metal"))
    return e


def fins(z2):
    out = []
    for x in (2.2, 12.8):                                                      # flame fins sweeping back
        out.append(box(x, 16.2, z2 - 3.6, x + 1.0, 19.6, z2 - 0.2, "red", faces={"west": "side", "east": "side", "north": "red", "south": "red", "up": "tail", "down": "red"},
                       uv={"west": [10, 0, 16, 16], "east": [16, 0, 10, 16]},
                       rot={"origin": [x + 0.5, 16.2, z2 - 0.2], "axis": "x", "angle": -22.5}))
    return out


def front_car():
    z1, z2 = -1.0, 17.5
    e = body(z1, z2, front=True)
    # the hood: long, low and pointed, flames down both flanks, a flame emblem on the nose
    e.append(box(2.0, 10.4, -6.0, 14.0, 14.4, z1 + 0.5, "red", faces={"north": "nose", "west": "side", "east": "side"},
                 uv={"west": [0, 0, 6, 16], "east": [6, 0, 0, 16]}))
    e.append(box(2.4, 13.6, -5.8, 13.6, 15.6, 2.2, "red", faces={"north": "nose", "up": "hood"},
                 rot={"origin": [8, 13.6, -5.8], "axis": "x", "angle": 22.5}))
    e.append(box(3.0, 10.2, -6.8, 13.0, 12.0, -5.8, "red", faces={"north": "nose"}))   # the snout
    e.append(box(1.6, 9.6, -7.2, 14.4, 10.4, -5.4, "dark"))                    # splitter
    e.append(box(2.6, 11.4, -6.25, 4.8, 12.8, -5.95, "light"))                 # headlights
    e.append(box(11.2, 11.4, -6.25, 13.4, 12.8, -5.95, "light"))
    e.append(box(5.2, 10.6, -6.9, 10.8, 11.3, -6.7, "metal"))                  # chrome bumper strip
    for (x, h, z) in ((7.3, 4.6, -3.2), (5.4, 3.0, -2.2), (9.4, 3.2, -2.4)):   # flame crest on the hood
        e.append(box(x, 14.6, z, x + 1.4, 14.6 + h, z + 1.0, "flame",
                     rot={"origin": [x + 0.7, 14.6, z + 0.5], "axis": "x", "angle": -22.5}))
    # no windscreen: with one (a translucent "glass" texture, the 11th texture of this model) players saw the
    # missing-model cube instead of the front car — look at every model change in game
    e.append(box(3.0, 10.4, z1, 13.0, 15.2, z1 + 1.0, "red"))                 # dash
    return e


def car():
    z1, z2 = -1.0, 17.5
    e = body(z1, z2)
    e.append(box(3.0, 10.4, z1, 13.0, 14.6, z1 + 1.2, "red", faces={"north": "red", "up": "hood"}))   # front cowl
    e.append(box(3.4, 14.0, z1 + 0.2, 12.6, 15.4, z1 + 3.2, "red", faces={"up": "hood"},
                 rot={"origin": [8, 14.0, z1 + 0.2], "axis": "x", "angle": 22.5}))
    e += fins(z2)
    return e


MODELS = {"front": front_car(), "car": car()}


def build(out_dir):
    # every coordinate inside the item-model limits (-16..32), every rotation a legal step
    for mid, els in MODELS.items():
        for e in els:
            for v in e["from"] + e["to"]:
                assert -16 <= v <= 32, (mid, e)
            if "rotation" in e:
                assert e["rotation"]["angle"] in (-45, -22.5, 0, 22.5, 45), (mid, e)
    tmp = os.path.join(out_dir, "build")
    if os.path.exists(tmp):
        shutil.rmtree(tmp)
    tdir = os.path.join(tmp, f"assets/{NS}/textures/item")
    mdir = os.path.join(tmp, f"assets/{NS}/models/item")
    idir = os.path.join(tmp, f"assets/{NS}/items")
    for d in (tdir, mdir, idir):
        os.makedirs(d, exist_ok=True)
    for k, fn in TEXTURES.items():
        fn().save(os.path.join(tdir, f"{k}.png"))
    tex = {k: T + k for k in TEXTURES}
    tex["particle"] = T + "red"
    for mid, els in MODELS.items():
        with open(os.path.join(mdir, f"{mid}.json"), "w") as f:
            json.dump({"textures": tex, "elements": els}, f)
        with open(os.path.join(idir, f"{mid}.json"), "w") as f:
            json.dump({"model": {"type": "minecraft:model", "model": f"{NS}:item/{mid}"}}, f)
    with open(os.path.join(tmp, "pack.mcmeta"), "w") as f:
        json.dump({"pack": {"description": "Pink Golem coaster train", "min_format": 88, "max_format": 88}}, f)
    z = os.path.join(out_dir, "coaster.zip")
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in sorted(os.walk(tmp)):
            for f in sorted(files):
                p = os.path.join(root, f)
                zf.write(p, os.path.relpath(p, tmp).replace(os.sep, "/"))
    return z, tmp


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Build the coaster train resource pack.")
    ap.add_argument("--out", default=os.path.join(ROOT, "resourcepacks", "coaster"), help="output folder (default resourcepacks/coaster)")
    ap.add_argument("--preview", help="also render both cars to this PNG (uses resourcepacks/tools/model_preview.py)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    zpath, built = build(a.out)
    print(zpath, hashlib.sha1(open(zpath, "rb").read()).hexdigest(), {k: len(v) for k, v in MODELS.items()}, os.path.getsize(zpath), "bytes")
    if a.preview:
        sys.path.insert(0, os.path.join(ROOT, "resourcepacks", "tools"))
        import model_preview
        print(model_preview.render(built, [f"{NS}:item/front", f"{NS}:item/car", f"{NS}:item/car"], a.preview, gap=2.45 * 8))
