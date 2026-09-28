"""gen_skinpaint.py -- the skin easel + creators' gallery (scarpet-apps/skinpaint.sc): everything that is data, not logic.

The easel paints a real 64x64 player skin (classic 4-px arms, base layer + second layer) on a wall of pixels. The wall
shows five VIEWS of the character, left to right as the painter (facing the wall) sees them -- the same order as the
skin template unwraps: right side | front | left side | back | top of the head. Every view cell points at one texel
of the base layer and one of the second layer; hidden faces (body sides under the arms, inner arm/leg faces, tops and
bottoms) are DERIVED from the visible edges when the skin is saved.

Pixels are drawn by text_displays with a pixel font from this pack (skinpaint:canvas):
  U+E000  a 10x10 white square, ascent 7 -> it fills the 10-px line pitch of a text display exactly
  U+E001  advance -1 (cancels the bitmap's automatic +1 advance -> seamless pixels)
  U+E002  an empty 10-px cell
  U+E003  a swatch: 8x8 inked at x 1..8 of a 10-px image -> advance exactly 10, with a built-in gap
A text component colour tints the white glyph -> any 24-bit colour. See skill/pinkgolem/reference/skin-easel.md.

Run:  pip install pillow && python3 resourcepacks/skinpaint/gen_skinpaint.py
  -> resourcepacks/skinpaint/build/ + skinpaint.zip          (font, kit item models, 15 toolbar icon quads)
  -> scarpet-apps/skinpaint.data.example/layout.json        (views, bands, cell -> texel map, derive pairs, wall UI)
  -> scarpet-apps/skinpaint.data.example/templates.json     (starting skins: blank, basic + resourcepacks/studio skins)
  -> scarpet-apps/skinpaint.data.example/config.json        (the places the app uses: stage, gallery, preview, buttons)
  -> jobs/skinpaint-1-walls.json + jobs/skinpaint-2-stage.json   (blocks only; the app spawns every entity)
  -> resourcepacks/skinpaint/previews/*.png                 (each template drawn through the views = mapping check)
"""
import colorsys
import json
import os
import shutil
import zipfile

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("PINKGOLEM_ROOT") or os.path.abspath(os.path.join(HERE, "..", ".."))
DATA = os.path.join(ROOT, "scarpet-apps", "skinpaint.data.example")
JOBS = os.environ.get("PINKGOLEM_JOBS") or os.path.join(ROOT, "jobs")
STUDIO = os.path.join(ROOT, "resourcepacks", "studio")      # skins.json + skins/<id>.png (gen_studio_pack.py)
OUT = os.path.join(HERE, "build")
ZIP = os.path.join(HERE, "skinpaint.zip")
PREV = os.path.join(HERE, "previews")
NS = "skinpaint"

# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# CONFIG -- the only block you edit to put the easel on your own wall.
#
# The example numbers are a real, tested room: the easel wall is the block column x = -79 (its face at x = -78.0) and
# it FACES EAST -- the painter stands east of it and looks WEST (-x); their left hand is +z (south). The app only
# supports this orientation (it casts the painter's view ray against a plane of constant x, looking toward -x, and
# turns its text displays to yaw -90). The creators' gallery is the room's north wall (z = -120), facing south.
#
# Every place is ORIGIN + an offset (dx, dy, dz), so moving the whole easel to another east-facing wall = change
# ORIGIN and rerun. Room needed (block offsets, inclusive): dx 0..12, dy 0..10, dz -20..1, empty (the jobs only place
# blocks; clear the room first).
# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
ORIGIN = (-79, -27, -100)   # x of the easel wall blocks, y of the floor blocks, z of the toolbar panel's south frame

PX = 0.19                   # block size of one skin pixel on the wall (the canvas is 56 px + 4 gaps wide, 32 px tall)
CANVAS = {                  # the five views, left edge = the south end (the painter's left)
    "plane_dx": 1.02,       # the displays' plane: 0.02 in front of the wall face (x = ORIGIN.x + 1)
    "top_dy": 7.88,         # top edge of pixel row 0
    "left_dz": -4.45,       # south edge of the first view; views run north (-z), 2 px apart
}
STRIP = {"left_dz": -4.45, "top_dy": 8.92, "cell": 0.25, "cols": 48, "rows": 4}   # colour spectrum ABOVE the canvas
TOOLBAR = {"left_dz": 0.0, "top_dy": 6.8, "cell": 0.6}   # MS-Paint-like toolbox LEFT of (south of) the canvas
PLACES = {                  # config.json for the app (offsets; yaw 0 = faces south, -90 = faces east)
    "easel_centre": (3, 5, -10.5),               # "near the easel" = within 14 blocks of this (claim, away timer)
    "status": (1.03, 6.88, -1.5),                  # the status card above the toolbar
    "labels_dy": 1.38,                           # view names under the canvas
    "preview": {"pos": (5.5, 3, -15.5), "yaw": 0, "label": (5.5, 5.05, -15.5)},   # spinning mannequin on the stage
    "gallery": {
        "slots": [(3.5, 2, -18.5), (6.5, 2, -18.5), (9.5, 2, -18.5)],   # mannequin feet on their plinths
        "plaque_dz": -17.93, "plaque_dy": 1.38,
        "prev_button": (2, 3, -19), "next_button": (11, 3, -19),       # vanilla buttons (block positions)
        "prev_label": (2.5, 3.375, -18.86), "next_label": (11.5, 3.375, -18.86),
        "title": (6.5, 5.05, -18.97), "page": (6.5, 4.4, -18.97),
    },
    "stage": {"min": (3, 2.7, -17), "max": (7, 5, 1)},   # stepping into this box claims the easel (feet at dy 3)
    "area": {"min": (-2, -1, -21), "max": (30, 11, 11)},  # the studio floor: leaving it auto-saves + frees the easel
}
TIMING = {"idle_release_s": 300, "away_release_s": 20, "save_cooldown_s": 30, "wear_cooldown_s": 10}
# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════════════


