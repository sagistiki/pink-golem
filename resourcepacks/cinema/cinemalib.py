"""cinemalib.py — generic toolkit for in-game silent films (server-side "screen = item-model frames" scheme, see
`skill/pinkgolem/reference/cinema-and-gallery.md` for the full write-up: no client mods, no map art, no shaders).

A film is a Python module (see film_demo.py) that draws 4:3 pictures with `Scene`, turns them into finished 256×144
silent-film frames with `finish()`, and a music module (see music_demo.py) that renders an Ogg with the synth
helpers below. gen_cinema_pack.py glues one or more films into a resource pack + films.json for `scarpet-apps/cinema.sc`.

Sections:
  1. Canvas constants and the sepia palette
  2. Scene — a supersampled grayscale 4:3 drawing surface (picture-pixel coordinates, camera offset, puppets)
  3. Silent-film post-fx: vignette, flicker, grain, scratch, iris, letterbox, quantise to ≤32 colours
  4. RTL (e.g. Hebrew/Arabic) text without raqm (manual visual reordering), fonts, word-wrap, intertitle cards
  5. FrameStore — content-hash dedupe of frames into unique model ids
  6. Pack — resource-pack writer (textures / models / items / sounds.json / pack.mcmeta / zip)
  7. Synth — tiny additive synth toolkit (numpy): notes, envelopes, piano / pad / pedal / tremolo / boom, reverb, mixer, Ogg writer
  8. Contact sheet for review
"""
import hashlib
import io
import json
import math
import os
import re
import shutil
import zipfile

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# ----------------------------------------------------------------------------------------------------------------------
# 1. Canvas constants and palette
# ----------------------------------------------------------------------------------------------------------------------
W, H = 256, 144            # texture canvas: 16:9, both multiples of 16 (mipmaps)
PIC_W, PIC_H = 192, 144    # the 4:3 picture inside the letterbox
PIC_X = (W - PIC_W) // 2   # black pillar width (32 px each side)
SS = 2                     # supersampling factor for drawing (antialiased silhouettes after downsampling)
N_COLOURS = 32             # ≤ 32 colours per frame (sepia ramp; index 0 = black)


def sepia_palette(n=N_COLOURS):
    """A warm silent-film ramp: black → deep brown → sepia → cream. Returns a flat [r,g,b,...] list of n entries."""
    stops = [(0.0, (4, 3, 2)), (0.45, (96, 66, 38)), (0.8, (200, 168, 118)), (1.0, (244, 232, 204))]
    pal = []
    for i in range(n):
        t = i / (n - 1)
        for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
            if t0 <= t <= t1:
                k = (t - t0) / (t1 - t0)
                pal += [int(round(c0[j] + (c1[j] - c0[j]) * k)) for j in range(3)]
                break
    return pal


PALETTE = sepia_palette()


# ----------------------------------------------------------------------------------------------------------------------
# 2. Scene — drawing surface
# ----------------------------------------------------------------------------------------------------------------------
def ease(t):
    """Smoothstep ease-in/out for t in [0,1]."""
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


def lerp(a, b, t):
    return a + (b - a) * t


def rotate_pts(pts, ox, oy, deg):
    """Rotate points around (ox, oy) by deg (screen coords, +y down, positive = clockwise)."""
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return [(ox + (x - ox) * c - (y - oy) * s, oy + (x - ox) * s + (y - oy) * c) for x, y in pts]


