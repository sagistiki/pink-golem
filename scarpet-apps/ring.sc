// ring.sc — SHRINKING RING, a small demo game built on the gamekit.scl library: the library does the joining, save /
// restore, elimination, spectating, end screen and records; this file is only the game rule (~60 lines).
// Stand on the pad north of the ring: a 10 s countdown (walk off the pad = you leave the queue), then everyone lands
// on the ring edge facing the centre. The ring of red particles shrinks; outside it you lose 4 health a second (the
// app's OWN damage, through gk_damage); running off the arena (4+ blocks past the starting ring) = out. 2+ players:
// the last one inside wins; alone: survive as long as you can (personal best). Out players spectate while others
// still play (Sneak = next player, the last Sneak = home). Nothing is built: the pad and the ring are particles.
// Setup: script in ring run setup(x, ground_y, z)   (arena centre, on the ground block)
// Test:  script in ring run global_allow_fake = true; reload()   then /player Test_A spawn at <pad>
// Needs gamekit.scl next to it in the scripts folder.

__config() -> {'stay_loaded' -> true, 'scope' -> 'global'};
import('gamekit', 'gk_new', 'gk_boot', 'gk_tick', 'gk_on_connect', 'gk_on_disconnect', 'gk_on_death', 'gk_on_respawn',
  'gk_alive', 'gk_damage', 'gk_eliminate', 'gk_secs', 'gk_yaw_to', 'gk_status', 'gk_restore', 'gk_top', 'gk_stop');

global_allow_fake = false;
global_R0 = 12;                 // starting radius
global_A = null;                // ring.data/arena.json = {"c": [x, y, z]} (feet level at the centre)
global_K = null;                // the gamekit state (all of it lives here, in the app)
global_r = global_R0;
global_deaths_seen = 0;         // __on_player_dies calls: a death caused by this app's own damage never arrives

setup(x, y, z) -> (write_file('arena', 'json', {'c' -> [x + 0.5, y + 1, z + 0.5]}); reload());
reload() -> (
  global_A = read_file('arena', 'json');
  if (!global_A, return('no arena yet: script in ring run setup(x, ground_y, z)'));
  c = global_A:'c'; R = global_R0; bx = floor(c:0); by = floor(c:1); bz = floor(c:2);
  global_K = gk_new({'id' -> 'ring', 'lobby' -> 10, 'allow_fake' -> global_allow_fake, 'text' -> {'prefix' -> '[Ring] '},
    'zone' -> [bx - 2, by, bz - R - 8, bx + 2, by + 2, bz - R - 6],       // the pad, north of the ring
    'home' -> [c:0, c:1, c:2 - R - 11, 0, 0],                             // back beside the pad, facing the ring
    'view' -> [c:0, c:1 + 12, c:2 - R - 6], 'focus' -> c,                 // spectator seat above the pad
    'on' -> {'start' -> _(K, names) -> _start(names), 'out' -> _(K, n, why) -> _out(n, why)}});
  gk_boot(global_K)
);
__on_start() -> reload();

__on_tick() -> (
  if (!global_K, return());
  gk_tick(global_K);
  t = tick_time();
  if (global_K:'state' == 'play', _play(t));
  if (t % 20 == 0, _pad())
);
__on_player_connects(p) -> if (global_K, gk_on_connect(global_K, p));
__on_player_disconnects(p, r) -> if (global_K, gk_on_disconnect(global_K, p));
__on_player_dies(p) -> (global_deaths_seen += 1; if (global_K, gk_on_death(global_K, p)));
__on_player_respawns(p) -> if (global_K, gk_on_respawn(global_K, p));

// everyone on the ring edge, facing the centre
_start(names) -> (
  c = global_A:'c'; k = length(names); global_r = global_R0;
  for (names, a = 360 * _i / k; q = [c:0 + sin(a) * (global_R0 - 2), c:1, c:2 + cos(a) * (global_R0 - 2)];
    run(str('tp %s %.2f %.2f %.2f %.1f 0', _, q:0, q:1, q:2, gk_yaw_to(q, c))))
);

_play(t) -> (
  c = global_A:'c'; s = gk_secs(global_K);
  global_r = max(0, global_R0 - max(0, s - 5) * 0.4);          // 5 s grace, then 0.4 blocks a second
  if (t % 10 == 0, _draw(c, global_r));
  if (t % 20 != 0, return());
  for (gk_alive(global_K), n = _; p = player(n);
    if (global_K:'state' != 'play', break());
    if (!p, continue());
    q = pos(p); d = sqrt((q:0 - c:0) ^ 2 + (q:2 - c:2) ^ 2);
    if (d > global_R0 + 4, gk_eliminate(global_K, n, 'out'),
        d > global_r, gk_damage(global_K, n, 4, 'minecraft:outside_border');
          run(str('title %s actionbar {"text":"Outside the ring! Get back in","color":"red"}', n)),
        run(str('title %s actionbar {"text":"Ring %.1f · %d s · %d left","color":"yellow"}', n, global_r, floor(s), length(gk_alive(global_K))))))
);

_out(n, why) -> run(str('playsound minecraft:entity.generic.explode master @a %.1f %.1f %.1f 0.8 1.4', global_A:'c':0, global_A:'c':1, global_A:'c':2));

_draw(c, r) -> if (r > 0.2, for (range(36), a = _ * 10;
  run(str('particle dust{color:[1.0,0.2,0.2],scale:1.6} %.2f %.2f %.2f 0 0.3 0 0 2 force', c:0 + sin(a) * r, c:1 + 0.3, c:2 + cos(a) * r))));
_pad() -> (
  z = global_K:'zone'; if (!z, return());
  for ([[z:0, z:2], [z:3 + 1, z:2], [z:0, z:5 + 1], [z:3 + 1, z:5 + 1]],
    run(str('particle happy_villager %.1f %.1f %.1f 0.1 0.3 0.1 0 3 force', _:0, z:1 + 0.3, _:1)))
);

status() -> (s = gk_status(global_K); s:'ring' = global_r; s:'deaths_event' = global_deaths_seen; s:'log' = global_K:'log'; s);
board() -> {'best' -> gk_top(global_K, 'best', 5), 'wins' -> gk_top(global_K, 'wins', 5)};
stop() -> gk_stop(global_K);