def ax(d):
    return round(ORIGIN[0] + d, 4)


def ay(d):
    return round(ORIGIN[1] + d, 4)


def az(d):
    return round(ORIGIN[2] + d, 4)


def at(o):
    return [ax(o[0]), ay(o[1]), az(o[2])]


def blk(dx, dy, dz):
    return f"{ORIGIN[0] + dx} {ORIGIN[1] + dy} {ORIGIN[2] + dz}"


# ------------------------------------------------------------------ skin template geometry (64x64, classic)
BOXES = {  # name: (u, v, w, h, d) of the box's UV origin
    "head": (0, 0, 8, 8, 8), "hat": (32, 0, 8, 8, 8),
    "body": (16, 16, 8, 12, 4), "jacket": (16, 32, 8, 12, 4),
    "rarm": (40, 16, 4, 12, 4), "rsleeve": (40, 32, 4, 12, 4),
    "larm": (32, 48, 4, 12, 4), "lsleeve": (48, 48, 4, 12, 4),
    "rleg": (0, 16, 4, 12, 4), "rpants": (0, 32, 4, 12, 4),
    "lleg": (16, 48, 4, 12, 4), "lpants": (0, 48, 4, 12, 4),
}
OVER = {"head": "hat", "body": "jacket", "rarm": "rsleeve", "larm": "lsleeve", "rleg": "rpants", "lleg": "lpants"}


def face(box, f):
    u, v, w, h, d = BOXES[box]
    return {"top": (u + d, v, w, d), "bottom": (u + d + w, v, w, d), "right": (u, v + d, d, h),
            "front": (u + d, v + d, w, h), "left": (u + d + w, v + d, d, h), "back": (u + 2 * d + w, v + d, w, h)}[f]


def tex(box, f, i, j):
    """texel index (y*64+x) of column i, row j of a face (as drawn in the template)."""
    x, y, w, h = face(box, f)
    assert 0 <= i < w and 0 <= j < h, (box, f, i, j)
    return (y + j) * 64 + x + i


# ------------------------------------------------------------------ the views (what the painter sees)
def view_cells(vid):
    """[(col, row, part, face, i, j)] -- part = base box name; the second layer uses OVER[part] with the same face."""
    c = []

    def put(col0, row0, part, f):
        _, _, w, h = face(part, f)
        for i in range(w):
            for j in range(h):
                c.append((col0 + i, row0 + j, part, f, i, j))
    if vid == "front":
        put(4, 0, "head", "front"); put(4, 8, "body", "front")
        put(0, 8, "rarm", "front"); put(12, 8, "larm", "front")
        put(4, 20, "rleg", "front"); put(8, 20, "lleg", "front")
    elif vid == "back":
        put(4, 0, "head", "back"); put(4, 8, "body", "back")
        put(0, 8, "larm", "back"); put(12, 8, "rarm", "back")
        put(4, 20, "lleg", "back"); put(8, 20, "rleg", "back")
    elif vid == "right":
        put(0, 0, "head", "right"); put(2, 8, "rarm", "right"); put(2, 20, "rleg", "right")
    elif vid == "left":
        put(0, 0, "head", "left"); put(2, 8, "larm", "left"); put(2, 20, "lleg", "left")
    elif vid == "top":
        put(0, 0, "head", "top")
    return c


VIEWS = [("right", 8, 32, "Right side"), ("front", 16, 32, "Front"), ("left", 8, 32, "Left side"),
         ("back", 16, 32, "Back"), ("top", 8, 8, "Head top")]
BANDS = [(0, 8), (8, 20), (20, 32)]   # one text_display per band: head / body + arms / legs


