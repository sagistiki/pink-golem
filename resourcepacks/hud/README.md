# HUD toolkit (resource pack + checker)

HUD elements anywhere on the screen with no client mods: a speedometer dial, a compass tape, a 7-segment timer, bars
and text, at eight anchors (corners, edges, centre). The composer is the scarpet library
[`scarpet-apps/hud.scl`](../../scarpet-apps/hud.scl); the technique is explained in
[`reference/hud.md`](../../skill/clawdblock/reference/hud.md). Minecraft 26.2 (pack format 88).

| File | What |
|---|---|
| `build_pack.py` | writes `build/` + `hud.zip` (sha1 printed) and the generated block of `scarpet-apps/hud.scl` (glyph tables and advances measured from the images) |
| `check_hud.py` | verifies the pack and real titles with no game client: advances, the glyph band, the anchors, the minimap part of the shader, `--preview` PNG |
| `sample_titles.json` | titles composed by `hud.scl` on a live server (speedometer, compass, timer, bar, text, all anchors) |
| `hud.zip` | the ready pack |

The pack contains:

- `assets/clawdblock/font/hud.json` + `textures/font/hud_*.png` — small 5×7 text (two heights), big text (×2),
  7-segment digits, a 20-segment dial in two 18-px slices, bar segments, compass ticks and pointer, dark backdrop
  strips, and power-of-two space glyphs (−512 … +512 px);
- `assets/minecraft/shaders/core/text.vsh` — the minimap's shader byte for byte plus the HUD block (built from
  `../minimap/build_pack.py`, so the two never drift apart);
- transparent white bossbar sprites (the carrier bar is invisible);
- `assets/clawdblock/hud_layout.json` — the band, the anchors and the minimap constants, for tools (the game ignores it).

## Build, check, deploy

```bash
python3 resourcepacks/hud/build_pack.py          # hud.zip + scarpet-apps/hud.scl generated block
python3 resourcepacks/hud/check_hud.py           # must end with "ALL CHECKS PASSED"
python3 resourcepacks/hud/check_hud.py --preview hud.png --only car_hud,game_hud
```

Merge `hud.zip` into your server pack **before** `minimap.zip` (only one `text.vsh` survives a merge and it must be
this one), host it under a new url, set `resource-pack` / `resource-pack-sha1`, restart. Copy `scarpet-apps/hud.scl`
into the world's `scripts/` folder and `import('hud', …)` it from your apps.

Changing the look: edit the glyph data in `build_pack.py` (fonts, dial geometry, colours), rebuild, run the checker,
recapture `sample_titles.json` from a test app if the element layout changed.
