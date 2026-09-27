"""gen_gallery_pack.py — a small demo art gallery: PIL-drawn paintings as quad item models (namespace `gallery`),
one spinning 3D exhibit on a plinth, one sculpture plaque, one quiet zone, and `art.json` for `scarpet-apps/gallery.sc`.
The technique (positions, the `face` = viewer-side yaw convention, why item-model quads beat a painting/map/banner)
is in [`skill/pinkgolem/reference/cinema-and-gallery.md`](../../skill/pinkgolem/reference/cinema-and-gallery.md).

Paintings are drawn at 4x and downsampled (anti-aliased), get a subtle paper grain, and are palette-quantised so
each PNG stays a few KB. Sizes follow the wall's aspect ratio: 4x3 -> 256x192, 3x2 -> 192x128, 2x2 -> 128x128.
Quad model: element [0,0,7.9]..[16,16,8.1], north+south faces, uv [0,0,16,16] (the same non-mirrored scheme used
by every quad model in this project — see `resourcepacks/cinema/cinemalib.py`'s `quad_model()`).

Run: python3 gen_gallery_pack.py
    -> resourcepacks/gallery/build/ + resourcepacks/gallery/gallery.zip
       scarpet-apps/gallery.data.example/art.json   (copy the whole gallery.data.example/ folder to your world as
                                                       gallery.data/)
       resourcepacks/gallery/preview_sheet.png + preview_model.png
"""
import json
import math
import os
import random
import shutil
import subprocess
import sys
import zipfile

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(HERE, "build")
NS = "gallery"
ART_JSON = os.path.join(ROOT, "scarpet-apps", "gallery.data.example", "art.json")
S = 4  # supersampling factor

# ---- palette (swap these for your own — used only by the demo paintings below) ------------------------------------
CREAM, CREAM_D = (247, 240, 228), (232, 220, 200)
PINK, PINK_L, PINK_D = (231, 130, 168), (245, 190, 208), (200, 78, 122)
ROSE, HOT, GOLD, GOLD_L = (110, 46, 82), (219, 40, 96), (210, 168, 70), (238, 206, 128)
TEAL, TEAL_D, TEAL_L = (44, 132, 132), (24, 82, 88), (140, 200, 196)
BLACK, WHITE, NAVY = (26, 24, 28), (250, 248, 244), (34, 30, 64)


def lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def grad_stops(t, stops):
    for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
        if t <= p1:
            k = 0 if p1 == p0 else (t - p0) / (p1 - p0)
            return lerp(c0, c1, max(0.0, min(1.0, k)))
    return stops[-1][1]


def vgrad(w, h, stops):
    im = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(im)
    for y in range(h):
        d.line([(0, y), (w, y)], fill=grad_stops(y / (h - 1), stops))
    return im


def overlay_alpha(base, draw_fn, alpha=255):
    """Draw shapes on a transparent layer and composite them with the given alpha (cheap translucency in plain PIL)."""
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(layer))
    if alpha < 255:
        a = layer.getchannel("A").point(lambda v: v * alpha // 255)
        layer.putalpha(a)
    base.paste(layer, (0, 0), layer)
    return base


def paper(im, strength=8, seed=1):
    """Subtle paper grain: soft-light with low-contrast noise — a painting with no grain reads as a flat sticker."""
    rng = np.random.default_rng(seed)
    noise = rng.normal(128, strength, (im.height, im.width)).clip(0, 255).astype(np.uint8)
    n = Image.fromarray(noise, "L").filter(ImageFilter.GaussianBlur(0.6)).convert("RGB")
    return ImageChops.soft_light(im, n)


def finish(im, w, h, colors=96, grain=8, seed=1):
    """Downsample from 4x, add grain, quantise to a small palette (this is what keeps every PNG a few KB)."""
    small = im.convert("RGB").resize((w, h), Image.LANCZOS)
    if grain:
        small = paper(small, grain, seed)
    return small.quantize(colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG)


def circle(d, cx, cy, r, **kw):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], **kw)


# ---- the demo paintings ---------------------------------------------------------------------------------------------
# id, (w, h), title, artist
PAINTINGS = [
    ("p01", (256, 192), "Harbour at Dawn", "Studio collection"),
    ("p02", (192, 128), "Circles in Gold", "J. Alto"),
    ("p03", (192, 128), "Night Garden", "R. Vale"),
    ("p04", (128, 128), "Op-Art Stripes", "Studio collection"),
]


