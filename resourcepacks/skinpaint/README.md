# Skin easel (resource pack + data for `scarpet-apps/skinpaint.sc`)

Players paint a real 64x64 Minecraft skin on a wall, pixel by pixel, then press **Save and wear**: a moment later
they are wearing it and everyone sees it. Saved skins go to a **creators' gallery** of mannequins that others can
click to wear (if the creator allowed it). No client mods: the canvas is `text_display`s drawn with a pixel font from
this pack. The technique and the numbers behind it are in
[`skill/pinkgolem/reference/skin-easel.md`](../../skill/pinkgolem/reference/skin-easel.md).

| File | What |
|---|---|
| `gen_skinpaint.py` | the generator. **Its `CONFIG` block at the top is the only thing you edit**: `ORIGIN` + offsets for the wall, canvas, colour strip, toolbar, stage, gallery and studio area. Writes everything below |
| `skinpaint.zip` | the pack part (namespace `skinpaint`): the pixel font `skinpaint:canvas`, the brush item, 15 toolbar icon quads `skinpaint:tb_*` |
| `../../scarpet-apps/skinpaint.data.example/` | `layout.json` (the five views, cell → texel map, derive pairs, strip + toolbar geometry), `templates.json` (blank, basic + the studio skins), `config.json` (the places), an empty `gallery.json` |
| `jobs/skinpaint-1-walls.json`, `jobs/skinpaint-2-stage.json` | the build (blocks only — the app spawns every entity): the easel wall, toolbar panel, gallery wall with three plinths and page buttons; the painting stage, stairs and rail |
| `previews/` | `skinpaint_views.png` (each template drawn through the five views = the texel mapping check), `skinpaint_toolbar_icons.png` |

## Run it

```bash
pip install pillow
python3 resourcepacks/studio/gen_studio_pack.py      # optional: the 7 studio skins become starting templates
python3 resourcepacks/skinpaint/gen_skinpaint.py
```

The example numbers are a tested room: the easel wall is the block column `x = -79`, **facing east** (the painter
stands east of it and looks west). The app supports only that orientation. To use your own east-facing wall, change
`ORIGIN` and rerun; the room needs about 13 x 11 x 22 empty blocks (see the comment above `ORIGIN`). Look at
`previews/skinpaint_views.png` before shipping: every row must show a sensible right side / front / left side / back /
head top.

## Use it

1. **Resource packs:** `skinpaint.zip` **and** `resourcepacks/wardrobe/wardrobe.zip` (the mannequins' fallback skin
   `wardrobe:entity/dummy` comes from the wardrobe pack). `minecraft_pack build` picks up every
   `resourcepacks/<name>/<name>.zip` by default.
2. **Mods:** the Key Bridge server mod **1.3+** ([`mods-src/keybridge`](../../mods-src/keybridge)) for saving
   (`/skinbake`: PNG + MineSkin upload), and SkinRestorer for wearing (`skin set web classic <url> <player>`). Without
   Key Bridge the easel still paints and keeps drafts; the save dialog says saving needs the mod.
3. **Build:** run `jobs/skinpaint-1-walls.json`, then `jobs/skinpaint-2-stage.json` (`minecraft_run_command
   commands_file:…`) in an empty room.
4. **App:** copy `scarpet-apps/skinpaint.data.example/` to your world's `scripts/skinpaint.data/` and
   `scarpet-apps/skinpaint.sc` to `scripts/`, then `script load skinpaint`.

## How it plays

- **Step onto the stage** in front of the easel: if it's free, it's yours, and the brush is put in your last hotbar
  slot (whatever was there is kept and given back when you finish). To claim it again after finishing, step off and
  back on.
- **Hold right-click** with the brush and aim at the wall. One ray per click decides what you aim at: the **colour
  strip** above the canvas (48 x 4 swatches), the **toolbar** on its left (current colour, lighter/darker, 8 recent
  colours, brush, thick brush, bucket fill, eyedropper, eraser, mirror, layers, undo, templates, my skins, save,
  done, custom hex colour, clear, magnifier), or the **canvas**. The action bar names whatever you point at.
- **A cursor:** a see-through square in the brush colour sits on the pixel you are aiming at, so you see where the
  paint will land (no cursor over a spot that isn't part of the skin).
- **Magnifier:** click it, then a spot in the painting: that area (up to 16 x 10 pixels) is drawn 3x bigger across the
  canvas and you paint on it; click it again for the full view. Small pixels are hard to hit from a few blocks away.
- **Layers:** *automatic* by default — the brush paints what you see (the second layer where it covers the pixel,
  else the body) and the eraser removes only the top layer. The button cycles automatic → layer 1 only (the body) →
  layer 2 only (clothes, hair; the body is shown dimmed). Without *automatic*, painting under a template's hair or
  jacket changed nothing visible and looked broken. **Mirror** paints the left and right side together.
- **Save and wear:** a name, *show in the gallery*, *others may wear it*. The skin is on you within seconds and the
  easel is free again. **My skins** (toolbar or the spinning preview mannequin) = wear, edit a copy, hide/show,
  delete.
- **Leaving the studio area** (lift, teleport, logout) auto-saves unsaved work as a private skin in "My skins" and
  frees the easel; stepping off the stage for 20 s or 5 minutes idle also frees it (the painting stays as a draft).
- **Gallery:** three mannequins per page, ◀ ▶ buttons; click one to wear it, edit a copy, or (creator/op) hide or
  delete it.

All text displays and icons use `view_range 1.0` so the canvas stays readable from across a big room (0.3 made it
vanish at about 30 blocks).
