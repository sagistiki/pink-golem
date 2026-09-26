# Rides — roller coasters and other moving rides made of display entities

Read this before you build anything that carries players along a path: a roller coaster, a dark ride, a monorail,
a log flume, a ghost train. Rail and minecart rides are in [rails.md](rails.md); driven vehicles in
[vehicles.md](vehicles.md). This page is the method behind the working example,
[`blueprints/coaster/`](../blueprints/coaster/README.md) — a 662-block steel coaster with a 67-block lift, a loop and
a helix, running in first person with no client mods. Every rule below was either measured or learned by breaking it.

| Part | Made of | Why |
|---|---|---|
| The path | Python: a turtle + Hermite heights → samples every 0.5 block (`track.py`) | smooth in slope and banking; checkable before anything is built |
| The track | ~1,400 static `block_display` boxes stretched and turned along the curve (`build.py`) | a smooth steel track — blocks can only make staircases |
| The train | `item_display` cars with models from a resource pack (`pack.py`) | any shape; goes upside down with a quaternion |
| The ride | a scarpet app: the same physics every tick, boarding, camera, effects (`coaster.sc`) | nothing needs a client mod |
| The rider | a spectator of a camera entity; a mannequin with their skin in the seat | a smooth, locked first-person view |

## 1. Design the path with a turtle

Describe the ride as pieces, like a pen that moves and turns: a straight or an arc in plan view, whose height goes
from the current `(y, slope)` to a target `(y1, m1)` along a **cubic Hermite** curve. Height and slope are
continuous at every joint, so the train never jolts — a kink in slope is a spike in G.

```python
t = Turtle(x, y, z, yaw)                       # the station start, heading yaw (0 south, 90 west, 180 north, 270 east)
B = t.y0
t.seg(24, tag="station")                       # straight, flat
t.seg(15.7, turn=90, tag="tyres")              # quarter circle, r = 15.7 / (π/2) = 10, turning right
t.seg(66, y1=B + 65.2, m1=0.95, tag="lift")    # climb to +65.2, arriving at slope 0.95 (43°)
t.seg(34, y1=B + 18.0, m1=-2.0)                # the drop: 67° at its steepest
t.loop(16.0, 8.5, 3.0)                         # a teardrop loop, 24.5 high, exiting 3 blocks to the right

# inside seg(): t = 0..1 along the piece's horizontal length L, m = rise per horizontal block
h00, h10, h01, h11 = 2*t**3 - 3*t**2 + 1, t**3 - 2*t**2 + t, -2*t**3 + 3*t**2, t**3 - t**2
y = h00*y0 + h10*L*m0 + h01*y1 + h11*L*m1
```

- **Close the circuit by computing, not guessing:** `t.along()` / `t.side()` give the turtle's offset from the
  start; size the turnaround and the last straight from them (`r = (t.along() + 8) / 2` puts the way back 8 blocks
  behind the start). The last sample must land within half a sample of the first.
- **A loop is its own element.** Its tangent angle θ runs 0 → 2π while the radius shrinks from Rb at the bottom to
  Rt at the top (`r = Rb + (Rt − Rb)(1 − cos θ)/2`) — the teardrop that keeps the top from being a G spike. It drifts
  sideways by `shift·(θ − sin θ)/2π` so the exit clears the entry, and it records its own up vector (toward the loop
  centre) for the frames: world-up is useless when the track is vertical.
- Tags are behaviour: `lift`, `brakes`, `tyres`, `station` change the physics, `loop` changes the camera, `air` and
  `helix` switch on effects.

## 2. Resample by 3D arc length

The turtle steps 0.1 block of *horizontal* length; on a 67° drop each step is 2.5 blocks of track. Resample to equal
**3D** distances (DS = 0.5): then a train position is just a distance `s`, a sample is `s / DS`, and the slope of a
sample is `Δy / DS` = sin(pitch) — exactly what gravity needs.

```python
cum = [0.0]                                    # running 3D length of the fine points
for a, b in zip(pts, pts[1:]): cum.append(cum[-1] + math.dist(a[:3], b[:3]))
s, j = 0.0, 0
while s < cum[-1]:
    while cum[j + 1] < s: j += 1
    k = (s - cum[j]) / (cum[j + 1] - cum[j]); out.append(lerp(pts[j], pts[j + 1], k)); s += DS
```

