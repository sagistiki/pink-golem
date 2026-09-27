// cars.sc — drivable cars, GTA-style, with no client mods (Sagi 26/9). Models: resource pack (gen_cars_pack.py),
// keys: the Key Bridge server mod (mcp-server/keybridge) writes each player's keys into the scoreboard "keys"
// (1 W · 2 S · 4 A · 8 D · 16 Space · 32 Shift · 64 Ctrl).
//
// A car = an item_display with the model (teleport_duration 2 → smooth), an interaction box (right-click = get in),
// a marker armor stand as the seat. Physics run here every tick, only for cars that have a driver or are still
// moving: throttle with a soft top speed, brakes, reverse, steering that scales with speed, grip on the tyres (the
// sideways slide decays) — Space pulls the handbrake: less grip, the tail slides out, you drift. Ctrl = boost.
// Solid blocks stop the car (bounce + crunch), 1-block steps are climbed, it falls off edges, grass slows it down,
// people in the way are pushed aside.
// Camera: "chase" (default) — you become a spectator of a camera that trails the car (GTA view), a mannequin with
// your skin sits at the wheel; "first" — you sit in the seat (F5 works as usual). /car view toggles it.
// Shift = get out (you are put next to the driver's door). An empty car away from its parking spot goes home after
// 3 minutes with nobody near. Test: set_keys('Name', bits) feeds keys to a fake player (no key bridge needed).
// Two seats: the first one in drives, a second one sits next to the driver (same views; the chase camera is shared,
// Shift gets out through the right door). If the driver gets out, the passenger stays and the next one in drives.

__config() -> {'stay_loaded' -> true, 'scope' -> 'global',
  'commands' -> {'view' -> 'cmd_view', 'home' -> 'cmd_home', 'here <model> <color>' -> ['cmd_here'], 'list' -> 'cmd_list'},
  'arguments' -> {'model' -> {'type' -> 'term', 'suggest' -> ['sedan', 'sports', 'suv', 'taxi', 'police']}, 'color' -> {'type' -> 'term', 'suggest' -> ['red', 'blue', 'white', 'black', 'yellow', 'pink']}}};
// HUD (hud.scl + the server pack's HUD fonts): speedometer bottom-right, compass top-centre while driving (26/9)
import('hud', 'hud_show', 'hud_hide', 'hud_speedo', 'hud_compass');

global_allow_fake = false;
global_MODEL_YAW = 180;         // added to the heading when drawing the model: the item model's nose points to -z (Sagi 26/9)
// model: [name, scale, top speed b/t, accel, turn deg/t at full lock, grip 0..1, camera distance, camera height, half length, half width]
global_M = {
  'sedan'  -> ['סדאן', 4.6, 1.05, 0.030, 4.2, 0.30, 7.6, 4.0, 2.1, 0.95],
  'sports' -> ['ספורט', 4.6, 1.35, 0.042, 4.6, 0.36, 7.4, 3.7, 2.1, 1.0],
  'suv'    -> ['ג\'יפ', 4.6, 0.95, 0.026, 3.8, 0.28, 8.2, 4.5, 2.1, 1.0],
  'taxi'   -> ['מונית', 4.6, 1.05, 0.030, 4.2, 0.30, 7.6, 4.0, 2.1, 0.95],
  'police' -> ['משטרה', 4.6, 1.20, 0.036, 4.4, 0.32, 7.6, 4.0, 2.1, 0.95]};
global_COL = {'red' -> 12597547, 'blue' -> 3949738, 'white' -> 15790320, 'black' -> 1908001, 'yellow' -> 16701501,
  'pink' -> 15961002, 'green' -> 6192150, 'orange' -> 16351261, 'purple' -> 8991416, 'silver' -> 10329495, 'cyan' -> 1481884};
global_ROAD_SLOW = {'grass_block' -> 0.72, 'dirt' -> 0.72, 'sand' -> 0.6, 'gravel' -> 0.75, 'moss_block' -> 0.72, 'mud' -> 0.5,
  'water' -> 0.3, 'farmland' -> 0.6, 'snow_block' -> 0.7};
