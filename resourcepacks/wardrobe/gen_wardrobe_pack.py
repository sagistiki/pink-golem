"""gen_wardrobe_pack.py -- the character studio's fitting wall (scarpet-apps/residents.sc): REAL clothes from the
resource pack (26.x equipment assets), not dyed leather. Everything here is original pixel art drawn in code:
15 tops, 11 bottoms, 8 pairs of shoes, 4 wigs, 5 pairs of wings, 15 3D hats and a blank fitting-dummy skin.

What the game gives us (checked in the 26.2 client jar):
  * an item with  equippable={slot:"chest",asset_id:"wardrobe:top_hoodie"}  is drawn with
    assets/wardrobe/equipment/top_hoodie.json -> layers humanoid / humanoid_leggings / wings, each a texture
    assets/wardrobe/textures/entity/equipment/<layer>/<name>.png (64x32, the old armour layout; transparent = not drawn).
    humanoid = head/chest/feet, humanoid_leggings = legs, wings = the elytra model.
    HumanoidArmorLayer.shouldRender = asset id present AND slot matches. Players and mannequins (AvatarRenderer) both.
  * the WINGS layer (elytra model) is drawn for the chest item whenever its asset has a "wings" layer -> one chest item
    can carry a top AND wings (asset top_<t>__<w>); without a "glider" component nobody glides.
  * a head item with equippable but WITHOUT an asset id goes through CustomHeadLayer: its item model is drawn on the
    head (translate y -0.25, rotate Y 180, scale 0.625/-0.625/-0.625) -> a 3D hat. The head spans model units
    1.6..14.4 on every axis (1 head pixel = 1.6 units), model north (-z) = the face, x is mirrored.
  * mannequins render like players, so a mannequin previews everything; `item replace entity <uuid> armor.<slot>`
    dresses it.
Layers: head (3D hats + wig textures), wings, top (chest), legs (leggings layer), feet (boots = humanoid legs, low rows).

Run: python3 resourcepacks/wardrobe/gen_wardrobe_pack.py
  -> resourcepacks/wardrobe/build/ + resourcepacks/wardrobe/wardrobe.zip (namespace "wardrobe")
  -> scarpet-apps/residents.data.example/wardrobe.json (catalogue for residents.sc: rows, names, item strings)
  -> resourcepacks/wardrobe/previews/wardrobe_sheet.png (every piece on the dummy, front + back),
     previews/wardrobe_hats_1.png + _2.png (the 3D hats, rendered with resourcepacks/tools/model_preview.py)
"""
import json
import os
import random
import shutil
import subprocess
import sys
import zipfile

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
NS = "wardrobe"
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, "build")
A = os.path.join(OUT, "assets", NS)
ZIP = os.path.join(HERE, "wardrobe.zip")
CATALOG = os.path.join(ROOT, "scarpet-apps", "residents.data.example", "wardrobe.json")
PREV = os.path.join(HERE, "previews")
MODEL_PREVIEW = os.path.join(ROOT, "resourcepacks", "tools", "model_preview.py")


def hexc(c):
    if c is None:
        return None
    if isinstance(c, tuple):
        return c if len(c) == 4 else tuple(c) + (255,)
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4)) + (255,)


def shade(c, f):
    r, g, b, a = hexc(c)
    return (max(0, min(255, int(r * f))), max(0, min(255, int(g * f))), max(0, min(255, int(b * f))), a)


def mix(c1, c2, t):
    c1, c2 = hexc(c1), hexc(c2)
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(4))


RAINBOW = ["#E53935", "#FB8C00", "#FDD835", "#43A047", "#1E88E5", "#8E24AA"]

# ------------------------------------------------------------------ 64x32 armour texture
HEAD, HAT = (0, 0, 8, 8, 8), (32, 0, 8, 8, 8)
BODY, ARM, LEG = (16, 16, 8, 12, 4), (40, 16, 4, 12, 4), (0, 16, 4, 12, 4)
SIDES = ("front", "back", "right", "left")
FACE_SHADE = {"front": 1.0, "back": 0.93, "right": 0.88, "left": 0.88, "top": 1.06, "bottom": 0.8}


def faces_of(box):
    ox, oy, w, h, d = box
    return {"top": (ox + d, oy, w, d), "bottom": (ox + d + w, oy, w, d),
            "right": (ox, oy + d, d, h), "front": (ox + d, oy + d, w, h),
            "left": (ox + d + w, oy + d, d, h), "back": (ox + 2 * d + w, oy + d, w, h)}


class Tex:
    def __init__(self, w=64, h=32):
        self.im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        self.px = self.im.load()
        self.w, self.h = w, h

    def put(self, x, y, c):
        if c is not None and 0 <= x < self.w and 0 <= y < self.h:
            self.px[x, y] = hexc(c)

    def paint(self, box, fn, faces=("front", "back", "right", "left", "top"), shaded=True):
        """fn(face, i, j, w, h) -> colour or None (None = transparent = not drawn). j = row from the top."""
        for f in faces:
            x, y, w, h = faces_of(box)[f]
            for i in range(w):
                for j in range(h):
                    c = fn(f, i, j, w, h)
                    if c is not None and shaded:
                        c = shade(c, FACE_SHADE[f])
                    self.put(x + i, y + j, c)


def noise(seed):
    rnd = random.Random(seed)
    cache = {}

    def n(*k):
        if k not in cache:
            cache[k] = rnd.random()
        return cache[k]
    return n


# ------------------------------------------------------------------ TOPS (chest: body + arms of the humanoid layer)
def top_base(t, body, arm, sleeve="long"):
    """body(face,i,j,w,h) / arm(face,i,j,w,h) give colours; sleeve long | short | none."""
    t.paint(BODY, body)
    if sleeve == "none":
        return

    def a(f, i, j, w, h):
        if f == "top":
            return arm("front", i, 0, w, 12)
        if sleeve == "short" and j > 3:
            return None
        return arm(f, i, j, w, h)
    t.paint(ARM, a)


def mk_hoodie(t):
    base, dark, rib = "#F48FB1", "#E07199", "#D8618B"

    def body(f, i, j, w, h):
        if j == 11:
            return rib
        if f == "front":
            if j in (1, 2, 3) and i in (3, 4):
                return "#FFFFFF" if j < 3 else "#F3D6E1"
            if 7 <= j <= 10 and 1 <= i <= 6:
                return dark if (j == 7 or i in (1, 6)) else base
        if f == "back" and j <= 3:
            return dark if (i in (0, 7) or j == 3) else mix(base, dark, 0.4)
        return base

    def arm(f, i, j, w, h):
        return rib if j == 11 else base
    top_base(t, body, arm)


def mk_leather(t):
    blk, hi = "#26262C", "#3E3E48"
    n = noise(2)

    def body(f, i, j, w, h):
        if f == "front":
            if i in (3, 4):
                return "#F2F2F2"
            if i in (2, 5) and j <= 4:
                return "#34343C"
            if i == 5 and j == 3:
                return "#FF6FAE"
            if i == 2 and j >= 5:
                return "#C5C5CE"
        if j == 11:
            return "#1A1A1F"
        return hi if n(f, i, j) < 0.12 else blk

    def arm(f, i, j, w, h):
        if j == 11:
            return "#C5C5CE" if (f == "front" and i == 1) else "#1A1A1F"
        return hi if n("a", f, i, j) < 0.12 else blk
    top_base(t, body, arm)