class Scene:
    """A grayscale 4:3 picture drawn at SS× resolution. All coordinates are picture pixels (0..192 × 0..144, floats OK)
    and are shifted by the camera offset, so a slow camera drift is just `Scene(cam=(dx, dy))`."""

    def __init__(self, bg=200, cam=(0.0, 0.0)):
        self.im = Image.new("L", (PIC_W * SS, PIC_H * SS), int(bg))
        self.d = ImageDraw.Draw(self.im)
        self.cx, self.cy = cam

    # -- coordinate helpers -------------------------------------------------------------------------------------------
    def p(self, x, y):
        return ((x - self.cx) * SS, (y - self.cy) * SS)

    def pts(self, pts):
        return [self.p(x, y) for x, y in pts]

    # -- primitives ---------------------------------------------------------------------------------------------------
    def poly(self, pts, fill, outline=None, width=1):
        self.d.polygon(self.pts(pts), fill=int(fill), outline=None if outline is None else int(outline),
                       width=max(1, int(width * SS)))

    def ellipse(self, cx, cy, rx, ry, fill, outline=None, width=1):
        x0, y0 = self.p(cx - rx, cy - ry)
        x1, y1 = self.p(cx + rx, cy + ry)
        self.d.ellipse([x0, y0, x1, y1], fill=int(fill), outline=None if outline is None else int(outline),
                       width=max(1, int(width * SS)))

    def rect(self, x0, y0, x1, y1, fill, outline=None, width=1):
        a, b = self.p(min(x0, x1), min(y0, y1))
        c, e = self.p(max(x0, x1), max(y0, y1))
        self.d.rectangle([a, b, c, e], fill=int(fill), outline=None if outline is None else int(outline),
                         width=max(1, int(width * SS)))

    def line(self, pts, fill, width=1.0):
        self.d.line(self.pts(pts), fill=int(fill), width=max(1, int(round(width * SS))), joint="curve")

    def dot(self, x, y, r, fill):
        self.ellipse(x, y, r, r, fill)

    def gradient(self, y0, y1, g0, g1, x0=None, x1=None):
        """Vertical gradient band from picture row y0 (gray g0) to y1 (gray g1); full width unless x0/x1 given."""
        x0 = -PIC_W if x0 is None else x0
        x1 = 2 * PIC_W if x1 is None else x1
        top = int(round((y0 - self.cy) * SS))
        bot = int(round((y1 - self.cy) * SS))
        n = max(1, bot - top)
        strip = np.linspace(g0, g1, n).astype(np.uint8).reshape(n, 1)
        band = Image.fromarray(np.repeat(strip, int((x1 - x0) * SS), axis=1), "L")
        self.im.paste(band, (int(round((x0 - self.cx) * SS)), top))
        self.d = ImageDraw.Draw(self.im)

    def text(self, x, y, s, font, fill, anchor="mm"):
        """Draw text (already in visual order — use `visual()` for Hebrew) at picture coords."""
        self.d.text(self.p(x, y), s, font=font, fill=int(fill), anchor=anchor)

    # -- puppets ------------------------------------------------------------------------------------------------------
    def figure(self, x, feet_y, h, fill=0, arm_l=0.0, arm_r=0.0, legs=0.15, dress=False, hair=False, cap=False,
               lean=0.0, flip=False, forearm_l=None, forearm_r=None):
        """A bold silhouette puppet standing on (x, feet_y) with height h.
        arm_l / arm_r: arm angle in degrees from straight down (0) — 90 = horizontal out, 180 = straight up.
        Left arm swings toward -x, right arm toward +x; `flip` mirrors the whole figure. forearm_*: extra bend (deg).
        legs: half-spread of the legs as a fraction of h. dress: skirt instead of legs. hair: long hair. cap: flat cap.
        lean: torso lean in degrees (positive = toward +x)."""
        sgn = -1 if flip else 1
        head_r = 0.075 * h
        shoulder_y = feet_y - 0.72 * h
        hip_y = feet_y - 0.42 * h
        head_y = shoulder_y - head_r * 1.4
        tw = 0.11 * h                                  # half torso width at shoulder
        hw = 0.09 * h                                  # half torso width at hip
        lean_dx = math.tan(math.radians(lean)) * (feet_y - hip_y)
        sx = x + lean_dx * 1.7                          # shoulder x after lean
        hx = x + lean_dx * 0.5

        def arm(side, ang, bend):
            ang = ang * (1 if side < 0 else 1)
            L = 0.30 * h
            ax = sx + side * sgn * tw * 0.8
            ay = shoulder_y + 0.02 * h
            a = math.radians(ang)
            ex, ey = ax + side * sgn * math.sin(a) * L * 0.55, ay + math.cos(a) * L * 0.55
            if bend is None:
                hx_, hy_ = ax + side * sgn * math.sin(a) * L, ay + math.cos(a) * L
            else:
                b = math.radians(ang + bend)
                hx_, hy_ = ex + side * sgn * math.sin(b) * L * 0.45, ey + math.cos(b) * L * 0.45
            self.line([(ax, ay), (ex, ey), (hx_, hy_)], fill, width=0.055 * h)
            self.dot(hx_, hy_, 0.025 * h, fill)

        # legs / dress first (behind the torso)
        if dress:
            self.poly([(hx - hw, hip_y), (hx + hw, hip_y), (x + 0.2 * h, feet_y), (x - 0.2 * h, feet_y)], fill)
        else:
            for side in (-1, 1):
                self.line([(hx + side * hw * 0.5, hip_y + 0.02 * h), (x + side * legs * h, feet_y)], fill, width=0.075 * h)
        # torso
        self.poly([(sx - tw, shoulder_y), (sx + tw, shoulder_y), (hx + hw, hip_y + 0.02 * h), (hx - hw, hip_y + 0.02 * h)], fill)
        self.ellipse(sx, shoulder_y + 0.01 * h, tw, 0.04 * h, fill)   # round shoulders
        # arms
        arm(-1, arm_l, forearm_l)
        arm(1, arm_r, forearm_r)
        # neck + head
        self.line([(sx, shoulder_y), (sx + lean_dx * 0.3, head_y)], fill, width=0.05 * h)
        hxx = sx + lean_dx * 0.3
        self.dot(hxx, head_y, head_r, fill)
        if hair:
            self.poly([(hxx - head_r * 0.9, head_y - head_r * 0.3), (hxx + head_r * 0.9, head_y - head_r * 0.3),
                       (hxx + head_r * 1.2, head_y + head_r * 2.4), (hxx - head_r * 1.2, head_y + head_r * 2.4)], fill)
            self.dot(hxx, head_y - head_r * 0.2, head_r * 1.05, fill)
        if cap:
            self.ellipse(hxx, head_y - head_r * 0.85, head_r * 1.35, head_r * 0.45, fill)

    def gull(self, x, y, span, flap, fill=0):
        """A distant seagull: two arcs. flap in [0,1] moves the wing tips up/down."""
        dy = (flap - 0.5) * span * 0.6
        self.line([(x - span / 2, y + dy), (x - span * 0.2, y - span * 0.1), (x, y), (x + span * 0.2, y - span * 0.1),
                   (x + span / 2, y + dy)], fill, width=max(0.6, span * 0.08))


