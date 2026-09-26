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
6. **Restore a player once.** "Give back the saved inventory" usually starts with `clear`; run it a second time on a
   player who is already home (restored on respawn, then again by the end-of-round reset) and it wipes what they have
   now. Restore only when the save file or the game tag still exists. Without a save, fall back to adventure for
   players below permission level 2 and creative for ops (`query(p, 'permission_level')`) — never hard-code creative.

The [gamekit library](gamekit.md) implements all of this (and the next section) for round-based games.

## Don't trust events alone for who is still in a game

Carpet switches scarpet event handling off while it runs the scarpet tick (every app's `__on_tick` and scheduled
calls): a death caused by your `run('damage ...')` there reaches NO app's `__on_player_dies` — yours included. (The
same `run()` inside a `/script` command is deferred until the command ends, so its events do arrive; a console
`/damage` too.) The player respawns, a respawn handler sends them home, and the round goes on with a "living" player
who is not there: their follower mobs chase them through the lobby, the visitor rule teleports them to the stands,
and the solo timer finally "wins" a round they lost.

- Route all of the app's damage through one helper that checks `query(p, 'health') <= 0` — and the
  `statistic(p, 'custom', 'deaths')` counter, because a Carpet fake player is reset to 20 health as it dies — right
  after and eliminates.
- Once a second, eliminate every participant who is offline, dead (health 0) or no longer carries the game tag.
- Make elimination idempotent (`if (!alive, return())`): the event, the helper and the sweep can all see one death.
- Anything teleported onto a player each tick (a bait mob wolves chase, a nameplate carrier) shoves them: put it on
  a team with `collisionRule never`.
- Solo rounds end with an end screen (time, personal best) and send the player home. Spectating is for rounds where
  others are still playing.

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
- For any starting mode (saved per player in a file, fallback by permission level after a lost save), use the
  `area` option of [gamekit](gamekit.md) instead.
- An admin tag (`tag <name> add game_admin`) lets builders work inside the area.
- Shape the area from one or two boxes (an L = two boxes) that cover nobody else's build.

## Keys and screens without client mods

The server only learns about a key press when the client sends a packet for it. A key nothing is bound to (M, say)
never reaches the server, and no server-side trick can detect it. What you can use (checked in the 26.2 client):

| Input | How the server sees it |
|---|---|
| W A S D, jump, sneak, sprint | the player-input packet → Key Bridge's `keys` scoreboard (`vehicles.md`), sneak also `p~'sneaking'` |
| **F** (swap hands) | `__on_player_swaps_hands(p)`, cancellable: return `'cancel'` and the items stay put. Spectators' clients never send it |
| Q (drop), hotbar scroll, use, attack | `__on_player_drops_item`, `__on_player_switches_slot`, `__on_player_uses_item`, `__on_player_attacks_entity` … |
| G (Quick Actions) | opens the dialogs in the `#minecraft:quick_actions` tag **on the client only**: the server is not told |

So a "press M for the map" feature is really "press F": cancel the swap, open the map, and tell players they can
rebind *Swap Item With Off Hand* to M in Controls. A resource pack can rename that control (`key.swapOffhand` in a
lang file), and a text component `{"keybind":"key.swapOffhand"}` shows each player the key they actually use.

**Dialogs (1.21.6+)** are real screens the server can open: `dialog show <player> <dialog>` (an id or inline SNBT)
with a title, text bodies (`plain_message`, `width` up to 1024, default 200), inputs and buttons that run commands;
Esc closes them. The body is a scrollable area between a 33 px header and a 33 px footer and is clipped to it. Good for
menus, shops and confirmations: no chest-GUI tricks needed.

The 26.x client jar is not obfuscated: `unzip` a class and run `javap -p -constants` to read exact layout numbers and
how an input is wired instead of guessing.

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

