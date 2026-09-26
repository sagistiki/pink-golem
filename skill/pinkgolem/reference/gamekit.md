# gamekit — the shared lifecycle of a minigame round (a scarpet library)

Every round-based game needs the same dull, bug-prone parts: a join zone with a countdown, saving and restoring
inventories and game modes, knowing who is still in, spectating, an end screen, records, surviving a reload.
[`scarpet-apps/gamekit.scl`](../../../scarpet-apps/gamekit.scl) does all of it, tested end to end;
[`scarpet-apps/ring.sc`](../../../scarpet-apps/ring.sc) is a complete demo game in ~60 lines of rules. Read
[minigames.md](minigames.md) for game design; this page is the library.

## How a scarpet library behaves (tested on Carpet 26.2)

A `.scl` file is loaded with `import('<name>', 'fn1', 'fn2', …)` from an app. It is not an app, and it is not a
copy-paste either:

| Fact | Consequence |
|---|---|
| The library's `global_*` variables are its own — one copy per importing app, kept between calls | the app's `global_x` and the library's `global_x` are two different variables |
| Importing a `global_*` name gives the app a copy taken at import time | not a live link: changes on either side are not seen by the other |
| A library function cannot call the app's functions by name (`Function '_x' is not defined nor visible by its name in the imported module`) | pass lambdas: `'on' -> {'start' -> _(K, names) -> _place(names)}` — a lambda runs in the APP's scope (app globals and functions work) |
| Maps and lists passed to a library function are the same objects | keep all state in one map owned by the app (`global_K`) and let the library change it |
| `schedule(t, '_fn', …)` inside the library finds the library's `_fn` | the library can time its own work |
| `read_file` / `write_file` in the library use the HOST app's data folder; `system_info('app_name')` is the host app | save files land in `<app>.data/` |
| Names starting with `_` can be imported | private helpers stay unimported unless you need them |
| `import('lib')` without names imports nothing and returns the list of symbols | use it to see what a library offers |
| An app that imports a module with its own name imports itself | "Cannot import …, either your imports are too deep or too loopy" |

## Wiring it into a game

```
__config() -> {'stay_loaded' -> true, 'scope' -> 'global'};
import('gamekit', 'gk_new', 'gk_boot', 'gk_tick', 'gk_on_connect', 'gk_on_disconnect', 'gk_on_death', 'gk_on_respawn',
  'gk_alive', 'gk_damage', 'gk_eliminate', 'gk_secs', 'gk_yaw_to', 'gk_status');

global_K = gk_new({'id' -> 'ring', 'zone' -> [x1, y1, z1, x2, y2, z2], 'lobby' -> 10, 'home' -> [x, y, z, yaw, 0],
  'view' -> [x, y, z], 'focus' -> [cx, cy, cz],
  'on' -> {'start' -> _(K, names) -> _place(names), 'out' -> _(K, n, why) -> _boom(n)}});
__on_start() -> gk_boot(global_K);
__on_tick() -> (gk_tick(global_K); if (global_K:'state' == 'play', _rules()));
__on_player_connects(p) -> gk_on_connect(global_K, p);
__on_player_disconnects(p, r) -> gk_on_disconnect(global_K, p);
__on_player_dies(p) -> gk_on_death(global_K, p);
__on_player_respawns(p) -> gk_on_respawn(global_K, p);
```

Your code only places players at the start and applies the game's rule: `gk_damage(K, n, 4, 'minecraft:generic')`
for damage, `gk_eliminate(K, n, 'out')` for "fell off / left the arena", `gk_score(K, n, v)` if the score is not the
survival time, `gk_finish(K, winner)` if the round does not end with the last one standing.

## Config (`gk_new`)

| Key | Default | Meaning |
|---|---|---|
| `id` | required | tags `<id>_in` / `<id>_spec` / `<id>_q`, files `gk_<id>_<uuid>.json`, `gk_<id>_records.json`, bossbar `gk:<id>` |
| `zone` | — | join box `[x1,y1,z1,x2,y2,z2]` (block coordinates, inclusive) |
| `lobby` / `min` / `max` | 10 / 1 / 16 | countdown seconds, players needed to start, places |
| `home` | the saved position | where everyone goes back `[x,y,z,yaw,pitch]` |
| `view`, `focus` | — | spectator seat and the point it faces (yaw/pitch computed, never hard-coded) |
| `mode` | `adventure` | game mode during the round |
| `keep_inv` | false | false = inventories are saved and cleared at the start |
| `last_standing` | true | end the round when one player is left (else you call `gk_finish`) |
| `better`, `fmt` | `high`, `time` | records: higher/lower is better; shown as `m:ss`, `dec` or a number |
| `end_ticks` | 100 | how long the end screen shows before everyone goes home (solo: at once) |
| `area`, `admin_tag` | — | optional game-mode area (parkour style): inside → `mode`, outside → the saved mode back |
| `allow_fake` | false | let Carpet fake players join (tests) |
| `text` | English | override any message (`'prefix' -> '[Ring] '`, …) |
| `on` | {} | callbacks: `start _(K, names)`, `out _(K, n, why)`, `end _(K, result)`, `home _(K, names)` — exact arities |

