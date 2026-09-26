"""build_pack.py — the HUD toolkit's resource pack (Minecraft 26.2, pack format 88): HUD glyph fonts + ONE text shader
that keeps the minimap working exactly as before and adds eight screen anchors for HUD elements.

How it works (no client mods, the same trick as the minimap — see skill reference/hud.md):
  • an app shows a HUD with an invisible WHITE bossbar whose title is made of glyphs from the font <NS>:hud;
  • every title totals exactly 0 in advance, so the client draws it starting at x = guiWidth / 2;
  • every HUD glyph sits in the band y = 2..20 of its bossbar slot (slots are 19 px apart), so the shader finds the
    slot from the glyph's own y — the HUD works whichever bossbar position it gets;
  • the glyph colour carries a marker: R&3 == 1, G&3 == 2 (the minimap's family), B&3 == 0 (row 0) or 2 (row 1 =
    18 px lower), and bit 2 of R, G, B = the anchor 0..7. The minimap keeps B&3 == 3 (cells) / 1 (overlays).
  • the shader moves each HUD glyph from the carrier to its anchor, keeping its x/y inside the element.

Glyph sets: small 5x7 text at two heights ('sm' top, 'sl' low), big digits/text (5x7 x2), 7-segment timer digits,
a 20-segment speedometer dial (two rows), bar segments, compass ticks + pointer, dark backdrop strips, and space glyphs.

Run: python3 resourcepacks/hud/build_pack.py → hud.zip (sha1 printed) and the generated block in scarpet-apps/hud.scl.
Check it: python3 resourcepacks/hud/check_hud.py (advances, band, anchors, minimap equivalence, sample titles).
"""
import hashlib
import importlib.util
import json
import math
import os
import shutil
import struct
import sys
import zipfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
NS = "pinkgolem"                                                   # font id <NS>:hud, textures <NS>:font/hud_*
MINIMAP_GEN = os.path.join(HERE, "..", "minimap", "build_pack.py")  # the minimap's shader + layout come from here
OUT = os.path.join(HERE, "build")
ZIP = os.path.join(HERE, "hud.zip")
SCL = os.path.join(HERE, "..", "..", "scarpet-apps", "hud.scl")     # its generated block is rewritten
PACK_FORMAT = 88
DESCRIPTION = "Pink Golem HUD + minimap shader"

BAND_TOP, BAND_H, PITCH, ROW2 = 2, 18, 19, 18   # glyph boxes live in y 2..20 of a bossbar slot; slots are 19 apart
TITLE_Y0 = 3                                     # bossbar slot 0 title y (BossHealthOverlay: 12 - 9), glyph top = y + 7 - ascent
# anchor: name, x = floor(fx * guiW) + bx, y (element top) = floor(fy * guiH) + by
ANCHORS = [
    ("top_left", 0.0, 6, 0.0, 68),          # under the minimap
    ("top_centre", 0.5, 0, 0.0, 3),
    ("top_right", 1.0, -6, 0.0, 6),
    ("bottom_centre", 0.5, 0, 1.0, -112),   # above the action bar
    ("bottom_right", 1.0, -6, 1.0, -42),
    ("bottom_left", 0.0, 6, 1.0, -42),
    ("middle_left", 0.0, 6, 0.5, -18),
    ("middle_right", 1.0, -6, 0.5, -18),
]

