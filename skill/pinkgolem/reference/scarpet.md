# Scarpet cheat sheet

Scarpet is Carpet's scripting language. You use it two ways: short **expressions** that read the world (faster and
more exact than pictures), and **apps** (`.sc` files) that give builds behaviour ([game-logic.md](game-logic.md)).
Read this before writing either; the traps at the end have each cost real debugging time.

## Running expressions

| Want | Call |
|---|---|
| Read the world | `minecraft_scarpet expression:"block(0,-61,0)"` |
| Use a helper app's functions (cu, your apps) | `minecraft_scarpet app:"cu" expression:"ytop(10,20)"` |
| Same through commands | `minecraft_run_command command:"script in cu run ytop(10,20)"` |
| Plain expression as a command | `minecraft_run_command command:"script run block(0,-61,0)"` |
| Send the text exactly as written | `minecraft_scarpet raw:true expression:"..."` |

- **RCON takes one line.** `minecraft_scarpet` joins multi-line code, strips `//` comments and a leading
  `script run` for you. In `minecraft_run_command` write it on one line yourself.
- **End with the value you want:** `l=[]; ...; l`. A trailing `for(...)`, `print(...)` or `;` returns null and you
  see `= null`. `minecraft_scarpet` then adds a hint and, if the code does not change the world, re-runs it inside
  `cu` in case you meant a cu function.
- **App functions exist only inside the app:** `script in cu run ...` / `app:"cu"`. So do `read_file` and
  `write_file` — they use the app's own data folder `<app>.data/`.
- **Strings use single quotes:** `'oak_stairs[facing=east]'`. Double quotes are free for JSON and SNBT inside them:
  `run('say "hi"')`.
- One command is at most 1400 bytes. Bigger logic belongs in an app file.

## Syntax in 10 lines

```
x = 5; l = [1, 2, 3]; m = {'a' -> 1, 'b' -> 2};      // ; separates statements, the last value is the result
l:0   m:'a'   pos(p):1                                 // : indexes lists, maps, positions
l += 4;                                                // += on a list appends ONE element
if (a > 1, 'big', a == 1, 'one', 'small')              // if(cond, then, cond2, then2, ..., else)
for (l, print(_))   for (range(10), ...)   _i          // _ = current element, _i = its index
loop(5, ...)   while (cond, 400, ...)                  // while(condition, max iterations, body)
f(a, b) -> a + b;   _private(x) -> x * 2;              // define functions (in apps; _ prefix = private)
p~'name'                                               // ~ on an entity = query(p, 'name')
'oak_log' ~ '_log$'                                    // ~ on a string = regex match (null if none)
str('%s at %d %d %d', b, x, y, z)                      // printf-style formatting
```

## Functions you will use

| Function | Returns / does |
|---|---|
| `block(x,y,z)` | the block; `str(block(...))` = its name (`'oak_stairs'`) |
| `block_state(b)` / `block_state(b, 'facing')` | map of states / one state (compare as string: `str(...) == 'true'`) |
| `air(x,y,z)`, `solid(x,y,z)` | true / false |
| `block_light(x,y,z)`, `sky_light(x,y,z)` | 0-15 |
| `set(x,y,z, 'oak_stairs[facing=east]')` | places a block with states (no undo — snapshot first, see cu below) |
| `volume(x1,y1,z1,x2,y2,z2, expr)` | runs `expr` for every block in the box, `_` = the block, `pos(_)` its position |
| `top('surface', x, 0, z)` | y of the first AIR above the surface — the top block is at `top(...) - 1` |
| `biome(x,y,z)` | biome name |
| `player()`, `player('all')`, `player('Name')` | players (fake players included — check `p~'player_type'`) |
| `entity_selector('@e[type=cat,tag=zoo]')` | list of entities (loaded chunks only) |
| `entity_area('*', [cx,cy,cz], [dx,dy,dz])` | entities in a box around a centre |
| `pos(e)`, `query(e, 'pos')` | `[x, y, z]` |
| `query(e, 'has_tag', 'x')` | true / false |
| `query(e, 'nbt', 'Path')` | one NBT value; wrap in `str()` (a UUID read raw came back as zeros) |
| `query(e, 'mount')`, `e~'type'`, `e~'gamemode'`, `e~'dimension'`, `e~'motion'` | vehicle, type, mode ... |
| `modify(e, 'swing')` | arm swing (players, mannequins) |
| `modify(e, 'pos', [x,y,z])`, `modify(e, 'yaw', 90)`, `modify(e, 'remove')` | move, turn, delete |
| `spawn('text_display', [x,y,z], '{...snbt...}')` | summons and returns the entity |
| `run('command')` | runs a command as the server console |
| `schedule(ticks, '_fn', args...)` | calls a function later (apps) |
| `read_file('name', 'json')` / `write_file('name', 'json', value)` | app data file `<app>.data/name.json` (write replaces it) |
| `list_files('', 'json')`, `delete_file('name', 'json')` | app data files |
| `draw_shape('box', ticks, {'from' -> a, 'to' -> b, 'color' -> 0x55FFFFFF})` | outlines players see (no blocks) |
| `tick_time()`, `rand(n)`, `floor()`, `round()`, `sqrt()`, `sin()` / `cos()` (degrees) | maths |
| `join(',', l)`, `split(',', s)`, `slice(l, a, b)`, `keys(m)`, `pairs(m)`, `has(m, k)`, `delete(m, k)` | collections |
| `filter(l, cond)`, `map(l, expr)`, `first(l, cond)`, `sort_key(l, _:1)`, `length(l)` | with `_` as element |

