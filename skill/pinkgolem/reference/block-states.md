# Block states: getting orientation and multi-part blocks right

A block string is `name[state=value,…]`, e.g. `oak_stairs[facing=east,half=bottom]`. Commands place exactly the state
you give — nothing is auto-corrected the way it is when a player places a block by hand. This page lists the states
that matter for building and the ones that trip everyone up. Verify any state in the world with
`minecraft_inspect pos:[x,y,z]` (it returns the full state string).

## Directional blocks

| Block | State | Meaning | Tip |
|---|---|---|---|
| Stairs | `facing=north/south/east/west` | the side the stair **rises toward** (its tall back) | walk up toward `facing` |
| Stairs | `half=bottom/top` | top = upside down | eaves, window hoods, ceiling trim |
| Chair / sofa (stairs) | `facing` = **behind** the sitter | the sitter looks the opposite way | `parts.chair(faces=…)` does it for you |
| Slabs | `type=bottom/top/double` | lower half / upper half / full | a top slab on nothing is a floating shelf or table |
| Logs, pillars, basalt | `axis=x/y/z` | grain direction | beams along a wall: the wall's axis (`{axis_i}` in a Frame) |
| Doors | `half=lower/upper`, `facing`, `hinge=left/right`, `open` | `facing` = the direction you walk IN | set BOTH halves with the same facing and hinge |
| Trapdoors | `facing`, `half=top/bottom`, `open=true/false` | an open trapdoor stands against the side opposite to `facing` | shutters, cabinet fronts, armrests |
| Beds | `part=foot/head`, `facing` | `facing` points from the foot to the head | place both parts; head cell = foot + facing |
| Ladders | `facing` | the open side (away from the wall) | a ladder on the north face of a wall has `facing=north` |
| Wall signs, wall torches, buttons on walls | `facing` | away from the wall they hang on | |
| Buttons, levers | `face=floor/wall/ceiling`, `facing`, `powered` | | game logic polls `powered` (`game-logic.md`) |
| Lanterns | `hanging=true/false` | true = hangs under a block | chandeliers: `iron_chain` above |
| Chains | `iron_chain[axis=y]` | the 26.x name is **`iron_chain`** (not `chain`) | |
| End rods | `facing=up/down/…` | | modern lamp posts |
| Campfires | `lit=true/false`, `signal_fire` | signal_fire = taller smoke | a fireplace, chimney smoke |
| Candles | `candles=1..4`, `lit=true` | | table lights |
| Furnace, smoker, barrel, chest | `facing` | the side the opening faces | toward the room / the cook |
| Repeaters, comparators | `facing` | points toward the **input** | see `redstone.md` |
| Pistons | `facing` | the push direction | |

## Blocks that don't connect by themselves

Fences, walls, glass panes, iron bars and redstone dust take their shape from neighbours only when a player places
them or a neighbour updates. Placed by commands they come out as lone posts. Give the states explicitly:

| Block | States |
|---|---|
| Fences, glass panes, iron bars | `north/south/east/west=true/false` |
| Stone/brick walls | `north/south/east/west=none/low/tall`, `up=true/false` |
| Redstone dust | `north/south/east/west=none/side/up`, `power=0..15` |

`Build.fence_ring(cells, "oak_fence", gates=[...])` computes all of it (panes and walls too). Glass-pane windows from
`parts.window` get their connections from the Frame.

## Multi-part blocks

| Block | Parts | Rule |
|---|---|---|
| Doors | lower + upper | same `facing` and `hinge` on both; a lone upper half is a floating door |
| Beds | foot + head | recolouring: set BOTH old halves to air first, then place foot and head — replacing half by half pops the bed |
| Tall flowers (`rose_bush`, `peony`, `lilac`, `sunflower`), `tall_grass`, `large_fern` | `half=lower/upper` | both halves; on soil |
| Double chests | `type=left/right` | usually easier as two single chests or a barrel |

## Blocks that don't exist (so don't try)

- **No stairs, slabs or walls for concrete, wool or terracotta.** For coloured furniture use quartz (white), crimson
  (red), warped (teal), cherry (pink), dark oak (brown), blackstone (black), or stone/brick variants.
- **No glass stairs or slabs.** Glass roofs are stepped strips of full glass blocks.
- **No "wall lantern" in vanilla.** Hang a lantern under a block, or put it on a fence post.

## Blocks that need support or soil

| Block | Needs | Otherwise |
|---|---|---|
| Flowers, saplings, grass, ferns, bushes | grass/dirt/moss/podzol below | pops off as an item |
| Indoor plants | use `potted_*` (e.g. `potted_fern`, `potted_flowering_azalea_bush`) or a `moss_block` planter | |
| Torches, buttons, ladders, signs on walls | the block they hang on | pops off when that block changes |
| Lanterns `hanging=true` | a block (or chain) above | falls off |
| Sand, gravel, concrete powder | a block below | falls |
| Scaffolding, cactus, sugar cane | their own rules | check after building |

Build order in a job: supporting blocks first, attached blocks after — `mclib` writes layers bottom-up, and raw
commands (`b.cmd`) run after the voxels.

## Light

| Light source | Level | Notes |
|---|---|---|
| `lantern`, `sea_lantern`, `glowstone`, froglights, `shroomlight`, `campfire`, `end_rod` (14) | 15 | froglights: `ochre_` (warm), `pearlescent_` (pink-white), `verdant_` (green) |
| `light[level=N]` | 0–15 | invisible, no collision — the tidy way to stop mob spawns in attics, towers and under trees |
| `redstone_lamp[lit=true]` | 15 | stays lit only if placed lit and nothing updates it — prefer real light sources |

## Renamed or new in 26.x

- `chain` → `iron_chain` (copper chains exist too).
- `grass` → `short_grass` (older rename, still trips people up).
- Item components use SNBT (`give @p potion[potion_contents={custom_color:…}]`); text components inside them are
  SNBT compounds, and JSON-style `{"text":"…"}` is accepted.
- The `mannequin` entity is the vanilla way to make NPCs (`entities.md`).

When unsure whether an id exists: place one with `minecraft_run_command command:"setblock x y z <id>"` and read it
back with `minecraft_inspect` before generating a thousand of them.

## Common mistakes

| Mistake | Fix |
|---|---|
| Sofa backs toward the TV | chair/sofa stairs face away from where the sitter looks |
| Roof stairs facing outward | roof stairs face the ridge (they rise toward it) |
| Door with one half | always both halves (or `Build.door` / `Frame.door`) |
| Fences as single posts | `fence_ring` or explicit `north/south/east/west` |
| Flowers on planks | pots or a moss planter |
| `chain` in a 26.x command | `iron_chain` |

See also: `coordinates.md`, `furniture.md`, `roofs.md`, `redstone.md`.
