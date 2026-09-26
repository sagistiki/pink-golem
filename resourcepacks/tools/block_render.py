"""block_render.py — render Minecraft blocks in 3D as crisp pixel art, to show a texture design before it goes into
a resource pack (show the person one or two blocks, get a yes, then do the rest in the same style).

Models come from the vanilla client jar (parents resolved: cube_all → cube → block, stairs, slabs, …); textures come
from --pack (a folder or .zip, your work in progress) first, then from the jar. Every texel is drawn as its own
parallelogram with Minecraft's face shading (top 1.0, north/south 0.8, east/west 0.6), so it looks like the game.

    python3 block_render.py oak_planks stone_bricks grass_block --pack my_pack --out render.png [--compare]
      --compare     draws each block twice: vanilla textures (left) and the pack's (right)
      --scale N     screen pixels per 1/16 block (default 10)
      --tint HEX    colour for biome-tinted faces (grass, leaves); default a plains green
      --jar PATH    the client jar (default: found in the usual .minecraft folder for --version, default 26.2)
Python 3 + Pillow.
"""
import argparse
import json
import math
import os
import zipfile

from PIL import Image, ImageDraw

SHADE = {"up": 1.0, "down": 0.5, "north": 0.8, "south": 0.8, "east": 0.6, "west": 0.6}
TINT = None           # colour for tinted faces (grass, leaves); None = a plains green
NO_TINT = {"cherry_leaves", "azalea_leaves", "flowering_azalea_leaves", "pale_oak_leaves"}   # tintindex in the model, but the game gives them no colour


def find_jar(version):
    """The client jar in the launcher's usual folder on macOS, Windows or Linux."""
    for base in (os.path.expanduser("~/Library/Application Support/minecraft"),
                 os.path.join(os.environ.get("APPDATA", ""), ".minecraft"), os.path.expanduser("~/.minecraft")):
        p = os.path.join(base, "versions", version, version + ".jar")
        if os.path.exists(p):
            return p
    raise SystemExit(f"client jar for {version} not found: start that version once in the launcher, or pass --jar")


class Assets:
    def __init__(self, jar, pack=None):
        self.jar = zipfile.ZipFile(jar)
        self.pack = zipfile.ZipFile(pack) if pack and pack.endswith(".zip") else pack
        self.cache = {}

    def _pack(self, rel):
        if not self.pack:
            return None
        if isinstance(self.pack, zipfile.ZipFile):
            try:
                return self.pack.read(rel)
            except KeyError:
                return None
        p = os.path.join(self.pack, rel)
        return open(p, "rb").read() if os.path.exists(p) else None

    def _read(self, rel):
        raw = self._pack(rel)
        if raw is not None:
            return raw
        try:
            return self.jar.read(rel)
        except KeyError:
            return None

    def model(self, ref):
        ns, path = ref.split(":") if ":" in ref else ("minecraft", ref)
        raw = self._read(f"assets/{ns}/models/{path}.json")
        if raw is None:
            raise SystemExit(f"model not found: {ref}")
        m = json.loads(raw)
        if "parent" in m:
            base = self.model(m["parent"])
            tex = dict(base.get("textures", {}))
            tex.update(m.get("textures", {}))
            out = dict(base)
            out["textures"] = tex
            if "elements" in m:
                out["elements"] = m["elements"]
            return out
        return m

    def texture(self, ref, vanilla=False):
        key = (ref, vanilla)
        if key in self.cache:
            return self.cache[key]
        ns, path = ref.split(":") if ":" in ref else ("minecraft", ref)
        rel = f"assets/{ns}/textures/{path}.png"
        raw = None if vanilla else self._pack(rel)
        if raw is None:
            try:
                raw = self.jar.read(rel)
            except KeyError:
                raw = None
        img = None
        if raw:
            import io
            img = Image.open(io.BytesIO(raw)).convert("RGBA")
            if img.height > img.width:                       # animated strip: first frame
                img = img.crop((0, 0, img.width, img.width))
        self.cache[key] = img
        return img


def resolve(tex, name):
    """Follow #references; 26.x may store a texture as {"sprite": ..., "force_translucent": ...}."""
    seen = 0
    if isinstance(name, dict):
        name = name.get("sprite", "")
    while name.startswith("#") and seen < 10:
        name = tex.get(name[1:], name)
        if isinstance(name, dict):
            name = name.get("sprite", "")
        seen += 1
    return name


def block_model_for(assets, block):
    """block name → model ref via the blockstate's first variant (or the plain block model)."""
    raw = assets._read(f"assets/minecraft/blockstates/{block}.json")
    if raw:
        bs = json.loads(raw)
        if "variants" in bs:
            v = next(iter(bs["variants"].values()))
            v = v[0] if isinstance(v, list) else v
            return v["model"]
        if "multipart" in bs:
            a = bs["multipart"][0]["apply"]
            a = a[0] if isinstance(a, list) else a
            return a["model"]
    return f"minecraft:block/{block}"


