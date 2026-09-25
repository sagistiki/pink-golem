# Vehicles — drivable cars (and boats, planes, coasters) with no client mods

A vehicle is a few server-side entities moved by a scarpet app every tick, a model from a resource pack, and the
player's keys read by a tiny server mod. Players install nothing. The working example is
[`scarpet-apps/cars.sc`](../../../scarpet-apps/cars.sc) with the models in
[`resourcepacks/cars/`](../../../resourcepacks/cars). This page is the recipe, so you can build a boat, a plane or a
coaster the same way.

## The parts

| Part | Entity | Why this one |
|---|---|---|
| Body | `item_display` holding `paper[item_model="cars:sedan", dyed_color=RGB]`, `teleport_duration:2` | any 3D model from the pack, tinted to any colour; `teleport_duration` makes each move glide on every client |
| Hit box | `interaction`, `width` ≈ car width, `response:1b` | right-click on it = `__on_player_interacts_with_entity` = get in |
| Seat | `armor_stand`, `Marker:1b, Invisible:1b, NoGravity:1b` | something to ride (first person) and for the driver body to ride |
| Camera | `item_display` with no item | the driver spectates it in the chase view |
| Driver body | `mannequin` with `profile:{name:"<player>"}`, riding the seat | the player (a spectator) is invisible; this shows them at the wheel |
| Input | scoreboard `keys`, written by the **Key Bridge** server mod ([`mods-src/keybridge/`](../../../mods-src/keybridge)) | the only way to read W/A/S/D/Space/Shift/Ctrl of a player who is spectating |

Every part is tagged `[<app>, <app>_car<id>, <generation>]` (see "Spawning safely").

## Input: one number per player

[Key Bridge](../../../mods-src/keybridge) copies each player's client input into `scoreboard('keys', name)` every tick it changes:

| Bit | Key | Car | Plane (suggested) | Boat |
|---|---|---|---|---|
| 1 | W | throttle | throttle up | forward |
| 2 | S | brake / reverse | throttle down | reverse |
| 4 | A | steer left | bank + turn left | left |
| 8 | D | steer right | bank + turn right | right |
| 16 | Space | handbrake (drift) | pull up | — |
| 32 | Shift | get out | get out (on the ground) | get out |
| 64 | Ctrl (sprint) | boost | push down | boost |

```
_keys(n) -> (f = global_fake_keys:n; if (f != null, return(f)); k = scoreboard('keys', n); if (k == null, 0, k));
set_keys(n, bits) -> (global_fake_keys:n = bits; bits);      // tests: fake players send no input
_bit(k, b) -> bitwise_and(k, b) != 0;
```

## The physics tick: steer first, then split the momentum

The heart of a good car feel is that the wheel turns the **nose**, not the **momentum**. Each tick:

```
// 1) steer: the nose turns in proportion to the speed along it, less lock at high speed, reversed when reversing
vf0 = vx * -sin(h) + vz * cos(h);
c:'steer' = c:'steer' + (want - c:'steer') * 0.35;                 // want = +1 right, -1 left: eased, not instant
sp = abs(vf0);
turn = c:'steer' * TURN * min(1, sp / 0.28) * (1 - 0.4 * min(1, sp / VMAX)) * if (hand, 1.45, 1);
if (vf0 < 0, turn = -turn);
h = h + turn;
// 2) the momentum did not turn: split it along the NEW nose (vf) and sideways (vr = the slip)
fx = -sin(h); fz = cos(h); rx = -cos(h); rz = -sin(h);            // forward and right for yaw h (0 = south)
vf = vx * fx + vz * fz; vr = vx * rx + vz * rz;
// 3) engine and brakes act along the nose only
if (gas, vf = vf + ACC * max(0.05, 1 - vf / VMAX),                 // soft top speed
  brk, if (vf > 0.04, vf = vf - 0.065, vf = max(-0.32, vf - ACC * 0.7)),
  vf = vf * 0.985);                                                 // rolling
if (hand, vf = if (abs(vf) <= 0.035, 0, vf - 0.035 * if (vf > 0, 1, -1)));   // handbrake alone stops in ~1 s
// 4) grip: the tyres kill part of the slip each tick; the handbrake (or ice) drops grip → the tail slides = drift
grip = GRIP * if (hand && abs(vf) > 0.12, 0.12, 1) * if (ice, 0.25, 1);
vf = vf + abs(vr) * grip * 0.25 * if (vf < 0, -1, 1);              // killed slip turns partly into speed: a drift exits fast
vr = vr * (1 - grip);
vx = vf * fx + vr * rx; vz = vf * fz + vr * rz;
```