Handy one-liners:
```
block_state(block(10,-60,4))                                                     full state map of one block
l=[]; for(entity_selector('@e[tag=zoo]'), p=pos(_); l+=str('%s %s %d %d %d', _~'type', _~'name', p:0,p:1,p:2)); l
l=[]; volume(0,-60,0, 10,-58,10, if(air(_), l+=pos(_))); l                       air cells in a wall box (holes)
map(player('all'), [str(_), pos(_), _~'gamemode'])                               who is where, in which mode
```

## The cu helper app

Installed with the server (`skill/pinkgolem/scripts/cu.sc`). Call as `script in cu run <fn>(...)` or
`minecraft_scarpet app:"cu"`. "Natural" below = ground, stone, sand, water, snow and wild plants.

| Call | Returns |
|---|---|
| `count(x1,y1,z1,x2,y2,z2)` | `{block: n}` for any box size, air skipped |
| `occupied(x1,y1,z1,x2,y2,z2)` | `{count, min, max, examples}` of BUILT blocks only; `count: 0` = free to build |
| `surface(x1,z1,x2,z2)` | `{min, max, avg}` ground height (top natural block, builds ignored) |
| `level(x1,z1,x2,z2, y)` | flattens: ground up to `y` (grass on top), AIR above up to `y+40` — deletes builds too |
| `snap('name', x1,y1,z1,x2,y2,z2)` | saves every block with states to `cu.data/snap_name.json` (max 300k blocks) |
| `restore('name')` | puts a snapshot back (only changed blocks) = undo for anything |
| `snaps()` / `unsnap('name')` | list / delete snapshots |
| `dark(x1,y1,z1,x2,y2,z2)` | `{spots, examples}`: floor spots with block AND sky light 0 (mobs spawn) |
| `find('block', x,y,z, r)` | positions of that block within r (max 60) |
| `show(x1,y1,z1,x2,y2,z2, 'label', seconds)` | glowing box + label for everyone (preview a site) |
| `mark(x,y,z, 'text', seconds)` | floating label at a spot |
| `ytop(x,z)` | y of the highest non-air block (builds and trees count); stand at `ytop + 1` |
| `bstr(block(x,y,z))` | `'oak_stairs[facing=east,half=bottom,...]'` |
| `verify('id', k)` | MCP only: compares `cu.data/verify_<id>_<k>.json` with the world |
| `vfluid('id', x1,y1,z1,x2,y2,z2)` | MCP only: water/lava the build did not place (`stray_fluids`, `flowing`) |
| `mon_start('id')` | MCP only: the sampler behind `minecraft_monitor` |

`level()`, `restore()` and your own `set()` calls bypass the MCP's zone guard and automatic undo: take a `snap`
first. Container and sign contents are not in snapshots.

Reading the ground: in a flat world the ground block is at y=-61 (players stand at -60); elsewhere use `standingOn.y` from
`minecraft_get_players`, `script in cu run ytop(x,z)`, or `surface()` for an area.

## Common mistakes: scarpet traps

