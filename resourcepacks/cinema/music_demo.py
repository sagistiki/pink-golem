"""music_demo.py — a short (~14.3 s) original score for film_demo.py, rendered entirely with cinemalib's synth
toolkit (numpy additive synthesis, no samples, no external audio). A gentle pad progression under a simple piano
melody, a soft low pedal at the very end. Mixer.buf is always mono, which is what a positional 'record'-category
sound in Minecraft needs (stereo Ogg files are not positional — see cinema-and-gallery.md).

Copy this file as the template for your own score: change the chord progression and the melody, keep the mix /
reverb / fade / normalize / write_ogg pipeline. `render(path)` is the only thing gen_cinema_pack.py calls.
"""
import cinemalib as cl

DUR = 14.3  # a little longer than the film (14.0 s) so the last note isn't cut off; the app stops it at frame end

# four bars of a simple pad progression (root, third, fifth), 3.5 s each
CHORDS = [("C4", "E4", "G4"), ("A3", "C4", "E4"), ("F3", "A3", "C4"), ("G3", "B3", "D4")]

# melody: (start time, note) — a simple rising-and-falling pentatonic-ish line over the first two chords
MELODY = [
    (0.2, "C5"), (0.8, "E5"), (1.4, "G5"), (2.0, "E5"), (2.6, "C5"),
    (3.7, "A4"), (4.3, "C5"), (4.9, "E5"), (5.5, "D5"), (6.1, "C5"),
    (7.4, "F4"), (8.0, "A4"), (8.6, "C5"), (9.2, "A4"),
    (10.7, "G4"), (11.3, "B4"), (11.9, "D5"),
]


def render(path):
    mixer = cl.Mixer(DUR)
    for i, chord in enumerate(CHORDS):
        t0 = i * 3.5
        for n in chord:
            mixer.add(t0, cl.pad(cl.note(n), 3.6, vel=0.75))
    for t0, n in MELODY:
        mixer.add(t0, cl.piano(cl.note(n), 1.1, vel=0.85))
    mixer.add(DUR - 3.2, cl.pedal(cl.note("C3"), 3.2, vel=0.6))          # a soft low note under the closing card
    mixer.buf = cl.reverb(mixer.buf, decay=0.4, mix=0.18)
    mixer.fade(fade_in=0.05, fade_out=1.3).normalize(-2.0)
    return mixer.write_ogg(path)
