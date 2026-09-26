"""track.py — the coaster's track geometry, physics simulation and frames (quaternions). No dependencies.

The track is drawn with a TURTLE: straights and arcs in the horizontal plane whose height follows a cubic Hermite
(y and slope continuous at every joint), plus a vertical LOOP element (a teardrop: tangent angle θ 0..2π with the
radius shrinking from Rb at the bottom to Rt at the top, drifting sideways by `shift`). Everything is sampled every
0.1 block, then resampled every DS = 0.5 block of 3D arc length for the app.

Frames: forward f = tangent; up u = world-up made perpendicular to f, then rolled by the bank angle (computed from
the simulated speed: atan(v²·κ / g), smoothed); inside the loop u points to the loop centre. l = u × f (left).
A car / display frame maps display x → l, y → u, z → f (one quaternion per sample).

Physics (coaster.sc runs the same every tick): g = 0.0245 blocks/tick² (real gravity at 1 block = 1 m), quadratic
drag + rolling resistance, the train's slope = the mean over its cars (it speeds up as more cars pass a crest); a
chain lift holds 0.30 b/t while any car is on it, tyres push 0.2 b/t in the station, brakes bleed to 0.22 b/t.
The head car stops 4 blocks before the end of the first "station" section.

Design check, before you build anything:
    python3 track.py                          the default layout: length, lap time, closure, top speed, stalls, G
    python3 track.py --layout my_ride.py      your own layout(t) function (see README.md, "Your own layout")
    python3 track.py --plot /tmp/ride         + a top view and a side profile PNG (height orange, speed blue)
"""
import argparse
import importlib.util
import math
import os
import sys

G = 0.0245            # blocks / tick²  (9.81 m/s² ÷ (20 ticks/s)², 1 block = 1 m)
DRAG = 0.0012         # per block (a -= DRAG·v²)
ROLL = 0.0004         # blocks / tick²
LIFT_V = 0.30
TYRE_V = 0.20
BRAKE_V = 0.22
N_CARS = 5
CAR_GAP = 2.45        # car centre to car centre, blocks (the single-seat cars of pack.py)
DS = 0.5              # app sample spacing (3D arc length)
FINE = 0.1
STOP_BEFORE_END = 4.0  # the head car stops this far before the end of the station section
YAW = {"south": 0.0, "west": 90.0, "north": 180.0, "east": 270.0}   # Minecraft yaw of each heading


def fwd(yaw):
    r = math.radians(yaw)
    return (-math.sin(r), math.cos(r))


def right_of(yaw):
    r = math.radians(yaw)
    return (-math.cos(r), -math.sin(r))


