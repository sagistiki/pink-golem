# Displays: floating text, signs, flags, showpieces and scoreboards

Read this when a build needs words or precise decoration: a name over a door, a plaque on a zoo enclosure, a menu,
a leaderboard, a striped flag, a spinning trophy, a speech bubble. All of these are **display entities**
(`text_display`, `block_display`, `item_display`): they have no hitbox, can be any size, glow at night if you ask, and
never get in the way of players.

## Rules that apply to every display

| Rule | Why |
|---|---|
| Give every display a `Tags:["<project>"]` | you can find, update and remove them later |
| In a generator, kill the old ones first: `b.before('kill @e[type=text_display,tag=<project>]')` | re-running the generator would otherwise stack duplicates |
| On a wall, put it on the **face** of the block ± 0.03, not the block centre | a block at z=50 spans z 50..51; a display inside the block is invisible |
| `brightness:{sky:15,block:15}` | full brightness at night, like a lit sign |
| Summon only in loaded chunks | the bot must be near (`entities.md`) |
| **No emoji** in game text | they render as empty boxes; use ★ ✦ ♥ ✓ ✖ ⏱ ▶ ◀ ♪ ⚒ |

Any language and any letters render fine; only emoji do not. Text is a text component written as SNBT-compatible
JSON: `{"text":"Welcome","color":"gold","bold":true}` or a list of them. A new line is `\n` inside the text.

## text_display — floating text

```
summon text_display 100.5 -58 40.5 {billboard:"center",Tags:["park"],alignment:"center",background:1073741824,brightness:{sky:15,block:15},text:{"text":"CITY PARK","color":"gold","bold":true}}
```

| Field | Values | Notes |
|---|---|---|
| `billboard` | `"center"` / `"fixed"` / `"vertical"` / `"horizontal"` | center = always turns to the viewer (labels in the open); fixed = a plaque on a wall |
| `Rotation:[yaw,0f]` | south 0, west 90, north 180, east -90 | only for `fixed`: the direction the text faces = where the readers stand |
| `background` | ARGB as a signed int | `1073741824` = the default translucent dark box; `0` = no box; `-1439485133` = a darker grey (speech bubbles) |
| `line_width` | pixels, default 200 | longer lines wrap; speech bubbles use 170 |
| `alignment` | `"center"` / `"left"` / `"right"` | |
| `transformation` … `scale:[s,s,s]` | 0.6 small print … 2.5 huge title | |
| `see_through`, `shadow` | `0b` / `1b` | `shadow:1b` helps on bright backgrounds |
| `teleport_duration` | ticks | smooths movement when the display follows something |

In a generator:

```python
from mclib import text_json, rainbow
b.text_display((x + 0.5, G + 3, z + 0.5), text_json("Welcome", "gold", True), "house", scale=1.0)
b.text_display((x + 0.5, G + 4, z + 0.5), rainbow("GRAND OPENING"), "house", scale=1.5)
P.label(b, x + 0.5, G + 2.2, z + 0.03, "Pandas", tag="zoo", color="white", facing="south")   # fixed plaque
```

`P.label` without `facing` makes a billboard label; with `facing` a fixed one. **G** = the ground block (flat world:
y=-61).

### Updating text

`data merge entity` accepts **one** entity. Select with `execute as`, which works for one or many:

```
execute as @e[type=text_display,tag=score_board] run data merge entity @s {text:{"text":"Score: 12","color":"yellow"}}
```

To pick one of several displays with the same tag, add a position: `@e[type=text_display,tag=zoo,x=87,y=-58,z=48,distance=..0.5,limit=1]`.
A live dashboard is a scarpet app that runs this every 20 ticks (`game-logic.md`).

## block_display — precise shapes and stripes

A `block_display` draws any block at any size, from its corner (the entity position) toward +x, +y, +z, scaled by
`transformation`. Use it for things blocks cannot do: thin stripes, flags, lasers, floating shapes.

```
summon block_display 100 -57 40.03 {Tags:["flag"],Rotation:[0f,0f],block_state:{Name:"minecraft:red_concrete"},transformation:{left_rotation:[0f,0f,0f,1f],right_rotation:[0f,0f,0f,1f],translation:[0f,0f,0f],scale:[1.2f,0.15f,0.03f]}}
```

- `block_state:{Name:"minecraft:oak_stairs",Properties:{facing:"east"}}` for blocks with states.
- `scale` stretches, `translation` offsets, `left_rotation`/`right_rotation` are quaternions (`[0f,0f,0.7071f,0.7071f]`
  = 90° around z, used for the flag pole).
- **Striped flags and signs:** a banner cannot make clean equal stripes (its patterns are fixed uneven bands).
  `parts.stripe_display` lays thin concrete slivers flat on a wall face:

  ```python
  P.stripe_display(b, x, y, z, "south", ["red", "orange", "yellow", "lime", "blue", "purple"], width=1.2, stripe=0.15, tag="flag")
  ```

  (x, y, z) = the top-left corner on the wall face; colours top to bottom; a dark log rod on top (`pole=None` to skip).
- **Lasers and moving light:** a long, thin, bright block_display (`sea_lantern`, `end_rod`, a stained glass). Animate
  by merging a new `transformation` together with `interpolation_duration:<ticks>` and `start_interpolation:0`. Test on
  one entity before summoning twenty.

## Rotating assemblies — wheels, fans, windmills, carousels

