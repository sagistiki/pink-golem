"""gen_club_pack.py — the club's music.

A seamless loop of original hard techno at 150 BPM, synthesised from scratch with numpy (no samples): a distorted
pitch-swept kick, an industrial rumble (the kick through a dark reverb, side-chained), off-beat open hats + 16th closed
hats, a clap with a tail, and a squelchy 303-style acid line with a slowly moving filter. 32 bars ≈ 51.2 s. The render
runs one extra bar and folds the tail back onto the start, so reverbs wrap around and the loop point is inaudible.
Mono Ogg Vorbis (positional in game), sounds.json event club:techno_loop (category record, stream).
Run: python3 gen_club_pack.py → club_pack/ + club_pack.zip + club/techno_loop_preview.ogg
"""
import json
import os
import shutil
import zipfile

import numpy as np
import soundfile as sf
from scipy.signal import butter, lfilter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "build")
SR = 44100
BPM = 150
BEAT = 60 / BPM
STEP = BEAT / 4                        # a 16th
BARS = 32
LOOP_S = BARS * 4 * BEAT               # 51.2 s
N = int(round(LOOP_S * SR))
rng = np.random.default_rng(1507)


def env_exp(n, tau):
    return np.exp(-np.arange(n) / (tau * SR))


def lp(x, fc, order=2):
    b, a = butter(order, min(fc, SR / 2 - 100) / (SR / 2), "low")
    return lfilter(b, a, x)


def hp(x, fc, order=2):
    b, a = butter(order, fc / (SR / 2), "high")
    return lfilter(b, a, x)


def kick():
    n = int(0.42 * SR); t = np.arange(n) / SR
    f = 44 + 150 * np.exp(-t / 0.035)                                # a fast pitch drop
    ph = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(ph) * env_exp(n, 0.16)
    click = rng.standard_normal(n) * env_exp(n, 0.002) * 0.6
    k = np.tanh(3.2 * (body + click))                                  # hard-clipped = hard techno
    return k / np.max(np.abs(k))


def clap():
    n = int(0.5 * SR); x = np.zeros(n)
    for d in (0, 0.009, 0.019, 0.031):                                 # the "flam" bursts of a clap
        s = int(d * SR); m = n - s
        x[s:] += rng.standard_normal(m) * env_exp(m, 0.012 if d < 0.03 else 0.14)
    x = hp(lp(x, 5200), 700)
    return x / np.max(np.abs(x))


def hat(open_):
    n = int((0.22 if open_ else 0.05) * SR)
    x = hp(rng.standard_normal(n), 7500, 4) * env_exp(n, 0.07 if open_ else 0.012)
    return x / np.max(np.abs(x))


def reverb(x, secs=1.6, damp=2500):
    """a cheap dark reverb: noise impulse response, exponentially decaying, low-passed"""
    n = int(secs * SR)
    ir = lp(rng.standard_normal(n), damp) * np.exp(-np.arange(n) / (secs / 5 * SR))
    ir /= np.sqrt(np.sum(ir ** 2))
    return np.convolve(x, ir)[: len(x)]


def place(track, sample, t, gain=1.0):
    s = int(round(t * SR)); e = min(len(track), s + len(sample))
    if s < len(track):
        track[s:e] += sample[: e - s] * gain


def acid_note(freq, dur, cutoff, reso=0.85, accent=False):
    """a 303-ish voice: saw → resonant low-pass whose cutoff sweeps down, a little drive"""
    n = int(dur * SR); t = np.arange(n) / SR
    saw = 2 * ((freq * t) % 1.0) - 1
    fc = cutoff * (0.25 + 0.75 * np.exp(-t / (0.09 if accent else 0.05)))
    y = np.zeros(n); lp1 = lp2 = bp = 0.0
    g = 2 * np.sin(np.pi * np.clip(fc, 40, 8000) / SR); q = 1 - reso
    for i in range(n):                                                  # a state-variable filter, per sample
        hp_ = saw[i] - lp1 - q * bp
        bp += g[i] * hp_
        lp1 += g[i] * bp
        y[i] = lp1
    y *= env_exp(n, 0.12 if accent else 0.07)
    return np.tanh(2.2 * y)


