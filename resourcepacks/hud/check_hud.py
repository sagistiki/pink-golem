"""check_hud.py — verify the HUD toolkit without a game client.

It reads the built pack (fonts + PNGs + text.vsh), measures every glyph exactly like the client (advance =
int(0.5 + inked width * scale) + 1; box top = title y + 7 - ascent), runs a Python port of the shader, and checks:
  1. the unified text.vsh is the minimap's text.vsh plus the HUD block — the minimap part is byte-identical and gives
     the same vertex positions as the old shader for every colour that is not a HUD marker;
  2. every HUD glyph box lies in the band, so all 4 vertices find the same bossbar slot;
  3. each title (captured from the real scarpet composer, hud.scl) totals exactly 0 in advance, every inked glyph
     carries a HUD marker, and every glyph lands at the same screen spot whichever bossbar slot (0..3) carries it,
     inside the screen for several GUI sizes. It prints the element boxes per anchor.

Run: python3 check_hud.py [--pack hud.zip] [--minimap ../minimap/minimap.zip] [--titles sample_titles.json]
                          [--scan <scripts folder>] [--verbose] [--preview out.png --only name,name]
"""
import argparse
import json
import math
import os
import re
import struct
import sys
import zipfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PACK = os.path.join(HERE, "hud.zip")
DEFAULT_MINIMAP = os.path.join(HERE, "..", "minimap", "minimap.zip")
DEFAULT_TITLES = os.path.join(HERE, "sample_titles.json")
TITLE_Y0, PITCH_BOSSBAR = 3, 19
GUI_SIZES = [(320, 240), (427, 240), (640, 360), (853, 480), (960, 540), (1280, 720)]


# ───────────── reading the pack ─────────────
class Pack:
    def __init__(self, src):
        self.src = src
        self.zip = zipfile.ZipFile(src) if os.path.isfile(src) else None

    def read(self, path):
        if self.zip:
            return self.zip.read(path)
        return open(os.path.join(self.src, path), "rb").read()

    def names(self):
        if self.zip:
            return self.zip.namelist()
        out = []
        for root, _, files in os.walk(self.src):
            for f in files:
                out.append(os.path.relpath(os.path.join(root, f), self.src).replace(os.sep, "/"))
        return out


