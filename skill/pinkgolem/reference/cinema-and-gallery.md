# Cinema and gallery — a screen with no client mods, and a data-driven picture gallery

Read this before building anything that shows a *picture* to players without a client mod: a cinema screen, a
looping trailer, an art gallery, a picture-frame slideshow, a scoreboard with a logo. Both `scarpet-apps/cinema.sc`
and `scarpet-apps/gallery.sc` draw pictures the same way — an `item_display` **quad** (a flat, one-element item
model) showing a small PNG baked into the resource pack — and share one yaw convention for "which way is this wall
facing". This page is written so a small/local model can follow it literally: exact file names, copy-pasteable
JSON, and a numbered build order. The working example is
[`resourcepacks/cinema/`](../../resourcepacks/cinema) (a complete 14 s demo film you can generate and play right
now) and [`resourcepacks/gallery/`](../../resourcepacks/gallery) (four demo paintings + a spinning exhibit).

## Why a quad of item-model frames (not a map, not text, not blocks)

| Method | Cost per frame | Resolution | Frame rate | Verdict |
|---|---|---|---|---|
| **Item-model frames** (this page) | ~100 bytes: one item-metadata packet per viewer, swapping which pre-rendered model shows | any — texture-limited (256x144 reads well) | any; wall-clock driven, 4 fps looks like an old film | **wins.** The PNGs are baked once at build time; playing a frame is just telling the client "show model N" |
| Map art (`item_frame` + `filled_map`) | ~16 KB **per map per client per frame** — the whole map image is resent | 128x128 per map | limited by bandwidth, not the game | a single 75 s film at 4 fps would resend multiple megabytes per second per viewer — a non-starter |
| `text_display` "pixel art" (space-sized glyphs) | cheap, but coarse | a practical ceiling around 64x36 "pixels" | fine for bars/text, not a picture | too coarse to read as an image |
| A wall you build/destroy every frame | one block update per changed block, but re-meshes the whole chunk section each time | 1 pixel = 1 block (room-sized "pixels" only) | chokes above ~2 fps | a visible client hitch on every frame, and each frame is a different build, not a texture swap |

Numbers from a real 75 s / 4 fps / 300-frame film: **256x144** frames land around **6 KB** each; after content-hash
dedupe (title cards, held frames, a still background) a 300-frame film needed only **~200 unique models ≈ 1.7 MB**
in the pack. The 14 s demo film shipped with this page: 56 frames → 46 unique models, 0.35 MB total.

## The one yaw convention (verify it once, reuse everywhere)

Both apps take `yaw` / `face` to mean: **the direction the VIEWERS stand in**, as a Minecraft yaw.

| Viewers stand... | yaw / face |
|---|---|
| south (+z) | `0` / `"south"` |
| east (+x) | `-90` / `"east"` |
| west (-x) | `90` / `"west"` |
| north (-z) | `180` / `"north"` |

The same value works for an `item_display` quad, a `text_display` plaque (`billboard:"fixed"`), and a mannequin's
`Rotation` yaw (the way it looks). **Verify it once, live, on a throwaway quad** before trusting it for a whole
room: place one quad with a texture that has an obvious "up" and "this side" (even a plain letter works), stand on
the side you expect to be the viewer side, and confirm it isn't mirrored or upside down. Every other position in
this page is derived from that one confirmed convention — don't re-derive it per wall.

A wall **block** at integer coordinate `Z` spans `Z..Z+1`. The quad's entity position is the centre of the picture,
**on the face the room's interior sees, offset ~0.05 blocks further into the room** — never at the block's
integer coordinate, which is *inside* the wall and renders nothing (see `displays.md`'s "Common mistakes" — the
same trap as a plaque centred in its block).

## Step by step: build the cinema demo and play it

1. **Generate the pack.**
   ```bash
   pip install numpy scipy pillow soundfile
   python3 resourcepacks/cinema/gen_cinema_pack.py
   ```
   This writes `resourcepacks/cinema/cinema.zip`, refreshes
   `scarpet-apps/cinema.data.example/films.json`, and three review images next to the script:
   `preview_demo_sheet.png` (every 4th frame + every card — **look at this before anything else**),
   `preview_poster.png`, `preview_model.png`. A film that looks wrong in the contact sheet will look exactly as
   wrong in the game — check it here, where one command redraws it, not after a live deploy.