def build_layout():
    views, z = [], az(CANVAS["left_dz"])
    for vid, w, h, name in VIEWS:
        grid = [[None] * w for _ in range(h)]
        for (col, row, part, f, i, j) in view_cells(vid):
            grid[row][col] = [tex(part, f, i, j), tex(OVER[part], f, i, j)]
        bands = [b for b in BANDS if b[0] < h]
        views.append({"id": vid, "name": name, "w": w, "h": h, "z_left": round(z, 4), "cells": grid,
                      "bands": [[a, min(b, h)] for a, b in bands]})
        z -= w * PX + 2 * PX
    # hidden faces derived from the visible ones (dst <- src)
    derive = []

    def cp(part, dst_face, fn, layers=("base", "over")):
        for layer in layers:
            p = part if layer == "base" else OVER[part]
            _, _, w, h = face(p, dst_face)
            for i in range(w):
                for j in range(h):
                    sf, si, sj = fn(i, j)
                    derive.append([tex(p, dst_face, i, j), tex(p, sf, si, sj)])
    # body sides (under the arms): half from the front edge, half from the back edge
    cp("body", "right", lambda i, j: ("back", 7, j) if i < 2 else ("front", 0, j))
    cp("body", "left", lambda i, j: ("front", 7, j) if i < 2 else ("back", 0, j))
    cp("body", "top", lambda i, j: ("front", i, 0), ("base",))
    cp("body", "bottom", lambda i, j: ("front", i, 11), ("base",))
    # inner faces of arms and legs
    for part in ("rarm", "rleg"):
        cp(part, "left", lambda i, j: ("front", 3, j) if i < 2 else ("back", 0, j))
    for part in ("larm", "lleg"):
        cp(part, "right", lambda i, j: ("back", 3, j) if i < 2 else ("front", 0, j))
    for part in ("rarm", "larm", "rleg", "lleg"):
        cp(part, "top", lambda i, j: ("front", i, 0), ("base",))
        cp(part, "bottom", lambda i, j: ("front", i, 11), ("base",))
    cp("head", "bottom", lambda i, j: ("front", i, 7), ("base",))
    base_texels = sorted({tex(p, f, i, j) for p in ("head", "body", "rarm", "larm", "rleg", "lleg")
                          for f in ("top", "bottom", "right", "front", "left", "back")
                          for i in range(face(p, f)[2]) for j in range(face(p, f)[3])})
    # a text display draws a font pixel as 0.025 block at scale 1 and one line is 10 font px -> scale = PX / 0.25
    return {"_doc": "generated by resourcepacks/skinpaint/gen_skinpaint.py -- do not edit by hand",
            "px": PX, "plane_x": ax(CANVAS["plane_dx"]), "y_top": ay(CANVAS["top_dy"]),
            "font_px": round(PX / 10.0, 5), "scale": round(PX / 0.25, 4),
            "views": views, "derive": derive, "base_texels": base_texels,
            "glyphs": {"px": "", "square": "", "empty": "", "swatch": ""},
            "toolbar": {"z_left": az(TOOLBAR["left_dz"]), "y_top": ay(TOOLBAR["top_dy"]), "cell": TOOLBAR["cell"],
                        "tools": [{"col": c, "row": r, "action": a, "icon": i, "tip": t} for (c, r, a, i, t) in TB_TOOLS],
                        "current": {"col": 0, "row": 0, "size": 2}, "shades": {"col": 0, "row": 2},
                        "recent": {"col": 0, "row": 3, "cols": 2, "rows": 4}},
            "strip": {"z_left": az(STRIP["left_dz"]), "y_top": ay(STRIP["top_dy"]), "cell": STRIP["cell"],
                      "cols": STRIP["cols"], "rows": STRIP["rows"], "colors": strip_colors()}}


def build_config():
    P, G = PLACES, PLACES["gallery"]
    return {
        "_doc": [
            "skinpaint.sc places -- generated by resourcepacks/skinpaint/gen_skinpaint.py from its CONFIG block (edit",
            "that and rerun; the example is a wall at x=-79 facing east). The easel wall is at layout.plane_x and",
            "painters face west (their left = +z). Text yaw: -90 = faces east, 0 = faces south.",
            "stage = the painting platform: stepping into this box claims the easel when it is free (step off to claim",
            "again). gallery.slots = mannequin feet on the north wall (facing south), plaques in front of them;",
            "prev_button/next_button = vanilla buttons from jobs/skinpaint-1-walls.json. easel_centre = 'near the",
            "easel' (14 blocks). area = the studio floor: leaving it (lift, teleport, logout) auto-saves unsaved work",
            "as a private skin in 'My skins' and frees the easel. *_s = seconds: release after idle / after this long",
            "off the stage; cooldowns for save and wear."],
        "easel_centre": at(P["easel_centre"]),
        "status": at(P["status"]),
        "labels_y": ay(P["labels_dy"]),
        "preview": {"pos": at(P["preview"]["pos"]), "yaw": P["preview"]["yaw"], "label": at(P["preview"]["label"])},
        "gallery": {
            "slots": [at(s) for s in G["slots"]],
            "plaque_z": az(G["plaque_dz"]), "plaque_y": ay(G["plaque_dy"]),
            "prev_button": [ORIGIN[i] + G["prev_button"][i] for i in range(3)],
            "next_button": [ORIGIN[i] + G["next_button"][i] for i in range(3)],
            "prev_label": at(G["prev_label"]), "next_label": at(G["next_label"]),
            "title": at(G["title"]), "page": at(G["page"]),
        },
        **TIMING,
        "stage": {"min": at(P["stage"]["min"]), "max": at(P["stage"]["max"])},
        "area": {"min": at(P["area"]["min"]), "max": at(P["area"]["max"])},
    }


