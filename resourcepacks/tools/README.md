# Resource pack tools

Helpers for people (and AIs) who make resource packs. Python 3, no dependencies.

| Tool | What |
|---|---|
| [`model_preview.py`](model_preview.py) | renders item / block models (JSON elements with textures, element and face rotation, parent chains) to a PNG — check a model's shape, decals and which way it faces without starting the game |

## model_preview.py

```bash
python3 resourcepacks/tools/model_preview.py <pack folder or .zip> <ns:item/model> [...] --out preview.png
python3 resourcepacks/tools/model_preview.py resourcepacks/coaster/coaster.zip coaster:item/front coaster:item/car --gap 19.6
python3 resourcepacks/tools/model_preview.py resourcepacks/cars/cars.zip cars:item/sedan --tint C04040 \
        --assets "<.minecraft>/versions/26.2/26.2.jar"       # vanilla textures come from the client jar
```

| Option | Default | Meaning |
|---|---|---|
| `--out` | `preview.png` | output file |
| `--yaw`, `--pitch` | 35, 25 | turn the models around the vertical axis, then look down on them (degrees) |
| `--gap` | the first model's length | model units between the models of a row (they line up along +z, the first in front at -z, like a train) |
| `--assets` | — | more pack folders / zips / the client jar, searched after the pack for textures and parent models (repeatable) |
| `--tint` | none | colour for faces with a `tintindex` (dyed items, grass) |
| `--size`, `--bg` | `900x460`, `E2E6EC` | image size and background |

- A texture it cannot find draws **magenta** and prints a warning (vanilla textures are not in your pack: pass the
  client jar with `--assets`).
- It is a point-splatting renderer with flat light from the upper front left: right for shapes, decals, texture
  mix-ups and orientation, not for lighting or transparency.
- Remember the item_display flip: an `item_display` shows an item model turned 180° (its +z side faces away from the
  display's yaw), so a vehicle whose nose is at -z in the preview drives toward the display's +z / its yaw
  ([reference/rides.md](../../skill/clawdblock/reference/rides.md), [vehicles.md](../../skill/clawdblock/reference/vehicles.md)).
- It checks what the model looks like, not whether the game accepts the pack: run `minecraft_pack action:build
  check_only:true` for that ([testing-apps.md](../../skill/clawdblock/reference/testing-apps.md)), and look at a
  new model in game once — a model the client rejects shows as the purple-black missing-model cube.
