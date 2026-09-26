"""gen_planes_pack.py — Air Bulbul aircraft models for the server resource pack (v3, Claude 27/9; replaces Gemini's v2).

Models (item_display models, 1 unit = scale/16 blocks; the app scales them 5-7.5×):
  planes:fighter      Bulbul Raptor — stepped nose, canopy, intakes, swept delta wings, twin fins, nozzle
  planes:private_jet  Gulfstream-style VIP jet — octagonal fuselage, window strip, pink cheatline, T-tail, rear engines
  planes:b737         Air Bulbul 737 — octagonal fuselage, window strip, cyan cheatline, pink fin with the logo,
                      under-wing turbofans with fan faces, winglets
  planes:helicopter   VIP helicopter — glass bubble, cabin, skids, tail boom, fin, tail rotor (the main rotor is
                      planes:rotor, a separate item_display the app spins)
  planes:rotor        two crossed blades + hub

Conventions (verified on the coaster, 26/9): an item_display draws the model turned 180° about y, so the NOSE is at
model -z and ends up at local +z = the display's forward. The fuselage axis is at model y = 8 and x = 8, so the app's
left_rotation (yaw · pitch · roll) turns the aircraft about its own axis; the app lifts the model by (8 − lowest y)/16
× scale so the wheels sit on the entity's y. Every face carries an explicit uv (parts outside 0..16 render black
with the default uv — Gabi Water lesson). Body faces are tinted (tintindex 0 → dyed_color); livery accents are
separate untinted boxes. Textures are drawn here with PIL (32×32).

Run: python3 gen_planes_pack.py → mcp-server/jobs/planes_pack/ + planes_pack.zip + previews/planes_preview.png
"""
import json
import os
import shutil
import subprocess
import sys
import zipfile

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "planes_pack")
NS = "planes"

WHITE = (244, 244, 246, 255)
PINK = (255, 105, 180, 255)
PINK_D = (226, 72, 150, 255)
CYAN = (53, 208, 224, 255)
CYAN_D = (30, 160, 176, 255)
DARK = (28, 30, 36, 255)
GREY = (120, 124, 132, 255)
GREY_D = (78, 82, 90, 255)
NAVY = (22, 34, 60, 255)
GLASS_HI = (150, 190, 230, 255)


# ─────────────────────────────── textures ───────────────────────────────
def solid(rgba, w=32, h=32):
    return Image.new("RGBA", (w, h), rgba)


def tex_body():
    """White skin with faint panel lines (tinted by dyed_color in game)."""
    im = solid(WHITE)
    d = ImageDraw.Draw(im)
    for y in (10, 21):
        d.line([(0, y), (31, y)], fill=(228, 228, 232, 255))
    for x in (7, 15, 23):
        d.line([(x, 0), (x, 31)], fill=(232, 232, 236, 255))
    return im


def tex_windows():
    """A row of cabin windows on a transparent strip (an overlay 0.05 outside the fuselage, side faces only)."""
    im = Image.new("RGBA", (64, 16), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for i in range(10):
        x = 3 + i * 6
        d.rounded_rectangle([x, 5, x + 3, 10], radius=1, fill=NAVY)
        d.point((x + 1, 6), fill=GLASS_HI)
    return im


def tex_cockpit():
    im = solid(NAVY)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 31, 31], outline=DARK)
    d.line([(2, 6), (29, 6)], fill=GLASS_HI)
    d.line([(2, 8), (16, 8)], fill=(90, 130, 180, 255))
    return im


def tex_fin():
    """Pink fin with the white Air Bulbul swoosh + a bird dot."""
    im = solid(PINK)
    d = ImageDraw.Draw(im)
    d.arc([2, 4, 40, 44], start=200, end=290, fill=WHITE, width=4)
    d.ellipse([20, 6, 27, 13], fill=WHITE)
    d.polygon([(26, 9), (31, 7), (27, 11)], fill=WHITE)
    d.line([(0, 30), (31, 30)], fill=PINK_D)
    return im


def tex_engine():
    im = solid(GREY_D)
    d = ImageDraw.Draw(im)
    for y in (3, 12, 21, 29):
        d.line([(0, y), (31, y)], fill=GREY)
    d.rectangle([0, 0, 31, 31], outline=DARK)
    return im