global_ICE = {'ice' -> 1, 'packed_ice' -> 1, 'blue_ice' -> 1};
// seat -> [its camera mode key, its mannequin key, its seat entity key, its side: 1 = left]
global_SEAT = {'driver' -> ['mode', 'man', 'seat', 1], 'pass' -> ['pmode', 'pman', 'seat2', -1]};

global_cars = {};          // id -> car
global_gen = str('car_g%d', floor(rand(1000000000)));
global_view = {};          // name -> 'chase' | 'first'
global_fake_keys = {};
global_restore = {};
global_next = 1;
global_spawned = false;

__on_start() -> (
  v = read_file('views', 'json'); if (v, global_view = v);
  global_lot = read_file('lot', 'json');
  // several parking lots, each with its own fleet (Sagi 27/9: the Gabi Water car park too): cars.data/lot*.json
  global_lots = [];
  for (['lot', 'lot_gabiwater'], d = read_file(_, 'json'); if (d, global_lots += {'name' -> _, 'data' -> d, 'spawned' -> false}));
  r = read_file('restore', 'json'); if (r, global_restore = r);
  for (keys(global_restore), if (player(_), _restore_player(_)));
  for (['item_display', 'interaction', 'armor_stand', 'mannequin'],
    entity_load_handler(_, _(e, new) -> if (!new, schedule(0, '_stale', query(e, 'uuid')))))
);
_stale(u) -> (e = entity_id(u); if (e, t = query(e, 'scoreboard_tags'); if (t && (t ~ 'car') != null && (t ~ global_gen) == null, modify(e, 'remove'))));

_real(p) -> global_allow_fake || (p ~ 'player_type') != 'fake';
_msg(n, t, c) -> run(str('title %s actionbar %s', n, encode_json({'text' -> t, 'color' -> c, 'bold' -> true})));
_keys(n) -> (f = global_fake_keys:n; if (f != null, return(f)); k = scoreboard('keys', n); if (k == null, 0, k));
set_keys(n, bits) -> (global_fake_keys:n = bits; bits);
_bit(k, b) -> bitwise_and(k, b) != 0;
global_hold = {};
// Shift has to be HELD for 1.5 s to get out (Sagi 27/9: a tap is not enough); a bar shows the progress
_hold(n, k) -> (
  if (global_hold == null, global_hold = {});
  if (!_bit(k, 32), global_hold:n = 0; return(false));
  c = global_hold:n; if (c == null, c = 0); c += 1; global_hold:n = c;
  if (c % 3 == 0, f = floor(c / 3); _msg(n, str('%s %s יציאה', join('', map(range(10), if (_ < f, '▮', '▯'))), if (c >= 30, '✓', '')), 'yellow'));
  if (c >= 30, global_hold:n = 0; true, false)
);

// ───────────── spawning ─────────────
// spots: each lot file (cars.data/lot.json from the dealership, lot_gabiwater.json for the water park car park) =
// {center, spots: [[x, y, z, yaw, model, color], ...], show?}. A lot's fleet is built when a player comes near it; its
// cars carry the tag carlot_<name> and go home to their own bay.
_spawn_lot(L) -> (
  nm = L:'name';
  for (entity_selector('@e[tag=car]'), if (!query(_, 'has_tag', global_gen) || query(_, 'has_tag', 'carlot_' + nm), modify(_, 'remove')));
  for (keys(global_cars), if (global_cars:_:'lot' == nm, delete(global_cars, _)));
  if (nm == 'lot', for (entity_selector('@e[tag=car_show]'), modify(_, 'remove')));
  lot = L:'data';
  global_lot_name = nm;
  if (lot,
    for (lot:'spots', s = _; _new_car(s:4, s:5, [s:0, s:1, s:2], s:3, true));
    sh = lot:'show';
    if (sh, global_show = query(spawn('item_display', [sh:0, sh:1, sh:2], str('{Tags:["car","car_show","%s"],item:{id:"minecraft:paper",count:1,components:{"minecraft:item_model":"cars:%s","minecraft:dyed_color":%d}},teleport_duration:20,brightness:{sky:15,block:15},transformation:{left_rotation:[0f,0f,0f,1f],right_rotation:[0f,0f,0f,1f],translation:[0f,%.3ff,0f],scale:[%.2ff,%.2ff,%.2ff]}}',
      global_gen, sh:3, global_COL:(sh:4), global_M:(sh:3):1 / 2 + 0.3, global_M:(sh:3):1, global_M:(sh:3):1, global_M:(sh:3):1)), 'uuid')));
  global_lot_name = null;
  L:'spawned' = true;
  global_spawned = true
);
global_lot = null; global_show = null; global_lots = []; global_lot_name = null;

