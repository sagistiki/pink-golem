"""model_preview.py — render Minecraft item/block model JSON (elements, textures, element and face rotation, parents)
to a PNG with a tiny point-splatting rasterizer, so a model can be checked without a game client. No dependencies.

    python3 resourcepacks/tools/model_preview.py <pack dir or .zip> <ns:item/model> [<ns:item/model> ...]
            [--out preview.png] [--yaw 35] [--pitch 25] [--gap 0] [--size 900x460] [--assets DIR_OR_ZIP ...]
            [--tint RRGGBB] [--bg E2E6EC]

  <pack>      a resource pack folder (the one with pack.mcmeta) or its zip.
  models      namespaced model ids, e.g. coaster:item/front. Several are drawn in a row along +z, the first one in
              front (at -z) — like a train. --gap = model units between their origins (0 = the first model's length).
  --yaw/--pitch  the view: yaw turns the row around the vertical axis, pitch looks down on it (degrees).
  --assets    more places to find textures and parent models, searched after the pack: e.g. the vanilla assets
              unzipped from the client jar (versions/<v>/<v>.jar). Missing textures draw magenta.
  --tint      the colour for faces with a "tintindex" (dyed items; default: untinted).

Faces are shaded by their normal (light from the upper front left). UVs follow the vanilla defaults per face, or the
face's "uv" and "rotation"; animated textures show their first frame. Good enough to check shapes, decals and which
way a model faces — not a lighting-accurate render. Returns / prints the output path.
"""
import json
import math
import os
import struct
import sys
import zipfile
import zlib


# ─────────────────────────────── files ───────────────────────────────
class Assets:
    """Looks files up in a list of pack roots (folders or zips), first hit wins."""

    def __init__(self, roots):
        self.roots = []
        for r in roots:
            if os.path.isfile(r) and r.lower().endswith((".zip", ".jar")):
                self.roots.append(zipfile.ZipFile(r))
            elif os.path.isdir(r):
                self.roots.append(r)
            else:
                raise SystemExit(f"not a pack folder or zip: {r}")

    def read(self, rel):
        for r in self.roots:
            if isinstance(r, zipfile.ZipFile):
                try:
                    return r.read(rel)
                except KeyError:
                    continue
            p = os.path.join(r, *rel.split("/"))
            if os.path.exists(p):
                with open(p, "rb") as f:
                    return f.read()
        return None


def split_id(ref):
    ns, path = ref.split(":", 1) if ":" in ref else ("minecraft", ref)
    return ns, path


def load_model(assets, ref, warn):
    """Follow the parent chain: textures merge (child wins), elements come from the nearest model that has them."""
    textures, elements, seen = {}, None, set()
    while ref and ref not in seen:
        seen.add(ref)
        ns, path = split_id(ref)
        raw = assets.read(f"assets/{ns}/models/{path}.json")
        if raw is None:
            if not ref.startswith("builtin/"):
                warn.add(f"model not found: {ref}")
            break
        m = json.loads(raw)
        for k, v in m.get("textures", {}).items():
            textures.setdefault(k, v)
        if elements is None and "elements" in m:
            elements = m["elements"]
        ref = m.get("parent")
    return elements or [], textures


def resolve_texture(textures, key):
    v, hops = "#" + key, 0
    while v.startswith("#") and hops < 12:
        v = textures.get(v[1:], "")
        hops += 1
    return v or None