2. **Look at what a screen quad model actually is** (this is what `gen_cinema_pack.py` writes per frame — you
   rarely hand-write it, but you must recognise it when a preview looks wrong). A 16-wide x 9-tall quad, vertically
   centred in the 16-unit item-model space, one texture on both faces (so it reads correctly from slightly off to
   either side):
   ```json
   {
     "textures": {"0": "cinema:item/demo_f0001", "particle": "cinema:item/demo_f0001"},
     "elements": [{
       "from": [0, 3.5, 7.9], "to": [16, 12.5, 8.1],
       "faces": {
         "north": {"uv": [0, 0, 16, 16], "texture": "#0"},
         "south": {"uv": [0, 0, 16, 16], "texture": "#0"}
       }
     }]
   }
   ```
   and the item definition that points a plain `paper` item at it (`assets/cinema/items/demo_f0001.json`):
   ```json
   {"model": {"type": "minecraft:model", "model": "cinema:item/demo_f0001"}}
   ```
   **Texture size must be a multiple of 16** (256x144 is 16x9 sixteens) — a texture that isn't costs the WHOLE
   atlas its mipmap levels, not just that one texture (`textures.md`). The screen's real on-wall size is this
   quad's shape (9/16 of a block tall at scale 1) times `screen.scale` in `rooms.json` — scale 7 gave a
   readable ~4-block screen in the demo room; a bigger room wants a bigger scale.