_new_car(model, color, q, yaw, home) -> (
  id = global_next; global_next += 1;
  m = global_M:model; if (!m, return(null));
  rgb = global_COL:color; if (rgb == null, rgb = number(color)); if (rgb == null, rgb = 15790320);
  tags = str('"car","car_%d","%s"%s', id, global_gen, if (global_lot_name, str(',"carlot_%s"', global_lot_name), ''));
  body = spawn('item_display', q, str('{Tags:[%s],item:{id:"minecraft:paper",count:1,components:{"minecraft:item_model":"cars:%s","minecraft:dyed_color":%d}},teleport_duration:2,Rotation:[%.1ff,0f],view_range:4f,shadow_radius:1.4f,shadow_strength:0.6f,transformation:{left_rotation:[0f,0f,0f,1f],right_rotation:[0f,0f,0f,1f],translation:[0f,%.3ff,0f],scale:[%.2ff,%.2ff,%.2ff]}}',
    tags, model, rgb, yaw + global_MODEL_YAW, m:1 / 2, m:1, m:1, m:1));
  hit = spawn('interaction', q, str('{Tags:[%s],width:%.2ff,height:1.6f,response:1b}', tags, m:9 * 2 + 0.2));
  seat_nbt = str('{Tags:[%s],Marker:1b,Invisible:1b,NoGravity:1b,Invulnerable:1b,Rotation:[%.1ff,0f]}', tags, yaw);
  seat = spawn('armor_stand', q, seat_nbt);
  seat2 = spawn('armor_stand', q, seat_nbt);
  c = {'id' -> id, 'model' -> model, 'color' -> color, 'body' -> query(body, 'uuid'), 'hit' -> query(hit, 'uuid'),
       'seat' -> query(seat, 'uuid'), 'seat2' -> query(seat2, 'uuid'),
       'x' -> q:0, 'y' -> q:1, 'z' -> q:2, 'h' -> yaw, 'vx' -> 0, 'vz' -> 0, 'vy' -> 0, 'steer' -> 0,
       'driver' -> null, 'cam' -> null, 'man' -> null, 'mode' -> null, 'pass' -> null, 'pman' -> null, 'pmode' -> null, 'idle' -> 0,
       'home' -> if (home, [q:0, q:1, q:2, yaw], null), 'lot' -> global_lot_name};
  global_cars:id = c;
  _place(c, 0);
  id
);

_car_of_entity(e) -> (t = parse_nbt(query(e, 'nbt', 'Tags')); if (!t, return(null)); for (t, if (_ ~ '^car_\\d+$', return(number(slice(_, 4))))); null);

// ───────────── getting in / out ─────────────
__on_player_interacts_with_entity(p, e, hand) -> (
  if (hand != 'mainhand' || query(e, 'type') != 'interaction', return());
  id = _car_of_entity(e); if (id == null, return());
  c = global_cars:id; n = p ~ 'name';
  if (!c || _seat_of(n), return());
  if (c:'driver' && c:'pass', _msg(n, 'הרכב מלא', 'red'); return());
  enter(n, id)
);

// [car, 'driver' | 'pass'] for someone sitting in a car, else null
_seat_of(n) -> (for (values(global_cars), c = _; for (['driver', 'pass'], if (c:_ == n, return([c, _])))); null);

