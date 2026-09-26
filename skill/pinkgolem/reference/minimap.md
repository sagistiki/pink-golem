# Minimap — a live HUD map with no client mods

A round minimap in the top-left corner for every player: the terrain around you, turning with your view (you always
face up), friends as coloured dots (on the rim when far away) and an N badge that travels around the ring. It needs
**no client mod**, only a server resource pack that players accept when they join.

Files: [`resourcepacks/minimap/`](../../../resourcepacks/minimap) (`build_pack.py`, `build_app.py`, the ready
`minimap.zip`) and the app [`scarpet-apps/minimap.sc`](../../../scarpet-apps/minimap.sc). Built for Minecraft 26.2
(resource pack format 88).

## How it works

The server can only put text in a few fixed places on the screen — none of them the top-left corner. The trick has
three parts:

1. **The map is text.** The app sends each player a bossbar whose title *is* the map, written in a custom font
   (`pinkgolem:mm`): a 1×2-pixel "cell" glyph per map row (one character per row; the row is set by the glyph's
   `ascent`), coloured per cell, joined by negative-space glyphs (`space` provider: `U+F801`… = −1, −2, −4…,
   `U+F811`… = +1, +2, +4…) so every row starts at the same x. Overlays (a ring, the N badge, friend dots, your
   arrow) are more glyphs, placed by moving the cursor with spaces.
2. **The bar is invisible.** The pack replaces the *white* bossbar sprites with transparent ones, and the minimap
   bossbar is white. Only its title shows. (Don't use white for other bossbars.)
3. **A shader moves it.** Bossbar titles are centred at the top. The pack overrides `core/text.vsh`: in the GUI
   branch, a glyph whose colour carries a **marker in the low bits** (`R&3 == 1`, `G&3 == 2`, `B&3 == 3` for map
   cells, `1` for overlays) is shifted by `LEFT − (guiWidth/2 − W/2)`, where `guiWidth = 2 / ProjMat[0][0]` and `W`
   is the title's total advance. Every other text is untouched. Cells are also widened by 1 px (bitmap glyphs always
   advance `width + 1`; 1-px glyphs + 1 px = seamless 2-px cells), using `gl_VertexID % 4` to find the right-hand
   corners.

The app samples the top block of each point (`top('surface', …)` then `map_colour(block)`), maps the name to the
vanilla map RGB, shades it against the block to the north like a real map (brighter uphill, darker downhill), darkens
deep water, then sets the marker bits. Samples are cached on a 2-block grid for 30 s; the terrain part is reused while
you stay in the same spot and look the same way (yaw rounded to 6°), and an unchanged title is not sent again. An
update is ~2–3 ms and ~8–11 KB; standing still costs ~0.2 ms.

## Install

1. Build (or use the committed `minimap.zip`): `python3 resourcepacks/minimap/build_pack.py` prints the SHA-1.
2. Host the zip somewhere players can download it (a raw GitHub URL of your fork pinned to a commit, a file host).
   If the server already sends a pack (Polymer's auto-host, a texture pack), **merge** the minimap assets into it —
   vanilla sends only one `resource-pack` — and host the merged zip. Nothing in the minimap pack clashes with normal
   packs unless they also replace `core/text.vsh` or the white bossbar sprites.
3. `server.properties`: `resource-pack=<url>` (escape `:` as `\:`), `resource-pack-sha1=<sha1>`,
   `require-resource-pack=false` or `true`. Restart.
4. `python3 pinkgolem.py app install minimap`, then turn it on for everyone:
   `script in minimap run set_default(true)`. Players: `/minimap on|off`.

Until the pack is live, keep the default **off** — a player without the pack sees the raw glyphs as a strip of
boxes at the top of the screen (`/minimap off` hides it for them).

## Sharing the shader with the HUD toolkit

Only one `core/text.vsh` can be active. The [HUD toolkit](hud.md) (`resourcepacks/hud/`) builds its `text.vsh` from
this pack's builder: the minimap block byte for byte, plus a HUD block for colours with `B&3 == 0` or `2` (the
minimap keeps `3` and `1`). The minimap works exactly as before with either shader (`check_hud.py` proves it). When
you use both, merge `hud.zip` BEFORE `minimap.zip` so the HUD's shader is the one that survives. After changing
`VSH`, `CELLS` or `LEFT` here, rebuild the HUD pack too.

## Changing it

- Size: `CELLS` (cells across, 2 px each) in **both** builders, `global_S` (blocks per cell) in `build_app.py`.
  Rebuild both, re-host the pack under a **new URL** and update the SHA-1.
- Another Minecraft version: copy that version's `assets/minecraft/shaders/core/text.vsh` from the client jar into
  `VSH` in `build_pack.py` (keep the marked block) and set `PACK_FORMAT` (`version.json` → `pack_version`).

## Lessons (each cost an evening)

- **Every cursor move must come from the layout, never a constant.** After shrinking 32 → 24 cells the row-return
  space was still −64 instead of −48: each row drifted 16 px, the title's advance became −336 instead of 48, and the
  shader moved the whole map off-screen — "it shows nothing". Check a real title: decode it, add up the advance of
  every character (a char → advance map from the font), it must equal `W`.
- **Never overwrite a pack zip in place while the game runs** (testing with a local copy in `resourcepacks/`): the
  client keeps the zip open and reads garbage without an error. Save it under a new name and re-select it.
- The client log (`logs/latest.log` of the player's game folder) lists the packs in load order
  (`Reloading ResourceManager: vanilla, file/…, server/…`) — the last one wins.
- `shadow_color: 0` on the title (text shadows are drawn with a darker colour, which would lose the marker and stay
  in the middle of the screen).
- Bitmap glyphs: `ascent` may not exceed `height`, or the whole font fails to load. A glyph far above its row needs
  a taller image.

## See also
[hud.md](hud.md) · [displays.md](displays.md) · [scarpet.md](scarpet.md) · [game-logic.md](game-logic.md)