## What each part does, and the bug it prevents

| Part | Behaviour | Why |
|---|---|---|
| **Joining** | standing in `zone` joins the queue; a countdown bossbar + titles for the last 3 s; walking OUT of the zone leaves the queue; an empty queue cancels | a player who walked away used to stay entered |
| **Save** `gk_save` | inventory (41 slots with components), game mode, position, dimension → `gk_<id>_<uuid>.json`; tag `<id>_in`; never overwrites an unrestored save | a reload, a crash or a disconnect must never lose things |
| **Restore once** `gk_restore` | only while a save file or a game tag exists; stop spectating, clear + give back the inventory, mode, health, tags off, delete the file, teleport home 2 ticks later | a second restore of someone already home wiped their inventory |
| **Mode fallback** `gk_fallback_mode` | no save → adventure below permission level 2, creative for ops | never hard-code creative (non-admins now default to adventure) |
| **Participants** | `K:'pl'` registry; `gk_eliminate` is idempotent | the event, the damage helper and the sweep can all see the same death |
| **The sweep** | once a second: offline → `quit`, health ≤ 0 → `died`, lost the tag → `left` | nothing else is reliable (next row) |
| **Damage helper** `gk_damage` | runs `damage`, then compares health AND the `deaths` statistic | events are not delivered while the scarpet tick runs; a Carpet fake player is reset to 20 health as it dies |
| **Spectating** | only while others still play; seat facing the arena; Sneak (on release) cycles players → the seat → home | vanilla uses Shift to stop spectating an entity; switching on release does not fight it |
| **Solo** | the round ends straight to the end screen and home — no spectating | nobody is left to watch |
| **End screen** | title (win / game over) + subtitle (result · new or old personal best), sound, records file, `gk_top(K, 'best', 5)` / `gk_top(K, 'wins', 5)` for a board | |
| **Followers** `gk_nocollide(K, e)` | puts the entity on `<id>_nc` with `collisionRule never` | a bait mob teleported onto a player every tick shoved them around |
| **Reload** `gk_boot` | whoever still has a tag or a save goes home with their things; queue tags cleared; bossbar + team created | `script load` forgets every global; tags and files survive |
| **Late join** `gk_on_connect` | 1 s after joining: restore if tagged/saved and not in a live round | the disconnect already counted as `quit`; their things come back when they return |
| **Yaw** `gk_yaw_to(a, b)` | `atan2(-dx, dz)` (0 = south, 90 = west, 180 = north) | a seat hard-coded to 180 faced the wall |

`gk_status(K)` = state, queue, alive, order out, spectators, seconds, last result; `K:'log'` holds the last 40
events with tick numbers — read both when testing.

## Testing a game built on it

With `allow_fake`, spawn fake players on the pad and play the round with teleports. What to know about Carpet fake
players (each one cost a failed test):

- A fake player that dies disconnects at once, and its health is reset to 20 first — check deaths with the
  `statistic(p, 'custom', 'deaths')` counter, not health. It rejoins with `/player X spawn` (late-join test).
- `/kill <fake>` does not kill it: it just disconnects ("lost connection: Killed"), no death, no event.
- A fake player switched to spectator falls out of the world unless you `modify(p, 'flying', true)`.
- A freshly joined player is invulnerable for ~3 s ("Target is invulnerable").
- The name you spawn may come back in another case (`Kit_A` → `Kit_a`): always use `p ~ 'name'`.
- Fake players send no Shift/keys by themselves: `/player X sneak` / `unsneak` drive the spectator cycle.

## Migrating an existing game

Replace, in this order: the join pad logic → `zone` + `gk_tick`; the save/restore code and its restore file →
`gk_save`/`gk_restore` (keep the old file readable once so nobody loses things); the alive map → `K:'pl'` with
`gk_eliminate`; every `run('damage …')` → `gk_damage`; the spectator code → `gk_spectate`; the records file →
`gk_finish` + `gk_top`; `__on_start` / join / leave handlers → the `gk_on_*` calls. Keep the game's own rules.

## See also
[minigames.md](minigames.md) · [game-logic.md](game-logic.md) · [scarpet.md](scarpet.md) · [hud.md](hud.md) (a timer or status for the round)