def p01(w, h):
    """A harbour at sunrise: warm sky gradient, a low sun, a lighter band of sea, two low buildings, a few birds."""
    W, H = w * S, h * S
    horizon = int(H * 0.68)
    im = vgrad(W, horizon, [(0, ROSE), (0.5, PINK_D), (0.8, PINK), (1, (255, 214, 168))])
    im.paste(vgrad(W, H - horizon, [(0, (150, 200, 196)), (0.4, TEAL), (1, TEAL_D)]), (0, horizon))
    d = ImageDraw.Draw(im)
    circle(d, W * 0.6, horizon, W * 0.09, fill=(255, 230, 170))
    for x, ww, hh in [(W * 0.05, W * 0.06, H * 0.06), (W * 0.14, W * 0.05, H * 0.09), (W * 0.82, W * 0.07, H * 0.07)]:
        overlay_alpha(im, lambda dd, x=x, ww=ww, hh=hh: dd.rectangle([x, horizon - hh, x + ww, horizon], fill=(230, 190, 190)), 130)
    d = ImageDraw.Draw(im)
    for bx, by, r in [(W * 0.30, H * 0.20, 4), (W * 0.35, H * 0.17, 3)]:
        d.arc([bx - r * S, by - r * S, bx, by + r * S], 200, 340, fill=ROSE, width=S)
        d.arc([bx, by - r * S, bx + r * S, by + r * S], 200, 340, fill=ROSE, width=S)
    return finish(im, w, h, colors=96)


def p02(w, h):
    """Abstract overlapping circles on cream with thin orbit lines — the simplest painting to reskin for your own room."""
    W, H = w * S, h * S
    im = vgrad(W, H, [(0, CREAM), (1, CREAM_D)])
    discs = [(0.22, 0.55, 0.34, PINK, 200), (0.50, 0.42, 0.28, GOLD, 190), (0.72, 0.62, 0.24, HOT, 170),
             (0.38, 0.30, 0.13, TEAL, 200), (0.10, 0.20, 0.07, GOLD, 255), (0.92, 0.85, 0.06, TEAL, 255)]
    for cx, cy, r, col, a in discs:
        overlay_alpha(im, lambda dd, cx=cx, cy=cy, r=r, col=col: circle(dd, cx * W, cy * H, r * H, fill=col), a)
    d = ImageDraw.Draw(im)
    for cx, cy, r in [(0.50, 0.42, 0.42), (0.22, 0.55, 0.40)]:
        d.ellipse([cx * W - r * H, cy * H - r * H, cx * W + r * H, cy * H + r * H], outline=BLACK, width=S)
    return finish(im, w, h, colors=64)


def p03(w, h):
    """A night garden: deep blue-green ground, a scatter of pale fireflies/stars, two simple flower silhouettes."""
    W, H = w * S, h * S
    im = vgrad(W, H, [(0, NAVY), (0.6, (30, 46, 60)), (1, (18, 30, 30))])
    d = ImageDraw.Draw(im)
    rng = random.Random(11)
    for _ in range(40):
        x, y = rng.random() * W, rng.random() * H * 0.7
        overlay_alpha(im, lambda dd, x=x, y=y: circle(dd, x, y, rng.choice([1.0, 1.4, 1.8]) * S, fill=GOLD_L), 200)
    d = ImageDraw.Draw(im)

    def stem(x, h_):
        d.line([(x, H), (x, H - h_)], fill=(30, 60, 40), width=int(1.4 * S))
        for k in range(3):
            circle(d, x + (6 if k % 2 else -6) * S, H - h_ + k * 10 * S, 4 * S, fill=PINK)
    stem(W * 0.30, H * 0.55)
    stem(W * 0.66, H * 0.62)
    return finish(im, w, h, colors=64)


