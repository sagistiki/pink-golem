"""build_pack.py — the resource pack for the server-side minimap (scarpet-apps/minimap.sc), Minecraft 26.2.

How it works (no client mods): the app sends each player a WHITE bossbar whose title is the map, written in the font
"clawdblock:mm" — 1x2-px cell glyphs (one char per map row, the row set by the glyph ascent), coloured per cell, plus dot /
arrow / frame glyphs, joined by negative spaces. The pack
  • makes the white bossbar sprites transparent (only the title is seen),
  • overrides core/text.vsh: GUI glyphs whose colour carries the marker (R&3 == 1, G&3 == 2, B&3 == 3 cell / 1 overlay)
    are moved from the top-centre (bossbar titles are centred) to the top-left corner, and cells are widened by 1 px
    (bitmap glyphs always advance width + 1, so 1-px cells + 1 px = seamless 2-px cells).
Layout contract with minimap.sc: the title's total advance is exactly W = 2 * CELLS px, cell rows start at y = TOP.

Run: python3 resourcepacks/minimap/build_pack.py → resourcepacks/minimap/minimap.zip (sha1 printed)
Another Minecraft version: copy that version's assets/minecraft/shaders/core/text.vsh into VSH (keep the marked
block) and set PACK_FORMAT (version.json → pack_version.resource_major of the client jar).
"""
import hashlib
import json
import math
import os
import shutil
import struct
import zipfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "build")
CELLS = 24          # map is CELLS x CELLS cells of 2x2 GUI px (48 px)
TOP = 10            # y of the first cell row (bossbar title line top is y 3, baseline + 7)
LEFT = 6            # x of the map's left edge
FRAME = 2 * CELLS + 8
PACK_FORMAT = 88


def png(path, w, h, px):
    """px(x, y) -> (r, g, b, a)"""
    raw = b"".join(b"\x00" + b"".join(bytes(px(x, y)) for x in range(w)) for y in range(h))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "wb").write(data)


def cp(n):
    return chr(n)


def build():
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    tex = os.path.join(OUT, "assets/clawdblock/textures/font")
    # cell: 1 px wide, 2 px tall, white (tinted by the text colour)
    png(os.path.join(tex, "cell.png"), 1, 2, lambda x, y: (255, 255, 255, 255))
    # friend dot 4x4 with a dark rim, self arrow 7x7 in 8 directions
    png(os.path.join(tex, "dot.png"), 4, 4, lambda x, y: (255, 255, 255, 255) if 0 < x < 3 or 0 < y < 3 else (0, 0, 0, 0))
    for d in range(8):
        a = math.radians(d * 45)
        def arrow(x, y, a=a):
            u, v = x - 3, y - 3                          # rotate the point back to the "north" arrow
            ru = u * math.cos(-a) - v * math.sin(-a); rv = u * math.sin(-a) + v * math.cos(-a)
            inside = rv >= -3.2 and rv <= 2.6 and abs(ru) <= (rv + 3.2) * 0.55
            notch = rv > 1.2 and abs(ru) < (rv - 1.2) * 0.9
            return (255, 255, 255, 255) if inside and not notch else (0, 0, 0, 0)
        png(os.path.join(tex, f"arrow{d}.png"), 7, 7, arrow)
    # frame: a round pink/white ring with an N notch on top (tinted white = its own colours)
    F = FRAME; c = (F - 1) / 2; R = CELLS + 0.5
    def ring(x, y):
        r = math.hypot(x - c, y - c)
        if R <= r < R + 1.2:
            return (255, 255, 255, 255)
        if R + 1.2 <= r < R + 3.2:
            ang = math.degrees(math.atan2(y - c, x - c)) % 360
            return (255, 120, 190, 255) if int(ang / 15) % 2 else (240, 70, 160, 255)
        if R + 3.2 <= r < R + 3.8:
            return (60, 20, 50, 255)
        return (0, 0, 0, 0)
    png(os.path.join(tex, "frame.png"), F, F, ring)
    # N badge 7x7
    Nmask = ["00000000", "00000000", "01000100", "01100100", "01010100", "01001100", "01000100", "00000000"]
    png(os.path.join(tex, "north.png"), 8, 8, lambda x, y: (255, 255, 255, 255) if Nmask[y][x] == "1" else ((240, 70, 160, 255) if (x - 3.5) ** 2 + (y - 4) ** 2 <= 14 else (0, 0, 0, 0)))

    providers = []
    # spaces: U+F801.. = -1,-2,-4..-128 ; U+F811.. = +1,+2..+128
    adv = {}
    for i in range(8):
        adv[cp(0xF801 + i)] = -(1 << i)
        adv[cp(0xF811 + i)] = (1 << i)
    providers.append({"type": "space", "advances": adv})
    # cell rows: U+E000 + r, ascent so the row's top lands at y = TOP + 2r (glyph top = 3 + 7 - ascent)
    for r in range(CELLS):
        providers.append({"type": "bitmap", "file": "clawdblock:font/cell.png", "ascent": 10 - (TOP + 2 * r), "height": 2, "chars": [cp(0xE000 + r)]})
    # dots per row (centred on the row): U+E100 + r
    for r in range(CELLS):
        providers.append({"type": "bitmap", "file": "clawdblock:font/dot.png", "ascent": 10 - (TOP + 2 * r - 1), "height": 4, "chars": [cp(0xE100 + r)]})
    # arrows (centre row): U+E200 + d
    mid = CELLS // 2
    for d in range(8):
        providers.append({"type": "bitmap", "file": f"clawdblock:font/arrow{d}.png", "ascent": 10 - (TOP + 2 * mid - 3), "height": 7, "chars": [cp(0xE200 + d)]})
    providers.append({"type": "bitmap", "file": "clawdblock:font/frame.png", "ascent": 10 - (TOP - 4), "height": FRAME, "chars": [cp(0xE300)]})
    providers.append({"type": "bitmap", "file": "clawdblock:font/north.png", "ascent": 10 - (TOP - 6), "height": 8, "chars": [cp(0xE301)]})
    # the N badge travels around the ring as the map turns: one glyph per top y, U+E400 + i → top = TOP - 7 + i
    for i in range(2 * CELLS + 7):
        providers.append({"type": "bitmap", "file": "clawdblock:font/north.png", "ascent": 10 - (TOP - 7 + i), "height": 8, "chars": [cp(0xE400 + i)]})
    fdir = os.path.join(OUT, "assets/clawdblock/font")
    os.makedirs(fdir, exist_ok=True)
    json.dump({"providers": providers}, open(os.path.join(fdir, "mm.json"), "w"), ensure_ascii=False)

    # invisible white bossbar (the minimap's carrier)
    bb = os.path.join(OUT, "assets/minecraft/textures/gui/sprites/boss_bar")
    for n in ("white_background.png", "white_progress.png"):
        png(os.path.join(bb, n), 182, 5, lambda x, y: (0, 0, 0, 0))

    # the text vertex shader (vanilla 26.2 core/text.vsh + the minimap move)
    sh = os.path.join(OUT, "assets/minecraft/shaders/core")
    os.makedirs(sh, exist_ok=True)
    open(os.path.join(sh, "text.vsh"), "w").write(VSH.replace("%W%", f"{2 * CELLS}.0").replace("%LEFT%", f"{LEFT}.0"))

    json.dump({"pack": {"description": "ClawdBlock minimap", "min_format": PACK_FORMAT, "max_format": PACK_FORMAT}},
              open(os.path.join(OUT, "pack.mcmeta"), "w"), ensure_ascii=False)
    png(os.path.join(OUT, "pack.png"), 64, 64, lambda x, y: ((240, 70, 160, 255) if (x - 31.5) ** 2 + (y - 31.5) ** 2 < 900 else (0, 0, 0, 0)))

    z = os.path.join(HERE, "minimap.zip")
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(OUT):
            for f in sorted(files):
                p = os.path.join(root, f)
                zf.write(p, os.path.relpath(p, OUT))
    print(z, hashlib.sha1(open(z, "rb").read()).hexdigest())


