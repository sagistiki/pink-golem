# HUD — a speedometer, a compass, a timer anywhere on the screen, with no client mods

The same trick as the [minimap](minimap.md), made general: a resource pack adds HUD fonts and ONE text shader, a
scarpet library composes the text, and an invisible bossbar carries it. Players only accept the server resource pack.

| File | What |
|---|---|
| [`resourcepacks/hud/build_pack.py`](../../../resourcepacks/hud/build_pack.py) | builds `hud.zip`: the fonts, the shared `text.vsh`, invisible white bossbar sprites; rewrites the generated block of `hud.scl` |
| [`resourcepacks/hud/check_hud.py`](../../../resourcepacks/hud/check_hud.py) | verifies it all without a game client (see "Checking") |
| [`scarpet-apps/hud.scl`](../../../scarpet-apps/hud.scl) | the composer library: `hud_speedo`, `hud_compass`, `hud_timer`, `hud_bar`, `hud_text`, `hud_backdrop`, `hud_show`, `hud_hide` |

## How it works

1. **The carrier.** Each player gets one WHITE bossbar per app (`hud:<app>.<player>`); the pack makes white bars
   transparent, so only the title shows. The title is written in the font `<ns>:hud`.
2. **The title totals 0.** Every element moves the cursor back to where it started, so the whole title has an
   advance of exactly 0 and the client draws it starting at `x = guiWidth / 2` (bossbar titles are centred at
   `guiWidth/2 - width/2`, integer division).
3. **The band.** Every HUD glyph lies between y = 2 and 20 of its bossbar slot, and bossbar slots are 19 px apart
   (the vanilla overlay draws titles at y = 3, 22, 41 …). So the shader finds the slot from the glyph's own y — the
   HUD works whether its bossbar is first, second or fourth.
4. **The marker.** A glyph's colour carries where it goes, in bits the eye cannot see (≤ 7/255):

| Glyph | R & 3 | G & 3 | B & 3 | bit 2 of R, G, B |
|---|---|---|---|---|
| minimap cell (unchanged) | 1 | 2 | 3 | colour |
| minimap overlay (unchanged) | 1 | 2 | 1 | colour |
| **HUD, row 0** | 1 | 2 | **0** | the anchor 0..7 (R = bit 0, G = bit 1, B = bit 2) |
| **HUD, row 1** (drawn 18 px lower) | 1 | 2 | **2** | the anchor |

5. **The move.** The shader keeps each glyph's x/y inside its element and adds the anchor:

| # | Anchor | x | y (element top) | Good for |
|---|---|---|---|---|
| 0 | `top_left` | 6 | 68 (under the minimap) | game status, lap counter |
| 1 | `top_centre` | W/2 | 3 | compass |
| 2 | `top_right` | W − 6 | 6 | timer |
| 3 | `bottom_centre` | W/2 | H − 112 (above the action bar) | a big message, a progress bar |
| 4 | `bottom_right` | W − 6 | H − 42 | speedometer |
| 5 | `bottom_left` | 6 | H − 42 | fuel, boost |
| 6 | `middle_left` | 6 | H/2 − 18 | lists |
| 7 | `middle_right` | W − 6 | H/2 − 18 | scores |

W and H are the GUI size (`2 / ProjMat[0][0]` and `|2 / ProjMat[1][1]|`). Elements are aligned by the composer: left
anchors grow right, right anchors grow left, centre anchors are centred. An element is 36 px tall at most (two rows).

## Using it in an app

```
import('hud', 'hud_show', 'hud_hide', 'hud_speedo', 'hud_compass', 'hud_timer', 'hud_text', 'hud_bar');

// every 4 ticks while someone drives (an unchanged title is not re-sent)
hud_show(n, [hud_speedo(kmh, 160, 'KM/H', 'bottom_right'), hud_compass(query(p, 'yaw'), 'top_centre')]);

// a game: a timer top right, a line of text and a bar under the minimap
hud_show(n, [hud_timer(secs, 0xFFFFFF, 'top_right'),
             hud_text('ALIVE 3', 'sm', 0xFFFFFF, 'top_left', 0, null),
             hud_bar(boost / 100, 10, 0xFF5555, 'top_left', 1, null)]);

hud_hide(n);     // on exit, on disconnect, at the end of a round
```