# ------------------------------------------------------------------ templates
def img_to_list(im):
    im = im.convert("RGBA")
    out = []
    for y in range(64):
        for x in range(64):
            r, g, b, a = im.getpixel((x, y))
            out.append(0 if a < 128 else (0xFF000000 | (r << 16) | (g << 8) | b))
    return out


def paint_face(im, part, f, fn):
    x, y, w, h = face(part, f)
    for i in range(w):
        for j in range(h):
            c = fn(i, j)
            if c:
                im.putpixel((x + i, y + j), c)


def hexc(s):
    s = s.lstrip("#")
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), 255)


def blank_skin(clothes):
    im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    skin, hair, shirt, pants, shoes = hexc("#F1C9A5"), hexc("#5A3A22"), hexc("#FFFFFF"), hexc("#3B5E9A"), hexc("#4A4A52")
    for part in ("head", "body", "rarm", "larm", "rleg", "lleg"):
        for f in ("top", "bottom", "right", "front", "left", "back"):
            if clothes and part == "body":
                col = shirt
            elif clothes and part in ("rleg", "lleg"):
                col = pants
            else:
                col = skin
            paint_face(im, part, f, lambda i, j: col)
            if clothes and part in ("rarm", "larm") and f != "bottom":
                paint_face(im, part, f, lambda i, j: shirt if (j < 4 or f == "top") else None)
            if clothes and part in ("rleg", "lleg") and f in ("right", "front", "left", "back"):
                paint_face(im, part, f, lambda i, j: shoes if j >= 10 else None)
    if clothes:
        for f in ("top", "right", "left", "back"):
            paint_face(im, "head", f, lambda i, j: hair)
        paint_face(im, "head", "front", lambda i, j: hair if j < 2 else None)
    # face
    for (i, j, c) in ((1, 4, "#FFFFFF"), (2, 4, "#3A6FD8"), (5, 4, "#3A6FD8"), (6, 4, "#FFFFFF"), (3, 6, "#C98A7A"), (4, 6, "#C98A7A")):
        paint_face(im, "head", "front", lambda ii, jj, i=i, j=j, c=c: hexc(c) if (ii, jj) == (i, j) else None)
    return im


def build_templates():
    t = {"blank": {"name": "Blank figure", "img": img_to_list(blank_skin(False))},
         "basic": {"name": "Basic figure", "img": img_to_list(blank_skin(True))}}
    lst_path = os.path.join(STUDIO, "skins.json")
    if not os.path.exists(lst_path):
        print("note: no resourcepacks/studio/skins.json -- run resourcepacks/studio/gen_studio_pack.py first to add the "
              "studio skins as templates (continuing with blank + basic only)")
        return t
    for s in json.load(open(lst_path, encoding="utf-8")):
        path = os.path.join(STUDIO, s["file"])
        if os.path.exists(path):
            t[s["id"]] = {"name": s.get("name_en") or s["id"], "img": img_to_list(Image.open(path))}
    return t


# ------------------------------------------------------------------ toolbar icons (16x16, drawn on a pink-rimmed tile)
PINK, DPINK, BROWN, GOLD, INK, BLUE = (255, 79, 160, 255), (200, 40, 120, 255), (140, 80, 55, 255), (232, 193, 90, 255), (70, 40, 60, 255), (60, 150, 230, 255)
DIG = {"1": ["010", "110", "010", "010", "111"], "2": ["110", "001", "010", "100", "111"]}


def _digit(d, ch, x, y, col):
    for j, row in enumerate(DIG[ch]):
        for i, c in enumerate(row):
            if c == "1":
                d.point((x + i, y + j), fill=col)


def ic_brush(d, im):
    for k in range(7):
        d.point((3 + k, 12 - k), fill=BROWN); d.point((4 + k, 12 - k), fill=BROWN)
    d.rectangle((10, 4, 11, 5), fill=GOLD)
    d.polygon([(11, 3), (13, 1), (14, 2), (12, 4)], fill=PINK)


def ic_big(d, im):
    for k in range(6):
        d.rectangle((2 + k, 11 - k, 4 + k, 13 - k), fill=BROWN)
    d.rectangle((8, 4, 10, 6), fill=GOLD)
    d.ellipse((10, 1, 14, 5), fill=PINK)


def ic_fill(d, im):
    d.polygon([(3, 6), (9, 3), (12, 9), (6, 12)], fill=(120, 170, 220, 255), outline=INK)
    d.line((5, 5, 9, 3), fill=INK)
    d.rectangle((12, 10, 13, 13), fill=PINK); d.point((12, 9), fill=PINK)


def ic_pick(d, im):
    for k in range(7):
        d.point((3 + k, 12 - k), fill=(150, 150, 170, 255)); d.point((4 + k, 12 - k), fill=(190, 190, 205, 255))
    d.rectangle((9, 3, 12, 6), fill=INK)
    d.point((2, 13), fill=PINK); d.point((3, 13), fill=PINK); d.point((2, 12), fill=PINK)