| Knob (per model) | Typical | Feel |
|---|---|---|
| top speed `VMAX` (blocks/tick) | 0.95 – 1.35 | ×72 = km/h on the speedometer |
| `ACC` | 0.026 – 0.042 | how hard it pulls |
| `TURN` (degrees/tick at full lock) | 3.8 – 4.6 | agility |
| `GRIP` (0..1) | 0.28 – 0.36 | lower = slides more in fast corners |
| handbrake grip factor | 0.12 | lower = longer drifts |
| surface factors | grass 0.72, sand 0.6, ice grip ×0.25 | read the block under the centre |

## Moving and colliding

- **Footprint probes:** 9 points (4 corners, nose centre, 4 side midpoints) of the rotated car rectangle, each tested
  at the feet block and the one above. Solid → blocked.
- **Step-up:** blocked at y but free at y + 1 → climb (`y += 1`, speed × 0.8). Blocked at both → a wall: bounce
  (`v = -v * 0.25`), stay put, a crunch sound above 0.3 b/t.
- **Falling:** only when the centre AND both axles have air below — otherwise a car falls into every 1-block gap.
  Gravity 0.08/tick, terminal 1.5, land on the first solid block.
- **Push mobs, never players:** entities in front get `motion` along the car and the car loses 20 % speed. Skip
  `player`, `armor_stand`, `mannequin` (the driver body, seats, other cars' parts) — shoving a player off a road
  feels like a bug, not physics.
- **Placing the parts** after the physics: body `modify(e, 'location', x, y, z, h + MODEL_YAW, 0)`, hit box
  `modify(e, 'pos', …)`, seat on the driver's side a little forward.

## The chase camera

The driver becomes a spectator of a camera `item_display` that the app moves every tick:

```
dh = ((h - c:'ch') % 360 + 540) % 360 - 180; c:'ch' = c:'ch' + dh * 0.18;   // the camera HEADING lags softly
ch = c:'ch'; pitch = atan2(CAM_H - 1, CAM_D);
modify(cam, 'location', x + sin(ch) * CAM_D, y + CAM_H, z - cos(ch) * CAM_D, ch, pitch);
```

- The camera sits exactly behind the car's **current** position and has the same `teleport_duration:2` as the body,
  so both glide identically — the car never shakes on screen. Only the heading is smoothed, so turns feel cinematic.
- Get in: `gamemode spectator <p>`, then `spectate <camera> <p>` **2 ticks later** (right after the mode switch it
  is ignored).
- First-person option: no camera; the player rides the seat in their own game mode (F5 works as usual). Leaving
  the seat (Shift) = `query(p, 'mount') == null` → get out.

## The driver body (mannequin yaw trick)

A mannequin that rides the seat ignores `modify(e, 'body_yaw', …)`; the game only keeps its body within 50° of the
entity's own yaw. So push the yaw 50° past the heading on the side the body lags — the clamp drags the body exactly
onto the heading (≤ 4° lag in a hard turn). The head follows the camera:

```
d = ((h - query(man, 'body_yaw')) % 360 + 540) % 360 - 180;
modify(man, 'yaw', h + if (abs(d) < 0.5, 0, d > 0, 50, -50));
modify(man, 'head_yaw', camera_yaw); modify(man, 'pitch', camera_pitch * 0.6);
```

## Getting out (the exit sequence)

Order matters; each step fixes a bug seen in play:

1. Remove the camera and the mannequin; stop the car (`v = 0`, a parked car must not roll on).
2. `ride <p> dismount` if riding (first person).
3. `execute as <p> run spectate` — stop spectating **first**, or the mode switch leaves the view stuck on the camera.
4. Restore the saved game mode (saved on entering, also in a file for reloads; no save → adventure for players
   below permission level 2, creative for ops — never hard-code creative).
5. `modify(p, 'flying', false)` — spectator → creative keeps flying on.
6. **2 ticks later**, teleport beside the driver's door on the ground: step up out of walls/other cars, then down to
   the first solid block. Teleporting in the same tick as the mode switch lands in the wrong place.

## Spawning safely

- **Lazy spawn:** build the fleet in `__on_tick` only when a real player is within ~96 blocks of the lot (its chunks
  are loaded, so old copies can be found and removed). Spawning at server start with nobody around leaves parts in
  unloaded chunks that nothing can remove.
- **Generation tag:** every run tags its parts with a random `<app>_g<number>`. `entity_load_handler` on
  `item_display`, `interaction`, `armor_stand`, `mannequin`: a part tagged with the app but not with this run's
  generation is removed as its chunk loads (`schedule(0, …)`, then `modify(e, 'remove')`).
- **Remove with `modify(e, 'remove')`**, never `run('kill …')` inside a function called by a command: that kill is
  deferred until the command ends and would also kill what you spawn right after it.
- Tag prefix = `system_info('app_name')`: the same file loaded under another name never touches the live cars.

## Model orientation

An `item_display` with yaw Y shows the item model's **+z side facing away** from its look direction. Build the nose
at +z (z 16 in model space) and draw the body with `h + 180` (`global_MODEL_YAW`), or build the nose at -z and use `h`.
Everything else (camera, seat, probes) uses the real heading `h` (0 = south, yaw math as in coordinates.md).

## Reusing the recipe

| Vehicle | Keep | Change |
|---|---|---|
| **Boat** | parts, input, camera, exit, spawning | drive only while the block under the centre is water (else strong drag); grip ≈ 0.08 (boats slide); no step-up; bob `y` with `sin(t * 9) * 0.05`; stop at the shore instead of bouncing |
| **Plane** | parts, input, camera, exit | a pitch state: Space/Ctrl change pitch; lift ∝ speed² cancels gravity above a stall speed; A/D bank (tilt the body with `left_rotation` about the nose axis) and turn with the bank; vertical speed from pitch; get out only on the ground; camera pitch follows the plane |
| **Coaster** | parts, exit, spawning | no steering: precompute the track as points; `s` = distance along it; `v += g * (y_prev - y_next) / step - friction`; place the car at `s` with yaw/pitch from the tangent; riders sit in the seat (first person); Shift only at the station |

## Traps

| Trap | What happens | Do instead |
|---|---|---|
| Teleporting a ridden vanilla boat/minecart every tick | "moved wrongly" spam, the ride stutters | your own entities (display + seat), moved with `modify` |
| `spectate` in the same tick as `gamemode spectator` | the camera is not taken | `schedule(2, '_spectate', …)` |
| Mode switch while still spectating | view stuck on the camera | `execute as <p> run spectate` first |
| Spectator → creative | the player keeps flying | `modify(p, 'flying', false)` |
| Put-down teleport in the same tick | lands inside the car / in the air | 2 ticks later, step out of solids, drop to the ground |
| `modify(mannequin, 'body_yaw', …)` while it rides | ignored | the ±50° yaw trick |
| Model drives backwards | display shows +z away from the yaw | + 180 to the drawn yaw |
| Respawning parts at server start | frozen copies pile up in unloaded chunks | lazy spawn + generation tag + load handler |
| Pushing everything in front | players get shoved off the road | skip players, stands, mannequins |
| Reading keys of a fake player | always 0 | `set_keys(name, bits)` for tests |
| Speed shown in blocks/tick | meaningless to players | km/h = b/t × 72 |

## See also
[displays.md](displays.md) · [game-logic.md](game-logic.md) · [hud.md](hud.md) · [scarpet.md](scarpet.md) ·
[coordinates.md](coordinates.md) · [rails.md](rails.md)
