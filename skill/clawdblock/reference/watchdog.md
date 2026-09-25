# Watchdog: finding what lags a server

A slow server has one of a few causes, and each leaves a fingerprint. This page is how to read them, with the
`minecraft_watchdog` tool and the `watchdog.sc` app that does the watching when no AI is connected.

## The one-minute version

1. `minecraft_watchdog` (action `status`): is it really lagging? Look at `tick.avg_ms`, `p95_ms`, `p99_ms` and
   `last_minute`. Under 30 ms is healthy, 30-50 ms is busy but still 20 TPS, over 50 ms the server falls behind.
   A high P99 with a low average = short spikes (a freeze now and then), not steady lag.
2. `minecraft_watchdog action:heavy`: what is loaded, where, and who owns it. Read `culprit` first, then `stacked`,
   `hottest_chunks`, `rises_since_quiet_census`.
3. Nothing in the entities? `action:heavy threads:true` shows which JVM threads burn CPU (the game tick, garbage
   collection, map rendering, chunk generation).
4. `action:incidents` shows what the app saw while nobody was looking (lag, freezes, leaks, junk, disk alerts).
5. Fix the cause in the app or generator that made it. Remove things only when you know what they are and the
   owner agrees. Tell the player in one line what it was.

## Measuring tick time

| Source | What you get | Notes |
|---|---|---|
| `tick query` (vanilla, over RCON) | average, P50, P95, P99 of the last 100 ticks | works everywhere; `minecraft_watchdog status` parses it |
| `script run system_info('server_last_tick_times')` | the last 100 tick times in ms, newest first | what `watchdog.sc` samples once a second |
| `spark tps` / `spark health` | rich numbers | **no text comes back over RCON** (spark answers asynchronously). `spark health` also **uploads a report** to spark.lucko.me — ask the owner first |
| `python3 clawdblock.py status` | a line of tick times | quick look from a terminal |

**Pause when empty.** With `pause-when-empty-seconds` in server.properties the server stops ticking a minute after
the last player leaves ("Server empty for 60 seconds, pausing" in the log). Tick numbers then describe the time
before the pause; `status` says `paused: true`. Fake players (bots) count as players and keep it ticking.

## The watchdog app (`scarpet-apps/watchdog.sc`)

Installed into the world by the first `minecraft_watchdog` call (or `python3 clawdblock.py apps add watchdog`).

- **Every second** it reads the last 20 tick times. That is the whole steady cost: a few microseconds per second.
- **An incident** opens when the mean tick over `lag_seconds` (15) stays above `lag_mspt` (45 ms): one entity
  census, a culprit sentence, a JSON line in `watchdog.data/incidents.txt`, and one chat line to the ops online.
  It closes when the mean over 30 s drops under 30 ms (logged with its length and peak).
- **Every 10 minutes while people are online** a quiet census becomes the baseline, so an incident can say what
  changed ("sharp rise: 3929 text_display now, 2013 six minutes ago"). It also reports **stacks of identical copies**
  on one block (see below) — one message per stack per 6 hours.
- **Freezes** (one tick over 2 s) are logged, not announced.
- **The only automatic fix:** more than 1000 dropped items (or 500 xp orbs) in ONE chunk are removed — never named
  or tagged ones — and the ops are told. Everything else is report-only.
- Chat: only to players with permission level 2+, at most one message per issue per 10 minutes.
- Tuning: `script in watchdog run config_set('lag_mspt', 40)` (saved in `watchdog.data/config.json`);
  `{"alerts": "dry"}` keeps the messages in `status()` instead of chat, `{"mitigate": false}` turns the junk removal off.
- Cost check: `script in watchdog run cost()` → `sample_us` (per second), `census_ms`, `per_tick_us` (amortised).

A census reads every loaded entity once: about 10-15 µs per entity (roughly 15 ms for 1,500 entities, 80 ms for
6,000). It runs on an incident, every 10 minutes while people play, and on demand — never every tick.

## Reading `heavy`

| Field | Meaning |
|---|---|
| `culprit` | the app's one-line verdict: a leak, a sharp rise, a hotspot, junk, or "no unusual entity load" |
| `stacked` | many entities of one type with the same tags on the same block. `identical:true` = their data is the same too: a **leak**. `identical:false` = parts of one assembly that share a pivot (a Ferris wheel, a pixel screen): fine |
| `hottest_chunks` | chunks ranked by a rough server-cost score, with the builds there and the tags inside |
| `dense` | chunks ranked by plain count. Display entities (block/item/text displays) cost the server little but the players' frame rate a lot: FPS problems show up here, not in the score |
| `rises_since_quiet_census` | what grew since the last quiet census, by type and by tag |
| `tags` | entity counts per tag prefix (`coaster_*`, `arena_*`) and the apps / generators whose code uses that tag |
| `junk` | item / xp piles over the thresholds |
| `force_loaded` | force-loaded chunks tick all the time, even with nobody near |
| `apps_running_every_tick` | apps with `__on_tick`: suspects when there is no entity culprit |
| `threads` | (threads:true) CPU % per JVM thread over 3 s |

Score weights: villager 6, other mobs 2, minecarts / boats / falling blocks 2, items and xp 1, armor stands 0.3,
displays / markers / interactions 0.05. It ranks suspects; it is not a profiler.

## Culprits and their fingerprints