// the first one in drives, a second one sits next to the driver
enter(n, id) -> (
  p = player(n); c = global_cars:id; if (!p || !c || _seat_of(n), return('no'));
  r = if (!c:'driver', 'driver', !c:'pass', 'pass', return('full'));
  global_restore:n = {'mode' -> p ~ 'gamemode'}; write_file('restore', 'json', global_restore);
  c:r = n; c:'idle' = 0;
  mode = global_view:n; if (mode == null, mode = 'chase');
  _set_view(c, r, mode);
  name = global_M:(c:'model'):0;
  if (r == 'driver',
    _msg(n, str('%s · W/S גז-בלם · A/D הגה · רווח = בלם יד (דריפט) · Ctrl = טורבו · החזק Shift 1.5 שניות = לצאת · /cars view = מצלמה', name), 'yellow'),
    _msg(n, str('%s · במושב ליד %s · החזק Shift 1.5 שניות = לצאת · /cars view = מצלמה', name, c:'driver'), 'yellow');
    _msg(c:'driver', str('%s במושב שלידך', n), 'light_purple'));
  run(str('playsound minecraft:block.iron_door.close master @a %.1f %.1f %.1f 0.8 1.4', c:'x', c:'y', c:'z'));
  r
);

_set_view(c, r, mode) -> (
  [km, kman, kseat, side] = global_SEAT:r;
  n = c:r; p = player(n);
  _drop_man(c, r);
  c:km = mode;
  if (mode == 'chase',
    _cam(c);
    tags = str('"car","car_%d","%s"', c:'id', global_gen);
    prof = if ((p ~ 'player_type') != 'fake', str(',profile:{name:"%s"}', n), '');
    man = spawn('mannequin', [c:'x', c:'y', c:'z'], str('{Tags:[%s],immovable:1b,hide_description:1b,Invulnerable:1b%s}', tags, prof));
    c:kman = query(man, 'uuid');
    run(str('ride %s mount %s', c:kman, c:kseat));
    if (query(p, 'mount'), run(str('ride %s dismount', n)));
    run(str('gamemode spectator %s', n));
    schedule(2, '_spectate', n, c:'cam'),
    // first person: sit in the seat
    run(str('gamemode %s %s', global_restore:n:'mode', n));
    run(str('ride %s mount %s', n, c:kseat))
  );
  _cam_check(c)
);
_spectate(n, u) -> run(str('spectate %s %s', u, n));

// the chase camera: one per car, shared by everyone in it who uses the chase view
_cam(c) -> (
  if (c:'cam' && entity_id(c:'cam'), return());
  m = global_M:(c:'model');
  tags = str('"car","car_%d","%s"', c:'id', global_gen);
  cq = _cam_target(c); c:'ch' = c:'h';
  cam = spawn('item_display', cq, str('{Tags:[%s],teleport_duration:2,Rotation:[%.1ff,%.1ff]}', tags, c:'h', atan2(m:7 - 1, m:6)));
  c:'cam' = query(cam, 'uuid'); c:'cq' = cq
);
_cam_check(c) -> (
  if (c:'cam' && c:'mode' != 'chase' && c:'pmode' != 'chase',
    e = entity_id(c:'cam'); if (e, modify(e, 'remove')); c:'cam' = null)
);
_drop_man(c, r) -> (k = global_SEAT:r:1; u = c:k; if (u, e = entity_id(u); if (e, modify(e, 'remove'))); c:k = null);

// someone vanished (logged out): free the seat
_gone(c, r) -> (n = c:r; _drop_man(c, r); hud_hide(n); c:r = null; k = global_SEAT:r:0; c:k = null; _cam_check(c));

leave(id) -> (c = global_cars:id; if (c, _out(c, 'driver')));