| Trap | What happens | Do instead |
|---|---|---|
| `put(m:k, null, v)` on an accessor | replaces the entry with null | `l = m:k; l += v; m:k = l` |
| `put(m:k, 'field', v)` to set a nested field | replaces the whole entry m:k with the STRING 'field' — the record is silently gone | `m:k:'field' = v` |
| expecting events from your own tick code | Carpet turns event handling off during the scarpet tick: a player killed by `run('damage ...')` in `__on_tick` / `schedule` reaches NO app's `__on_player_dies` (inside a `/script` command the `run` is deferred, so that one does arrive) | check health and the `deaths` statistic right after your own damage, and sweep the state once a second (game-logic.md, gamekit.md) |
| `run('clear ...')` (or `kill`, `team join` …) inside a function called by a command (`script load` → `__on_start`, `script in … run`) | deferred until the command ends: a `clear` then wipes the items you gave back right after it | `for (range(41), inventory_set(p, _, 0))`, `modify(e, 'remove')` — immediate |
| a library (`.scl`) sharing the app's globals | its `global_*` are its own; it cannot call the app's functions by name; `read_file` uses the app's data folder | keep state in a map owned by the app, pass lambdas for callbacks (gamekit.md, "How a scarpet library behaves") |
| an app importing a module with its own name | "Cannot import …, too deep or too loopy" | name the library differently from every app |
| Carpet fake players in tests | dying resets health to 20 and disconnects; `/kill` only disconnects (no death); in spectator they fall out of the world unless flying; the name may come back in another case (`Kit_A` → `Kit_a`) | `statistic(p, 'custom', 'deaths')`, `/damage`, `modify(p, 'flying', true)`, always `p ~ 'name'` |
| `slice()` of an empty list | throws "/ by zero" | `if (l, slice(l, 0, min(5, length(l))), [])` |
| `list + list` | adds element by element (fails on uneven sizes) | `for (b, a += _)` |
| `...` spread | does not exist | pass the list, index it |
| a lambda that uses a local of the function that made it | lambdas don't capture: the local is null inside | capture it with `_(outer(x), e) -> ...`, pass it as an argument, or keep it in a `global_` |
| `query(e, 'tags')` | deprecated | `query(e, 'has_tag', 'x')` |
| `query(e, 'owner')` | does not exist | `data get entity <uuid> Owner`, or `query(e, 'nbt', 'Owner')` |
| `block()` right after `run('setblock ...')` in the same call | still returns the OLD block (same for `weather()`) | read it in a separate call |
| a function named `top`, `block`, `count` ... in your app | clashes with a built-in | prefix it: `_top_floor` |
| `/` | float division: `7 / 2 = 3.5` | `floor(a / b)` for grid maths |
| `str('%.2f', n)` with a whole number | fails | `str('%.2f', n * 1.0)` |
| `a \|\| b` as a default | may return true/false, not the value | `if (v == null, d, v)` (the apps' `_or(v, d)`) |
| `sin(a)`, `cos(a)` | take DEGREES | no radians conversion |
| `read_file` in `minecraft_scarpet` without `app` | returns nothing (no app, no data folder) | `app:"cu"` or `script in <app> run` |
| `execute as @e run tp @s ~ ~ ~` without `at @s` | `~` resolves at the world origin | `execute as @e[...] at @s run ...` |
| `player()` (no arguments) in a command run from the console / RCON | returns the NEAREST player, not null — a console `/money` once treated a random player as the sender | `system_info('source_entity')` (null for the console) |
| `a ~ b != null` | `~` and `!=` bind unexpectedly | `(a ~ b) != null` |
| a variable starting with `_` (`[x, _y, z] = pos(p)`) | "0 is not a variable" — `_`, `_i`, `_a` … are reserved | name it `yy`, or `q = pos(p); x = q:0` |
| `sort_key` / `slice` on an EMPTY map or list | throws ("math is wrong, null") | `if (!m, return([]))` first |
| emoji outside the Basic Multilingual Plane (💰 🏆 🎰) in texts | render as boxes | ★ ✦ ♠ ♥ $ ⏱ ▶ |
| Carpet `player X use` to test a lever | the fake player's look ray often misses small blocks | call the handler: `script in <app> run __on_player_interacts_with_block(player('X'), 'mainhand', block(x,y,z), 'south', null)` — then still ask a real player to try it |

## See also
[game-logic.md](game-logic.md) · [gamekit.md](gamekit.md) · [verification.md](verification.md) · [redstone.md](redstone.md) ·
[troubleshooting.md](troubleshooting.md) · [coordinates.md](coordinates.md)