def png_read(data):
    """8-bit RGBA / RGB PNG → (w, h, rows of (r, g, b, a)); all five filter types"""
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, idat, w = 8, b"", 0
    while pos < len(data):
        n = struct.unpack(">I", data[pos:pos + 4])[0]; t = data[pos + 4:pos + 8]; d = data[pos + 8:pos + 8 + n]
        if t == b"IHDR":
            w, h, depth, ctype = struct.unpack(">IIBB", d[:10])
            assert depth == 8 and ctype in (2, 6), "only 8-bit RGB/RGBA"
            bpp = 4 if ctype == 6 else 3
        elif t == b"IDAT":
            idat += d
        pos += 12 + n
    raw = zlib.decompress(idat)
    stride = w * bpp
    rows, prev = [], bytearray(stride)
    for y in range(h):
        f = raw[y * (stride + 1)]; line = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0; b = prev[i]; c = prev[i - bpp] if i >= bpp else 0
            if f == 1: line[i] = (line[i] + a) & 255
            elif f == 2: line[i] = (line[i] + b) & 255
            elif f == 3: line[i] = (line[i] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c; pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append([tuple(line[x * bpp:x * bpp + bpp]) + ((255,) if bpp == 3 else ()) for x in range(w)])
        prev = line
    return w, h, rows


def font_metrics(src, ns, font="hud"):
    """char → {advance, top, bottom, width, ink, file} for slot 0 (title y = 3), exactly like the client"""
    pack = Pack(src)
    fdef = json.loads(pack.read(f"assets/{ns}/font/{font}.json"))
    out = {}
    for pr in fdef["providers"]:
        if pr["type"] == "space":
            for ch, a in pr["advances"].items():
                out[ch] = {"advance": a, "top": None, "bottom": None, "width": 0, "ink": False, "file": "space"}
        elif pr["type"] == "bitmap":
            fns, fpath = pr["file"].split(":")
            w, h, px = png_read(pack.read(f"assets/{fns}/textures/{fpath}"))
            rows = pr["chars"]; cols = len(rows[0])
            cw, chh = w // cols, h // len(rows)
            height = pr.get("height", 8); ascent = pr["ascent"]
            assert ascent <= height, f"{pr['file']}: ascent {ascent} > height {height} — the whole font would fail to load"
            scale = height / chh
            for r, line in enumerate(rows):
                for c, ch in enumerate(line):
                    if ch == "\0":
                        continue
                    actual, ink = 0, False
                    for x in range(cw - 1, -1, -1):
                        colpx = [px[r * chh + y][c * cw + x] for y in range(chh)]
                        if any(p[3] != 0 for p in colpx) and actual == 0:
                            actual = x + 1
                        if any(p[3] >= 26 for p in colpx):
                            ink = True
                    top = TITLE_Y0 + 7 - ascent
                    out[ch] = {"advance": int(0.5 + actual * scale) + 1, "top": top, "bottom": top + chh * scale,
                               "width": cw * scale, "ink": ink, "file": pr["file"], "tex": (px, c * cw, r * chh, cw, chh, scale)}
    return out


# ───────────── the shader, in Python ─────────────
def parse_vsh(text):
    s = {"minimap": None, "hud": None}
    m = re.search(r"pos\.x \+= ([\d.]+) - \(guiW \* 0\.5 - ([\d.]+) \* 0\.5\);", text)
    if m:
        s["minimap"] = (float(m.group(1)), float(m.group(2)))
    m = re.search(r"float k = floor\(\(pos\.y - ([\d.]+) \+ 0\.5\) / ([\d.]+)\);", text)
    if m:
        row2 = float(re.search(r"\(c\.b & 3\) == 2 \? ([\d.]+) : 0\.0", text).group(1))
        anchors = {}
        for mm in re.finditer(r"(?:vec4 A|if \(a == (\d)\) A) = vec4\(([-\d.]+), ([-\d.]+), ([-\d.]+), ([-\d.]+)\);\s+// (\d) (\w+)", text):
            anchors[int(mm.group(6))] = (mm.group(7), float(mm.group(2)), float(mm.group(3)), float(mm.group(4)), float(mm.group(5)))
        s["hud"] = {"band_top": float(m.group(1)), "pitch": float(m.group(2)), "row2": row2, "anchors": anchors}
    return s


def run_vsh(s, rgb, vid, x, y, gw, gh):
    """what text.vsh does to one GUI vertex (float maths like the GPU)"""
    r, g, b = rgb
    if s["minimap"] and (r & 3) == 1 and (g & 3) == 2 and ((b & 3) == 3 or (b & 3) == 1):
        left, w = s["minimap"]
        x += left - (gw * 0.5 - w * 0.5)
        if (b & 3) == 3 and vid % 4 in (2, 3):
            x += 1.0
    if s["hud"] and (r & 3) == 1 and (g & 3) == 2 and ((b & 3) == 0 or (b & 3) == 2):
        H = s["hud"]
        k = math.floor((y - H["band_top"] + 0.5) / H["pitch"])
        lx = x - math.floor(gw * 0.5 + 0.01)
        ly = y - H["band_top"] - H["pitch"] * k + (H["row2"] if (b & 3) == 2 else 0.0)
        a = ((r >> 2) & 1) | (((g >> 2) & 1) << 1) | (((b >> 2) & 1) << 2)
        _, fx, bx, fy, by = H["anchors"][a]
        x = math.floor(fx * gw + 0.01) + bx + lx
        y = math.floor(fy * gh + 0.01) + by + ly
    return x, y


def hud_marker(rgb):
    r, g, b = rgb
    if (r & 3) == 1 and (g & 3) == 2 and (b & 3) in (0, 2):
        return ((r >> 2) & 1) | (((g >> 2) & 1) << 1) | (((b >> 2) & 1) << 2), (1 if (b & 3) == 2 else 0)
    return None


def minimap_marker(rgb):
    r, g, b = rgb
    return (r & 3) == 1 and (g & 3) == 2 and (b & 3) in (1, 3)


# ───────────── checks ─────────────
def check_shader(new_text, old_text, report):
    s_new, s_old = parse_vsh(new_text), parse_vsh(old_text)
    ok = True
    # textual: removing the HUD block gives back the minimap's text.vsh byte for byte
    a = new_text.find("    // HUD toolkit"); b = new_text.find("#endif\n    gl_Position")
    stripped = new_text[:a] + new_text[b:] if a >= 0 and b > a else None
    same = stripped == old_text
    report.append(f"shader: minimap part byte-identical to the minimap pack's text.vsh: {'yes' if same else 'NO'}")
    ok &= same
    # numeric: every colour that is not a HUD marker moves exactly as before
    diffs = 0; tested = 0
    for gw in (320, 427, 640, 853, 854, 960, 1280, 1920):
        for r in range(8):
            for g in range(8):
                for bb in range(8):
                    rgb = (240 + r, 240 + g, 240 + bb)
                    for vid in range(4):
                        for (x, y) in ((100.0, 3.0), (437.0, 30.0), (12.0, 55.0)):
                            tested += 1
                            if hud_marker(rgb):
                                continue
                            if run_vsh(s_new, rgb, vid, x, y, gw, gw * 0.5625) != run_vsh(s_old, rgb, vid, x, y, gw, gw * 0.5625):
                                diffs += 1
    report.append(f"shader: {tested} vertex/colour/width cases, non-HUD colours moved differently from before: {diffs}")
    ok &= diffs == 0
    return ok, s_new


def check_band(metrics, hud, report):
    bad = []
    for ch, m in metrics.items():
        if m["top"] is None:
            continue
        if m["top"] < hud["band_top"] or m["bottom"] > hud["band_top"] + hud["pitch"] - 1:
            bad.append((hex(ord(ch)), m["top"], m["bottom"], m["file"]))
    report.append(f"band: {sum(1 for m in metrics.values() if m['top'] is not None)} glyph boxes, outside y {hud['band_top']:.0f}..{hud['band_top'] + hud['pitch'] - 1:.0f}: {len(bad)} {bad[:5]}")
    return not bad


def flatten(comp, inherited=None):
    """a text component → [(text, colour, font)] in drawing order"""
    inherited = dict(inherited or {})
    if isinstance(comp, str):
        return [(comp, inherited.get("color"), inherited.get("font"))]
    if isinstance(comp, list):
        out = []
        for i, c in enumerate(comp):
            out += flatten(c, inherited if i == 0 else inherited)
        return out
    st = dict(inherited)
    for k in ("color", "font"):
        if k in comp:
            st[k] = comp[k]
    out = [(comp.get("text", ""), st.get("color"), st.get("font"))]
    for c in comp.get("extra", []):
        out += flatten(c, st)
    return out


def colour_rgb(c):
    if c is None:
        return (255, 255, 255)
    if c.startswith("#"):
        v = int(c[1:], 16)
        return (v >> 16 & 255, v >> 8 & 255, v & 255)
    return None


def check_title(name, title, metrics, s, font_id, report, verbose, drawn=None):
    comp = json.loads(title) if isinstance(title, str) else title
    runs = flatten(comp)
    x = 0; glyphs = []; problems = []
    for text, col, font in runs:
        for ch in text:
            if font != font_id:
                problems.append(f"char U+{ord(ch):04X} not in font {font_id} (font {font})")
                continue
            m = metrics.get(ch)
            if m is None:
                problems.append(f"U+{ord(ch):04X} is not in the font")
                continue
            if m["ink"]:
                glyphs.append((ch, x, m, colour_rgb(col)))
            x += m["advance"]
    total = x
    if total != 0:
        problems.append(f"total advance {total} (must be 0)")
    boxes = {}
    for ch, gx, m, rgb in glyphs:
        mk = hud_marker(rgb) if rgb else None
        if mk is None:
            problems.append(f"U+{ord(ch):04X} at x {gx} has no HUD marker (colour {rgb}): it would stay in the middle of the top edge")
            continue
        a, row = mk
        placed = None
        for k in range(4):
            cy = k * PITCH_BOSSBAR
            for gw, gh in GUI_SIZES:
                x0 = gw // 2 - int(math.ceil(total)) // 2
                verts = [(x0 + gx, cy + m["top"]), (x0 + gx, cy + m["bottom"]), (x0 + gx + m["width"], cy + m["bottom"]), (x0 + gx + m["width"], cy + m["top"])]
                out = [run_vsh(s, rgb, vid, vx, vy, gw, gh) for vid, (vx, vy) in enumerate(verts)]
                xs = [p[0] for p in out]; ys = [p[1] for p in out]
                box = (min(xs), min(ys), max(xs), max(ys))
                if (gw, gh) == (960, 540):
                    if placed is None:
                        placed = box
                    elif box != placed:
                        problems.append(f"U+{ord(ch):04X}: slot {k} moves it to {box}, slot 0 to {placed}")
                if box[0] < 0 or box[1] < 0 or box[2] > gw or box[3] > gh:
                    problems.append(f"U+{ord(ch):04X} off screen at GUI {gw}x{gh}: {box}")
        key = (a, s["hud"]["anchors"][a][0])
        ly_top = m["top"] - s["hud"]["band_top"] + (s["hud"]["row2"] if row else 0)
        ly_bot = m["bottom"] - s["hud"]["band_top"] + (s["hud"]["row2"] if row else 0)
        b = boxes.get(key, [1e9, 1e9, -1e9, -1e9, 0, placed])
        boxes[key] = [min(b[0], gx), min(b[1], ly_top), max(b[2], gx + m["advance"] - 1), max(b[3], ly_bot), b[4] + 1,
                      (min(b[5][0], placed[0]), min(b[5][1], placed[1]), max(b[5][2], placed[2]), max(b[5][3], placed[3])) if b[5] else placed]
        if drawn is not None:
            drawn.append((m, rgb, placed))
        if verbose:
            report.append(f"    U+{ord(ch):04X} anchor {a} row {row} local x {gx}..{gx + m['width']:.0f} y {ly_top:.0f}..{ly_bot:.0f} → 960x540 {placed}")
    report.append(f"title {name}: {len(runs)} components, {len(glyphs)} inked glyphs, total advance {total} {'OK' if total == 0 else 'WRONG'}")
    for (a, an), b in sorted(boxes.items()):
        sb = b[5]
        report.append(f"    anchor {a} {an}: {b[4]} glyphs, element x {b[0]}..{b[2]}, y {b[1]:.0f}..{b[3]:.0f}  →  at GUI 960x540: x {sb[0]:.0f}..{sb[2]:.0f}, y {sb[1]:.0f}..{sb[3]:.0f}")
    for p in problems[:8]:
        report.append("    PROBLEM: " + p)
    return not problems


def preview(drawn, path, gw=960, gh=540, zoom=2):
    """draw the glyph textures where the shader puts them (GUI 960x540, a grey background, the hotbar outline)"""
    W, H = gw * zoom, gh * zoom
    img = [[(92, 110, 140) if y < H * 0.55 else (96, 132, 70) for x in range(W)] for y in range(H)]
    for x in range(gw // 2 - 91, gw // 2 + 91):                       # hotbar and action bar positions, for orientation
        for y in (gh - 22, gh - 1):
            for zx in range(zoom):
                img[y * zoom][x * zoom + zx] = (40, 40, 40)
    for m, rgb, box in drawn:
        px, x0, y0, cw, chh, scale = m["tex"]
        for ty in range(chh):
            for tx in range(cw):
                r, g, b, a = px[y0 + ty][x0 + tx]
                if a < 26:
                    continue
                cr, cg, cb = r * rgb[0] // 255, g * rgb[1] // 255, b * rgb[2] // 255
                al = a / 255
                for yy in range(int(scale * zoom)):
                    for xx in range(int(scale * zoom)):
                        X = int((box[0] + tx * scale) * zoom) + xx; Y = int((box[1] + ty * scale) * zoom) + yy
                        if 0 <= X < W and 0 <= Y < H:
                            o = img[Y][X]
                            img[Y][X] = (int(o[0] * (1 - al) + cr * al), int(o[1] * (1 - al) + cg * al), int(o[2] * (1 - al) + cb * al))
    raw = b"".join(b"\x00" + bytes(v for p in row for v in p) for row in img)
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def scan_colours(folder, report):
    hits = []
    for f in sorted(os.listdir(folder)):
        if not f.endswith((".sc", ".scl")):
            continue
        for i, line in enumerate(open(os.path.join(folder, f), encoding="utf-8", errors="replace"), 1):
            for m in re.finditer(r"#([0-9A-Fa-f]{6})\b", line):
                v = int(m.group(1), 16); rgb = (v >> 16 & 255, v >> 8 & 255, v & 255)
                if hud_marker(rgb) and "hud" not in f:
                    hits.append(f"{f}:{i} #{m.group(1)}")
    report.append(f"colour scan of {folder}: hex colours that the HUD shader would now move: {len(hits)} {hits[:10]}")
    return not hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack", default=DEFAULT_PACK)
    ap.add_argument("--minimap", default=DEFAULT_MINIMAP)
    ap.add_argument("--titles", default=DEFAULT_TITLES)
    ap.add_argument("--scan")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--preview", help="write a PNG of these titles drawn at GUI 960x540 (x2)")
    ap.add_argument("--only", help="comma-separated title names for the preview")
    a = ap.parse_args()
    pack = Pack(a.pack)
    layout_path = [n for n in pack.names() if n.endswith("/hud_layout.json")][0]
    layout = json.loads(pack.read(layout_path))
    ns = layout["ns"]
    report = [f"pack {a.pack} (font {layout['font']})"]
    ok = True
    new_vsh = pack.read("assets/minecraft/shaders/core/text.vsh").decode()
    old_vsh = Pack(a.minimap).read("assets/minecraft/shaders/core/text.vsh").decode()
    good, s = check_shader(new_vsh, old_vsh, report); ok &= good
    metrics = font_metrics(a.pack, ns)
    ok &= check_band(metrics, s["hud"], report)
    report.append("anchors: " + ", ".join(f"{i} {v[0]} (x {v[1]:g}·W{v[2]:+g}, y {v[3]:g}·H{v[4]:+g})" for i, v in sorted(s["hud"]["anchors"].items())))
    groups = {}
    for ch, m in metrics.items():
        groups.setdefault(m["file"], set()).add(m["advance"])
    report.append("advances: " + "; ".join(f"{os.path.basename(k)} {sorted(v)}" for k, v in sorted(groups.items()) if k != "space"))
    if os.path.exists(a.titles):
        titles = json.load(open(a.titles, encoding="utf-8"))
        if isinstance(titles, dict):
            titles = list(titles.items())
        drawn = []
        only = a.only.split(",") if a.only else None
        for name, t in titles:
            ok &= check_title(name, t, metrics, s, layout["font"], report, a.verbose, drawn if (not only or name in only) else None)
        if a.preview:
            preview(drawn, a.preview)
            report.append(f"preview: {a.preview}")
    else:
        report.append(f"no titles file {a.titles}: compose some with hud.scl (see reference/hud.md) to check them")
    if a.scan:
        scan_colours(a.scan, report)
    print("\n".join(report))
    print("RESULT:", "ALL CHECKS PASSED" if ok else "PROBLEMS FOUND")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
