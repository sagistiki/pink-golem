# Case study: a tower of floors people actually use

Over two days, a live server's lobby tower grew from an empty shell into eleven floors. A small group of friends
played in it while it was being built. This page covers what worked, what broke, and the rules that came out of it.
The apps and a step-by-step guide are in
[`skill/pinkgolem/reference/tower-floors.md`](../skill/pinkgolem/reference/tower-floors.md).

## The shape of the job

Each floor was one loop:

1. **A short contract (SPEC).** It gave the box, the fixed things (the lift shaft, its door, the corner pillars), a
   table of coordinates, and the owner's choices, asked as 3-4 multiple-choice questions before building.
2. **A Python generator.** It used guarded `put`/`pbox` helpers and ended with assertions over every voxel: nothing in
   the shaft, nothing in front of the lift door, nothing outside the floor's box. The same script writes the app's
   data file, so a coordinate lives in exactly one place.
3. **Dry run, then build, then verify.** The dry run lists every existing block the build would overwrite. That is
   how a player's frame of 41 magenta shulker boxes in the arcade was saved: the build switched to
   `fill ... replace air`.
4. **An app, then a live look.** A block render cannot show display entities, so the owner walked the floor.
   Floor by floor, those walks produced the corrections below.

## What the owner corrected, and what it taught

| Floor | The request or the problem | The lesson |
|---|---|---|
| Hotel | "The pool faces out of the city, turn it round." A 180° turn was impossible because the lift owns that facade, so the pool went to the west side, toward the water park | Ask which *view* matters before placing a pool, a balcony or a window seat |
| Hotel | Suite doors "vanished", then two doors appeared in one suite | Toggling each door half with scarpet `set()` let the game move the door. Now: both halves with `setblock` and the full state |
| Hotel | "If I leave the server, check me out." "If my suite is gone, don't respawn me in it." | Every booking needs an end: logout, restart, expiry. A respawn point is part of the booking |
| Lift | Friends were left behind when one person pressed the button | Everyone standing in the car rides together. The car leaves after one second without movement |
| Registration | New players should not leave the lobby before registering | The barrier is a position check, not a wall: it holds however they got out |
| Studio | Skin names were readable through the floor | Floating nametags show through walls. Use a label with a short view range |
| Studio | A creative player killed two "invulnerable" mannequins | `Invulnerable` does not stop creative mode. Cancel the attack event |
| Arcade | "The lane says a game is running, nobody played for a minute" | Every game needs an idle timeout and a "nobody left" check |
| Arcade | The ball threw itself before a power was chosen | Holding right-click repeats the use event. Hold-to-charge needs a consumable item and the release event |
| Arcade | "I'm on the red line and it says I'm not" | Boundaries in messages must match boundaries in code, including the line itself |
| Arcade | The dance arrows pointed inward | Glazed terracotta's printed arrow points opposite its `facing`. Test one tile first |
| Culture | A "quiet please" message fired inside the lift going past | Every zone rule excludes the shaft and anyone riding |
| Club | "Not enough light, and I want people: dancing, sitting, hugging" | A believable crowd is mannequins in poses, riding marker stands on sofas, swinging on the beat |
| Club | "Add LED bars from the ceiling: red and white waves, a rainbow, strobes" | A `text_display` column of coloured blocks is a cheap LED bar. Cycle the patterns every 8 bars |
| A friend's tower | "Only she may add to it or edit it" | Carpet can cancel breaking, placing, right-clicks, bucket use and entity hits. The block logger names the builder |

## Numbers

| | |
|---|---|
| Floors built | 10 plus a roof, with one kept empty for a future gym |
| Techno loop | 150 BPM, 51.2 s = 1024 ticks, synthesised with numpy, 534 KB |
| Museum photos | 16 landmarks, 320x200 each, 776 KB in the pack |
| Longest lift ride | 154 blocks. At 5.8 ticks a block it took 45 s, so long rides were capped to about 17 s |

## What to copy

- **A contract, then a generator with assertions, then a dry run.** Guards in code caught every "put a block in the
  lift shaft" mistake before it reached the world.
- **One data file per app, written by the generator.** Moving a sign or a lane meant running one script again, never
  editing numbers in two places.
- **The owner's words go into the code comment** next to the rule they caused, so the next model knows why the rule
  exists before changing it.
