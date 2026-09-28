"""gen_arcade_pack.py — models for the arcade & bowling floor.

arcade:pin (white bowling pin, red neck stripes), arcade:ball (a rounded ball tinted by the item's dyed_color — every
player a different colour), arcade:mole (whack-a-mole critter, face on both sides), arcade:claw_open / claw_closed (the
claw-machine claw), prizes arcade:plush_bunny / plush_frog / plush_star / plush_golem.
Model space: x/z centred on 8, y from 0 up — an item_display puts the model point (8,8,8) at its position, so an object
standing on a floor at height f with scale s goes at y = f + 0.5*s (bottom = y 0).
Run: python3 gen_arcade_pack.py → arcade_pack/ + arcade_pack.zip + previews/arcade_*.png
"""
import json
import os
import shutil
import subprocess
import sys
import zipfile

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "build")
NS = "arcade"


def solid(c):
    return lambda: Image.new("RGBA", (16, 16), c)


def tex_pin():
    im = Image.new("RGBA", (16, 16), (246, 244, 238, 255))
    d = ImageDraw.Draw(im)
    for y in range(16):
        for x in range(16):
            if (x * 7 + y * 3) % 11 == 0:
                im.putpixel((x, y), (232, 230, 224, 255))      # a faint lacquer grain
    return im


def tex_stripe():
    im = Image.new("RGBA", (16, 16), (246, 244, 238, 255))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 3, 15, 5], fill=(214, 40, 48, 255))
    d.rectangle([0, 9, 15, 11], fill=(214, 40, 48, 255))
    return im


def tex_ball():                                               # greyscale marble — tinted by dyed_color
    im = Image.new("RGBA", (16, 16), (230, 230, 230, 255))
    for y in range(16):
        for x in range(16):
            v = 200 + ((x * 13 + y * 7 + (x * y) % 5) % 40)
            im.putpixel((x, y), (v, v, v, 255))
    return im


def tex_ball_holes():
    im = tex_ball()
    d = ImageDraw.Draw(im)
    for (cx, cy) in ((6, 5), (10, 5), (8, 10)):
        d.ellipse([cx - 1, cy - 1, cx + 1, cy + 1], fill=(40, 40, 40, 255))
    return im


def tex_mole_fur():
    im = Image.new("RGBA", (16, 16), (122, 84, 52, 255))
    for y in range(16):
        for x in range(16):
            if (x + 2 * y) % 5 == 0:
                im.putpixel((x, y), (104, 70, 42, 255))
    return im


def tex_mole_face():
    im = tex_mole_fur()
    d = ImageDraw.Draw(im)
    d.rectangle([3, 4, 5, 6], fill=(20, 20, 20, 255)); d.point((4, 4), fill=(255, 255, 255, 255))
    d.rectangle([10, 4, 12, 6], fill=(20, 20, 20, 255)); d.point((11, 4), fill=(255, 255, 255, 255))
    d.rectangle([6, 7, 9, 9], fill=(240, 120, 150, 255))                        # pink nose
    d.rectangle([6, 11, 9, 12], fill=(250, 250, 240, 255))                      # teeth
    d.point((2, 8), fill=(230, 120, 140, 255)); d.point((13, 8), fill=(230, 120, 140, 255))
    return im


def tex_metal():
    im = Image.new("RGBA", (16, 16), (180, 186, 196, 255))
    d = ImageDraw.Draw(im)
    d.line([0, 2, 15, 2], fill=(220, 226, 236, 255))
    d.line([0, 12, 15, 12], fill=(140, 146, 156, 255))
    return im


TEXTURES = {
    "pin": tex_pin, "pin_stripe": tex_stripe, "ball": tex_ball, "ball_holes": tex_ball_holes,
    "mole_fur": tex_mole_fur, "mole_face": tex_mole_face, "metal": tex_metal,
    "red": solid((214, 40, 48, 255)), "pink": solid((255, 150, 200, 255)), "pink_d": solid((230, 110, 170, 255)),
    "white": solid((250, 250, 250, 255)), "black": solid((25, 25, 30, 255)), "green": solid((110, 200, 90, 255)),
    "green_d": solid((70, 150, 60, 255)), "yellow": solid((255, 214, 60, 255)), "gold": solid((230, 170, 40, 255)),
}
TEX = {k: f"{NS}:item/{k}" for k in TEXTURES}


def box(x1, y1, z1, x2, y2, z2, tex, faces=None, tint=False):
    fs = {}
    for f in ("north", "south", "east", "west", "up", "down"):
        t = (faces or {}).get(f, tex)
        if t is None:
            continue
        fs[f] = {"texture": "#" + t, "uv": [0, 0, 16, 16]}
        if tint:
            fs[f]["tintindex"] = 0
    return {"from": [x1, y1, z1], "to": [x2, y2, z2], "faces": fs}


def pin():
    return [box(6.5, 0, 6.5, 9.5, 2, 9.5, "pin"),              # foot
            box(5.5, 2, 5.5, 10.5, 7, 10.5, "pin"),            # belly
            box(6.2, 7, 6.2, 9.8, 8.5, 9.8, "pin"),
            box(6.8, 8.5, 6.8, 9.2, 10.5, 9.2, "pin_stripe"),  # neck with the two red stripes
            box(6.2, 10.5, 6.2, 9.8, 13, 9.8, "pin"),          # head
            box(6.8, 13, 6.8, 9.2, 14, 9.2, "pin")]


