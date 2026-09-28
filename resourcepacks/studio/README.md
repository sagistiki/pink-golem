# Character studio (for `scarpet-apps/residents.sc`)

Seven original 64x64 skins drawn in code (mannequin textures `studio:entity/skin/<id>`, plain PNGs in `skins/` for SkinRestorer) and a resident-card item. Also used by the club, hotel, museum and roof examples for their NPCs.

```bash
pip install numpy pillow scipy soundfile
python3 resourcepacks/studio/gen_studio_pack.py
```

The output zip is a resource-pack part: add it to your pack list. The guide is
[`skill/pinkgolem/reference/tower-floors.md`](../../skill/pinkgolem/reference/tower-floors.md).
