"""build_pack.py — 3D car models for scarpet-apps/cars.sc, as a resource pack (Minecraft 26.2, pack format 88).

Each model is an item model (assets/cars/models/item/<id>.json) made of boxes with vanilla textures; the body faces
carry tintindex 0 and the item definition (assets/cars/items/<id>.json) tints them with the stack's dyed_color, so one
model comes in any colour. The app shows a car as an item_display holding
paper[item_model="cars:<id>", dyed_color=RGB], scaled by SCALE.

Model space: 16 units = 1 block before scaling; x 8 = centre line, z 0 = rear, z 16 = front (nose at +z), y 0 = ground.
An item_display shows a model's +z side facing AWAY from its yaw, so the app adds 180 to the heading (MODEL_YAW).
Add a model: write a function returning boxes, add it to MODELS, and add a row to global_M in cars.sc.

Run: python3 resourcepacks/cars/build_pack.py → resourcepacks/cars/cars.zip (sha1 printed). Players get it as the
server resource pack (merge it with any other pack you send; see reference/hud.md → "One server pack").
"""
import hashlib
import json
import os
import shutil
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "build")
SCALE = 4.6            # 16 units → 4.6 blocks: a sedan is ~4.4 long, 2.0 wide, 1.5 high

TEX = {"body": "minecraft:block/white_concrete", "glass": "minecraft:block/tinted_glass", "tire": "minecraft:block/black_concrete",
       "rim": "minecraft:block/iron_block", "lamp": "minecraft:block/glowstone", "tail": "minecraft:block/red_concrete",
       "grey": "minecraft:block/gray_concrete", "chrome": "minecraft:block/light_gray_concrete", "yellow": "minecraft:block/yellow_concrete",
       "blue": "minecraft:block/blue_concrete", "red": "minecraft:block/red_concrete", "seat": "minecraft:block/brown_concrete",
       "particle": "minecraft:block/white_concrete"}


def box(x1, y1, z1, x2, y2, z2, tex, tint=False, faces=None):
    fs = {}
    for f in ("north", "south", "east", "west", "up", "down"):
        t = (faces or {}).get(f, tex)
        if t is None:
            continue
        d = {"texture": "#" + t}
        if tint and t == "body":
            d["tintindex"] = 0
        fs[f] = d
    return {"from": [x1, y1, z1], "to": [x2, y2, z2], "faces": fs}


def wheels(xl, xr, zr, zf, r=2.3, w=1.3):
    """4 wheels: x from the outer side (left xl .. xl+w, right xr-w .. xr), rear axle zr, front axle zf."""
    out = []
    for (x1, x2) in ((xl, xl + w), (xr - w, xr)):
        for zc in (zr, zf):
            out.append(box(x1, 0, zc - r / 2 - 0.2, x2, r, zc + r / 2 + 0.2, "tire",
                           faces={"east": "rim" if x1 > 8 else "tire", "west": "rim" if x1 < 8 else "tire"}))
    return out


def lights(xl, xr, y1, y2, zf, zr):
    return [box(xl + 0.4, y1, zf - 0.1, xl + 1.8, y2, zf + 0.25, "lamp"), box(xr - 1.8, y1, zf - 0.1, xr - 0.4, y2, zf + 0.25, "lamp"),
            box(xl + 0.4, y1, zr - 0.25, xl + 1.8, y2, zr + 0.1, "tail"), box(xr - 1.8, y1, zr - 0.25, xr - 0.4, y2, zr + 0.1, "tail")]


def sedan(extra=()):
    e = [box(4.5, 1.1, 0.4, 11.5, 3.2, 15.6, "body", True),                          # lower body
         box(4.3, 1.0, 0.0, 11.7, 1.8, 0.5, "chrome"), box(4.3, 1.0, 15.5, 11.7, 1.8, 16.0, "chrome"),   # bumpers
         box(5.6, 3.2, 12.3, 10.4, 3.5, 15.5, "grey"),                                 # grille strip on the hood
         box(4.8, 3.2, 4.0, 11.2, 5.1, 11.6, "glass", faces={"up": None}),            # cabin glass
         box(4.7, 5.1, 4.2, 11.3, 5.5, 11.4, "body", True),                            # roof
         box(4.8, 3.2, 7.6, 11.2, 5.1, 8.0, "body", True, faces={"north": "body", "south": "body"})]   # B-pillar
    return e + wheels(4.0, 12.0, 3.4, 12.4) + lights(4.5, 11.5, 2.2, 2.9, 15.6, 0.4) + list(extra)