def ic_erase(d, im):
    d.polygon([(2, 10), (8, 4), (13, 9), (7, 15)], fill=(255, 170, 200, 255), outline=INK)
    d.polygon([(2, 10), (5, 7), (10, 12), (7, 15)], fill=(250, 250, 250, 255), outline=INK)


def ic_mirror(d, im):
    for y in range(2, 14, 2):
        d.point((7, y), fill=INK); d.point((8, y + 1), fill=INK)
    d.polygon([(6, 4), (2, 8), (6, 12)], fill=PINK)
    d.polygon([(9, 4), (13, 8), (9, 12)], fill=(255, 190, 220, 255))


def ic_layer(d, im, n):
    d.rectangle((5, 2, 13, 10), fill=(200, 190, 200, 255), outline=INK)
    d.rectangle((2, 5, 10, 13), fill=(255, 255, 255, 255) if n == "1" else PINK, outline=INK)
    _digit(d, n, 5, 7, INK if n == "1" else (255, 255, 255, 255))


def ic_undo(d, im):
    d.arc((3, 3, 13, 13), 200, 90, fill=INK, width=2)
    d.polygon([(2, 4), (7, 4), (4, 8)], fill=PINK)


def ic_templates(d, im):
    for (x, y, c) in ((2, 2, PINK), (9, 2, BLUE), (2, 9, GOLD), (9, 9, (140, 200, 120, 255))):
        d.rectangle((x + 1, y, x + 3, y + 2), fill=(240, 200, 170, 255))
        d.rectangle((x, y + 3, x + 4, y + 5), fill=c)


def ic_mine(d, im):
    d.rectangle((6, 2, 9, 5), fill=(240, 200, 170, 255))
    d.rectangle((5, 6, 10, 10), fill=PINK); d.rectangle((6, 11, 9, 13), fill=BLUE)
    d.point((11, 3), fill=DPINK); d.point((13, 3), fill=DPINK); d.rectangle((11, 4, 13, 4), fill=DPINK); d.point((12, 5), fill=DPINK)


def ic_save(d, im):
    d.rectangle((2, 2, 13, 13), fill=PINK, outline=INK)
    d.rectangle((5, 2, 10, 6), fill=(245, 245, 250, 255)); d.rectangle((8, 3, 9, 5), fill=INK)
    d.rectangle((4, 9, 11, 13), fill=(255, 255, 255, 255))


def ic_done(d, im):
    d.rectangle((3, 2, 9, 13), fill=BROWN); d.point((8, 8), fill=GOLD)
    d.polygon([(10, 5), (14, 8), (10, 11)], fill=PINK); d.rectangle((9, 7, 11, 9), fill=PINK)


def ic_custom(d, im):
    for k, c in enumerate([(229, 57, 53), (251, 140, 0), (253, 216, 53), (67, 160, 71), (30, 136, 229), (142, 36, 170)]):
        d.rectangle((2 + k * 2, 3, 3 + k * 2, 12), fill=c + (255,))
    d.rectangle((5, 6, 10, 9), fill=(255, 255, 255, 255))
    d.point((6, 7), fill=INK); d.point((8, 7), fill=INK); d.point((7, 8), fill=INK); d.point((9, 8), fill=INK)


def ic_clear(d, im):
    d.rectangle((4, 5, 11, 13), fill=(200, 200, 210, 255), outline=INK)
    d.rectangle((3, 3, 12, 4), fill=INK); d.rectangle((6, 2, 9, 2), fill=INK)
    for x in (6, 9):
        d.line((x, 7, x, 11), fill=INK)


def ic_zoom(d, im):
    d.ellipse((2, 2, 10, 10), fill=(220, 240, 255, 255), outline=INK, width=2)
    d.line((9, 9, 13, 13), fill=BROWN, width=3)
    d.rectangle((5, 5, 7, 7), fill=PINK)


TOOL_ICONS = {"zoom": ic_zoom, "brush": ic_brush, "big": ic_big, "fill": ic_fill, "pick": ic_pick, "erase": ic_erase, "mirror": ic_mirror,
              "layer1": lambda d, im: ic_layer(d, im, "1"), "layer2": lambda d, im: ic_layer(d, im, "2"),
              "undo": ic_undo, "templates": ic_templates, "mine": ic_mine, "save": ic_save, "done": ic_done,
              "custom": ic_custom, "clear": ic_clear}

# The toolbar grid (cells of TOOLBAR["cell"] blocks, col 0 = the painter's left): cols 0-1 = the current colour (2x2),
# lighter + darker, 8 recent colours; cols 3-4 = the tool icons (item_display quads). The strip = 48 x 4 swatches.
TB_TOOLS = [  # col, row, action, icon, tooltip (the action bar text while aiming at it)
    (3, 0, "tool:brush", "brush", "Brush"), (4, 0, "tool:big", "big", "Thick brush (2x2)"),
    (3, 1, "tool:fill", "fill", "Bucket - fills an area"), (4, 1, "tool:pick", "pick", "Eyedropper - takes a colour from the painting"),
    (3, 2, "tool:erase", "erase", "Eraser (layer 2)"), (4, 2, "mirror", "mirror", "Mirror - one side paints the other too"),
    (3, 3, "layer", "layer1", "Layers: automatic (paint what you see) · 1 body · 2 clothes & hair"), (4, 3, "undo", "undo", "Undo"),
    (3, 4, "templates", "templates", "Starting templates"), (4, 4, "mine", "mine", "My skins"),
    (3, 5, "save", "save", "✦ Save and wear"), (4, 5, "done", "done", "Finish and free the easel"),
    (3, 6, "custom", "custom", "Your own colour (hex code)"), (4, 6, "clear", "clear", "Clear the painting"),
    (3, 7, "zoom", "zoom", "Magnifier — click it, then a spot in the painting (3x). Again = back")]


