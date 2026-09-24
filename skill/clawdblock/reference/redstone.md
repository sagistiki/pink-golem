# Redstone, command blocks and rides

Read this before you place pistons, dust, repeaters, rails or command blocks with `setblock`. Placing redstone by
command is different from placing it by hand: nothing faces you, nothing auto-connects, and the bot cannot press a
button. The facts below were tested on Java 26.2. For logic that is easier in code, see [game-logic.md](game-logic.md).

## Block-state facts for setblock

| Block | Fact | Example |
|---|---|---|
| Repeater | `facing` points toward the INPUT | `repeater[facing=west]` takes power from the west, outputs east |
| Comparator | `facing` points toward the INPUT too | `comparator[facing=east]` reads the block to its east, outputs west |
| Piston / sticky piston | `facing` = the push direction | `sticky_piston[facing=south]` pushes toward +z |
| Redstone dust | set every connection yourself | `redstone_wire[north=side,south=side,east=none,west=none,power=0]`; `up` on the side where it climbs a block |
| Copper bulb | a T flip-flop: each rising edge toggles `lit` | `waxed_copper_bulb[lit=true]` (waxed = never oxidises) |
| Button / lever | strongly powers the block it is attached to | `stone_button[face=wall,facing=north]` faces north, so it hangs on the block SOUTH of it |
| Rails | give `shape` explicitly | `rail[shape=north_south]`, `powered_rail[shape=east_west,powered=false]` |

- **Pistons:** place them retracted, with the block to move right in front of them. Powered, it pushes it; unpowered,
  a sticky piston pulls it back.
- **Dust** powers the block underneath each dust and the block it points into. A powered block powers adjacent
  pistons, lamps, note blocks and repeaters.
- **Copper bulb:** a comparator behind it reads 15 when lit and 0 when unlit. It keeps its state, so a door built on
  it stays open or closed until toggled again.
- **Quasi-connectivity works:** a piston is also powered when the block ABOVE it would be powered. In a 2-high
  piston column only the top piston needs power; the lower one follows because the moving upper piston updates it.
- `setblock`/`fill` of a block that is already exactly like that answers "Could not set the block": harmless.
- Pumpkins and melons break when a piston pushes them.

## Testing without a player

The bot cannot press buttons. Instead, swap one block on the input path for a `redstone_block` for about 0.4 s, then
put the original back — one rising edge, exactly like a press:

```
minecraft_run_command commands:["setblock X Y Z redstone_block", "setblock X Y Z polished_blackstone_bricks"] pace_ms:400
```

Then check the result: `minecraft_inspect pos:[bulb]` (is `lit` what you expect?) and the door cells, or record the
whole sequence with `minecraft_monitor blocks:[[x,y,z,'bulb'],[x,y,z,'door']] every_ticks:2 seconds:5` while you swap.

## A 2-high hidden piston door

A 2-wide, 2-high opening in a wall that runs north-south (along z) at `x = W`. `G` = the ground block (flat world:
y=-61; elsewhere `standingOn.y` from `minecraft_get_players` or `script in cu run ytop(x,z)`). `Z` = the first cell.

```
side view along the wall (x = W), z grows to the right
 y=G+4   dust  dust  dust  dust  dust  dust        ← hidden: cover it with one more layer of wall/ceiling
 y=G+3   wall  wall  wall  wall  wall  wall        ← the dust powers these; the end ones power the top pistons
 y=G+2   SP→S  door  ....  ....  door  SP→N
 y=G+1   SP→S  door  ....  ....  door  SP→N
 z=      Z     Z+1   Z+2   Z+3   Z+4   Z+5
```

| Cells | Block |
|---|---|
| `W, G+1..G+2, Z` | `sticky_piston[facing=south]` (2 high) |
| `W, G+1..G+2, Z+5` | `sticky_piston[facing=north]` (2 high) |
| `W, G+1..G+2, Z+1` and `Z+4` | the door blocks — the same block as the wall so the closed door is invisible |
| `W, G+1..G+2, Z+2..Z+3` | air (the opening) |
| `W, G+3, Z..Z+5` | wall blocks (lintel) |
| `W, G+4, Z..Z+5` | dust line, connected north-south, covered by the next layer |

Control: `button → the block it is on → repeater (facing toward that block) → dust → waxed_copper_bulb`, and
`bulb → comparator (facing toward the bulb) → dust line on top of the wall`. Bulb lit = pistons extended = door
CLOSED; every press toggles it. A second button on the other side feeds its own dust path into the same bulb. A
button on a wall strongly powers the block it sits on, so a repeater behind that block carries the signal through
the wall.

If it gets out of sync: `setblock <bulb> waxed_copper_bulb[lit=true]` closes the door, `lit=false` opens it.

Checklist after building: swap-test it twice (open, close), `minecraft_inspect` all 6 faces of every piston and
dust cell from the outside, and walk the bot through the open door (`minecraft_bot action:walk_to`).

