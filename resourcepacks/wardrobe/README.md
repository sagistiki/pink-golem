# Wardrobe (real clothes for the fitting wall in `scarpet-apps/residents.sc`)

Clothes that look like clothes, with no client mods: 15 tops, 11 bottoms, 8 pairs of shoes, 4 wigs, 5 pairs of wings
and 15 3D hats, all original pixel art drawn in code. They use the 26.x equipment assets (namespace `wardrobe`), so
the pieces are drawn on the player's body the way armour is, not as dyed leather. The pack also has a blank
fitting-dummy skin for the mannequin that shows off each look.

| File | What |
|---|---|
| `gen_wardrobe_pack.py` | the generator: every piece is a small function (`mk_hoodie`, `hat_crown`, …) listed in `TOPS` / `BOTTOMS` / `SHOES` / `WIGS` / `WINGS` / `HATS` |
| `wardrobe.zip` | the ready pack part (namespace `wardrobe`) |

## Run it

```bash
pip install pillow
python3 resourcepacks/wardrobe/gen_wardrobe_pack.py
```

This writes `build/` + `wardrobe.zip`, the catalogue
[`scarpet-apps/residents.data.example/wardrobe.json`](../../scarpet-apps/residents.data.example/wardrobe.json) (the
fitting wall's rows, names and the `/item` string of every piece), and review images in `previews/`:
`wardrobe_sheet.png` (every piece on the dummy, front and back) and `wardrobe_hats_1.png` + `_2.png` (the 3D hats,
rendered with [`resourcepacks/tools/model_preview.py`](../tools/model_preview.py), no game client needed). **Look at
them before shipping the pack.**

## Use it

1. Add `wardrobe.zip` to your server resource-pack build (`minecraft_pack build` picks up every
   `resourcepacks/<name>/<name>.zip` by default).
2. Copy `wardrobe.json` next to `studio.json` in your world's `scripts/residents.data/`, and add a `fitting` section
   to `studio.json` (see the example: a row of ◀ ▶ vanilla buttons per clothes row, three action buttons, the dummy's
   position). The coordinates in the example are from one real build: use your own.
3. `script load residents`. Players press ◀ ▶ to dress the dummy, then ✓ to wear the look (or right-click the dummy).
   The residents clerk can reset anyone's look: studio clothes off and their own skin back.

## How it works

- An item with `equippable={slot:"chest",asset_id:"wardrobe:top_hoodie"}` is drawn with
  `assets/wardrobe/equipment/top_hoodie.json`. Its layers are `humanoid` (a 64x32 texture in the old armour layout:
  head, chest, feet), `humanoid_leggings` (legs) and `wings` (the elytra model). Transparent pixels are not drawn.
- One chest asset can hold a `humanoid` layer AND a `wings` layer, so a top and wings share the chest slot
  (`top_<top>__<wings>`). Without a `glider` component nobody glides.
- A head item with `equippable` but no `asset_id` is drawn by the custom-head layer: its item model sits on the head.
  The head spans model units 1.6 to 14.4 on every axis (1 head pixel = 1.6 units), the model's north is the face, and
  x is mirrored.
- Mannequins render like players, so a mannequin previews everything: `item replace entity <uuid> armor.<slot>`
  dresses it. (`query(e, 'holds', slot)` returns null on mannequins, so the app always re-dresses it in full.)
- Every piece carries `custom_data={studio_outfit:1b}` and no armour points. The app only replaces or removes pieces
  with that tag, so a player's real armour is never touched.

## Add a piece

Write a `mk_<id>(t)` (paint the texture with `top_base` / `bottom_base` / `shoe_base` / `wig`) or a `hat_<id>()`
(boxes in head-pixel coordinates), add it to its list with an English name, and rerun the generator. The catalogue
and the fitting wall pick it up on the next `script load residents`.