def mk_tux(t):
    jk = "#1B1B25"

    def body(f, i, j, w, h):
        if f == "front":
            if j <= 1 and 2 <= i <= 5:
                return "#E0287F" if i in (3, 4) else "#FF4FA0"
            if i in (3, 4) and j <= 6:
                return "#FAFAFA"
            if i in (2, 5) and j <= 6:
                return "#34344A"
            if i == 3 and j in (8, 10):
                return "#E8C15A"
            if i == 6 and j == 3:
                return "#FF7AC6"
        return jk

    def arm(f, i, j, w, h):
        if j == 11:
            return "#FAFAFA"
        if j == 10 and f == "front" and i == 2:
            return "#E8C15A"
        return jk
    top_base(t, body, arm)


def mk_rainbow(t):
    def body(f, i, j, w, h):
        return RAINBOW[min(5, j // 2)]

    def arm(f, i, j, w, h):
        return RAINBOW[min(5, j // 2)]
    top_base(t, body, arm, "short")


HEART = [".XX.XX.", "XXXXXXX", "XXXXXXX", ".XXXXX.", "..XXX..", "...X..."]


def mk_pride(t):
    def body(f, i, j, w, h):
        if f == "front" and 2 <= j <= 7:
            hi, hj = i, j - 2
            if hi < 7 and HEART[hj][hi] == "X":
                return RAINBOW[min(5, hj)]
        if j == 0 and f == "front" and 2 <= i <= 5:
            return "#E6E6E6"
        return "#F7F7F7"

    def arm(f, i, j, w, h):
        return "#FF7AC6" if j == 3 else "#F7F7F7"
    top_base(t, body, arm, "short")


def mk_denim(t):
    d, lt, dk = "#4A78B5", "#7FA3D6", "#355A8C"

    def body(f, i, j, w, h):
        if j == 0:
            return lt
        if f == "front":
            if i in (3, 4) and j in (2, 5, 8):
                return "#D4B06A"
            if j in (3, 4) and i in (1, 2, 5, 6):
                return dk if j == 3 else mix(d, dk, 0.5)
            if i in (1, 6):
                return lt if j % 2 == 0 else d
        if j == 11:
            return dk
        return d

    def arm(f, i, j, w, h):
        return lt if j >= 10 else d
    top_base(t, body, arm)


def mk_hawaii(t):
    n = noise(7)
    base = "#26C6DA"

    def pat(tag, f, i, j):
        k = n(tag, f, i // 3, j // 3)
        ci, cj = i % 3, j % 3
        if k < 0.45:
            if ci == 1 and cj == 1:
                return "#FFE066"
            if (ci, cj) in ((0, 1), (2, 1), (1, 0), (1, 2)):
                return "#FF5C8A"
        elif k < 0.6 and (ci + cj) % 3 == 0:
            return "#2E9E5B"
        return base

    def body(f, i, j, w, h):
        if f == "front" and j <= 1 and i in (3, 4):
            return None
        if f == "front" and j <= 2 and i in (2, 5):
            return "#FFFFFF"
        return pat("b", f, i, j)

    def arm(f, i, j, w, h):
        return "#FFFFFF" if j == 3 else pat("a", f, i, j)
    top_base(t, body, arm, "short")


def mk_hearts(t):
    cream, rib = "#F3E5D0", "#E0CBAA"

    def pat(i, j):
        a, b = i % 4, j % 4
        if (a, b) in ((0, 0), (2, 0), (0, 1), (1, 1), (2, 1), (1, 2)):
            return "#E0284F"
        return cream

    def body(f, i, j, w, h):
        if j >= 10 or j == 0:
            return rib if i % 2 else cream
        return pat(i + (1 if f in ("left", "right") else 0), j + 1)

    def arm(f, i, j, w, h):
        if j >= 10:
            return rib if i % 2 else cream
        return pat(i, j + 3)
    top_base(t, body, arm)


def mk_kimono(t):
    n = noise(11)
    base = "#F7B6CF"

    def dots(tag, f, i, j):
        k = n(tag, f, i, j)
        return "#FFFFFF" if k < 0.10 else ("#E0487F" if k < 0.16 else base)

    def body(f, i, j, w, h):
        if 6 <= j <= 8:
            return "#E8B84A" if j == 7 else "#8E1B3F"
        if f == "front" and j < 6 and i in (3 - j // 2, 4 + j // 2):     # the crossed V collar
            return "#C9577F"
        return dots("b", f, i, j)

    def arm(f, i, j, w, h):
        return "#C9577F" if j == 11 else dots("a", f, i, j)
    top_base(t, body, arm)


def mk_stars(t):
    n = noise(13)
    base = "#1E2A5A"

    def s(tag, f, i, j):
        k = n(tag, f, i, j)
        if k < 0.08:
            return "#FFE066"
        if k < 0.13:
            return "#FFFFFF"
        if k < 0.16:
            return "#FF7AC6"
        return base

    def body(f, i, j, w, h):
        return "#2E3D7A" if j == 11 else s("b", f, i, j)

    def arm(f, i, j, w, h):
        return "#2E3D7A" if j == 11 else s("a", f, i, j)
    top_base(t, body, arm)


TRANS = ["#5BCEFA", "#5BCEFA", "#F5A9B8", "#F5A9B8", "#F5A9B8", "#FFFFFF", "#FFFFFF", "#F5A9B8", "#F5A9B8",
         "#F5A9B8", "#5BCEFA", "#5BCEFA"]


def mk_trans(t):
    def body(f, i, j, w, h):
        if f == "front" and j in (1, 2, 3) and i in (3, 4):
            return "#FFFFFF" if j < 3 else "#DDE8F0"
        return TRANS[j]

    def arm(f, i, j, w, h):
        return TRANS[j]
    top_base(t, body, arm)


def mk_fur(t):
    n = noise(17)
    tones = ["#F8A5C2", "#F592B6", "#FBB9D0", "#EE86AE"]

    def fur(tag, f, i, j):
        return tones[int(n(tag, f, i, j) * 4)]

    def body(f, i, j, w, h):
        if f == "front" and i in (3, 4):
            return "#FFFFFF" if n("t", i, j) > 0.25 else "#F1ECEF"
        if j == 11:
            return "#FFFFFF"
        return fur("b", f, i, j)

    def arm(f, i, j, w, h):
        return "#FFFFFF" if j >= 10 else fur("a", f, i, j)
    top_base(t, body, arm)


def mk_jersey(t):
    white, pink, purple = "#F7F7F7", "#FF4FA0", "#8E4FD6"

    def body(f, i, j, w, h):
        if f in ("left", "right") and i in (1, 2):
            return pink
        if f == "front" and j == 0 and 2 <= i <= 5:
            return pink
        if f == "front" and j == 1 and i in (2, 5):
            return pink
        if f == "front" and (i, j) in ((5, 3), (4, 4), (5, 4), (6, 4), (5, 5)):
            return "#FFD23F"
        if f == "back" and 3 <= j <= 8:
            hi, hj = i - 1 if i >= 1 else 9, j - 3
            if 0 <= hi < 7 and hj < 6 and HEART[hj][hi] == "X":
                return pink
        return white

    def arm(f, i, j, w, h):
        return pink if j == 1 else (purple if j == 2 else white)
    top_base(t, body, arm, "short")


def mk_princess(t):
    base, lt, gold = "#F9A8D4", "#FFD1E8", "#E8B84A"

    def body(f, i, j, w, h):
        if j == 0:
            return "#FFFFFF" if (i + (1 if f == "back" else 0)) % 2 == 0 else lt
        if j >= 10:
            return gold if j == 10 else base
        if f == "front" and 2 <= j <= 9 and i in (3, 4):
            return gold if (i == 3) == (j % 2 == 0) else "#FFE9A8"
        return base

    def arm(f, i, j, w, h):
        if j == 3:
            return "#FFFFFF"
        return lt if (i + j) % 3 else "#FFE3F1"
    top_base(t, body, arm, "short")


def mk_tank(t):
    def body(f, i, j, w, h):
        if f in ("front", "back") and j == 0 and 2 <= i <= 5:
            return None
        if j == 0 and f in ("front", "back"):
            return "#FF4FA0"
        if f == "front" and j == 4 and 2 <= i <= 5:
            return "#FF4FA0"
        return "#222226"
    top_base(t, body, None, "none")


TOPS = [
    ("hoodie", "Pink hoodie", mk_hoodie), ("leather", "Black leather jacket", mk_leather), ("tux", "Party suit", mk_tux),
    ("rainbow", "Rainbow stripe tee", mk_rainbow), ("pride", "Pride heart tee", mk_pride), ("denim", "Denim jacket", mk_denim),
    ("hawaii", "Hawaiian shirt", mk_hawaii), ("hearts", "Hearts sweater", mk_hearts), ("kimono", "Cherry kimono", mk_kimono),
    ("stars", "Star shirt", mk_stars), ("trans", "Trans hoodie", mk_trans), ("fur", "Pink fur coat", mk_fur),
    ("jersey", "Sports jersey", mk_jersey), ("princess", "Princess corset", mk_princess), ("tank", "Black tank top", mk_tank),
]


# ------------------------------------------------------------------ BOTTOMS (humanoid_leggings: body waist + legs)
def bottom_base(t, leg, waist):
    t.paint(LEG, leg, faces=SIDES)
    t.paint(BODY, lambda f, i, j, w, h: waist(f, i, j) if j >= 9 else None, faces=SIDES)


def belt(col, buckle):
    return lambda f, i, j: (buckle if (f == "front" and i in (3, 4) and j == 10) else (col if j >= 10 else None))


def mk_jeans(t):
    d, seam, dk = "#3B5E9A", "#5D82C0", "#2D4A7C"
    bottom_base(t, lambda f, i, j, w, h: dk if j == 11 else (seam if f in ("right", "left") and i == 1 else
                (mix(d, seam, 0.35) if f == "front" and j in (5, 6) else d)),
                lambda f, i, j: "#6B4423" if j >= 10 and not (f == "front" and i in (3, 4) and j == 10) else
                ("#E8C15A" if j == 10 else d))


def mk_ripped(t):
    n = noise(21)
    blk = "#2A2A2E"

    def leg(f, i, j, w, h):
        if f == "front" and j in (4, 5, 8):
            k = n(i, j)
            if k < 0.35:
                return None
            if k < 0.55:
                return "#DADADA"
        return "#1E1E22" if j == 11 else blk
    bottom_base(t, leg, belt("#111114", "#C5C5CE"))


def mk_pleats(t):
    pink, dk = "#F48FB1", "#D86A93"

    def leg(f, i, j, w, h):
        if j > 5:
            return None
        if j == 5:
            return "#FFFFFF"
        return dk if i % 2 else pink
    bottom_base(t, leg, lambda f, i, j: dk if j == 9 else (dk if i % 2 else pink))


def mk_tutu(t):
    n = noise(23)
    tones = ["#FFC4DD", "#FFFFFF", "#FFB0D2", "#FFD8E9"]

    def leg(f, i, j, w, h):
        if j > 3:
            return None
        if j == 3 and (i + (f == "back")) % 2:
            return None
        return tones[int(n(f, i, j) * 4)]
    bottom_base(t, leg, lambda f, i, j: "#FF7AB0" if j == 9 else tones[int(n("w", f, i, j) * 4)])


def mk_suitpants(t):
    bottom_base(t, lambda f, i, j, w, h: "#33334A" if (f == "front" and i == 1) else ("#15151C" if j == 11 else "#1C1C24"),
                belt("#101014", "#C5C5CE"))


def mk_rainbowleg(t):
    bottom_base(t, lambda f, i, j, w, h: RAINBOW[(j // 2) % 6], lambda f, i, j: RAINBOW[5] if j >= 10 else RAINBOW[4])


def mk_cargo(t):
    k, dk, lt = "#8D8455", "#6E663F", "#A49B6A"

    def leg(f, i, j, w, h):
        if f in ("right", "left") and 4 <= j <= 7:
            return dk if (j == 4 or i in (0, 3)) else lt
        return dk if j == 11 else k
    bottom_base(t, leg, belt("#4B4632", "#C5C5CE"))


def mk_shorts(t):
    n = noise(29)

    def leg(f, i, j, w, h):
        if j < 4:
            return "#6C95CC" if not (f == "front" and j == 1 and i == 1) else "#4E77AE"
        if j == 4:
            return "#E9F0FA" if n(f, i) < 0.6 else None
        return None
    bottom_base(t, leg, lambda f, i, j: "#6B4423" if j >= 10 else "#6C95CC")


def mk_sequins(t):
    n = noise(31)
    tones = ["#E8C15A", "#FFF1B0", "#C99A2E", "#F5D77A"]
    bottom_base(t, lambda f, i, j, w, h: tones[int(n(f, i, j) * 4)], lambda f, i, j: tones[int(n("w", f, i, j) * 4)])


def mk_gown(t):
    n = noise(37)

    def leg(f, i, j, w, h):
        if j == 11:
            return "#E8B84A"
        c = mix("#F9A8D4", "#E75A9A", j / 11)
        return "#FFFFFF" if n(f, i, j) < 0.06 else c
    bottom_base(t, leg, lambda f, i, j: "#E8B84A" if j == 9 else "#F9A8D4")


def mk_tartan(t):
    def tart(i, j):
        if j % 4 == 1 or i % 4 == 1:
            return "#1F4D2B" if (j % 4 == 1) != (i % 4 == 1) else "#111111"
        if i % 4 == 3:
            return "#F2D35B"
        return "#C62828"

    def leg(f, i, j, w, h):
        if j > 6:
            return None
        return "#6E1414" if j == 6 else tart(i + (2 if f in ("left", "right") else 0), j)
    bottom_base(t, leg, lambda f, i, j: "#111111" if j == 9 else tart(i, j))


BOTTOMS = [
    ("jeans", "Blue jeans", mk_jeans), ("ripped", "Ripped black jeans", mk_ripped), ("pleats", "Pink pleated skirt", mk_pleats),
    ("tutu", "Tutu skirt", mk_tutu), ("suitpants", "Suit trousers", mk_suitpants), ("rainbowleg", "Rainbow leggings", mk_rainbowleg),
    ("cargo", "Cargo trousers", mk_cargo), ("shorts", "Denim shorts", mk_shorts), ("sequins", "Gold sequin trousers", mk_sequins),
    ("gown", "Ball-gown skirt", mk_gown), ("tartan", "Tartan skirt", mk_tartan),
]


# ------------------------------------------------------------------ SHOES (humanoid layer, feet slot: legs, low rows)
def shoe_base(t, top_row, fn, sole):
    t.paint(LEG, lambda f, i, j, w, h: fn(f, i, j) if j >= top_row else None, faces=SIDES)
    t.paint(LEG, lambda f, i, j, w, h: sole, faces=("bottom",))


def mk_sneakers(t):
    shoe_base(t, 9, lambda f, i, j: "#D5D5DA" if j == 11 else ("#FF4FA0" if (f in ("left", "right") and j == 10 and i in (1, 2)) else
              ("#BDBDC6" if (f == "front" and j == 9 and i in (1, 2)) else "#FAFAFA")), "#C8C8CE")


def mk_boots(t):
    shoe_base(t, 6, lambda f, i, j: "#3A3A40" if j == 11 else ("#C5C5CE" if (f in ("left", "right") and j == 8 and i in (1, 2)) else
              ("#2E2E36" if (i + j) % 5 == 0 else "#1E1E22")), "#3A3A40")


def mk_heels(t):
    shoe_base(t, 10, lambda f, i, j: ("#FF9CCB" if (f == "front" and j == 10) else ("#B8336A" if (f == "back" and j == 11 and i in (1, 2)) else "#FF4FA0")),
              "#B8336A")


def mk_cowboy(t):
    shoe_base(t, 5, lambda f, i, j: "#3B2415" if j == 11 else ("#D6A26B" if j == 5 or (f in ("front", "back") and (i + j) % 4 == 0 and j < 10) else "#A0663A"),
              "#3B2415")


def mk_rainbowshoe(t):
    shoe_base(t, 9, lambda f, i, j: "#FAFAFA" if j == 11 else RAINBOW[(i + (4 if f in ("left", "right") else 0) + j) % 6], "#FAFAFA")


def mk_goldshoe(t):
    n = noise(41)
    tones = ["#E8C15A", "#FFF1B0", "#C99A2E"]
    shoe_base(t, 9, lambda f, i, j: "#8C6A1C" if j == 11 else tones[int(n(f, i, j) * 3)], "#8C6A1C")


def mk_slippers(t):
    n = noise(43)
    tones = ["#D9C2F0", "#FFFFFF", "#E8D8FA", "#C9ACEB"]
    shoe_base(t, 9, lambda f, i, j: tones[int(n(f, i, j) * 4)] if not (f == "front" and j == 9 and i in (1, 2)) else "#FF7AC6", "#B79AD9")


def mk_redhigh(t):
    shoe_base(t, 8, lambda f, i, j: "#FAFAFA" if j == 11 or (f == "front" and j == 10) else
              ("#FAFAFA" if (f == "front" and j in (8, 9) and i in (1, 2)) else "#D32F2F"), "#E6E6E6")


SHOES = [
    ("sneakers", "White sneakers", mk_sneakers), ("boots", "Black boots", mk_boots), ("heels", "Pink heels", mk_heels),
    ("cowboy", "Cowboy boots", mk_cowboy), ("rainbowshoe", "Rainbow shoes", mk_rainbowshoe), ("goldshoe", "Gold shoes", mk_goldshoe),
    ("slippers", "Fluffy slippers", mk_slippers), ("redhigh", "Red high-tops", mk_redhigh),
]


# ------------------------------------------------------------------ WIGS (helmet texture: head box, face left open)
def wig(t, col_fn, side_rows, back_rows, fringe):
    def fn(f, i, j, w, h):
        if f == "top":
            return col_fn(f, i, j)
        if f == "front":
            if j < fringe or (i in (0, 7) and j < side_rows):
                return col_fn(f, i, j)
            return None
        if f in ("left", "right"):
            return col_fn(f, i, j) if j < side_rows else None
        if f == "back":
            return col_fn(f, i, j) if j < back_rows else None
    t.paint(HEAD, fn, faces=("front", "back", "right", "left", "top"))


def strands(base, dark, seed):
    n = noise(seed)
    return lambda f, i, j: dark if n(f, i) < 0.3 and j % 3 != 0 else (shade(base, 1.08) if n(f, i, j) < 0.1 else base)


def mk_wig_pink(t):
    wig(t, strands("#F7A1C4", "#E27FAA", 51), 8, 8, 2)


def mk_wig_bob(t):
    wig(t, strands("#5FA8E8", "#3F86C8", 53), 6, 6, 3)


def mk_wig_rainbow(t):
    wig(t, lambda f, i, j: RAINBOW[(i if f in ("front", "back", "top") else j) % 6], 7, 8, 2)


def mk_wig_blonde(t):
    wig(t, strands("#F2D07A", "#D9B25A", 57), 7, 8, 2)


# ------------------------------------------------------------------ WINGS (elytra box at (22,0) 10x20x2: the back face)
def wing_mask(kind):
    m = [[False] * 10 for _ in range(20)]
    for j in range(20):
        for i in range(10):
            if kind == "angel":
                taper = max(0, (j - 8) // 2)      # like vanilla: full width on top, tapering at the bottom
                ok = i >= taper and not (j == 0 and i in (0, 9))
            elif kind in ("fairy", "butterfly"):
                up = ((i - 4.5) / 5.0) ** 2 + ((j - 6) / 6.5) ** 2 <= 1
                lo = ((i - 4.5) / 4.0) ** 2 + ((j - 15) / 4.6) ** 2 <= 1
                ok = up or lo
            elif kind == "bat":
                scallop = j >= 16 and ((i % 4) - 1.5) ** 2 + (j - 19.5) ** 2 < 4.2
                ok = (i >= max(0, (j - 10) // 2)) and not scallop and not (j == 0 and i > 6)
            else:  # rainbow: rounded rectangle
                ok = not ((i in (0, 9)) and (j in (0, 19))) and not (j > 16 and i < j - 16)
            m[j][i] = ok
    return m


def mk_wings(t, kind):
    m = wing_mask(kind)
    n = noise(61)
    x0, y0 = 36, 2

    def edge(i, j):
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ii, jj = i + di, j + dj
            if not (0 <= ii < 10 and 0 <= jj < 20) or not m[jj][ii]:
                return True
        return False
    for j in range(20):
        for i in range(10):
            if not m[j][i]:
                continue
            e = edge(i, j)
            if kind == "angel":
                c = "#C9CFDD" if e else ("#DDE2EE" if j % 4 == 3 else ("#FFFFFF" if n(i, j) > 0.15 else "#F1F3F9"))
            elif kind == "fairy":
                c = mix(mix("#FFB3D9", "#C9A7FF", j / 19), "#9FE8F5", i / 18)
                if e:
                    c = "#B388EB"
                elif i == 4 or (j in (6, 15) and i % 2 == 0):
                    c = shade(c, 0.9)
                elif n(i, j) < 0.07:
                    c = "#FFFFFF"
            elif kind == "butterfly":
                c = "#1B1B1B" if e or i == 4 or j == 11 else "#F59A23"
                if e and n(i, j) < 0.35:
                    c = "#FFFFFF"
                if not e and ((i + j) % 7 == 0):
                    c = "#FFC04D"
            elif kind == "bat":
                c = "#2A1638" if e else ("#5A3470" if (i - j // 2) % 4 == 0 else "#3A1F4A")
            else:
                c = "#FFFFFF" if e else RAINBOW[min(5, j * 6 // 20)]
            t.put(x0 + i, y0 + j, c)
            t.put(24 + (9 - i), y0 + j, c)       # the front face too (mirrored), so the wing reads from both sides


WINGS = [("angel", "Angel wings"), ("fairy", "Fairy wings"), ("butterfly", "Butterfly wings"), ("bat", "Bat wings"),
         ("rainbowwing", "Rainbow wings")]


# ------------------------------------------------------------------ 3D HATS (item models on the head)
PALETTE = []


def pal(c):
    c = hexc(c)
    if c not in PALETTE:
        PALETTE.append(c)
    k = PALETTE.index(c)
    return (k % 16, k // 16)


def hp(v):
    return round(1.6 + 1.6 * v, 3)


class Hat:
    def __init__(self):
        self.el = []

    def box(self, x0, y0, z0, x1, y1, z1, col, rot=None):
        """Head-pixel coords: x 0..8 (mirrored in game), y 0 chin .. 8 top, z 0 face .. 8 back of the head."""
        u, v = pal(col)
        faces = {k: {"texture": "#p", "uv": [u + 0.25, v + 0.25, u + 0.75, v + 0.75]} for k in
                 ("north", "south", "east", "west", "up", "down")}
        e = {"from": [hp(x0), hp(y0), hp(z0)], "to": [hp(x1), hp(y1), hp(z1)], "faces": faces}
        if rot:
            axis, ang, org = rot
            e["rotation"] = {"axis": axis, "angle": ang, "origin": [hp(org[0]), hp(org[1]), hp(org[2])]}
        self.el.append(e)
        return self


def hat_crown():
    h, g, dg = Hat(), "#F6C945", "#D9A520"
    for (a, b, c, d) in ((0, 0, 8, 0.5), (0, 7.5, 8, 8), (0, 0, 0.5, 8), (7.5, 0, 8, 8)):
        h.box(a - 0.2, 8, b - 0.2, c + 0.2, 9.6, d + 0.2, g)
    for p in (0, 2.5, 5.5, 7.5):          # spikes on each side
        for (x0, z0) in ((p - 0.2, -0.2), (p - 0.2, 7.5), (-0.2, p - 0.2), (7.5, p - 0.2)):
            h.box(x0, 9.6, z0, x0 + 0.9, 11, z0 + 0.9 if z0 in (-0.2, 7.5) else z0 + 0.9, dg)
    h.box(3.4, 8.4, -0.45, 4.6, 9.2, -0.2, "#D81B60")
    h.box(1.2, 8.5, -0.4, 2.0, 9.1, -0.2, "#1E88E5")
    h.box(6.0, 8.5, -0.4, 6.8, 9.1, -0.2, "#1E88E5")
    return h


def hat_cat():
    h = Hat()
    h.box(0, 8, 3.2, 8, 8.4, 4.2, "#FF7AC6")          # headband
    for x in (0.4, 5.2):
        h.box(x, 8.4, 3.2, x + 2.4, 9.4, 4.2, "#FF7AC6")
        h.box(x + 0.4, 9.4, 3.2, x + 2.0, 10.4, 4.2, "#FF7AC6")
        h.box(x + 0.8, 10.4, 3.2, x + 1.6, 11.2, 4.2, "#FF7AC6")
        h.box(x + 0.6, 8.4, 3.05, x + 1.8, 9.8, 3.2, "#FFD1E8")
    return h


def hat_bunny():
    h = Hat()
    h.box(0, 8, 3.2, 8, 8.4, 4.2, "#FFFFFF")
    h.box(1.4, 8.4, 3.3, 3.0, 13.2, 4.1, "#FFFFFF")
    h.box(1.8, 8.8, 3.15, 2.6, 12.6, 3.3, "#FFB0D2")
    h.box(5.0, 8.4, 3.3, 6.6, 12.4, 4.1, "#FFFFFF", ("z", -22.5, (5.8, 8.4, 3.7)))
    h.box(5.4, 8.8, 3.15, 6.2, 11.8, 3.3, "#FFB0D2", ("z", -22.5, (5.8, 8.4, 3.7)))
    return h


def hat_tophat():
    h = Hat()
    h.box(-1.2, 8, -1.2, 9.2, 8.5, 9.2, "#1B1B22")
    h.box(1.0, 8.5, 1.0, 7.0, 13.5, 7.0, "#1B1B22")
    h.box(0.9, 8.5, 0.9, 7.1, 9.6, 7.1, "#FF4FA0")
    h.box(5.6, 9.0, 0.7, 6.6, 10.0, 0.9, "#FFFFFF")
    return h


def hat_flowers():
    h = Hat()
    cols = ["#FF7AC6", "#FFFFFF", "#FFE066", "#C9A7FF", "#FF5C8A"]
    ring = [(x, -0.3) for x in (0.2, 2.2, 4.2, 6.2)] + [(8.3 - 0.9, z) for z in (1.6, 3.6, 5.6)] + \
           [(x, 8.3 - 0.9) for x in (6.2, 4.2, 2.2, 0.2)] + [(-0.3, z) for z in (5.6, 3.6, 1.6)]
    for k, (x, z) in enumerate(ring):
        h.box(x, 7.7, z, x + 1.4, 8.9, z + 1.4 if z < 7 else z + 1.2, cols[k % len(cols)])
        h.box(x + 0.45, 8.9, z + 0.45 if z > 0 else z + 0.3, x + 0.95, 9.1, z + 0.95, "#FFD23F")
    for (x, z) in ((1.6, -0.25), (5.6, -0.25), (-0.25, 4.6), (7.9, 2.6)):
        h.box(x, 7.8, z, x + 0.6, 8.4, z + 0.5, "#43A047")
    return h


def hat_halo():
    h = Hat()
    for (a, b, c, d) in ((1, 1, 7, 1.6), (1, 6.4, 7, 7), (1, 1, 1.6, 7), (6.4, 1, 7, 7)):
        h.box(a, 10.2, b, c, 10.7, d, "#FFE066")
    return h


def hat_bow():
    h = Hat()
    h.box(3.4, 8.0, 5.0, 4.6, 9.2, 6.2, "#C2185B")
    h.box(0.8, 7.9, 5.3, 3.4, 9.9, 5.9, "#FF4FA0")
    h.box(4.6, 7.9, 5.3, 7.2, 9.9, 5.9, "#FF4FA0")
    h.box(1.4, 8.3, 5.9, 2.8, 9.5, 6.0, "#FF8CC6")
    h.box(5.2, 8.3, 5.9, 6.6, 9.5, 6.0, "#FF8CC6")
    return h


def hat_cowboy():
    h = Hat()
    h.box(-1.6, 8, -1.6, 9.6, 8.5, 9.6, "#FF7AC6")
    h.box(-1.6, 8.5, -1.6, -0.8, 9.4, 9.6, "#FF7AC6")
    h.box(8.8, 8.5, -1.6, 9.6, 9.4, 9.6, "#FF7AC6")
    h.box(1.0, 8.5, 1.0, 7.0, 11.2, 7.0, "#FF7AC6")
    h.box(0.9, 8.5, 0.9, 7.1, 9.2, 7.1, "#FFFFFF")
    h.box(3.6, 10.8, 1.0, 4.4, 11.2, 7.0, "#E0609F")
    return h


def hat_beanie():
    h = Hat()
    h.box(-0.3, 6.2, -0.3, 8.3, 9.0, 8.3, "#8E4FD6")
    h.box(-0.4, 6.2, -0.4, 8.4, 7.2, 8.4, "#7A3CC0")
    h.box(0.8, 9.0, 0.8, 7.2, 9.4, 7.2, "#8E4FD6")
    h.box(3.0, 9.4, 3.0, 5.0, 11.0, 5.0, "#FFB0D2")
    return h


def hat_shades():
    h = Hat()
    for x in (0.4, 4.6):
        h.box(x, 3.2, -0.5, x + 3.0, 4.8, -0.2, "#FF2E7A")
        h.box(x + 0.2, 4.8, -0.5, x + 1.3, 5.3, -0.2, "#FF2E7A")
        h.box(x + 1.7, 4.8, -0.5, x + 2.8, 5.3, -0.2, "#FF2E7A")
        h.box(x + 0.9, 2.7, -0.5, x + 2.1, 3.2, -0.2, "#FF2E7A")
    h.box(3.4, 4.3, -0.45, 4.6, 4.6, -0.2, "#222222")
    h.box(-0.35, 4.2, -0.3, -0.05, 4.6, 5.0, "#222222")
    h.box(8.05, 4.2, -0.3, 8.35, 4.6, 5.0, "#222222")
    return h


def hat_headphones():
    h = Hat()
    h.box(-0.6, 8.0, 3.4, 8.6, 8.7, 4.6, "#F7F7F7")
    h.box(-0.6, 5.0, 3.4, -0.1, 8.0, 4.6, "#F7F7F7")
    h.box(8.1, 5.0, 3.4, 8.6, 8.0, 4.6, "#F7F7F7")
    h.box(-1.3, 2.4, 2.4, -0.1, 5.4, 5.6, "#FF4FA0")
    h.box(8.1, 2.4, 2.4, 9.3, 5.4, 5.6, "#FF4FA0")
    return h


def hat_party():
    h = Hat()
    cols = ["#FF4FA0", "#FFE066", "#5BCEFA", "#FF4FA0", "#FFE066"]
    for k in range(5):
        s = 2.4 - k * 0.45
        h.box(4 - s, 8 + k * 0.9, 4 - s, 4 + s, 8.9 + k * 0.9, 4 + s, cols[k])
    h.box(3.5, 12.5, 3.5, 4.5, 13.4, 4.5, "#FFFFFF")
    return h


def hat_horns():
    h = Hat()
    for x in (1.0, 5.6):
        h.box(x, 8.0, 2.2, x + 1.4, 9.0, 3.6, "#D32F2F")
        h.box(x + 0.25, 9.0, 2.4, x + 1.15, 10.0, 3.4, "#C62828")
        h.box(x + 0.45, 10.0, 2.6, x + 0.95, 10.8, 3.1, "#8E0000")
    return h


def hat_unicorn():
    h = Hat()
    cols = ["#FFE066", "#FFFFFF", "#FFE066", "#FFFFFF", "#FFE066"]
    for k in range(5):
        s = 0.75 - k * 0.12
        h.box(4 - s, 8 + k * 0.8, 1.1 - s, 4 + s, 8.8 + k * 0.8, 1.1 + s, cols[k], ("x", 22.5, (4, 8, 1.1)))
    for k, c in enumerate(["#FF7AC6", "#C9A7FF", "#5BCEFA"]):
        h.box(3.2 + k * 0.5, 7.9, 1.8 + k * 1.6, 4.8 - k * 0.5 + 1, 8.6, 3.2 + k * 1.6, c)
    return h


def hat_cap():
    h = Hat()
    h.box(-0.3, 7.0, -0.3, 8.3, 8.8, 8.3, "#FF4FA0")
    h.box(0.6, 8.8, 0.6, 7.4, 9.1, 7.4, "#FF4FA0")
    h.box(0.4, 7.0, -3.2, 7.6, 7.35, -0.3, "#C2185B")
    h.box(3.6, 9.1, 3.6, 4.4, 9.4, 4.4, "#FFFFFF")
    return h


HATS = [("crown", "Gold crown", hat_crown), ("cat", "Cat ears", hat_cat), ("bunny", "Bunny ears", hat_bunny),
        ("tophat", "Top hat", hat_tophat), ("flowers", "Flower crown", hat_flowers), ("halo", "Halo", hat_halo),
        ("bow", "Giant bow", hat_bow), ("cowboy", "Pink cowboy hat", hat_cowboy), ("beanie", "Beanie", hat_beanie),
        ("shades", "Heart shades", hat_shades), ("headphones", "Headphones", hat_headphones), ("party", "Party hat", hat_party),
        ("horns", "Little horns", hat_horns), ("unicorn", "Unicorn horn", hat_unicorn), ("cap", "Baseball cap", hat_cap)]
WIGS = [("wig_pink", "Long pink wig", mk_wig_pink), ("wig_bob", "Blue bob wig", mk_wig_bob),
        ("wig_rainbow", "Rainbow wig", mk_wig_rainbow), ("wig_blonde", "Blonde wig", mk_wig_blonde)]


# ------------------------------------------------------------------ the fitting dummy (64x64 player skin)
def dummy_skin():
    im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    t = Tex(64, 64)
    t.im, t.px = im, im.load()
    base, joint = "#EFE3D3", "#D9C8B2"
    n = noise(71)

    def f(face, i, j, w, h):
        return joint if (h == 12 and j in (0, 11)) else (base if n(face, i, j) > 0.1 else shade(base, 0.97))
    for box in ((0, 0, 8, 8, 8), (16, 16, 8, 12, 4), (40, 16, 4, 12, 4), (32, 48, 4, 12, 4), (0, 16, 4, 12, 4), (16, 48, 4, 12, 4)):
        t.paint(box, f, faces=("front", "back", "right", "left", "top", "bottom"), shaded=False)
    for (x, y) in ((10, 12), (13, 12)):
        t.put(x, y, "#6B5A48")
    t.put(11, 14, "#C9A48F"); t.put(12, 14, "#C9A48F")
    t.put(9, 13, "#F2C2C2"); t.put(14, 13, "#F2C2C2")
    return im


# ------------------------------------------------------------------ writing the pack
def wjson(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(obj, open(path, "w"), ensure_ascii=False, indent=1)


def save_tex(img, layer, name):
    p = os.path.join(A, "textures", "entity", "equipment", layer, name + ".png")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    img.save(p)


def icon_from(img, kind):
    """A 16x16 inventory icon cut from the texture's front faces."""
    ic = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    fb, fa, fl = faces_of(BODY)["front"], faces_of(ARM)["front"], faces_of(LEG)["front"]
    crop = lambda r: img.crop((r[0], r[1], r[0] + r[2], r[1] + r[3]))
    if kind == "top":
        ic.paste(crop(fb), (4, 2), crop(fb))
        a = crop(fa)
        ic.paste(a, (0, 2), a); ic.paste(a.transpose(Image.FLIP_LEFT_RIGHT), (12, 2), a.transpose(Image.FLIP_LEFT_RIGHT))
    elif kind == "legs":
        w = crop((fb[0], fb[1] + 9, 8, 3)); ic.paste(w, (4, 1), w)
        l = crop(fl); ic.paste(l, (4, 4), l); ic.paste(l.transpose(Image.FLIP_LEFT_RIGHT), (8, 4), l.transpose(Image.FLIP_LEFT_RIGHT))
    elif kind == "feet":
        l = crop((fl[0], fl[1] + 5, 4, 7))
        ic.paste(l, (3, 6), l); ic.paste(l, (9, 6), l)
    elif kind == "wig":
        f = faces_of(HEAD)
        top = crop(f["back"]); ic.paste(top.resize((12, 12), Image.NEAREST), (2, 2), top.resize((12, 12), Image.NEAREST))
        fr = crop(f["front"]).resize((12, 12), Image.NEAREST); ic.paste(fr, (2, 2), fr)
    elif kind == "wings":
        wg = img.crop((36, 2, 46, 22)).resize((7, 14), Image.NEAREST)
        ic.paste(wg, (1, 1), wg); ic.paste(wg.transpose(Image.FLIP_LEFT_RIGHT), (8, 1), wg.transpose(Image.FLIP_LEFT_RIGHT))
    return ic


def item_icon(name, img):
    p = os.path.join(A, "textures", "item", name + ".png")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    img.save(p)
    wjson(os.path.join(A, "models", "item", name + ".json"),
          {"parent": "minecraft:item/generated", "textures": {"layer0": f"{NS}:item/{name}"}})
    wjson(os.path.join(A, "items", name + ".json"), {"model": {"type": "minecraft:model", "model": f"{NS}:item/{name}"}})


def snbt_name(name):
    return '{text:"%s",color:"#FF7AC6",italic:false}' % name.replace('"', '\\"')


# custom_data studio_outfit marks the piece as a studio outfit: residents.sc only ever replaces / removes pieces that
# carry it, so a player's real armour is never touched. attribute_modifiers=[] = no armour points (it's clothing).
LORE = '[{text:"Character studio",color:"gray",italic:false}]'
COMMON = 'custom_data={studio_outfit:1b},enchantment_glint_override=false,attribute_modifiers=[],lore=%s' % LORE


def item_str(base, slot, asset, model, name, sound="item.armor.equip_leather"):
    """The /item-command string of one piece. asset=None (hats) -> no asset_id -> the item model is drawn on the head."""
    eq = 'equippable={slot:"%s",equip_sound:"%s"%s}' % (slot, sound, (',asset_id:"%s:%s"' % (NS, asset)) if asset else "")
    return '%s[%s,item_model="%s:%s",custom_name=%s,%s]' % (base, eq, NS, model, snbt_name(name), COMMON)


def build():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(A)
    cat = {"_doc": "generated by resourcepacks/wardrobe/gen_wardrobe_pack.py -- do not edit by hand. rows = the fitting "
                   "wall's rows (item 0 = none); chest = '<top>|<wings>' -> one chest item carrying both layers",
           "rows": [], "chest": {}}
    tex = {}

    # tops
    for tid, nm, fn in TOPS:
        t = Tex(); fn(t); tex["top_" + tid] = t.im
        save_tex(t.im, "humanoid", "top_" + tid)
        item_icon("icon_top_" + tid, icon_from(t.im, "top"))
    # wings
    for wid, nm in WINGS:
        t = Tex(); mk_wings(t, wid.replace("rainbowwing", "rainbow")); tex["wings_" + wid] = t.im
        save_tex(t.im, "wings", "wings_" + wid)
        item_icon("icon_wings_" + wid, icon_from(t.im, "wings"))
        wjson(os.path.join(A, "equipment", "wings_" + wid + ".json"), {"layers": {"wings": [{"texture": f"{NS}:wings_{wid}"}]}})
    for tid, nm, fn in TOPS:
        wjson(os.path.join(A, "equipment", "top_" + tid + ".json"), {"layers": {"humanoid": [{"texture": f"{NS}:top_{tid}"}]}})
        cat["chest"][tid + "|none"] = item_str("leather_chestplate", "chest", "top_" + tid, "icon_top_" + tid, nm)
        for wid, wnm in WINGS:
            aid = f"top_{tid}__{wid}"
            wjson(os.path.join(A, "equipment", aid + ".json"),
                  {"layers": {"humanoid": [{"texture": f"{NS}:top_{tid}"}], "wings": [{"texture": f"{NS}:wings_{wid}"}]}})
            cat["chest"][tid + "|" + wid] = item_str("leather_chestplate", "chest", aid, "icon_top_" + tid, nm + " + " + wnm)
    for wid, wnm in WINGS:
        cat["chest"]["none|" + wid] = item_str("leather_chestplate", "chest", "wings_" + wid, "icon_wings_" + wid, wnm)
    # bottoms
    for bid, nm, fn in BOTTOMS:
        t = Tex(); fn(t); tex["legs_" + bid] = t.im
        save_tex(t.im, "humanoid_leggings", "legs_" + bid)
        wjson(os.path.join(A, "equipment", "legs_" + bid + ".json"), {"layers": {"humanoid_leggings": [{"texture": f"{NS}:legs_{bid}"}]}})
        item_icon("icon_legs_" + bid, icon_from(t.im, "legs"))
    # shoes
    for sid, nm, fn in SHOES:
        t = Tex(); fn(t); tex["feet_" + sid] = t.im
        save_tex(t.im, "humanoid", "feet_" + sid)
        wjson(os.path.join(A, "equipment", "feet_" + sid + ".json"), {"layers": {"humanoid": [{"texture": f"{NS}:feet_{sid}"}]}})
        item_icon("icon_feet_" + sid, icon_from(t.im, "feet"))
    # wigs
    for gid, nm, fn in WIGS:
        t = Tex(); fn(t); tex[gid] = t.im
        save_tex(t.im, "humanoid", gid)
        wjson(os.path.join(A, "equipment", gid + ".json"), {"layers": {"humanoid": [{"texture": f"{NS}:{gid}"}]}})
        item_icon("icon_" + gid, icon_from(t.im, "wig"))
    # 3D hats
    hat_models = {}
    for hid, nm, fn in HATS:
        hat_models[hid] = fn()
    ptex = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    for k, c in enumerate(PALETTE):
        ptex.putpixel((k % 16, k // 16), c)
    assert len(PALETTE) <= 256
    os.makedirs(os.path.join(A, "textures", "item"), exist_ok=True)
    ptex.save(os.path.join(A, "textures", "item", "hat_palette.png"))
    for hid, h in hat_models.items():
        for e in h.el:
            for v in e["from"] + e["to"]:
                assert -16 <= v <= 32, (hid, e)
        wjson(os.path.join(A, "models", "item", "hat_" + hid + ".json"), {
            "textures": {"p": f"{NS}:item/hat_palette", "particle": f"{NS}:item/hat_palette"},
            "elements": h.el,
            "display": {
                "head": {"rotation": [0, 0, 0], "translation": [0, 0, 0], "scale": [1, 1, 1]},
                "gui": {"rotation": [25, 145, 0], "translation": [0, -5.5, 0], "scale": [0.7, 0.7, 0.7]},
                "ground": {"translation": [0, -2, 0], "scale": [0.4, 0.4, 0.4]},
                "fixed": {"translation": [0, -5, 0], "scale": [0.7, 0.7, 0.7]},
                "thirdperson_righthand": {"rotation": [0, 45, 0], "translation": [0, -3, 2], "scale": [0.4, 0.4, 0.4]},
                "firstperson_righthand": {"rotation": [0, 45, 0], "translation": [0, -2, 0], "scale": [0.4, 0.4, 0.4]}}})
        wjson(os.path.join(A, "items", "hat_" + hid + ".json"), {"model": {"type": "minecraft:model", "model": f"{NS}:item/hat_{hid}"}})
    # dummy mannequin skin
    p = os.path.join(A, "textures", "entity", "dummy.png")
    dummy_skin().save(p)

    none = {"id": "none", "name": "None"}
    head = [none] + [{"id": hid, "name": nm, "item": item_str("leather_helmet", "head", None, "hat_" + hid, nm)} for hid, nm, _ in HATS] + \
           [{"id": gid, "name": nm, "item": item_str("leather_helmet", "head", gid, "icon_" + gid, nm)} for gid, nm, _ in WIGS]
    cat["rows"] = [
        {"key": "head", "slot": "head", "name": "Hats & wigs", "items": head},
        {"key": "wings", "slot": "chest", "name": "Wings", "items": [none] + [{"id": w, "name": nm} for w, nm in WINGS]},
        {"key": "top", "slot": "chest", "name": "Tops", "items": [none] + [{"id": t, "name": nm} for t, nm, _ in TOPS]},
        {"key": "legs", "slot": "legs", "name": "Trousers & skirts", "items": [none] + [
            {"id": b, "name": nm, "item": item_str("leather_leggings", "legs", "legs_" + b, "icon_legs_" + b, nm)} for b, nm, _ in BOTTOMS]},
        {"key": "feet", "slot": "feet", "name": "Shoes", "items": [none] + [
            {"id": s, "name": nm, "item": item_str("leather_boots", "feet", "feet_" + s, "icon_feet_" + s, nm)} for s, nm, _ in SHOES]},
    ]
    wjson(os.path.abspath(CATALOG), cat)

    json.dump({"pack": {"description": "Pink Golem wardrobe: real clothes, hats and wings", "min_format": 88, "max_format": 88}},
              open(os.path.join(OUT, "pack.mcmeta"), "w"))
    zpath = ZIP
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for d, _, fs in os.walk(OUT):
            for f in sorted(fs):
                z.write(os.path.join(d, f), os.path.relpath(os.path.join(d, f), OUT))
    return zpath, tex


# ------------------------------------------------------------------ preview: every piece on the dummy (front + back)
def compose(skin, layers, back=False, wings=None):
    """2D front (or back) view at 1 px per texel: head 8x8, body 8x12, arms 4x12, legs 4x12 -> 16x32 (+ wings)."""
    im = Image.new("RGBA", (16, 32), (0, 0, 0, 0))
    k = "back" if back else "front"

    def blit(src, box, x, y):
        f = faces_of(box)[k]
        c = src.crop((f[0], f[1], f[0] + f[2], f[1] + f[3]))
        if back:
            c = c.transpose(Image.FLIP_LEFT_RIGHT)
        im.alpha_composite(c, (x, y))
    sk = {"head": (0, 0, 8, 8, 8), "body": (16, 16, 8, 12, 4), "arm": (40, 16, 4, 12, 4), "leg": (0, 16, 4, 12, 4)}
    blit(skin, sk["head"], 4, 0); blit(skin, sk["body"], 4, 8)
    blit(skin, sk["arm"], 0, 8); blit(skin, sk["arm"], 12, 8)
    blit(skin, sk["leg"], 4, 20); blit(skin, sk["leg"], 8, 20)
    for (lim, parts) in layers:
        if "head" in parts:
            blit(lim, HEAD, 4, 0)
        if "body" in parts:
            blit(lim, BODY, 4, 8)
        if "arm" in parts:
            blit(lim, ARM, 0, 8); blit(lim, ARM, 12, 8)
        if "leg" in parts:
            blit(lim, LEG, 4, 20); blit(lim, LEG, 8, 20)
    if back and wings is not None:
        w = wings.crop((36, 2, 46, 22))
        big = Image.new("RGBA", (28, 32), (0, 0, 0, 0))
        big.alpha_composite(w.transpose(Image.FLIP_LEFT_RIGHT), (0, 7)); big.alpha_composite(w, (18, 7))
        big.alpha_composite(im, (6, 0))
        return big
    return im


def preview(tex):
    dummy = dummy_skin()
    looks = []
    for tid, nm, _ in TOPS:
        looks.append((nm, [(tex["top_" + tid], ("body", "arm"))], None))
    for bid, nm, _ in BOTTOMS:
        looks.append((nm, [(tex["legs_" + bid], ("body", "leg"))], None))
    for sid, nm, _ in SHOES:
        looks.append((nm, [(tex["feet_" + sid], ("leg",))], None))
    for gid, nm, _ in WIGS:
        looks.append((nm, [(tex[gid], ("head",))], None))
    for wid, nm in WINGS:
        looks.append((nm, [], tex["wings_" + wid]))
    S, cols = 6, 8
    cw, ch = 30 * S + 24, 34 * S + 30
    rows = (len(looks) + cols - 1) // cols
    sheet = Image.new("RGBA", (cols * cw, rows * ch), (246, 240, 244, 255))
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 13)
    except Exception:
        font = ImageFont.load_default()
    for k, (nm, layers, wings) in enumerate(looks):
        x, y = (k % cols) * cw, (k // cols) * ch
        fr = compose(dummy, layers).resize((16 * S // 2, 32 * S // 2), Image.NEAREST)
        bk = compose(dummy, layers, back=True, wings=wings)
        bk = bk.resize((bk.width * S // 2, 32 * S // 2), Image.NEAREST)
        sheet.alpha_composite(fr, (x + 8, y + 8))
        sheet.alpha_composite(bk, (x + 16 + fr.width, y + 8))
        d.text((x + 8, y + ch - 20), nm, fill=(80, 40, 70, 255), font=font)
    os.makedirs(PREV, exist_ok=True)
    out = os.path.join(PREV, "wardrobe_sheet.png")
    sheet.save(out)
    return out


if __name__ == "__main__":
    zpath, tex = build()
    sheet = preview(tex)
    hats = [f"{NS}:item/hat_{h}" for h, _, _ in HATS]
    if os.path.isfile(MODEL_PREVIEW):          # the 3D hats, rendered without a game client
        for part, ids in (("1", hats[:8]), ("2", hats[8:])):
            subprocess.run([sys.executable, MODEL_PREVIEW, OUT] + ids +
                           ["--out", os.path.join(PREV, "wardrobe_hats_%s.png" % part), "--yaw", "65", "--pitch", "20",
                            "--gap", "26", "--size", "1400x420"], check=False)
    else:
        print("resourcepacks/tools/model_preview.py not found -- skipping the hat renders", file=sys.stderr)
    print(json.dumps({"zip": zpath, "zip_kb": os.path.getsize(zpath) // 1024, "sheet": sheet,
                      "counts": {"tops": len(TOPS), "bottoms": len(BOTTOMS), "shoes": len(SHOES), "hats": len(HATS),
                                 "wigs": len(WIGS), "wings": len(WINGS)}, "palette": len(PALETTE)}, ensure_ascii=False))
