"""gen_museum_pack.py — the framed photos of the server-history museum (scarpet-apps/museum.sc).

Photograph each landmark with minecraft_screenshot (iso render) and name the shot mus_<id> → mcp-server/screenshots/mus_<id>-*.png.
Here every render is cropped to its content (the four image corners are always background in an iso render, so the
background is estimated per row by interpolating the top-left and bottom-left pixels), then set into a cream museum mat
with a dark frame and a thin gold line: a 320x200 texture (aspect 1.6 → hung at 4 x 2.5 blocks).
Item models museum:<id> = the 16x16 quad of gen_lobby_map.py / gen_gallery_pack.py (element [0,0,7.9]..[16,16,8.1]).
Run: python3 gen_museum_pack.py <id> <id> ... → build/ + museum.zip + museum_sheet.png
"""
import glob
import json
import os
import shutil
import sys
import zipfile

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
SHOTS = os.environ.get("MUSEUM_SHOTS", os.path.join(os.path.dirname(os.path.dirname(HERE)), "mcp-server", "screenshots"))
OUT = os.path.join(HERE, "build")
NS = "museum"
W, H = 320, 200
FRAME, GOLD, MAT = 7, 2, 9
IDS = [a for a in sys.argv[1:]] or ["spawn", "first_house", "tower"]   # your station ids, oldest first


def latest(i):
    fs = sorted(glob.glob(os.path.join(SHOTS, f"mus_{i}-*.png")))
    assert fs, f"no screenshot for {i}"
    return fs[-1]


def crop_to_content(im):
    a = np.asarray(im.convert("RGB")).astype(np.int32)
    h, w, _ = a.shape
    top, bot = a[0, 0], a[h - 1, 0]
    t = np.linspace(0, 1, h)[:, None]
    bg = top[None, :] * (1 - t) + bot[None, :] * t                     # per-row background colour
    d = np.abs(a - bg[:, None, :]).sum(axis=2)
    ys, xs = np.nonzero(d > 30)
    if len(xs) == 0:
        return im
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    px, py = int((x1 - x0) * 0.04) + 4, int((y1 - y0) * 0.04) + 4
    return im.crop((max(0, x0 - px), max(0, y0 - py), min(w, x1 + px), min(h, y1 + py)))


def framed(im):
    c = Image.new("RGB", (W, H), (244, 239, 230))                       # the mat
    d = ImageDraw.Draw(c)
    d.rectangle([0, 0, W - 1, H - 1], outline=(43, 33, 24), width=FRAME)
    d.rectangle([FRAME, FRAME, W - 1 - FRAME, H - 1 - FRAME], outline=(201, 162, 74), width=GOLD)
    iw, ih = W - 2 * (FRAME + GOLD + MAT), H - 2 * (FRAME + GOLD + MAT)
    s = min(iw / im.width, ih / im.height)
    ph = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.LANCZOS)
    ox = (W - ph.width) // 2
    oy = (H - ph.height) // 2
    # a soft shadow under the print
    d.rectangle([ox + 2, oy + 2, ox + ph.width + 1, oy + ph.height + 1], fill=(214, 206, 192))
    c.paste(ph, (ox, oy))
    return c


def main():
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    tdir, mdir, idir = (os.path.join(OUT, f"assets/{NS}/{p}") for p in ("textures/item", "models/item", "items"))
    for dd in (tdir, mdir, idir):
        os.makedirs(dd, exist_ok=True)
    images = {}
    for i in IDS:
        src = Image.open(latest(i)).convert("RGB")
        im = framed(crop_to_content(src))
        im.save(os.path.join(tdir, f"{i}.png"), optimize=True)
        images[i] = im
        quad = {"textures": {"0": f"{NS}:item/{i}", "particle": f"{NS}:item/{i}"},
                "elements": [{"from": [0, 0, 7.9], "to": [16, 16, 8.1],
                              "faces": {"north": {"uv": [0, 0, 16, 16], "texture": "#0"},
                                        "south": {"uv": [0, 0, 16, 16], "texture": "#0"}}}]}
        json.dump(quad, open(os.path.join(mdir, f"{i}.json"), "w"))
        json.dump({"model": {"type": "minecraft:model", "model": f"{NS}:item/{i}"}}, open(os.path.join(idir, f"{i}.json"), "w"))
    json.dump({"pack": {"description": "Pink Golem museum photos", "min_format": 88, "max_format": 88}}, open(os.path.join(OUT, "pack.mcmeta"), "w"))
    z = os.path.join(HERE, "museum.zip")
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(OUT):
            for f in sorted(files):
                p = os.path.join(root, f)
                zf.write(p, os.path.relpath(p, OUT))
    cols = 4
    sheet = Image.new("RGB", (cols * (W + 8), ((len(IDS) + cols - 1) // cols) * (H + 8)), (30, 30, 30))
    for k, i in enumerate(IDS):
        sheet.paste(images[i], ((k % cols) * (W + 8) + 4, (k // cols) * (H + 8) + 4))
    sp = os.path.join(HERE, "museum_sheet.png")
    sheet.save(sp)
    print(json.dumps({"zip": z, "kb": os.path.getsize(z) // 1024, "photos": len(IDS), "sheet": sp}))


if __name__ == "__main__":
    main()
