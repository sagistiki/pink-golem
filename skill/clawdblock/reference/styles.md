# Styles and palettes

Read this when you choose the blocks for a build, when a build "looks off" and you are not sure why, or when you add
to something that already exists. It gives tested palettes per style, the 60-30-10 rule, texture mixing, and which
blocks have stairs, slabs and walls.

## 1. Look before you choose

If there are builds nearby, **match them** — a new house in a street should belong to the street.

1. `minecraft_vision target:near_player` (or `target:pos`) → the neighbour's size, block counts, roof and windows.
2. `minecraft_inspect from:[...] to:[...] mode:counts` on a wall or roof → the exact blocks and states.
3. Continue *that*: the same wall and roof blocks, roof pitch, window size, path width and lamp style. Vary one
   thing (the accent colour, the roof material) so it is a sibling, not a copy.

Only on empty land do you pick a style freely — ask the player which they like, or offer two.

## 2. The 60-30-10 rule

| Share | Role | Example (cottage) |
|---|---|---|
| ~60 % | main wall block | `white_terracotta` |
| ~30 % | structure: frame, roof, base | `stripped_spruce_log`, `spruce_stairs`, `stone_bricks` |
| ~10 % | one accent | red rug, red bed, flowers at the door |

**2–3 main blocks + 1 accent.** More than that looks noisy; one block alone looks flat. The accent repeats in
small doses (door, shutters, flowers, interior textiles), never on a whole wall.

## 3. Palettes

Block strings are exact ids. `*_stairs`/`*_slab` means the stairs/slabs of that material (check the table in §6).

| Style | Walls | Frame / structure | Base | Roof | Floor | Windows | Accent / details |
|---|---|---|---|---|---|---|---|
| **Cottage** (`cottage.py` oak) | `white_terracotta` | `stripped_spruce_log` | `stone_bricks` | `spruce_stairs` / `spruce_planks` / `spruce_slab` | `oak_planks` | `glass_pane` 2×2 | `spruce_door`, red carpet, flower beds, lanterns |
| Cottage, birch variant | `birch_planks` | `stripped_birch_log` | `mossy_cobblestone` | `cherry_*` | `birch_planks` | `glass_pane` | `cherry_door`, pink |
| **Modern** (`modern_villa.py` white) | `white_concrete` | `black_concrete` trim bands | — | flat, `light_gray_concrete` + black trim | `smooth_quartz` | `glass` full-height, 2-high bands | `dark_oak_planks` deck, `pearlescent_froglight` in ceilings, `end_rod` lamps |
| Modern, dark | `black_concrete` | `white_concrete` trim | — | flat, `gray_concrete` | `polished_deepslate` | `tinted_glass` | `spruce_planks` deck |
| Modern, warm | `white_concrete` + `stripped_dark_oak_wood` | `black_concrete` | — | flat | `birch_planks` | `glass` | `stripped_oak_wood` deck |
| Other modern pairs | `smooth_quartz` + `dark_oak`; `polished_andesite` + `spruce`; `light_gray_concrete` + black glass box | | | flat with overhang | | 2-high glass bands | |
| **Medieval / stone** (`cottage.py` dark, `tower.py` stone) | `stone_bricks` (+ mossy/cracked, §4) | `dark_oak_log` | `cobblestone` | `deepslate_tile_stairs` / `deepslate_tiles` | `dark_oak_planks`, `spruce_planks` | narrow `glass_pane` slits | `mossy_stone_bricks` bands, lanterns, `iron_bars` |
| **Japanese** | `white_terracotta` panels | `stripped_dark_oak_log`, `dark_oak_log` | `stone_bricks`, `andesite` | `deepslate_tile_stairs` or `dark_oak_stairs`, wide overhang | `bamboo_mosaic`, `spruce_planks` | `spruce_trapdoor` screens | `bamboo_fence`, lanterns, cherry trees, a red accent |
| **Fairytale** | `smooth_quartz` | `quartz_pillar` columns | `pink_terracotta` | `cherry_stairs` / `cherry_planks`, `pink_concrete` cones | `cherry_planks`, checker floors | `pink_stained_glass`, rose windows in gables | `gold_block` + `end_rod` spire tips, cherry doors and fences |
| **Desert** (`tower.py` sandstone) | `cut_sandstone`, `smooth_sandstone` | `chiseled_sandstone` | `sandstone` | flat with parapet: `smooth_sandstone_slab` | `smooth_sandstone`, `birch_planks` | small `glass_pane` | `orange_terracotta` / `terracotta` bands, `acacia` details |
| Desert, mud | `mud_bricks`, `packed_mud` | `stripped_acacia_log` | `mud_bricks` | flat, `mud_brick_slab` | `packed_mud` | small windows | `orange_terracotta` |
| **Nordic / spruce** | `spruce_planks` | `spruce_log`, `stripped_spruce_log` | `cobblestone`, `stone` | steep `dark_oak_stairs` or `deepslate_tile_stairs` | `spruce_planks` | `glass_pane` with `spruce_trapdoor` shutters | `white_wool` / `snow_block` touches, lanterns, campfire chimney |
| **Industrial** | `bricks`, `polished_deepslate`, `deepslate_bricks` | `iron_bars`, `iron_chain` | `polished_andesite` | flat, `smooth_stone_slab`, `red_nether_bricks` rim | `gray_concrete`, `smooth_stone` | `tinted_glass` band | `waxed_cut_copper` pipes, `iron_trapdoor`, `end_rod` lights |

Copper turns green over time; use the `waxed_*` blocks to keep a colour.

## 4. Texture mixing

