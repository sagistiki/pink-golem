# Cinema films (resource pack for `scarpet-apps/cinema.sc`)

A silent-film screening room with no client mods: the "screen" is one big `item_display` quad whose item model is
swapped every frame (a small PNG pre-rendered into the pack), timed by the wall clock so lag never desyncs the
picture from the music. The technique, the numbers behind it, and a full step-by-step guide are in
[`skill/pinkgolem/reference/cinema-and-gallery.md`](../../skill/pinkgolem/reference/cinema-and-gallery.md).

| File | What |
|---|---|
| `cinemalib.py` | the generic toolkit: `Scene` (a supersampled grayscale drawing surface + silhouette puppets), `finish()` (silent-film post-fx + palette quantise), RTL-safe text and intertitle `card()`s, `FrameStore` (content-hash dedupe), `Pack` (resource-pack writer), a small additive synth (`piano`/`pad`/`pedal`/`tremolo`/`boom`/`reverb`/`Mixer`), a contact-sheet helper |
| `film_demo.py` + `music_demo.py` | "The Lighthouse": a complete, working 14 s example film — copy these two files as the template for your own |
| `gen_cinema_pack.py` | the driver: renders every film in `FILMS`, dedupes frames, renders the score, writes `build/` + `cinema.zip` + `films.json` + review PNGs |
| `cinema.zip` | the ready pack (namespace `cinema`) — the demo film only |

## Run it

```bash
pip install numpy scipy pillow soundfile
python3 resourcepacks/cinema/gen_cinema_pack.py
```

This writes `resourcepacks/cinema/cinema.zip`, `scarpet-apps/cinema.data.example/films.json` (the demo film's real
entry — regenerated every run), and three review images next to this file: `preview_demo_sheet.png` (a contact
sheet of every 4th frame + every card), `preview_poster.png`, `preview_model.png` (the screen quad rendered with
[`resourcepacks/tools/model_preview.py`](../tools/model_preview.py), no game client needed). **Look at the review
images before shipping the pack** — they are the only check that catches a wrong yaw, a clipped card or a blank
frame ahead of a live deploy.

## Use it

1. Add `cinema.zip` to your server resource-pack build (`minecraft_pack build`, or your own merge step — vanilla
   sends only one pack per player).
2. Copy the whole [`scarpet-apps/cinema.data.example/`](../../scarpet-apps/cinema.data.example) folder to your
   world's `scripts/cinema.data/`, and `scarpet-apps/cinema.sc` to `scripts/`. `script load cinema`.
3. Edit `cinema.data/rooms.json` for your own room (position, seats, button, screen size) — the full walkthrough,
   including how to verify each position live before trusting it, is
   [`cinema-and-gallery.md`](../../skill/pinkgolem/reference/cinema-and-gallery.md).
4. `/cinema menu` (or press the room's button) opens the programme dialog; `/cinema list` lists what's loaded.

## Add a film

1. Copy `film_demo.py` → `film_<id>.py` and `music_demo.py` → `music_<id>.py`.
2. Write your scene(s) with `cinemalib.Scene` (silhouette puppets, gradients, simple shapes — see `film_demo.py`'s
   `scene()`), your intertitle `CARDS` (short phrases, logical order, no internal periods/commas within one card —
   see "Common mistakes" in the reference page for why), and an ORIGINAL melody in `music_<id>.py` with the synth
   toolkit (never a real recorded song — resource-pack Ogg files reach every player).
3. Add `"film_<id>"` to `FILMS` in `gen_cinema_pack.py` and rerun it.
4. Look at the new `preview_<id>_sheet.png` and `preview_poster.png` before shipping.