class Turtle:
    """Draws the track. Starts at (x, y, z) heading `yaw` (Minecraft yaw: 0 south, 90 west, 180 north, 270 east)."""

    def __init__(self, x, y, z, yaw):
        self.x, self.y, self.z, self.yaw, self.m = x, y, z, yaw, 0.0
        self.x0, self.y0, self.z0, self.yaw0 = x, y, z, yaw
        self.pts = [(x, y, z, None)]           # (x, y, z, loop_up or None)
        self.tags = []                          # (tag, fine index from, to)

    def along(self):
        """How far ahead of the start the turtle is, measured along the start heading."""
        f = fwd(self.yaw0)
        return (self.x - self.x0) * f[0] + (self.z - self.z0) * f[1]

    def side(self):
        """How far right of the start line the turtle is."""
        r = right_of(self.yaw0)
        return (self.x - self.x0) * r[0] + (self.z - self.z0) * r[1]

    def _mark(self, tag, i0):
        if tag:
            self.tags.append((tag, i0, len(self.pts) - 1))

    def seg(self, L, turn=0.0, y1=None, m1=0.0, tag=None):
        """Horizontal length L, turning `turn` degrees (right +), height Hermite (y, slope) → (y1, m1)."""
        i0 = len(self.pts) - 1
        y0, m0 = self.y, self.m
        if y1 is None:
            y1 = y0
        n = max(2, int(round(L / FINE)))
        x, z, yaw0 = self.x, self.z, self.yaw
        for i in range(1, n + 1):
            t = i / n
            yaw = yaw0 + turn * (t - 0.5 / n)
            dx, dz = fwd(yaw)
            x += dx * L / n
            z += dz * L / n
            h00, h10, h01, h11 = 2 * t ** 3 - 3 * t ** 2 + 1, t ** 3 - 2 * t ** 2 + t, -2 * t ** 3 + 3 * t ** 2, t ** 3 - t ** 2
            y = h00 * y0 + h10 * L * m0 + h01 * y1 + h11 * L * m1
            self.pts.append((x, y, z, None))
        self.x, self.z, self.y, self.m, self.yaw = x, z, y1, m1, yaw0 + turn
        self._mark(tag, i0)

    def loop(self, Rb, Rt, shift, tag="loop"):
        """A vertical teardrop loop: radius Rb at the bottom, Rt at the top, ending `shift` blocks to the right."""
        i0 = len(self.pts) - 1
        fx, fz = fwd(self.yaw)
        rx, rz = right_of(self.yaw)
        x0, y0, z0 = self.x, self.y, self.z
        F = U = 0.0
        th = 0.0
        while th < 2 * math.pi:
            r = Rb + (Rt - Rb) * (1 - math.cos(th)) / 2
            dth = min(FINE / r, 2 * math.pi - th)
            tm = th + dth / 2
            rm = Rb + (Rt - Rb) * (1 - math.cos(tm)) / 2
            F += rm * math.cos(tm) * dth
            U += rm * math.sin(tm) * dth
            th += dth
            lat = shift * (th - math.sin(th)) / (2 * math.pi)
            up = (-math.sin(th) * fx, math.cos(th), -math.sin(th) * fz)
            self.pts.append((x0 + fx * F + rx * lat, y0 + U, z0 + fz * F + rz * lat, up))
        self.x, self.y, self.z = self.pts[-1][0], self.pts[-1][1], self.pts[-1][2]
        self.m = 0.0
        self._mark(tag, i0)


def layout(t):
    """The demo ride: ~662 blocks, a 43° chain lift to 67 above the station, a 67° first drop, a 24.5-high teardrop
    loop, a climbing 180, an airtime hill, a rising banked helix, a bunny hop, brakes. It turns RIGHT (the platform
    is on the left) and with the station needs 46 × 213 blocks, 74 high: from 10 behind the station start to 35
    ahead of it (along the station), and from 8 left of the track to 204 right of it. Heights are relative to the
    station track (B)."""
    B = t.y0
    t.seg(24, tag="station")                                   # the station straight
    t.seg(15.7, turn=90, tag="tyres")                           # a right turn, r 10
    t.seg(8, y1=B + 2.5, m1=0.95, tag="lift")                   # onto the lift
    t.seg(66, y1=B + 65.2, m1=0.95, tag="lift")                 # the chain lift, 43°
    t.seg(9, y1=B + 67.0, m1=-0.9, tag="lift")                  # crest
    t.seg(34, y1=B + 18.0, m1=-2.0)                             # first drop (steepest ~67°)
    t.seg(30, y1=B + 0.5, m1=0.0)                               # pull-out
    t.seg(6, y1=B + 0.5)
    t.loop(16.0, 8.5, 3.0, tag="loop")                          # the loop (24.5 high), drifting 3 to the right
    t.seg(8, y1=B + 1.0)
    r = (t.along() + 8) / 2                                     # the 180 lands the return leg 8 behind the start
    t.seg(r * math.pi / 2, turn=90, y1=B + 14.0, m1=0.0)        # climbing 180 …
    t.seg(r * math.pi / 2, turn=90, y1=B + 8.0, m1=-0.3)        # … now heading back, parallel to the way out
    t.seg(18, y1=B + 0.5, m1=0.0)                               # valley
    t.seg(28, y1=B + 10.0, m1=0.0, tag="air")                   # airtime hill (9.5 high, long enough to float)
    t.seg(28, y1=B + 0.5, m1=0.0)
    t.seg(6, y1=B + 0.5)
    t.seg(62.83, turn=360, y1=B + 7.5, m1=0.0, tag="helix")     # rising helix, r 10, banked
    t.seg(20, y1=B + 0.5, m1=0.0)
    t.seg(16, y1=B + 4.5, m1=0.0, tag="air")                    # bunny hop
    t.seg(16, y1=B + 0.5, m1=0.0)
    rest = t.side() - 8                                         # straight left before the last turn
    t.seg(rest - 12, y1=B + 0.5, tag="brakes")
    t.seg(12, y1=B, m1=0.0, tag="brakes")
    t.seg(8 * math.pi / 2, turn=90, y1=B, tag="tyres")          # r 8 into the station
    return t


