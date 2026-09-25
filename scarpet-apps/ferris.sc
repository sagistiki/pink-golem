// ferris.sc — a working Ferris wheel you can ride, no mods needed (static part: blueprints/ferris_wheel.py).
// The wheel is read from ferris.data/wheel.json = {"x": X, "gy": Y, "z": Z} (the ground block under the axle).
// setup() writes it; blueprints/ferris_wheel.py ends with  script in ferris run setup(X, Y, Z)  so you rarely call it.
// Without a wheel file the app idles. Everything is derived from that point: the axle at X+0.5, Y+14.5, Z+0.5 (the wheel
// turns in the x-y plane, rims at z ± 1.3), the gold BOARD pad x X-3..X-2 z Z-1..Z+1, the EXIT spot at X+3.5 Y+1 Z+0.5.
//
// How it works: the wheel (two red rims, white spokes, yellow cross-bars, a gold hub, 24 chasing lights) is made of
// block displays that all stand at the axle; each one's `transformation` places and turns it on the wheel. Every 10
// ticks the app merges the next angle with interpolation_duration:10, so every client animates the turn smoothly.
// The 8 cabins stay level: each is an invisible armor stand ("seat") that the app moves along the circle every tick,
// with 12 small gondola displays riding on it (a passenger display rides at seat + 1.975, a player's feet at + 1.375).
// A player is put in a cabin with  ride <player> mount <seat uuid>  and stays mounted while the seat moves.
//
// It runs like a fairground wheel: turn one cabin (5 s, eased), stop (4 s). At every stop the cabin at the bottom lets
// off a rider who has been all the way round and takes the player standing on the gold pad. Shift = get off at once
// (the game dismounts you; the app puts you on the exit spot). It only runs while a real player is within 90 blocks.
//
// Testing with a fake player (Carpet): set global_allow_fake = true below, `script load ferris`, then
//   /player Rider spawn at <X-2> <Y+1> <Z>      (on the pad) → it boards at the next stop and goes round;
//   script in ferris run global_riders          → {cabin: [name, stops]};  /player Rider sneak → back on the exit spot.
// The display visuals cannot be checked from the server: ask a real player to ride and look before you announce it.
// Reload after editing wheel.json:  script in ferris run reload()      Remove everything:  script in ferris run remove()

__config() -> {'stay_loaded' -> true, 'scope' -> 'global'};

global_R = 11;                  // rim radius
global_RC = 10.5;               // cabins hang from cross-bars just inside the rim
global_N = 8;                   // cabins
global_STEP = 45;               // 360 / N
global_MOVE = 100;              // ticks to turn one cabin
global_STOP = 80;               // ticks stopped at each cabin
global_UPD = 10;                // ticks between wheel updates (= the interpolation)
global_DROP = 4.3;              // cross-bar → seat; tuned so the cabin roof clears the cross-bar
global_colors = ['red', 'orange', 'yellow', 'lime', 'light_blue', 'blue', 'purple', 'magenta'];
global_allow_fake = false;

global_ready = false;
global_pieces = [];
global_bulbs = [];
global_seats = [];
global_riders = {};
global_theta = 270;
global_th0 = 270;
global_phase = 'stop';
global_t = 0;
global_active = false;
global_shift = 0;

// ───────────── setup ─────────────
setup(x, gy, z) -> (
  if (length(global_riders) > 0, return('someone is riding — run setup again after they get off'));
  w = {'x' -> x, 'gy' -> gy, 'z' -> z};
  write_file('wheel', 'json', w);
  _derive(w);
  _spawn();
  str('Ferris wheel at %d %d %d — stand on the gold pad at %d %d %d to ride', x, gy, z, x - 2, gy + 1, z)
);

reload() -> (
  w = read_file('wheel', 'json');
  if (!w, return('no wheel yet — run setup(x, y, z) with the ground block under the axle'));
  _put_down_all();
  _derive(w);
  _spawn();
  str('wheel at %d %d %d', w:'x', w:'gy', w:'z')
);

remove() -> (
  _put_down_all();
  global_ready = false;
  _kill_all();
  delete_file('wheel', 'json');
  'removed (the static blocks stay: undo the blueprint jobs to remove them)'
);

