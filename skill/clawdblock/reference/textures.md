# Block textures — a texture pack made from code

When someone wants their world to *look* different (more detailed, more realistic, softer, a colour theme), you can
make the block textures yourself with numpy, and show them in 3D before anything goes into the game. Files:
[`resourcepacks/textures/build_pack.py`](../../../resourcepacks/textures/build_pack.py) (25 textures in a natural,
near-vanilla look at any resolution) and [`resourcepacks/tools/block_render.py`](../../../resourcepacks/tools/block_render.py).

## The workflow people like

1. **Ask for the direction in their words** ("more realistic", "cute and pastel", "sharper"), then offer 2-3 concrete
   variants side by side: resolutions (16 / 32 / 64), palettes, shading styles.
2. **Start with one or two blocks** (planks + grass show most styles). Render them in 3D next to vanilla with
   `block_render.py --compare`, plus a zoomed flat grid of the texels. Get a yes.
3. **Then the batch, in the same style:** a whole material family per step (all woods, the stone family, ground).
   Render before every push.
4. **Push it live** and ask them to walk around and say what stands out, good and bad. Fix only what they name.

Images you open yourself are invisible to the person: save the renders where they can open them, and say where.

## How the generator works

- Every surface is a **value field in [0, 1]** mapped through a **material ramp** (5 colours, dark → light) sampled from
  the vanilla texture's own darkest and lightest tones. Fields come from tileable FFT noise, fbm, domain warp and
  tileable Voronoi (a 3×3 copy of the points in a KD-tree gives distance to the nearest and second-nearest cell).
- **Structure first, then detail:** joints and seams are masks; cells get their own tone; a distance-field bevel or
  a bump-lit "dome" per cell gives depth; noise and single-pixel grit come last.
- **Everything tiles:** `np.roll` / `mode="wrap"` everywhere, positions taken modulo the size.
- **Colour families come from vanilla itself.** For 16 dye colours × 3 materials, don't pick ramps by hand. Read the
  vanilla texture from the client jar and take its brightness percentiles (4, 27, 50, 73, 96) as the 5 tones. Where
  vanilla is nearly flat (concrete spans 3 brightness levels, terracotta 5), build the ramp from the average colour
  darkened and lightened a little instead, toward black and white so that black and white concrete get tones too.
- A texture that mixes two colours (cherry leaves: pink + green) needs one ramp per colour. A single brightness ramp
  across both blends them into mud.
- **Sizes scale with the resolution:** tune at 64 px and multiply lengths by `K = res / 64` and counts of cells by
  `K²`. At 32 the cobblestones and gravel came out as tiny noise until the Voronoi site counts and radii were scaled.

## Rules that save a redo

- **Biome-tinted textures stay grey:** `grass_block_top`, the grass side *overlay*, vines, and the oak, spruce, birch,
  jungle, acacia, dark oak and mangrove leaves. The game multiplies them by the biome colour. Draw the detail in grey
  and keep vanilla's model. A coloured texture (or a model override without `tintindex`) makes grass the same green in
  every biome. Cherry, azalea, flowering azalea and pale oak leaves are NOT tinted, even though their models have a
  `tintindex`: draw them in colour (a vanilla texture's saturation tells you which kind it is: the tinted ones are grey).
- **Pixel-art feel = fewer tones, not fewer pixels.** `--pixel=N` k-means each texture to N tones (8 looks clearly
  pixel-art, 12 softer) and lets a lone pixel one tone away from its neighbours join them. Quantise each material on its
  own (bricks vs mortar, log rings vs bark rim, blossoms vs leaves): with one palette the mortar borrowed brick colours
  and seven small azalea flowers vanished into the greens.
- **Keep vanilla's layout:** plank board count, brick courses, where the log top's bark rim is. Players read blocks by
  their layout; a different pattern looks like a different block.
- Keep block textures square; an animated one is a vertical strip of square frames plus a `.png.mcmeta`.
- 26.x block models may store a texture as `{"sprite": ..., "force_translucent": ...}` instead of a string.
- Changing only textures needs no model files: the vanilla models pick up the new PNGs.

## Shipping it

The textures are one more part of the server resource pack: put the zip in the pack's parts, then
`minecraft_pack build` → `deploy` ([testing-apps.md](testing-apps.md)). A live push shows every player a reload screen
for a few seconds: check who is online and busy first. Keep the previous zip, so going back is one deploy.

**A block shows as a purple-black cube:** a texture or model it points to is missing or invalid. Bisect live: push
the pack with half the suspects removed, ask which half looks right, repeat.

## See also
[hud.md](hud.md) (the same pack carries the HUD) · [testing-apps.md](testing-apps.md) · [styles.md](styles.md)