Large areas of one block look like wallpaper. Mix in variants of the **same** material at random:

```python
import random
rnd = random.Random(seed)
def stone():
    return rnd.choices(["stone_bricks", "mossy_stone_bricks", "cracked_stone_bricks"], weights=[70, 20, 10])[0]
for i in range(0, W + 1):
    for j in range(1, H + 1):
        f.set(b, (i, j, 0), stone())
```

| Main block | Mix in |
|---|---|
| `stone_bricks` | `mossy_stone_bricks`, `cracked_stone_bricks` |
| `cobblestone` | `mossy_cobblestone`, `stone`, `andesite` |
| `deepslate_bricks` | `cracked_deepslate_bricks`, `deepslate_tiles` |
| `bricks` | `granite` specks (a few %), `mud_bricks` |
| `sandstone` | `smooth_sandstone`, `cut_sandstone` |
| roof `deepslate_tiles` | `cobbled_deepslate` near the eaves |
| paths | `dirt_path`, `coarse_dirt`, `gravel` (`landscaping.md`) |

- Keep the **mix inside one colour family** — random colours read as damage, not texture.
- Weather the **bottom** more than the top: mossy blocks near the ground and on the north side.
- Use a fixed `seed` so a regeneration gives the same pattern.

## 5. Colour harmony

- **Warm with warm, cool with cool**: oak, birch, sandstone, terracotta, bricks together; spruce, dark oak, stone,
  deepslate, andesite together. Quartz and white concrete go with both.
- **Contrast between wall and roof**: a light wall under a dark roof (or the reverse). Same-tone walls and roof
  melt into one blob.
- **Frame darker than infill**: logs around plaster, stone under wood.
- **Saturated colours** (concrete, wool) in small areas only — accents, awnings, flowers. A whole house of
  `lime_concrete` looks like a toy.
- **One accent colour per build**, repeated three or four times.
- Glass: plain `glass` for houses; stained or `tinted_glass` for modern and night glow.

## 6. Which blocks have stairs, slabs and walls

| Material | Stairs | Slab | Wall |
|---|---|---|---|
| every wood: oak, spruce, birch, jungle, acacia, dark_oak, mangrove, cherry, pale_oak, bamboo, crimson, warped | ✓ | ✓ | ✗ (fence + fence gate) |
| `stone` | ✓ | ✓ | ✗ |
| `smooth_stone` | ✗ | ✓ | ✗ |
| `cobblestone`, `mossy_cobblestone`, `stone_bricks`, `mossy_stone_bricks` | ✓ | ✓ | ✓ |
| `granite`, `diorite`, `andesite` | ✓ | ✓ | ✓ |
| `polished_granite`, `polished_diorite`, `polished_andesite` | ✓ | ✓ | ✗ |
| `cobbled_deepslate`, `polished_deepslate`, `deepslate_bricks`, `deepslate_tiles` | ✓ | ✓ | ✓ |
| `tuff`, `polished_tuff`, `tuff_bricks` | ✓ | ✓ | ✓ |
| `bricks`, `mud_bricks` | ✓ | ✓ | ✓ |
| `sandstone`, `red_sandstone` | ✓ | ✓ | ✓ |
| `smooth_sandstone`, `smooth_red_sandstone` | ✓ | ✓ | ✗ |
| `cut_sandstone`, `cut_red_sandstone` | ✗ | ✓ | ✗ |
| `quartz_block` (→ `quartz_stairs`), `smooth_quartz` | ✓ | ✓ | ✗ |
| `prismarine` | ✓ | ✓ | ✓ |
| `prismarine_bricks`, `dark_prismarine` | ✓ | ✓ | ✗ |
| `nether_bricks`, `red_nether_bricks` | ✓ | ✓ | ✓ |
| `blackstone`, `polished_blackstone`, `polished_blackstone_bricks` | ✓ | ✓ | ✓ |
| `end_stone_bricks` | ✓ | ✓ | ✓ |
| `purpur_block` (→ `purpur_stairs`) | ✓ | ✓ | ✗ |
| `cut_copper` (all oxidation stages, waxed too) | ✓ | ✓ | ✗ |
| **concrete, wool, terracotta (plain and coloured), glazed terracotta, glass, stained glass** | ✗ | ✗ | ✗ |
| logs, `quartz_pillar`, `quartz_bricks`, cracked and chiseled variants, `deepslate` itself | ✗ | ✗ | ✗ |

- Plural blocks get singular names: `deepslate_tiles` → `deepslate_tile_stairs`, `stone_bricks` →
  `stone_brick_slab`, `bricks` → `brick_wall`, `mud_bricks` → `mud_brick_stairs`.
- Need a white or coloured stair/slab? Use `quartz_*` / `smooth_quartz_*` for white, or pick a wood or stone of
  that colour (the sofa table in `furniture.md`). Glass has panes; wool has carpets.
- Fences, walls and panes placed by commands do not connect — use `Build.fence_ring` (`block-states.md`).

## Common mistakes

| Mistake | Fix |
|---|---|
| Five main blocks and three accents | 2–3 main + 1 accent |
| `white_concrete_stairs` / `glass_slab` in a job | they do not exist — see §6 |
| A new build ignores the style of its neighbours | inspect first, continue their palette |
| Random mix of unrelated blocks as "texture" | variants of one material only |
| Roof the same tone as the walls | contrast wall and roof |
| Unwaxed copper for a fixed colour | `waxed_*` copper |

See also: `houses.md` · `roofs.md` · `furniture.md` · `landscaping.md` · `block-states.md` · `behaving-naturally.md`
