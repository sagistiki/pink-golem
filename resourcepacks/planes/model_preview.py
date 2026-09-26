"""model_preview.py — render Minecraft item/block model JSON (elements + textures + element rotation) to a PNG with a
tiny point-splatting rasterizer, so a model can be checked without a game client.

    python3 model_preview.py <pack_dir> <ns:item/model> [<ns:item/model> ...] --out preview.png [--yaw 35] [--pitch 25]

Several models are drawn in a row along -z (like a train: the first model in front). Faces are shaded by their normal.
UVs follow the vanilla defaults per face (or the face's "uv"); good enough to see decals and orientation.
"""
import json
import math
import os
import sys

from PIL import Image


def load_model(pack, ref):
    ns, path = ref.split(":")
    m = json.load(open(os.path.join(pack, "assets", ns, "models", path + ".json")))
    tex = {}
    for k, v in m.get("textures", {}).items():
        tns, tpath = v.split(":") if ":" in v else ("minecraft", v)
        f = os.path.join(pack, "assets", tns, "textures", tpath + ".png")
        tex[k] = Image.open(f).convert("RGBA") if os.path.exists(f) else None
    return m["elements"], tex


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


def rotate(p, rot):
    if not rot:
        return p
    o = rot["origin"]
    a = math.radians(rot["angle"])
    x, y, z = p[0] - o[0], p[1] - o[1], p[2] - o[2]
    c, s = math.cos(a), math.sin(a)
    ax = rot["axis"]
    if ax == "x":
        y, z = y * c - z * s, y * s + z * c
    elif ax == "y":
        x, z = x * c + z * s, -x * s + z * c
    else:
        x, y = x * c - y * s, x * s + y * c
    return (x + o[0], y + o[1], z + o[2])


def render(pack, refs, out, yaw=35, pitch=25, W=900, H=460, gap=18.5):
    img = Image.new("RGB", (W, H), (226, 230, 236))
    zb = [[1e9] * W for _ in range(H)]
    ya, pa = math.radians(yaw), math.radians(pitch)
    light = (0.35, 0.8, -0.45)
    pts = []
    for n, ref in enumerate(refs):
        els, tex = load_model(pack, ref)
        dz = n * gap
        for e in els:
            a, b = e["from"], e["to"]
            for face, fd in e["faces"].items():
                t = tex.get(fd["texture"].lstrip("#"))
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
                        nrm = rotate((nrm[0], nrm[1], nrm[2]), {"origin": [0, 0, 0], **e["rotation"]} if e.get("rotation") else None)
                        col = (200, 0, 200)
                        if t is not None:
                            u = uv[0] + (uv[2] - uv[0]) * s_
                            v = uv[1] + (uv[3] - uv[1]) * t_
                            px = t.getpixel((min(t.width - 1, max(0, int(u / 16 * t.width))), min(t.height - 1, max(0, int(v / 16 * t.height)))))
                            if px[3] < 20:
                                continue
                            col = px[:3]
                        pts.append(((p[0], p[1], p[2] + dz), nrm, col))
    # camera: look at the train from the front-left, above
    xs = [q[0][0] for q in pts]; ys = [q[0][1] for q in pts]; zs = [q[0][2] for q in pts]
    cx, cy, cz = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, (min(zs) + max(zs)) / 2
    proj = []
    for (p, nrm, col) in pts:
        x, y, z = p[0] - cx, p[1] - cy, p[2] - cz
        x1 = x * math.cos(ya) - z * math.sin(ya)
        z1 = x * math.sin(ya) + z * math.cos(ya)
        y2 = y * math.cos(pa) - z1 * math.sin(pa)
        z2 = y * math.sin(pa) + z1 * math.cos(pa)
        sh = 0.55 + 0.45 * max(0.0, nrm[0] * light[0] + nrm[1] * light[1] + nrm[2] * light[2])
        proj.append((x1, y2, z2, tuple(int(c * sh) for c in col)))
    span = max(max(abs(q[0]) for q in proj) * 2, max(abs(q[1]) for q in proj) * 2 * W / H) or 1
    sc = W * 0.9 / span
    for (x, y, z, col) in proj:
        u, v = int(W / 2 + x * sc), int(H / 2 - y * sc)
        for du in (0, 1):
            for dv in (0, 1):
                uu, vv = u + du, v + dv
                if 0 <= uu < W and 0 <= vv < H and z < zb[vv][uu]:
                    zb[vv][uu] = z
                    img.putpixel((uu, vv), col)
    img.save(out)
    return out


if __name__ == "__main__":
    args = sys.argv[1:]
    out = args[args.index("--out") + 1] if "--out" in args else "preview.png"
    yaw = float(args[args.index("--yaw") + 1]) if "--yaw" in args else 35
    pitch = float(args[args.index("--pitch") + 1]) if "--pitch" in args else 25
    refs = [a for a in args[1:] if ":" in a]
    print(render(args[0], refs, out, yaw, pitch))