def build():
    L = N + int(4 * BEAT * SR)                                          # one spare bar for the tails
    kicks, rumble_src, claps, hats, acid = (np.zeros(L) for _ in range(5))
    K, C, HO, HC = kick(), clap(), hat(True), hat(False)
    for bar in range(BARS + 1):
        b0 = bar * 4 * BEAT
        for beat in range(4):
            place(kicks, K, b0 + beat * BEAT, 1.0)
            place(rumble_src, K, b0 + beat * BEAT, 1.0)
            place(hats, HO, b0 + beat * BEAT + 2 * STEP, 0.55)          # off-beat open hat
            if beat in (1, 3):
                place(claps, C, b0 + beat * BEAT, 0.7)
        for s16 in range(16):
            if s16 % 2 == 1 or bar % 4 == 3:
                place(hats, HC, b0 + s16 * STEP, 0.28 + 0.1 * (s16 % 4 == 3))
    # acid: a 16-step pattern in A (root 55 Hz ×2), accents + octave jumps, filter opens and closes over 16 bars
    pat = [(0, 1, 1), (None,), (0, 0, 0), (12, 1, 0), (0, 0, 0), (None,), (3, 0, 1), (0, 0, 0),
           (0, 1, 1), (7, 0, 0), (None,), (12, 1, 1), (0, 0, 0), (10, 0, 0), (0, 1, 0), (5, 0, 1)]
    for bar in range(BARS + 1):
        if bar < 4:
            continue                                                    # first 4 bars: drums only (a DJ-friendly start)
        sweep = 0.5 - 0.5 * np.cos(2 * np.pi * (bar % 16) / 16)         # 0 → 1 → 0 across 16 bars
        for i, st in enumerate(pat):
            if st[0] is None:
                continue
            semi, acc, slide = st
            f = 110 * 2 ** (semi / 12)
            v = acid_note(f, STEP * (1.6 if slide else 0.9), 250 + 2600 * sweep + (900 if acc else 0), 0.86, bool(acc))
            place(acid, v, bar * 4 * BEAT + i * STEP, 0.55 if acc else 0.4)
    # rumble: the kick through a dark reverb, low-passed, ducked on every kick (side-chain)
    rum = lp(reverb(rumble_src, 1.8, 900), 180, 4)
    duck = np.ones(L)
    for bar in range(BARS + 1):
        for beat in range(4):
            s = int((bar * 4 + beat) * BEAT * SR); m = int(BEAT * SR)
            seg = 1 - np.exp(-np.arange(m) / (0.07 * SR))
            duck[s:s + m] = np.minimum(duck[s:s + m], seg[: len(duck[s:s + m])])
    rum = rum / (np.max(np.abs(rum)) + 1e-9) * duck
    claps = claps + 0.35 * reverb(claps, 1.2, 3500)
    acid = acid * (0.55 + 0.45 * duck) + 0.18 * reverb(acid, 0.9, 3000)
    mix = 1.0 * kicks + 0.55 * rum + 0.45 * claps + 0.35 * hats + 0.62 * acid
    # fold the spare bar back onto the start → a seamless loop
    loop = mix[:N].copy()
    tail = mix[N:]
    loop[: len(tail)] += tail
    loop = np.tanh(1.4 * loop / np.max(np.abs(loop))) / np.tanh(1.4)  # glue + loudness
    loop *= 10 ** (-1 / 20)                                            # peak −1 dBFS
    return loop.astype(np.float32)


def main():
    y = build()
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    sd = os.path.join(OUT, "assets/club/sounds")
    os.makedirs(sd, exist_ok=True)
    sf.write(os.path.join(sd, "techno_loop.ogg"), y, SR, format="OGG", subtype="VORBIS")
    json.dump({"techno_loop": {"category": "record", "sounds": [{"name": "club:techno_loop", "stream": True}]}},
              open(os.path.join(OUT, "assets/club/sounds.json"), "w"), indent=1)
    json.dump({"pack": {"description": "Pink Golem club music", "min_format": 88, "max_format": 88}}, open(os.path.join(OUT, "pack.mcmeta"), "w"))
    z = os.path.join(HERE, "club.zip")
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(OUT):
            for f in sorted(files):
                p = os.path.join(root, f)
                zf.write(p, os.path.relpath(p, OUT))
        info = sf.info(os.path.join(sd, "techno_loop.ogg"))
    print(json.dumps({"zip": z, "kb": round(os.path.getsize(z) / 1024), "seconds": round(info.duration, 2),
                      "loop_ticks": round(LOOP_S * 20), "peak_db": round(float(20 * np.log10(np.max(np.abs(y)))), 2)}))


if __name__ == "__main__":
    main()