# ───────────── a 5x7 pixel font ─────────────
F5 = {
    "0": "01110 10001 10011 10101 11001 10001 01110", "1": "00100 01100 00100 00100 00100 00100 01110",
    "2": "01110 10001 00001 00010 00100 01000 11111", "3": "11111 00010 00100 00010 00001 10001 01110",
    "4": "00010 00110 01010 10010 11111 00010 00010", "5": "11111 10000 11110 00001 00001 10001 01110",
    "6": "00110 01000 10000 11110 10001 10001 01110", "7": "11111 00001 00010 00100 01000 01000 01000",
    "8": "01110 10001 10001 01110 10001 10001 01110", "9": "01110 10001 10001 01111 00001 00010 01100",
    "A": "01110 10001 10001 11111 10001 10001 10001", "B": "11110 10001 10001 11110 10001 10001 11110",
    "C": "01110 10001 10000 10000 10000 10001 01110", "D": "11100 10010 10001 10001 10001 10010 11100",
    "E": "11111 10000 10000 11110 10000 10000 11111", "F": "11111 10000 10000 11110 10000 10000 10000",
    "G": "01110 10001 10000 10111 10001 10001 01111", "H": "10001 10001 10001 11111 10001 10001 10001",
    "I": "111 010 010 010 010 010 111", "J": "00111 00010 00010 00010 00010 10010 01100",
    "K": "10001 10010 10100 11000 10100 10010 10001", "L": "10000 10000 10000 10000 10000 10000 11111",
    "M": "10001 11011 10101 10101 10001 10001 10001", "N": "10001 10001 11001 10101 10011 10001 10001",
    "O": "01110 10001 10001 10001 10001 10001 01110", "P": "11110 10001 10001 11110 10000 10000 10000",
    "Q": "01110 10001 10001 10001 10101 10010 01101", "R": "11110 10001 10001 11110 10100 10010 10001",
    "S": "01111 10000 10000 01110 00001 00001 11110", "T": "11111 00100 00100 00100 00100 00100 00100",
    "U": "10001 10001 10001 10001 10001 10001 01110", "V": "10001 10001 10001 10001 10001 01010 00100",
    "W": "10001 10001 10001 10101 10101 10101 01010", "X": "10001 10001 01010 00100 01010 10001 10001",
    "Y": "10001 10001 01010 00100 00100 00100 00100", "Z": "11111 00001 00010 00100 01000 10000 11111",
    ":": "00 11 11 00 11 11 00", ".": "00 00 00 00 00 11 11", "/": "00001 00010 00010 00100 01000 01000 10000",
    "-": "0000 0000 0000 1111 0000 0000 0000", "+": "00000 00100 00100 11111 00100 00100 00000",
    "%": "11001 11010 00010 00100 01000 01011 10011", "!": "1 1 1 1 1 0 1", "?": "01110 10001 00001 00010 00100 00000 00100",
}
CHARSET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ:./-+%!?"
DIGITS = "0123456789"
# style: base codepoint, scale, top y of the glyph box in the band
TEXT_STYLES = {"sm": (0xE000, 1, 2), "sl": (0xE100, 1, 11), "big": (0xE200, 2, 4)}
SEG_BASE, SEG_TOP, SEG_CHARS = 0xE300, 4, "0123456789:- "
GAUGE_BASE, GAUGE_BASE2, GAUGE_N, GAUGE_W, GAUGE_H, GAUGE_R_IN = 0xE400, 0xE420, 20, 64, 36, 25.5   # dial: 2 rows
BAR_CH, BAR_TOP = 0xE500, 12
TICK_MINOR, TICK_MAJOR, POINTER = 0xE510, 0xE511, 0xE512
BACK_BASE, BACK_TOP, BACK_ALPHA = 0xE600, 2, 110
SPACE_NEG, SPACE_POS, SPACE_BITS, SPACE_WORD = 0xF800, 0xF810, 10, 4


def png(path, w, h, px):
    """px(x, y) -> (r, g, b, a); writes an 8-bit RGBA PNG (filter 0)"""
    raw = b"".join(b"\x00" + b"".join(bytes(px(x, y)) for x in range(w)) for y in range(h))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "wb").write(data)