| Fingerprint | Usual cause | Fix |
|---|---|---|
| `stacked` with `identical:true`: hundreds of copies of one display / armor stand on one block | an app does "if the entity is missing, summon it" — but a missing entity is often just in an **unloaded chunk**, so every check while nobody is near adds one more. If the app also updates "all entities with the tag" each second, every copy costs server time | in the app: act only when the chunk is loaded and a player is near, and keep exactly one (remove the extras). Then remove the extra copies once. Real case: 2,177 copies of one scoreboard text; after the fix the average tick went from ~30 ms to ~16 ms |
| a sharp rise of minecarts / boats at one place | the same pattern for a ride's cart (a new cart every few seconds) | the same fix; count carts per tag before and after |
| `junk`: thousands of dropped items in one chunk | a broken farm, a hopper line that overflows, an explosion | the watchdog removes the pile; fix the farm |
| many mobs that never leave | persistent mobs, a spawner farm, mobs that don't despawn on this difficulty | a small app with `entity_load_handler` that removes the unwanted ones as they load |
| lots of villagers in few chunks | breeding halls, crowded villages: pathfinding + AI is the heaviest per entity | fewer villagers per area, or blocks that stop them from wandering |
| a `dense` chunk full of display entities, ticks fine | a big display build | not a server problem; lower detail if players' FPS drops there |
| no entity culprit, `Server thread` near 100 % | chunk generation (players flying into new land, a Chunky pre-generation running), or an app doing heavy work each tick | pre-generate with Chunky while nobody plays; look at `apps_running_every_tick` |
| no entity culprit, GC threads high, swap nearly full | the computer is short of RAM: garbage collection on swapped-out memory stalls the game | less RAM for other programs, or a smaller `memory_mb` so the heap fits in real RAM |
| one freeze of several seconds when a bot joins | a fake player with a never-seen name makes the server look up its profile on the main thread | reuse the same bot names |

## Examples

```
minecraft_watchdog                                   → status: tick now + last minute, heap, swap, disk
minecraft_watchdog action:heavy top:5                → the culprit and the top 5 chunks
minecraft_watchdog action:heavy threads:true         → + which JVM threads use the CPU
minecraft_watchdog action:incidents kind:lag limit:5 → the last 5 lag incidents with their census
minecraft_watchdog action:disk                       → disk, world, ledger, what could be freed (deletes nothing)
minecraft_watchdog action:backup dry_run:true        → would a backup fit? what would rotation remove?
script in watchdog run census(5)                     → the raw census from the app
```

A `heavy` answer that points at a leak (shortened):

```json
{ "mspt": { "avg_ms": 30.7, "p95_ms": 60.5, "p99_ms": 283.6 }, "verdict": "busy (still 20 TPS)",
  "culprit": "2177 stacked copies of text_display [arena,arena_screen] on one block at -150,-36,432 (overworld): something keeps re-creating it",
  "stacked": [ { "n": 2177, "type": "text_display", "tags": "arena,arena_screen", "identical": true } ],
  "rises_since_quiet_census": { "age_min": 6, "types": [["text_display", 4108, 2013, 104.75]] },
  "tags": [ { "tag": "arena_*", "n": 3816, "used_by": ["arena.sc", "gen_arena.py"] } ] }
```

## Disk and memory

A full disk is the most dangerous thing for a world: when a save fails halfway, chunks can be lost. The MCP
checks every minute (one AI client at a time) and tells the ops online when free space drops under 2 GB, and
more urgently under 1 GB — once per level, repeated after 6 hours, never deleting anything. Settings go in
`clawdblock.json`: `"watchdog": {"disk_warn_gb": 5, "disk_crit_gb": 2}`.

- `action:disk` lists what could be freed in this install with sizes: old backups, the Ledger database, undo
  snapshots, the BlueMap render cache, old logs, screenshots. Deleting is the owner's call.
- On macOS swap files live on the same disk, 1 GB each: a Mac short of RAM loses disk space as swap grows.
- Heap numbers from `status` are the JVM's own; a heap much larger than the free RAM means the machine swaps.

## Backups

```
python3 clawdblock.py backup                  # → backups/world-YYYYMMDD-HHMMSS.zip, keeps the newest 3
python3 clawdblock.py backup --dry-run        # sizes, free space, what rotation would remove
python3 clawdblock.py backup --keep 7 --dest /Volumes/USB/mc-backups --include-ledger
minecraft_watchdog action:backup dry_run:true # the same from the AI
```

The order is save-off → save-all flush → copy → save-on → zip → verify → rotate, so saving is paused only
while the world is copied, and it is switched back on even after an error or Ctrl+C. It **refuses** when the
destination has less than 3× the world's size free (the running server must always be able to save). The Ledger
database is left out unless asked (it is often bigger than the world); with `--include-ledger` it is copied with
SQLite's backup API, a consistent snapshot while Ledger keeps writing. Rotation only removes zips the command made.

## Restarts

The watchdog never stops or restarts the server. A nightly restart when nobody is online only makes sense when
something starts the server again after it stops — a service (systemd, launchd, a Windows task) or a loop script.
Stop with `save-all flush` then `stop` over RCON and wait for the process to exit: never kill it on a timer, a
slow final save must be allowed to finish.

## For app authors: traps found while building the watchdog

- `entity_types('living')` also lists display entities. For "mobs with AI" use the mob categories: `monster`,
  `creature`, `ambient`, `water_creature`, `water_ambient`, `underground_water_creature`, `axolotls`, plus
  villagers and golems (they are in `misc`).
- Map keys that are lists (`m:[dim, cx, cz]`) made a census three times slower than one number per chunk.
- `slice()` of an empty list throws "/ by zero"; guard every `slice` on a filtered list.
- `entity_area` with a box of exactly one block misses entities standing exactly on the block's edge (y = -36.0):
  use a half-size of 0.6, not 0.5.
- A tool that "loads the app if the answer mentions *not loaded*" will reload your app when your own message text
  contains those words. Check that the answer is a value (`= …`) instead.