_out(c, r) -> (
  n = c:r; if (!n, return());
  side = global_SEAT:r:3; p = player(n);
  _gone(c, r);
  if (r == 'driver',
    c:'vx' = 0; c:'vz' = 0;                                                      // parked: it does not roll on without a driver
    if (c:'pass', _hud(c, 0)));
  if (p,
    if (query(p, 'mount'), run(str('ride %s dismount', n)));
    run(str('execute as %s run spectate', n));                                  // stop following the camera first
    rs = global_restore:n; if (rs, run(str('gamemode %s %s', rs:'mode', n)); delete(global_restore, n); write_file('restore', 'json', global_restore));
    modify(p, 'flying', false);                                                  // spectator → creative keeps flying on
    // out through your own door (driver left, passenger right), on the ground — once the game mode has switched
    h = c:'h'; ox = c:'x' + side * cos(h) * 1.8; oz = c:'z' + side * sin(h) * 1.8;
    schedule(2, '_put_down', n, ox, c:'y', oz, h));
  run(str('playsound minecraft:block.iron_door.open master @a %.1f %.1f %.1f 0.8 1.3', c:'x', c:'y', c:'z'))
);

_put_down(n, x, y, z, h) -> (
  p = player(n); if (!p, return());
  gy = floor(y); while (_solid(floor(x), gy, floor(z)) || _solid(floor(x), gy + 1, floor(z)), 6, gy += 1);   // not inside a wall / another car
  while (!_solid(floor(x), gy - 1, floor(z)) && gy > y - 6, 6, gy += -1);                               // down to the ground
  modify(p, 'flying', false);
  run(str('tp %s %.2f %d %.2f %.1f 0', n, x, gy, z, h))
);

_restore_player(n) -> (r = global_restore:n; if (r && player(n), run(str('gamemode %s %s', r:'mode', n)); delete(global_restore, n); write_file('restore', 'json', global_restore)));

cmd_view() -> (
  p = player(); n = p ~ 'name';
  v = if (global_view:n == 'first', 'chase', 'first'); global_view:n = v; write_file('views', 'json', global_view);
  s = _seat_of(n); if (s, _set_view(s:0, s:1, v));
  if (v == 'first', 'מצלמה: גוף ראשון (F5 לגוף שלישי)', 'מצלמה: מרדף מאחורי הרכב')
);
cmd_home() -> (p = player(); s = _seat_of(p ~ 'name'); if (s && s:1 == 'driver', c = s:0; _out(c, 'pass'); _out(c, 'driver'); _go_home(c)); 'ok');
cmd_here(model, color) -> (p = player(); q = pos(p); if (!global_M:model, return('models: ' + join(', ', keys(global_M)))); id = _new_car(model, color, q, query(p, 'yaw'), false); str('car %d', id));
cmd_list() -> map(values(global_cars), str('%d %s %s %s %s', _:'id', _:'model', _:'color', if (_:'driver', _:'driver', '-'), if (_:'pass', _:'pass', '-')));

__on_player_disconnects(p, r) -> (s = _seat_of(p ~ 'name'); if (s, _gone(s:0, s:1)));
__on_player_connects(p) -> (n = p ~ 'name'; if (has(global_restore, n), schedule(20, '_restore_player', n)));

// ───────────── the loop ─────────────
__on_tick() -> (
  t = tick_time();
  // build each lot's fleet only with a player near it (its chunks are loaded, old copies can be removed)
  if (t % 20 == 0, for (global_lots, L = _; if (!L:'spawned',
    ctr = L:'data':'center';
    if (first(player('all'), _real(_) && (!ctr || abs(pos(_):0 - ctr:0) < 96 && abs(pos(_):2 - ctr:1) < 96)) != null, _spawn_lot(L)))));
  if (!global_spawned, return());
  if (global_show && t % 20 == 0, e = entity_id(global_show); if (e, sh = global_lot:'show'; modify(e, 'location', sh:0, sh:1, sh:2, (t / 20 * 18) % 360, 0)));
  for (values(global_cars),
    c = _;
    if (c:'pass', _pass_tick(c));
    if (c:'driver',
      p = player(c:'driver');
      if (!p, _gone(c, 'driver'); continue());
      k = _keys(c:'driver');
      // a Shift TAP makes the game itself stop spectating (chase view) or stand you up out of the seat (first person): put it back at once,
      // only a HELD Shift (1.5 s, in either view) gets you out
      if (c:'mode' == 'chase' && _bit(k, 32), _spectate(c:'driver', c:'cam'));
      if (_hold(c:'driver', k), leave(c:'id'); continue());
      if (c:'mode' == 'first' && !query(p, 'mount'), run(str('ride %s mount %s', c:'driver', c:'seat')));
      _drive(c, k, t),
      if (abs(c:'vx') + abs(c:'vz') > 0.005 || c:'vy' != 0, _drive(c, 0, t),
        if (c:'home' && !c:'pass' && t % 200 == 0, _maybe_home(c)))
    )
  )
);