def sports():
    e = [box(4.3, 0.9, 0.4, 11.7, 2.7, 15.6, "body", True),
         box(4.1, 0.8, 0.0, 11.9, 1.5, 0.5, "grey"), box(4.1, 0.8, 15.5, 11.9, 1.5, 16.0, "grey"),
         box(5.0, 2.7, 5.2, 11.0, 4.2, 10.6, "glass", faces={"up": None}),
         box(4.9, 4.2, 5.4, 11.1, 4.5, 10.4, "body", True),
         box(4.6, 3.6, 0.6, 11.4, 3.9, 2.2, "body", True),                            # spoiler wing
         box(5.6, 2.7, 1.2, 6.2, 3.6, 1.8, "grey"), box(9.8, 2.7, 1.2, 10.4, 3.6, 1.8, "grey"),
         box(6.0, 2.7, 12.5, 10.0, 2.9, 15.0, "grey")]                                  # hood scoop
    return e + wheels(3.7, 12.3, 3.3, 12.5, r=2.2, w=1.4) + lights(4.3, 11.7, 1.8, 2.4, 15.6, 0.4)


def suv():
    e = [box(4.3, 1.4, 0.4, 11.7, 3.9, 15.6, "body", True),
         box(4.1, 1.2, 0.0, 11.9, 2.1, 0.5, "grey"), box(4.1, 1.2, 15.5, 11.9, 2.1, 16.0, "grey"),
         box(4.6, 3.9, 2.0, 11.4, 6.2, 12.2, "glass", faces={"up": None}),
         box(4.5, 6.2, 2.2, 11.5, 6.6, 12.0, "body", True),
         box(4.8, 6.6, 3.0, 5.2, 6.9, 11.2, "grey"), box(10.8, 6.6, 3.0, 11.2, 6.9, 11.2, "grey"),   # roof rails
         box(5.5, 1.6, 0.0, 10.5, 3.2, 0.4, "tire")]                                   # spare wheel
    return e + wheels(3.8, 12.2, 3.6, 12.4, r=2.8, w=1.4) + lights(4.3, 11.7, 2.6, 3.4, 15.6, 0.4)


def taxi():
    return sedan([box(6.8, 5.5, 7.0, 9.2, 6.4, 8.6, "yellow")])


def police():
    return sedan([box(5.8, 5.5, 7.2, 7.9, 6.0, 8.4, "red"), box(8.1, 5.5, 7.2, 10.2, 6.0, 8.4, "blue"),
                  box(4.45, 1.9, 4.5, 4.5, 2.6, 11.5, "blue"), box(11.5, 1.9, 4.5, 11.55, 2.6, 11.5, "blue")])


MODELS = {"sedan": sedan(), "sports": sports(), "suv": suv(), "taxi": taxi(), "police": police()}


def build():
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    for mid, elements in MODELS.items():
        mdir = os.path.join(OUT, "assets/cars/models/item")
        idir = os.path.join(OUT, "assets/cars/items")
        os.makedirs(mdir, exist_ok=True); os.makedirs(idir, exist_ok=True)
        json.dump({"textures": TEX, "elements": elements}, open(os.path.join(mdir, f"{mid}.json"), "w"))
        json.dump({"model": {"type": "minecraft:model", "model": f"cars:item/{mid}", "tints": [{"type": "minecraft:dye", "default": -1}]}},
                  open(os.path.join(idir, f"{mid}.json"), "w"))
    json.dump({"pack": {"description": "Pink Golem cars", "min_format": 88, "max_format": 88}}, open(os.path.join(OUT, "pack.mcmeta"), "w"))
    z = os.path.join(HERE, "cars.zip")
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(OUT):
            for f in sorted(files):
                p = os.path.join(root, f)
                zf.write(p, os.path.relpath(p, OUT))
    print(z, hashlib.sha1(open(z, "rb").read()).hexdigest(), {k: len(v) for k, v in MODELS.items()})


if __name__ == "__main__":
    build()