### tntrun — TNT Run: the floor vanishes under your feet
Stand on the gold JOIN pad in the lobby: a 10 s countdown starts (more players can step on), then everyone on the pad
lands on the top of four floors. Every block you stand on turns red and vanishes (0.4 s, 0.2 s after a minute; after
90 s the floors crumble by themselves). Shift in the air = double jump, 3 per game. Below the last floor you are out and
watch from the gallery. 2+ players: the last one standing wins; alone: a survival-time record. Adventure mode +
resistance during a game, the old game mode comes back after (also on reconnect). Records and a top-5 board live in
`tntrun.data/records.json`; the floors are rebuilt 5 s after every game. `tntrun.data/arena.json`:
```
{"cx": 0, "gy": -61, "cz": 0}
```
= the arena centre on the ground block. Everything else (floors at gy+30/23/16/9, the pad at cz-30, the gallery) is
derived from it, so the app fits the layout of `blueprints/tnt_run.py` only. Easiest setup: run `tnt_run.py` with
`minecraft_generate`; its last job runs `script in tntrun run setup(cx, gy, cz)`, which writes the file. Test with two
fake players on the pad and `global_allow_fake = true` (the header of `tntrun.sc` shows how).

### ferris — a Ferris wheel you ride
A wheel of block displays that turns smoothly (one cabin in 5 s, then a 4 s stop), 8 level cabins, chasing lights.
Stand on the gold BOARD pad: at the next stop you are seated in the bottom cabin; after a full turn you are let off on
the exit spot; Shift gets you off at once (put down on the exit spot, never dropped). Runs only while a real player is
within 90 blocks. `ferris.data/wheel.json`:
```
{"x": 0, "gy": -61, "z": 0}
```
= the ground block under the axle (axle at gy+14, radius 11, pad at x-3..x-2). Easiest setup: run
`blueprints/ferris_wheel.py` with `minecraft_generate`; its last job runs `script in ferris run setup(x, gy, z)`.
`script in ferris run remove()` takes the moving parts away. How it is made: displays.md, "Rotating assemblies".

### ring — Shrinking Ring, the gamekit demo
Stand on the pad north of the ring (particles mark it): 10 s countdown, everyone lands on the ring edge facing the
centre, the ring of red particles shrinks, outside it you lose health, off the arena you are out and spectate (Sneak =
next player, the last Sneak = home). Last one inside wins; alone = survival-time personal best. Nothing is built.
Setup: `script in ring run setup(x, ground_y, z)`. It needs `gamekit.scl` next to it (`clawdblock.py apps add ring`
copies it) — the library does joining, save/restore, elimination, spectating, end screen and records
([gamekit.md](gamekit.md)); the file itself is only the rule.

### cars — drivable cars
Right-click a car to get in; W/S/A/D, Space = handbrake drift, Ctrl = boost, Shift = get out; chase camera or first
person (`/cars view`). Needs the models pack (`resourcepacks/cars/`) and the Key Bridge server mod (`mods-src/keybridge/`, players' keys
in the scoreboard `keys`). Put one down with `/cars here sports red`; a parking lot goes in `cars.data/lot.json`. The
recipe (physics, camera, exit sequence, safe spawning) is in [vehicles.md](vehicles.md).

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
| "Respawn it if `entity_selector` finds none" | The entity may just be in an unloaded chunk — hundreds pile up. Respawn only with a real player near and the spot loaded, and remove extras (`rails.md`) |
| A seat / spectator spot facing the wrong way | Yaw toward a point = `atan2(-dx, dz)` (yaw 0 = south, 180 = north); compute it, don't hardcode 180 |
| Core game input is a button click | Prefer standing on a pad / crossing a line — a fake player can then test the whole round (`minigames.md`) |

## See also
[scarpet.md](scarpet.md) · [minigames.md](minigames.md) · [gamekit.md](gamekit.md) · [vehicles.md](vehicles.md) · [hud.md](hud.md) · [rails.md](rails.md) · [redstone.md](redstone.md) · [entities.md](entities.md) ·
[displays.md](displays.md) · [verification.md](verification.md) · [troubleshooting.md](troubleshooting.md)
