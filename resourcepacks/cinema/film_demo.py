"""film_demo.py — "The Lighthouse": a short (14 s) demo silent film, the working example for cinemalib.py /
gen_cinema_pack.py. Copy this file as the template for your own film: everything film-specific lives here (the
intertitle texts, beat timing, the scene drawn with cinemalib.Scene, and the poster). The generic look (sepia,
grain, flicker, iris, letterbox) comes from cinemalib.finish().

Contract for a film module (what gen_cinema_pack.py needs):
    FILM           dict: id, title, en, year, fps, frames, music (module name), music_s
    CARDS          list of (from_frame, to_frame_inclusive, logical text — also what the subtitle strip shows)
    render_frame(i) -> finished 256x144 'P' frame for played frame i
    POSTERS        dict: {model_name: poster_fn} — poster_fn() -> 128x192 RGB poster image; must contain
                    "poster_<FILM id>"

Timeline (seconds, 4 fps): 0-1 studio card · 1-2 title card · 2-3 setup card · 3-12 the scene (keeper, lamp, gull,
camera drift) · 12-13 "THE END" · 13-14 studio card again.
"""
import math
import random

import cinemalib as cl
from cinemalib import PIC_H, PIC_W, Scene

FPS = 4
FRAMES = 56  # 14 s @ 4 fps

FILM = {"id": "demo", "title": "The Lighthouse", "en": "The Lighthouse", "year": "1926", "fps": FPS,
        "frames": FRAMES, "music": "music_demo", "music_s": 14.0}

# Intertitles: (first frame, last frame inclusive, logical-order text). The text is also what the subtitle strip
# shows while these frames play. Write real RTL scripts (Hebrew, Arabic, ...) in LOGICAL order here too —
# cinemalib.card() calls visual() for you when it bakes the PNG frame.
CARDS = [
    (0, 3, "SILENT PICTURES"),
    (4, 7, "THE LIGHTHOUSE"),
    (8, 11, "One keeper. One lamp. One visitor."),
    (48, 51, "THE END"),
    (52, 55, "SILENT PICTURES"),
]


def camera(t, amp=1.4):
    """Slow drift plus a hair of gate weave, like a hand-cranked print — never a perfectly still picture."""
    r = random.Random(int(t * FPS))
    return (amp * math.sin(t * 0.35) + r.uniform(-0.3, 0.3), amp * 0.5 * math.sin(t * 0.27 + 1.1) + r.uniform(-0.2, 0.2))


def scene(t):
    """The one scene of the demo film: a lighthouse on a rock, its lamp turning, a keeper waving, a gull passing."""
    sc = Scene(bg=200, cam=camera(t))
    horizon = 96
    sc.gradient(-40, horizon, 150, 224)                                   # sky
    sc.dot(206, 34, 11, 246)                                              # sun, low in the frame
    sc.gradient(horizon, PIC_H + 40, 58, 40)                              # sea
    sc.line([(-40, horizon), (PIC_W + 40, horizon)], 96, 0.8)

    # the rock the tower stands on
    sc.poly([(96, horizon + 2), (176, horizon + 2), (168, 140), (104, 140)], 24)

    # the tower: tapered body, two lighter stripes, lamp housing, a turning glow
    lx, base_y, top_y = 136, 118, 40
    sc.poly([(lx - 13, base_y), (lx - 8, top_y), (lx + 8, top_y), (lx + 13, base_y)], 28)
    for k in (0.28, 0.58):
        y0 = top_y + (base_y - top_y) * k
        sc.rect(lx - 11 + k * 2, y0, lx + 11 - k * 2, y0 + 5, 96)
    sc.rect(lx - 6, top_y - 11, lx + 6, top_y, 18)
    glow = 9 + 3 * max(0.0, math.sin(t * 2.6))                           # the lamp sweeps roughly once every 2.4 s
    sc.ellipse(lx, top_y - 6, glow, glow * 0.55, 244)

    # the keeper on the rock, waving — arm_r swings 0..90 degrees on a slow cycle
    wave = 45 + 45 * max(0.0, math.sin(t * 2.2))
    sc.figure(66, base_y - 4, 32, fill=14, arm_l=15, arm_r=wave, legs=0.14, cap=True)

    # a gull crossing the frame left to right, looping every ~6.4s, flapping at 4 Hz
    gx = (t * 34) % (PIC_W + 40) - 20
    sc.gull(gx, 50 + 9 * math.sin(t * 1.7), 9, (math.sin(t * 8) + 1) / 2, fill=20)
    return sc


_CARD_CACHE = {}


def render_frame(i):
    """Played frame i (0..FRAMES-1) -> finished 256x144 'P' image. Card frames alternate two flicker variants so a
    held card dedupes to two models; scene frames are all unique (motion never repeats a pixel-identical frame)."""
    for n, (a, b, text) in enumerate(CARDS):
        if a <= i <= b:
            if n not in _CARD_CACHE:
                # keep size low enough that the longest single word still fits the wrap width — wrap() only breaks
                # at word boundaries, so an oversized single word clips past the ornamental frame instead of shrinking.
                size = 22 if text in ("THE LIGHTHOUSE", "THE END", "SILENT PICTURES") else 20
                sub = FILM["year"] if text == "THE LIGHTHOUSE" else None
                _CARD_CACHE[n] = cl.card(text, size=size, sub=sub)
            return cl.finish(_CARD_CACHE[n], seed=1000 + n * 2 + (i % 2), grain=4.0, scratch_p=0.0, vignette=0.45)
    t = i / FPS
    return cl.finish(scene(t), seed=i)


# ----------------------------------------------------------------------------------------------------------------------
# Poster (128x192): cream paper, brown ink, one accent colour — the same look as the intertitle cards.
# ----------------------------------------------------------------------------------------------------------------------
def poster():
    from PIL import Image, ImageDraw
    W, H, SS = 128, 192, 3
    im = Image.new("L", (W * SS, H * SS), 224)
    d = ImageDraw.Draw(im)
    cl.ornament(d, 8 * SS, 8 * SS, W * SS - 9 * SS, H * SS - 9 * SS, 30, scale=SS)
    fnt = cl.font("serif", 15 * SS)
    cl.draw_lines(d, W * SS / 2, 40 * SS, cl.wrap("THE LIGHTHOUSE", fnt, (W - 24) * SS), fnt, 20)
    # a tiny tower + rock silhouette, centred
    lx, by, ty = W * SS / 2, 150 * SS, 90 * SS
    d.polygon([(lx - 9 * SS, by), (lx - 5 * SS, ty), (lx + 5 * SS, ty), (lx + 9 * SS, by)], fill=40)
    d.rectangle([lx - 4 * SS, ty - 7 * SS, lx + 4 * SS, ty], fill=20)
    d.polygon([(lx - 24 * SS, by), (lx + 24 * SS, by), (lx + 16 * SS, by + 12 * SS), (lx - 16 * SS, by + 12 * SS)], fill=36)
    fnt2 = cl.font("serif_regular", 9 * SS)
    cl.draw_lines(d, W * SS / 2, 172 * SS, ["A silent film demo · 1926"], fnt2, 60)
    return im.resize((W, H), Image.LANCZOS).convert("RGB")


POSTERS = {"poster_demo": poster}
