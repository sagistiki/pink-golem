# Car models (resource pack for `scarpet-apps/cars.sc`)

Five box-built car models — `sedan`, `sports`, `suv`, `taxi`, `police` — as item models in the namespace `cars`.
The body is tinted with the item's `dyed_color`, so one model comes in every colour. Minecraft 26.2 (pack format 88).

| File | What |
|---|---|
| `build_pack.py` | writes `build/` and `cars.zip`, prints the SHA-1 (stdlib Python only) |
| `cars.zip` | the ready pack |

## Use

1. Send it to players as the server resource pack (`server.properties`: `resource-pack=<url>`,
   `resource-pack-sha1=<sha1>`). Vanilla sends only ONE pack: merge it with the minimap / HUD packs first
   (see [`reference/hud.md`](../../skill/pinkgolem/reference/hud.md), "One server pack").
2. Install the app: copy `scarpet-apps/cars.sc` into the world's `scripts/` folder, `script load cars`.
3. Install the **Key Bridge** server mod ([`mods-src/keybridge/`](../../mods-src/keybridge): a tiny Fabric mod that
   copies each player's movement keys into the scoreboard `keys`; players install nothing). Without it, cars only move with `set_keys()` in tests.
4. Put a car down: stand somewhere flat and run `/cars here sports red`. For a parking lot write
   `scripts/cars.data/lot.json` (format in the header of `cars.sc`) and `script load cars`.

## Add a model

Write a function that returns boxes (`box(x1, y1, z1, x2, y2, z2, texture, tint)` in 16-units-per-block model space,
nose at +z), add it to `MODELS`, rebuild, and add a row to `global_M` in `cars.sc` (scale, top speed, acceleration,
steering, grip, camera distance/height, half length/width). The recipe behind the physics and the camera:
[`reference/vehicles.md`](../../skill/pinkgolem/reference/vehicles.md).