def tex_fan():
    """Turbofan face: dark disc, spinner, blades."""
    im = solid(GREY_D)
    d = ImageDraw.Draw(im)
    d.ellipse([1, 1, 30, 30], fill=DARK, outline=GREY)
    for a in range(0, 360, 30):
        import math
        x = 16 + 13 * math.cos(math.radians(a))
        y = 16 + 13 * math.sin(math.radians(a))
        d.line([(16, 16), (x, y)], fill=(70, 74, 82, 255))
    d.ellipse([12, 12, 19, 19], fill=GREY, outline=(200, 200, 205, 255))
    return im


def tex_tire():
    im = solid(DARK)
    d = ImageDraw.Draw(im)
    d.ellipse([8, 8, 23, 23], fill=GREY, outline=GREY_D)
    return im


def tex_metal():
    im = solid(GREY)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 31, 31], outline=GREY_D)
    return im


def tex_rotor():
    im = solid(DARK)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 31, 31], outline=(60, 62, 70, 255))
    d.rectangle([26, 0, 31, 31], fill=(210, 210, 215, 255))
    return im


def tex_flame():
    im = solid((255, 150, 40, 255))
    d = ImageDraw.Draw(im)
    d.ellipse([6, 6, 25, 25], fill=(255, 230, 120, 255))
    return im


TEXTURES = {
    "body": tex_body, "windows": tex_windows, "cockpit": tex_cockpit, "fin": tex_fin, "engine": tex_engine,
    "fan": tex_fan, "tire": tex_tire, "metal": tex_metal, "rotor": tex_rotor, "flame": tex_flame,
    "pink": lambda: solid(PINK), "cyan": lambda: solid(CYAN), "dark": lambda: solid(DARK),
}
TEX = {k: f"{NS}:item/{k}" for k in TEXTURES}


# ─────────────────────────────── model helpers ───────────────────────────────
def box(x1, y1, z1, x2, y2, z2, tex, tint=False, faces=None, uv=None, rot=None):
    """An element with an explicit uv on every face (stretched texture unless given). faces={'west': None} drops a
    face; faces={'north': 'fan'} swaps its texture."""
    fs = {}
    for f in ("north", "south", "east", "west", "up", "down"):
        t = tex
        if faces and f in faces:
            t = faces[f]
        if t is None:
            continue
        d = {"texture": "#" + t, "uv": (uv or {}).get(f, [0, 0, 16, 16])}
        if tint and t == "body":
            d["tintindex"] = 0
        fs[f] = d
    e = {"from": [x1, y1, z1], "to": [x2, y2, z2], "faces": fs}
    if rot:
        e["rotation"] = rot
    return e


def tube(xc, yc, z1, z2, r, tex="body", tint=True, faces=None):
    """Octagonal fuselage section: an axis-aligned box plus the same box turned 45° about z."""
    e = [box(xc - r, yc - r, z1, xc + r, yc + r, z2, tex, tint, faces=faces)]
    k = r * 0.94
    e.append(box(xc - k, yc - k, z1 + 0.01, xc + k, yc + k, z2 - 0.01, tex, tint,
                 rot={"origin": [xc, yc, (z1 + z2) / 2], "axis": "z", "angle": 45}))
    return e


def cone(xc, yc, z_base, z_tip, r, steps, tex="body", tint=True, tip_tex="dark"):
    """A stepped nose (z_tip < z_base, nose toward -z) or tail cone (z_tip > z_base)."""
    e = []
    n = steps
    for i in range(n):
        f0, f1 = i / n, (i + 1) / n
        za = z_base + (z_tip - z_base) * f0
        zb = z_base + (z_tip - z_base) * f1
        rr = r * (1 - 0.85 * f1) + 0.15
        e.append(box(xc - rr, yc - rr, min(za, zb), xc + rr, yc + rr, max(za, zb), tex if i < n - 1 else tip_tex, tint and i < n - 1))
    return e


def windows(xc, yc, z1, z2, r):
    """Cabin window strip: two thin overlay boxes just outside the sides, side faces only."""
    return [box(xc - r - 0.06, yc + 0.2, z1, xc - r - 0.02, yc + 1.2, z2, "windows", faces={"north": None, "south": None, "up": None, "down": None, "east": None}, uv={"west": [0, 0, 16, 16]}),
            box(xc + r + 0.02, yc + 0.2, z1, xc + r + 0.06, yc + 1.2, z2, "windows", faces={"north": None, "south": None, "up": None, "down": None, "west": None}, uv={"east": [16, 0, 0, 16]})]


