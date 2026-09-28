# Studio music — a lift lofi and a runway track, synthesised from scratch

Two original pieces for the character studio, written in Python (numpy + scipy, Vorbis through `soundfile`; no
samples, no ffmpeg, no copied melodies). One command builds the pack part:

```
python3 resourcepacks/studio_music/gen_studio_music.py   # → studio_music.zip (~1.1 MB) + previews/
```

| Sound event | Length | What it is |
|---|---|---|
| `lounge:lift.lofi_0` … `lift.lofi_5` | 6 × 12.0 s (240 ticks each) | an 80 BPM lofi in F major (Rhodes-like electric piano, a breathy flute, round bass, swung brushed drums, vinyl crackle, tape wow), rendered once as 24 bars and sliced into six 4-bar segments that follow on from each other; segment 5 leads back into 0 |
| `lounge:runway.show` | 64.0 s (1280 ticks), loopable | a 120 BPM nu-disco / disco-house in D major (four-on-the-floor, claps, offbeat hats, octave bass, plucky stabs, a hook, a build and a drop) |
| `lounge:runway.pose` | 2.6 s | a camera flash, shutter clicks and a small crowd cheer |

All files are **mono** (a stereo sound is not positional and ignores distance) and the long ones are `"stream": true`.
The script decodes every Ogg back and checks mono, the sample rate and the exact durations.

## Music in a lift: segments + `minVolume`

A lift ride is 2-17 s and the listener travels up to ~150 blocks during it. Two tricks make it feel like one calm,
continuous track that only the riders hear:

- **Segments, played in turn per player.** Each ride plays the rider's *next* 12 s segment and schedules the one after
  it 240 ticks later while they are still riding; arriving stops it. The next ride carries on from there, so over a
  few rides you hear the whole piece.
- **`minVolume`.** A played sound stays where it started. With
  `execute as <rider> at @s run playsound lounge:lift.lofi_<n> record @s ~ ~ ~ 0.55 1 0.55` a rider who has moved
  out of the sound's range keeps hearing it at 0.55 instead of it fading away. `@s` = nobody else hears it.

The runway track is re-triggered every 1280 ticks for each player on the studio floor while a show runs
(`scarpet-apps/runway.sc`), and stopped for them when it ends.