## Rules

- **Keep every component 1 block away from anything it must not touch.** A dust line next to a lamp, note block or
  another piston will power it too.
- **Hide mechanisms behind decoration** (a lintel, speakers, a bookshelf wall, a thicker wall), never behind thin air.
  Check all 6 faces of every piston and dust cell from the outside and cover outer corners with terrain.
- **Prefer a toggle (copper bulb) over a timer** unless it must close by itself. Monostable loops fed back into the
  bulb break when someone double-presses.
- **No repeating command blocks that summon things** and no clocks that spawn entities: entity spam is the classic
  way to lag a server into a watchdog crash.

## When a scarpet app is better

`scarpet-apps/secret_door.sc` swaps blocks instead of moving them: any wall thickness, any shape of passage, nothing
to hide, optional auto-close, and it cannot get out of sync (`set_door` forces a state). Use redstone when the
players want to see or tinker with a real mechanism; use the app when the passage just has to work. Same for
buttons that do more than one thing: `vendor.sc` (see below) and your own apps poll the button's `powered` state.

## Command blocks for simple buttons

A free-item button on a counter:

1. `stone_button[face=wall,facing=north]` on the counter's front face (the button strongly powers the counter block).
2. `command_block[facing=up]` right under that counter block, with its command:
   ```
   setblock X Y Z command_block[facing=up]{Command:'execute as @p[distance=..5] at @s run give @s cookie[custom_name={"text":"Ice cream","italic":false}] 1'}
   ```
   Potions: `potion[potion_contents={potion:"minecraft:swiftness"}]`.
3. Several commands per press: an impulse `command_block[facing=down]` with `chain_command_block[facing=down]{auto:1b,Command:'...'}`
   blocks below it.
4. Test: put a `redstone_block` next to the command block for a moment (then remove it) and read the result with
   `data get block X Y Z LastOutput`.

Use **`vendor.sc`** instead when the button should do more than hand out one item: a random named menu, drinks with
effects, a bartender who turns and serves, cooldowns, several stands from one JSON file ([game-logic.md](game-logic.md)).

## Minecarts and rides

| Fact | Detail |
|---|---|
| Speed | a ridden cart tops out at 0.4 blocks/tick (8 blocks/s) |
| Lift hill | every rail a `powered_rail` on a `redstone_block` support: climbs at full speed |
| Flat track | one booster (powered rail on a redstone block) every 10-15 blocks |
| Stopped cart | a cart standing still on a powered rail does NOT start by itself: give it a push |
| Brakes | unpowered powered rails; 6 of them stop a full-speed cart in about 2 blocks |
| Detector rail | strongly powers the block it sits on: a command block 2 below the rail fires, lamps beside that block flash, dust under it is powered |
| Spacing | keep detectors, boosters and command-block chains at least 3 cells apart |
| Curves | detector and powered rails cannot be curves |

**Station:** 6 brake rails + a GO button → impulse command block `setblock <under a brake> redstone_block` → chain
command block `execute positioned <brake> as @e[type=minecart,distance=..4] run data merge entity @s {Motion:[0.25d,0d,0d]}`
(set the Motion axis to the track direction). A detector rail just after the station puts the original support block
back, so the brakes work again for the next arrival.

**Automatic door on a track:** a redstone torch on a block S under a 2-high sticky-piston stack keeps the door closed
(torch → lower piston; the torch strongly powers the block above it → upper piston). Dust from a chain of detector
rails (every 3 blocks, starting 12 blocks before the door) into S turns the torch off: the door opens as the cart
arrives and slams about 1 s after it passes.

**Track building:** rails placed with an explicit `shape` keep it as long as the track never runs right next to
itself; verify every cell afterwards (block AND shape) with `minecraft_inspect`.

**Test ride with the bot:** look at the cart, `minecraft_bot action:raw raw:"mount"`, confirm with
`minecraft_scarpet expression:"query(player('<bot>'), 'mount')"`, launch by swapping the GO button's block for a
redstone block for ~0.4 s, and record the ride with `minecraft_monitor track:['<bot>'] every_ticks:10 seconds:40`.
Pair it with `blocks` for the door cells to see whether the door opened in time.

## Common mistakes

- Setting a repeater or comparator `facing` toward the OUTPUT: it points toward the input.
- Placing dust without explicit connections: it will not turn toward the next component.
- Powering only the LOWER piston of a 2-high column: the upper one stays retracted. Power the top one; the lower
  one follows by quasi-connectivity.
- Dust or a powered block touching a lamp, note block or piston that should stay quiet: keep 1 block of space.
- Declaring a door done without pressing it twice (open AND close) and walking through it.

## See also
[game-logic.md](game-logic.md) · [block-states.md](block-states.md) · [verification.md](verification.md) ·
[scarpet.md](scarpet.md) · [troubleshooting.md](troubleshooting.md)
