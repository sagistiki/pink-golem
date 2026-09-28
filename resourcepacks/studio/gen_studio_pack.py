"""gen_studio_pack.py -- character studio: SEVEN original 64x64 player skins (pink + queer vibe, fashionable,
each a distinct character) as mannequin textures assets/studio/textures/entity/skin/<id>.png
(profile:{model:"wide",texture:"studio:entity/skin/<id>"} on a mannequin -- "wide" = classic 4px arms), also
copied plain to studio_skins/<id>.png for players to wear later; a resident_card item (flat square quad, like
the lobby map's quad model) + a bigger card_display wall quad (also like gen_lobby_map.py); pack.mcmeta format 88.

Skin UV layout used here (64x64, classic/"wide" 4px-arm, base + overlay/second layer) -- see minecraft.wiki "Skin":
  HEAD  (0,0,8,8,8)   HAT/hair-overlay (32,0,8,8,8)
  BODY  (16,16,8,12,4) JACKET overlay (16,32,8,12,4)
  R-ARM (40,16,4,12,4) R-SLEEVE overlay (40,32,4,12,4)
  L-ARM (32,48,4,12,4) L-SLEEVE overlay (48,48,4,12,4)
  R-LEG (0,16,4,12,4)  R-PANTS overlay (0,32,4,12,4)
  L-LEG (16,48,4,12,4) L-PANTS overlay (0,48,4,12,4)

Run: python3 gen_studio_pack.py
  -> studio_pack/ + studio_pack.zip (namespace "studio")
  -> studio_skins/<id>.png (raw, plain files for later upload)
  -> studio_skins.json (list for the pack builder / registration flow)
  -> previews/studio_skins_sheet.png (front+back assembled x8 + raw atlas, labelled)
  -> previews/resident_card_preview.png, previews/card_display_preview.png (model_preview.py renders)
"""
import json
import os
import random
import subprocess
import sys
import zipfile

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
NS = "studio"
OUT = os.path.join(HERE, "build")
SKIN_DIR = os.path.join(OUT, "assets", NS, "textures", "entity", "skin")
ITEM_TEX_DIR = os.path.join(OUT, "assets", NS, "textures", "item")
ITEM_MODEL_DIR = os.path.join(OUT, "assets", NS, "models", "item")
ITEM_DIR = os.path.join(OUT, "assets", NS, "items")
RAW_DIR = os.path.join(HERE, "skins")
PREV_DIR = os.path.join(HERE, "previews")
for d in (SKIN_DIR, ITEM_TEX_DIR, ITEM_MODEL_DIR, ITEM_DIR, RAW_DIR, PREV_DIR):
    os.makedirs(d, exist_ok=True)


# ---------------------------------------------------------------- colour helpers
def hexc(c):
    if isinstance(c, tuple):
        return c if len(c) == 4 else c + (255,)
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4)) + (255,)


def shade(c, f):
    r, g, b, a = hexc(c)
    return (max(0, min(255, int(r * f))), max(0, min(255, int(g * f))), max(0, min(255, int(b * f))), a)


def mix(c1, c2, t):
    c1, c2 = hexc(c1), hexc(c2)
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(4))


# ---------------------------------------------------------------- skin canvas
class Skin:
    def __init__(self):
        self.im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        self.px = self.im.load()

    def r(self, x, y, w, h, c):
        c = hexc(c)
        for i in range(x, x + w):
            for j in range(y, y + h):
                if 0 <= i < 64 and 0 <= j < 64:
                    self.px[i, j] = c

    def p(self, x, y, c):
        if 0 <= x < 64 and 0 <= y < 64:
            self.px[x, y] = hexc(c)


def part(s, ox, oy, w, h, d, col):
    """Paint (if col is not None) and always return the six UV face rects for a box whose UV origin is (ox,oy)."""
    faces = {
        "top": (ox + d, oy, w, d), "bottom": (ox + d + w, oy, w, d),
        "right": (ox, oy + d, d, h), "front": (ox + d, oy + d, w, h),
        "left": (ox + d + w, oy + d, d, h), "back": (ox + 2 * d + w, oy + d, w, h),
    }
    if col is not None:
        for (x, y, ww, hh) in faces.values():
            s.r(x, y, ww, hh, col)
    return faces


HEAD, HAT = (0, 0, 8, 8, 8), (32, 0, 8, 8, 8)
BODY, JKT = (16, 16, 8, 12, 4), (16, 32, 8, 12, 4)
RARM, RSLV = (40, 16, 4, 12, 4), (40, 32, 4, 12, 4)
LARM, LSLV = (32, 48, 4, 12, 4), (48, 48, 4, 12, 4)
RLEG, RPANT = (0, 16, 4, 12, 4), (0, 32, 4, 12, 4)
LLEG, LPANT = (16, 48, 4, 12, 4), (0, 48, 4, 12, 4)