## 3. Physics in blocks per tick — and test it before you build

With 1 block = 1 m and 20 ticks a second, real gravity is **g = 9.81 / 20² = 0.0245 blocks/tick²**; a speed in
blocks/tick × 72 = km/h. The same update runs in the Python check and in the app every tick:

```
a = 0; for (range(NC), a += _sin(s - _ * GAP));                    // slope averaged over the cars
v = v - G * a / NC - DRAG * v * abs(v) - ROLL * if (v > 0, 1, 0);  // gravity, air (0.0012/block), rolling (0.0004)
if (on_lift, v = 0.30,                                             // the chain holds 0.30 while ANY car is on it
    head_on_brakes && v > 0.22, v = max(0.22, v * 0.93),
    in_station && v < 0.20, v = min(0.20, v + 0.02));              // tyres
s += v;
```

- **Average the slope over the cars.** A 5-car train speeds up as more cars pass a crest and is still pulled while the
  head climbs the next hill; a single point stalls on crests the real train clears (and clears ones it wouldn't).
- **Run the design in Python first:** `python3 track.py [--layout mine.py] [--plot DIR]` prints length, lap time,
  closure, top speed, the slowest speed outside lift and tyres, every stall position, and the felt G. The demo:
  662 blocks, 62 s, 120 km/h, slowest 0.17 b/t. Fix stalls by lowering that hill or making the drop before it
  steeper — rebuilding 1,400 displays to find out is the expensive way.
- Felt G along the car's up = `(v²·curvature + g·ŷ) · up / g`. Riders feel nothing in Minecraft, but a design that
  shows −2.7 G on a crest would throw a real train off, and the stats screen reports it.

## 4. Banking from speed

A curve is banked so the felt force points into the seat: **bank = atan(v²·κ / g)**, κ = the signed horizontal
curvature. The bank depends on the speed, so simulate first, then bank:

```python
kappa = -dheading / (4 * DS)                    # heading change across ±2 samples, + = turning right
bank = math.atan2(max(v, 0.2) ** 2 * kappa, G)
# smooth over ±12 samples (±6 blocks) so the roll eases in, cap at 72°
```

Slow curves (the station turns) stay nearly flat; the helix at speed leans hard — without hand-tuning each curve.

## 5. Frames → quaternions (and the item_display flip)

Per sample: **f** = the tangent; **u** = world-up made perpendicular to f, rolled by the bank (in the loop: the loop's
own up); **l** = u × f. The rotation whose columns are (l, u, f) maps display x → left, y → up, z → forward; turn it
into a quaternion and store it with the sample (`[x,y,z, qx,qy,qz,qw, ux,uy,uz, lx,ly,lz]` in `track.json`).

- **Keep neighbouring quaternions in one hemisphere** (`if dot(q, prev) < 0: q = −q`): q and −q are the same
  rotation, but the app blends neighbouring samples, and a sign flip in between blends through a 180° spin.
- **A car** is an `item_display` whose `transformation.left_rotation` is that quaternion — so it banks, climbs and goes
  upside down in the loop. Each tick: `modify(e, 'pos', …)` plus an `nbt_merge` of the transformation with
  `start_interpolation:0`; `teleport_duration:1` and `interpolation_duration:1` make every client glide between ticks.
- **An `item_display` draws item models turned 180° about the vertical axis.** Build vehicle models with the nose at
  **−z** (it ends up along the display's +z = forward); the same flip puts the model's +x side on the right.
  `resourcepacks/tools/model_preview.py` renders a model to PNG without a client — check which way it faces.
- Model space: 16 units = 1 block at scale 1; the item renderer puts the model's (8, 8, 8) on the entity, so the track
  point (rail top, centre) is (8, 8, 8) and the seat an offset from it.

## 6. The track: display boxes along a curve

A `block_display` draws a unit cube from its position toward +x +y +z, then applies
`translation + left_rotation · (scale ∘ v)`. For a box from point A to point C, `w` wide and `h` high, with axes
l, u, f: rotate by the (l, u, f) quaternion, scale `[w, h, |AC|]`, stand the entity at the midpoint and centre it with

```python
tr = [-(l[k] * w / 2 + u[k] * h / 2 + f[k] * length / 2) for k in range(3)]   # in world axes, not rotated
```

- **Adaptive segmentation:** start a box at sample i and grow it while every sample in between stays within 0.035 of
  the chord, it is at most 6 blocks long, and the up vector turns less than 7° (the twist of a banked curve). Straights
  become 6-block boxes, the loop dozens of short ones. Pad each box 0.03 at both ends so no seam shows.
- Members of a steel track: two rails (0.2 × 0.2 at ±0.6 left), a spine (0.36 × 0.4 half a block below), a tie every
  2.5 blocks, a dark chain strip on the lift. `view_range:2.5f` (≈ 160 blocks) and a fixed `brightness` so it glows
  a little at night.
- **Supports:** every 4 blocks where the track is roughly upright (`u.y ≥ 0.35`), a column from the ground to 0.66
  under the track — **only if nothing is in the way**: no other part of the track below the column's top within 1.7
  blocks sideways (ignoring the ±7 blocks around the column itself). A-frames on the tall lift. Skip the station.

## 7. The camera: spectate or ride?

| | **Spectate a camera entity** (the coaster) | **Ride a seat entity** |
|---|---|---|
| How | the player is a spectator of an `item_display` the app moves each tick (`spectate <camera> <player>`) | `ride <player> mount <seat>`; the seat is moved each tick |
| View | locked to the ride: the camera's yaw and pitch ARE the view — the drop, the loop | free look: the player turns their head; the view does not follow the track's pitch |
| Smooth | `teleport_duration:1` → the client interpolates | yes, when the seat has `teleport_duration` too |
| FOV | **cannot be changed**: FOV effects only apply when the camera entity is the player itself | the server can widen it: raise the rider's `movement_speed` attribute during the ride (the client widens its FOV as when sprinting; reset it after; players with FOV Effects at 0 see no change) |
| Others see | a mannequin with the rider's skin riding the seat | the player |
| Shift | leaves the camera — the app must catch it (§9) | dismounts — the app must catch it |

Minecraft has **no camera roll**: banking and loops can only be shown by yaw and pitch. The frame is where the camera
sits, so place it well (§8).

## 8. The seat, the eye and the loop

- **A rider's eye is 1.02 above the entity it rides** (measured, players and mannequins alike). So the seat entity
  goes at `eye − 1.02` (in world y), with the eye = the model's seat point + up·0.87.
- The camera sits at the eye plus forward·0.6 — at 0.3 riders saw the inside of their own mannequin's head.
- The mannequin rides the seat, and a riding mannequin ignores `body_yaw`: use the ±50° yaw trick from
  [vehicles.md](vehicles.md). Make it invisible for the loop (it stays upright while the car turns over).
- **Lock the yaw in the loop.** The camera's yaw is the track's heading, `atan2(−f.x, f.z)`; at the top of a loop the
  heading reverses, so the view would snap 180°. Inside a `loop` section (and wherever the track is nearly vertical)
  keep the loop's entry yaw and only pitch:

```
yaw = if (in_loop || sqrt(f:0^2 + f:2^2) < 0.2, LOOP_YAW, atan2(-f:0, f:2));
pitch = -asin(max(-1, min(1, f:1)));
modify(camera, 'location', eye:0 + f:0 * 0.6, eye:1 + f:1 * 0.6, eye:2 + f:2 * 0.6, yaw, pitch);
```

## 9. Getting in and out

- **Board** by right-clicking an `interaction` box at each seat (`__on_player_interacts_with_entity`): save the game
  mode in a file, tag the rider, spawn the camera and the mannequin, `gamemode spectator`, and `spectate` **2 ticks
  later** (right after a mode switch it is ignored). Remove the boxes while the train runs.
- **Shift:** a spectator leaves the camera with Shift — vanilla does it. Read Shift on its rising edge: from the
  Key Bridge mod's `keys` scoreboard (bit 32) when it is installed, else the vanilla sneak flag. In the station it
  means "get out"; mid-ride, spectate the camera again at once.
- **Every tick, re-attach a rider** who is not in spectator or is more than 2.5 blocks from the camera. **Never use
  that distance as "the rider left":** a Carpet fake player spectating a moving camera has no client, so its position
  drifts away and it would be thrown off in every test.
- **Getting off** follows the exit sequence in [vehicles.md](vehicles.md): stop spectating first, restore the saved
  mode (no save → adventure, or creative for ops), flying off, teleport to the exit 2 ticks later.

## 10. Reload safety — and never a second train

- Riders carry a tag and their mode is in `restore.json`: `__on_start` lands anyone who was riding when the app
  reloaded or the server stopped, and a rider who logs back in is landed on join.
- **Generation tags:** every spawn of the train tags its parts with a new `<app>_g<n>`; an `entity_load_handler`
  removes a loaded part of the app without the current generation. A frozen copy in a chunk nobody visited dies the
  moment its chunk loads.
- **Lazy spawn:** spawn the train only when a real player is near the station and its chunk is loaded — never
  "summon it because a selector found nothing": the chunk may just not be loaded, and a check every few seconds
  piles up hundreds of copies ([game-logic.md](game-logic.md)).
- **The static track gets a build tag too** (`<app>_b<id>`, the id in `track.json`). A generator's `kill` only
  reaches loaded chunks; the app removes parts of an older build as their chunks load, so a rebuilt or moved track
  leaves no ghost.
- **Force-load the ride's chunks while the train runs, and release them after.** The app moves every car itself, but
  a car in an unloaded chunk does not exist for `entity_id()` — an empty show run far from players would lose cars.
  One `forceload add` covers at most 256 chunks.

## 11. The entity budget

| What | Demo coaster (662 blocks of track) |
|---|---|
| Rails, spine, ties, chain | 1,166 displays |
| Supports | ~210 displays |
| Signs, board | 3 |
| **Static total** | **~1,400 displays ≈ 2 per block of track** |
| Train | 5 cars + 5 seats + 5 click boxes; + a camera and a mannequin per rider |
| Per tick while running | per car one `modify pos` and one `nbt_merge`; per rider a camera move |

Static displays have no AI and no physics: the cost is the client drawing them within `view_range` and the chunks
saving and loading them. Keep the moving parts few. After building, `minecraft_watchdog action:heavy` counts entities
by tag prefix — a number that grows between two checks is a leak.

## Common mistakes

| Mistake | What happens | Do instead |
|---|---|---|
| Heights typed per block instead of a smooth curve | jolts, G spikes, a stall where two slopes meet | Hermite pieces; check with `track.py` |
| Samples every 0.5 of *horizontal* length | the train races on steep parts and crawls on flat ones | resample by 3D arc length |
| Physics on one point | stalls on crests a train would clear | average the slope over the cars |
| Model nose at +z on an `item_display` | the train rides backwards | nose at −z (or yaw + 180) |
| Neighbouring quaternions with opposite signs | a car spins once between two samples | flip q when `dot(q, prev) < 0` |
| Camera yaw from the heading through the loop | the view snaps 180° at the top | keep the entry yaw in the loop, pitch only |
| Camera at the eye | the rider sees the inside of the mannequin's head | eye + forward·0.6 |
| "Rider is > N blocks from the camera → they left" | fake players are thrown off in every test | distance only re-attaches; Shift and disconnect end a ride |
| Spawning the train when a selector finds none | hundreds of trains in unloaded chunks | lazy spawn + generation tag + load handler |
| Support columns straight down everywhere | columns through the track below | the clearance test |
| Announcing it from the server's side | displays can't be seen by the server | ask a real player to ride it first |

## See also
[vehicles.md](vehicles.md) · [displays.md](displays.md) · [rails.md](rails.md) · [game-logic.md](game-logic.md) ·
[scarpet.md](scarpet.md) · [testing-apps.md](testing-apps.md) · [watchdog.md](watchdog.md) ·
[blueprints/coaster](../blueprints/coaster/README.md)
