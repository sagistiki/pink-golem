"""siren_check.py — catch siren-like sounds BEFORE they ship. Some players live where air-raid and rocket-alert sirens
are real: a wail in a game can be a trauma trigger, not an effect.

    python3 siren_check.py a.ogg b.wav ...       # files
    python3 siren_check.py some/dir              # every .ogg/.wav under it
    python3 siren_check.py pack.zip [prefix]     # every .ogg inside a resource-pack zip (optionally under a path prefix)

A pitch tracker (McLeod NSDF, 70-2500 Hz) follows every clearly pitched stretch; vibrato is smoothed away.
  ✗ GLIDE  the pitch moves >= 2 semitones (x1.12) one way over >= 0.3 s: wails, wind-ups, falling calls, sweeping
           whines, slide and kettle whistles, long trombone bends. Falling glides count as much as rising ones.
  ⚠ TONE   a nearly pure tone (sine-like, one partial) held >= 0.6 s — a swelling sine chord was heard as a "sine
           siren" too. A quick bell or ding that dies away is fine; never as a random ambience sound.
Exit code 1 when any GLIDE is found. Judge the ⚠ ones by ear and context. Needs numpy and soundfile.
"""
import io
import os
import sys
import zipfile

import numpy as np
import soundfile as sf

FMIN, FMAX = 70.0, 2500.0
WIN, HOP = 2048, 256
CLARITY = 0.85        # NSDF key maximum: a clearly pitched frame
GATE_DB = -35         # frames quieter than this (vs the loudest frame) are ignored
GLIDE_ST, GLIDE_S = 2.0, 0.3
TONE_S, PURE = 0.6, 0.8