# ----------------------------------------------------------------------------------------------------------------------
# 3. Post-fx → finished frame
# ----------------------------------------------------------------------------------------------------------------------
_VIGNETTE = None


def _vignette_mask(strength):
    global _VIGNETTE
    if _VIGNETTE is None:
        yy, xx = np.mgrid[0:PIC_H, 0:PIC_W]
        nx = (xx - PIC_W / 2) / (PIC_W / 2)
        ny = (yy - PIC_H / 2) / (PIC_H / 2)
        r = np.sqrt(nx * nx + ny * ny) / math.sqrt(2)
        _VIGNETTE = r
    return 1.0 - strength * np.clip(_VIGNETTE - 0.25, 0, 1) ** 1.6


def finish(pic, seed=0, iris=1.0, flicker=0.10, grain=5.0, scratch_p=0.10, vignette=0.7, contrast=1.08):
    """Turn a Scene (or any 'L' image of the picture at 1× or SS×) into a finished palette frame 256×144:
    downsample, contrast, vignette, flicker, grain, occasional scratch/dust, iris (0..1, 1 = open), letterbox, quantise.
    Deterministic for a given (picture, seed) — so identical held frames dedupe to one model."""
    im = pic.im if isinstance(pic, Scene) else pic
    if im.size != (PIC_W, PIC_H):
        im = im.resize((PIC_W, PIC_H), Image.LANCZOS)
    a = np.asarray(im, dtype=np.float32) / 255.0
    rng = np.random.default_rng(seed)
    # contrast around mid-gray, a touch of lift in the blacks like old print stock
    a = np.clip((a - 0.5) * contrast + 0.5, 0, 1)
    a = a * _vignette_mask(vignette)
    a = a * (1.0 - flicker * rng.random())
    if grain > 0:   # coarse grain: 2×2 blocks so it reads as film grain, not pixel noise, and compresses better
        g = rng.normal(0, grain / 255.0, (PIC_H // 2, PIC_W // 2)).astype(np.float32)
        a = a + np.kron(g, np.ones((2, 2), np.float32))
    if rng.random() < scratch_p:   # a vertical scratch: thin, slightly wandering, light or dark
        x = int(rng.integers(8, PIC_W - 8))
        y0 = int(rng.integers(0, PIC_H // 2))
        y1 = int(rng.integers(y0 + 20, PIC_H + 1))
        val = 0.85 if rng.random() < 0.6 else 0.05
        for y in range(y0, min(y1, PIC_H)):
            xs = x + int(round(math.sin(y * 0.15 + seed) * 0.8))
            if 0 <= xs < PIC_W:
                a[y, xs] = a[y, xs] * 0.4 + val * 0.6
    for _ in range(int(rng.integers(0, 3))):   # dust specks
        x, y = int(rng.integers(2, PIC_W - 2)), int(rng.integers(2, PIC_H - 2))
        a[y:y + 2, x:x + 2] *= 0.35
    if iris < 1.0:   # iris in/out: soft-edged black circle mask
        yy, xx = np.mgrid[0:PIC_H, 0:PIC_W]
        r = np.sqrt((xx - PIC_W / 2) ** 2 + (yy - PIC_H / 2) ** 2)
        rmax = math.hypot(PIC_W / 2, PIC_H / 2) * 1.02
        edge = np.clip((iris * rmax - r) / 3.0, 0, 1)
        a = a * edge
    idx = np.clip(np.rint(a * (N_COLOURS - 1)), 0, N_COLOURS - 1).astype(np.uint8)
    frame = np.zeros((H, W), np.uint8)
    frame[:, PIC_X:PIC_X + PIC_W] = idx
    out = Image.fromarray(frame, "P")
    out.putpalette(PALETTE)
    return out


def black_frame():
    out = Image.new("P", (16, 16), 0)
    out.putpalette(PALETTE)
    return out


def png_bytes(im):
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return buf.getvalue()


# ----------------------------------------------------------------------------------------------------------------------
# 4. RTL text (Hebrew, Arabic, ...) without raqm, fonts, wrap, cards
# ----------------------------------------------------------------------------------------------------------------------
_MIRROR = {"(": ")", ")": "(", "[": "]", "]": "[", "{": "}", "}": "{", "<": ">", ">": "<"}
_LTR_RUN = re.compile(r"[A-Za-z0-9]+(?:[ .,'\-:][A-Za-z0-9]+)*")
_RTL_BLOCKS = [(0x0590, 0x05FF), (0x0600, 0x06FF), (0x0700, 0x074F), (0x0780, 0x07BF),
               (0x08A0, 0x08FF), (0xFB1D, 0xFDFF), (0xFE70, 0xFEFF)]
_RTL_CHAR = re.compile("[" + "".join(chr(a) + "-" + chr(b) for a, b in _RTL_BLOCKS) + "]")


def visual(line):
    """Logical RTL line (e.g. Hebrew) → visual order for PIL (no raqm installed): reverse the whole line (RTL base
    direction), mirror brackets, then restore every Latin/digit run so e.g. 'Studio 1926' still reads left-to-right
    inside the RTL text. In Minecraft text components, write the LOGICAL order instead — the client does its own
    bidi reordering, so `visual()` is only for baking text into a PNG frame with PIL.

    A line with NO RTL characters at all (e.g. an English card in an otherwise-RTL film, or any LTR-language film)
    is returned unchanged: the whole-line reversal is only correct when the base direction actually is RTL — run it
    on a pure-LTR sentence with punctuation ('One keeper. One lamp.') and the _LTR_RUN fix-up (meant to restore a
    short embedded Latin phrase inside Hebrew) reorders whole clauses instead, because two connector characters
    in a row (". ", reversed to " .") break its one-connector-per-gap assumption. Mixed lines (RTL text with a
    short embedded Latin/number run) still take the reversal path, which is what this function is for."""
    if not _RTL_CHAR.search(line):
        return line
    rev = "".join(_MIRROR.get(c, c) for c in line[::-1])
    return _LTR_RUN.sub(lambda m: m.group(0)[::-1], rev)


FONT_PATHS = {
    "serif": ["/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf"],            # Hebrew + Latin, period look
    "serif_regular": ["/System/Library/Fonts/Supplemental/Times New Roman.ttf"],
    "sans": ["/System/Library/Fonts/Supplemental/Arial Bold.ttf"],
    "sans_regular": ["/System/Library/Fonts/Supplemental/Arial Unicode.ttf"],
}
_FALLBACKS = ["/System/Library/Fonts/Supplemental/Arial Unicode.ttf", "/System/Library/Fonts/ArialHB.ttc"]
_FONT_CACHE = {}


def font(kind="serif", size=24):
    """A PIL font of the requested family; verifies the path exists and falls back to Arial Unicode / ArialHB."""
    key = (kind, size)
    if key not in _FONT_CACHE:
        for p in FONT_PATHS.get(kind, []) + _FALLBACKS:
            if os.path.exists(p):
                _FONT_CACHE[key] = ImageFont.truetype(p, size)
                break
        else:
            raise FileNotFoundError("no Hebrew-capable font found for " + kind)
    return _FONT_CACHE[key]


def text_width(fnt, s):
    x0, _, x1, _ = fnt.getbbox(s)
    return x1 - x0


def wrap(logical, fnt, max_w):
    """Word-wrap a logical-order line so each line's visual rendering fits max_w px. Returns logical lines."""
    words, lines, cur = logical.split(" "), [], ""
    for w in words:
        cand = (cur + " " + w).strip()
        if cur and text_width(fnt, visual(cand)) > max_w:
            lines.append(cur)
            cur = w
        else:
            cur = cand
    if cur:
        lines.append(cur)
    return lines


def draw_lines(d, cx, cy, lines, fnt, fill, spacing=1.25):
    """Draw logical-order lines centred on (cx, cy) with an ImageDraw (handles Hebrew via visual())."""
    lh = fnt.size * spacing
    top = cy - lh * (len(lines) - 1) / 2
    for i, ln in enumerate(lines):
        d.text((cx, top + i * lh), visual(ln), font=fnt, fill=fill, anchor="mm")


def ornament(d, x0, y0, x1, y1, fill, scale=SS):
    """Ornamental intertitle frame: double rule with small corner diamonds and a centred flourish top and bottom."""
    w = max(1, int(1.0 * scale))
    d.rectangle([x0, y0, x1, y1], outline=fill, width=w)
    g = int(4 * scale)
    d.rectangle([x0 + g, y0 + g, x1 - g, y1 - g], outline=fill, width=max(1, w // 2))
    r = int(3 * scale)
    for (x, y) in ((x0 + g, y0 + g), (x1 - g, y0 + g), (x0 + g, y1 - g), (x1 - g, y1 - g)):
        d.polygon([(x, y - r), (x + r, y), (x, y + r), (x - r, y)], fill=fill)
    cx = (x0 + x1) / 2
    for y in (y0 + g, y1 - g):
        d.line([(cx - 8 * scale, y), (cx - 2 * scale, y - 2 * scale), (cx, y), (cx + 2 * scale, y - 2 * scale), (cx + 8 * scale, y)],
               fill=fill, width=w)
        d.polygon([(cx, y - 3 * scale), (cx + 2 * scale, y), (cx, y + 3 * scale), (cx - 2 * scale, y)], fill=fill)


def card(text, size=22, kind="serif", fill=226, bg=0, sub=None, sub_size=12):
    """An intertitle card as a supersampled 'L' picture: centred text (logical Hebrew, wrapped) in an ornamental frame.
    `sub` = optional smaller second text under a short rule (e.g. a Latin title). Pass the result to finish()."""
    im = Image.new("L", (PIC_W * SS, PIC_H * SS), bg)
    d = ImageDraw.Draw(im)
    m = int(7 * SS)
    ornament(d, m, m, PIC_W * SS - m - 1, PIC_H * SS - m - 1, fill)
    fnt = font(kind, size * SS)
    lines = []
    for para in text.split("\n"):
        lines += wrap(para, fnt, (PIC_W - 30) * SS)
    cy = PIC_H * SS / 2 - (10 * SS if sub else 0)
    draw_lines(d, PIC_W * SS / 2, cy, lines, fnt, fill)
    if sub:
        y = cy + (len(lines) * size * 1.25 / 2 + 6) * SS
        d.line([(PIC_W * SS / 2 - 18 * SS, y), (PIC_W * SS / 2 + 18 * SS, y)], fill=fill, width=SS)
        draw_lines(d, PIC_W * SS / 2, y + 9 * SS, [sub], font(kind, sub_size * SS), fill)
    return im


# ----------------------------------------------------------------------------------------------------------------------
# 5. FrameStore — dedupe
# ----------------------------------------------------------------------------------------------------------------------
class FrameStore:
    """Collects frames in play order and dedupes identical images into unique model ids `<prefix>_f0001..`."""

    def __init__(self, prefix):
        self.prefix = prefix
        self.by_hash = {}        # content hash → model id
        self.images = {}         # model id → PIL image
        self.sequence = []       # model id per played frame

    def add(self, im):
        h = hashlib.md5(im.tobytes() + bytes(im.getpalette() or [])).hexdigest()
        mid = self.by_hash.get(h)
        if mid is None:
            mid = f"{self.prefix}_f{len(self.images) + 1:04d}"
            self.by_hash[h] = mid
            self.images[mid] = im
        self.sequence.append(mid)
        return mid

    @property
    def unique(self):
        return len(self.images)


# ----------------------------------------------------------------------------------------------------------------------
# 6. Pack writer
# ----------------------------------------------------------------------------------------------------------------------
# Quad face/uv scheme copied from gen_lobby_map.py (proven non-mirrored in game on a north wall viewed from the south).
QUAD_FACES = {"north": {"uv": [0, 0, 16, 16], "texture": "#0"}, "south": {"uv": [0, 0, 16, 16], "texture": "#0"}}


def quad_model(texture_ref, y0=0.0, y1=16.0, x0=0.0, x1=16.0):
    """A flat one-element quad model in the x/y plane at z≈8 showing `texture_ref` (e.g. 'cinema:item/foo')."""
    return {"textures": {"0": texture_ref, "particle": texture_ref},
            "elements": [{"from": [x0, y0, 7.9], "to": [x1, y1, 8.1], "faces": QUAD_FACES}]}


class Pack:
    """Writes a resource-pack part: assets/<ns>/{textures/item, models/item, items, sounds}, sounds.json, pack.mcmeta."""

    def __init__(self, out_dir, ns, description, pack_format=88):
        self.out, self.ns, self.desc, self.fmt = out_dir, ns, description, pack_format
        self.sounds = {}
        self.sizes = {}
        if os.path.exists(out_dir):
            shutil.rmtree(out_dir)
        for sub in ("textures/item", "models/item", "items", "sounds"):
            os.makedirs(os.path.join(out_dir, "assets", ns, sub), exist_ok=True)

    def _path(self, *parts):
        return os.path.join(self.out, "assets", self.ns, *parts)

    def texture(self, name, im):
        assert im.width % 16 == 0 and im.height % 16 == 0, f"texture {name} must be multiples of 16: {im.size}"
        data = png_bytes(im)
        with open(self._path("textures/item", name + ".png"), "wb") as f:
            f.write(data)
        self.sizes[name] = len(data)
        return len(data)

    def model(self, name, model_json):
        with open(self._path("models/item", name + ".json"), "w") as f:
            json.dump(model_json, f, separators=(",", ":"))
        with open(self._path("items", name + ".json"), "w") as f:
            json.dump({"model": {"type": "minecraft:model", "model": f"{self.ns}:item/{name}"}}, f)

    def quad(self, name, im, y0=0.0, y1=16.0):
        """Texture + quad model + item def in one go; returns the item model id 'ns:name'."""
        self.texture(name, im)
        self.model(name, quad_model(f"{self.ns}:item/{name}", y0, y1))
        return f"{self.ns}:{name}"

    def sound_path(self, event):
        """Where the ogg for `event` lives inside the pack (render straight into it, then call sound())."""
        return self._path("sounds", event + ".ogg")

    def sound(self, event, ogg_path, stream=True, category="record"):
        """Copies the ogg into assets/<ns>/sounds/<event>.ogg (unless already there) and registers the sound event."""
        dst = self.sound_path(event)
        if os.path.abspath(ogg_path) != os.path.abspath(dst):
            shutil.copyfile(ogg_path, dst)
        self.sounds[event] = {"category": category, "sounds": [{"name": f"{self.ns}:{event}", "stream": stream}]}
        return f"{self.ns}:{event}"

    def write(self, zip_path):
        if self.sounds:
            with open(self._path("sounds.json"), "w") as f:
                json.dump(self.sounds, f, ensure_ascii=False, indent=1)
        with open(os.path.join(self.out, "pack.mcmeta"), "w") as f:
            json.dump({"pack": {"description": self.desc, "min_format": self.fmt, "max_format": self.fmt}}, f)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(self.out):
                for fn in sorted(files):
                    p = os.path.join(root, fn)
                    zf.write(p, os.path.relpath(p, self.out))
        return os.path.getsize(zip_path)


# ----------------------------------------------------------------------------------------------------------------------
# 7. Synth toolkit
# ----------------------------------------------------------------------------------------------------------------------
SR = 44100
_NOTE_IDX = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def note(name):
    """'A4' → 440.0, 'C#5', 'Bb2' etc."""
    m = re.fullmatch(r"([A-Ga-g])([#b]?)(-?\d)", name)
    if not m:
        raise ValueError(name)
    semis = _NOTE_IDX[m.group(1).upper()] + {"#": 1, "b": -1, "": 0}[m.group(2)] + 12 * (int(m.group(3)) + 1)
    return 440.0 * 2 ** ((semis - 69) / 12)


def _t(dur):
    return np.arange(int(dur * SR)) / SR


def adsr(n, a=0.01, d=0.1, s=0.7, r=0.3):
    """Linear ADSR envelope of n samples (release included at the end)."""
    a_n, d_n, r_n = int(a * SR), int(d * SR), int(r * SR)
    s_n = max(0, n - a_n - d_n - r_n)
    env = np.concatenate([np.linspace(0, 1, a_n, endpoint=False), np.linspace(1, s, d_n, endpoint=False),
                          np.full(s_n, s), np.linspace(s, 0, r_n)])
    return env[:n] if len(env) >= n else np.pad(env, (0, n - len(env)))


def _tail(x, ms=30):
    """Short linear fade at the very end so a truncated decay never clicks."""
    n = min(len(x), int(ms / 1000 * SR))
    if n:
        x[-n:] *= np.linspace(1, 0, n)
    return x


def piano(freq, dur, vel=1.0):
    """Piano-ish: sine + harmonics that decay faster the higher they are, slight detune, soft hammer attack."""
    t = _t(dur + 0.6)
    out = np.zeros_like(t)
    for k in range(1, 9):
        amp = 1.0 / (k ** 1.35)
        decay = 2.2 + 0.9 * k + freq / 900.0
        out += amp * np.exp(-decay * t) * np.sin(2 * np.pi * freq * k * (1 + 0.0004 * k) * t)
    out += 0.06 * np.exp(-40 * t) * np.random.default_rng(int(freq)).normal(0, 1, len(t))   # hammer noise
    att = np.minimum(1.0, t / 0.006)
    return _tail(out * att * vel * 0.45)


def pad(freq, dur, vel=1.0, attack=0.8, release=1.2):
    """Soft string pad: three slightly detuned voices of a few odd/even harmonics with slow attack/release."""
    t = _t(dur)
    out = np.zeros_like(t)
    for det in (-0.004, 0.0, 0.004):
        f = freq * (1 + det)
        for k, amp in ((1, 1.0), (2, 0.35), (3, 0.22), (4, 0.10), (5, 0.06)):
            out += amp * np.sin(2 * np.pi * f * k * t + det * 40)
    vib = 1 + 0.003 * np.sin(2 * np.pi * 5.2 * t)
    out = out * vib
    return out * adsr(len(t), attack, 0.2, 0.85, release) * vel * 0.10


def pedal(freq, dur, vel=1.0):
    """Low pedal tone: fundamental + a little second harmonic, slow swell."""
    t = _t(dur)
    out = np.sin(2 * np.pi * freq * t) + 0.3 * np.sin(2 * np.pi * freq * 2 * t)
    return out * adsr(len(t), 1.5, 0.5, 0.8, 2.0) * vel * 0.28


def tremolo(freq, dur, rate=9.0, vel=1.0):
    """Low bowed tremolo: pad-like tone with fast amplitude modulation."""
    t = _t(dur)
    base = np.sin(2 * np.pi * freq * t) + 0.5 * np.sin(2 * np.pi * freq * 2 * t) + 0.3 * np.sin(2 * np.pi * freq * 3 * t)
    mod = 0.55 + 0.45 * np.abs(np.sin(2 * np.pi * rate * t))
    return base * mod * adsr(len(t), 0.4, 0.3, 0.8, 1.5) * vel * 0.22


def boom(dur=3.0, vel=1.0):
    """Impact: a sub-bass sweep 70→28 Hz plus a filtered noise burst, long decay."""
    t = _t(dur)
    f = 28 + 42 * np.exp(-4 * t)
    phase = 2 * np.pi * np.cumsum(f) / SR
    sub = np.sin(phase) * np.exp(-1.6 * t)
    noise = np.random.default_rng(7).normal(0, 1, len(t))
    # cheap low-pass: moving average
    k = 40
    noise = np.convolve(noise, np.ones(k) / k, mode="same") * np.exp(-6 * t)
    return _tail((sub + noise * 1.2) * vel)


def reverb(x, decay=0.5, mix=0.25):
    """Schroeder reverb: four feedback combs + two allpasses (scipy lfilter), returns dry/wet mix."""
    from scipy.signal import lfilter
    wet = np.zeros_like(x)
    for delay_ms in (29.7, 37.1, 41.1, 43.7):
        n = int(delay_ms / 1000 * SR)
        b = np.zeros(n + 1); b[n] = 1.0
        a = np.zeros(n + 1); a[0] = 1.0; a[n] = -decay * 0.84
        wet += lfilter(b, a, x)
    wet /= 4
    for delay_ms, g in ((5.0, 0.7), (1.7, 0.7)):
        n = int(delay_ms / 1000 * SR)
        b = np.zeros(n + 1); b[0] = -g; b[n] = 1.0
        a = np.zeros(n + 1); a[0] = 1.0; a[n] = -g
        wet = lfilter(b, a, wet)
    return x * (1 - mix) + wet * mix


class Mixer:
    """A mono buffer of `seconds`; add(t, signal, gain) mixes a signal starting at time t (clipped to the buffer)."""

    def __init__(self, seconds):
        self.buf = np.zeros(int(seconds * SR))

    def add(self, t, sig, gain=1.0):
        i = int(t * SR)
        if i >= len(self.buf):
            return
        n = min(len(sig), len(self.buf) - i)
        self.buf[i:i + n] += sig[:n] * gain

    def fade(self, fade_in=0.0, fade_out=0.0):
        n_in, n_out = int(fade_in * SR), int(fade_out * SR)
        if n_in:
            self.buf[:n_in] *= np.linspace(0, 1, n_in)
        if n_out:
            self.buf[-n_out:] *= np.linspace(1, 0, n_out) ** 1.5
        return self

    def normalize(self, peak_db=-1.0):
        peak = np.max(np.abs(self.buf)) or 1.0
        self.buf *= (10 ** (peak_db / 20)) / peak
        return self

    def write_ogg(self, path):
        import soundfile as sf
        y = np.clip(self.buf, -1, 1).astype(np.float32)
        sf.write(path, y, SR, format="OGG", subtype="VORBIS")
        return path


# ----------------------------------------------------------------------------------------------------------------------
# 8. Contact sheet
# ----------------------------------------------------------------------------------------------------------------------
def contact_sheet(frames, labels, cols=6, scale=1):
    """Grid of frames (PIL images, same size) with a label strip under each; returns an RGB image."""
    fw, fh = frames[0].size
    fw, fh = fw * scale, fh * scale
    lab = 16
    rows = (len(frames) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (fw + 6) + 6, rows * (fh + lab + 6) + 6), (40, 40, 40))
    d = ImageDraw.Draw(sheet)
    fnt = font("sans", 12)
    for i, (fr, lb) in enumerate(zip(frames, labels)):
        x = 6 + (i % cols) * (fw + 6)
        y = 6 + (i // cols) * (fh + lab + 6)
        sheet.paste(fr.convert("RGB").resize((fw, fh), Image.NEAREST), (x, y))
        d.text((x + 3, y + fh + 2), lb, font=fnt, fill=(230, 230, 230))
    return sheet