3. **Recognise the sound registration** (`assets/cinema/sounds.json`, written by `Pack.sound()`):
   ```json
   {"demo_theme": {"category": "record", "sounds": [{"name": "cinema:demo_theme", "stream": true}]}}
   ```
   Three rules that matter more than anything else about the audio, each one a real, silent failure if skipped:
   - **Mono, not stereo.** A 'record'-category sound is positional (it fades with distance and pans with the
     listener's position) only in mono — a stereo Ogg plays flat, centred, the same everywhere. `soundfile`
     writes mono Vorbis with zero extra setup (`sf.write(path, mono_array, sr, format="OGG", subtype="VORBIS")` —
     see `Mixer.write_ogg` in `cinemalib.py`); no ffmpeg needed.
   - **`"stream": true`** for anything longer than a couple of seconds, or the client tries to load the whole
     decoded file into memory up front.
   - **`category: "record"`**, and in the `sound()` call itself, **volume > 1 only extends the audible range** —
     it does not make it louder where you already are. Use `sound(id, pos, volume, pitch, 'record')` in scarpet.
   - Compose an **original** melody (`music_demo.py` is a full worked example with the synth toolkit) — a
     resource-pack Ogg reaches every player who joins, so a recorded real song is a licensing problem waiting to
     happen; procedural synthesis has none.

4. **Copy the example data and the app.**
   ```bash
   cp -r scarpet-apps/cinema.data.example server/world/scripts/cinema.data
   cp scarpet-apps/cinema.sc server/world/scripts/
   ```
   Add `cinema.zip` to your resource-pack build (`minecraft_pack build`), then `script load cinema`.

5. **Edit `cinema.data/rooms.json` for your own room.** Reread the `_doc` block at its top — it repeats the yaw
   convention, the seat/light/button/sound formats, and is deleted from `global_rooms` at load time (never treated
   as a room). Key fields, with the reasons behind their numbers:

   | Field | What | The number behind it |
   |---|---|---|
   | `screen.pos` / `.yaw` / `.scale` | quad centre, viewer-side yaw, size multiplier | pos is the wall face + 0.05, never the block's own coordinate |
   | `subtitle.pos` / `.yaw` | a `text_display` strip under the screen | shows each film's `cards[].text` while it plays |
   | `seats` | list of `[x, y_seat, z]` | `y_seat` = the seat **block**'s y (e.g. a stair) |
   | `seat_dy` | armor-stand spawn offset above `y_seat` | an invisible **Marker** `armor_stand`'s rider sits with their feet **~0.6 below the stand's own y** — so `stand_y = seat_block_y + 0.5` puts the feet about `seat_block_y - 0.1`, i.e. resting on the seat block. Measured live once, reused everywhere: `seat_dy: 0.5` |
   | `seat_yaw` | which way seated players face | if the seat is a **stair block used as a backrest**, its `facing` state is the side the BACK faces — a seat that looks north needs `facing=south` (the stair's riser is behind the sitter) |
   | `button.block` / `.state` | a plain vanilla button, placed if the cell is empty | polled for its `powered` rising edge every 2 ticks — no resource-pack item, no interaction entity, so it costs nothing to add another one. Reserve a **custom item-model button** for one signature feature (a lift call button, say); reusing one custom model for every button in the world makes every button look and behave the same and stops reading as special |
   | `lights` | a box of `light` blocks | set to `dim` while a film plays, `on` after — the simplest "house lights" there is |
   | `sound.pos` / `.volume` | feeds `sound(music, pos, volume, 1, 'record')` | see step 3 |

6. **Play it.** `/cinema menu` (or press the room's button) opens the programme dialog; `/cinema play demo`;
   `/cinema list`; admin `/cinema stop` / `/cinema reset`. `/script in cinema run status()` reports the running
   frame, how many seconds are left, and how many of the room's entities actually exist (a number lower than
   expected means the chunk wasn't loaded when `_ensure()` last ran — walk closer and wait for the next sweep).

## The frame-swap itself (the one line that plays a film)

The screen is **one** `item_display` entity per room, kept forever (tag `cinema_e_screen_<room>`). Playing a frame
never respawns anything — it merges a new `item` component onto the same entity:

```
modify(e, 'nbt_merge', '{item:{id:"minecraft:paper",count:1,components:{"minecraft:item_model":"cinema:demo_f0007"}}}')
```

**Item swaps on a display entity are instant — there is no interpolation for `item`.** (`transformation` changes
*do* interpolate, over `interpolation_duration` ticks, if you're also animating position/scale — a spinning
showpiece uses that; a frame swap does not need to.) So a new item shows the instant the packet arrives, which is
exactly what you want for 4 fps stop-motion.

**Schedule frames by the wall clock, never by a tick counter.** A tick counter drifts the moment the server lags
even slightly (a GC pause, a heavy chunk), and picture and music fall out of sync forever, because the *music* is
also running on wall-clock time (real playback) while a tick counter is server-time. The fix, from `cinema.sc`:

```
idx = floor((unix_time() - t0) * fps / 1000);      // t0 = unix_time() taken when playback started
if (idx != R:'idx', ( R:'idx' = idx; modify(screen_entity, 'nbt_merge', '{' + item_for(frames:idx) + '}') ));
```

`unix_time()` is milliseconds since epoch; comparing `idx` to the last shown index means a frame that never
changes (a held title card) triggers **zero** extra packets — you only pay for the frames that actually differ,
whatever the server's tick rate does in the meantime.

## Data-driven rooms/films, and why every entity is guarded

Nothing about a room or a film lives in the `.sc` file — `cinema.sc` only knows how to *read* `rooms.json` and
`films.json`. Adding a film is one Python module + one `FILMS` entry (no scarpet edit); adding a room is one JSON
object (no scarpet edit). This is what makes the app itself generic and reusable across any server.

**Every entity the app owns is spawned through a "one entity per tag" guard** (`_one()` in both apps): look up the
tag first (by a remembered UUID, then by a fresh selector), and only spawn if truly missing. Two things fall out of
that one guard:

- **A reload or a server restart never doubles anything.** Re-running `_ensure()` after `/reload` or a crash finds
  the existing screen/seats/button-label already there and touches nothing.
- **An entity can only be summoned in a loaded chunk.** `_ensure()` is called only when a real player is within
  range (`_near()`/`_someone_near()`), on a periodic sweep — never blindly at server start, when nobody may be
  anywhere near the room. A room whose entity count (`status()`'s `ents`) is lower than expected simply hasn't had
  anyone walk close enough yet; it completes on the next sweep once someone does.

## The gallery: the same techniques, one room of art

`gallery.sc` reuses the exact same quad/yaw scheme for paintings, adds spinning `item_display` **exhibits** on
plinths (any 3D item model, not just a flat quad — see `trophy_model()` in `gen_gallery_pack.py` for the smallest
possible 3D model: two boxes), block-built **sculptures** that just need a plaque, and **quiet zones** (a box that
whispers an action-bar message once per player per visit).

```bash
pip install numpy pillow
python3 resourcepacks/gallery/gen_gallery_pack.py
cp -r scarpet-apps/gallery.data.example server/world/scripts/gallery.data
cp scarpet-apps/gallery.sc server/world/scripts/
# add gallery.zip to your pack build, then: script load gallery
```

`art.json`'s schema (written by the generator, editable by hand for a one-off change):

```json
{
  "paintings": [{"id": "p01", "model": "gallery:p01", "title": "Harbour at Dawn", "artist": "Studio collection",
                 "year": "2026", "pos": [10.0, -58.5, 20.05], "face": "south", "w": 4, "h": 3}],
  "exhibits":  [{"id": "trophy", "model": "gallery:trophy", "pos": [12.0, -59.5, 22.0], "scale": 0.6, "spin": 3,
                 "title": "Founders' Cup", "sub": "Awarded every season"}],
  "sculptures":[{"id": "wave", "title": "Tidal Form", "plaque": [13.5, -58.4, 25.9], "face": "south"}],
  "quiet_zones":[{"name": "Reading corner", "min": [9, -60, 19], "max": [17, -54, 27],
                  "msg": "Quiet corner — please keep your voice down"}]
}
```

`pos` for a painting is the quad's centre: the wall face coordinate **plus** a small offset toward the viewers
(`OFF` in `gen_gallery_pack.py`: `+0.05` on the axis the viewers approach from). `w`/`h` are in **blocks**, not
pixels — a 256x192 PNG (4:3) reads as a `w:4, h:3` painting on the wall.

## Text in a baked frame vs. text in the game

Two different things are both called "text" here, and mixing them up is the single most common mistake:

- **A card baked into a PNG frame** (`cinemalib.card()`) — an intertitle with an ornamental frame, part of the
  picture itself, subject to the sepia/grain/vignette look. Written with **PIL**, which does not reorder
  right-to-left scripts on its own (no `raqm`).
- **The subtitle strip** (`films.json`'s `cards[].text`, shown via a `text_display`) — a live Minecraft text
  component, sent as JSON, refreshed every time the shown card changes.

For a PIL-baked card in a right-to-left script (Hebrew, Arabic, ...): write the **logical** string, then call
`cinemalib.visual()` before drawing — it reverses the line's character order (the standard trick for faking RTL
in a renderer with no bidi engine) and un-reverses any embedded Latin/digit run so e.g. "Studio 1926" still reads
left-to-right inside the RTL line. **For the Minecraft text component (the subtitle strip, any `tellraw`, any
sign), write the LOGICAL order and do NOT call `visual()`** — the client does its own bidi reordering; running
RTL-reversal on text the game will reorder itself un-reverses it right back to wrong.

**`visual()` only reverses a line that actually contains an RTL character.** A pure-Latin line is returned
unchanged. This matters even in an all-English film: the reversal algorithm's job is "flip a Hebrew/Arabic line,
but keep a short embedded Latin phrase forward" — fed a whole ENGLISH sentence with punctuation (`"One keeper.
One lamp."`), the same fix-up instead **reorders whole clauses**, because a period immediately followed by a
space produces two connector characters in a row once reversed, which the fix-up's one-connector-per-gap pattern
doesn't expect. This is a real bug the demo film in this repo hit and fixed — if you ever hand-roll your own
RTL-safe text helper instead of using `cinemalib.visual()`, test it on a 100%-Latin string, not only on a mixed
RTL+Latin one.

## Building this like a real project (what actually worked)

1. **Survey the real space before writing a single coordinate.** Stand where the wall will be; the far side of it
   might be sky, not terrain — `minecraft_survey` / a bot walk-through beats guessing from an old build's numbers.
2. **Write one SPEC with exact coordinates before building anything**, and treat it as the contract every piece
   reads from: the room box, the screen wall, every seat, the button cell, the light box. Changing a number means
   editing the SPEC and regenerating, never patching a build in place.
3. **Split ownership when more than one agent/session works on it**: one on the room's blocks, one on the scarpet
   app, one on the film, one on the art — each one only touches its own files, and each one reads the SPEC, not
   each other's in-progress work.
4. **Playtest with a fake player before calling it done.** `minecraft_playtest` can walk a fake player to the
   button, assert the programme dialog opened, assert a film is running, sit it in a seat, assert it's mounted —
   end to end, in one call, cleaned up automatically (`testing-apps.md`).
5. **Review the contact sheet and the poster before deploying — every time.** A contact sheet catches a clipped
   card, a wrong palette, a frame that's accidentally identical to the previous one, in one glance. It once caught
   a completely blank frame (a texture path typo) that would otherwise have shipped as one dead second in the
   middle of a film. **Never ship a resource-pack part you haven't visually checked.**
6. **Deploy the resource pack as one push.** Merge every part into one zip, build once, deploy once
   (`minecraft_pack build` → `deploy`, `testing-apps.md`) — never overwrite a live URL players already cached; a
   client mid-download when you replace it gets a broken pack.

## Checklist

- [ ] Every generated texture's width and height are multiples of 16.
- [ ] The sound is mono (check `channels == 1` after reading it back — `gen_cinema_pack.py` asserts this), `stream:
      true`, category `record`.
- [ ] The melody is your own (procedural synthesis, or something you have the rights to) — never a recorded real
      song.
- [ ] The yaw convention was verified once, live, on a throwaway quad, before every room's numbers were written.
- [ ] Every quad's `pos` is on the wall's FACE + a small offset toward the viewers, never the block's own
      coordinate.
- [ ] Seats: `seat_dy` accounts for the ~0.6-below-stand rider offset; a stair-backrest seat's `facing` is the
      *back* side, not the *looking* side.
- [ ] A plain vanilla button is used unless the trigger is meant to be a signature, one-off feature.
- [ ] The contact sheet / poster / model preview were opened and actually looked at before deploying.
- [ ] A fake-player playtest exercised the button → dialog → play/sit path at least once.
- [ ] The pack was added to the merged build and deployed as one push, not left as a separate loose zip.

## Common mistakes

| Mistake | What happens | Fix |
|---|---|---|
| A quad's `pos` at the wall block's own integer coordinate | invisible — the display is inside the solid block | position on the FACE, offset ~0.05 toward the room |
| A texture whose width or height isn't a multiple of 16 | the WHOLE atlas silently loses mipmap levels, not just this texture | pad/crop to a multiple of 16 (`textures.md`) |
| A stereo Ogg for the film's score | plays flat and centred everywhere — not positional | render mono (`soundfile`, `Mixer.buf` is already 1-D) |
| A tick-counter frame index | drifts out of sync with the (wall-clock) music under any lag | `floor((unix_time()-t0)*fps/1000)` |
| RTL-reversing a 100%-Latin card string | scrambles multi-clause English into the wrong word order | `cinemalib.visual()` passes pure-LTR lines through unchanged — don't hand-roll a reversal without the same check |
| Re-spawning a room's entities every tick, or on every reload | duplicate screens/seats pile up | the one-entity-per-tag guard (`_one()`); reload only re-checks, never force-respawns |
| Summoning at server start with nobody near | silently does nothing (unloaded chunk) | `_ensure()` only runs when a real player is within range, on a periodic sweep |
| A custom item-model button reused for every trigger in the world | every button looks and behaves the same, and none of them feel special | plain vanilla button (polled `powered` edge) for ordinary triggers; save a custom model for one signature feature |
| A seat's stair `facing` set to the direction it looks | the backrest ends up in front of the sitter | `facing` = the side the BACK faces (a seat looking north: `facing=south`) |
| Shipping a resource-pack part nobody looked at | a blank map, a missing texture, a clipped card reach live players first | contact sheet + poster + model preview, every time, before deploy |

## See also

[`resourcepacks/cinema/README.md`](../../resourcepacks/cinema/README.md) ·
[`resourcepacks/gallery/README.md`](../../resourcepacks/gallery/README.md) ·
[`docs/case-study-cinema.md`](../../docs/case-study-cinema.md) · `displays.md` (the shared display-entity rules) ·
`textures.md` (mipmaps, palettes, shipping a pack) · `testing-apps.md` (playtests, `minecraft_pack`, deploying
live) · `lessons.md` (stairs facing, plaques inside the wall, preview-before-ship)