def p04(w, h):
    """Op-art: pink/white vertical stripes warped by a central bulge (pure numpy)."""
    W, H = w * S, h * S
    ys, xs = np.mgrid[0:H, 0:W].astype(np.float64)
    u, v = xs / W - 0.5, ys / H - 0.5
    r2 = (u * 0.85) ** 2 + (v * 1.1) ** 2
    bulge = 0.34 * np.exp(-r2 / 0.045)
    phase = (u + 0.5) * 22 * (1 + 0.6 * np.abs(u)) + bulge * 9 * np.sign(u + 1e-9) * np.exp(-(v * 2.2) ** 2)
    stripe = (np.sin(phase * np.pi) > 0).astype(np.float64)
    pink, hot, white = (np.array(c, dtype=np.float64) for c in (PINK, HOT, WHITE))
    shade = np.clip(1 - 0.35 * np.exp(-r2 / 0.03), 0.65, 1.0)[..., None]
    col = np.where(stripe[..., None] > 0.5, pink * (1 - bulge[..., None] * 1.6) + hot * (bulge[..., None] * 1.6),
                   white * shade + (1 - shade) * pink)
    im = Image.fromarray(np.clip(col, 0, 255).astype(np.uint8), "RGB")
    d = ImageDraw.Draw(im)
    circle(d, W * 0.5, H * 0.5, 4 * S, fill=GOLD)
    circle(d, W * 0.5, H * 0.5, 1.8 * S, fill=BLACK)
    return finish(im, w, h, colors=48, grain=5)


DRAW = {"p01": p01, "p02": p02, "p03": p03, "p04": p04}

# ---- world positions: face + a small offset toward the viewers. `face` = the side the viewers stand on -----------
# (same convention as scarpet-apps/cinema.sc: south -> yaw 0, east -> -90, west -> 90, north -> 180). These numbers
# are for the small demo room the reference guide walks through — replace them with your own wall positions.
WALLS = {
    "p01": ((10.0, -58.5, 20.0), "south", 4, 3),
    "p02": ((10.0, -57.0, 24.0), "east", 3, 2),
    "p03": ((14.0, -57.0, 20.0), "north", 3, 2),
    "p04": ((16.0, -57.0, 22.0), "west", 2, 2),
}
OFF = {"south": (0, 0, 0.05), "north": (0, 0, -0.05), "east": (0.05, 0, 0), "west": (-0.05, 0, 0)}

# one spinning exhibit: a simple two-box "trophy" model, item_display on a 1x1 plinth (block top at y=8 model units
# -> world y -60 if the plinth's top block is at y=-61..-60). HOVER lifts its lowest point clear of the plinth.
PLINTH_TOP, HOVER = -60.0, 0.2
EXHIBIT_YMIN = 0.0  # the trophy model's lowest vertex, in 16-units-per-block model space


def trophy_model():
    """A tiny two-box trophy: a stem (0..16 wide at y0..6) and a cup (y6..16), gold-tinted."""
    tex = f"{NS}:item/trophy"
    faces = lambda: {f: {"uv": [0, 0, 16, 16], "texture": "#0"} for f in ("north", "south", "east", "west", "up", "down")}
    return {"textures": {"0": tex, "particle": tex},
            "elements": [{"from": [6, 0, 6], "to": [10, 7, 10], "faces": faces()},
                         {"from": [3, 7, 3], "to": [13, 16, 13], "faces": faces()}]}


def trophy_texture():
    im = Image.new("RGB", (16, 16), GOLD)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 15, 2], fill=GOLD_L)
    d.rectangle([0, 13, 15, 15], fill=(150, 112, 40))
    d.line([(0, 6), (15, 6)], fill=(150, 112, 40))
    return im


EXHIBITS = [("trophy", f"{NS}:trophy", (12.0, 22.0), 0.6, "Founders' Cup", "Awarded every season")]


def art_json():
    paintings = []
    for pid, (wh, title, artist) in ((p[0], p[1:]) for p in PAINTINGS):
        (fx, fy, fz), face, w, h = WALLS[pid]
        ox, oy, oz = OFF[face]
        paintings.append({"id": pid, "model": f"{NS}:{pid}", "title": title, "artist": artist, "year": "2026",
                          "pos": [round(fx + ox, 3), fy, round(fz + oz, 3)], "face": face, "w": w, "h": h})
    exhibits = []
    for eid, model, (x, z), scale, title, sub in EXHIBITS:
        y = PLINTH_TOP + HOVER - (EXHIBIT_YMIN - 8) / 16 * scale
        exhibits.append({"id": eid, "model": model, "pos": [x, round(y, 3), z], "scale": scale, "spin": 3,
                         "title": title, "sub": sub})
    return {"paintings": paintings, "exhibits": exhibits,
            "sculptures": [{"id": "wave", "title": "Tidal Form", "artist": "Studio collection", "year": "2026",
                            "plaque": [13.5, -58.4, 25.9], "face": "south"}],
            "quiet_zones": [{"name": "Reading corner", "min": [9, -60, 19], "max": [17, -54, 27],
                             "msg": "Quiet corner — please keep your voice down"}]}