def ball():
    return [box(4, 5, 5, 12, 11, 11, "ball", faces={"up": "ball_holes"}, tint=True),
            box(5, 4, 5, 11, 12, 11, "ball", faces={"up": "ball_holes"}, tint=True),
            box(5, 5, 4, 11, 11, 12, "ball", faces={"up": "ball_holes"}, tint=True)]


def mole():
    return [box(4, 0, 4, 12, 9, 12, "mole_fur", faces={"north": "mole_face", "south": "mole_face"}),
            box(5, 9, 5, 11, 11, 11, "mole_fur"),
            box(3, 6, 6, 4, 8, 10, "pink"), box(12, 6, 6, 13, 8, 10, "pink")]         # little paws


def claw(open_):
    spread = 3.5 if open_ else 1.2
    els = [box(6, 12, 6, 10, 16, 10, "metal"),                                   # the hub
           box(7.5, 16, 7.5, 8.5, 24, 8.5, "metal")]                             # cable stub
    for (dx, dz) in ((0, -1), (0.87, 0.5), (-0.87, 0.5)):                        # three prongs
        cx, cz = 8 + dx * spread, 8 + dz * spread
        els.append(box(cx - 0.6, 5, cz - 0.6, cx + 0.6, 12, cz + 0.6, "metal"))
        tipx, tipz = 8 + dx * (spread - 1.2), 8 + dz * (spread - 1.2)
        els.append(box(tipx - 0.6, 4, tipz - 0.6, tipx + 0.6, 5.5, tipz + 0.6, "metal"))
    return els


def plush_bunny():
    return [box(5, 0, 5, 11, 7, 11, "pink", faces={"north": "white", "south": "white"}),
            box(5.5, 7, 5.5, 10.5, 12, 10.5, "pink"),
            box(6, 12, 7.5, 7.2, 16, 8.5, "pink_d"), box(8.8, 12, 7.5, 10, 16, 8.5, "pink_d")]


def plush_frog():
    return [box(4.5, 0, 5, 11.5, 6, 11, "green"),
            box(5, 6, 5.5, 11, 9, 10.5, "green"),
            box(5.2, 9, 7, 7.2, 11, 9, "white"), box(8.8, 9, 7, 10.8, 11, 9, "white"),
            box(4, 0, 4, 6, 1.5, 6, "green_d"), box(10, 0, 4, 12, 1.5, 6, "green_d")]


def plush_star():
    return [box(6, 0, 6.5, 10, 12, 9.5, "yellow"), box(2, 6, 6.5, 14, 9, 9.5, "yellow"),
            box(4, 2, 6.5, 6, 6, 9.5, "gold"), box(10, 2, 6.5, 12, 6, 9.5, "gold")]


def plush_golem():
    return [box(5, 0, 6, 7, 4, 10, "pink_d"), box(9, 0, 6, 11, 4, 10, "pink_d"),
            box(4, 4, 5.5, 12, 10, 10.5, "pink"),
            box(2.5, 3, 7, 4, 10, 9, "pink_d"), box(12, 3, 7, 13.5, 10, 9, "pink_d"),
            box(5.5, 10, 6, 10.5, 14, 10, "pink", faces={"north": "white", "south": "white"})]


MODELS = {"pin": pin, "ball": ball, "mole": mole, "claw_open": lambda: claw(True), "claw_closed": lambda: claw(False),
          "plush_bunny": plush_bunny, "plush_frog": plush_frog, "plush_star": plush_star, "plush_golem": plush_golem}
TINTED = {"ball"}


def build():
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    tdir, mdir, idir = (os.path.join(OUT, f"assets/{NS}/{p}") for p in ("textures/item", "models/item", "items"))
    for d in (tdir, mdir, idir):
        os.makedirs(d, exist_ok=True)
    for k, fn in TEXTURES.items():
        fn().save(os.path.join(tdir, f"{k}.png"))
    for mid, fn in MODELS.items():
        els = fn()
        for e in els:
            for v in e["from"] + e["to"]:
                assert -16 <= v <= 32, (mid, e)
        json.dump({"textures": TEX, "elements": els}, open(os.path.join(mdir, f"{mid}.json"), "w"), indent=1)
        model = {"type": "minecraft:model", "model": f"{NS}:item/{mid}"}
        if mid in TINTED:
            model["tints"] = [{"type": "minecraft:dye", "default": -1}]
        json.dump({"model": model}, open(os.path.join(idir, f"{mid}.json"), "w"), indent=2)
    json.dump({"pack": {"description": "Pink Golem arcade & bowling", "min_format": 88, "max_format": 88}}, open(os.path.join(OUT, "pack.mcmeta"), "w"))
    z = os.path.join(HERE, "arcade.zip")
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(OUT):
            for f in sorted(files):
                p = os.path.join(root, f)
                zf.write(p, os.path.relpath(p, OUT))
    os.makedirs(os.path.join(HERE, "previews"), exist_ok=True)
    for mid in ("pin", "ball", "mole", "claw_open", "plush_golem"):
        subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.dirname(HERE)), "resourcepacks", "tools", "model_preview.py"), OUT, f"{NS}:item/{mid}",
                        "--out", os.path.join(HERE, "previews", f"arcade_{mid}.png"), "--yaw", "25", "--pitch", "15"],
                       check=False, capture_output=True)
    print(json.dumps({"zip": z, "kb": round(os.path.getsize(z) / 1024, 1), "models": list(MODELS)}))


if __name__ == "__main__":
    build()
