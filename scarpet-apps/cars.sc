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
// CALL (Sagi 27/9): C in the Bulbul Map mod (or /cars call) sends a random car of the fleet to you: it materialises far away (55-85
// blocks, on a road when there is one), drives to you by itself (a flood-fill over open ground + line-of-sight smoothing, the
// AI presses the same keys a driver would), stops a few blocks short of you, honks twice and tells you. No way through = it
// comes as close as it can. One call per player, a few at a time on the server, presses are rate-limited. See "the call" below.
// Two seats: the first one in drives, a second one sits next to the driver (same views; the chase camera is shared,
// Shift gets out through the right door). If the driver gets out, the passenger stays and the next one in drives.

__config() -> {'stay_loaded' -> true, 'scope' -> 'global',
  'commands' -> {'view' -> 'cmd_view', 'home' -> 'cmd_home', 'call' -> 'cmd_call', 'key' -> 'cmd_key', 'here <model> <color>' -> ['cmd_here'], 'list' -> 'cmd_list'},
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
  run('kill @e[tag=car_ai]');
  global_SPIRAL = []; for (range(-20, 21), i = _; for (range(-20, 21), put(global_SPIRAL, null, [i, _])));
  global_SPIRAL = sort_key(global_SPIRAL, _:0 * _:0 + _:1 * _:1);
  global_RING = []; for (range(-2, 3), i = _; for (range(-2, 3), if (i != 0 || _ != 0, put(global_RING, null, [i, _]))));
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
global_ai_tag = false;
global_lot = null; global_show = null; global_lots = []; global_lot_name = null;

_new_car(model, color, q, yaw, home) -> (
  id = global_next; global_next += 1;
  m = global_M:model; if (!m, return(null));
  rgb = global_COL:color; if (rgb == null, rgb = number(color)); if (rgb == null, rgb = 15790320);
  tags = str('"car","car_%d","%s"%s%s', id, global_gen, if (global_lot_name, str(',"carlot_%s"', global_lot_name), ''), if (global_ai_tag, ',"car_ai"', ''));
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
  if (c:'owner' && c:'owner' != n && c:'lock' && unix_time() < c:'lock' && !c:'driver', _msg(n, str('הרכב הוזמן על ידי %s', c:'owner'), 'yellow'); return());
  enter(n, id)
);

// [car, 'driver' | 'pass'] for someone sitting in a car, else null
_seat_of(n) -> (for (values(global_cars), c = _; for (['driver', 'pass'], if (c:_ == n, return([c, _])))); null);

// the first one in drives, a second one sits next to the driver
enter(n, id) -> (
  p = player(n); c = global_cars:id; if (!p || !c || _seat_of(n), return('no'));
  r = if (!c:'driver', 'driver', !c:'pass', 'pass', return('full'));
  global_restore:n = {'mode' -> p ~ 'gamemode'}; write_file('restore', 'json', global_restore);
  if (c:'ai', _ai_taken(c));
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

__on_player_disconnects(p, r) -> (n = p ~ 'name'; s = _seat_of(n); if (s, _gone(s:0, s:1)); cl = global_calls:n; if (cl && cl:'car', c = global_cars:(cl:'car'); if (c && c:'ai', _ai_dismiss(c))); if (cl && !cl:'car', cl:'phase' = 'done'; delete(global_calls, n)));
__on_player_connects(p) -> (n = p ~ 'name'; if (has(global_restore, n), schedule(20, '_restore_player', n)));

// ───────────── the loop ─────────────
__on_tick() -> (
  t = tick_time();
  // build each lot's fleet only with a player near it (its chunks are loaded, old copies can be removed)
  if (t % 20 == 0, for (global_lots, L = _; if (!L:'spawned',
    ctr = L:'data':'center';
    if (first(player('all'), _real(_) && (!ctr || abs(pos(_):0 - ctr:0) < 96 && abs(pos(_):2 - ctr:1) < 96)) != null, _spawn_lot(L)))));
  if (!global_spawned && !length(global_cars) && !length(global_plans), return());     // (called cars also run before any lot was built)
  if (global_show && t % 20 == 0, e = entity_id(global_show); if (e, sh = global_lot:'show'; modify(e, 'location', sh:0, sh:1, sh:2, (t / 20 * 18) % 360, 0)));
  for (global_plans, _plan_step(_));
  global_plans = filter(global_plans, _:'phase' != 'done');
  for (values(global_cars),
    c = _;
    if (c:'ai', _ai(c, t); continue());
    if (c:'temp' && !c:'driver' && !c:'pass' && t % 40 == 0, _temp_check(c));
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

// ───────────── the call: a car that drives up to you ─────────────
global_PLANE = -60;            // the car level of the city (grass/road top is y -61)
global_calls = {};             // owner -> the call {owner, phase, car}
global_call_last = {};         // owner -> unix ms of the last press (rate limit)
global_call_msg = {};          // owner -> unix ms of the last "already on its way" line
global_plans = [];             // calls that are still being planned (a slice of work per tick)
global_CALL_MAX = 4;           // cars on their way at once, server wide
global_PLAN_MAX = 2;           // plans in progress at once
global_SPIRAL = []; global_RING = [];
global_N8 = [[1, 0], [-1, 0], [0, 1], [0, -1], [1, 1], [1, -1], [-1, 1], [-1, -1]];
global_WAIT_MS = 180000;       // a car nobody gets into leaves after 3 minutes
global_LOCK_MS = 90000;        // for the first 90 s only the caller may get in

_key(i, j) -> (i + 5000) * 10000 + j + 5000;
// a 5x5 patch of open ground under the open sky: the car fits (cell centre = block (2i, 2j))
_ok_cell(bx, bz) -> (
  y = global_PLANE;
  if (!loaded(bx, y, bz), return(false));
  if (!_solid(bx, y - 1, bz) || _solid(bx, y, bz) || _solid(bx, y + 1, bz) || top('motion', bx, 0, bz) > y, return(false));      // open sky: never into a hall or under a roof
  for (global_RING, x = bx + _:0; z = bz + _:1; if (!_solid(x, y - 1, z) || _solid(x, y, z) || _solid(x, y + 1, z), return(false)));
  true
);

cmd_call() -> _call_player(player());
_call_player(p) -> (
  if (!p, return(null));
  n = p ~ 'name';
  if ((p ~ 'player_type') == 'fake' && !global_allow_fake, return(null));
  now = unix_time();
  if (global_call_last:n && now - global_call_last:n < 2500, return(null));            // key spam: ignored silently
  global_call_last:n = now;
  if ((p ~ 'dimension') != 'overworld' || (p ~ 'gamemode') == 'spectator', return(null));
  if (_seat_of(n), _msg(n, 'אתה כבר ברכב', 'yellow'); return(null));
  cl = global_calls:n;
  if (cl, (
    if (!global_call_msg:n || now - global_call_msg:n > 4000, (global_call_msg:n = now; _msg(n, 'הרכב שלך כבר בדרך, רגע...', 'yellow')));
    return(null)));
  if (length(global_calls) >= global_CALL_MAX || length(global_plans) >= global_PLAN_MAX, _msg(n, 'כל הרכבים בדרך, נסה שוב בעוד רגע', 'yellow'); return(null));
  q = pos(p);
  _call_begin(n, q:0, q:2);
  null
);
_call_begin(owner, x, z) -> (
  cl = {'owner' -> owner, 'phase' -> 'seed', 'q' -> [x, z], 'sp' -> 0, 'car' -> null};
  global_calls:owner = cl;
  put(global_plans, null, cl);
  _msg(owner, 'מזמין רכב...', 'aqua')
);
// test without a player: script in cars run test_call('Nobody', x, z)
test_call(owner, x, z) -> (_call_begin(owner, x, z); 'planning');

_plan_fail(pl, text) -> (pl:'phase' = 'done'; delete(global_calls, pl:'owner'); _msg(pl:'owner', text, 'red'));
_plan_step(pl) -> (
  ph = pl:'phase';
  if (ph == 'seed', _seed_step(pl), ph == 'flood', _flood_step(pl), ph == 'choose', _plan_choose(pl))
);

// 1) the nearest open ground to the player (spiral over cells, a slice per tick)
_seed_step(pl) -> (
  q = pl:'q'; ci = round(q:0 / 2); cj = round(q:1 / 2);
  n = 0;
  while (pl:'sp' < length(global_SPIRAL) && n < 60, 100000, (
    o = global_SPIRAL:(pl:'sp'); pl:'sp' = pl:'sp' + 1; n = n + 1;
    i = ci + o:0; j = cj + o:1;
    if (_ok_cell(i * 2, j * 2), (
      k = _key(i, j);
      pl:'seed' = [i, j]; pl:'phase' = 'flood';
      pl:'seen' = {k -> true}; pl:'par' = {}; pl:'cells' = {k -> [i, j]}; pl:'queue' = [[i, j]]; pl:'far' = []; pl:'head' = 0;
      return()
    ))
  ));
  if (pl:'sp' >= length(global_SPIRAL), _plan_fail(pl, 'אין מקום לרכב בקרבת מקום'))
);

// 2) flood the open ground around the seed (breadth first, 8 neighbours), noting cells 55+ blocks from the player
_flood_step(pl) -> (
  S = pl:'seen'; P = pl:'par'; C = pl:'cells'; Q = pl:'queue'; F = pl:'far';
  qx = pl:'q':0; qz = pl:'q':1;
  budget = 70;
  while (pl:'head' < length(Q) && budget > 0 && length(F) < 40 && length(Q) < 3500, 100000, (
    cur = Q:(pl:'head'); pl:'head' = pl:'head' + 1;
    for (global_N8, (
      ni = cur:0 + _:0; nj = cur:1 + _:1; k = _key(ni, nj);
      if (S:k == null, (
        bx = ni * 2; bz = nj * 2;
        if (abs(bx - qx) > 110 || abs(bz - qz) > 110, S:k = false, (
          budget = budget - 1;
          ok = _ok_cell(bx, bz);
          S:k = ok;
          if (ok, (
            P:k = _key(cur:0, cur:1); C:k = [ni, nj]; put(Q, null, [ni, nj]);
            if ((bx - qx) ^ 2 + (bz - qz) ^ 2 >= 3025, put(F, null, [ni, nj]))
          ))
        ))
      ))
    ))
  ));
  if (pl:'head' >= length(Q) || length(F) >= 40 || length(Q) >= 3500, pl:'phase' = 'choose')
);

// 3) pick a start (a road cell far away when there is one), walk the parents back to the seed, smooth, spawn
_plan_choose(pl) -> (
  q = pl:'q'; C = pl:'cells'; P = pl:'par'; F = pl:'far'; seed = pl:'seed';
  start = null;
  if (length(F) > 0, (
    for (range(10), f = F:(floor(rand(length(F)))); if (start == null && str(block(f:0 * 2, global_PLANE - 1, f:1 * 2)) ~ 'black_terracotta', start = f));
    if (start == null, start = F:(floor(rand(length(F)))))
  ), (
    bd = -1;
    for (values(C), d = (_:0 * 2 - q:0) ^ 2 + (_:1 * 2 - q:1) ^ 2; if (d > bd, (bd = d; start = _)))
  ));
  if (start == null, start = seed);
  pts = []; cur = start; done = false; guard = 0;
  while (!done && guard < 3000, 3000, (
    put(pts, null, [cur:0 * 2 + 0.5, cur:1 * 2 + 0.5]);
    if (cur:0 == seed:0 && cur:1 == seed:1, done = true, (
      pk = P:(_key(cur:0, cur:1));
      if (pk == null, done = true, cur = C:pk)
    ));
    guard = guard + 1
  ));
  // stop about 4 blocks short of the player, not on top of them
  cut = 0; while (length(pts) > 3 && cut < 2, 5, (pts = slice(pts, 0, length(pts) - 1); cut = cut + 1));
  pts = _smooth(pts, pl:'seen');
  pl:'phase' = 'done';
  _spawn_ai(pl, pts)
);

_los(a, b, S) -> (
  dx = b:0 - a:0; dz = b:1 - a:1; n = ceil(sqrt(dx * dx + dz * dz));
  for (range(1, n), f = _ / n; if (S:(_key(round((a:0 + dx * f - 0.5) / 2), round((a:1 + dz * f - 0.5) / 2))) != true, return(false)));
  true
);
_smooth(pts, S) -> (
  out = [pts:0]; i = 0; n = length(pts);
  while (i < n - 1, 1000, (
    j = n - 1;
    while (j > i + 1 && !_los(pts:i, pts:j, S), 1000, j = j - 1);
    put(out, null, pts:j); i = j
  ));
  out
);

_spawn_ai(pl, pts) -> (
  owner = pl:'owner';
  models = keys(global_M); model = models:(floor(rand(length(models))));
  cols = keys(global_COL); color = cols:(floor(rand(length(cols))));
  p0 = pts:0;
  p1 = if (length(pts) > 1, pts:1, pl:'q');
  h = atan2(-(p1:0 - p0:0), p1:1 - p0:1);
  global_ai_tag = true;
  id = _new_car(model, color, [p0:0, global_PLANE, p0:1], h, false);
  global_ai_tag = false;
  c = global_cars:id;
  if (!c, delete(global_calls, owner); return());
  n = length(pts); rem = []; for (range(n), put(rem, null, 0));
  for (range(n - 2, -1, -1), rem:_ = rem:(_ + 1) + sqrt((pts:(_ + 1):0 - pts:_:0) ^ 2 + (pts:(_ + 1):1 - pts:_:1) ^ 2));
  c:'ai' = {'owner' -> owner, 'path' -> pts, 'rem' -> rem, 'i' -> if (n > 1, 1, 0), 'state' -> 'appear', 'go' -> tick_time() + 26,
            'last' -> [p0:0, p0:1], 'lastt' -> tick_time(), 'stuck' -> 0, 'rev' -> 0, 'near' -> false, 'test' -> (owner ~ '^Test') != null};
  c:'owner' = owner;
  pl_call = global_calls:owner; if (pl_call, pl_call:'car' = id);
  _fade(c, 0.03, 0.03, 0); schedule(3, '_fade_up', id);
  run(str('particle minecraft:cloud %.1f %.1f %.1f 1.2 0.6 1.2 0.02 40', p0:0, global_PLANE + 1, p0:1));
  run(str('playsound minecraft:block.beacon.activate neutral @a %.1f %.1f %.1f 1.5 1.6', p0:0, global_PLANE + 1, p0:1))
);

// the car grows out of nothing (a fade)
_fade(c, s0, s1, tk) -> (
  e = entity_id(c:'body'); if (!e, return());
  m = global_M:(c:'model'); s = s1;
  run(str('data merge entity %s {start_interpolation:0,interpolation_duration:%d,transformation:{left_rotation:[0f,0f,0f,1f],right_rotation:[0f,0f,0f,1f],translation:[0f,%.3ff,0f],scale:[%.3ff,%.3ff,%.3ff]}}', query(e, 'uuid'), tk, m:1 / 2 * s, m:1 * s, m:1 * s, m:1 * s))
);
_fade_up(id) -> (c = global_cars:id; if (c, _fade(c, 0.03, 1, 24)));

// ── the driver: the same keys a player would press ──
_ai(c, t) -> (
  a = c:'ai';
  st = a:'state';
  if (st == 'gone', return());
  if (!player(a:'owner') && !a:'test', _ai_dismiss(c); return());
  x = c:'x'; z = c:'z'; h = c:'h';
  vf = c:'vx' * -sin(h) + c:'vz' * cos(h);
  if (st == 'appear', if (t >= a:'go', (a:'state' = 'drive'; a:'lastt' = t; a:'last' = [x, z])); return());
  if (st == 'wait', (
    if (abs(c:'vx') + abs(c:'vz') > 0.005 || c:'vy' != 0, _drive(c, 0, t));
    if (unix_time() - a:'since' > global_WAIT_MS, _ai_dismiss(c));
    return()
  ));
  path = a:'path'; i = a:'i'; last = i >= length(path) - 1;
  tx = path:i:0; tz = path:i:1;
  dx = tx - x; dz = tz - z; d = sqrt(dx * dx + dz * dz);
  if (d < if (last, 1.8, 3.4), (
    if (last, a:'state' = 'stopping', (a:'i' = i + 1; i = i + 1; last = i >= length(path) - 1; tx = path:i:0; tz = path:i:1; dx = tx - x; dz = tz - z; d = sqrt(dx * dx + dz * dz)))
  ));
  m = global_M:(c:'model');
  dend = d + a:'rem':i;
  if (a:'state' == 'stopping', (
    if (abs(vf) < 0.07, (_ai_arrived(c, false); return()));
    _drive(c, 2, t); _ai_sound(c, t); return()
  ));
  // the owner hears it coming: "close" once, at about 40 blocks of road
  if (!a:'near' && dend < 40, (a:'near' = true; _msg(a:'owner', 'הרכב שלך מתקרב...', 'aqua')));
  hd = atan2(-dx, dz);
  err = ((hd - h) % 360 + 540) % 360 - 180;
  vt = min(m:2 * 0.85, 0.3 + dend * 0.1);
  if (abs(err) > 25, vt = min(vt, 0.55));
  if (abs(err) > 60, vt = min(vt, 0.3));
  k = 0;
  if (a:'rev' > 0, (
    a:'rev' = a:'rev' - 1;
    k = 2 + if (err > 0, 4, 8)                                  // reverse, wheel the other way
  ), (
    if (err > 3, k = k + 8, err < -3, k = k + 4);
    if (vf < vt - 0.04, k = k + 1, vf > vt + 0.10 && vf > 0.15, k = k + 2)
  ));
  // stuck? (it wants to move but has not gone 1 block in 1.5 s)
  if (t - a:'lastt' >= 30, (
    mv = sqrt((x - a:'last':0) ^ 2 + (z - a:'last':1) ^ 2);
    a:'last' = [x, z]; a:'lastt' = t;
    if (mv < 1.0 && a:'rev' == 0, (
      a:'stuck' = a:'stuck' + 1;
      if (a:'stuck' >= 3, a:'state' = 'stopping', a:'rev' = 14)
    ), a:'stuck' = max(0, a:'stuck' - 1))
  ));
  _drive(c, k, t);
  _ai_sound(c, t)
);
_ai_sound(c, t) -> (
  s = sqrt(c:'vx' ^ 2 + c:'vz' ^ 2);
  if (t % 5 == 0 && s > 0.05, run(str('playsound minecraft:entity.minecart.riding neutral @a %.1f %.1f %.1f %.2f %.2f', c:'x', c:'y' + 0.5, c:'z', 1.2 + s * 0.8, 0.5 + s * 1.1)))
);

// two quick honks, loud enough to hear from far away, then the message
_honk(x, y, z) -> (
  run(str('playsound minecraft:block.note_block.bit neutral @a %.1f %.1f %.1f 5 0.6', x, y, z));
  run(str('playsound minecraft:block.note_block.pling neutral @a %.1f %.1f %.1f 5 0.5', x, y, z))
);
_honk_at(id) -> (c = global_cars:id; if (c, _honk(c:'x', c:'y' + 1, c:'z')));
_compass(dx, dz) -> (
  a = (atan2(dx, -dz) + 360) % 360;
  ['צפון', 'צפון-מזרח', 'מזרח', 'דרום-מזרח', 'דרום', 'דרום-מערב', 'מערב', 'צפון-מערב']:(floor((a + 22.5) / 45) % 8)
);
_ai_arrived(c, partial) -> (
  a = c:'ai'; a:'state' = 'wait'; a:'since' = unix_time();
  c:'vx' = 0; c:'vz' = 0; c:'lock' = unix_time() + global_LOCK_MS;
  _honk(c:'x', c:'y' + 1, c:'z'); schedule(5, '_honk_at', c:'id');
  p = player(a:'owner');
  if (p, (
    q = pos(p); dx = c:'x' - q:0; dz = c:'z' - q:2;
    dist = round(sqrt(dx * dx + dz * dz));
    name = global_M:(c:'model'):0;
    _msg(a:'owner', str('הרכב שלך הגיע: %s, %d מטר %s', name, dist, if (dist < 3, 'ממש לידך', _compass(dx, dz))), 'green');
    print(p, str('הרכב שלך הגיע (%s%s) - %d מטר בכיוון %s. לחיצה ימנית עליו כדי להיכנס.', name, if (partial, ', כמה שיכל להתקרב', ''), dist, if (dist < 3, 'ממש לידך', _compass(dx, dz))))
  ))
);
_ai_taken(c) -> (
  a = c:'ai'; delete(global_calls, a:'owner');
  c:'ai' = null; c:'temp' = true; c:'tsince' = unix_time()
);
_ai_dismiss(c) -> (
  a = c:'ai'; if (!a || a:'state' == 'gone', return());
  a:'state' = 'gone'; delete(global_calls, a:'owner');
  _fade(c, 1, 0.03, 20);
  run(str('particle minecraft:cloud %.1f %.1f %.1f 1 0.5 1 0.02 25', c:'x', c:'y' + 1, c:'z'));
  schedule(22, '_car_remove', c:'id')
);
_car_remove(id) -> (
  c = global_cars:id; if (!c, return());
  for (['body', 'hit', 'seat', 'seat2', 'cam', 'man', 'pman'], u = c:_; if (u, e = entity_id(u); if (e, modify(e, 'remove'))));
  delete(global_cars, id)
);
// a car that was called and driven, then left empty: it leaves 3 minutes after the last player was near it
_temp_check(c) -> (
  near = first(player('all'), _distance(pos(_), [c:'x', c:'y', c:'z']) < 30) != null;
  if (near, c:'tsince' = unix_time(), unix_time() - c:'tsince' > 180000, (delete(global_calls, c:'owner'); _fade(c, 1, 0.03, 20); schedule(22, '_car_remove', c:'id'); c:'temp' = false))
);

// the CAR KEY (no client mod needed): a paper item with a pack model; right click with it = call a car. /cars key gives one.
__on_player_uses_item(p, item, hand) -> (
  if (hand == 'mainhand' && item && item:0 == 'paper' && (str(item:2) ~ 'carkey') != null, _call_player(p))
);
cmd_key() -> (
  p = player(); if (!p, return(null)); n = p ~ 'name';
  has = false;
  for (range(inventory_size(p)), s = inventory_get(p, _); if (s && s:0 == 'paper' && (str(s:2) ~ 'carkey') != null, has = true));
  if (has, return('you already have a car key'));
  run(str('give %s paper[item_model="bulbul:car_key",custom_data={carkey:1b},custom_name={text:"Car key",color:"light_purple",italic:false},lore=[{text:"Right click = call a car",color:"gray",italic:false}]] 1', n));
  'you got a car key: right click it to call a car'
);
