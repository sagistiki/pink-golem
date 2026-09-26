# Water: pools, ponds, fountains, waterfalls and safe landings

Read this before you place a single water (or lava) block. Water is the one building material that moves by itself:
one careless source can flood a room, wash away flowers and torches, and leave stray sources that show up in every
later check. The rules below keep it where you put it.

**G** = the ground block (flat world: y=-61); see `coordinates.md` for normal terrain.

## How water moves (vanilla)

| Behaviour | Consequence |
|---|---|
| A source flows into **air beside it and below it**, never up | every water cell needs a solid (or water) neighbour on 4 sides and below |
| On a flat surface it spreads up to 7 blocks from the source | a single leak floods a whole room |
| It falls any height, then spreads again where it lands | a leak on a roof runs down the facade |
| It flows into and breaks non-solid blocks: flowers, grass, torches, redstone dust, rails | they drop as items |
| Flowing water dries up once its source is gone | remove the source, not the flow |
| Waterlogged blocks behave like sources | a waterlogged slab at a basin edge leaks |
| Placed ice melts near bright block light | decorative ice turns into loose water — use `packed_ice` or `blue_ice` |

## The containment rules

1. **Build the basin first, water in the LAST job.** Separate Build for the water saved last, or raw commands at the
   end with `b.cmd(...)` (raw commands run after all voxels). Water placed before its walls spills at once.
2. **Close every side.** Walk the rim in your head at each water level: 4 side neighbours and the block below must be
   solid or water. On normal terrain a lower neighbouring column means a gap in the rim.
3. **Dig, don't stack.** A pool dug into the ground (surface at G) is contained by the ground itself; a pool built on
   top of the ground needs its own walls.
4. **Fill only the air:** `fill x1 y1 z1 x2 y2 z2 water replace air` keeps pillars, lights and plants inside the basin.
5. **Count it.** `script in cu run count(x1, y1, z1, x2, y2, z2)` → the `water` entry must equal what you placed
   (`b.counts()` in the generator gives the plan). More water = a leak or flowing water.
6. Remove water with `fill … air replace water`; waterlogged blocks need their state set to `waterlogged=false`.

## What the verification tells you

After every build job the automatic verification (and `minecraft_verify` later) scans the build box for fluids the
build did not place:

| Field | Meaning | Action |
|---|---|---|
| `stray_fluids` | water/lava **source** blocks you did not place, with examples | a leak or spill — find and fix it; the job is not `ok` while this is above 0 |
| `flowing_water` | number of flowing blocks | expected for fountains and waterfalls; a leak if they run outside the basin |

Only the build's own box is scanned. If you suspect water ran further, `count` a bigger box. Waterlogged blocks are not
water blocks, so they never count as stray sources, but the flow they make does show up as flowing.

## Pools

```python
P.pool(b, x1, z1, x2, z2, G, depth=2, rim="smooth_quartz", lining="light_blue_concrete", lights=True)
```

Water fills x1..x2 × z1..z2 from G-depth+1 up to G; the lining wraps it one block out on every side and underneath;
the rim is flush with the ground; `sea_lantern`s sit in the long walls. Depth 2 is a paddling pool, 3 feels like a
real pool. Surround it with a deck at G (it replaces the ground, like a path) and loungers at G+1. The modern villa
blueprint uses it with `depth=3`.

## Ponds

```python
P.pond(b, cx, G, cz, rx=5, rz=4, depth=2, seed=1, lilies=4)
```

A natural oval dug into the ground: water `depth` deep in the middle and 1 deep at the edge, a sand/gravel/clay bed,
a ragged sand/gravel shore, lily pads on the surface and seagrass on the bottom. The rim is the existing ground at G,
so on uneven terrain level the site first (`landscaping.md`). Sugar cane on the shore must stand on sand/dirt right next to a water block.

## Fountains

```python
P.fountain(b, cx, G + 1, cz, r=3, rim="smooth_quartz", water=True, jet="quartz_pillar")
```

The rim block replaces the ground under the whole disk, a 1-high rim ring stands at G+1, water fills the inside, and a
2-high pillar in the centre carries a water source on top that runs down into the basin. **Flowing water here is
expected** — it will appear in `flowing_water`. Keep the basin radius ≥ 2 so the jet's spill lands inside it.

## Waterfalls

- Put the source in a pocket at the top (a notch in a cliff, a ceiling pocket in a cave) so it spills over one edge.
- Let the falling column land **in a pool of source blocks**: falling water that lands on dry ground spreads up to 7
  blocks in every direction.
- Give the landing pool a 1-block rim and count it like any basin.

## Troughs, sinks and small water

| Want | Use | Why |
|---|---|---|
| Animal trough, kitchen sink, bird bath | `water_cauldron[level=3]` | a full cauldron never flows (`parts.kitchen` uses it) |
| Underwater plants | `seagrass`, `kelp`, `sea_pickle` inside source water | they need water around them |
| Bubble column (aquarium effect) | `soul_sand` (up) or `magma_block` (down) under a column of sources | |
| Water in a stair, slab, fence, pane or lantern | the block with `waterlogged=true` | a plain `setblock` over water replaces the water |

Waterlogged blocks placed next to air leak like a source, so keep them inside the sealed basin.

## Falling into water

Landing in water negates fall damage. **2 blocks deep is enough**: a 187-block free fall into a 2-deep pool was
tested and the player landed at full health. Make the landing pool wider than the shaft above it so a player drifting
sideways still hits water. `round-and-tall.md` shows the free-fall tower with its launch pad and landing pool
(`blueprints/drop_tower.py`).

## Lava safety

| Rule | Why |
|---|---|
| Lava also goes in the last job and gets counted | it flows (about 3 blocks on the overworld) and the verification reports it as stray too |
| No wood, wool, leaves, carpet or other flammable blocks near open lava | lava sets fire to flammable blocks near it and fire spreads |
| Put lava behind glass or deep in a non-flammable basin | players and mobs walk into open lava |
| Keep lava and water apart | where they meet you get cobblestone, stone or obsidian and a hissing mess |
| Prefer the look without the risk | `magma_block`, `shroomlight`, orange stained glass over a light source, a lit `campfire` |

## Common mistakes

- Water in the same job before the walls exist → flooded interior, flowers and torches as items on the floor
  (`minecraft_cleanup` removes the items).
- A pool with a lining but the rim missing on one side, or a window block in a tank wall that is not full glass.
- A waterlogged block on the outside edge of a basin → an endless leak.
- A waterfall landing on grass → water spreads over the lawn.
- Checking with a screenshot only → use `count` and the `stray_fluids` field.
- Decorative ice under lanterns → melts into water.

## See also

`landscaping.md` · `round-and-tall.md` · `verification.md` · `block-states.md` · `interiors.md` · `troubleshooting.md`
