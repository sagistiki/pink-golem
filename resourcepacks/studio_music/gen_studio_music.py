"""gen_studio_music.py — original music for the character studio (lift ride + runway show), synthesised from scratch.

Everything is composed here (chords, melodies, rhythms) and rendered with numpy — no samples, no existing melodies.
Same technique as gen_club_pack.py: per-note synth voices placed on a CIRCULAR buffer (tails wrap round to the start,
so every piece loops without a seam), whole-bus effects applied circularly, mono Ogg Vorbis via soundfile.

1. LIFT LOFI — 80 BPM, F major, 24 bars = 72 s, sliced into 6 segments of exactly 4 bars (12.0 s):
     seg0 A   Bbmaj9 | Am9 | Gm9 | C9sus4→C7b9      keys + bass + soft rim-shot groove, a tiny e-piano fill
     seg1 A'  (same)                                  the flute theme enters, 16th hats (swing 58 %)
     seg2 B   Dm9 | Am9 | Bbmaj9 | C9sus4→C7b9       brighter, brushed snare, the theme answered higher
     seg3 B'  Dm9 | Am9 | Bbmaj9 | Bbm6→C7b9         a borrowed minor iv, a soft pad, ghost notes
     seg4 A'' Bbmaj9 | Am9 | Gm9 | C9sus4→C7b9      the theme varied high, pad
     seg5 out Fmaj9 | Dm9 | Gm9 | C9sus4→C7b9       drums drop out then return, a pickup fill back into seg0
   FM/Rhodes-style e-piano, a breathy sine flute, a round sine+triangle bass, muted kick / rim / brush / swung hats,
   vinyl crackle + hiss, tape wow & flutter, low-pass warmth. Peak ≈ −8 dBFS. 20 ms fade in/out at every slice.
2. RUNWAY SHOW — 120 BPM nu-disco / disco-house in D major (B dorian verse), 32 bars = 64.0 s, loopable:
     0–3 intro (filter opening) · 4–11 verse Bm9 E9 Gmaj9 A6/9 · 12–15 chorus Gmaj9 A6/9 F#m7 Bm7 + hook ·
     16–19 breakdown (pad + bell hook) · 20–23 build (snare roll, riser, gap) · 24–27 drop · 28–31 groove + fill.
   Four-on-the-floor kick, claps on 2 & 4, off-beat open hats, octave bass, plucky saw chord stabs, a square/saw
   lead with a dotted-8th echo, side-chain pump. Peak ≈ −3 dBFS.
   + runway.pose: a 2.6 s camera-flash / paparazzi-shutter / crowd-cheer sting (not streamed).

Pack: namespace lounge — assets/lounge/sounds.json + assets/lounge/sounds/{lift,runway}/*.ogg, pack.mcmeta format 88.
Sound events: lounge:lift.lofi_0 … lift.lofi_5, lounge:runway.show (all "stream": true), lounge:runway.pose.
Run: python3 gen_studio_music.py → studio_music_pack/ + studio_music_pack.zip + previews/studio_music_waveforms.png
     (+ studio_music/lofi_full_preview.ogg — the 6 segments back to back, for listening; not in the pack)
"""
import json
import os
import shutil
import zipfile

import numpy as np
import soundfile as sf
from scipy.signal import butter, fftconvolve, sosfilt

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "build")
ZIP = os.path.join(HERE, "studio_music.zip")
PNG = os.path.join(HERE, "previews", "studio_music_waveforms.png")
PREVIEW_DIR = os.path.join(HERE, "previews")
NS = "lounge"
SR = 32000                       # mono 32 kHz keeps the pack small; 16 kHz of bandwidth is plenty in game
VORBIS_LEVEL = 0.62              # libsndfile compression level (0 = best); ≈ Vorbis quality 0.38
rng = np.random.default_rng(2809)
TAU = 2 * np.pi


