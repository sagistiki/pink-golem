# Rails — trams, coasters and lines that actually run

Rails placed by commands do not connect themselves: every rail needs its `shape`, boosters need power, and an empty
cart behaves very differently from a ridden one. Plan the line, lay it with the tool, then trace it and ride it.

## Lay a line: `minecraft_rails action:path`

```
minecraft_rails action:path points:[[0,-60,0],[40,-60,0],[40,-57,20],[0,-57,20]] closed:true name:"loop" build:true
```

- `points` are corners; every leg runs straight along x **or** z. y may change along a leg (one block per step, at most
  leg length − 2) — the tool writes `ascending_*` shapes; corners always stay flat.
- Curves get the right `north_east / north_west / south_east / south_west` shape from the directions in and out.
- Boosters: a powered rail on a redstone block every `boost_every` (default 5) and on the `curve_boost` (default 2)
  rails right after each corner (powered rails cannot curve).
- `support` (default smooth_stone) goes under every rail where there is air (`setblock … keep`), so lines on bridges
  and slopes do not pop off.
- `closed:true` joins the last point to the first. Open lines end straight: join them to an existing line yourself.
- `dry_run:true` = generate + preflight only; `build:true` = build as a normal job (undo, zones, verify).
- In a generator: `from city import rail_path` (`skill/clawdblock/scripts/city.py`) does the same thing, and
  `road(b, a, c, tram=True)` lays a street with a rail in each lane.

## Check a line: `minecraft_rails action:trace pos:[x,y,z]`

Follows every connected rail from one rail and reports: count, closed loop or not, **open ends**, **one-way links**
(a rail pointing into the side of another — the cart derails there), unpowered powered rails (brakes) and
**stretches longer than `gap` (8) without a booster**. Run it after every change to a line.

## Test it: `minecraft_rails action:ride pos:[x,y,z] direction:east`

A real cart with an invisible armor-stand rider rolls from `pos`; you get a timeline, where it stopped or stalled,
the distance, the top speed and "came back to the start" for loops. `until_pos` ends the ride early.

## Facts that decide whether a cart moves

- **An empty cart loses speed fast** (friction 0.96 per tick) and stops ~8 rails after a booster. A cart with a player
  (or any passenger) keeps its speed (0.997). Test with `rider:true` (the default) to see what players will feel.
- **A cart stopped on a powered rail does not start** unless a solid block sits at one end. Keep boosters dense on
  lines that must run empty (a tram that circles on its own), or nudge the cart from an app every second:
  `modify(cart, 'motion', dx * 0.4, 0, dz * 0.4)` in the direction it last moved.
- **Carts only move in ticking chunks** — near a player. Forceloaded chunks do not tick entities, and a server with
  `pause-when-empty-seconds` stops everything when nobody is online (RCON still answers, nothing moves). The ride tool
  brings a spectator fake player when nobody is near; its first spawn looks the name up at Mojang (a short freeze).
- **Never respawn a "missing" cart blindly.** `entity_selector` only sees loaded entities: an app that summons a new
  cart whenever it finds none piles up hundreds of carts in unloaded chunks (a real server collected 190 and lagged).
  Only respawn when a real player is near and the spawn point is loaded, and remove extras:

```
_keep_one(tag, sp, cmd) -> (
    near = filter(player('all'), _~'player_type' != 'fake' && abs(pos(_):0 - sp:0) < 96 && abs(pos(_):2 - sp:2) < 96);
    if (!near || !loaded(sp), return());
    carts = entity_selector('@e[type=minecart,tag=' + tag + ']');
    if (!carts, run(cmd); return());
    if (length(carts) > 1,
        keep = first(carts, query(_, 'passengers')); if (!keep, keep = carts:0);
        for (carts, if (query(_, 'id') != query(keep, 'id'), modify(_, 'remove'))))
);
```

## See also
[game-logic.md](game-logic.md) · [scarpet.md](scarpet.md) · [large-builds.md](large-builds.md) · [troubleshooting.md](troubleshooting.md)