# ---------------------------------------------------------------- pattern helpers (operate inside a rect)
def hstripes(s, x, y, w, h, colors):
    n = len(colors)
    for j in range(h):
        s.r(x, y + j, w, 1, colors[min(n - 1, (j * n) // h)])


def sparkle(s, x, y, w, h, base, spark, density=0.30, seed=0):
    s.r(x, y, w, h, base)
    rnd = random.Random(seed)
    for i in range(w):
        for j in range(h):
            if rnd.random() < density:
                s.p(x + i, y + j, spark if rnd.random() < 0.55 else shade(spark, 1.25))


def ribbing(s, x, y, w, h, base, dark, period=2):
    s.r(x, y, w, h, base)
    for j in range(0, h, period):
        s.r(x, y + j, w, 1, dark)


def dots(s, x, y, positions, col):
    for (i, j) in positions:
        s.p(x + i, y + j, col)


# ---------------------------------------------------------------- shared body builders
def face(s, eye, brow, lip, blush=None, lash=False, freckle=False, glasses=None, eyeshadow=None):
    fx, fy = 8, 8
    if eyeshadow:
        s.r(fx + 1, fy + 3, 2, 1, eyeshadow); s.r(fx + 5, fy + 3, 2, 1, eyeshadow)
    s.r(fx + 1, fy + 4, 2, 2, "#FFFFFF"); s.r(fx + 5, fy + 4, 2, 2, "#FFFFFF")
    s.p(fx + 2, fy + 4, eye); s.p(fx + 2, fy + 5, eye); s.p(fx + 5, fy + 4, eye); s.p(fx + 5, fy + 5, eye)
    s.r(fx + 1, fy + 3, 2, 1, brow); s.r(fx + 5, fy + 3, 2, 1, brow)
    if lash:
        s.p(fx, fy + 3, "#2A2029"); s.p(fx + 7, fy + 3, "#2A2029")
    if blush:
        s.p(fx + 1, fy + 6, blush); s.p(fx + 6, fy + 6, blush)
    if freckle:
        for (i, j) in [(1, 5), (2, 6), (6, 5), (5, 6)]:
            s.p(fx + i, fy + j, shade(blush or "#D89A86", 0.85))
    s.r(fx + 3, fy + 7, 2, 1, lip)
    if glasses:
        g = glasses
        for x0 in (fx, fx + 4):
            s.r(x0, fy + 3, 4, 1, g); s.r(x0, fy + 6, 4, 1, g)
            s.p(x0, fy + 4, g); s.p(x0, fy + 5, g); s.p(x0 + 3, fy + 4, g); s.p(x0 + 3, fy + 5, g)
        s.r(fx + 3, fy + 4, 2, 1, g)


def hair_base(s, hair, top=True, sides="both", back=True, fringe_rows=2):
    if top:
        s.r(8, 0, 8, 8, hair)
    if sides in ("both", "right"):
        s.r(0, 8, 8, 8, hair)
    if sides in ("both", "left"):
        s.r(16, 8, 8, 8, hair)
    if back:
        s.r(24, 8, 8, 8, hair)
    if fringe_rows:
        s.r(8, 8, 8, fringe_rows, hair)


def legs(s, bottom, shoes, skin, skirt_hem=None, holes=None, sock=None, pattern=None):
    for (lx, ly) in ((0, 16), (16, 48)):
        part(s, lx, ly, 4, 12, 4, bottom)
        for (x, y) in ((lx + 4, ly + 4), (lx, ly + 4), (lx + 8, ly + 4), (lx + 12, ly + 4)):
            if skirt_hem is not None:
                s.r(x, y + skirt_hem, 4, 9 - skirt_hem, skin)
                s.r(x, y + skirt_hem - 1, 4, 1, mix(bottom, "#B5476B", 0.55))
            if sock:
                s.r(x, y + 9, 4, 2, sock); s.r(x, y + 11, 4, 1, shoes)
            else:
                s.r(x, y + 9, 4, 3, shoes)
            if holes:
                for (hx, hy) in holes:
                    s.p(x + hx, y + hy, skin)
            if pattern:               # decorative touch, applied last so it can sit on top of the shoe
                pattern(s, x, y, 4, 12)


def sleeves_bare(s, skin, wristband=None):
    for (ax, ay) in ((40, 16), (32, 48)):
        part(s, ax, ay, 4, 12, 4, skin)
        if wristband:
            for (x, y) in ((ax + 4, ay + 4), (ax, ay + 4), (ax + 8, ay + 4), (ax + 12, ay + 4)):
                s.r(x, y + 9, 4, 1, wristband)


def sleeves(s, skin, sleeve, cuff=None, pattern=None):
    for (ax, ay, ox, oy) in ((40, 16, 40, 32), (32, 48, 48, 48)):
        part(s, ax, ay, 4, 12, 4, skin)
        fs = part(s, ox, oy, 4, 12, 4, sleeve)
        if pattern:
            for k in ("front", "back", "right", "left"):
                x, y, w, h = fs[k]
                pattern(s, x, y, w, h)
        if cuff:
            for k in ("front", "back", "right", "left"):
                x, y, w, h = fs[k]
                s.r(x, y + h - 1, w, 1, cuff)


def torso(s, shirt, jacket, pattern=None, collar_trim=None, hem=None):
    part(s, *BODY, shirt)
    fj = part(s, *JKT, jacket)
    if pattern:
        for k in ("front", "back", "right", "left"):
            x, y, w, h = fj[k]
            pattern(s, x, y, w, h)
    if collar_trim:
        for k in ("front", "back", "right", "left"):
            x, y, w, h = fj[k]
            s.r(x, y, w, 1, collar_trim)
    if hem:
        for k in ("front", "back", "right", "left"):
            x, y, w, h = fj[k]
            s.r(x, y + h - 1, w, 1, hem)
    return fj


# ---------------------------------------------------------------- the 7 characters
def make_pastel_pride():
    s = Skin()
    skin, hair, hi = "#F6D7C4", "#F2A9CE", "#FCD3E7"
    part(s, *HEAD, skin)
    hair_base(s, hair, fringe_rows=2)
    face(s, "#4FA0E0", "#C9739E", "#D8607C", blush="#F2A0A8")
    fh = part(s, *HAT, None)
    for k in ("top", "right", "left", "back"):
        x, y, w, h = fh[k]; s.r(x, y, w, h, hair)
    x, y, w, h = fh["front"]; s.r(x, y, w, 3, hair)
    x, y, w, h = fh["right"]; s.r(x, y + 2, 1, 4, hi)
    x, y, w, h = fh["left"]; s.r(x + w - 1, y + 2, 1, 4, hi)
    x, y, w, h = fh["back"]; s.r(x + w // 2, y, 1, h, shade(hair, 0.82))  # centre part
    stripes = ["#5BCEFA", "#F5A9B8", "#FFFFFF", "#F5A9B8", "#5BCEFA"]
    torso(s, "#FFFFFF", "#EAEFF7", pattern=lambda s, x, y, w, h: hstripes(s, x, y, w, h, stripes), collar_trim="#5BCEFA")
    sleeves(s, skin, "#EAEFF7", cuff="#5BCEFA", pattern=lambda s, x, y, w, h: hstripes(s, x, y, w, h, stripes))
    legs(s, "#8FB8E8", "#FFFFFF", skin)
    return s.im, skin, hair


def make_neon_diva():
    s = Skin()
    skin, hair, hi = "#8B5A3C", "#EDEDED", "#FFFFFF"
    part(s, *HEAD, skin)
    hair_base(s, hair, fringe_rows=1)
    face(s, "#3A2A1E", "#2A1E16", "#B5153B", eyeshadow="#6E3A55", lash=True)
    fh = part(s, *HAT, None)
    for k in ("top", "right", "left", "back"):
        x, y, w, h = fh[k]; s.r(x, y, w, h, hair)
    x, y, w, h = fh["front"]; s.r(x, y, w, 2, hair)
    x, y, w, h = fh["top"]; dots(s, x, y, [(1, 1), (4, 2), (6, 4), (2, 5)], hi)
    dress = "#FF1B8D"
    silver = "#F4E9F2"
    torso(s, dress, dress, pattern=lambda s, x, y, w, h: sparkle(s, x, y, w, h, dress, silver, 0.16, seed=1))
    sleeves_bare(s, skin, wristband="#FFFFFF")
    legs(s, dress, "#EDEDED", skin, skirt_hem=5,
         pattern=lambda s, x, y, w, h: sparkle(s, x, y, w, min(h, 5), dress, silver, 0.16, seed=2))
    return s.im, skin, hair


def make_rainbow_skater():
    s = Skin()
    skin, hair, hi = "#D9A66C", "#3B2A22", "#2FBFA0"
    part(s, *HEAD, skin)
    hair_base(s, hair, fringe_rows=2)
    face(s, "#2E7D5B", "#241812", "#B85C4A", blush="#E79C7A")
    fh = part(s, *HAT, None)
    for k in ("top", "back"):
        x, y, w, h = fh[k]; s.r(x, y, w, h, hair)
    for k in ("right", "left"):
        x, y, w, h = fh[k]; s.r(x, y, w, h, hair); s.r(x, y + h - 2, w, 1, hi)
    x, y, w, h = fh["front"]; s.r(x, y, w, 2, hair)
    rainbow = ["#E4402D", "#F3901F", "#F6D22E", "#4CAF50", "#2F6FE0", "#7B3FC4"]
    torso(s, "#FFFFFF", "#F2F2F2", pattern=lambda s, x, y, w, h: hstripes(s, x, y, w, h, rainbow), collar_trim="#E4402D")
    sleeves(s, skin, "#F2F2F2", cuff="#E4402D", pattern=lambda s, x, y, w, h: hstripes(s, x, y, w, h, rainbow))
    legs(s, "#2B4C86", "#F6D22E", skin,
         pattern=lambda s, x, y, w, h: s.r(x + 1, y + 11, 2, 1, "#E4402D"))
    return s.im, skin, hair


def make_bubblegum_punk():
    s = Skin()
    skin, hair, hi = "#E8B894", "#2A1B22", "#FF3FA4"
    part(s, *HEAD, skin)
    fb = part(s, *HEAD, None)
    for k in ("right", "left"):
        x, y, w, h = fb[k]; s.r(x, y, w, h, skin)          # shaved sides on the BASE layer
        for i in range(0, w, 2):                            # buzzed stubble texture
            for j in range(1, h, 2):
                s.p(x + i, y + j, shade(hair, 2.2))
    x, y, w, h = fb["top"]; s.r(x, y, w, h, skin); s.r(x + 3, y, 2, h, hair)
    x, y, w, h = fb["back"]; s.r(x, y, w, h, skin); s.r(x + 3, y, 2, h, hair)
    x, y, w, h = fb["front"]; s.r(x, y, w, 2, skin)
    face(s, "#4A2E3A", "#B9899E", "#9C1B4A")
    fh = part(s, *HAT, None)
    for k in ("right", "left", "front"):
        x, y, w, h = fh[k]  # leave transparent -> shaved sides show through
    x, y, w, h = fh["top"]; s.r(x + 3, y, 2, h, hair); s.r(x + 3, y, 2, 2, hi)
    x, y, w, h = fh["front"]; s.r(x + 3, y, 2, 2, hair)
    x, y, w, h = fh["back"]; s.r(x + 3, y, 2, h, hair)
    studs_pos = [(1, 1), (5, 1), (1, 4), (5, 4), (1, 8), (5, 8), (3, 10)]
    torso(s, "#EDEDED", "#161616", pattern=lambda s, x, y, w, h: dots(s, x, y, studs_pos, "#FF3FA4"), collar_trim="#FF3FA4")
    sleeves(s, skin, "#161616", cuff="#FF3FA4", pattern=lambda s, x, y, w, h: dots(s, x, y, [(1, 1), (1, 6)], "#FF3FA4"))
    legs(s, "#26262E", "#FF3FA4", skin, holes=[(1, 3), (2, 4), (1, 7)])
    return s.im, skin, hair


def make_cherry_blossom():
    s = Skin()
    skin, hair, hi = "#F3D2B8", "#241A1E", "#3A2A2E"
    part(s, *HEAD, skin)
    hair_base(s, hair, fringe_rows=3)
    face(s, "#3E2A2A", "#241A1E", "#D8607C", blush="#F2A0A8")
    fh = part(s, *HAT, None)
    for k in ("top", "right", "left", "back"):
        x, y, w, h = fh[k]; s.r(x, y, w, h, hair)
    x, y, w, h = fh["front"]; s.r(x, y, w, 3, hair)
    x, y, w, h = fh["right"]; dots(s, x, y, [(0, 2), (1, 3), (0, 3)], "#FF9FC6"); s.p(x + 1, y + 2, "#FFE17A")
    fj_back_hair_row = 3
    torso(s, "#FFF3EC", "#FFE3EE")
    fj = part(s, *JKT, None)
    x, y, w, h = fj["front"]
    s.r(x, y, w, h, "#FFE3EE")
    s.r(x, y, w, 3, "#FBD3E4")
    for row in range(h):
        cut = max(0, 3 - row)
        if cut:
            s.r(x + w // 2 - cut, y + row, cut * 2, 1, "#F49FC4")
    petal_pts = [(1, 6), (6, 8), (2, 9), (5, 5)]
    dots(s, x, y, petal_pts, "#FF9FC6")
    xb, yb, wb, hb = fj["back"]
    s.r(xb, yb, wb, hb, "#FFE3EE")
    s.r(xb, yb + hb - fj_back_hair_row, wb, fj_back_hair_row, hair)
    for k in ("right", "left"):
        x, y, w, h = fj[k]; s.r(x, y, w, h, "#FBD3E4")
    sleeves(s, skin, "#FFE3EE", cuff="#F49FC4")
    legs(s, "#FBD3E4", "#FFF7F2", skin, skirt_hem=6, sock="#FFFFFF")
    return s.im, skin, hair


def make_disco_cowboy():
    s = Skin()
    skin, hair, hi = "#B97A52", "#241812", "#3A2A20"
    part(s, *HEAD, skin)
    hair_base(s, hair, top=False, fringe_rows=0)
    face(s, "#241812", "#1C130E", "#B5153B", blush="#E79C7A")
    pink, gold, dark = "#FF3FA4", "#F6C453", "#B02E7C"
    fh = part(s, *HAT, None)                     # crown + brim only -- rows 3-7 (eyes..mouth) stay transparent
    x, y, w, h = fh["top"]; s.r(x, y, w, h, "#FF6BBE")
    for k in ("front", "back", "right", "left"):
        x, y, w, h = fh[k]
        s.r(x, y, w, 3, pink)     # brim band sits above the brow line only
        s.r(x, y, w, 1, dark)     # crown seam
        s.r(x, y + 2, w, 1, gold)  # brim edge
    torso(s, "#FFEFD6", pink, collar_trim=dark, hem=dark)
    fj = part(s, *JKT, None)
    for k in ("front", "back"):
        x, y, w, h = fj[k]
        for col in range(w):
            if col % 2 == 0:
                s.r(x + col, y + h - 3, 1, 3, gold)
    sleeves(s, skin, pink, cuff=gold)
    legs(s, "#2B2038", gold, skin, sock=None)
    return s.im, skin, hair


def make_soft_boy():
    s = Skin()
    skin, hair, hi = "#E3B48C", "#8A5A3C", "#B98457"
    part(s, *HEAD, skin)
    hair_base(s, hair, fringe_rows=2)
    face(s, "#3E2A1C", "#5B4436", "#B5715B", blush="#E7B69A", glasses="#4A4A54")
    fh = part(s, *HAT, None)
    for k in ("top", "right", "left", "back"):
        x, y, w, h = fh[k]; s.r(x, y, w, h, hair)
    x, y, w, h = fh["front"]; s.r(x, y, w, 2, hair)
    for k in ("top", "back", "right", "left"):        # curl speckle -- NOT "front": rows 2-7 (eyes..mouth) must stay clear
        x, y, w, h = fh[k]
        for i in range(0, w, 2):
            for j in range(0, h, 3):
                s.p(x + i, y + j, hi)
    x, y, w, h = fh["front"]                          # a couple of curl flecks in the fringe only (rows 0-1)
    for i in range(0, w, 2):
        s.p(x + i, y, hi)
    pink = "#F5A3C7"
    torso(s, "#FFFFFF", pink, pattern=lambda s, x, y, w, h: ribbing(s, x, y, w, h, pink, shade(pink, 0.82), period=2),
          collar_trim=shade(pink, 0.75), hem=shade(pink, 0.75))
    sleeves(s, skin, pink, cuff=shade(pink, 0.75),
            pattern=lambda s, x, y, w, h: ribbing(s, x, y, w, h, pink, shade(pink, 0.82), period=2))
    legs(s, "#7C93C4", "#F1E9DD", skin)
    return s.im, skin, hair


CHARACTERS = [
    ("pastel_pride", "Pastel Pride", "Pastel Pride", make_pastel_pride),
    ("neon_diva", "Neon Diva", "Neon Diva", make_neon_diva),
    ("rainbow_skater", "Rainbow Skater", "Rainbow Skater", make_rainbow_skater),
    ("bubblegum_punk", "Bubblegum Punk", "Bubblegum Punk", make_bubblegum_punk),
    ("cherry_blossom", "Cherry Blossom", "Cherry Blossom", make_cherry_blossom),
    ("disco_cowboy", "Disco Cowboy", "Disco Cowboy", make_disco_cowboy),
    ("soft_boy", "Cozy Soft Boy", "Cozy Soft Boy", make_soft_boy),
]


MASK_EXCEPTIONS = set()  # skin ids where opaque overlay pixels legitimately sit over rows 3-7 (e.g. a visor/mask)


def color_dist(c1, c2):
    a, b = hexc(c1), hexc(c2)
    return sum((a[i] - b[i]) ** 2 for i in range(3)) ** 0.5


def validate_face(sid, im, skin, hair):
    """Guard against the overlay/hat layer hiding the face: rows 3-7 of the HAT front face (eyes -> mouth)
    must be mostly transparent unless the id is in MASK_EXCEPTIONS; also the base skin tone must actually
    read as skin, not as the hair colour."""
    fh_front = part(Skin(), *HAT, None)["front"]   # (x,y,w,h) of the overlay/hat front face, fixed geometry
    x, y, w, h = fh_front
    y0, h0 = y + 3, 5   # rows 3..7 = eyes through mouth
    transparent = sum(1 for i in range(w) for j in range(h0) if im.getpixel((x + i, y0 + j))[3] == 0)
    frac = transparent / (w * h0)
    if sid not in MASK_EXCEPTIONS and frac < 0.60:
        raise SystemExit(f"FACE CHECK FAILED for {sid}: overlay covers the face -- only {frac:.0%} of the "
                          f"eyes/mouth region (hat-layer front rows 3-7) is transparent (need >=60%)")
    if color_dist(skin, hair) < 40:
        raise SystemExit(f"FACE CHECK FAILED for {sid}: base skin tone {skin} is too close to the hair "
                          f"colour {hair} (distance {color_dist(skin, hair):.0f}, need >=40) -- the face will "
                          f"read as a blank blob")
    print(f"  face check ok: {sid} (overlay transparent {frac:.0%}, skin/hair distance {color_dist(skin, hair):.0f})")


def build_skins():
    imgs = {}
    for sid, name_en, name_he, fn in CHARACTERS:
        im, skin, hair = fn()
        validate_face(sid, im, skin, hair)
        im.save(os.path.join(SKIN_DIR, sid + ".png"))
        im.save(os.path.join(RAW_DIR, sid + ".png"))
        imgs[sid] = im
    return imgs


# ---------------------------------------------------------------- preview sheet (front+back x8 + raw atlas)
def crop(im, x, y, w, h):
    return im.crop((x, y, x + w, y + h))


def compose_view(im, order):
    can = Image.new("RGBA", (16, 32), (0, 0, 0, 0))
    can.alpha_composite(crop(im, *order["head"]), (4, 0)); can.alpha_composite(crop(im, *order["hat"]), (4, 0))
    can.alpha_composite(crop(im, *order["body"]), (4, 8)); can.alpha_composite(crop(im, *order["body_o"]), (4, 8))
    can.alpha_composite(crop(im, *order["rarm"]), (0, 8)); can.alpha_composite(crop(im, *order["rarm_o"]), (0, 8))
    can.alpha_composite(crop(im, *order["larm"]), (12, 8)); can.alpha_composite(crop(im, *order["larm_o"]), (12, 8))
    can.alpha_composite(crop(im, *order["rleg"]), (4, 20)); can.alpha_composite(crop(im, *order["rleg_o"]), (4, 20))
    can.alpha_composite(crop(im, *order["lleg"]), (8, 20)); can.alpha_composite(crop(im, *order["lleg_o"]), (8, 20))
    return can


FRONT = dict(head=(8, 8, 8, 8), hat=(40, 8, 8, 8), body=(20, 20, 8, 12), body_o=(20, 36, 8, 12),
             rarm=(44, 20, 4, 12), rarm_o=(44, 36, 4, 12), larm=(36, 52, 4, 12), larm_o=(52, 52, 4, 12),
             rleg=(4, 20, 4, 12), rleg_o=(4, 36, 4, 12), lleg=(20, 52, 4, 12), lleg_o=(4, 52, 4, 12))
BACK = dict(head=(24, 8, 8, 8), hat=(56, 8, 8, 8), body=(32, 20, 8, 12), body_o=(32, 36, 8, 12),
            rarm=(52, 20, 4, 12), rarm_o=(52, 36, 4, 12), larm=(44, 52, 4, 12), larm_o=(60, 52, 4, 12),
            rleg=(12, 20, 4, 12), rleg_o=(12, 36, 4, 12), lleg=(28, 52, 4, 12), lleg_o=(12, 52, 4, 12))


def build_sheet(imgs):
    SC = 8
    RAWSC = 3
    row_h = 32 * SC + 34
    front_w = 16 * SC
    raw_w = 64 * RAWSC
    col_gap = 14
    row_w = col_gap + front_w + col_gap + front_w + col_gap + raw_w + col_gap
    sheet = Image.new("RGBA", (row_w, row_h * len(imgs) + 10), (24, 20, 30, 255))
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 16)
        font_s = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 12)
    except Exception:
        font = ImageFont.load_default(); font_s = font
    for n, (sid, name_en, name_he, _fn) in enumerate(CHARACTERS):
        im = imgs[sid]
        y0 = 10 + n * row_h
        front = compose_view(im, FRONT).resize((front_w, 32 * SC), Image.NEAREST)
        back = compose_view(im, BACK).resize((front_w, 32 * SC), Image.NEAREST)
        raw = im.resize((raw_w, raw_w), Image.NEAREST)
        d.rectangle([col_gap - 4, y0 - 4, col_gap + front_w + 4, y0 + 32 * SC + 4], outline=(90, 90, 110), width=1)
        sheet.alpha_composite(front, (col_gap, y0))
        x2 = col_gap + front_w + col_gap
        d.rectangle([x2 - 4, y0 - 4, x2 + front_w + 4, y0 + 32 * SC + 4], outline=(90, 90, 110), width=1)
        sheet.alpha_composite(back, (x2, y0))
        x3 = x2 + front_w + col_gap
        sheet.alpha_composite(raw, (x3, y0))
        d.rectangle([x3 - 2, y0 - 2, x3 + raw_w + 2, y0 + raw_w + 2], outline=(90, 90, 110), width=1)
        d.text((col_gap, y0 + 32 * SC + 6), f"{n + 1}. {name_en}", fill=(255, 255, 255), font=font)
        d.text((col_gap, y0 + 32 * SC + 24), f"id: {sid}   64x64 atlas ->", fill=(200, 200, 210), font=font_s)
    sheet.convert("RGB").save(os.path.join(PREV_DIR, "studio_skins_sheet.png"))


# ---------------------------------------------------------------- resident_card + card_display (flat quad items)
def quad_model(tex_ref):
    return {"textures": {"0": tex_ref, "particle": tex_ref},
            "elements": [{"from": [0, 0, 7.9], "to": [16, 16, 8.1],
                           "faces": {"north": {"uv": [0, 0, 16, 16], "texture": "#0"},
                                     "south": {"uv": [0, 0, 16, 16], "texture": "#0"}}}]}


def draw_resident_card(size):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    m = size // 16
    x0, y0, x1, y1 = m, int(m * 2.2), size - m, size - int(m * 2.2)
    d.rounded_rectangle([x0 + 1, y0 + 2, x1 + 1, y1 + 2], radius=m, fill=(120, 30, 80, 90))  # soft shadow
    for i in range(y1 - y0):
        t = i / max(1, (y1 - y0))
        col = mix("#FFE3EE", "#FF9FC6", t)
        d.line([(x0, y0 + i), (x1, y0 + i)], fill=col)
    d.rounded_rectangle([x0, y0, x1, y1], radius=m, outline=(255, 255, 255, 230), width=max(1, m // 3))
    d.rounded_rectangle([x0 + 1, y0 + 1, x1 - 1, y1 - 1], radius=m, outline=(214, 60, 130, 255), width=1)
    # tiny tower silhouette top-left (abstract skyline)
    bx, by = x0 + m, y0 + m
    tw = m // 2
    heights = [3, 5, 4, 6, 3]
    tower_dark = (150, 40, 95, 255)
    for i, hh in enumerate(heights):
        hh_px = hh * (m // 3)
        d.rectangle([bx + i * tw, by + (5 * (m // 3)) - hh_px, bx + i * tw + tw - 1, by + 5 * (m // 3)], fill=tower_dark)
    # photo box (rounded square + person silhouette) upper right
    pb = int(m * 3.2)
    px1, py1 = x1 - m - pb, y0 + m
    d.rounded_rectangle([px1, py1, px1 + pb, py1 + pb], radius=max(2, m // 3), fill=(255, 255, 255, 235),
                         outline=(214, 60, 130, 255))
    cx, cy = px1 + pb // 2, py1 + int(pb * 0.38)
    rr = int(pb * 0.22)
    d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=(214, 60, 130, 255))
    d.pieslice([cx - int(pb * 0.34), cy + int(pb * 0.05), cx + int(pb * 0.34), cy + int(pb * 0.6)], 180, 360,
               fill=(214, 60, 130, 255))
    # abstract text bars
    ty = py1 + pb + m
    bar_widths = [0.62, 0.42, 0.5]
    for i, bw in enumerate(bar_widths):
        yy = ty + i * (m + 1)
        d.rounded_rectangle([x0 + m, yy, x0 + m + int((x1 - x0 - 2 * m) * bw), yy + max(2, m // 2)],
                             radius=1, fill=(150, 90, 120, 220))
    # gold chip bottom-left
    chw, chh = int(m * 2.6), int(m * 1.8)
    chx, chy = x0 + m, y1 - m - chh
    d.rounded_rectangle([chx, chy, chx + chw, chy + chh], radius=max(1, m // 4), fill=(214, 172, 90, 255),
                         outline=(150, 112, 48, 255))
    for gy in range(chy + 2, chy + chh - 1, max(2, chh // 4)):
        d.line([(chx + 1, gy), (chx + chw - 1, gy)], fill=(150, 112, 48, 255))
    # holo strip bottom-right
    hx0, hy0, hx1, hy1 = x1 - int(m * 2.2), y1 - m - int(m * 1.4), x1 - m, y1 - m
    for i in range(hx0, hx1):
        t = (i - hx0) / max(1, hx1 - hx0)
        d.line([(i, hy0), (i, hy1)], fill=mix("#B0E0FF", "#FFD3EF", t))
    return im


def draw_card_display(w, h):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    m = w // 24
    for i in range(h):
        t = i / h
        d.line([(0, i), (w, i)], fill=mix("#FFE3EE", "#FF9FC6", t))
    d.rectangle([m // 2, m // 2, w - m // 2, h - m // 2], outline=(214, 60, 130, 255), width=max(1, m // 4))
    heights = [40, 70, 55, 95, 45, 60]
    tw = int(w * 0.28) // len(heights)
    bx, by = int(m * 1.6), int(h * 0.62)
    for i, hh in enumerate(heights):
        hh = int(hh * (h / 300))
        d.rectangle([bx + i * tw, by - hh, bx + i * tw + tw - 3, by], fill=(150, 40, 95, 255))
        d.rectangle([bx + i * tw + 2, by - hh + 4, bx + i * tw + tw - 5, by - hh + 8], fill=(255, 220, 130, 220))
    pb = int(h * 0.42)
    px1, py1 = w - int(m * 3) - pb, int(m * 2)
    d.rounded_rectangle([px1, py1, px1 + pb, py1 + pb], radius=8, fill=(255, 255, 255, 235), outline=(214, 60, 130, 255), width=3)
    cx, cy = px1 + pb // 2, py1 + int(pb * 0.4)
    rr = int(pb * 0.22)
    d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=(214, 60, 130, 255))
    d.pieslice([cx - int(pb * 0.34), cy + int(pb * 0.08), cx + int(pb * 0.34), cy + int(pb * 0.62)], 180, 360, fill=(214, 60, 130, 255))
    ty = py1 + pb + int(m * 1.2)
    for i, bw in enumerate([0.6, 0.4, 0.5]):
        yy = ty + i * int(h * 0.06)
        d.rounded_rectangle([int(m * 1.6), yy, int(m * 1.6) + int(w * 0.4 * bw), yy + int(h * 0.03)], radius=3, fill=(150, 90, 120, 220))
    chw, chh = int(w * 0.14), int(h * 0.12)
    chx, chy = int(m * 1.6), h - int(m * 2) - chh
    d.rounded_rectangle([chx, chy, chx + chw, chy + chh], radius=4, fill=(214, 172, 90, 255), outline=(150, 112, 48, 255), width=2)
    for gy in range(chy + 4, chy + chh - 2, max(3, chh // 5)):
        d.line([(chx + 2, gy), (chx + chw - 2, gy)], fill=(150, 112, 48, 255), width=2)
    return im


def build_items():
    card = draw_resident_card(64)
    card.save(os.path.join(ITEM_TEX_DIR, "resident_card.png"))
    display = draw_card_display(256, 160)
    display.save(os.path.join(ITEM_TEX_DIR, "card_display.png"))
    json.dump(quad_model(f"{NS}:item/resident_card"), open(os.path.join(ITEM_MODEL_DIR, "resident_card.json"), "w"))
    json.dump(quad_model(f"{NS}:item/card_display"), open(os.path.join(ITEM_MODEL_DIR, "card_display.json"), "w"))
    for iid in ("resident_card", "card_display"):
        json.dump({"model": {"type": "minecraft:model", "model": f"{NS}:item/{iid}"}},
                   open(os.path.join(ITEM_DIR, iid + ".json"), "w"))


def build_pack_meta_and_zip():
    json.dump({"pack": {"description": "Pink Golem character studio", "min_format": 88, "max_format": 88}},
              open(os.path.join(OUT, "pack.mcmeta"), "w"))
    zpath = os.path.join(HERE, "studio.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for d, _, fs in os.walk(OUT):
            for f in sorted(fs):
                z.write(os.path.join(d, f), os.path.relpath(os.path.join(d, f), OUT))
    return zpath


def build_json_list():
    listing = [{"id": sid, "name_he": name_he, "name_en": name_en, "model": "classic",
                "file": f"skins/{sid}.png"} for sid, name_en, name_he, _fn in CHARACTERS]
    p = os.path.join(HERE, "skins.json")
    json.dump(listing, open(p, "w"), ensure_ascii=False, indent=2)
    return p


def render_model_previews():
    for mid, out in (("resident_card", "resident_card_preview.png"), ("card_display", "card_display_preview.png")):
        outp = os.path.join(PREV_DIR, out)
        subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.dirname(HERE)), "resourcepacks", "tools", "model_preview.py"), OUT, f"{NS}:item/{mid}",
                        "--out", outp, "--yaw", "25", "--pitch", "18"], check=False)


if __name__ == "__main__":
    imgs = build_skins()
    build_sheet(imgs)
    build_items()
    zpath = build_pack_meta_and_zip()
    jpath = build_json_list()
    render_model_previews()
    print(json.dumps({"zip": zpath, "zip_kb": os.path.getsize(zpath) // 1024, "json": jpath,
                       "chars": [c[0] for c in CHARACTERS]}, ensure_ascii=False))