// the passenger gets out with Shift in the chase view, or by standing up in first person
_pass_tick(c) -> (
  n = c:'pass'; p = player(n);
  if (!p, _gone(c, 'pass'); return());
  k = _keys(n);
  if (c:'pmode' == 'chase' && _bit(k, 32), _spectate(n, c:'cam'));
  if (_hold(n, k), _out(c, 'pass'),
    c:'pmode' == 'first' && !query(p, 'mount'), run(str('ride %s mount %s', n, c:'seat2')))
);

_maybe_home(c) -> (
  hm = c:'home';
  if ((c:'x' - hm:0) ^ 2 + (c:'z' - hm:2) ^ 2 < 4, c:'idle' = 0; return());
  c:'idle' = c:'idle' + 200;
  if (c:'idle' >= 3600 && first(player('all'), _distance(pos(_), [c:'x', c:'y', c:'z']) < 24) == null, _go_home(c))
);
_go_home(c) -> (hm = c:'home'; if (!hm, return()); c:'x' = hm:0; c:'y' = hm:1; c:'z' = hm:2; c:'h' = hm:3; c:'vx' = 0; c:'vz' = 0; c:'vy' = 0; c:'idle' = 0; _place(c, 0));
_distance(a, b) -> sqrt((a:0 - b:0) ^ 2 + (a:2 - b:2) ^ 2);

_solid(x, y, z) -> (b = block(x, y, z); !air(b) && solid(b));

