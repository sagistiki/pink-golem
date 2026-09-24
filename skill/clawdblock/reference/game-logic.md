# Game logic: builds that DO things

Read this when a build should react to players: a button that serves drinks, a secret passage, a race with a record
board, a launch pad, a welcome show. All of it is done with **scarpet apps** (Carpet's scripting language) that run
inside the server. For the language itself see [scarpet.md](scarpet.md); for wiring see [redstone.md](redstone.md).

## Where apps live and how to start them

| Step | How |
|---|---|
| App files | `<server folder>/<world>/scripts/<app>.sc` (default: `server/world/scripts/` in the ClawdBlock folder) |
| Install a bundled app | `python3 clawdblock.py apps add vendor race` (copies from `scarpet-apps/`, loads it if the server runs) |
| List / remove | `python3 clawdblock.py apps list` · `python3 clawdblock.py apps remove vendor` (unloads it too) |
| Your own app | write `<app>.sc` into the scripts folder (directly, or from a generator run with `minecraft_generate`) |
| Load or reload | `script load <app>` with `minecraft_run_command` |
| Stop it | `script unload <app>` |
| Call a function | `script in <app> run reload()` |
| App settings | `<scripts>/<app>.data/<name>.json`, read inside the app with `read_file('<name>', 'json')` |

`__config() -> {'stay_loaded' -> true, 'scope' -> 'global'}` makes an app load again by itself when the server starts,
and gives it one shared state for all players (not one copy per player).

The core apps `cu`, `helpers` and `bubble` are installed by setup; the MCP needs them (checks, undo, builder animation,
speech bubbles). Never unload them.

## App skeleton

```
__config() -> {'stay_loaded' -> true, 'scope' -> 'global'};

global_allow_fake = false;      // true only while you test with your bot
global_items = [];              // loaded from <app>.data/items.json
global_prev = {};               // last `powered` state per trigger (rising-edge detection)

reload() -> (
    d = read_file('items', 'json');
    global_items = if (d, d, []);
    str('%d item(s)', length(global_items))      // end with a value: it is what `script in` prints
);
__on_start() -> reload();                         // runs on every load AND every reload

__on_tick() -> (
    if (tick_time() % 2 != 0 || !global_items, return());     // throttle: 20 ticks = 1 second
    for (global_items,
        c = _:'button'; k = str(c);
        on = str(block_state(block(c:0, c:1, c:2), 'powered')) == 'true';
        if (on && !global_prev:k, _act(_));        // act once per press, not every tick it stays powered
        global_prev:k = on
    )
);

_act(item) -> run(str('say pressed %s', item:'name'));

__on_player_connects(p) -> if (query(p, 'player_type') != 'fake', schedule(40, '_hello', p~'name'));
_hello(n) -> if (player(n), run(str('title %s actionbar {"text":"Welcome, %s"}', n, n)));
__on_player_disconnects(p, reason) -> null;       // forget per-player state here (race.sc ends the run)
```

Rules and their reasons:
- **Throttle `__on_tick`.** It runs 20 times a second; check buttons every 2 ticks, zones every 5-10, boards every 20.
- **Poll buttons, levers and plates by their `powered` state every 2 ticks** instead of relying on interaction events.
  Polling works for every client; `__on_player_swings_hand` does not even fire for server-side swings.
- **Detect the rising edge** (off to on) and remember the previous state per trigger, or one press fires 10 times.
- **`schedule(ticks, '_fn', args...)`** for delays; a join greeting waits ~40 ticks so the client has finished loading.
- **Skip fake players** (`query(p, 'player_type') == 'fake'`) in greetings and games: your bot and the helper
  builders are fake players. Let them in only through a `global_allow_fake` switch while testing.
- Private helpers start with `_`; public ones (`reload`, `set_door`, `show`) are what you call with `script in`.
- **One-target commands** (`data merge entity`, `rotate`) accept ONE entity: use
  `execute as @e[tag=x] run data merge entity @s {...}` and `execute as @e[tag=x] at @s run tp @s ~ ~ ~ <yaw> 0`.
- `run('<command>')` runs as the server console, so `execute as <player> run warp tp <warp>` works for every player,
  and `ride <player> mount <entity>` seats someone in a boat or minecart.

## Config files

Apps read their settings from JSON so you can change a build's logic without touching code:

1. **Generator (best for builds):** a Python generator run with `minecraft_generate` gets the environment variable
   `CLAWDBLOCK_CU_DATA` = `<scripts>/cu.data`; its parent folder is the scripts folder. Write
   `<scripts>/<app>.data/<name>.json` there, merge with entries already in the file (other builds use the same app),
   and add `script load <app>` or `script in <app> run reload()` as the last job command. `blueprints/drop_tower.py`
   does exactly this for the launch pad.
2. **Direct file access:** write the same file yourself, then `script in <app> run reload()`.
3. **Tiny configs from inside the app:** `script in secret_door run write_file('doors', 'json', [{'name' -> 'den',
   'trigger' -> [5,-60,3], 'cells' -> [[6,-60,4],[6,-59,4]], 'closed' -> 'bookshelf', 'auto_close' -> 0}]); reload()`.
   One RCON command is at most 1400 bytes, so this only fits small files — and it REPLACES the file.

Coordinates in config files are absolute block positions. Keep entries for other builds when you edit a file.

## Reload safety — people play while you work

`script load <app>` re-runs `__on_start` and forgets every global. Players often test a build before you say it is
done, so a careless reload can break a game under them (a race reload once killed the boats mid-race).

1. **Check the app's state before reloading or resetting anything:** `script in race run global_run` (who is racing),
   `script in <app> run global_mode`, or who stands in the game area. Wait until nobody uses it.
2. **Anything that must survive a reload goes into player TAGS or files, never only a global.** "Which players did I
   switch to adventure" in a global is lost on reload and those players stay stuck in adventure; a tag
   (`tag <player> add game_managed`) survives reloads and restarts. Records go through `write_file`.
3. **`__on_start` cleans up its own world state:** kill the app's own tagged entities, dismount riders and send them
   somewhere safe, reset gates and lights. Then a reload always starts from a known state.
4. **A button left `powered=true` fires again after every reload** (the app sees a new rising edge). Reset test
   buttons to `powered=false`.
5. `reload()` functions (all bundled apps have one) re-read the JSON without a full `script load`.

## Game areas that switch game mode

Parkour, races and mazes need adventure mode (no breaking blocks). Pattern: a box switches players to adventure on the
way in and back on the way out, with the state kept in a tag.

```
global_box = [10, -61, 10, 40, -40, 60];          // x1,y1,z1,x2,y2,z2 (inclusive, x1<=x2 ...)
_in(q) -> (b = global_box; q:0 >= b:0 && q:0 < b:3 + 1 && q:1 >= b:1 && q:1 < b:4 + 1 && q:2 >= b:2 && q:2 < b:5 + 1);
__on_tick() -> (
    if (tick_time() % 10 != 0, return());
    for (player('all'),
        p = _; n = p~'name';
        if (p~'player_type' != 'fake' && !query(p, 'has_tag', 'game_admin'),
            m = query(p, 'has_tag', 'game_managed'); inside = _in(pos(p));
            if (inside && !m && p~'gamemode' == 'creative',
                run('gamemode adventure ' + n); run('tag ' + n + ' add game_managed'),
            !inside && m,
                run('gamemode creative ' + n); run('tag ' + n + ' remove game_managed')
            )
        )
    )
);
```

- Only players who were in creative are switched, so a survival player never comes out in creative.
- An admin tag (`tag <name> add game_admin`) lets builders work inside the area.
- Shape the area from one or two boxes (an L = two boxes) that cover nobody else's build.

## Testing with the bot

Your bot cannot click buttons, so test like this:

1. `script in <app> run global_allow_fake = true` — the app now accepts fake players.
2. Put the bot where a player would stand (`minecraft_bot action:walk_to`, or `tp`).
3. **Press a button:** `setblock x y z stone_button[face=wall,facing=north,powered=true]` (repeat its real `face` and
   `facing`), and in the NEXT call `setblock ... powered=false`. The app sees one rising edge.
4. Watch it: `minecraft_monitor` with the door cells or the bot in `blocks` / `track`, `minecraft_get_chat` for
   titles and messages, `minecraft_inspect` for the result.
5. Clean up: `global_allow_fake = false`, button unpowered, delete test records but keep real players' records.

Fake players cannot steer boats: test a boat course with a throwaway app that moves the boat along waypoints with
`modify(boat, 'pos', [x, y, z])`, then unload and delete it. `minecraft_wait_for_chat timeout_seconds:N` is a clean
N-second pause while an in-game countdown runs.

## The bundled apps (`scarpet-apps/`)

### vendor — button stands that serve things
Pressing a stand's button gives the nearest real player (within 4.5 blocks, 3 up or down) a random named item from the
menu, plus the potion effect; the NPC with `npc_tag` turns to them and swings; a sound and particles play. 1.5 s
cooldown per player. `vendor.data/stands.json`:
```
[{"name": "beach bar", "button": [x,y,z], "npc_tag": "bartender", "menu": [
   {"name": "Mojito", "color": "green", "item": "potion", "potion_color": 5635925, "effect": "speed", "seconds": 60},
   {"name": "Ice cream", "color": "white", "item": "cookie"}]}]
```
Setup: counter with a button on its front face, an NPC (mannequin or villager) tagged `bartender` behind it, write the
stand into `stands.json`, `apps add vendor` (or `script in vendor run reload()`), test with the bot.

### secret_door — hidden passages without wiring
Each rising edge of the trigger's `powered` state toggles the `cells` between `closed` and air, with a piston sound and
dust. `auto_close` = ticks until it closes by itself (0 = stays open). `secret_door.data/doors.json`:
```
[{"name": "library", "trigger": [x,y,z], "cells": [[x,y,z], ...], "closed": "bookshelf", "auto_close": 100}]
```
The trigger can be a button, lever or pressure plate anywhere; the wall can be any thickness. Force a state with
`script in secret_door run set_door('library', true)` (`false` closes). After a reload the app assumes every door is
closed, so close open doors with `set_door(name, false)` first.

### race — timed courses with a record board
Walk through the start box, the timer runs on the action bar, pass every checkpoint in order, reach the finish box: time, sound, and the
top-5 board updates. Below `fall_y` you go back to your last checkpoint. Records survive restarts
(`race.data/records.json`). `race.data/courses.json`:
```
[{"name": "sky parkour", "start": [x1,y1,z1,x2,y2,z2], "checkpoints": [[x1,y1,z1,x2,y2,z2], ...],
  "finish": [x1,y1,z1,x2,y2,z2], "board": [x,y,z], "fall_y": -58}]
```
Boxes are inclusive block boxes tested against the player's feet, so include the feet level: one above the ground
block (flat world: the ground block is y=-61, feet y=-60; elsewhere read `standingOn.y` from `minecraft_get_players`).
Boards are `text_display` entities tagged `race_board_<index in the list>`: add new courses at the END of the list.
Works for foot, parkour, horse and boat tracks. Boats are 1.375 blocks wide: a blocking block must start more than
0.69 from the boat's centre or the boat already overlaps it and passes through. Hold boats with barrier gates, never
by teleporting a ridden boat every tick (it feels like crashing).

### launchpad — fly up a tower, free-fall into a pool
Step on the pad and levitation lifts you up the shaft (particles, sound); at the top you are teleported onto the roof
facing the hole; jump in, watch the falling height on the action bar, and get a splash and "N m in T s" in the pool.
`launchpad.data/pads.json` (written by `blueprints/drop_tower.py`):
```
[{"name": "drop1", "pad": [x,y,z], "top": [x,y,z,yaw,pitch], "top_y": 70, "hole": [cx,cz,r], "pool": [cx,cz,r,y]}]
```
`pad` = the plate cell (feet level), `top` = where you arrive on the roof, `top_y` = the roof's feet level, `hole` =
centre and radius of the roof opening, `pool` = centre, radius and the y of the top water layer. Two water blocks
deep stop any fall. Easiest setup: run `drop_tower.py` with `minecraft_generate`; it builds the tower, writes the pad
and loads the app.

### welcome — a greeting for real players
Title with the player's name, a colour shimmer on the action bar, a ring of particles, a chime. Bots and helpers get
nothing. No config file: edit `global_title` and `global_colors` in `welcome.sc`, then `script load welcome`.

### fireworks — a show around a point
`script in fireworks run show(x, y, z, seconds)` (from the AI, a command block, or another app's `run()`). Rockets
rise in waves every 2 s from a ring 3-8 blocks around the point, ending with a finale. One show at a time. Keep the
point clear of roofs and 6+ blocks from people.

## Common mistakes

| Mistake | Fix |
|---|---|
| Reloading an app while someone plays it | Check its state first; wait |
| Mode switch remembered only in a global | Player tag |
| Function name equal to a built-in (`top`, `block`) | Prefix it: `_top_floor` |
| Button stays powered after a test | `setblock ... powered=false` in the next call |
| Editing JSON but not reloading | `script in <app> run reload()` |
| Entity-spawning loop in `__on_tick` | Spawn once, tag it, move it with `modify`; unbounded spawning lags or crashes the server |

## See also
[scarpet.md](scarpet.md) · [redstone.md](redstone.md) · [entities.md](entities.md) · [displays.md](displays.md) ·
[verification.md](verification.md) · [troubleshooting.md](troubleshooting.md)