_derive(w) -> (
  x = w:'x'; gy = w:'gy'; z = w:'z';
  global_C = [x + 0.5, gy + 14.5, z + 0.5];
  global_pad = [x - 3, gy, z - 1, x - 1, gy + 3, z + 2];    // x1 y1 z1 (inclusive) → x2 y2 z2 (exclusive)
  global_exit = [x + 3.5, gy + 1, z + 0.5];
  global_snd_y = gy + 3
);

// The wheel is (re)built lazily, when a real player is near, so its chunks are loaded and the old copy is removed
// first. Every build carries its own generation tag; a part of an older build that loads later (a chunk that was
// unloaded during the rebuild, e.g. after a restart) is removed on load — otherwise a frozen copy stands next to the
// live wheel.
global_gen = str('fw_g%d', floor(rand(1000000000)));
__on_start() -> (
  global_ready = false;
  for (['block_display', 'armor_stand'], entity_load_handler(_, _(e, new) -> if (!new, schedule(0, '_stale', query(e, 'uuid')))));
  w = read_file('wheel', 'json');
  if (w, _derive(w), logger('warn', '[ferris] no wheel yet — run: script in ferris run setup(x, y, z)'))
);
_stale(u) -> (e = entity_id(u); if (e && global_ready, t = parse_nbt(query(e, 'nbt', 'Tags')); if (t && (t ~ 'fw') != null && (t ~ global_gen) == null, modify(e, 'remove'))));
// remove at once — a `kill` run from inside a command (script in ferris run setup/reload) is deferred until after it
// and would also remove the wheel that was just built
_kill_all() -> for (entity_selector('@e[tag=fw]'), modify(_, 'remove'));

_real(p) -> global_allow_fake || (p ~ 'player_type') != 'fake';
_ease(f) -> f * f * (3 - 2 * f);
_msg(n, t, c) -> run(str('title %s actionbar %s', n, encode_json({'text' -> t, 'color' -> c, 'bold' -> true})));
_snd(s, v, pt) -> run(str('playsound %s master @a %.1f %.1f %.1f %.1f %.2f', s, global_C:0, global_snd_y, global_C:2, v, pt));

// ───────────── the moving parts ─────────────
_disp(blk) -> spawn('block_display', global_C, str('{Tags:["fw","fw_rot","%s"],block_state:{Name:"minecraft:%s"},teleport_duration:0,brightness:{sky:15,block:15}}', global_gen, blk));

// a piece of the wheel: centre (pu, pv) on the wheel plane at angle 0, z offset zo, own angle phi, size sx × sy × sz
_piece(pu, pv, zo, phi, sx, sy, sz, blk) -> (
  p = [query(_disp(blk), 'uuid'), pu, pv, zo, phi, sx, sy, sz];
  global_pieces += p;
  p
);