// ───────────── physics ─────────────
_drive(c, k, t) -> (
  m = global_M:(c:'model');
  h = c:'h'; vx = c:'vx'; vz = c:'vz';
  gas = _bit(k, 1); brk = _bit(k, 2); left = _bit(k, 4); right = _bit(k, 8); hand = _bit(k, 16); boost = _bit(k, 64);
  under = str(block(floor(c:'x'), floor(c:'y') - 1, floor(c:'z')));
  slow = global_ROAD_SLOW:under; if (slow == null, slow = 1);
  ice = has(global_ICE, under);
  vmax = m:2 * slow * if (boost, 1.35, 1);
  acc = m:3 * if (boost, 1.5, 1);
  // 1) the wheel turns the NOSE, in proportion to the speed along it; less lock at high speed
  vf0 = vx * -sin(h) + vz * cos(h);
  want = if (right, 1, 0) - if (left, 1, 0);
  c:'steer' = c:'steer' + (want - c:'steer') * 0.35;
  sp = abs(vf0);
  turn = c:'steer' * m:4 * min(1, sp / 0.28) * (1 - 0.4 * min(1, sp / m:2)) * if (hand, 1.45, 1);
  if (vf0 < 0, turn = -turn);
  h = h + turn;
  // 2) the momentum did not turn: split it along the new nose (vf) and sideways (vr = slip)
  fx = -sin(h); fz = cos(h); rx = -cos(h); rz = -sin(h);
  vf = vx * fx + vz * fz; vr = vx * rx + vz * rz;
  // 3) engine / brakes along the nose
  if (gas, vf = vf + acc * max(0.05, 1 - vf / vmax),
    brk, if (vf > 0.04, vf = vf - 0.065, vf = max(-0.32, vf - acc * 0.7)),
    vf = vf * 0.985; if (abs(vf) < 0.004, vf = 0));
  if (vf > vmax, vf = vf * 0.96);
  // handbrake: a real brake on the rear wheels — alone it stops the car in about a second, with W + A/D it drifts
  if (hand, vf = if (abs(vf) <= 0.035, 0, vf - 0.035 * if (vf > 0, 1, -1)));
  // 4) the tyres pull the slip back to zero — the handbrake (or ice) lets the tail slide out: a drift
  grip = m:5 * if (hand && abs(vf) > 0.12, 0.12, 1) * if (ice, 0.25, 1);
  // part of the slip that the tyres kill becomes forward speed again (a drift exits with speed)
  vf = vf + abs(vr) * grip * 0.25 * if (vf < 0, -1, 1);
  vr = vr * (1 - grip);
  vx = vf * fx + vr * rx; vz = vf * fz + vr * rz;
  // move, collide
  x = c:'x'; y = c:'y'; z = c:'z';
  nx = x + vx; nz = z + vz;
  hit = _blocked(c, m, nx, y, nz, h);
  if (hit == 1,
    // a 1-block step: climb it
    if (!_blocked_at(c, m, nx, y + 1, nz, h), y = y + 1; vx = vx * 0.8; vz = vz * 0.8, hit = 2));
  if (hit == 2,
    s2 = sqrt(vx * vx + vz * vz);
    if (s2 > 0.3,
      run(str('playsound minecraft:entity.generic.explode master @a %.1f %.1f %.1f %.2f 1.8', x, y, z, min(1, s2)));
      run(str('particle minecraft:crit %.1f %.1f %.1f 0.6 0.4 0.6 0.2 20', x + fx * m:8, y + 0.8, z + fz * m:8)));
    vx = -vx * 0.25; vz = -vz * 0.25; nx = x; nz = z);
  // ground: fall off edges, land on the next floor
  gy = floor(y);
  if (!_solid(floor(nx), gy - 1, floor(nz)) && !_solid(floor(nx + fx * m:8 * 0.7), gy - 1, floor(nz + fz * m:8 * 0.7)) && !_solid(floor(nx - fx * m:8 * 0.7), gy - 1, floor(nz - fz * m:8 * 0.7)),
    vy = max(-1.5, c:'vy' - 0.08); ny = y + vy;
    if (_solid(floor(nx), floor(ny), floor(nz)), ny = floor(ny) + 1; vy = 0);       // landed
    y = ny; c:'vy' = vy,
    c:'vy' = 0; y = gy);
  // animals / mobs in the way get pushed aside (players never)
  if (sqrt(vx * vx + vz * vz) > 0.15 && t % 2 == 0,
    for (entity_selector(str('@e[x=%.1f,y=%.1f,z=%.1f,distance=..%.1f]', nx + fx * m:8 * 0.6, y + 0.5, nz + fz * m:8 * 0.6, m:9 + 0.6)),
      e = _;
      if (query(e, 'health') == null || query(e, 'type') ~ 'player|armor_stand|mannequin', continue());   // never push players
      modify(e, 'motion', vx * 1.6 + rx * 0.3, 0.35, vz * 1.6 + rz * 0.3);
      vx = vx * 0.8; vz = vz * 0.8));
  c:'x' = nx; c:'y' = y; c:'z' = nz; c:'h' = h; c:'vx' = vx; c:'vz' = vz;
  _place(c, t);
  // sounds and effects
  s = sqrt(vx * vx + vz * vz);
  if (c:'driver' && t % 5 == 0 && (gas || s > 0.05),
    run(str('playsound minecraft:entity.minecart.riding neutral @a %.1f %.1f %.1f %.2f %.2f', nx, y + 0.5, nz, 0.25 + s * 0.4, 0.5 + s * 1.1)));
  if (abs(vr) > 0.18 && s > 0.3,
    run(str('particle minecraft:white_smoke %.2f %.2f %.2f 0.4 0.05 0.4 0.01 3', nx - fx * m:8, y + 0.1, nz - fz * m:8));
    if (t % 4 == 0, run(str('playsound minecraft:block.sand.break neutral @a %.1f %.1f %.1f 0.6 0.6', nx, y, nz))));
  if (boost && gas && t % 2 == 0, run(str('particle minecraft:flame %.2f %.2f %.2f 0.1 0.05 0.1 0.01 2', nx - fx * (m:8 + 0.3), y + 0.4, nz - fz * (m:8 + 0.3))));
  if ((c:'driver' || c:'pass') && t % 4 == 0, _hud(c, s));
  if (c:'driver' && t % 10 == 0 && (hand || (boost && gas)),
    _msg(c:'driver', if (hand, 'דריפט!', 'טורבו!'), if (hand, 'light_purple', 'gold')))
);