def _frames(y):
    n = 1 + max(0, (len(y) - WIN) // HOP)
    y = np.pad(y, (0, max(0, WIN - len(y))))
    idx = np.arange(WIN)[None, :] + HOP * np.arange(n)[:, None]
    return y[idx]


def track(y, sr):
    """per frame: (f0 or nan, pure 0/1)"""
    F = _frames(y)
    rms = np.sqrt((F ** 2).mean(axis=1)) + 1e-12
    loud = 20 * np.log10(rms / rms.max()) > GATE_DB
    X = np.fft.rfft(F, 2 * WIN, axis=1)
    r = np.fft.irfft(np.abs(X) ** 2, axis=1)[:, :WIN]
    c = np.cumsum(F ** 2, axis=1)
    tot = c[:, -1:]
    lags = np.arange(WIN)
    m = c[:, WIN - 1 - lags] + tot - np.concatenate([np.zeros((len(F), 1)), c[:, :-1]], axis=1)
    nsdf = 2 * r / (m + 1e-12)
    lo, hi = int(sr / FMAX), int(sr / FMIN)
    win = np.hanning(WIN)
    freqs = np.fft.rfftfreq(WIN, 1 / sr)
    f0, pure = np.full(len(F), np.nan), np.zeros(len(F))
    for i in np.nonzero(loud)[0]:
        d = nsdf[i, :hi + 2]
        peaks = [k for k in range(max(lo, 1), hi + 1) if d[k] > 0 and d[k] >= d[k - 1] and d[k] > d[k + 1]]
        if not peaks:
            continue
        top = max(d[k] for k in peaks)
        if top < CLARITY:
            continue
        k = next(k for k in peaks if d[k] >= 0.9 * top)
        a, b, cc = d[k - 1], d[k], d[k + 1]
        tau = k + 0.5 * (a - cc) / (a - 2 * b + cc + 1e-12)
        f = sr / tau
        f0[i] = f
        sp = np.abs(np.fft.rfft(F[i] * win)) ** 2
        band = (freqs > 50) & (freqs < 8000)
        near = band & (np.abs(freqs - f) < max(0.03 * f, 1.6 * sr / WIN))
        pure[i] = sp[near].sum() / (sp[band].sum() + 1e-12) >= PURE
    return f0, pure


def _runs(f0):
    """stretches of pitched frames whose pitch moves < 1 semitone per frame (gaps of <= 3 frames bridged)"""
    out, cur, gap = [], [], 0
    for i, f in enumerate(f0):
        if np.isnan(f):
            gap += 1
            if gap > 3 and cur:
                out.append(cur)
                cur = []
            continue
        if cur and abs(12 * np.log2(f / f0[cur[-1]])) >= 1:
            out.append(cur)
            cur = []
        cur.append(i)
        gap = 0
    if cur:
        out.append(cur)
    return out


def _zigzag(t, s, rev=0.5):
    """pivots where the contour turns back by more than `rev` semitones"""
    piv, ext, dirn = [0], 0, 0
    for i in range(1, len(s)):
        if dirn >= 0 and s[i] >= s[ext] or dirn <= 0 and s[i] <= s[ext]:
            ext = i
            if dirn == 0 and abs(s[i] - s[0]) > rev:
                dirn = 1 if s[i] > s[0] else -1
        elif abs(s[i] - s[ext]) > rev:
            piv.append(ext)
            dirn = -1 if s[i] < s[ext] else 1
            ext = i
    piv.append(ext if ext != piv[-1] else len(s) - 1)
    return piv


def check(y, sr):
    if y.ndim > 1:
        y = y.mean(axis=1)
    f0, pure = track(y.astype(np.float64), sr)
    dt = HOP / sr
    found = []
    for run in _runs(f0):
        if len(run) * dt < GLIDE_S:
            continue
        t = np.array(run) * dt
        st = 12 * np.log2(f0[run])
        k = max(1, int(0.2 / dt))                            # 0.2 s moving average removes vibrato
        s = np.convolve(np.pad(st, (k // 2, k - 1 - k // 2), mode="edge"), np.ones(k) / k, mode="valid")
        piv = _zigzag(t, s)
        for a, b in zip(piv, piv[1:]):
            d, dur = s[b] - s[a], t[b] - t[a]
            if abs(d) >= GLIDE_ST and dur >= GLIDE_S:
                fa, fb = 2 ** (s[a] / 12), 2 ** (s[b] / 12)
                found.append(("GLIDE", f"{'rise' if d > 0 else 'fall'} {fa:.0f}->{fb:.0f} Hz "
                                       f"({abs(d):.1f} st) over {dur:.2f} s at {t[a]:.2f} s"))
        p = pure[run]
        if p.mean() >= 0.8 and len(run) * dt >= TONE_S:
            found.append(("TONE", f"pure tone ~{np.nanmedian(f0[run]):.0f} Hz held {len(run) * dt:.2f} s at {t[0]:.2f} s"))
    return found


def _sources(args):
    if args[0].endswith(".zip"):
        z = zipfile.ZipFile(args[0])
        pre = args[1] if len(args) > 1 else ""
        for n in sorted(z.namelist()):
            if n.endswith(".ogg") and n.startswith(pre):
                yield n, lambda n=n: sf.read(io.BytesIO(z.read(n)))
        return
    for a in args:
        if os.path.isdir(a):
            for root, _, files in os.walk(a):
                for f in sorted(files):
                    if f.endswith((".ogg", ".wav")):
                        p = os.path.join(root, f)
                        yield p, lambda p=p: sf.read(p)
        else:
            yield a, lambda a=a: sf.read(a)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    n = glides = 0
    for name, load in _sources(sys.argv[1:]):
        y, sr = load()
        n += 1
        for kind, msg in check(y, sr):
            glides += kind == "GLIDE"
            print(("✗ GLIDE " if kind == "GLIDE" else "⚠ TONE  ") + f"{name}: {msg}")
    print(f"{'✓' if not glides else '✗'} {n} sounds checked, {glides} siren-like glides")
    sys.exit(1 if glides else 0)