_spawn() -> (
  global_ready = false;
  _kill_all();
  global_pieces = []; global_bulbs = []; global_seats = []; global_riders = {};
  R = global_R;
  for ([-1.3, 1.3],
    zo = _;
    for (range(24), a = _ * 15; _piece(R * cos(a), R * sin(a), zo, a + 90, 2 * 3.14159 * R / 24 + 0.35, 0.35, 0.35, 'red_concrete'));
    for (range(8), a = _ * 45 + 22.5; _piece(R / 2 * cos(a), R / 2 * sin(a), zo, a, R, 0.22, 0.22, 'white_concrete'))
  );
  for (range(global_N), a = _ * global_STEP; _piece(global_RC * cos(a), global_RC * sin(a), 0, a, 0.3, 0.3, 2.9, 'yellow_concrete'));
  _piece(0, 0, 0, 0, 1.6, 1.6, 3.2, 'gold_block');
  for (range(24),
    a = _ * 15 + 7.5;
    p = _piece((R + 0.3) * cos(a), (R + 0.3) * sin(a), -1.55, a, 0.45, 0.45, 0.2, global_colors:(_ % 8) + '_concrete');
    global_bulbs += p:0
  );
  // cabins: a seat each, with the gondola riding on it
  for (range(global_N),
    col = global_colors:(_ % 8);
    s = spawn('armor_stand', global_C, str('{Tags:["fw","fw_seat","%s"],Invisible:1b,NoGravity:1b,Invulnerable:1b,Silent:1b,DisabledSlots:4144959}', global_gen));
    global_seats += query(s, 'uuid');
    y0 = -0.72;                                                    // just under the rider's feet
    for ([[col + '_concrete', -0.9, y0, -0.9, 1.8, 0.12, 1.8],     // floor
          [col + '_concrete', -0.9, y0, -0.9, 1.8, 0.75, 0.08],     // four low walls
          [col + '_concrete', -0.9, y0, 0.82, 1.8, 0.75, 0.08],
          [col + '_concrete', -0.9, y0, -0.9, 0.08, 0.75, 1.8],
          [col + '_concrete', 0.82, y0, -0.9, 0.08, 0.75, 1.8],
          ['white_concrete', -1.0, y0 + 2.25, -1.0, 2.0, 0.15, 2.0],  // roof
          [col + '_wool', -0.7, y0 + 2.4, -0.7, 1.4, 0.2, 1.4],
          ['iron_block', -0.88, y0, -0.88, 0.07, 2.25, 0.07],         // corner posts
          ['iron_block', 0.81, y0, -0.88, 0.07, 2.25, 0.07],
          ['iron_block', -0.88, y0, 0.81, 0.07, 2.25, 0.07],
          ['iron_block', 0.81, y0, 0.81, 0.07, 2.25, 0.07],
          ['iron_block', -0.05, y0 + 2.6, -0.05, 0.1, 0.45, 0.1]],    // hanger up to the cross-bar
      q = _;
      d = spawn('block_display', global_C, str('{Tags:["fw","fw_cab","%s"],block_state:{Name:"minecraft:%s"},brightness:{sky:15,block:13},transformation:{left_rotation:[0f,0f,0f,1f],right_rotation:[0f,0f,0f,1f],translation:[%.3ff,%.3ff,%.3ff],scale:[%.3ff,%.3ff,%.3ff]}}', global_gen,
        q:0, q:1, q:2, q:3, q:4, q:5, q:6));
      run(str('ride %s mount %s', query(d, 'uuid'), query(s, 'uuid')))
    )
  );
  global_theta = 270; global_th0 = 270; global_phase = 'stop'; global_t = 0;
  _wheel(global_theta, 0);
  _seats(global_theta);
  global_ready = true;
  'spawned'
);

// ───────────── motion ─────────────
// A display is drawn from its entity position (the axle): translation = the piece's centre turned by th, minus its
// half-size turned by th + phi (so it rotates about its own centre); rotation = quaternion about z by th + phi.
_tf(p, th) -> (
  pu = p:1; pv = p:2; zo = p:3; phi = p:4; sx = p:5; sy = p:6; sz = p:7;
  qx = pu * cos(th) - pv * sin(th); qy = pu * sin(th) + pv * cos(th);
  ps = th + phi;
  hx = sx / 2; hy = sy / 2;
  cx = cos(ps) * hx - sin(ps) * hy; cy = sin(ps) * hx + cos(ps) * hy;
  str('{translation:[%.4ff,%.4ff,%.4ff],left_rotation:[0f,0f,%.5ff,%.5ff],scale:[%.3ff,%.3ff,%.3ff],right_rotation:[0f,0f,0f,1f]}',
    qx - cx, qy - cy, zo - sz / 2, sin(ps / 2), cos(ps / 2), sx, sy, sz)
);

_wheel(th, dur) -> for (global_pieces,
  run(str('data merge entity %s {start_interpolation:0,interpolation_duration:%d,transformation:%s}', _:0, dur, _tf(_, th)))
);

_seat_pos(i, th) -> (a = th + i * global_STEP; [global_C:0 + global_RC * cos(a), global_C:1 + global_RC * sin(a) - global_DROP, global_C:2]);

_seats(th) -> for (global_seats,
  e = entity_id(_);
  if (e, p = _seat_pos(_i, th); modify(e, 'pos', p:0, p:1, p:2))
);

