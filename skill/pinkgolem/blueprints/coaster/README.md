# Roller coaster (display entities, real physics, first-person ride)

A steel coaster that really runs, with no client mods: a smooth track of `block_display` boxes (not voxels), a train of
single-seat cars from a small resource pack, and a scarpet app that drives it with real gravity. Riders see the ride
in first person — up the chain lift, down a 67° drop, upside down through a loop — while everyone else watches a
mannequin with their skin in the car. Ride stats (top speed, G, airtime) come up at the station, and a board keeps
the rides count.

The demo ride: 662 blocks of track, a lift to 67 above the station, 120 km/h at the bottom of the drop, a 24.5-high
teardrop loop, a climbing turnaround, an airtime hill, a banked helix, a bunny hop, brakes — a 62 s lap, 46 × 213
blocks of flat ground. `layouts/family.py` is a small one (306 blocks, 22 high, no loop) and shows how to write your
own. How every part works, with the reasons: [reference/rides.md](../../reference/rides.md).

| File | What |
|---|---|
| `track.py` | the path (a turtle of straights, arcs and a loop with Hermite heights), arc-length resampling, the physics simulation, banking, frames → quaternions; `python3 track.py` checks a design |
| `build.py` | the generator: station, track displays, supports, and `track.json` for the app; installs the app |
| `pack.py` | the train as item models (`coaster:front`, `coaster:car`) with drawn flame textures → `resourcepacks/coaster/coaster.zip` |
| `coaster.sc` | the ride app: physics every tick, boarding, the camera, the loop, effects, stats, reload safety |
| `canvas.py` | a tiny PNG canvas the other files draw with |
| `layouts/family.py` | a second, smaller layout |

## Run order

1. **Check the design** (nothing touches the server):
   `python3 skill/pinkgolem/blueprints/coaster/track.py` → length, lap time, closure, top speed, stalls, G. It must
   end with `OK`. With `--layout layouts/family.py` for another layout, `--plot DIR` for a top view and a side profile.
2. **Find flat ground.** The demo needs 46 × 213 blocks and 74 high: the station track starts at `--at`, runs toward
   `--facing`, and the ride turns **right** (the platform is on the left). `minecraft_survey`, then
   `minecraft_vision mode:check` on the box a dry run prints; level it first if needed (`script in cu run level(…)`).