def face_quad(face, a, b):
    """The 4 corners of a face in model units, ordered to match the texture's (u0,v0) (u1,v0) (u1,v1) (u0,v1)."""
    x1, y1, z1 = a
    x2, y2, z2 = b
    return {
        "north": [(x2, y2, z1), (x1, y2, z1), (x1, y1, z1), (x2, y1, z1)],
        "south": [(x1, y2, z2), (x2, y2, z2), (x2, y1, z2), (x1, y1, z2)],
        "west": [(x1, y2, z1), (x1, y2, z2), (x1, y1, z2), (x1, y1, z1)],
        "east": [(x2, y2, z2), (x2, y2, z1), (x2, y1, z1), (x2, y1, z2)],
        "up": [(x1, y2, z1), (x2, y2, z1), (x2, y2, z2), (x1, y2, z2)],
        "down": [(x1, y1, z2), (x2, y1, z2), (x2, y1, z1), (x1, y1, z1)],
    }[face]


def default_uv(face, a, b):
    x1, y1, z1 = a
    x2, y2, z2 = b
    return {"down": [x1, 16 - z2, x2, 16 - z1], "up": [x1, z1, x2, z2], "north": [16 - x2, 16 - y2, 16 - x1, 16 - y1],
            "south": [x1, 16 - y2, x2, 16 - y1], "west": [z1, 16 - y2, z2, 16 - y1], "east": [16 - z2, 16 - y2, 16 - z1, 16 - y1]}[face]


def project(p, s, ox, oy):
    """Classic isometric-ish view from the south-east, above (the inventory angle)."""
    x, y, z = p
    X = (x - z) * math.cos(math.radians(30))
    Y = (x + z) * math.sin(math.radians(30)) - y
    return (ox + X * s, oy + Y * s)


def draw_block(img, assets, block, ox, oy, scale, vanilla=False):
    m = assets.model(block_model_for(assets, block))
    no_tint = block in NO_TINT
    tex = m.get("textures", {})
    d = ImageDraw.Draw(img)
    polys = []
    for e in m.get("elements", []):
        a, b = e["from"], e["to"]
        for face in ("up", "south", "east"):                       # the three faces this view can see
            fd = e.get("faces", {}).get(face)
            if not fd:
                continue
            t = assets.texture(resolve(tex, fd["texture"]), vanilla)
            if t is None:
                continue
            uv = fd.get("uv") or default_uv(face, a, b)
            q = face_quad(face, a, b)
            tw, th = t.width, t.height
            u0, v0, u1, v1 = uv
            nu = max(1, round(abs(u1 - u0) / 16 * tw))
            nv = max(1, round(abs(v1 - v0) / 16 * th))
            tint = fd.get("tintindex") is not None and not no_tint
            depth = sum(p[0] + p[2] + p[1] * 0.01 for p in q) / 4
            for i in range(nu):
                for j in range(nv):
                    su, sv = (i + 0.5) / nu, (j + 0.5) / nv
                    tu = u0 + (u1 - u0) * su
                    tv = v0 + (v1 - v0) * sv
                    px = t.getpixel((min(tw - 1, int(tu / 16 * tw)), min(th - 1, int(tv / 16 * th))))
                    if px[3] < 128:
                        continue
                    col = px[:3]
                    if tint:
                        tc = TINT or (140, 204, 115)                      # plains grass / foliage
                        col = tuple(int(col[k] * tc[k] / 255) for k in range(3))
                    sh = SHADE[face]
                    col = tuple(int(c * sh) for c in col)

                    def at(fu, fv):
                        top = [q[0][k] + (q[1][k] - q[0][k]) * fu for k in range(3)]
                        bot = [q[3][k] + (q[2][k] - q[3][k]) * fu for k in range(3)]
                        return [top[k] + (bot[k] - top[k]) * fv for k in range(3)]
                    corners = [at(i / nu, j / nv), at((i + 1) / nu, j / nv), at((i + 1) / nu, (j + 1) / nv), at(i / nu, (j + 1) / nv)]
                    polys.append((depth, [project(c, scale, ox, oy) for c in corners], col))
    polys.sort(key=lambda p: p[0])
    for (_, pts, col) in polys:
        d.polygon(pts, fill=col, outline=col)


def render(blocks, pack, out, scale=10, compare=False, jar=None):
    assets = Assets(jar, pack)
    cell = int(scale * 31)                     # a block spans ±13.9 texels across and 32 texels high
    cols = len(blocks) * (2 if compare else 1)
    W, H = max(cell * cols, 200), int(scale * 33) + 40
    img = Image.new("RGB", (W, H), (226, 230, 236))
    d = ImageDraw.Draw(img)
    k = 0
    for b in blocks:
        for vanilla in ((True, False) if compare else (False,)):
            ox, oy = k * cell + cell / 2, 16 * scale + 12
            draw_block(img, assets, b, ox, oy, scale, vanilla)
            label = b + (" (vanilla)" if compare and vanilla else " (new)" if compare else "")
            d.text((k * cell + 10, H - 26), label, fill=(60, 64, 72))
            k += 1
    img.save(out)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("blocks", nargs="+")
    ap.add_argument("--pack")
    ap.add_argument("--out", default="block_render.png")
    ap.add_argument("--scale", type=int, default=10)
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--tint")
    ap.add_argument("--jar")
    ap.add_argument("--version", default="26.2")
    a = ap.parse_args()
    if a.tint:
        TINT = tuple(int(a.tint.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    print(render(a.blocks, a.pack, a.out, a.scale, a.compare, a.jar or find_jar(a.version)))