def cheatline(xc, yc, z1, z2, r, tex, y_off=-0.6):
    return [box(xc - r - 0.05, yc + y_off, z1, xc - r - 0.01, yc + y_off + 0.4, z2, tex, faces={"east": None}),
            box(xc + r + 0.01, yc + y_off, z1, xc + r + 0.05, yc + y_off + 0.4, z2, tex, faces={"west": None})]


def swept_wing(xc, y, z_root, chord, span, sweep, thick=0.6, steps=4, tex="body"):
    """A wing on both sides: `steps` boxes whose leading edge moves back `sweep` units toward the tip."""
    e = []
    for i in range(steps):
        f0, f1 = i / steps, (i + 1) / steps
        za = z_root + sweep * f0
        c = chord * (1 - 0.45 * f1)
        for sgn in (-1, 1):
            xa = xc + sgn * span * f0 * (1 if sgn > 0 else 1)
            xb = xc + sgn * span * f1
            e.append(box(min(xa, xb), y, za, max(xa, xb), y + thick, za + c, tex, True))
    return e


def gear(x, z, h_top, h=1.6, w=0.8):
    return [box(x - 0.15, h_top - h + 0.6, z - 0.15, x + 0.15, h_top + 0.4, z + 0.15, "metal"),
            box(x - w / 2, h_top - h, z - 0.5, x + w / 2, h_top - h + 1.0, z + 0.5, "tire")]


# ─────────────────────────────── aircraft ───────────────────────────────
def fighter():
    e = []
    e += cone(8, 8, -1, -6, 1.5, 3, tip_tex="dark")                       # radome
    e += tube(8, 8, -1, 5, 1.7)                                            # forward fuselage
    e.append(box(6.7, 9.2, -0.5, 9.3, 11.0, 5.5, "cockpit"))                # canopy
    e += tube(8, 8, 5, 19, 2.1)                                            # main fuselage
    e.append(box(4.6, 6.6, 6, 5.9, 8.8, 12, "metal"))                        # intakes
    e.append(box(10.1, 6.6, 6, 11.4, 8.8, 12, "metal"))
    e.append(box(4.7, 7.0, 5.9, 5.8, 8.4, 6.0, "dark"))                      # intake mouths
    e.append(box(10.2, 7.0, 5.9, 11.3, 8.4, 6.0, "dark"))
    e += swept_wing(8, 7.4, 6.5, 11, 12, 6, thick=0.5, steps=4)              # delta wings (x -4..20)
    e.append(box(-4.4, 7.2, 12.5, -4.0, 7.8, 17.5, "dark"))                 # wingtip rails
    e.append(box(20.0, 7.2, 12.5, 20.4, 7.8, 17.5, "dark"))
    for x in (5.8, 9.6):                                                     # twin fins (canted)
        e.append(box(x, 9.8, 13, x + 0.6, 15.5, 19.5, "fin", rot={"origin": [x + 0.3, 9.8, 16], "axis": "z", "angle": 22.5 if x < 8 else -22.5}))
    e.append(box(2.5, 7.5, 16.5, 5.9, 8.0, 21, "body", True))                # stabilizers
    e.append(box(10.1, 7.5, 16.5, 13.5, 8.0, 21, "body", True))
    e.append(box(6.6, 6.6, 19, 9.4, 9.4, 23.5, "engine", faces={"south": "flame"}))   # nozzle + glow
    e += gear(8, 0.5, 6.4, h=2.0, w=0.7)                                     # nose gear
    e += gear(5.6, 10.5, 6.2, h=1.8)
    e += gear(10.4, 10.5, 6.2, h=1.8)
    return e