# ─────────────────────────────── PNG ───────────────────────────────
def png_read(data):
    """8/16-bit and palette PNGs (non-interlaced) → (w, h, rows of RGBA tuples)."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    pos, idat, plte, trns = 8, [], None, None
    while pos < len(data):
        ln = struct.unpack(">I", data[pos:pos + 4])[0]
        typ, body = data[pos + 4:pos + 8], data[pos + 8:pos + 8 + ln]
        pos += 12 + ln
        if typ == b"IHDR":
            w, h, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", body)
        elif typ == b"PLTE":
            plte = body
        elif typ == b"tRNS":
            trns = body
        elif typ == b"IDAT":
            idat.append(body)
        elif typ == b"IEND":
            break
    if interlace:
        raise ValueError("interlaced PNG")
    ch = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    bits = ch * depth
    stride, bpp = (w * bits + 7) // 8, max(1, bits // 8)
    raw = zlib.decompress(b"".join(idat))
    rows, prev, i = [], bytearray(stride), 0
    for _ in range(h):
        f, line = raw[i], bytearray(raw[i + 1:i + 1 + stride])
        i += 1 + stride
        for x in range(stride):
            a = line[x - bpp] if x >= bpp else 0
            b = prev[x]
            c = prev[x - bpp] if x >= bpp else 0
            if f == 1:
                line[x] = (line[x] + a) & 255
            elif f == 2:
                line[x] = (line[x] + b) & 255
            elif f == 3:
                line[x] = (line[x] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append(line)
        prev = line
    out = []
    for line in rows:
        if depth == 16:
            s = list(line[::2])
        elif depth == 8:
            s = list(line)
        else:
            s = [(line[k * depth // 8] >> (8 - depth - (k * depth) % 8)) & ((1 << depth) - 1) for k in range(w * ch)]
        px = []
        for x in range(w):
            if ctype == 3:
                k = s[x]
                px.append(tuple(plte[3 * k:3 * k + 3]) + ((trns[k] if trns and k < len(trns) else 255),))
                continue
            v = s[x * ch:(x + 1) * ch]
            if depth < 8:
                v = [c * 255 // ((1 << depth) - 1) for c in v]
            px.append({1: lambda q: (q[0], q[0], q[0], 255), 2: lambda q: (q[0], q[0], q[0], q[1]),
                       3: lambda q: (q[0], q[1], q[2], 255), 4: tuple}[ch](v))
        out.append(px)
    return w, h, out


def png_write(path, w, h, rgb):
    raw = b"".join(b"\x00" + bytes(rgb[y * w * 3:(y + 1) * w * 3]) for y in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


class Texture:
    def __init__(self, data):
        self.w, h, self.px = png_read(data)
        self.h = self.w if h > self.w and h % self.w == 0 else h        # animated strip: the first frame

    def sample(self, u, v):
        """u, v in model texture units (0..16)."""
        x = min(self.w - 1, max(0, int(u / 16 * self.w)))
        y = min(self.h - 1, max(0, int(v / 16 * self.h)))
        return self.px[y][x]


# ─────────────────────────────── geometry ───────────────────────────────
def default_uv(face, a, b):
    x1, y1, z1 = a
    x2, y2, z2 = b
    return {"down": [x1, 16 - z2, x2, 16 - z1], "up": [x1, z1, x2, z2], "north": [16 - x2, 16 - y2, 16 - x1, 16 - y1],
            "south": [x1, 16 - y2, x2, 16 - y1], "west": [z1, 16 - y2, z2, 16 - y1], "east": [16 - z2, 16 - y2, 16 - z1, 16 - y1]}[face]


def face_param(face, a, b, s, t):
    """Point on a face for (s, t) in [0,1]²: s runs with the texture's u, t with v (top → bottom)."""
    x1, y1, z1 = a
    x2, y2, z2 = b
    lerp = lambda p, q, k: p + (q - p) * k
    if face == "north":
        return (lerp(x2, x1, s), lerp(y2, y1, t), z1), (0, 0, -1)
    if face == "south":
        return (lerp(x1, x2, s), lerp(y2, y1, t), z2), (0, 0, 1)
    if face == "west":
        return (x1, lerp(y2, y1, t), lerp(z1, z2, s)), (-1, 0, 0)
    if face == "east":
        return (x2, lerp(y2, y1, t), lerp(z2, z1, s)), (1, 0, 0)
    if face == "up":
        return (lerp(x1, x2, s), y2, lerp(z1, z2, t)), (0, 1, 0)
    return (lerp(x1, x2, s), y1, lerp(z2, z1, t)), (0, -1, 0)


def rotate(p, rot, about_origin=True):
    """Element rotation (degrees about one axis through `origin`), with vanilla's optional rescale."""
    if not rot:
        return p
    o = rot.get("origin", [8, 8, 8]) if about_origin else [0, 0, 0]
    ang = math.radians(rot.get("angle", 0))
    x, y, z = p[0] - o[0], p[1] - o[1], p[2] - o[2]
    ax = rot.get("axis", "y")
    if about_origin and rot.get("rescale"):
        k = 1 / max(1e-6, math.cos(abs(ang)))
        x, y, z = (x if ax == "x" else x * k), (y if ax == "y" else y * k), (z if ax == "z" else z * k)
    c, s = math.cos(ang), math.sin(ang)
    if ax == "x":
        y, z = y * c - z * s, y * s + z * c
    elif ax == "y":
        x, z = x * c + z * s, -x * s + z * c
    else:
        x, y = x * c - y * s, x * s + y * c
    return (x + o[0], y + o[1], z + o[2])


def uv_turn(s, t, deg):
    """Face "rotation": the texture turns clockwise on the face."""
    return {90: (t, 1 - s), 180: (1 - s, 1 - t), 270: (1 - t, s)}.get(int(deg) % 360, (s, t))