def load_layout(path):
    """A layout file is Python with a function layout(t) (it may import math); returns that function."""
    spec = importlib.util.spec_from_file_location("coaster_layout", os.path.abspath(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.layout


def resample(pts):
    """Uniform 3D arc length samples: list of (x, y, z, loop_up or None) every DS, plus total length."""
    cum = [0.0]
    for a, b in zip(pts, pts[1:]):
        cum.append(cum[-1] + math.dist(a[:3], b[:3]))
    L = cum[-1]
    out, j = [], 0
    s = 0.0
    while s < L - 1e-6:
        while cum[j + 1] < s:
            j += 1
        a, b = pts[j], pts[j + 1]
        k = (s - cum[j]) / max(1e-9, cum[j + 1] - cum[j])
        p = tuple(a[i] + (b[i] - a[i]) * k for i in range(3))
        up = b[3] if b[3] is not None else a[3]
        out.append((p[0], p[1], p[2], up))
        s += DS
    return out, L, cum


def norm(v):
    n = math.sqrt(sum(c * c for c in v)) or 1.0
    return tuple(c / n for c in v)


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def tangents(S):
    n = len(S)
    return [norm(tuple(S[(i + 1) % n][k] - S[(i - 1) % n][k] for k in range(3))) for i in range(n)]


def tag_ranges(t, cum, L):
    """Map fine-index tag ranges to arc-length ranges [(tag, s0, s1)]."""
    return [(tag, cum[i0], cum[i1]) for (tag, i0, i1) in t.tags]


def in_tag(tags, s, name, L):
    s %= L
    return any(tg == name and s0 <= s <= s1 for (tg, s0, s1) in tags)


def station_stop(tags):
    """Arc length where the head car stops: STOP_BEFORE_END before the end of the first "station" section."""
    st = [c for (tg, a, c) in tags if tg == "station"]
    if not st:
        raise SystemExit("the layout needs a section tagged 'station' (the first one, where riders board)")
    return round(st[0] - STOP_BEFORE_END, 2)


def simulate(S, tags, L, stop=20.0, n_cars=N_CARS, gap=CAR_GAP):
    """One lap from the station stop. Returns per-sample speed (max seen there), time, min free speed, max speed."""
    n = len(S)
    ys = [p[1] for p in S]

    def slope(s):
        i = int(s / DS) % n
        return (ys[(i + 1) % n] - ys[i]) / DS

    s, v, t = stop, 0.0, 0           # head car at the stop (station), train behind it
    speed = [0.0] * n
    vmin_free, vmax, stalls = 9.0, 0.0, []
    travelled = 0.0
    while travelled < L and t < 20 * 400:
        cars = [s - k * gap for k in range(n_cars)]
        a = -G * sum(slope(c) for c in cars) / n_cars          # samples are 3D arc length apart: Δy/DS = sin(pitch)
        v += a - DRAG * v * abs(v) - ROLL * (1 if v > 0 else -1 if v < 0 else 0)
        on = lambda name: any(in_tag(tags, c, name, L) for c in cars)
        if on("lift"):
            v = LIFT_V
        elif in_tag(tags, s, "brakes", L) and v > BRAKE_V:
            v = max(BRAKE_V, v * 0.93)
        elif (on("tyres") or on("station")) and v < TYRE_V:
            v = min(TYRE_V, v + 0.02)
        elif not (on("tyres") or on("station")):
            vmin_free = min(vmin_free, v)
            if v < 0.08:
                stalls.append(round(s % L, 1))
        vmax = max(vmax, v)
        speed[int(s / DS) % n] = max(speed[int(s / DS) % n], v)
        s += v
        travelled += v
        t += 1
    return speed, t, vmin_free, vmax, stalls


def frames(S, speed, tags, L):
    """Per sample: forward, up, left (display x→l, y→u, z→f).
    Note: speed[i] is the top speed seen AT sample i; above DS per tick the train jumps over samples, which keep 0 and
    bank as if at 0.2 b/t. After the ±6-block smoothing that softens the bank on fast stretches. The demo ride was
    tuned (and ridden) with exactly this, so it stays."""
    n = len(S)
    T = tangents(S)
    # horizontal curvature (signed, + = right turn) for banking
    bank = []
    for i in range(n):
        a, b = T[(i - 2) % n], T[(i + 2) % n]
        ha, hb = math.atan2(a[0], a[2]), math.atan2(b[0], b[2])
        d = (hb - ha + math.pi) % (2 * math.pi) - math.pi
        horiz = math.hypot(T[i][0], T[i][2])
        kappa = -d / (4 * DS) if horiz > 0.3 else 0.0          # + = turning right (MC yaw grows)
        v = max(speed[i], 0.2)
        bank.append(math.atan2(v * v * kappa, G))
    # smooth the bank over ~6 blocks, cap 72°
    w = 12
    sb = [sum(bank[(i + k) % n] for k in range(-w, w + 1)) / (2 * w + 1) for i in range(n)]
    sb = [max(-math.radians(72), min(math.radians(72), b)) for b in sb]
    out = []
    for i in range(n):
        f = T[i]
        if S[i][3] is not None:
            u = S[i][3]
            u = norm(tuple(u[k] - f[k] * dot(u, f) for k in range(3)))
        else:
            wu = (0.0, 1.0, 0.0)
            u0 = norm(tuple(wu[k] - f[k] * dot(wu, f) for k in range(3)))
            r = cross(f, u0)                         # right = f × u
            b = sb[i]
            u = norm(tuple(u0[k] * math.cos(b) + r[k] * math.sin(b) for k in range(3)))
        l = cross(u, f)
        out.append((f, u, l))
    return out


def quat(l, u, f):
    """Rotation matrix with columns l, u, f → quaternion (x, y, z, w)."""
    m00, m01, m02 = l[0], u[0], f[0]
    m10, m11, m12 = l[1], u[1], f[1]
    m20, m21, m22 = l[2], u[2], f[2]
    tr = m00 + m11 + m22
    if tr > 0:
        s = math.sqrt(tr + 1.0) * 2
        return ((m21 - m12) / s, (m02 - m20) / s, (m10 - m01) / s, 0.25 * s)
    if m00 > m11 and m00 > m22:
        s = math.sqrt(1.0 + m00 - m11 - m22) * 2
        return (0.25 * s, (m01 + m10) / s, (m02 + m20) / s, (m21 - m12) / s)
    if m11 > m22:
        s = math.sqrt(1.0 + m11 - m00 - m22) * 2
        return ((m01 + m10) / s, 0.25 * s, (m12 + m21) / s, (m02 - m20) / s)
    s = math.sqrt(1.0 + m22 - m00 - m11) * 2
    return ((m02 + m20) / s, (m12 + m21) / s, 0.25 * s, (m10 - m01) / s)


class Track:
    """Everything the builder and the app need, from one layout."""

    def __init__(self, start=(0.0, 0.0, 0.0), yaw=270.0, layout_fn=layout, n_cars=N_CARS, gap=CAR_GAP):
        t = Turtle(start[0], start[1], start[2], yaw)
        layout_fn(t)
        S, L, cum = resample(t.pts)
        tags = tag_ranges(t, cum, L)
        self.stop = station_stop(tags)
        self.n_cars, self.gap = n_cars, gap
        speed, ticks, vmin, vmax, stalls = simulate(S, tags, L, self.stop, n_cars, gap)
        F = frames(S, speed, tags, L)
        Q = []
        prev = None
        for (f, u, l) in F:
            q = quat(l, u, f)
            if prev and sum(a * b for a, b in zip(q, prev)) < 0:
                q = tuple(-c for c in q)                 # keep neighbours in the same hemisphere: the app lerps them
            Q.append(q)
            prev = q
        self.turtle, self.S, self.L, self.tags, self.speed = t, S, L, tags, speed
        self.ticks, self.vmin, self.vmax, self.stalls, self.F, self.Q = ticks, vmin, vmax, stalls, F, Q

    def ranges(self, name):
        return [(a, c) for (tg, a, c) in self.tags if tg == name]

    def g_forces(self):
        return g_forces(self.S, self.F, self.speed)

    def report(self):
        """Human-readable checks. Returns (lines, problems, notes): problems break the ride (it does not close, the
        train stalls); notes are things a real coaster would not do (G beyond +5 / -1.5, crawling over a crest) —
        riders feel nothing in Minecraft, but the stats screen shows the G and a crawl is a stall waiting to happen."""
        S, L = self.S, self.L
        gs = self.g_forces()
        ys = [p[1] for p in S]; xs = [p[0] for p in S]; zs = [p[2] for p in S]
        gap = math.dist(S[-1][:3], S[0][:3])
        lines = [f"length {L:.1f} blocks, {len(S)} samples, lap {self.ticks / 20:.1f} s, {self.n_cars} cars, stop at s {self.stop}",
                 f"closure: the last sample is {gap:.2f} blocks from the first (closed when it is at most {DS})",
                 f"x {min(xs):.1f}..{max(xs):.1f}  y {min(ys):.1f}..{max(ys):.1f}  z {min(zs):.1f}..{max(zs):.1f}",
                 f"speed max {self.vmax:.2f} b/t = {self.vmax * 72:.0f} km/h, min free {self.vmin:.2f} b/t, stalls {self.stalls[:5]}",
                 f"g max {max(gs):.1f}, min {min(gs):.1f}"]
        for (tag, s0, s1) in self.tags:
            lines.append(f"  {tag:8s} s {s0:6.1f} .. {s1:6.1f}  y {ys[int(s0 / DS) % len(S)]:.1f} → {ys[int(s1 / DS) % len(S)]:.1f}")
        problems, notes = [], []
        if gap > 1.2 * DS:
            problems.append(f"the track does not close: the end is {gap:.2f} blocks from the start")
        if self.stalls:
            problems.append(f"the train stalls at s {self.stalls[:5]} (below 0.08 b/t outside lift/tyres): lower that hill or add speed")
        if self.vmin < 0.12 and not self.stalls:
            notes.append(f"the train crawls over a crest (min {self.vmin:.2f} b/t): little margin")
        hi = [i * DS for i, g in enumerate(gs) if g > 5.0]
        lo = [i * DS for i, g in enumerate(gs) if g < -1.5]
        if hi:
            notes.append(f"{max(gs):.1f} G (over 5 G on {len(hi) * DS:.1f} blocks, first at s {hi[0]:.0f}): a real train would need a wider curve there")
        if lo:
            notes.append(f"{min(gs):.1f} G (under -1.5 G on {len(lo) * DS:.1f} blocks, first at s {lo[0]:.0f}): a real train would leave the rails, round that crest")
        return lines, problems, notes

    def plot(self, out_dir):
        """Top view (height = yellow → orange) and side profile (height orange, speed blue) as PNG."""
        from canvas import Canvas
        S, L = self.S, self.L
        xs = [p[0] for p in S]; zs = [p[2] for p in S]; ys = [p[1] for p in S]
        k = 4
        x0, z0 = min(xs) - 10, min(zs) - 10
        W, H = int((max(xs) - x0 + 10) * k), int((max(zs) - z0 + 10) * k)
        im = Canvas(W, H, (30, 30, 30))
        for gx in range(int(x0) // 10 * 10, int(max(xs)) + 20, 10):
            im.line((gx - x0) * k, 0, (gx - x0) * k, H, (60, 60, 60))
            im.text((gx - x0) * k + 2, 2, gx, (160, 160, 160))
        for gz in range(int(z0) // 10 * 10, int(max(zs)) + 20, 10):
            im.line(0, (gz - z0) * k, W, (gz - z0) * k, (60, 60, 60))
            im.text(2, (gz - z0) * k + 2, gz, (160, 160, 160))
        y_lo, y_hi = min(ys), max(ys)
        for i in range(len(S) - 1):
            c = int(max(0, min(255, (S[i][1] - y_lo) / max(1, y_hi - y_lo) * 255)))
            im.line((S[i][0] - x0) * k, (S[i][2] - z0) * k, (S[i + 1][0] - x0) * k, (S[i + 1][2] - z0) * k, (255, 255 - c, 60), width=3)
        os.makedirs(out_dir, exist_ok=True)
        top = im.save(os.path.join(out_dir, "track_top.png"))
        hs = 2.5
        im2 = Canvas(int(L * 2) + 20, int((y_hi - y_lo) * hs) + 60, (30, 30, 30))
        base = im2.h - 10
        for i in range(len(S) - 1):
            im2.line(i + 10, base - (S[i][1] - y_lo) * hs, i + 11, base - (S[i + 1][1] - y_lo) * hs, (255, 120, 40), width=2)
            if self.speed[i] > 0:                      # 0 = a sample the train jumped over (> DS per tick)
                im2.put(i + 10, int(base - self.speed[i] * 80), (80, 200, 255))
        side = im2.save(os.path.join(out_dir, "track_profile.png"))
        return top, side


def g_forces(S, F, speed):
    """Felt vertical g (along the car's up) per sample: (v²κ·n + g·up)/g."""
    n = len(S)
    out = []
    for i in range(n):
        a, b, c = S[(i - 2) % n], S[i], S[(i + 2) % n]
        acc = tuple((a[k] - 2 * b[k] + c[k]) / (2 * DS) ** 2 for k in range(3))   # curvature vector
        v = speed[i]
        cent = tuple(acc[k] * v * v for k in range(3))
        felt = tuple(cent[k] + (0, G, 0)[k] for k in range(3))
        out.append(dot(felt, F[i][1]) / G)
    return out


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(description="Check a coaster layout: length, closure, speeds, stalls, G.")
    ap.add_argument("--layout", help="a .py file with layout(t) (default: the demo ride)")
    ap.add_argument("--cars", type=int, default=N_CARS)
    ap.add_argument("--plot", metavar="DIR", help="write track_top.png and track_profile.png into DIR")
    a = ap.parse_args()
    trk = Track((0.0, 0.0, 0.0), YAW["east"], load_layout(a.layout) if a.layout else layout, n_cars=a.cars)
    lines, problems, notes = trk.report()
    print("\n".join(lines + ["note: " + n for n in notes]))
    print("\n".join("PROBLEM: " + p for p in problems) if problems else "OK: the track closes and the train never stalls")
    if a.plot:
        print("plots:", *trk.plot(a.plot))
