# Gallery art (resource pack for `scarpet-apps/gallery.sc`)

A small art gallery with no client mods: paintings are `item_display` quads (a flat 16x16 model scaled to the
painting's size, drawn with PIL, one per wall), an exhibit spins on a plinth, a sculpture gets a plaque, and a
quiet zone whispers once to whoever walks in. The technique — the `face`/yaw convention shared with
`scarpet-apps/cinema.sc`, why a quad beats an item frame or a painting entity — is in
[`skill/pinkgolem/reference/cinema-and-gallery.md`](../../skill/pinkgolem/reference/cinema-and-gallery.md).

| File | What |
|---|---|
| `gen_gallery_pack.py` | four demo paintings + one spinning exhibit, drawn and packed; writes `build/` + `gallery.zip` + `art.json` |
| `gallery.zip` | the ready pack (namespace `gallery`) |

## Run it

```bash
pip install numpy pillow
python3 resourcepacks/gallery/gen_gallery_pack.py
```

Writes `gallery.zip`, `scarpet-apps/gallery.data.example/art.json` (regenerated every run), `preview_sheet.png`
(every painting at 1:1 pixels — the only way to actually read a 128x128 PNG), and `preview_model.png` (rendered
with [`resourcepacks/tools/model_preview.py`](../tools/model_preview.py), no game client needed). Look at both
before shipping the pack.

## Use it

1. Add `gallery.zip` to your server resource-pack build.
2. Copy [`scarpet-apps/gallery.data.example/`](../../scarpet-apps/gallery.data.example) to your world's
   `scripts/gallery.data/`, and `scarpet-apps/gallery.sc` to `scripts/`. `script load gallery`.
3. Edit `gallery.data/art.json` for your own walls (the numbers in `WALLS` at the top of `gen_gallery_pack.py` are
   for the small demo room the reference guide walks through).
4. `/gallery list` lists what's loaded; admin `/gallery reset` respawns every entity.

## Add a painting

Write a function `pNN(w, h) -> PIL Image` (see `p01`..`p04` — gradients, `overlay_alpha` for translucency, `paper`
for grain), add it to `PAINTINGS` and `DRAW`, give it a wall entry in `WALLS` (position + `face` = the side the
viewers stand on + wall size), and rerun. Keep every texture's final `w`/`h` a multiple of 16, or the pack loses
mipmap levels ([`skill/pinkgolem/reference/textures.md`](../../skill/pinkgolem/reference/textures.md)).
