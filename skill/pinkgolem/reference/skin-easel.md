# Skin easel — paint a real player skin on a wall, wear it, share it

Read this before building anything that lets players **draw pixels in the world** (a skin editor, a pixel-art wall,
a drawing board) or that turns something made in game into a **real player skin**. The working example is
[`scarpet-apps/skinpaint.sc`](../../../scarpet-apps/skinpaint.sc) with its pack part and generator in
[`resourcepacks/skinpaint/`](../../../resourcepacks/skinpaint) (setup steps in its README) and the `/skinbake`
command of the Key Bridge server mod ([`mods-src/keybridge/`](../../../mods-src/keybridge)). Every number here was
verified live on Minecraft 26.2.

| Piece | What it does |
|---|---|
| `resourcepacks/skinpaint/gen_skinpaint.py` | one `CONFIG` block (the wall's `ORIGIN` + offsets) → `layout.json`, `templates.json`, `config.json`, the pack part, two build jobs, a mapping preview |
| `skinpaint.zip` | the pixel font `skinpaint:canvas`, the brush item, 15 toolbar icon quads |
| `scarpet-apps/skinpaint.sc` | the stage, the canvas, painting, the wall toolbar, dialogs, the gallery, saving |
| Key Bridge `/skinbake <id>` | PNG + MineSkin upload off the server thread, calls the app back |
| SkinRestorer | `skin set web classic <textures.minecraft.net url> <player>` puts it on the player for everyone |
| `resourcepacks/wardrobe` | `wardrobe:entity/dummy`, the blank skin of empty gallery mannequins |

## Pixels: a text_display with a 10x10 pixel font

A `text_display` is the cheapest way to show thousands of coloured pixels: one entity per band of rows, one text
component per run of equal colour, rebuilt only when a pixel in that band changes.

- **Line pitch.** Text display lines are exactly **10 font px** apart (`DisplayRenderer`: line height 9 + 1), and a
  font px is **0.025 block** at scale 1 (the renderer scales by -0.025). So a pixel of size `PX` blocks needs
  `scale = PX / 0.25`.
- **The glyph.** A 10x10 white bitmap with `height 10, ascent 7` fills one line exactly. Its automatic +1 advance is
  cancelled with a **space glyph of advance -1** after every pixel (`""`), so pixels touch with no seams.
  An empty cell is a space glyph of advance 10 (``).
- **Colour.** The component's `color` tints the white glyph: any 24-bit colour, no palette. Turn the display's
  `shadow` **off** (a shadow draws a dark copy 1 px down-right) and give it `background:0`.
- **Swatches with a gap** (colour strip, recent colours): ink only x 1..8 of the 10-px image. Its advance is then
  exactly 10 (inked width 9 + 1), so no spacer glyph is needed and every swatch has a 2-px gap.
- **Where it lands.** The text block grows **up** from the entity position, and its last row sits **1 font px below**
  the entity's y. For a band whose bottom edge is at `y_bottom`: entity y = `y_bottom + PX / 10`.
- **One display per band** (head rows / body + arms / legs): a stroke rewrites at most a few components, and a
  48-row picture never becomes one huge text.
- **view_range 1.0.** At `0.3` the canvas vanished from ~30 blocks away; set `view_range:1.0f` on every display and
  icon that must read across a room.

## Painting: one ray per click, hold-to-paint

- The painter's eye ray is intersected with the wall **plane** (constant x) in scarpet — no block raycast, no
  entities to hit. The same `[y, z]` hit decides, in order: the **colour strip** → the **toolbar** grid → the
  **canvas** views. One ray, three UIs.
- **Hold right-click** = a `paper` item with a `consumable` component (`consume_seconds:72000`, `animation:"brush"`,
  `sound:"minecraft:intentionally_empty"`, `has_consume_particles:false`): it never finishes, the arm animates, and
  nothing is eaten.
- Carpet 26.2 has **no `query(p, 'active_item')`**: track holding with `__on_player_uses_item` (start the stroke) +
  `__on_player_releases_item` / `__on_player_switches_slot` (end it) and check `query(p, 'holds', 'mainhand')` every
  tick while painting. Interpolate between the last and the current hit so fast strokes have no holes.
- Give the brush with `item replace entity <p> hotbar.8 with …` and select that slot; stash what was there and give it
  back on release (a plain `/give` gives nothing to a full inventory).
- Tooltips: while the brush is held, the action bar names what the ray points at (only when it changes).
- **A cursor:** one `text_display` with the pixel glyph, `text_opacity:150`, a hair in front of the canvas, moved
  every 2 ticks onto the aimed cell in the brush colour (only when the cell changes). Without it players can't tell
  whether the ray lands one pixel off.
- **Magnifier:** pixels of 0.19 block are hard to hit from 3-4 blocks. A zoom window (up to 16 x 10 cells of one view)
  is drawn by one more `text_display` at 3x scale over the canvas area; the normal bands are blanked while it is open,
  and the hit test maps the ray through the window. Painting marks the window dirty instead of the bands.
- **Paint what you see:** templates have a second layer (hair, jackets). Painting layer 1 under it changes nothing
  visible — it looks broken. Default to an automatic layer: write the second-layer texel where it is set, else the
  body; the eraser clears only the top layer.
- **A reload must not hand the easel to someone else:** save the painter's name in `__on_close` and let only them
  reclaim for a few seconds after the app loads (two people on the stage = the first in the player list won).

## The skin mapping

The wall shows five views, left to right as the painter sees them: **right side | front | left side | back | top of
the head** (the order the 64x64 template unwraps in). Each view cell points at one base-layer texel and one
second-layer texel. Faces nobody can paint from the front (body sides under the arms, inner arm/leg faces, tops and
bottoms) are **derived** at save time from the nearest visible edge. The base layer is always kept opaque (the
eraser only ever clears the second layer). `gen_skinpaint.py` writes the map and a preview that draws every template through
the views — the only mapping check you need.

## Saving: scarpet can't write a PNG → Key Bridge `/skinbake`

1. The app writes `skinpaint.data/bake/<id>.json` (4096 ARGB numbers) and runs `skinbake <id>`.
2. Key Bridge builds the PNG and uploads it to **MineSkin v2** on a worker thread: `POST
   https://api.mineskin.org/v2/generate`, multipart `file`, `variant`, `visibility`, `name`. It works **without an
   API key** (about 10/min, 60/h, 6 s apart); the answer has `skin.texture.url.skin` (a `textures.minecraft.net`
   url) and `skin.texture.data.value` / `.signature`.
3. Back on the server thread: `performPrefixedCommand("script in skinpaint run _baked('<id>','<url>','<value>','<sig>')")`.
4. The app runs `skin set web classic <url> <player>` (SkinRestorer re-signs it instantly for everyone) and dresses a
   gallery mannequin.

**Scarpet apps load before Fabric's `SERVER_STARTED`.** Key Bridge writes its marker file
(`skinpaint.data/keybridge.json`) at `SERVER_STARTED`, so it is **not there yet in `__on_start`** — read it lazily
when someone opens the save dialog.

## Mannequins with a signed skin

```
data modify entity <uuid> profile set value {properties:[{name:"textures",value:"<value>",signature:"<sig>"}]}
```

Set the **whole** profile (merging only the properties keeps the old look). An empty slot goes back to a pack
texture: `profile set value {texture:"wardrobe:entity/dummy",model:"wide"}`.

## Traps (each one happened)

- An entity **tag containing `:`** breaks `@e[tag=…]` and silently stops the rest of a spawn pass: build tags like
  `sp_tbi_tool_brush`, never `sp_tbi_tool:brush`.
- Scarpet `[a] + []` is **element-wise math**, not concatenation: build lists with `l += x`.
- Never put a `//` comment **inside** an expression (a multi-line map, a function argument); put it after a `;` or on
  its own line.
- A text component with an **empty `extra: []` is invalid** — send `{'text' -> ''}` instead.
- Summon only when the chunk is loaded (`loaded_status(pos) >= 3`) and after a cooldown, never because a selector
  came back empty (an unloaded chunk finds nothing → a new copy every tick).
- One painter at a time: stepping onto the stage claims a free easel; after finishing you must **step off** before the
  stage claims it for you again. Release on save, idle, time off the stage, leaving the studio area (with an
  auto-save as a private skin), and disconnect.