def render(pack, refs, out, yaw=35, pitch=25, W=900, H=460, gap=0, assets=(), tint=None, bg=(226, 230, 236)):
    """Render the models `refs` from `pack` (+ extra asset roots) into the PNG `out`. Returns out."""
    fs = Assets([pack, *assets])
    warn, cache = set(), {}
    ya, pa = math.radians(yaw), math.radians(pitch)
    light = (0.35, 0.8, -0.45)
    pts, dz = [], 0.0
    for n, ref in enumerate(refs):
        els, textures = load_model(fs, ref, warn)
        if not els:
            warn.add(f"{ref}: no elements (builtin/generated items are flat sprites; nothing to draw)")
            continue
        if n and gap:
            dz = n * gap
        for e in els:
            a, b = e["from"], e["to"]
            for face, fd in e.get("faces", {}).items():
                tref = resolve_texture(textures, fd.get("texture", "#missing").lstrip("#"))
                tx = None
                if tref:
                    if tref not in cache:
                        ns, path = split_id(tref)
                        data = fs.read(f"assets/{ns}/textures/{path}.png")
                        try:
                            cache[tref] = Texture(data) if data else None
                        except (ValueError, KeyError, zlib.error) as err:
                            cache[tref] = None
                            warn.add(f"texture {tref}: {err}")
                        if data is None:
                            warn.add(f"texture not found: {tref}")
                    tx = cache[tref]
                uv = fd.get("uv") or default_uv(face, a, b)
                area = {"north": (b[0] - a[0]) * (b[1] - a[1]), "south": (b[0] - a[0]) * (b[1] - a[1]),
                        "west": (b[2] - a[2]) * (b[1] - a[1]), "east": (b[2] - a[2]) * (b[1] - a[1]),
                        "up": (b[0] - a[0]) * (b[2] - a[2]), "down": (b[0] - a[0]) * (b[2] - a[2])}[face]
                k = max(6, int(math.sqrt(max(area, 0.01)) * 9))
                for i in range(k):
                    for j in range(k):
                        s_, t_ = (i + 0.5) / k, (j + 0.5) / k
                        p, nrm = face_param(face, a, b, s_, t_)
                        p = rotate(p, e.get("rotation"))
                        nrm = rotate(nrm, e.get("rotation"), about_origin=False)
                        col = (200, 0, 200)
                        if tx is not None:
                            su, tv = uv_turn(s_, t_, fd.get("rotation", 0))
                            px = tx.sample(uv[0] + (uv[2] - uv[0]) * su, uv[1] + (uv[3] - uv[1]) * tv)
                            if px[3] < 20:
                                continue
                            col = px[:3]
                            if tint and "tintindex" in fd:
                                col = tuple(c * t // 255 for c, t in zip(col, tint))
                        pts.append(((p[0], p[1], p[2] + dz), nrm, col))
        if not gap:
            zs = [z for e in els for z in (e["from"][2], e["to"][2])]
            dz += (max(zs) - min(zs)) + 1.0
    if not pts:
        raise SystemExit("nothing to draw: " + "; ".join(sorted(warn)))
    # camera: turn the row by yaw, then look down on it by pitch (depth z2 grows away from the viewer)
    xs = [q[0][0] for q in pts]; ys = [q[0][1] for q in pts]; zs = [q[0][2] for q in pts]
    cx, cy, cz = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, (min(zs) + max(zs)) / 2
    proj = []
    for (p, nrm, col) in pts:
        x, y, z = p[0] - cx, p[1] - cy, p[2] - cz
        x1 = x * math.cos(ya) - z * math.sin(ya)
        z1 = x * math.sin(ya) + z * math.cos(ya)
        y2 = y * math.cos(pa) + z1 * math.sin(pa)
        z2 = -y * math.sin(pa) + z1 * math.cos(pa)
        sh = 0.55 + 0.45 * max(0.0, nrm[0] * light[0] + nrm[1] * light[1] + nrm[2] * light[2])
        proj.append((x1, y2, z2, tuple(int(c * sh) for c in col)))
    span = max(max(abs(q[0]) for q in proj) * 2, max(abs(q[1]) for q in proj) * 2 * W / H) or 1
    sc = W * 0.9 / span
    img = bytearray(bytes(bg) * (W * H))
    zb = [1e9] * (W * H)
    for (x, y, z, col) in proj:
        u, v = int(W / 2 + x * sc), int(H / 2 - y * sc)
        for du in (0, 1):
            for dv in (0, 1):
                uu, vv = u + du, v + dv
                if 0 <= uu < W and 0 <= vv < H and z < zb[vv * W + uu]:
                    zb[vv * W + uu] = z
                    img[(vv * W + uu) * 3:(vv * W + uu) * 3 + 3] = bytes(col)
    png_write(out, W, H, img)
    for w_ in sorted(warn):
        print("warning:", w_, file=sys.stderr)
    return out


def _hex(s):
    s = s.lstrip("#")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)

    def opt(name, default, conv=str, many=False):
        vals = [conv(args[i + 1]) for i, v in enumerate(args[:-1]) if v == name]
        return vals if many else (vals[-1] if vals else default)
    size = opt("--size", "900x460")
    w, h = (int(v) for v in size.lower().split("x"))
    takes = {"--out", "--yaw", "--pitch", "--gap", "--size", "--assets", "--tint", "--bg"}
    refs = [v for i, v in enumerate(args[1:], 1) if ":" in v and args[i - 1] not in takes]
    print(render(args[0], refs, opt("--out", "preview.png"), opt("--yaw", 35, float), opt("--pitch", 25, float), w, h,
                 opt("--gap", 0, float), opt("--assets", [], str, many=True), opt("--tint", None, _hex), opt("--bg", (226, 230, 236), _hex)))