VSH = """#version 330

#if !defined(IS_GUI) && !defined(IS_SEE_THROUGH)
#moj_import <minecraft:fog.glsl>
#moj_import <minecraft:sample_lightmap.glsl>
#endif

#moj_import <minecraft:dynamictransforms.glsl>
#moj_import <minecraft:projection.glsl>

in vec3 Position;
in vec4 Color;
in vec2 UV0;
#if !defined(IS_GUI) && !defined(IS_SEE_THROUGH)
in ivec2 UV2;
#endif

#if !defined(IS_GUI) && !defined(IS_SEE_THROUGH)
uniform sampler2D Sampler2;
out float sphericalVertexDistance;
out float cylindricalVertexDistance;
#endif

out vec4 vertexColor;
out vec2 texCoord0;

void main() {
    vec3 pos = Position;
#if defined(IS_GUI)
    // ClawdBlock minimap: glyphs whose colour carries the marker are moved from the centred bossbar title to the
    // top-left corner; map cells (B&3 == 3) are widened by 1 px to close the bitmap glyph spacing.
    ivec3 c = ivec3(round(Color.rgb * 255.0));
    if ((c.r & 3) == 1 && (c.g & 3) == 2 && ((c.b & 3) == 3 || (c.b & 3) == 1)) {
        float guiW = 2.0 / ProjMat[0][0];
        pos.x += %LEFT% - (guiW * 0.5 - %W% * 0.5);
        if ((c.b & 3) == 3) {
            int v = gl_VertexID % 4;
            if (v == 2 || v == 3) pos.x += 1.0;
        }
    }
#endif
    gl_Position = ProjMat * ModelViewMat * vec4(pos, 1.0);

#if !defined(IS_GUI) && !defined(IS_SEE_THROUGH)
    sphericalVertexDistance = fog_spherical_distance(Position);
    cylindricalVertexDistance = fog_cylindrical_distance(Position);
    vertexColor = Color * sample_lightmap(Sampler2, UV2);
#else
    vertexColor = Color;
#endif
    texCoord0 = UV0;
}
"""

if __name__ == "__main__":
    build()
