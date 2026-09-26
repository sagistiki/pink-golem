# Minigames — rounds, joining, fairness, and testing that proves it works

A minigame is a build plus a scarpet app that runs rounds. Players forgive a plain arena; they do not forgive a game
that "doesn't work". Design for reliable input first, then test the whole round before you announce it.

## Join by standing, not by clicking

The most reliable input is **where a player is**: stand on a pad to join, fall below a floor to be out, reach a
finish line to win. The app polls positions every few ticks (`for (player('all'), …)` + a box test), so there is no
click event to miss, no button that stays powered, and — most important — **a fake player can play a whole round**:
it stands on the pad, gets teleported, stands still, falls, is eliminated. Buttons and levers are fine for extras
(a chip size, a menu), but not for the core loop.

## A round, step by step

The library [`gamekit.scl`](gamekit.md) does steps 1-3 and 5-6 for you (join zone, countdown, save/restore, elimination,
spectating, end screen, records, reload safety); [`scarpet-apps/ring.sc`](../../../scarpet-apps/ring.sc) is a whole game
built on it. Show a round timer or status with the [HUD toolkit](hud.md).


1. **Lobby** — a pad (gold block border), a canopy, the rules on a text display, a records board.
2. **Countdown** — starts when the first player steps on the pad (10 s), more can join, it cancels if the pad empties.
   A boss bar for everyone near + big numbers for the last 3 seconds.
3. **Start** — remember each player's game mode, switch them to **adventure** (no breaking, no flying) with
   `effect give <p> minecraft:resistance infinite 255 true` if falls are part of the game, then teleport them in.
   Give a short grace period before the danger starts.
4. **Play** — each tick for each alive player: out-of-bounds check, the game rule, abilities (e.g. Shift in the air
   = a double jump, counted per player). Ramp up: faster after 60 s, something new after 90 s.
5. **Out** — restore the game mode, clear the effect, teleport to a viewing gallery, announce "X is out, N left".
6. **End** — last one standing wins (2+ players) / survival time record (solo). Titles, fireworks, records file.
   `schedule(100, '_reset')` **before** any display update, so a display error can never leave the game stuck.
7. **Reset** — rebuild the arena from code (the app must be able to rebuild it alone, with a little randomness so
   rounds differ), back to idle.

Also: a player who disconnects mid-round is remembered, and `__on_player_connects` restores their game mode.

## Testing it end to end

1. `script in <app> run global_allow_fake = true`
2. Spawn two fake players on the pad: `player Test_Runner spawn at <pad x y z>` (reuse the same names — a new name
   is looked up at Mojang on first join and freezes the server for a few seconds).
3. `minecraft_wait until:"global_state == 'playing'" app:<app>` → then `until:"global_state == 'idle'"`.
4. Read the result: `script in <app> run [global_state, global_rec]`, the players' game modes and positions, the board.
5. Clean up: kill the fake players, `global_allow_fake = false`, reset the records the test created.
6. **Then ask a real player to try one round** (`minecraft_wait reply_from:<name> ask:"…"`) before you announce it.

## TNT Run (bundled)

`skill/pinkgolem/blueprints/tnt_run.py --at <centre x,ground y,centre z>` builds a round arena (four coloured floors
over TNT, glass wall, water pit, lobby with a join pad to the north, a viewing gallery) and loads
`scarpet-apps/tntrun.sc` with `setup(x, y, z)`. Every block a runner stands on turns red and vanishes; Shift in the air
= double jump (3 per round); faster after 60 s, crumbling after 90 s; last one standing wins, solo = time record.

## See also
[gamekit.md](gamekit.md) · [hud.md](hud.md) · [game-logic.md](game-logic.md) · [scarpet.md](scarpet.md) · [rails.md](rails.md) · [entities.md](entities.md) · [displays.md](displays.md)