def load_minimap():
    spec = importlib.util.spec_from_file_location("minimap_gen", MINIMAP_GEN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def minimap_vsh(mm):
    return mm.VSH.replace("%W%", f"{2 * mm.CELLS}.0").replace("%LEFT%", f"{mm.LEFT}.0")


HUD_BLOCK = """    // HUD toolkit (build_pack.py in resourcepacks/hud): glyphs marked R&3 == 1, G&3 == 2, B&3 == 0 (row 0) or 2
    // (row 1) come from a HUD bossbar title whose total advance is 0 (it starts at x = guiWidth / 2). Every HUD glyph
    // lies in the band y = %BT%..%BB% of its bossbar slot and slots are %PITCH% px apart, so the slot k comes from the glyph's
    // own y. Bit 2 of R, G, B = the anchor 0..7. The glyph keeps its x/y inside the element and moves to the anchor.
    if ((c.r & 3) == 1 && (c.g & 3) == 2 && ((c.b & 3) == 0 || (c.b & 3) == 2)) {
        float hudW = 2.0 / ProjMat[0][0];
        float hudH = abs(2.0 / ProjMat[1][1]);
        float k = floor((pos.y - %BT%.0 + 0.5) / %PITCH%.0);
        float lx = pos.x - floor(hudW * 0.5 + 0.01);
        float ly = pos.y - %BT%.0 - %PITCH%.0 * k + ((c.b & 3) == 2 ? %ROW2%.0 : 0.0);
        int a = ((c.r >> 2) & 1) | (((c.g >> 2) & 1) << 1) | (((c.b >> 2) & 1) << 2);
%ANCHORS%
        pos.x = floor(A.x * hudW + 0.01) + A.y + lx;
        pos.y = floor(A.z * hudH + 0.01) + A.w + ly;
    }
"""


def unified_vsh(mm):
    """the minimap's own text.vsh, byte for byte, with the HUD block added after the minimap block"""
    base = minimap_vsh(mm)
    anchor_lines = []
    for i, (name, fx, bx, fy, by) in enumerate(ANCHORS):
        v = f"vec4({fx:.1f}, {bx:.1f}, {fy:.1f}, {by:.1f})"
        anchor_lines.append(f"        vec4 A = {v};   // {i} {name}" if i == 0 else f"        if (a == {i}) A = {v};   // {i} {name}")
    block = (HUD_BLOCK.replace("%BT%", str(BAND_TOP)).replace("%BB%", str(BAND_TOP + BAND_H)).replace("%PITCH%", str(PITCH))
             .replace("%ROW2%", str(ROW2)).replace("%ANCHORS%", "\n".join(anchor_lines)))
    marker = "#endif\n    gl_Position = ProjMat * ModelViewMat * vec4(pos, 1.0);"
    assert base.count(marker) == 1, "the minimap shader changed: update unified_vsh()"
    # the HUD block goes inside the same #if defined(IS_GUI) section, right after the minimap block
    return base.replace(marker, block + marker)


# ───────────── glyph images ─────────────
def rows_of(ch):
    return F5[ch].split(" ")


def text_provider(style, base, scale, top, pins):
    """one provider: all CHARSET glyphs in one row of 5-px cells, padded so ascent <= height"""
    cell_w, content_h = 5, 7
    ascent = TITLE_Y0 + 7 - top
    pad = max(0, math.ceil(ascent / scale) - content_h)
    cell_h = content_h + pad
    img = f"hud_{style}.png"

    def px(x, y):
        ch = CHARSET[x // cell_w]; cx = x % cell_w
        r = rows_of(ch)
        if y < content_h and cx < len(r[y]) and r[y][cx] == "1":
            return (255, 255, 255, 255)
        if ch in pins and cx == cell_w - 1 and y == cell_h - 1 and all(len(rr) < cell_w or rr[cell_w - 1] == "0" for rr in r):
            return (255, 255, 255, 1)                                    # invisible width pin (alpha < 0.1 is discarded)
        return (0, 0, 0, 0)
    png(os.path.join(OUT, f"assets/{NS}/textures/font/{img}"), cell_w * len(CHARSET), cell_h, px)
    return {"type": "bitmap", "file": f"{NS}:font/{img}", "ascent": ascent, "height": cell_h * scale,
            "chars": ["".join(chr(base + i) for i in range(len(CHARSET)))]}


SEG = {  # 7-segment digits: segments a b c d e f g
    "0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc", "5": "afgcd", "6": "afgedc", "7": "abc",
    "8": "abcdefg", "9": "abcdfg", "-": "g", " ": ""}


def seg_px(ch, x, y):
    """8x14 cell, stroke 2: a rows 0-1, upper verticals 2-5, g rows 6-7, lower verticals 8-11, d rows 12-13"""
    if ch == ":":
        return x in (0, 1) and y in (4, 5, 9, 10)                        # advances 3: 1 px either side
    s = SEG[ch]
    hor = 2 <= x <= 5
    return ((("a" in s) and hor and y in (0, 1)) or (("g" in s) and hor and y in (6, 7)) or (("d" in s) and hor and y in (12, 13))
            or (("f" in s) and x in (0, 1) and 2 <= y <= 5) or (("b" in s) and x in (6, 7) and 2 <= y <= 5)
            or (("e" in s) and x in (0, 1) and 8 <= y <= 11) or (("c" in s) and x in (6, 7) and 8 <= y <= 11))


def seg_provider():
    cw, chh = 8, 14
    def px(x, y):
        ch = SEG_CHARS[x // cw]; cx = x % cw
        if seg_px(ch, cx, y):
            return (255, 255, 255, 255)
        if ch != ":" and cx == cw - 1 and y == chh - 1:
            return (255, 255, 255, 1)                                    # pin: every digit (and blank) advances 9
        return (0, 0, 0, 0)
    png(os.path.join(OUT, f"assets/{NS}/textures/font/hud_seg.png"), cw * len(SEG_CHARS), chh, px)
    return {"type": "bitmap", "file": f"{NS}:font/hud_seg.png", "ascent": TITLE_Y0 + 7 - SEG_TOP, "height": chh,
            "chars": ["".join(chr(SEG_BASE + i) for i in range(len(SEG_CHARS)))]}


def gauge_colour(f):
    """green → yellow → red along the arc"""
    if f < 0.55:
        t = f / 0.55
        return (int(70 + 185 * t), 220, 70)
    t = (f - 0.55) / 0.45
    return (255, int(220 - 170 * t), int(70 - 30 * t))


def gauge_seg(x, y):
    """the segment (0 = left end) of pixel (x, y) in the GAUGE_W x GAUGE_H dial: a 180° ring, ~1 px gaps"""
    dx, dy = x + 0.5 - GAUGE_W / 2, GAUGE_H - (y + 0.5)
    r = math.hypot(dx, dy)
    if not (GAUGE_R_IN <= r < GAUGE_W / 2):
        return None
    step = 180 / GAUGE_N
    ang = 180 - math.degrees(math.atan2(dy, dx))
    i = int(ang // step)
    if i < 0 or i >= GAUGE_N:
        return None
    off = ang - i * step
    if min(off, step - off) * math.pi / 180 * r < 0.6:
        return None
    return i


def gauge_providers():
    """the dial is 36 px tall = two 18-px slices: the top slice is shown in row 0, the bottom slice in row 1"""
    out = []
    for half, base in ((0, GAUGE_BASE), (1, GAUGE_BASE2)):
        def px(x, y, half=half):
            i, lx = x // GAUGE_W, x % GAUGE_W
            if gauge_seg(lx, y + half * BAND_H) == i:
                return gauge_colour(i / (GAUGE_N - 1)) + (255,)
            if lx == GAUGE_W - 1 and y == BAND_H - 1:
                return (255, 255, 255, 1)                                # pin: every slice advances GAUGE_W + 1
            return (0, 0, 0, 0)
        png(os.path.join(OUT, f"assets/{NS}/textures/font/hud_gauge{half}.png"), GAUGE_W * GAUGE_N, BAND_H, px)
        out.append({"type": "bitmap", "file": f"{NS}:font/hud_gauge{half}.png", "ascent": TITLE_Y0 + 7 - BAND_TOP, "height": BAND_H,
                    "chars": ["".join(chr(base + i) for i in range(GAUGE_N))]})
    return out


def simple_provider(name, cp, w, h, top, fn):
    png(os.path.join(OUT, f"assets/{NS}/textures/font/hud_{name}.png"), w, h, fn)
    return {"type": "bitmap", "file": f"{NS}:font/hud_{name}.png", "ascent": TITLE_Y0 + 7 - top, "height": h, "chars": [chr(cp)]}


def build():
    mm = load_minimap()
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    providers = []
    adv = {chr(SPACE_NEG + i): -(1 << i) for i in range(SPACE_BITS)}
    adv.update({chr(SPACE_POS + i): (1 << i) for i in range(SPACE_BITS)})
    adv[" "] = SPACE_WORD
    providers.append({"type": "space", "advances": adv})
    for style, (base, scale, top) in TEXT_STYLES.items():
        providers.append(text_provider(style, base, scale, top, DIGITS))
    providers.append(seg_provider())
    providers += gauge_providers()
    white = lambda x, y: (255, 255, 255, 255)
    providers.append(simple_provider("bar", BAR_CH, 3, 6, BAR_TOP, white))
    providers.append(simple_provider("tick_minor", TICK_MINOR, 1, 3, 14, white))
    providers.append(simple_provider("tick_major", TICK_MAJOR, 1, 6, 11, white))
    providers.append(simple_provider("pointer", POINTER, 5, 3, 17, lambda x, y: (255, 255, 255, 255) if abs(x - 2) <= y else (0, 0, 0, 0)))
    for i in range(8):
        w = 1 << i
        providers.append(simple_provider(f"back{w}", BACK_BASE + i, w, BAND_H, BACK_TOP, lambda x, y: (0, 0, 0, BACK_ALPHA)))
    fdir = os.path.join(OUT, f"assets/{NS}/font")
    os.makedirs(fdir, exist_ok=True)
    json.dump({"providers": providers}, open(os.path.join(fdir, "hud.json"), "w"), ensure_ascii=False)
    # the carrier bossbar is WHITE and invisible (same sprites as the minimap pack)
    bb = os.path.join(OUT, "assets/minecraft/textures/gui/sprites/boss_bar")
    for n in ("white_background.png", "white_progress.png"):
        png(os.path.join(bb, n), 182, 5, lambda x, y: (0, 0, 0, 0))
    sh = os.path.join(OUT, "assets/minecraft/shaders/core")
    os.makedirs(sh, exist_ok=True)
    open(os.path.join(sh, "text.vsh"), "w").write(unified_vsh(mm))
    layout = {"ns": NS, "font": f"{NS}:hud", "band_top": BAND_TOP, "band_h": BAND_H, "pitch": PITCH, "row2": ROW2,
              "title_y0": TITLE_Y0, "anchors": ANCHORS, "minimap": {"left": mm.LEFT, "w": 2 * mm.CELLS}}
    json.dump(layout, open(os.path.join(OUT, f"assets/{NS}/hud_layout.json"), "w"), indent=1)
    json.dump({"pack": {"description": DESCRIPTION, "min_format": PACK_FORMAT, "max_format": PACK_FORMAT}},
              open(os.path.join(OUT, "pack.mcmeta"), "w"), ensure_ascii=False)
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(OUT):
            for f in sorted(files):
                p = os.path.join(root, f)
                zf.write(p, os.path.relpath(p, OUT))
    write_scl(providers)
    print(ZIP, os.path.getsize(ZIP), hashlib.sha1(open(ZIP, "rb").read()).hexdigest())


# ───────────── the generated block of hud.scl ─────────────
def advances_from_images():
    """char -> advance, measured from the images exactly like the client (BitmapProvider.getActualGlyphWidth)"""
    sys.path.insert(0, HERE)
    import check_hud
    return check_hud.font_metrics(OUT, NS)


def q(s):
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def write_scl(providers):
    if not os.path.exists(SCL):
        print("no", SCL, "- skipped the scarpet block")
        return
    metrics = advances_from_images()
    adv = {ch: m["advance"] for ch, m in metrics.items()}
    lines = ["// <generated> by resourcepacks/hud/build_pack.py — do not edit by hand, rebuild instead"]
    lines.append(f"global_hud_font_id = {q(NS + ':hud')};")
    lines.append("global_hud_anchor = {" + ", ".join(f"{q(a[0])} -> {i}" for i, a in enumerate(ANCHORS)) + "};")
    lines.append("global_hud_neg = [" + ", ".join(q(chr(SPACE_NEG + i)) for i in range(SPACE_BITS)) + "];")
    lines.append("global_hud_pos = [" + ", ".join(q(chr(SPACE_POS + i)) for i in range(SPACE_BITS)) + "];")
    fonts = {}
    for style, (base, scale, top) in TEXT_STYLES.items():
        fonts[style] = {c: chr(base + i) for i, c in enumerate(CHARSET)}
    fonts["seg"] = {c: chr(SEG_BASE + i) for i, c in enumerate(SEG_CHARS)}
    lines.append("global_hud_font = {" + ", ".join(f"{q(s)} -> {{" + ", ".join(f"{q(c)} -> {q(g)}" for c, g in m.items()) + "}" for s, m in fonts.items()) + "};")
    blank = {"sm": SPACE_WORD, "sl": SPACE_WORD, "big": 2 * SPACE_WORD + 1, "seg": adv[chr(SEG_BASE + SEG_CHARS.index(" "))]}
    lines.append("global_hud_blank = {" + ", ".join(f"{q(s)} -> {v}" for s, v in blank.items()) + "};")
    lines.append("global_hud_gauge = [" + ", ".join(q(chr(GAUGE_BASE + i)) for i in range(GAUGE_N)) + "];")
    lines.append("global_hud_gauge2 = [" + ", ".join(q(chr(GAUGE_BASE2 + i)) for i in range(GAUGE_N)) + "];")
    lines.append(f"global_hud_gauge_adv = {adv[chr(GAUGE_BASE)]};")
    lines.append(f"global_hud_bar = {q(chr(BAR_CH))}; global_hud_bar_adv = {adv[chr(BAR_CH)]};")
    lines.append(f"global_hud_tick = [{q(chr(TICK_MINOR))}, {q(chr(TICK_MAJOR))}]; global_hud_tick_adv = {adv[chr(TICK_MINOR)]};")
    lines.append(f"global_hud_pointer = {q(chr(POINTER))}; global_hud_pointer_adv = {adv[chr(POINTER)]};")
    lines.append("global_hud_back = [" + ", ".join(q(chr(BACK_BASE + i)) for i in range(8)) + "];")
    all_adv = dict(adv)
    lines.append("global_hud_adv = {" + ", ".join(f"{q(c)} -> {v}" for c, v in sorted(all_adv.items())) + "};")
    lines.append("// </generated>")
    src = open(SCL, encoding="utf-8").read()
    a, b = src.index("// <generated>"), src.index("// </generated>") + len("// </generated>")
    open(SCL, "w", encoding="utf-8").write(src[:a] + "\n".join(lines) + src[b:])
    print("updated", SCL)


if __name__ == "__main__":
    build()