// the speedometer and compass, for everyone in the car
_hud(c, s) -> (
  els = [hud_speedo(round(s * 72), 160, 'KM/H', 'bottom_right'), hud_compass(c:'h', 'top_centre')];
  for (['driver', 'pass'], if (c:_, hud_show(c:_, els)))
);

// 0 = free, 1 = a step (the lower corner blocks are solid but the car could climb), 2 = a wall
_blocked(c, m, x, y, z, h) -> (
  if (_blocked_at(c, m, x, y, z, h), 1, 0)
);
_blocked_at(c, m, x, y, z, h) -> (
  fx = -sin(h); fz = cos(h); rx = -cos(h); rz = -sin(h);
  L = m:8; W = m:9;
  for ([[L, 0], [L, W * 0.9], [L, -W * 0.9], [-L, W * 0.9], [-L, -W * 0.9], [L * 0.5, W], [L * 0.5, -W], [-L * 0.5, W], [-L * 0.5, -W]],
    px = x + fx * _:0 + rx * _:1; pz = z + fz * _:0 + rz * _:1;
    if (_solid(floor(px), floor(y), floor(pz)) || _solid(floor(px), floor(y) + 1, floor(pz)), return(true)));
  false
);

// move every part; the camera trails the car with a little lag
_place(c, t) -> (
  x = c:'x'; y = c:'y'; z = c:'z'; h = c:'h';
  e = entity_id(c:'body'); if (e, modify(e, 'location', x, y, z, h + global_MODEL_YAW, 0));
  e = entity_id(c:'hit'); if (e, modify(e, 'pos', x, y, z));
  e = entity_id(c:'seat'); if (e, modify(e, 'location', x - sin(h) * 0.15 + cos(h) * 0.45, y + 0.35, z + cos(h) * 0.15 + sin(h) * 0.45, h, 0));   // driver's seat: left, a bit forward
  e = entity_id(c:'seat2'); if (e, modify(e, 'location', x - sin(h) * 0.15 - cos(h) * 0.45, y + 0.35, z + cos(h) * 0.15 - sin(h) * 0.45, h, 0));  // passenger: right
  if (c:'cam',
    // the camera sits exactly behind the car's position (it moves with the same interpolation as the car, so the car
    // never shakes on screen); only its heading follows the car's heading softly, so turns feel smooth
    dh = ((h - c:'ch') % 360 + 540) % 360 - 180; c:'ch' = c:'ch' + dh * 0.18;
    m = global_M:(c:'model'); ch = c:'ch';
    cq = [x + sin(ch) * m:6, y + m:7, z - cos(ch) * m:6];
    yaw = ch; pitch = atan2(m:7 - 1, m:6);
    e = entity_id(c:'cam'); if (e, modify(e, 'location', cq:0, cq:1, cq:2, yaw, pitch));
    for (['man', 'pman'], if (c:_, _man_fix(c:_, h, yaw, pitch * 0.6))))
);

// The driver mannequin sits (it rides the seat), so the game ignores a direct body_yaw and only keeps the body within
// 50° of the entity's own yaw. Push the yaw 50° past the car's heading on the side the body lags: the clamp then
// drags the body exactly onto the heading. The head follows the camera.
_man_fix(u, h, yawcam, pitch) -> (
  e = entity_id(u); if (!e, return());
  d = ((h - query(e, 'body_yaw')) % 360 + 540) % 360 - 180;
  modify(e, 'yaw', h + if (abs(d) < 0.5, 0, d > 0, 50, -50));
  modify(e, 'head_yaw', yawcam); modify(e, 'pitch', pitch)
);
_cam_target(c) -> (m = global_M:(c:'model'); h = c:'h'; [c:'x' + sin(h) * m:6, c:'y' + m:7, c:'z' - cos(h) * m:6]);