3. **Build the train pack** (optional for a first test — `--no-models` shows the cars as plain blocks):
   `python3 skill/pinkgolem/blueprints/coaster/pack.py --preview /tmp/train.png` writes
   `resourcepacks/coaster/coaster.zip`; look at the preview, then `minecraft_pack action:deploy` merges it into the
   server pack (live with the Key Bridge mod's `/packpush`, otherwise after a restart).
4. **Preflight:** `minecraft_generate script:"skill/pinkgolem/blueprints/coaster/build.py"
   args:["--at","X,Y,Z","--facing","east"] dry_run:true` — Y = the ground block (-61 on a flat world). It prints the
   box, the entity count and the files.
5. **Build:** the same call with `build:true helpers:3`, then `minecraft_jobs action:wait` until all three jobs are done.
   The helpers walk the track — summons only work in loaded chunks. The first job loads the app (`script load coaster`):
   if a coaster is already running, check `script in coaster run status()` first (nobody riding).
6. **Ride:** walk up the stairs, right-click a seat. The train leaves 8 s after the first rider. Shift in the station
   gets you out; mid-ride it does nothing (the camera takes you straight back). With nobody riding, the train does a
   show run every ~45 s while someone is watching. Then `minecraft_map action:add` and a note, as for any build.

Without `minecraft_generate` (plain Python): `python3 build.py --at X,Y,Z` writes the jobs to `jobs/` and the track
data to `jobs/coaster.data/track.json`; copy that to `<world>/scripts/coaster.data/`, copy `coaster.sc` to
`<world>/scripts/`, run the three job files with `minecraft_run_command commands_files:[…] background:true`.

## Options

| `build.py` option | Default | |
|---|---|---|
| `--at X,Y,Z` | — | the ground block under the start of the station track (the track runs at Y+3) |
| `--facing` | `east` | the direction the train leaves the station |
| `--name` | `coaster` | app name, tag prefix, job-file prefix: a second coaster is `--name coaster2` (its own app `coaster2.sc`, data, tags) |
| `--title` | `INFERNO` | the name on the sign, the ride screens and the board (no emoji) |
| `--cars` | 5 | 1–8 single-seat cars (fewer = lighter: a little slower over the hills — check with `track.py --cars N`) |
| `--platform` | 5 | platform depth, 3–8 |
| `--no-roof` | | a platform with lamp posts instead of a roofed station |
| `--layout FILE.py` | the demo | your own ride (below) |
| `--rails`, `--spine` | `red_concrete`, `black_concrete` | track colours (spine = spine, ties, supports) |
| `--no-models` | | plain-block cars until the train pack is live for players |
| `--update-app` | | overwrite an installed `<name>.sc` with this folder's `coaster.sc` (else an existing one is kept) |
| `--data DIR` | `<world>/scripts/<name>.data` | where `track.json` goes |
| `--force` | | build even when the design check fails |

The **Key Bridge** server mod ([mods-src/keybridge](../../../../mods-src/keybridge/README.md)) is optional: with it the
app reads Shift from the `keys` scoreboard (bit 32); without it, from the vanilla sneak flag. The ride was play-tested
with Key Bridge.

## Your own layout

A layout is a Python file with `layout(t)`; `t` is the turtle from `track.py`, standing at the station start, facing
`--facing`. Copy `layouts/family.py` and change it. The rules:

- **Start with the station:** `t.seg(L, tag="station")`, flat and straight, L ≥ 16 (the train stops 4 before its end;
  5 cars need 16). The platform is built along it on the left, so the ride should turn **right** first.
- **Heights relative to the station:** `B = t.y0`, then `y1=B + 12.0`. `m1` is the slope at the end of a piece
  (rise per horizontal block: 1.0 = 45°). Heights follow a cubic Hermite, so slopes are smooth across joints — give
  a piece enough length for its height change, or the curve overshoots (the check shows `y` going below the station).
- **Pieces:** `t.seg(L, turn=deg, y1, m1, tag)` (`turn` + = right; a quarter circle of radius r is `L = r·π/2,
  turn=90`) and `t.loop(Rb, Rt, shift)` (a teardrop loop, bottom radius Rb, top radius Rt, exits `shift` to the right).
- **Tags** give sections their behaviour: `lift` (the chain pulls at 0.30 b/t), `brakes` (down to 0.22), `tyres`
  (push to 0.2 near the station), `station`; `loop`, `air`, `helix` switch on effects and the loop camera.
- **Close the circuit:** end exactly at the start, heading `--facing`, at B. `t.along()` and `t.side()` tell where the
  turtle is relative to the start; compute the last pieces from them (see how both layouts size their turnaround
  and last straight). The check fails if the end is more than 0.5 from the start.
- **Check:** `python3 track.py --layout mine.py --plot /tmp/mine` until it says `OK` (no stall anywhere outside the
  lift and tyres) and the notes are acceptable (G beyond +5 / −1.5 is more than a real coaster would do).
- The ground must be flat at Y; supports go down to Y+1 wherever no other part of the track is below.

## Running it

| Call | Does |
|---|---|
| `script in coaster run status()` | state, riders, speed, generation — `busy:true` while anyone rides |
| `script in coaster run show_run()` | sends the empty train round |
| `script in coaster run stop()` | puts every rider on the exit platform, parks the train, opens the gates |
| `script in coaster run respawn()` | rebuilds the train (idle only) |
| `script in coaster run remove()` | takes the ride down: the train and loaded parts now, the rest as its chunks load (keep the app loaded); undo the station job for its blocks |
| `/coaster` | a player's own rides and top speed |

**Rebuilding or moving it:** run the generator again and build. Each generation tags its parts with a new build id
(in `track.json`); the app removes parts of an older build when their chunk loads, so no frozen copy of the old track
survives in chunks nobody visited. Build right after generating: the app follows the new `track.json` from its next
load.

**Testing with a fake player** (the server cannot see display entities: ask a real player to ride before you
announce it):

```
script in coaster run global_allow_fake = true
/player Rider spawn at <x> <y> <z>          (near the station: the train spawns when a player is within 96)
script in coaster run board('Rider', 0)     then  show_run() or wait 8 s;  status() while it runs
script in coaster run set_keys('Rider', 32) (Shift) in the station → Rider is put on the exit platform
script in coaster run set_keys('Rider', 0); global_allow_fake = false
```

A fake player's position drifts away from the camera it spectates (it has no client); the app re-attaches it every
few ticks, which is harmless.