def preview_sheet(images, path):
    font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 16)
    font_b = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 18)
    cols, cell_w, cell_h, pad = 4, 280, 240, 16
    rows = math.ceil(len(images) / cols)
    sheet = Image.new("RGB", (cols * cell_w + pad, rows * cell_h + pad + 40), (60, 56, 62))
    d = ImageDraw.Draw(sheet)
    d.text((pad, 10), "Demo gallery — paintings P1..P4 (1:1 pixels)", font=font_b, fill=WHITE)
    for i, (pid, wh, title, artist) in enumerate(PAINTINGS):
        im = images[pid].convert("RGB")
        cx = pad + (i % cols) * cell_w
        cy = 40 + pad + (i // cols) * cell_h
        x = cx + (cell_w - pad - im.width) // 2
        d.rectangle([x - 6, cy - 6, x + im.width + 6, cy + im.height + 6], fill=GOLD)
        sheet.paste(im, (x, cy))
        d.text((cx, cy + 190), f"P{i + 1} · {title}", font=font_b, fill=WHITE)
        d.text((cx, cy + 210), f"{im.width}x{im.height} · {artist}", font=font, fill=(220, 214, 220))
    sheet.save(path, optimize=True)


def build():
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    tdir, mdir, idir = (os.path.join(OUT, f"assets/{NS}/{p}") for p in ("textures/item", "models/item", "items"))
    for d in (tdir, mdir, idir):
        os.makedirs(d, exist_ok=True)

    def item_def(name, model_ref):
        json.dump({"model": {"type": "minecraft:model", "model": model_ref}}, open(os.path.join(idir, f"{name}.json"), "w"))

    def quad_model_json(name):
        return {"textures": {"0": f"{NS}:item/{name}", "particle": f"{NS}:item/{name}"},
                "elements": [{"from": [0, 0, 7.9], "to": [16, 16, 8.1],
                              "faces": {"north": {"uv": [0, 0, 16, 16], "texture": "#0"},
                                        "south": {"uv": [0, 0, 16, 16], "texture": "#0"}}}]}

    images, sizes = {}, {}
    for pid, (w, h), title, artist in PAINTINGS:
        im = DRAW[pid](w, h)
        assert im.size == (w, h), (pid, im.size)
        p = os.path.join(tdir, f"{pid}.png")
        im.save(p, optimize=True)
        images[pid], sizes[pid] = im, os.path.getsize(p)
        json.dump(quad_model_json(pid), open(os.path.join(mdir, f"{pid}.json"), "w"))
        item_def(pid, f"{NS}:item/{pid}")

    trophy_texture().save(os.path.join(tdir, "trophy.png"))
    json.dump(trophy_model(), open(os.path.join(mdir, "trophy.json"), "w"))
    item_def("trophy", f"{NS}:item/trophy")

    json.dump({"pack": {"description": "Demo art gallery (Pink Golem cinema-and-gallery example)",
                        "min_format": 88, "max_format": 88}}, open(os.path.join(OUT, "pack.mcmeta"), "w"))
    zpath = os.path.join(HERE, "gallery.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(OUT):
            for f in sorted(files):
                p = os.path.join(root, f)
                zf.write(p, os.path.relpath(p, OUT))

    os.makedirs(os.path.dirname(ART_JSON), exist_ok=True)
    with open(ART_JSON, "w", encoding="utf-8") as f:
        json.dump(art_json(), f, ensure_ascii=False, indent=1)

    sheet = os.path.join(HERE, "preview_sheet.png")
    preview_sheet(images, sheet)
    prev = os.path.join(HERE, "preview_model.png")
    preview_tool = os.path.join(ROOT, "resourcepacks", "tools", "model_preview.py")
    subprocess.run([sys.executable, preview_tool, OUT, f"{NS}:item/p01", f"{NS}:item/trophy",
                    "--out", prev, "--yaw", "25", "--pitch", "10"], check=False)
    print(json.dumps({"zip": zpath, "zip_kb": os.path.getsize(zpath) // 1024, "png_bytes": sizes,
                      "png_total_kb": sum(sizes.values()) // 1024, "sheet": sheet, "model_preview": prev,
                      "art_json": ART_JSON}, indent=1))


if __name__ == "__main__":
    build()