def _hsl(h, s, l):
    r, g, b = colorsys.hls_to_rgb(h / 360.0, l, s)
    return "#%02X%02X%02X" % (round(r * 255), round(g * 255), round(b * 255))


def strip_colors():
    """rows x cols of '#RRGGBB': 36 hues in 4 shades, then greys / skin tones / hair / fashion basics."""
    shades = [(0.70, 0.86), (0.80, 0.70), (0.90, 0.52), (0.75, 0.30)]
    extra = [
        ["#FFFFFF", "#EBEBEB", "#D6D6D6", "#BFBFBF", "#A6A6A6", "#8C8C8C", "#737373", "#595959", "#404040", "#2B2B2B", "#171717", "#000000"],
        ["#FFE3D3", "#FFDBC4", "#F6CBA8", "#F1C9A5", "#E8B48C", "#E0AC69", "#D09A6A", "#C68642", "#A86B3C", "#8D5524", "#6E4226", "#4A2C1A"],
        ["#1B1B1B", "#3B2A1A", "#5A3A22", "#6B4423", "#8B4A2B", "#B5562A", "#D98C3F", "#E6C35C", "#F2E3B3", "#F7A1C4", "#B983FF", "#5FA8E8"],
        ["#FF4FA0", "#FF7AC6", "#F9A8D4", "#C9A7FF", "#5BCEFA", "#F5A9B8", "#3B5E9A", "#8D8455", "#E8C15A", "#C5C5CE", "#8E1B3F", "#1E2A5A"]]
    rows = []
    for r, (sat, lig) in enumerate(shades):
        rows.append([_hsl(c * 10, sat, lig) for c in range(36)] + extra[r])
    return rows


# ------------------------------------------------------------------ pack: pixel font + kit items + toolbar icons
def build_pack():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    A = os.path.join(OUT, "assets", NS)
    for d in ("font", "textures/font", "textures/item", "models/item", "items"):
        os.makedirs(os.path.join(A, d), exist_ok=True)
    Image.new("RGBA", (10, 10), (255, 255, 255, 255)).save(os.path.join(A, "textures", "font", "px.png"))
    sw = Image.new("RGBA", (10, 10), (0, 0, 0, 0))   # swatch: 8x8 inked at x 1..8 of a 10-px cell -> advance exactly 10
    ImageDraw.Draw(sw).rectangle((1, 1, 8, 8), fill=(255, 255, 255, 255))
    sw.save(os.path.join(A, "textures", "font", "swatch.png"))
    # height 10 + ascent 7: the glyph covers one text-display line (9 px line height + 1 px spacing) exactly
    json.dump({"providers": [
        {"type": "bitmap", "file": f"{NS}:font/px.png", "height": 10, "ascent": 7, "chars": [""]},
        {"type": "bitmap", "file": f"{NS}:font/swatch.png", "height": 10, "ascent": 7, "chars": [""]},
        {"type": "space", "advances": {"": -1, "": 10, " ": 4}}]},
        open(os.path.join(A, "font", "canvas.json"), "w"))

    def icon(name, draw):
        im = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        draw(ImageDraw.Draw(im), im)
        im.save(os.path.join(A, "textures", "item", name + ".png"))
        json.dump({"parent": "minecraft:item/handheld", "textures": {"layer0": f"{NS}:item/{name}"}},
                  open(os.path.join(A, "models", "item", name + ".json"), "w"))
        json.dump({"model": {"type": "minecraft:model", "model": f"{NS}:item/{name}"}},
                  open(os.path.join(A, "items", name + ".json"), "w"))

    def brush(d, im):   # a diagonal brush: cherry handle, gold ferrule, pink tip
        for k in range(9):
            d.point((2 + k, 13 - k), fill=(150, 80, 60, 255)); d.point((3 + k, 13 - k), fill=(120, 60, 45, 255))
        for k in range(2):
            d.point((11 + k, 4 - k), fill=(232, 193, 90, 255)); d.point((12 + k, 4 - k), fill=(200, 160, 60, 255))
        for (x, y) in ((13, 2), (14, 1), (13, 1), (14, 2), (15, 0), (14, 0), (15, 1)):
            d.point((x, y), fill=(255, 79, 160, 255))

    def palette(d, im):
        d.ellipse((1, 3, 14, 13), fill=(222, 184, 135, 255), outline=(150, 110, 70, 255))
        d.ellipse((9, 8, 12, 11), fill=(0, 0, 0, 0))
        for (x, y, c) in ((4, 5, (229, 57, 53)), (7, 4, (253, 216, 53)), (10, 5, (30, 136, 229)), (4, 9, (67, 160, 71)), (6, 11, (255, 79, 160))):
            d.rectangle((x, y, x + 1, y + 1), fill=c + (255,))

    def menu(d, im):
        d.rectangle((2, 1, 13, 14), fill=(255, 245, 250, 255), outline=(255, 79, 160, 255))
        for y in (4, 7, 10):
            d.line((4, y, 11, y), fill=(160, 100, 140, 255))
        d.point((12, 12), fill=(255, 79, 160, 255))
    icon("brush", brush); icon("palette", palette); icon("menu", menu)   # the app gives only the brush now
    for name, fn in TOOL_ICONS.items():
        tile = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        d = ImageDraw.Draw(tile)
        d.rounded_rectangle((0, 0, 15, 15), radius=3, fill=(255, 240, 247, 255), outline=(255, 122, 198, 255))
        fn(d, tile)
        tile.save(os.path.join(A, "textures", "item", "tb_" + name + ".png"))
        fc = {"texture": "#t", "uv": [0, 0, 16, 16]}
        json.dump({"textures": {"t": f"{NS}:item/tb_{name}", "particle": f"{NS}:item/tb_{name}"},
                   "elements": [{"from": [0, 0, 8], "to": [16, 16, 8], "faces": {"north": fc, "south": fc}}]},
                  open(os.path.join(A, "models", "item", "tb_" + name + ".json"), "w"))
        json.dump({"model": {"type": "minecraft:model", "model": f"{NS}:item/tb_{name}"}},
                  open(os.path.join(A, "items", "tb_" + name + ".json"), "w"))
    sheet = Image.new("RGBA", (len(TOOL_ICONS) * 72, 72), (255, 255, 255, 255))
    for k, name in enumerate(TOOL_ICONS):
        im = Image.open(os.path.join(A, "textures", "item", "tb_" + name + ".png")).resize((64, 64), Image.NEAREST)
        sheet.alpha_composite(im, (k * 72 + 4, 4))
    os.makedirs(PREV, exist_ok=True)
    sheet.save(os.path.join(PREV, "skinpaint_toolbar_icons.png"))
    json.dump({"pack": {"description": "Pink Golem skin easel", "min_format": 88, "max_format": 88}},
              open(os.path.join(OUT, "pack.mcmeta"), "w"))
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
        for d, _, fs in sorted(os.walk(OUT)):
            for f in sorted(fs):
                z.write(os.path.join(d, f), os.path.relpath(os.path.join(d, f), OUT))
    return ZIP


