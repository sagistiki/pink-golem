# Museum photos (for `scarpet-apps/museum.sc`)

Frames your own landmark renders: crops each `minecraft_screenshot` render named `mus_<id>` to its content, sets it in a mat with a frame (320x200) and packs `museum:<id>` quads. No photos ship with it: they are pictures of your world.

```bash
pip install numpy pillow scipy soundfile
python3 resourcepacks/museum/gen_museum_pack.py spawn first_house tower
```

The output zip is a resource-pack part: add it to your pack list. The guide is
[`skill/pinkgolem/reference/tower-floors.md`](../../skill/pinkgolem/reference/tower-floors.md).