def private_jet():
    e = []
    e += cone(8, 8, 0, -5, 2.0, 3)
    e.append(box(6.6, 9.0, -1.5, 9.4, 10.6, 1.5, "cockpit"))
    e += tube(8, 8, 0, 22, 2.0)
    e += windows(8, 8, 3, 18, 2.0)
    e += cheatline(8, 8, -1, 21, 2.0, "pink")
    e += swept_wing(8, 6.9, 8, 6, 15, 5, thick=0.5, steps=4)                  # x -7..23
    e.append(box(-7.4, 6.9, 12.5, -7.0, 10.0, 14.5, "pink"))                 # winglets
    e.append(box(23.0, 6.9, 12.5, 23.4, 10.0, 14.5, "pink"))
    for x in (3.2, 10.8):                                                    # rear engines
        e.append(box(x, 8.6, 15, x + 2.0, 10.6, 20.5, "engine", faces={"north": "fan"}))
    e.append(box(5.2, 8.9, 16.5, 6.1, 10.2, 19, "metal"))                     # pylons
    e.append(box(9.9, 8.9, 16.5, 10.8, 10.2, 19, "metal"))
    e += cone(8, 8, 22, 26, 2.0, 2, tip_tex="body")                          # tail cone
    e.append(box(7.6, 9.9, 18, 8.4, 16.5, 25, "fin", uv={"east": [0, 0, 16, 16], "west": [16, 0, 0, 16]}))  # T-tail fin
    e.append(box(3.0, 16.3, 21.5, 13.0, 16.9, 25, "body", True))              # T stabilizer
    e.append(box(2.8, 16.0, 21.5, 3.2, 17.2, 25, "pink"))
    e.append(box(12.8, 16.0, 21.5, 13.2, 17.2, 25, "pink"))
    e += gear(8, 1.5, 6.0, h=1.6, w=0.7)
    e += gear(5.4, 12, 6.0, h=1.6)
    e += gear(10.6, 12, 6.0, h=1.6)
    return e


def b737():
    e = []
    e += cone(8, 8, -2, -7, 2.6, 3)
    e.append(box(6.2, 9.4, -3.5, 9.8, 10.9, -0.5, "cockpit"))
    e += tube(8, 8, -2, 22, 2.6)
    e += windows(8, 8, 1, 19, 2.6)
    e += cheatline(8, 8, -3, 21, 2.6, "cyan", y_off=-0.4)
    e += swept_wing(8, 6.7, 8, 7, 19, 7, thick=0.7, steps=5)                  # x -11..27
    e.append(box(-11.4, 6.7, 14.5, -11.0, 10.5, 17.5, "cyan"))               # winglets
    e.append(box(27.0, 6.7, 14.5, 27.4, 10.5, 17.5, "cyan"))
    for x in (0.6, 11.8):                                                    # under-wing turbofans
        e.append(box(x, 3.9, 6.5, x + 3.6, 7.3, 13.5, "engine", faces={"north": "fan"}))
        e.append(box(x + 1.4, 7.3, 9.5, x + 2.2, 8.0, 12.5, "metal"))          # pylon
    e += cone(8, 8, 22, 27, 2.6, 2, tip_tex="body")
    e.append(box(7.5, 10.4, 17.5, 8.5, 19.0, 26.5, "fin", uv={"east": [0, 0, 16, 16], "west": [16, 0, 0, 16]}))
    e.append(box(1.5, 8.2, 22, 14.5, 8.9, 26.5, "body", True))                # stabilizers
    e.append(box(7.5, 8.0, 15.5, 8.5, 10.6, 18.0, "fin"))                    # fin root fillet
    e += gear(8, -0.5, 5.4, h=2.0, w=0.9)
    e += gear(5.2, 12.5, 5.4, h=2.0, w=1.0)
    e += gear(10.8, 12.5, 5.4, h=2.0, w=1.0)
    return e


def helicopter():
    e = []
    e.append(box(6.0, 6.8, -1.5, 10.0, 10.8, 3.5, "cockpit"))                # glass bubble
    e.append(box(6.2, 5.8, -1.0, 9.8, 7.0, 3.5, "body", True))                # chin
    e.append(box(5.6, 5.6, 3.5, 10.4, 11.0, 12.5, "body", True))              # cabin
    e += windows(8, 8.2, 5, 12, 2.4)
    e.append(box(5.55, 6.2, 4, 5.6, 6.8, 12, "pink", faces={"east": None}))   # pink trim
    e.append(box(10.4, 6.2, 4, 10.45, 6.8, 12, "pink", faces={"west": None}))
    for x in (4.6, 10.8):                                                    # skids + struts
        e.append(box(x, 3.6, -1.0, x + 0.6, 4.2, 13.0, "metal"))
        e.append(box(x + 0.1, 4.2, 1.0, x + 0.5, 5.8, 1.6, "metal"))
        e.append(box(x + 0.1, 4.2, 10.0, x + 0.5, 5.8, 10.6, "metal"))
    e.append(box(6.6, 11.0, 5.0, 9.4, 11.8, 9.5, "engine"))                    # engine cowl
    e.append(box(7.4, 11.8, 6.6, 8.6, 12.4, 7.8, "dark"))                      # mast
    e.append(box(7.0, 8.0, 12.5, 9.0, 9.4, 24.0, "body", True))                # tail boom
    e.append(box(7.6, 8.6, 22.0, 8.4, 13.0, 25.0, "fin", uv={"east": [0, 0, 16, 16], "west": [16, 0, 0, 16]}))
    e.append(box(8.45, 9.0, 22.5, 8.55, 14.0, 23.5, "rotor"))                 # tail rotor (vertical blade)
    e.append(box(8.45, 11.0, 20.8, 8.55, 12.0, 25.2, "rotor"))                 # tail rotor (horizontal blade)
    e.append(box(4.5, 8.8, 19.5, 11.5, 9.3, 21.5, "body", True))               # small stabilizer
    return e