| Element | Size | Notes |
|---|---|---|
| `hud_speedo(value, max, unit, anchor)` | 91 × 36 | 20-segment dial (green → red, both rows), the number in big digits inside, the unit on the right |
| `hud_compass(yaw, anchor)` | 121 × 18 | ±90° tape, ticks every 15°, N NE E … letters (N red), gold pointer; yaw 0 = south as in scarpet |
| `hud_timer(secs, rgb, anchor)` | 35–56 × 18 | `M:SS` / `H:MM:SS`, 7-segment digits over dim 8s on a dark panel |
| `hud_bar(frac, n, rgb, anchor, row, align)` | 4n × 6 | lit segments + dim ones |
| `hud_text(text, style, rgb, anchor, row, align)` | | styles `sm` (small, top of the row), `sl` (small, bottom), `big` (14 px), `seg`; characters 0-9 A-Z : . / - + % ! ? |
| `hud_backdrop(w, rows, anchor, align)` | w × 18/36 | a dark translucent panel |
| `hud_col(rgb, anchor, row)` | | the marked colour, for your own components |
| `hud_sp(px)` | | a horizontal move of any size (power-of-two space glyphs) |

Build your own element: a list of components `{'text' -> glyphs, 'color' -> hud_col(rgb, anchor, row)}` whose
advances sum to exactly 0. Every glyph that has ink needs a marked colour — an unmarked glyph stays where the carrier
draws it, in the middle of the top edge.

**In a vehicle app** (see [vehicles.md](vehicles.md)): import the library, call `hud_show(driver, …)` every 4 ticks
from the physics tick instead of the speed on the action bar (`kmh = speed × 72`), and `hud_hide(driver)` when the
driver gets out or disconnects.

## One shader, one server pack

- There can be only ONE `core/text.vsh` in the pack the player loads — the last pack wins. The HUD pack's shader is
  the minimap's shader byte for byte, plus the HUD block, so it serves both. `build_pack.py` builds it FROM the
  minimap's builder (`resourcepacks/minimap/build_pack.py`), so they cannot drift apart.
- Vanilla sends a single server resource pack: merge everything into one zip. **Put `hud.zip` before `minimap.zip`**
  in the merge (the first copy of a path wins in a simple merge): the HUD's `text.vsh` must be the one that survives.
  The white bossbar sprites are identical in both packs.
- Re-host the merged zip under a NEW url and update `resource-pack-sha1` (clients cache by hash). With the Key Bridge
  mod ([`mods-src/keybridge/`](../../../mods-src/keybridge)) `/packpush <url> <sha1>` sends it to everyone online
  without a restart.

## Checking (no game client needed)

`python3 resourcepacks/hud/check_hud.py` reads the built pack and:

1. confirms the minimap part of `text.vsh` is byte-identical to the minimap pack's and moves every non-HUD colour
   exactly as before (49,152 vertex × colour × screen-width cases);
2. measures every glyph from its PNG like the client does (advance = inked width × scale + 1, box top = 10 − ascent)
   and checks that all boxes lie in the band;
3. for each title in `sample_titles.json` (captured from the real `hud.scl` on a server): the advance totals 0, every
   inked glyph is marked, each glyph lands on the same spot from bossbar slots 0–3 and stays on screen at GUI sizes
   from 320×240 to 1280×720 — and prints each element's box per anchor;
4. `--preview out.png --only car_hud` draws the titles at GUI 960×540 so you can look at the layout;
   `--scan <scripts folder>` lists hex colours in your apps that the HUD shader would now move (should be none).

Capture your own titles: in a test app, `write_file('titles', 'json', {'mine' -> hud_title([…elements…])})` and run
the checker with `--titles <scripts>/<app>.data/titles.json`.

## Traps

| Trap | What happens | Do instead |
|---|---|---|
| A title whose advance is not exactly 0 | everything shifts sideways by half the error | `hud_show` refuses it (`hud_advance` ≠ 0); compose with the table, never with constants |
| A glyph taller than the band, or placed outside y 2..20 | its top and bottom corners find different slots: the glyph is torn | two rows (B&3 = 2) for tall things; the checker flags it |
| Text shadow | drawn in a darker colour = no marker = junk in the middle | `shadow_color: 0` on the title (the library does it) |
| A glyph without a marked colour | stays at the carrier position | colour every visible component with `hud_col` |
| Using the default font for labels | unknown advances, the total is wrong | only the HUD font's characters |
| Proportional digits | a timer jitters as digits change | the pack pins digit widths with an invisible pixel (alpha 1 < the 0.1 cut-off) |
| `bitmap` ascent > height | the whole font fails to load | the builder pads the image; the checker asserts it |
| A white bossbar for something visible | invisible with the pack | other colours for visible bars |
| More than ~4 bossbars at once | the vanilla overlay stops drawing below guiHeight/3 | keep visible bars few |
| Two `text.vsh` in the merged pack | the one merged first wins; with the old minimap shader the HUD glyphs stay at the top | hud.zip before minimap.zip |
| Overwriting a pack zip the game has open | the client reads garbage silently | new file name / new url |

## See also
[minimap.md](minimap.md) · [vehicles.md](vehicles.md) · [minigames.md](minigames.md) · [displays.md](displays.md) · [scarpet.md](scarpet.md)