Blocks cannot move, but block displays can, smoothly and without mods (`scarpet-apps/ferris.sc` is the full example):

- **Spawn every piece at the pivot** (the axle) and place it with its `transformation` only. A display is drawn from
  its entity position toward +x +y +z, so for a piece whose centre sits at (u, v) on the wheel with its own angle φ
  and size (sx, sy, sz), at wheel angle θ around z:
  `left_rotation = [0, 0, sin(ψ/2), cos(ψ/2)]` with ψ = θ + φ, and
  `translation = R(θ)·(u, v) − R(ψ)·(sx/2, sy/2)` (plus `−sz/2` in z), so it turns about its own centre.
- **Animate on the client:** every N ticks merge the NEXT angle with `start_interpolation:0,interpolation_duration:N`.
  Players see a smooth turn; the server sends only 1/N of the updates. N = 10 works for ~100 pieces. Ease the angle
  (`f*f*(3-2f)`) for gentle starts and stops.
- **Things that must stay level** (cabins, seats) do not rotate: use an invisible `NoGravity` armor stand moved with
  `modify(e, 'pos', …)` every tick, and let the cabin's displays ride it (`ride <display> mount <stand>`); they
  follow it automatically. A riding display sits at stand + 1.975, a riding player's feet at stand + 1.375 — put the
  cabin floor just under the feet.
- **Players ride** with `ride <player> mount <stand uuid>` and stay mounted while the stand moves. Shift dismounts in
  vanilla: watch `query(p, 'mount')` every tick and teleport a rider who got off to a safe spot, or they fall.
- Board by standing on a pad (position polling), not by clicking — a fake player can then test the whole ride. The
  server cannot render display transformations, so ask a real player to look before you announce it.
- Keep it cheap: run only while a real player is near, tag every entity and `kill @e[tag=…]` before respawning.

## item_display — showpieces and display cases

```
summon item_display 100.5 -58.5 40.5 {Tags:["trophy"],item:{id:"minecraft:golden_apple",count:1},teleport_duration:2,brightness:{sky:15,block:15},transformation:{left_rotation:[0f,0f,0f,1f],right_rotation:[0f,0f,0f,1f],translation:[0f,0f,0f],scale:[1.2f,1.2f,1.2f]}}
```

- **Spinning showpiece:** with `teleport_duration:2`, turning the yaw a few degrees every 2 ticks spins it smoothly.
  In a scarpet app:

  ```
  __on_tick() -> if (tick_time() % 2 == 0, for (entity_selector('@e[type=item_display,tag=trophy]'), modify(_, 'yaw', query(_, 'yaw') + 6)));
  ```

- **Display case:** a `glass` block with an item_display at its centre (x+0.5, y+0.5, z+0.5) — a museum case that
  nobody can take the item from.
- Items keep their components: `item:{id:"minecraft:diamond_sword",count:1,components:{"minecraft:enchantment_glint_override":true}}`.

## Speech bubbles

| Who speaks | How |
|---|---|
| Your bot | `minecraft_chat` — public messages also float above the bot's head (`bubble:false` to skip) |
| A helper builder | `minecraft_helpers action:say name:"<helper>" message:"..."` |
| Any player-type body (bot, helpers) | `script in bubble run say('<name>', 'text', 4)` / `clear('<name>')` |
| An NPC (mannequin, villager) | a temporary text_display above its head, killed after ~3 s (`entities.md`) |

`bubble.sc` follows the speaker every tick, removes the bubble after the given seconds, and removes all bubbles when
it reloads. Keep bubble text short (one or two lines).

## Holograms and leaderboards

The record board in `scarpet-apps/race.sc` is the pattern:

1. Build the text as a list of components, one per line: a gold title, then `1. name  time` lines (first place in
   yellow), or "no times yet" when empty.
2. If a display with the board's tag exists → `execute as @e[type=text_display,tag=<tag>] run data merge entity @s
   {text:[...]}`; otherwise summon it (billboard center, translucent background).
3. Keep the data in the app's data file (`race.data/records.json`), never only in memory, so a reload or restart
   redraws the same board.

For a sign-like board on a wall use `billboard:"fixed"` with the wall's yaw.

## Names on entities

- `CustomName:"Mia"` — a **plain string**. A JSON string such as `'{"text":"Mia"}'` shows the raw JSON, and
  `'"Mia"'` shows the quotes.
- `CustomNameVisible:1b` shows it always; without it the name shows only when you look at the entity.

## Colourful text

`mclib.rainbow("TEXT")` returns a component list with one colour per character (8 colours, bold). Use it in
`b.text_display(...)`, in `tellraw` and in `title @a title <json>`. `mclib.text_json(s, color, bold)` makes a single
plain component. Colours by name (`gold`, `aqua`, `light_purple` …) or `#RRGGBB`.

## Common mistakes

- Display centred in the wall block → invisible. Use the face ± 0.03.
- `data merge entity @e[tag=x]` matching two displays → error; use `execute as … run data merge entity @s`.
- Emoji in a plaque → boxes.
- Regenerating without `b.before('kill …')` → two copies of every label.
- A banner for a rainbow flag → uneven bands; use `parts.stripe_display`.
- Board data kept only in an app global → the board resets on reload.

## See also

`entities.md` · `game-logic.md` · `scarpet.md` · `landscaping.md` · `round-and-tall.md` · `behaving-naturally.md`