def rotor():
    return [box(7.4, 7.6, 7.4, 8.6, 8.6, 8.6, "dark"),
            box(-3, 7.9, 7.6, 19, 8.3, 8.4, "rotor", uv={"up": [0, 0, 16, 16], "down": [0, 0, 16, 16]}),
            box(7.6, 7.9, -3, 8.4, 8.3, 19, "rotor", uv={"up": [0, 0, 16, 16], "down": [0, 0, 16, 16]})]


MODELS = {"fighter": fighter, "private_jet": private_jet, "b737": b737, "helicopter": helicopter, "rotor": rotor}


def lowest_y(elements):
    return min(el["from"][1] for el in elements)


def check(mid, elements):
    for el in elements:
        for i, (a, b) in enumerate(zip(el["from"], el["to"])):
            assert -16 <= a <= 32 and -16 <= b <= 32, f"{mid}: element {el['from']}→{el['to']} leaves -16..32"
            assert a <= b, f"{mid}: from > to in {el}"
        for f, d in el["faces"].items():
            assert "uv" in d, f"{mid}: face {f} without uv"


def build():
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    tdir = os.path.join(OUT, f"assets/{NS}/textures/item")
    mdir = os.path.join(OUT, f"assets/{NS}/models/item")
    idir = os.path.join(OUT, f"assets/{NS}/items")
    for d in (tdir, mdir, idir):
        os.makedirs(d, exist_ok=True)
    for k, fn in TEXTURES.items():
        fn().save(os.path.join(tdir, f"{k}.png"))
    info = {}
    for mid, fn in MODELS.items():
        els = fn()
        check(mid, els)
        info[mid] = {"elements": len(els), "lowest_y": lowest_y(els)}
        json.dump({"textures": TEX, "elements": els}, open(os.path.join(mdir, f"{mid}.json"), "w"), indent=1)
        json.dump({"model": {"type": "minecraft:model", "model": f"{NS}:item/{mid}",
                             "tints": [{"type": "minecraft:dye", "default": -1}]}},
                  open(os.path.join(idir, f"{mid}.json"), "w"), indent=2)
    json.dump({"pack": {"description": "Air Bulbul planes", "min_format": 88, "max_format": 88}}, open(os.path.join(OUT, "pack.mcmeta"), "w"))
    z = os.path.join(HERE, "planes_pack.zip")
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(OUT):
            for f in sorted(files):
                p = os.path.join(root, f)
                zf.write(p, os.path.relpath(p, OUT))
    print(json.dumps({"zip": z, "models": info}, indent=1))
    # ground offsets for planes.sc: (8 - lowest_y) / 16 * scale
    for mid, sc in (("fighter", 5.0), ("private_jet", 6.0), ("b737", 7.5), ("helicopter", 5.0)):
        print(f"  {mid}: ground_off at scale {sc} = {(8 - info[mid]['lowest_y']) / 16 * sc:.3f} blocks")
    prev = os.path.join(HERE, "planes_preview.png")
    os.makedirs(os.path.dirname(prev), exist_ok=True)
    subprocess.run([sys.executable, os.path.join(HERE, "model_preview.py"), OUT] + [f"{NS}:item/{m}" for m in ("fighter", "private_jet", "b737", "helicopter")]
                   + ["--out", prev, "--yaw", "35", "--pitch", "25"], check=False)


if __name__ == "__main__":
    build()