_bottom() -> (k = round((270 - global_theta) / global_STEP) % global_N; if (k < 0, k + global_N, k));

__on_tick() -> (
  if (!global_C, return());
  t = tick_time();
  if (t % 20 == 0, global_active = length(filter(player('all'), _real(_) && _ ~ 'dimension' == 'overworld'
    && abs(pos(_):0 - global_C:0) < 90 && abs(pos(_):2 - global_C:2) < 90)) > 0 || length(global_riders) > 0);
  if (!global_active, return());
  if (!global_ready, _spawn(); return());
  global_t += 1;
  if (global_phase == 'move',
    f = min(1, global_t / global_MOVE);
    _seats(global_th0 + global_STEP * _ease(f));
    if (global_t % global_UPD == 0 && global_t < global_MOVE,
      _wheel(global_th0 + global_STEP * _ease(min(1, (global_t + global_UPD) / global_MOVE)), global_UPD));
    if (global_t >= global_MOVE,
      global_theta = (global_th0 + global_STEP) % 360; global_phase = 'stop'; global_t = 0; _arrive()),
    // stopped: board / unload at the bottom
    if (global_t % 5 == 0, _board());
    if (global_t >= global_STOP,
      global_phase = 'move'; global_t = 0; global_th0 = global_theta;
      _wheel(global_th0 + global_STEP * _ease(global_UPD / global_MOVE), global_UPD);
      _snd('block.note_block.chime', 0.6, 1.2))
  );
  _check_riders();
  if (t % 10 == 0, _lights());
);

// ───────────── riders ─────────────
_put_down(n) -> (
  run(str('ride %s dismount', n));
  run(str('tp %s %.1f %.1f %.1f -90 0', n, global_exit:0, global_exit:1, global_exit:2))
);

_put_down_all() -> (
  for (values(global_riders), if (player(_:0), _put_down(_:0)));
  global_riders = {}
);

_arrive() -> (
  k = _bottom();
  for (keys(global_riders), r = global_riders:_; global_riders:_ = [r:0, r:1 + 1]);
  r = global_riders:k;
  if (r && r:1 >= global_N,
    delete(global_riders, k);
    n = r:0;
    _put_down(n);
    _msg(n, 'Thanks for riding the Ferris wheel!', 'gold');
    run(str('playsound minecraft:entity.player.levelup master %s', n))
  );
  _snd('block.note_block.bell', 0.8, 1.0)
);

_on_pad(p) -> (q = pos(p); b = global_pad; q:0 >= b:0 && q:0 < b:3 && q:2 >= b:2 && q:2 < b:5 && q:1 >= b:1 && q:1 < b:4);

_board() -> (
  k = _bottom();
  if (has(global_riders, k), return());
  seat = global_seats:k;
  for (player('all'),
    p = _; n = p ~ 'name';
    if (_real(p) && _on_pad(p) && !query(p, 'mount') && !first(values(global_riders), _:0 == n),
      run(str('ride %s mount %s', n, seat));
      global_riders:k = [n, 0];
      _msg(n, 'Enjoy the ride! Shift = get off', 'yellow');
      run(str('playsound minecraft:block.note_block.pling master %s', n));
      break()
    )
  )
);

// Shift dismounts in vanilla: put the player down safely instead of letting them drop from the cabin
_check_riders() -> for (keys(global_riders),
  k = _; r = global_riders:k; n = r:0; p = player(n);
  if (!p, delete(global_riders, k); continue());
  if (!query(p, 'mount'),
    delete(global_riders, k);
    run(str('tp %s %.1f %.1f %.1f -90 0', n, global_exit:0, global_exit:1, global_exit:2));
    _msg(n, 'You got off the wheel', 'gray')
  )
);

// ───────────── chasing lights ─────────────
_lights() -> (
  global_shift = (global_shift + 1) % 8;
  for (global_bulbs,
    run(str('data merge entity %s {block_state:{Name:"minecraft:%s_concrete"}}', _, global_colors:((_i + global_shift) % 8)))
  )
);