# ----------------------------------------------------------------------------------------------------------------
# shared DSP helpers
# ----------------------------------------------------------------------------------------------------------------
def mtof(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def _sos(kind, fc, order=2):
    ny = SR / 2
    if kind == "band":
        lo, hi = fc
        return butter(order, [max(lo, 20) / ny, min(hi, ny - 200) / ny], "band", output="sos")
    return butter(order, min(max(fc, 20), ny - 200) / ny, kind, output="sos")


def lp(x, fc, order=2):
    return sosfilt(_sos("low", fc, order), x)


def hp(x, fc, order=2):
    return sosfilt(_sos("high", fc, order), x)


def bp(x, lo, hi, order=2):
    return sosfilt(_sos("band", (lo, hi), order), x)


def circ(fn, x):
    """apply a causal filter as if x repeated forever: run it over two copies and keep the second (steady state)"""
    n = len(x)
    return fn(np.concatenate([x, x]))[n:]


def env_exp(n, tau):
    return np.exp(-np.arange(n) / (tau * SR))


def gate(n, dur, attack, release):
    """raised-cosine attack, hold until `dur`, raised-cosine release over `release` s"""
    e = np.ones(n)
    na = max(1, int(attack * SR))
    na = min(na, n)
    e[:na] = 0.5 - 0.5 * np.cos(np.pi * np.arange(na) / na)
    nd = int(dur * SR)
    if nd < n:
        m = n - nd
        e[nd:] *= 0.5 + 0.5 * np.cos(np.pi * np.arange(m) / m)
    return e


def creverb(x, secs=1.8, damp=3000, predelay=0.015):
    """a soft noise-IR reverb, applied circularly (the tail wraps round to the loop start)"""
    n = int(secs * SR)
    ir = lp(rng.standard_normal(n), damp) * np.exp(-np.arange(n) / (secs / 6 * SR))
    ir[: int(predelay * SR)] = 0
    ir /= np.sqrt(np.sum(ir ** 2))
    y = fftconvolve(x, ir)
    out = y[: len(x)].copy()
    tail = y[len(x):]
    out[: len(tail)] += tail
    return out


def active_rms(x):
    f = 1600
    m = len(x) // f
    r = np.sqrt(np.mean(x[: m * f].reshape(m, f) ** 2, axis=1))
    if r.max() <= 0:
        return 1e-9
    act = r[r > 0.05 * r.max()]
    return float(np.sqrt(np.mean(act ** 2)))


def level(x, db):
    """scale a bus so its RMS (over the frames where it actually plays) sits at `db` dBFS"""
    return x * (10 ** (db / 20) / active_rms(x))


class Bus:
    """a circular mix buffer: anything that runs past the end wraps to the start (seamless loops)"""

    def __init__(self, n):
        self.n = n
        self.b = np.zeros(n)

    def add(self, t, x, g=1.0):
        s = int(round(t * SR)) % self.n
        L = len(x)
        e = s + L
        if e <= self.n:
            self.b[s:e] += g * x
        else:
            k = self.n - s
            self.b[s:] += g * x[:k]
            self.b[: L - k] += g * x[k:]


def duck_env(n, times, depth, recover=0.09, span=0.45):
    """side-chain: 1 → (1-depth) at each kick, recovering exponentially"""
    d = np.ones(n)
    m = int(span * SR)
    curve = 1 - depth * np.exp(-np.arange(m) / (recover * SR))
    for t in times:
        s = int(round(t * SR)) % n
        idx = (s + np.arange(m)) % n
        d[idx] = np.minimum(d[idx], curve)
    return d


def write_ogg(path, y):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sf.write(path, np.asarray(y, dtype=np.float32), SR, format="OGG", subtype="VORBIS", compression_level=VORBIS_LEVEL)


# ----------------------------------------------------------------------------------------------------------------
# 1. LIFT LOFI
# ----------------------------------------------------------------------------------------------------------------
L_BPM = 80
L_BEAT = 60 / L_BPM              # 0.75 s
L_BAR = 4 * L_BEAT               # 3.0 s
SEG_BARS = 4
NSEG = 6
SEG_S = SEG_BARS * L_BAR         # 12.0 s
L_N = int(round(NSEG * SEG_S * SR))
SWING = 0.58

# chord name → (bass MIDI note, e-piano voicing without the root)
L_CHORDS = {
    "Bbmaj9": (34, [62, 65, 69, 72]),      # D F A C
    "Am9":    (33, [60, 64, 67, 71]),      # C E G B
    "Gm9":    (31, [53, 57, 58, 62]),      # F A Bb D
    "C9sus":  (36, [58, 62, 65, 67]),      # Bb D F G
    "C7b9":   (36, [58, 61, 64, 67]),      # Bb Db E G
    "Dm9":    (38, [53, 57, 60, 64]),      # F A C E
    "Bbm6":   (34, [61, 65, 67, 70]),      # Db F G Bb
    "Fmaj9":  (41, [57, 60, 64, 67]),      # A C E G
}
_A = [[(0, "Bbmaj9")], [(0, "Am9")], [(0, "Gm9")], [(0, "C9sus"), (2, "C7b9")]]
L_PROG = [
    _A,
    _A,
    [[(0, "Dm9")], [(0, "Am9")], [(0, "Bbmaj9")], [(0, "C9sus"), (2, "C7b9")]],
    [[(0, "Dm9")], [(0, "Am9")], [(0, "Bbmaj9")], [(0, "Bbm6"), (2, "C7b9")]],
    _A,
    [[(0, "Fmaj9")], [(0, "Dm9")], [(0, "Gm9")], [(0, "C9sus"), (2, "C7b9")]],
]

# melody per segment: (beat within the 16-beat segment, MIDI, length in beats, instrument)
F, E = "fl", "ep"
L_MELODY = [
    [(11.5, 77, .5, E), (12, 76, .5, E), (12.5, 74, 1.5, E), (14.5, 72, .5, E), (15, 69, 1.0, E)],
    [(0.5, 69, .5, F), (1, 72, 1.0, F), (2.5, 74, .5, F), (3, 72, 1.5, F),
     (5, 76, 1.0, F), (6, 74, .5, F), (6.5, 72, 1.5, F),
     (8.5, 74, .5, F), (9, 77, 1.5, F), (10.5, 76, .5, F), (11, 74, 1.0, F),
     (12, 72, 1.0, F), (13, 70, .5, F), (13.5, 69, .5, F), (14, 67, 1.5, F)],
    [(1.5, 81, .5, F), (2, 79, .5, F), (2.5, 77, 1.5, F),
     (4.5, 76, .5, F), (5, 79, 1.0, F), (6, 76, .5, F), (6.5, 72, 1.0, F),
     (8, 74, 1.5, F), (9.5, 77, .5, F), (10, 81, 1.5, F), (11.5, 79, .5, F),
     (12, 77, 1.0, F), (13, 74, .5, F), (14, 76, 1.5, F), (15.5, 74, .5, F)],
    [(0, 77, 1.0, F), (1, 76, .5, F), (1.5, 74, .5, F), (2, 72, 1.5, F), (3.5, 69, .5, F),
     (4, 72, .5, F), (4.5, 74, .5, F), (5, 76, 2.0, F), (7.5, 79, .5, F),
     (8, 81, 1.0, F), (9, 79, .5, F), (9.5, 77, .5, F), (10, 74, 2.0, F),
     (12, 73, 1.0, F), (13, 72, .5, F), (14, 70, .5, F), (14.5, 67, 1.5, F)],
    [(0.5, 77, .5, F), (1, 81, 1.0, F), (2.5, 79, .5, F), (3, 77, 1.0, F),
     (4.5, 76, 1.5, F), (6, 72, .5, F), (6.5, 69, 1.5, F),
     (8.5, 70, .5, F), (9, 74, .5, F), (9.5, 77, 1.0, F), (10.5, 81, 1.0, F), (11.5, 79, .5, F),
     (12, 77, 1.5, F), (13.5, 74, .5, F), (14, 76, 1.0, F), (15, 79, 1.0, F)],
    [(1, 72, 1.5, F), (5, 76, 2.0, F), (9, 74, 1.0, F), (10, 70, 2.0, F),
     (14.5, 69, .5, E), (15, 72, .5, E), (15.5, 74, .5, E)],
]


def l_time(seg, bar, beat):
    return (seg * SEG_BARS + bar) * L_BAR + beat * L_BEAT


def swing16(step):
    """time (in beats) of a 16th step inside a bar, the off 16ths pushed late (58 % swing)"""
    return (step // 2) * 0.5 + (step % 2) * SWING * 0.5


def chord_at(seg, bar, beat):
    name = L_PROG[seg][bar][0][1]
    for b0, nm in L_PROG[seg][bar]:
        if beat >= b0:
            name = nm
    return name


def next_root(seg, bar):
    bar += 1
    if bar == SEG_BARS:
        bar, seg = 0, (seg + 1) % NSEG
    return L_CHORDS[L_PROG[seg][bar][0][1]][0]


def ep_voice(f, dur, vel):
    """FM electric piano: 1:1 FM with a decaying index (bark) + a quiet 7× tine ping, soft release"""
    rel = 0.35
    n = int((dur + rel) * SR)
    t = np.arange(n) / SR
    idx = (0.3 + 1.6 * vel) * np.exp(-t / 0.3) + 0.2
    y = np.sin(TAU * f * t + idx * np.sin(TAU * f * t))
    y += 0.08 * vel * np.sin(TAU * f * 7.0 * t) * env_exp(n, 0.015)
    y += 0.12 * np.sin(TAU * 2 * f * t) * env_exp(n, 0.4)
    amp = env_exp(n, 1.8 if f < 300 else 1.2) * gate(n, dur, 0.004, rel)
    return y * amp * vel


def flute_voice(f, dur, vel):
    """a soft breathy flute: sine + few harmonics, delayed vibrato, a breath-noise layer"""
    rel = 0.2
    n = int((dur + rel) * SR)
    t = np.arange(n) / SR
    vib = 1 + 0.0045 * np.sin(TAU * 5.1 * t) * np.clip((t - 0.18) / 0.3, 0, 1)
    ph = TAU * np.cumsum(f * vib) / SR
    y = np.sin(ph) + 0.18 * np.sin(2 * ph) + 0.05 * np.sin(3 * ph)
    breath = bp(rng.standard_normal(n), f * 1.5, min(f * 6, 9000)) * (0.10 + 0.12 * env_exp(n, 0.06))
    amp = gate(n, dur, 0.07, rel) * (0.85 + 0.15 * env_exp(n, 0.3))
    return (y + breath) * amp * vel


def l_bass_voice(f, dur, vel):
    rel = 0.09
    n = int((dur + rel) * SR)
    t = np.arange(n) / SR
    tri = 2 / np.pi * np.arcsin(np.sin(TAU * f * t))
    y = np.tanh(1.6 * (0.8 * np.sin(TAU * f * t) + 0.35 * tri))
    return y * gate(n, dur, 0.012, rel) * (0.75 + 0.25 * env_exp(n, 0.5)) * vel


def pad_voice(f, dur, vel):
    rel = 0.9
    n = int((dur + rel) * SR)
    t = np.arange(n) / SR
    y = np.zeros(n)
    for det in (-0.006, 0.0, 0.0055):
        ph0 = rng.uniform(0, 1)
        y += 2 * ((f * (1 + det) * t + ph0) % 1.0) - 1
    y = lp(y, 900)
    return y * gate(n, dur, 0.7, rel) * vel


def soft_kick():
    n = int(0.4 * SR)
    t = np.arange(n) / SR
    f = 48 + 70 * np.exp(-t / 0.03)
    y = np.sin(TAU * np.cumsum(f) / SR) * env_exp(n, 0.2) * gate(n, 0.4, 0.002, 0.0)
    return lp(np.tanh(1.3 * y), 900)


def soft_snare():
    n = int(0.3 * SR)
    t = np.arange(n) / SR
    y = bp(rng.standard_normal(n), 1100, 5000) * env_exp(n, 0.09) * 0.8
    y += np.sin(TAU * 185 * t) * env_exp(n, 0.05) * 0.55
    return lp(y * gate(n, 0.3, 0.0015, 0.0), 5200)


def brush():
    n = int(0.3 * SR)
    y = bp(rng.standard_normal(n), 2000, 7000) * gate(n, 0.3, 0.012, 0.0) * env_exp(n, 0.12)
    return y


def rim():
    n = int(0.08 * SR)
    t = np.arange(n) / SR
    y = np.sin(TAU * 1650 * t) * env_exp(n, 0.010) + 0.5 * bp(rng.standard_normal(n), 2000, 6000) * env_exp(n, 0.005)
    return lp(y, 5000)


def soft_hat(open_=False):
    n = int((0.2 if open_ else 0.06) * SR)
    y = hp(rng.standard_normal(n), 6500, 2) * env_exp(n, 0.06 if open_ else 0.016)
    return lp(y, 11000)


def vinyl(n):
    """crackle (sparse filtered clicks + rare pops) and a faint hiss"""
    imp = np.zeros(n)
    k = rng.poisson(9 * n / SR)
    imp[rng.integers(0, n, k)] = rng.lognormal(0, 0.8, k) * rng.choice([-1, 1], k)
    kp = rng.poisson(0.25 * n / SR)
    imp[rng.integers(0, n, kp)] += rng.uniform(3, 6, kp) * rng.choice([-1, 1], kp)
    kern = rng.standard_normal(40) * np.exp(-np.arange(40) / 6)
    clicks = circ(lambda z: lp(hp(z, 1200), 6500), np.convolve(imp, kern, "same"))
    hiss = circ(lambda z: lp(hp(z, 700), 5000), rng.standard_normal(n))
    return clicks / (np.max(np.abs(clicks)) + 1e-9) + 0.06 * hiss / np.std(hiss)


def wow_flutter(x):
    """tape wow & flutter: a slowly modulated read position (integer cycles over the loop → seamless)"""
    n = len(x)
    t = np.arange(n) / SR
    d_ms = 1.1 * (1 + np.sin(TAU * 0.5 * t)) + 1.5 * (1 + np.sin(TAU * t / 12 + 1.0)) + 0.05 * np.sin(TAU * 6.0 * t)
    pos = np.arange(n) - d_ms * 1e-3 * SR
    return np.interp(pos, np.arange(n), x, period=n)


def render_lofi():
    n = L_N
    keys, flute, bass, pad = Bus(n), Bus(n), Bus(n), Bus(n)
    kick, snare, hats, crack = Bus(n), Bus(n), Bus(n), None
    K, S, BR, RIM, HC, HO = soft_kick(), soft_snare(), brush(), rim(), soft_hat(), soft_hat(True)
    kick_times = []

    def hum(t):
        return t + rng.normal(0, 0.004)

    def vj(v):
        return v * rng.uniform(0.9, 1.08)

    for seg in range(NSEG):
        for bar in range(SEG_BARS):
            chords = L_PROG[seg][bar]
            # --- e-piano comping (strummed a touch, slightly behind the beat = lazy lofi feel) ---
            for ci, (b0, name) in enumerate(chords):
                b1 = chords[ci + 1][0] if ci + 1 < len(chords) else 4
                voicing = L_CHORDS[name][1]
                if b1 - b0 == 4:
                    hits = [(0, 2.4, .55), (2.5 + (SWING - .5), 1.3, .40)]
                    if seg in (2, 3) and bar % 2 == 1:
                        hits = [(0, 1.6, .55), (1.75, 0.6, .35), (2.5 + (SWING - .5), 1.3, .42)]
                    if seg == 0 or (seg == 5 and bar < 2):
                        hits = [(0, 3.6, .5)]
                else:
                    hits = [(0, (b1 - b0) - 0.2, .5)]
                for hb, hd, hv in hits:
                    t0 = l_time(seg, bar, b0 + hb) + 0.012
                    for i, m in enumerate(voicing):
                        keys.add(hum(t0 + i * 0.014), ep_voice(mtof(m), hd * L_BEAT, vj(hv * (0.85 + 0.05 * i))))
                # pad (B', A'' and a hint in B)
                if seg in (3, 4) or (seg == 2 and bar >= 2):
                    for m in voicing:
                        pad.add(l_time(seg, bar, b0), pad_voice(mtof(m - 12 if m > 64 else m), (b1 - b0) * L_BEAT, 0.5))
            # --- bass ---
            root = L_CHORDS[chord_at(seg, bar, 0)][0]
            simple = seg == 0 and bar < 2 or seg == 5 and bar < 2
            if simple:
                bass.add(l_time(seg, bar, 0) + 0.01, l_bass_voice(mtof(root), 3.4 * L_BEAT, 0.9))
            else:
                r2 = L_CHORDS[chord_at(seg, bar, 2.5)][0]
                bass.add(hum(l_time(seg, bar, 0) + 0.01), l_bass_voice(mtof(root), 1.7 * L_BEAT, vj(.95)))
                fifth = r2 + (7 if (bar + seg) % 2 == 0 else 12)
                bass.add(hum(l_time(seg, bar, 2.5 + (SWING - .5))), l_bass_voice(mtof(fifth), 0.8 * L_BEAT, vj(.7)))
                nr = next_root(seg, bar)
                approach = nr - 1 if (bar % 2 == 1) else r2
                bass.add(hum(l_time(seg, bar, 3.5 + (SWING - .5))), l_bass_voice(mtof(approach), 0.4 * L_BEAT, vj(.6)))
            # --- drums ---
            no_kick = seg == 5 and bar < 2
            kick_steps = [0, 10] if bar % 2 == 0 else [0, 7, 10]
            if not no_kick:
                for st in kick_steps:
                    t = hum(l_time(seg, bar, swing16(st)))
                    kick.add(t, K, vj(1.0 if st == 0 else 0.75))
                    kick_times.append(t)
            for bt in (1, 3):
                t = hum(l_time(seg, bar, bt) + 0.008)
                if seg == 0 or no_kick:
                    snare.add(t, RIM, vj(0.55))
                elif seg in (2, 3):
                    snare.add(t, S, vj(0.75))
                    snare.add(t - 0.01, BR, vj(0.6))
                else:
                    snare.add(t, S, vj(0.8))
            if seg == 3 or (seg == 1 and bar == 3):
                for st in (7, 15):
                    snare.add(hum(l_time(seg, bar, swing16(st))), S, vj(0.18))
            if seg == 5 and bar == 3:                                           # the fill back into segment 0
                for st, v in ((13, .25), (14, .35), (15, .5)):
                    snare.add(hum(l_time(seg, bar, swing16(st))), S, vj(v))
            sixteenths = seg in (1, 2, 3, 4) and not no_kick
            for st in range(16):
                if st % 2 == 1 and not sixteenths:
                    continue
                v = (0.55 if st % 4 == 0 else 0.42) if st % 2 == 0 else 0.22
                smp = HO if (st == 14 and seg in (2, 3)) else HC
                hats.add(hum(l_time(seg, bar, swing16(st))), smp, vj(v))
        # --- melody ---
        for beat, m, dur, inst in L_MELODY[seg]:
            t = hum(l_time(seg, 0, beat) + 0.015)
            if inst == F:
                flute.add(t, flute_voice(mtof(m), dur * L_BEAT * 0.95, vj(0.8)))
            else:
                keys.add(t, ep_voice(mtof(m), dur * L_BEAT, vj(0.55)))

    # --- buses: warmth, gentle pump, space ---
    t = np.arange(n) / SR
    keys_b = circ(lambda z: lp(z, 3200), keys.b) * (1 + 0.08 * np.sin(TAU * 4.5 * t))   # e-piano tremolo (4.5 Hz → whole cycles)
    pump = duck_env(n, kick_times, 0.18, 0.12)
    keys_b *= pump
    pad_b = pad.b * pump
    flute_b = circ(lambda z: lp(z, 4500), flute.b)
    bass_b = circ(lambda z: lp(z, 420, 2), bass.b)
    drums = (level(kick.b, -20) + level(snare.b, -27) + level(hats.b, -36))
    drums = circ(lambda z: lp(z, 6500), np.tanh(1.5 * drums / np.max(np.abs(drums))) * np.max(np.abs(drums)) / 1.3)
    keys_b = level(keys_b, -20)
    flute_b = level(flute_b, -22.5)
    pad_b = level(pad_b, -31)
    bass_b = level(bass_b, -21)
    wet = creverb(keys_b + flute_b + 0.5 * level(snare.b, -27), 2.2, 2600)
    mus = keys_b + flute_b + pad_b + bass_b + drums + 0.22 * wet
    mus = wow_flutter(mus)
    mus = circ(lambda z: lp(z, 5500), mus)                                    # the "low-pass warmth"
    mix = mus + level(vinyl(n), -41)
    mix = np.tanh(1.2 * mix / np.max(np.abs(mix)))
    mix *= 10 ** (-8.3 / 20) / np.max(np.abs(mix))                            # peak −8 dBFS (−0.3 for Vorbis overshoot)
    return mix


def slice_lofi(mix):
    seg_n = int(round(SEG_S * SR))
    fn = int(0.02 * SR)
    ramp = 0.5 - 0.5 * np.cos(np.pi * np.arange(fn) / fn)
    segs = []
    for i in range(NSEG):
        s = mix[i * seg_n:(i + 1) * seg_n].copy()
        s[:fn] *= ramp
        s[-fn:] *= ramp[::-1]
        segs.append(s)
    return segs


# ----------------------------------------------------------------------------------------------------------------
# 2. RUNWAY SHOW
# ----------------------------------------------------------------------------------------------------------------
R_BPM = 120
R_BEAT = 60 / R_BPM              # 0.5 s
R_BAR = 4 * R_BEAT               # 2.0 s
R_BARS = 32
R_N = int(round(R_BARS * R_BAR * SR))
R_STEP = R_BEAT / 4

R_CHORDS = {
    "Bm9":   (35, [62, 66, 69, 73]),       # D F# A C#
    "E9":    (40, [62, 66, 68, 71]),       # D F# G# B
    "Gmaj9": (43, [59, 62, 66, 69]),       # B D F# A
    "A69":   (45, [61, 64, 66, 71]),       # C# E F# B
    "F#m7":  (42, [61, 64, 66, 69]),       # C# E F# A
    "Bm7":   (35, [62, 66, 69, 71]),       # D F# A B
}
PROG_A = ["Bm9", "E9", "Gmaj9", "A69"]
PROG_B = ["Gmaj9", "A69", "F#m7", "Bm7"]


def section(bar):
    if bar < 4:
        return "intro"
    if bar < 12:
        return "verse"
    if bar < 16:
        return "chorus"
    if bar < 20:
        return "break"
    if bar < 24:
        return "build"
    if bar < 28:
        return "drop"
    return "groove"


def r_chord(bar):
    return (PROG_B if section(bar) in ("chorus", "break", "drop") else PROG_A)[bar % 4]


# hook over PROG_B, one list per bar: (beat, MIDI, beats)
HOOK = [
    [(0, 83, .5), (.5, 86, .5), (1.5, 83, .5), (2, 81, .75), (3, 78, .5), (3.5, 81, .5)],
    [(0, 85, .75), (.75, 83, .25), (1, 81, .5), (1.5, 76, 1.5), (3.5, 78, .5)],
    [(0, 81, .5), (.5, 85, .5), (1, 88, .75), (2, 85, .5), (2.5, 81, .5), (3, 83, 1.0)],
    [(0, 86, .5), (.5, 85, .25), (.75, 83, 1.25), (2.5, 78, .5), (3, 81, .5), (3.5, 83, .5)],
]
# answer motif over PROG_A
MOTIF = [
    [(.5, 78, .5), (1, 81, .5), (1.5, 83, 1.0), (3, 81, .5), (3.5, 78, .5)],
    [(.5, 80, .5), (1, 83, .5), (1.5, 83, 1.0), (3, 78, 1.0)],
    [(.5, 78, .5), (1, 81, .5), (1.5, 83, 1.0), (3, 86, .5), (3.5, 83, .5)],
    [(0, 85, 1.0), (1, 83, .5), (1.5, 81, 1.5), (3.5, 76, .5)],
]
# octave bass: (16th step, octave up?, length in 16ths, semitone offset)
BASS_PAT = [(0, 0, 1.6, 0), (2, 1, .8, 0), (3, 0, .6, 0), (4, 0, .8, 0), (6, 1, .8, 0), (8, 0, .8, 0),
            (10, 1, .8, 0), (11, 0, .6, 0), (12, 0, .8, 0), (14, 1, .8, 0), (15, 1, .6, -5)]


def saw(f, t, ph0=0.0):
    return 2 * ((f * t + ph0) % 1.0) - 1


def r_kick():
    n = int(0.45 * SR)
    t = np.arange(n) / SR
    f = 50 + 125 * np.exp(-t / 0.04)
    y = np.sin(TAU * np.cumsum(f) / SR) * env_exp(n, 0.26)
    y += rng.standard_normal(n) * env_exp(n, 0.0015) * 0.3
    return np.tanh(1.8 * y) / np.tanh(1.8)


def r_clap():
    n = int(0.45 * SR)
    x = np.zeros(n)
    for d in (0, 0.008, 0.017, 0.027):
        s = int(d * SR)
        m = n - s
        x[s:] += rng.standard_normal(m) * env_exp(m, 0.01 if d < 0.027 else 0.11)
    x = hp(lp(x, 6000), 800)
    return x / np.max(np.abs(x))


def r_snare():
    n = int(0.25 * SR)
    t = np.arange(n) / SR
    y = bp(rng.standard_normal(n), 1500, 8000) * env_exp(n, 0.07) + 0.6 * np.sin(TAU * 200 * t) * env_exp(n, 0.04)
    return y / np.max(np.abs(y))


def r_hat(open_):
    n = int((0.26 if open_ else 0.05) * SR)
    y = hp(rng.standard_normal(n), 7500, 4) * env_exp(n, 0.08 if open_ else 0.011)
    return y / np.max(np.abs(y))


def r_crash():
    n = int(2.6 * SR)
    t = np.arange(n) / SR
    metal = sum(np.sign(np.sin(TAU * f * t)) for f in (587, 845, 1120, 1433, 1735, 2090))
    y = hp(rng.standard_normal(n) + 0.25 * metal, 4500, 2) * env_exp(n, 0.8)
    return y / np.max(np.abs(y))


def r_bass_voice(f, dur, vel):
    rel = 0.03
    n = int((dur + rel) * SR)
    t = np.arange(n) / SR
    x = 0.6 * saw(f, t) + 0.4 * np.sign(np.sin(TAU * f * t))
    dark, bright = lp(x, 260), lp(x, 2000)
    e = env_exp(n, 0.05)
    y = dark + (bright - dark) * e + 0.6 * np.sin(TAU * f * t)
    return np.tanh(1.4 * y) * gate(n, dur, 0.003, rel) * vel


def stab_voice(freqs, dur, vel, bright=1.0):
    rel = 0.08
    n = int((dur + rel) * SR)
    t = np.arange(n) / SR
    x = np.zeros(n)
    for f in freqs:
        for det in (-0.005, 0.0, 0.005):
            x += saw(f * (1 + det), t, rng.uniform(0, 1))
    x /= 3 * len(freqs)
    dark = lp(x, 600)
    br = lp(x, 900 + 5500 * bright)
    y = dark + (br - dark) * env_exp(n, 0.07)
    return y * gate(n, dur, 0.002, rel) * env_exp(n, max(dur, 0.1)) * vel


def lead_voice(f, dur, vel, bell=False):
    rel = 0.25 if bell else 0.09
    n = int((dur + rel) * SR)
    t = np.arange(n) / SR
    vib = 1 + 0.005 * np.sin(TAU * 5.6 * t) * np.clip((t - 0.15) / 0.2, 0, 1)
    ph = TAU * np.cumsum(f * vib) / SR
    if bell:                                          # the breakdown voice: a soft FM bell
        y = np.sin(ph + 1.2 * env_exp(n, 0.25) * np.sin(3.5 * ph)) * env_exp(n, 0.6)
        return y * gate(n, dur, 0.003, rel) * vel
    x = 0.55 * np.tanh(3.5 * np.sin(ph)) + 0.35 * (2 * ((ph / TAU) % 1.0) - 1) + 0.2 * np.sin(2 * ph)
    dark, bright = lp(x, 1600), lp(x, 6000)
    y = dark + (bright - dark) * env_exp(n, 0.15)
    amp = gate(n, dur, 0.004, rel) * (0.7 + 0.3 * env_exp(n, 0.2))
    return y * amp * vel


def r_pad_voice(f, dur, vel):
    rel = 0.6
    n = int((dur + rel) * SR)
    t = np.arange(n) / SR
    y = sum(saw(f * (1 + d), t, rng.uniform(0, 1)) for d in (-0.007, 0, 0.006))
    return lp(y, 1500) * gate(n, dur, 0.35, rel) * vel


def riser(secs):
    n = int(secs * SR)
    t = np.arange(n) / SR
    noise = rng.standard_normal(n)
    dark, bright = bp(noise, 300, 1500), hp(noise, 2500)
    k = (t / secs) ** 2
    y = dark * (1 - k) + bright * k
    sweep = np.sin(TAU * np.cumsum(250 * 2 ** (2.3 * t / secs)) / SR) * 0.25
    return (y / np.max(np.abs(y)) + sweep) * (t / secs) ** 1.5


def render_runway():
    n = R_N
    kick, clap, hats_o, hats_c, snare, crash = (Bus(n) for _ in range(6))
    bass, stabs, lead, pad, fx = (Bus(n) for _ in range(5))
    K, C, SN, HO, HC, CR = r_kick(), r_clap(), r_snare(), r_hat(True), r_hat(False), r_crash()
    kick_times = []

    def T(bar, beat=0.0):
        return bar * R_BAR + beat * R_BEAT

    def vj(v):
        return v * rng.uniform(0.92, 1.06)

    for bar in range(R_BARS):
        sec = section(bar)
        ch = r_chord(bar)
        root, voicing = R_CHORDS[ch]
        freqs = [mtof(m) for m in voicing]
        # ---------------- drums ----------------
        for beat in range(4):
            gap = sec == "build" and bar == 23 and beat >= 2
            if sec != "break" and not gap:
                kick.add(T(bar, beat), K, 1.0)
                kick_times.append(T(bar, beat))
            if beat in (1, 3) and sec not in ("build",) and not (sec == "break" and bar < 18):
                clap.add(T(bar, beat), C, vj(0.55 if sec == "break" else 0.9))
            if not gap and sec != "break" and not (sec == "intro" and bar < 2):
                hats_o.add(T(bar, beat + 0.5), HO, vj(0.7))
        if sec in ("verse", "chorus", "drop", "groove", "intro"):
            for st in range(16):
                hats_c.add(T(bar) + st * R_STEP + (0.006 if st % 2 else 0), HC, vj(0.5 if st % 4 == 2 else 0.3))
        if sec == "break" and bar >= 18:
            for st in range(0, 16, 2):
                hats_c.add(T(bar) + st * R_STEP, HC, vj(0.25))
        if sec == "build":                                                         # snare roll 4ths → 8ths → 16ths
            k = bar - 20
            steps = {0: range(0, 16, 4), 1: range(0, 16, 2), 2: range(16), 3: range(8)}[k]
            for st in steps:
                v = 0.3 + 0.6 * ((k * 16 + st) / 56)
                snare.add(T(bar) + st * R_STEP, SN, v)
        if bar == 31:                                                              # fill back to the top
            for st in (12, 13, 14, 15):
                snare.add(T(bar) + st * R_STEP, SN, 0.45 + 0.1 * (st - 12))
        if bar in (0, 4, 12, 24, 28):
            crash.add(T(bar), CR, 1.0 if bar == 24 else 0.6)
        # ---------------- bass ----------------
        if sec == "break":
            bass.add(T(bar), r_bass_voice(mtof(root), 1.8, 0.55))
        elif sec == "build":
            last = 2 if bar == 23 else 4
            for e8 in range(last * 2):
                bass.add(T(bar, e8 * 0.5), r_bass_voice(mtof(root), 0.2, 0.75 + 0.1 * (e8 % 2)))
        else:
            for st, up, ln, semi in BASS_PAT:
                m = root + 12 * up + semi
                bass.add(T(bar) + st * R_STEP, r_bass_voice(mtof(m), ln * R_STEP, vj(0.9 if up else 1.0)))
        # ---------------- chord stabs / pad ----------------
        if sec in ("intro", "verse", "groove"):
            bright = 0.15 + 0.2 * bar if sec == "intro" else 0.85
            for st in (2, 6, 10, 14):
                stabs.add(T(bar) + st * R_STEP, stab_voice(freqs, 0.13, vj(0.9), bright))
        elif sec in ("chorus", "drop"):
            for st, d in ((0, 0.28), (3, 0.13), (6, 0.13), (10, 0.13), (13, 0.2)):
                stabs.add(T(bar) + st * R_STEP, stab_voice(freqs, d, vj(1.0), 1.0))
        elif sec == "build":
            last = 2 if bar == 23 else 4
            for e8 in range(last * 2):
                bright = 0.2 + 0.8 * ((bar - 20) * 8 + e8) / 30
                stabs.add(T(bar, e8 * 0.5 + 0.25), stab_voice(freqs, 0.1, 0.8, bright))
        if sec in ("break", "drop"):
            for m in voicing:
                pad.add(T(bar), r_pad_voice(mtof(m), R_BAR - 0.05, 0.9 if sec == "break" else 0.5))
        # ---------------- lead ----------------
        notes, bell = None, False
        if sec in ("chorus", "drop"):
            notes = HOOK[bar % 4]
        elif sec == "break":
            notes, bell = HOOK[bar % 4], True
        elif (sec == "verse" and bar >= 8) or sec == "groove":
            notes = MOTIF[bar % 4]
        if notes:
            for beat, m, d in notes:
                lead.add(T(bar, beat), lead_voice(mtof(m - (12 if bell else 0)), d * R_BEAT * 0.92, vj(0.9), bell))
                if sec == "drop":                                                  # the drop doubles the hook an octave down
                    lead.add(T(bar, beat), lead_voice(mtof(m - 12), d * R_BEAT * 0.92, vj(0.5)))
    fx.add(T(20), riser(3.5 * R_BAR), 1.0)                                         # the build riser, cut at the gap

    # --- buses ---
    duck = duck_env(n, kick_times, 1.0, 0.08, R_BEAT)
    pump = lambda depth: 1 - depth * (1 - duck)                                   # noqa: E731
    lead_b = lead.b
    echo = np.zeros(n)
    d = int(round(0.75 * R_BEAT * SR))                                            # dotted-8th delay
    for k in range(1, 5):
        echo += (0.38 ** k) * np.roll(lead_b, k * d)
    lead_b = lead_b + circ(lambda z: lp(z, 3500), echo)
    parts = {
        "kick": level(kick.b, -13.5),
        "clap": level(clap.b + 0.3 * creverb(clap.b, 1.2, 4500), -21),
        "hat_o": level(hats_o.b, -26),
        "hat_c": level(hats_c.b, -33),
        "snare": level(snare.b, -23),
        "crash": level(crash.b, -29),
        "bass": level(circ(lambda z: lp(z, 2500), bass.b) * pump(0.45), -16.5),
        "stabs": level(stabs.b * pump(0.55), -21),
        "lead": level(lead_b * pump(0.2), -20),
        "pad": level(pad.b * pump(0.6), -25),
        "fx": level(fx.b, -25),
    }
    wet = creverb(parts["stabs"] + parts["lead"] + 0.5 * parts["clap"], 1.6, 4000)
    mix = sum(parts.values()) + 0.16 * wet
    mix = circ(lambda z: hp(z, 28), mix)
    mix = np.tanh(1.25 * mix / np.max(np.abs(mix)))
    mix *= 10 ** (-3.3 / 20) / np.max(np.abs(mix))                              # peak −3 dBFS
    fi, fo = int(0.005 * SR), int(0.01 * SR)                                      # the game re-triggers it: no edge clicks
    mix[:fi] *= np.linspace(0, 1, fi)
    mix[-fo:] *= np.linspace(1, 0, fo)
    return mix


def render_pose():
    """camera flash (charge whine + pop), a burst of shutters, then a crowd 'wooo' + applause, 2.6 s"""
    n = int(2.6 * SR)
    y = np.zeros(n)
    t = np.arange(n) / SR

    def put(s_t, x, g=1.0):
        s = int(s_t * SR)
        e = min(n, s + len(x))
        y[s:e] += g * x[: e - s]

    # flash: a quick rising whine + a pop
    m = int(0.3 * SR)
    tt = np.arange(m) / SR
    whine = np.sin(TAU * np.cumsum(2500 + 5000 * tt / 0.3) / SR) * (tt / 0.3) * 0.12
    put(0.0, whine)
    pop = lp(rng.standard_normal(int(0.08 * SR)), 3500) * env_exp(int(0.08 * SR), 0.015)
    put(0.3, pop, 0.8)
    # shutters: mirror slap + curtain, several photographers
    for st, v in ((0.30, 1.0), (0.44, .7), (0.57, .8), (0.71, .55), (0.9, .65), (1.18, .45), (1.5, .35), (1.85, .25)):
        k = int(0.06 * SR)
        c1 = bp(rng.standard_normal(k), 1500, 7000) * env_exp(k, 0.003)
        c2 = bp(rng.standard_normal(k), 700, 4000) * env_exp(k, 0.006)
        thump = np.sin(TAU * 130 * np.arange(k) / SR) * env_exp(k, 0.012) * 0.4
        put(st, (c1 + thump) * v * 0.9)
        put(st + 0.045, c2 * v * 0.7)
    # crowd voices: buzzy sources through two vowel formants, gliding up ("wooo!")
    crowd = np.zeros(n)
    for _ in range(34):
        st = rng.uniform(0.35, 0.8)
        dur = rng.uniform(0.7, 1.7)
        k = int(dur * SR)
        tk = np.arange(k) / SR
        f0 = rng.uniform(170, 430)
        glide = 1 + 0.35 * np.clip(tk / 0.35, 0, 1) - 0.12 * np.clip((tk - 0.5) / dur, 0, 1)
        vib = 1 + 0.02 * np.sin(TAU * rng.uniform(4, 7) * tk)
        src = saw(1, np.cumsum(f0 * glide * vib) / SR)
        f1, f2 = rng.uniform(500, 800), rng.uniform(900, 1400)
        v = bp(src, f1 * 0.8, f1 * 1.2) + 0.6 * bp(src, f2 * 0.85, f2 * 1.15)
        env = gate(k, dur, rng.uniform(0.08, 0.2), min(0.5, dur * 0.4))
        s = int(st * SR)
        e = min(n, s + k)
        crowd[s:e] += (v * env)[: e - s] * rng.uniform(0.5, 1.0)
    y += 0.9 * crowd / (np.max(np.abs(crowd)) + 1e-9)
    # applause: dense random hand claps swelling and fading
    imp = np.zeros(n)
    rate = 90 * np.clip((t - 0.4) / 0.3, 0, 1) * np.exp(-np.clip(t - 1.2, 0, None) / 0.8)
    hits = rng.random(n) < rate / SR
    imp[hits] = rng.uniform(0.3, 1.0, hits.sum())
    kern = bp(rng.standard_normal(int(0.02 * SR)), 900, 4000) * env_exp(int(0.02 * SR), 0.004)
    claps = np.convolve(imp, kern)[:n]
    y += 0.8 * claps / (np.max(np.abs(claps)) + 1e-9)
    # one whistle from the crowd
    k = int(0.6 * SR)
    tk = np.arange(k) / SR
    wf = 1900 + 900 * np.clip(tk / 0.25, 0, 1) - 300 * np.clip((tk - 0.35) / 0.25, 0, 1)
    put(0.55, np.sin(TAU * np.cumsum(wf) / SR) * gate(k, 0.5, 0.03, 0.1) * 0.22)
    y = creverb(y, 0.9, 5000) * 0.25 + y
    y *= gate(n, 2.15, 0.001, 0.45)
    y = np.tanh(1.1 * y / np.max(np.abs(y)))
    y *= 10 ** (-3.3 / 20) / np.max(np.abs(y))
    return y


# ----------------------------------------------------------------------------------------------------------------
# pack, previews, checks
# ----------------------------------------------------------------------------------------------------------------
def waveform_png(entries):
    from PIL import Image, ImageDraw
    W, WH, SH, PAD = 1200, 70, 70, 22
    rowh = PAD + WH + SH + 10
    img = Image.new("RGB", (W, rowh * len(entries) + 8), (24, 18, 30))
    dr = ImageDraw.Draw(img)
    for r, (label, y) in enumerate(entries):
        y0 = r * rowh + 6
        dr.text((8, y0 + 4), f"{label}   {len(y) / SR:.2f} s   peak {20 * np.log10(np.max(np.abs(y)) + 1e-12):.1f} dBFS",
                fill=(255, 200, 230))
        top = y0 + PAD
        cols = np.array_split(y, W)
        mid = top + WH // 2
        for x, c in enumerate(cols):
            a, b = float(c.min()), float(c.max())
            dr.line([(x, mid - b * WH / 2), (x, mid - a * WH / 2)], fill=(255, 105, 180))
        # spectrogram 0–8 kHz, log magnitude
        win = 1024
        hann = np.hanning(win)
        centers = np.linspace(win // 2, len(y) - win // 2 - 1, W).astype(int)
        frames = np.stack([y[c - win // 2:c + win // 2] * hann for c in centers])
        mag = 20 * np.log10(np.abs(np.fft.rfft(frames, axis=1))[:, : int(8000 / (SR / win))] + 1e-6)
        mag = np.clip((mag - (mag.max() - 70)) / 70, 0, 1)
        rows = np.linspace(mag.shape[1] - 1, 0, SH).astype(int)
        v = mag[:, rows].T
        rgb = np.stack([255 * v, 90 * v ** 2 + 20 * v, 150 * v + 60 * v ** 3], axis=-1).clip(0, 255).astype(np.uint8)
        img.paste(Image.fromarray(rgb), (0, top + WH + 4))
    os.makedirs(os.path.dirname(PNG), exist_ok=True)
    img.save(PNG)


def main():
    lofi = render_lofi()
    segs = slice_lofi(lofi)
    show = render_runway()
    pose = render_pose()

    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    sd = os.path.join(OUT, "assets", NS, "sounds")
    files, events = {}, {}
    for i, s in enumerate(segs):
        rel = f"lift/lofi_{i}"
        write_ogg(os.path.join(sd, rel + ".ogg"), s)
        files[rel] = s
        events[f"lift.lofi_{i}"] = {"category": "record", "sounds": [{"name": f"{NS}:{rel}", "stream": True}]}
    write_ogg(os.path.join(sd, "runway/show.ogg"), show)
    files["runway/show"] = show
    events["runway.show"] = {"category": "record", "sounds": [{"name": f"{NS}:runway/show", "stream": True}]}
    write_ogg(os.path.join(sd, "runway/pose.ogg"), pose)
    files["runway/pose"] = pose
    events["runway.pose"] = {"category": "record", "sounds": [{"name": f"{NS}:runway/pose"}]}
    json.dump(events, open(os.path.join(OUT, "assets", NS, "sounds.json"), "w"), indent=1)
    json.dump({"pack": {"description": "Pink Golem studio music (lift lofi + runway show)", "min_format": 88, "max_format": 88}},
              open(os.path.join(OUT, "pack.mcmeta"), "w"))
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, fs in os.walk(OUT):
            for f in sorted(fs):
                p = os.path.join(root, f)
                zf.write(p, os.path.relpath(p, OUT))
    os.makedirs(PREVIEW_DIR, exist_ok=True)
    write_ogg(os.path.join(PREVIEW_DIR, "lofi_full_preview.ogg"), np.concatenate(segs))

    # ---- check: decode everything back ----
    expect = {**{f"lift/lofi_{i}": SEG_S for i in range(NSEG)}, "runway/show": 64.0, "runway/pose": None}
    summary = {"files": {}, "events": [f"{NS}:{e}" for e in events]}
    decoded = []
    for rel, want in expect.items():
        p = os.path.join(sd, rel + ".ogg")
        y, sr = sf.read(p, always_2d=True)
        assert y.shape[1] == 1, f"{rel}: not mono"
        assert sr == SR, f"{rel}: sample rate {sr}"
        dur = y.shape[0] / sr
        if want is not None:
            assert abs(dur - want) <= 0.05, f"{rel}: {dur:.3f} s, want {want}"
        peak = float(20 * np.log10(np.max(np.abs(y)) + 1e-12))
        summary["files"][f"sounds/{rel}.ogg"] = {"seconds": round(dur, 3), "kb": round(os.path.getsize(p) / 1024, 1),
                                                 "peak_dbfs": round(peak, 1), "sr": sr, "channels": y.shape[1]}
        decoded.append((f"{NS}:{rel.replace('/', '.')}", y[:, 0]))
    ev = json.load(open(os.path.join(OUT, "assets", NS, "sounds.json")))
    for e in ev.values():
        for s in e["sounds"]:
            assert os.path.exists(os.path.join(sd, s["name"].split(":", 1)[1] + ".ogg")), s["name"]
    # continuity: every lofi slice boundary (incl. 5 → 0) lines up with the unsliced render
    seg_n = int(round(SEG_S * SR))
    for i in range(NSEG):
        a, b = lofi[(i + 1) * seg_n - 1], lofi[((i + 1) % NSEG) * seg_n]
        assert abs(a - b) < 0.05, f"lofi boundary {i}: jump {a - b:.3f}"
    try:
        waveform_png(decoded)
        summary["png"] = PNG
    except Exception as ex:                                  # the preview is optional
        summary["png_error"] = repr(ex)
    summary["zip"] = ZIP
    summary["zip_kb"] = round(os.path.getsize(ZIP) / 1024, 1)
    summary["loop_ticks"] = {"lift.lofi_N": int(SEG_S * 20), "runway.show": 64 * 20}
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