# ------------------------------------------------------------------ the build (blocks only; the app spawns entities)
def build_walls_job():
    """The easel wall (light grey paper in a pink frame + the white toolbar panel) and the creators' gallery wall
    (white, pink frame, three plinths, lights, the page buttons)."""
    c = []
    # EASEL WALL (dx 0): paper dz -17..-5 (the canvas spans dz -4.45..-16.61), toolbar panel dz -3..-1, pink frame
    c.append(f"fill {blk(0, 1, -17)} {blk(0, 9, -5)} light_gray_concrete")
    c.append(f"fill {blk(0, 9, -18)} {blk(0, 9, 0)} pink_concrete")                 # top rail
    c.append(f"fill {blk(0, 1, -17)} {blk(0, 1, -5)} pink_concrete")                # under the canvas (view labels)
    c.append(f"fill {blk(0, 1, -18)} {blk(0, 9, -18)} pink_concrete")               # north edge
    c.append(f"fill {blk(0, 1, -4)} {blk(0, 9, -4)} pink_concrete")                 # between canvas and toolbar
    c.append(f"fill {blk(0, 1, -3)} {blk(0, 8, -1)} white_concrete")                # the toolbar panel
    c.append(f"fill {blk(0, 1, 0)} {blk(0, 9, 0)} pink_concrete")                   # its south edge
    # GALLERY WALL (dz -20, facing south): white, pink frame; plinths + ceiling lights for the three mannequins
    c.append(f"fill {blk(1, 1, -20)} {blk(12, 6, -20)} white_concrete")
    c.append(f"fill {blk(1, 6, -20)} {blk(12, 6, -20)} pink_concrete")
    c.append(f"fill {blk(1, 1, -20)} {blk(1, 6, -20)} pink_concrete")
    c.append(f"fill {blk(12, 1, -20)} {blk(12, 6, -20)} pink_concrete")
    for s in PLACES["gallery"]["slots"]:
        dx = int(s[0] // 1)
        c.append(f"setblock {blk(dx, 1, -19)} smooth_quartz")
        c.append(f"setblock {blk(dx, 9, -19)} end_rod[facing=down]")
    for key in ("prev_button", "next_button"):                                        # the app polls these
        b = PLACES["gallery"][key]
        c.append(f"setblock {blk(*b)} cherry_button[face=wall,facing=south]")
    for (dx, dz) in ((4, -16), (4, -10), (4, -4), (7, -18)):
        c.append(f"execute if block {blk(dx, 8, dz)} air run setblock {blk(dx, 8, dz)} light[level=13]")
    return c


def build_stage_job():
    """A 2-high painting stage in front of the easel so the painter's eyes are at the canvas middle, wide stairs from
    the east, a glass rail. Stepping onto it gives the brush (the preview mannequin stands on it too)."""
    c = []
    c.append(f"fill {blk(3, 1, -17)} {blk(7, 1, 0)} smooth_quartz")
    c.append(f"fill {blk(3, 2, -17)} {blk(7, 2, 0)} cherry_planks")                 # surface: feet at dy 3
    c.append(f"fill {blk(3, 2, -17)} {blk(3, 2, 0)} pink_concrete")                 # the lip facing the easel
    c.append(f"fill {blk(8, 1, -14)} {blk(8, 1, -11)} cherry_stairs[facing=west]")  # wide stairs from the east
    # glass rail on the east edge (except the stairs) and on both ends
    c.append(f"fill {blk(7, 3, -16)} {blk(7, 3, -15)} glass_pane[north=true,south=true]")
    c.append(f"fill {blk(7, 3, -10)} {blk(7, 3, -1)} glass_pane[north=true,south=true]")
    c.append(f"setblock {blk(7, 3, 0)} glass_pane[north=true,west=true]")
    c.append(f"fill {blk(4, 3, 0)} {blk(6, 3, 0)} glass_pane[east=true,west=true]")
    c.append(f"setblock {blk(3, 3, 0)} glass_pane[east=true]")
    c.append(f"setblock {blk(7, 3, -17)} glass_pane[south=true,west=true]")
    c.append(f"fill {blk(4, 3, -17)} {blk(6, 3, -17)} glass_pane[east=true,west=true]")
    c.append(f"setblock {blk(3, 3, -17)} glass_pane[east=true]")
    c.append(f"setblock {blk(7, 3, -14)} air")                                        # the stairs' opening
    for (dx, dz) in ((5, -16), (5, -8), (5, -1)):
        c.append(f"execute if block {blk(dx, 7, dz)} air run setblock {blk(dx, 7, dz)} light[level=14]")
    return c


def write_jobs():
    os.makedirs(JOBS, exist_ok=True)
    out = []
    for name, cmds in (("skinpaint-1-walls", build_walls_job()), ("skinpaint-2-stage", build_stage_job())):
        p = os.path.join(JOBS, name + ".json")
        json.dump(cmds, open(p, "w"))
        out.append(os.path.relpath(p, ROOT).replace(os.sep, "/"))
    return out


# ------------------------------------------------------------------ mapping check picture
def preview(layout, templates):
    S = 6
    ids = ["basic"] + [k for k in templates if k not in ("blank", "basic")][:4]
    W = sum(v["w"] for v in layout["views"]) * S + 4 * 2 * S + 20
    im = Image.new("RGBA", (W, len(ids) * (34 * S) + 10), (200, 200, 205, 255))
    d = ImageDraw.Draw(im)
    for r, tid in enumerate(ids):
        img = templates[tid]["img"]
        x0 = 10
        for v in layout["views"]:
            for row in range(v["h"]):
                for col in range(v["w"]):
                    cell = v["cells"][row][col]
                    if not cell:
                        continue
                    b, o = cell
                    c = img[o] if img[o] else img[b]
                    rgb = ((c >> 16) & 255, (c >> 8) & 255, c & 255, 255)
                    d.rectangle((x0 + col * S, 5 + r * 34 * S + row * S, x0 + col * S + S - 1,
                                 5 + r * 34 * S + row * S + S - 1), fill=rgb)
            x0 += v["w"] * S + 2 * S
    os.makedirs(PREV, exist_ok=True)
    out = os.path.join(PREV, "skinpaint_views.png")
    im.save(out)
    return out


if __name__ == "__main__":
    os.makedirs(DATA, exist_ok=True)
    layout = build_layout()
    templates = build_templates()
    # every template must keep the base layer opaque (the easel never erases base texels)
    for k, t in templates.items():
        bad = [i for i in layout["base_texels"] if not t["img"][i]]
        if bad:
            print("warning: template", k, "has", len(bad), "transparent base texels -> filled with its head front colour")
            fill = t["img"][8 * 64 + 8 + 64 * 7] or 0xFFF1C9A5
            for i in bad:
                t["img"][i] = fill
    json.dump(layout, open(os.path.join(DATA, "layout.json"), "w"))
    json.dump(templates, open(os.path.join(DATA, "templates.json"), "w"))
    json.dump(build_config(), open(os.path.join(DATA, "config.json"), "w"), indent=1)
    z = build_pack()
    jobs = write_jobs()
    p = preview(layout, templates)
    last = layout["views"][-1]
    print(json.dumps({"views": len(layout["views"]), "derive": len(layout["derive"]), "templates": list(templates),
                      "pack": os.path.relpath(z, ROOT), "jobs": jobs, "preview": os.path.relpath(p, ROOT),
                      "canvas_z": [layout["views"][0]["z_left"], round(last["z_left"] - last["w"] * PX, 3)],
                      "canvas_y": [round(layout["y_top"] - 32 * PX, 3), layout["y_top"]]}))
