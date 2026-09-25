// cars.sc — drivable cars, GTA-style, with no client mods. Recipe and reasons: skill reference/vehicles.md.
// Needs: the car models resource pack (resourcepacks/cars/build_pack.py → cars.zip, models cars:<model>) and the
// Key Bridge server mod (mods-src/keybridge), which writes each player's movement keys into the scoreboard "keys"
// (1 W · 2 S · 4 A · 8 D · 16 Space · 32 Shift · 64 Ctrl). Players install nothing.
//
// A car = an item_display with the model (teleport_duration 2 → smooth), an interaction box (right-click = get in)
// and a marker armor stand as the seat. Physics run here every tick for cars with a driver or still moving: throttle
// with a soft top speed, brakes, reverse, steering that scales with speed, tyre grip (the sideways slip decays) —
// Space = handbrake: less grip, the tail slides out, you drift. Ctrl = boost. Walls stop the car (bounce + crunch),
// 1-block steps are climbed, it falls off edges, grass/sand slow it, mobs in the way are pushed aside (players never).
// Camera: "chase" (default) — you spectate a camera entity that trails the car, a mannequin with your skin sits at the
// wheel; "first" — you sit in the seat (F5 works). /cars view toggles it. Shift = get out beside the driver's door.
// Parked cars that were moved go back to their spot after 3 minutes with nobody near.
//
// Parking lot: <app>.data/lot.json = {"spots": [[x, y, z, yaw, "model", "colour"], ...], "show": [x, y, z, "model",
// "colour"] (optional turntable), "center": [x, z]} — the fleet is built the first time a real player comes within
// 96 blocks of the center (its chunks are loaded then). /cars here <model> <colour> puts a car where you stand.
// Every entity is tagged with this app's name and a generation id; stale copies from an older run are removed as
// their chunk loads. So the app is safe to load under any name.
// Test: script in cars run global_allow_fake = true; set_keys('Bot', 1 + 8) feeds keys to a fake player.

__config() -> {'stay_loaded' -> true, 'scope' -> 'global',
  'commands' -> {'view' -> 'cmd_view', 'home' -> 'cmd_home', 'here <model> <colour>' -> ['cmd_here'], 'list' -> 'cmd_list'},
  'arguments' -> {'model' -> {'type' -> 'term', 'suggest' -> ['sedan', 'sports', 'suv', 'taxi', 'police']},
                  'colour' -> {'type' -> 'term', 'suggest' -> ['red', 'blue', 'white', 'black', 'yellow', 'pink', 'green', 'orange', 'silver']}}};

global_allow_fake = false;
global_T = system_info('app_name');   // tag prefix = this app's name
global_MODEL_YAW = 180;               // an item_display shows a model's +z side AWAY from its yaw: the pack builds the nose at +z
// model: [name, scale, top speed b/t, accel, turn deg/t at full lock, grip 0..1, camera distance, camera height, half length, half width]
global_M = {
  'sedan'  -> ['Sedan', 4.6, 1.05, 0.030, 4.2, 0.30, 7.6, 4.0, 2.1, 0.95],
  'sports' -> ['Sports car', 4.6, 1.35, 0.042, 4.6, 0.36, 7.4, 3.7, 2.1, 1.0],
  'suv'    -> ['SUV', 4.6, 0.95, 0.026, 3.8, 0.28, 8.2, 4.5, 2.1, 1.0],
  'taxi'   -> ['Taxi', 4.6, 1.05, 0.030, 4.2, 0.30, 7.6, 4.0, 2.1, 0.95],
  'police' -> ['Police car', 4.6, 1.20, 0.036, 4.4, 0.32, 7.6, 4.0, 2.1, 0.95]};
global_COL = {'red' -> 12597547, 'blue' -> 3949738, 'white' -> 15790320, 'black' -> 1908001, 'yellow' -> 16701501,
  'pink' -> 15961002, 'green' -> 6192150, 'orange' -> 16351261, 'purple' -> 8991416, 'silver' -> 10329495, 'cyan' -> 1481884};
global_ROAD_SLOW = {'grass_block' -> 0.72, 'dirt' -> 0.72, 'sand' -> 0.6, 'gravel' -> 0.75, 'moss_block' -> 0.72, 'mud' -> 0.5,
  'water' -> 0.3, 'farmland' -> 0.6, 'snow_block' -> 0.7};
global_ICE = {'ice' -> 1, 'packed_ice' -> 1, 'blue_ice' -> 1};

global_cars = {};          // id -> car
global_gen = str('%s_g%d', global_T, floor(rand(1000000000)));
global_view = {};          // name -> 'chase' | 'first'
global_fake_keys = {};
global_restore = {};       // name -> {'mode'} while driving (also in restore.json: survives a reload)
global_next = 1;
global_spawned = false;
global_lot = null; global_show = null;

__on_start() -> (
  v = read_file('views', 'json'); if (v, global_view = v);
  global_lot = read_file('lot', 'json');
  r = read_file('restore', 'json'); if (r, global_restore = r);
  for (keys(global_restore), if (player(_), _restore_player(_)));
  for (['item_display', 'interaction', 'armor_stand', 'mannequin'],
    entity_load_handler(_, _(e, new) -> if (!new, schedule(0, '_stale', query(e, 'uuid')))))
);
// a part of an older run (tagged with this app, not with this run's generation) is removed as its chunk loads
_stale(u) -> (e = entity_id(u); if (e, t = parse_nbt(query(e, 'nbt', 'Tags')); if (t && (t ~ global_T) != null && (t ~ global_gen) == null, modify(e, 'remove'))));

_real(p) -> global_allow_fake || (p ~ 'player_type') != 'fake';
_msg(n, t, c) -> run(str('title %s actionbar %s', n, encode_json({'text' -> t, 'color' -> c, 'bold' -> true})));
_keys(n) -> (f = global_fake_keys:n; if (f != null, return(f)); k = scoreboard('keys', n); if (k == null, 0, k));
set_keys(n, bits) -> (global_fake_keys:n = bits; bits);
_bit(k, b) -> bitwise_and(k, b) != 0;
_fallback(p) -> if (query(p, 'permission_level') >= 2, 'creative', 'adventure');
_tags(id) -> str('"%s","%s_car%d","%s"', global_T, global_T, id, global_gen);

// ───────────── spawning ─────────────
_spawn_all() -> (
  for (entity_selector('@e[tag=' + global_T + ']'), modify(_, 'remove'));     // immediate (a run('kill') can be deferred)
  global_cars = {};
  lot = global_lot;
  if (lot,
    for (lot:'spots', s = _; _new_car(s:4, s:5, [s:0, s:1, s:2], s:3, true));
    sh = lot:'show';
    if (sh, m = global_M:(sh:3); if (m, global_show = query(spawn('item_display', [sh:0, sh:1, sh:2], str('{Tags:["%s","%s"],item:{id:"minecraft:paper",count:1,components:{"minecraft:item_model":"cars:%s","minecraft:dyed_color":%d}},teleport_duration:20,brightness:{sky:15,block:15},transformation:{left_rotation:[0f,0f,0f,1f],right_rotation:[0f,0f,0f,1f],translation:[0f,%.3ff,0f],scale:[%.2ff,%.2ff,%.2ff]}}',
      global_T, global_gen, sh:3, _or(global_COL:(sh:4), 15790320), m:1 / 2 + 0.3, m:1, m:1, m:1)), 'uuid'))));
  global_spawned = true
);
_or(v, d) -> if (v == null, d, v);

_new_car(model, colour, q, yaw, home) -> (
  m = global_M:model; if (!m, return(null));
  id = global_next; global_next += 1;
  rgb = global_COL:colour; if (rgb == null, rgb = number(colour)); if (rgb == null, rgb = 15790320);
  tags = _tags(id);
  body = spawn('item_display', q, str('{Tags:[%s],item:{id:"minecraft:paper",count:1,components:{"minecraft:item_model":"cars:%s","minecraft:dyed_color":%d}},teleport_duration:2,Rotation:[%.1ff,0f],view_range:4f,shadow_radius:1.4f,shadow_strength:0.6f,transformation:{left_rotation:[0f,0f,0f,1f],right_rotation:[0f,0f,0f,1f],translation:[0f,%.3ff,0f],scale:[%.2ff,%.2ff,%.2ff]}}',
    tags, model, rgb, yaw + global_MODEL_YAW, m:1 / 2, m:1, m:1, m:1));
  hit = spawn('interaction', q, str('{Tags:[%s],width:%.2ff,height:1.6f,response:1b}', tags, m:9 * 2 + 0.2));
  seat = spawn('armor_stand', q, str('{Tags:[%s],Marker:1b,Invisible:1b,NoGravity:1b,Invulnerable:1b,Rotation:[%.1ff,0f]}', tags, yaw));
  global_cars:id = {'id' -> id, 'model' -> model, 'colour' -> colour, 'body' -> query(body, 'uuid'), 'hit' -> query(hit, 'uuid'),
    'seat' -> query(seat, 'uuid'), 'x' -> q:0, 'y' -> q:1, 'z' -> q:2, 'h' -> yaw, 'vx' -> 0, 'vz' -> 0, 'vy' -> 0, 'steer' -> 0,
    'driver' -> null, 'cam' -> null, 'man' -> null, 'mode' -> null, 'idle' -> 0, 'ch' -> yaw,
    'home' -> if (home, [q:0, q:1, q:2, yaw], null)};
  _place(global_cars:id, 0);
  id
);

_car_of_entity(e) -> (
  t = parse_nbt(query(e, 'nbt', 'Tags')); if (!t, return(null));
  pre = global_T + '_car';
  for (t, if ((_ ~ ('^' + pre + '\\d+$')) != null, return(number(slice(_, length(pre))))));
  null
);

// ───────────── getting in / out ─────────────
__on_player_interacts_with_entity(p, e, hand) -> (
  if (hand != 'mainhand' || query(e, 'type') != 'interaction' || !_real(p), return());
  id = _car_of_entity(e); if (id == null, return());
  c = global_cars:id; if (!c, return());
  if (c:'driver', _msg(p ~ 'name', 'This car is taken', 'red'); return());
  if (first(values(global_cars), _:'driver' == (p ~ 'name')) != null, return());
  enter(p ~ 'name', id)
);

enter(n, id) -> (
  p = player(n); c = global_cars:id; if (!p || !c || c:'driver', return('no'));
  global_restore:n = {'mode' -> p ~ 'gamemode'}; write_file('restore', 'json', global_restore);
  c:'driver' = n; c:'idle' = 0;
  _set_view(c, _or(global_view:n, 'chase'));
  _msg(n, str('%s · W/S gas/brake · A/D steer · Space handbrake (drift) · Ctrl boost · Shift get out · /%s view camera', global_M:(c:'model'):0, global_T), 'yellow');
  run(str('playsound minecraft:block.iron_door.close master @a %.1f %.1f %.1f 0.8 1.4', c:'x', c:'y', c:'z'));
  'in'
);

_set_view(c, mode) -> (
  n = c:'driver'; p = player(n);
  _drop_cam(c);
  c:'mode' = mode;
  if (mode == 'chase',
    m = global_M:(c:'model');
    cq = _cam_target(c); c:'ch' = c:'h';
    cam = spawn('item_display', cq, str('{Tags:[%s],teleport_duration:2,Rotation:[%.1ff,%.1ff]}', _tags(c:'id'), c:'h', atan2(m:7 - 1, m:6)));
    c:'cam' = query(cam, 'uuid');
    prof = if ((p ~ 'player_type') != 'fake', str(',profile:{name:"%s"}', n), '');
    man = spawn('mannequin', [c:'x', c:'y', c:'z'], str('{Tags:[%s],immovable:1b,hide_description:1b,Invulnerable:1b%s}', _tags(c:'id'), prof));
    c:'man' = query(man, 'uuid');
    run(str('ride %s mount %s', c:'man', c:'seat'));
    if (query(p, 'mount'), run(str('ride %s dismount', n)));
    run(str('gamemode spectator %s', n));
    schedule(2, '_spectate', n, c:'cam'),                                     // after the game mode switch
    // first person: sit in the seat
    run(str('gamemode %s %s', _or(global_restore:n:'mode', _fallback(p)), n));
    run(str('ride %s mount %s', n, c:'seat'))
  )
);
_spectate(n, u) -> run(str('spectate %s %s', u, n));
_drop_cam(c) -> for (['cam', 'man'], u = c:_; if (u, e = entity_id(u); if (e, modify(e, 'remove'))); c:_ = null);

// Exit: stop spectating FIRST, restore the game mode, switch flying off (spectator → creative keeps flying on),
// and put the player down beside the driver's door 2 ticks later, once the game mode has really switched.
leave(id) -> (
  c = global_cars:id; if (!c || !c:'driver', return());
  n = c:'driver'; p = player(n);
  _drop_cam(c);
  c:'driver' = null; c:'mode' = null; c:'vx' = 0; c:'vz' = 0;                  // parked: it does not roll on
  if (p,
    if (query(p, 'mount'), run(str('ride %s dismount', n)));
    run(str('execute as %s run spectate', n));
    _restore_player(n);
    modify(p, 'flying', false);
    h = c:'h'; ox = c:'x' + cos(h) * 1.8; oz = c:'z' + sin(h) * 1.8;            // the driver's side
    schedule(2, '_put_down', n, ox, c:'y', oz, h));
  run(str('playsound minecraft:block.iron_door.open master @a %.1f %.1f %.1f 0.8 1.3', c:'x', c:'y', c:'z'))
);
_put_down(n, x, y, z, h) -> (
  p = player(n); if (!p, return());
  gy = floor(y); while (_solid(floor(x), gy, floor(z)) || _solid(floor(x), gy + 1, floor(z)), 6, gy += 1);   // not inside a wall
  while (!_solid(floor(x), gy - 1, floor(z)) && gy > y - 6, 6, gy += -1);                               // down to the ground
  modify(p, 'flying', false);
  run(str('tp %s %.2f %d %.2f %.1f 0', n, x, gy, z, h))
);
_restore_player(n) -> (
  p = player(n); if (!p, return());
  r = global_restore:n;
  run(str('gamemode %s %s', if (r && r:'mode', r:'mode', _fallback(p)), n));
  delete(global_restore, n); write_file('restore', 'json', global_restore)
);

cmd_view() -> (
  p = player(); n = p ~ 'name';
  v = if (global_view:n == 'first', 'chase', 'first'); global_view:n = v; write_file('views', 'json', global_view);
  c = first(values(global_cars), _:'driver' == n); if (c, _set_view(c, v));
  if (v == 'first', 'Camera: first person (F5 for third person)', 'Camera: chase view behind the car')
);
cmd_home() -> (p = player(); c = first(values(global_cars), _:'driver' == (p ~ 'name')); if (c, leave(c:'id'); _go_home(c)); 'ok');
cmd_here(model, colour) -> (
  p = player(); if (!global_M:model, return('models: ' + join(', ', keys(global_M))));
  if (!global_spawned, global_spawned = true);
  str('car %d', _new_car(model, colour, pos(p), p ~ 'yaw', false))
);
cmd_list() -> map(values(global_cars), str('%d %s %s %s', _:'id', _:'model', _:'colour', _or(_:'driver', '-')));

__on_player_disconnects(p, r) -> (n = p ~ 'name'; c = first(values(global_cars), _:'driver' == n); if (c, _drop_cam(c); c:'driver' = null; c:'mode' = null));
__on_player_connects(p) -> (n = p ~ 'name'; if (has(global_restore, n), schedule(20, '_restore_player', n)));

// ───────────── the loop ─────────────
__on_tick() -> (
  t = tick_time();
  if (!global_spawned,
    // build the fleet lazily, with a real player near the lot: its chunks are loaded and old copies can be removed
    ctr = if (global_lot, global_lot:'center', null);
    if (ctr && t % 20 == 0 && first(player('all'), _real(_) && abs(pos(_):0 - ctr:0) < 96 && abs(pos(_):2 - ctr:1) < 96) != null, _spawn_all());
    if (!global_spawned, return()));
  if (global_show && t % 20 == 0, e = entity_id(global_show); if (e, sh = global_lot:'show'; modify(e, 'location', sh:0, sh:1, sh:2, (t / 20 * 18) % 360, 0)));
  for (values(global_cars),
    c = _;
    if (c:'driver',
      p = player(c:'driver');
      if (!p, _drop_cam(c); c:'driver' = null; continue());
      k = _keys(c:'driver');
      if (_bit(k, 32) && c:'mode' == 'chase', leave(c:'id'); continue());          // Shift in the chase view
      if (c:'mode' == 'first' && !query(p, 'mount'), leave(c:'id'); continue());   // dismounted in first person
      _drive(c, k, t),
      if (abs(c:'vx') + abs(c:'vz') > 0.005 || c:'vy' != 0, _drive(c, 0, t),
        if (c:'home' && t % 200 == 0, _maybe_home(c))))
  )
);

_maybe_home(c) -> (
  hm = c:'home';
  if ((c:'x' - hm:0) ^ 2 + (c:'z' - hm:2) ^ 2 < 4, c:'idle' = 0; return());
  c:'idle' = c:'idle' + 200;
  if (c:'idle' >= 3600 && first(player('all'), _dist2d(pos(_), [c:'x', c:'y', c:'z']) < 24) == null, _go_home(c))
);
_go_home(c) -> (hm = c:'home'; if (!hm, return()); c:'x' = hm:0; c:'y' = hm:1; c:'z' = hm:2; c:'h' = hm:3; c:'vx' = 0; c:'vz' = 0; c:'vy' = 0; c:'idle' = 0; _place(c, 0));
_dist2d(a, b) -> sqrt((a:0 - b:0) ^ 2 + (a:2 - b:2) ^ 2);
_solid(x, y, z) -> (b = block(x, y, z); !air(b) && solid(b));

// ───────────── physics ─────────────
_drive(c, k, t) -> (
  m = global_M:(c:'model');
  h = c:'h'; vx = c:'vx'; vz = c:'vz';
  gas = _bit(k, 1); brk = _bit(k, 2); left = _bit(k, 4); right = _bit(k, 8); hand = _bit(k, 16); boost = _bit(k, 64);
  under = str(block(floor(c:'x'), floor(c:'y') - 1, floor(c:'z')));
  slow = _or(global_ROAD_SLOW:under, 1);
  ice = has(global_ICE, under);
  vmax = m:2 * slow * if (boost, 1.35, 1);
  acc = m:3 * if (boost, 1.5, 1);
  // 1) STEER FIRST: the wheel turns the nose, in proportion to the speed along it; less lock at high speed
  vf0 = vx * -sin(h) + vz * cos(h);
  want = if (right, 1, 0) - if (left, 1, 0);
  c:'steer' = c:'steer' + (want - c:'steer') * 0.35;
  sp = abs(vf0);
  turn = c:'steer' * m:4 * min(1, sp / 0.28) * (1 - 0.4 * min(1, sp / m:2)) * if (hand, 1.45, 1);
  if (vf0 < 0, turn = -turn);
  h = h + turn;
  // 2) the momentum did NOT turn: split it along the new nose (vf) and sideways (vr = slip)
  fx = -sin(h); fz = cos(h); rx = -cos(h); rz = -sin(h);
  vf = vx * fx + vz * fz; vr = vx * rx + vz * rz;
  // 3) engine / brakes along the nose
  if (gas, vf = vf + acc * max(0.05, 1 - vf / vmax),
    brk, if (vf > 0.04, vf = vf - 0.065, vf = max(-0.32, vf - acc * 0.7)),
    vf = vf * 0.985; if (abs(vf) < 0.004, vf = 0));
  if (vf > vmax, vf = vf * 0.96);
  // handbrake: a real brake on the rear wheels — alone it stops the car in about a second, with W + A/D it drifts
  if (hand, vf = if (abs(vf) <= 0.035, 0, vf - 0.035 * if (vf > 0, 1, -1)));
  // 4) GRIP: the tyres pull the slip back to zero — the handbrake (or ice) lets the tail slide out = a drift;
  //    part of the slip the tyres kill becomes forward speed again (a drift exits with speed)
  grip = m:5 * if (hand && abs(vf) > 0.12, 0.12, 1) * if (ice, 0.25, 1);
  vf = vf + abs(vr) * grip * 0.25 * if (vf < 0, -1, 1);
  vr = vr * (1 - grip);
  vx = vf * fx + vr * rx; vz = vf * fz + vr * rz;
  // move, collide
  x = c:'x'; y = c:'y'; z = c:'z';
  nx = x + vx; nz = z + vz;
  hit = if (_blocked_at(m, nx, y, nz, h), 1, 0);
  if (hit == 1, if (!_blocked_at(m, nx, y + 1, nz, h), y = y + 1; vx = vx * 0.8; vz = vz * 0.8, hit = 2));   // STEP-UP one block
  if (hit == 2,
    s2 = sqrt(vx * vx + vz * vz);
    if (s2 > 0.3,
      run(str('playsound minecraft:entity.generic.explode master @a %.1f %.1f %.1f %.2f 1.8', x, y, z, min(1, s2)));
      run(str('particle minecraft:crit %.1f %.1f %.1f 0.6 0.4 0.6 0.2 20', x + fx * m:8, y + 0.8, z + fz * m:8)));
    vx = -vx * 0.25; vz = -vz * 0.25; nx = x; nz = z);
  // ground: fall off edges (centre and both axles in the air), land on the next floor
  gy = floor(y);
  if (!_solid(floor(nx), gy - 1, floor(nz)) && !_solid(floor(nx + fx * m:8 * 0.7), gy - 1, floor(nz + fz * m:8 * 0.7)) && !_solid(floor(nx - fx * m:8 * 0.7), gy - 1, floor(nz - fz * m:8 * 0.7)),
    vy = max(-1.5, c:'vy' - 0.08); ny = y + vy;
    if (_solid(floor(nx), floor(ny), floor(nz)), ny = floor(ny) + 1; vy = 0);
    y = ny; c:'vy' = vy,
    c:'vy' = 0; y = gy);
  // mobs in the way get pushed aside — players, stands and mannequins never
  if (sqrt(vx * vx + vz * vz) > 0.15 && t % 2 == 0,
    for (entity_selector(str('@e[x=%.1f,y=%.1f,z=%.1f,distance=..%.1f]', nx + fx * m:8 * 0.6, y + 0.5, nz + fz * m:8 * 0.6, m:9 + 0.6)),
      e = _;
      if (query(e, 'health') == null || query(e, 'type') ~ 'player|armor_stand|mannequin', continue());
      modify(e, 'motion', vx * 1.6 + rx * 0.3, 0.35, vz * 1.6 + rz * 0.3);
      vx = vx * 0.8; vz = vz * 0.8));
  c:'x' = nx; c:'y' = y; c:'z' = nz; c:'h' = h; c:'vx' = vx; c:'vz' = vz;
  _place(c, t);
  s = sqrt(vx * vx + vz * vz);
  if (c:'driver' && t % 5 == 0 && (gas || s > 0.05),
    run(str('playsound minecraft:entity.minecart.riding neutral @a %.1f %.1f %.1f %.2f %.2f', nx, y + 0.5, nz, 0.25 + s * 0.4, 0.5 + s * 1.1)));
  if (abs(vr) > 0.18 && s > 0.3,
    run(str('particle minecraft:white_smoke %.2f %.2f %.2f 0.4 0.05 0.4 0.01 3', nx - fx * m:8, y + 0.1, nz - fz * m:8));
    if (t % 4 == 0, run(str('playsound minecraft:block.sand.break neutral @a %.1f %.1f %.1f 0.6 0.6', nx, y, nz))));
  if (boost && gas && t % 2 == 0, run(str('particle minecraft:flame %.2f %.2f %.2f 0.1 0.05 0.1 0.01 2', nx - fx * (m:8 + 0.3), y + 0.4, nz - fz * (m:8 + 0.3))));
  if (c:'driver' && t % 10 == 0,
    _msg(c:'driver', str('%d km/h%s', round(s * 72), if (hand, ' · drift!', boost && gas, ' · boost!', '')), if (hand, 'light_purple', boost && gas, 'gold', 'white')))
);

// the car's footprint (corners + side midpoints) against solid blocks at the feet and one above
_blocked_at(m, x, y, z, h) -> (
  fx = -sin(h); fz = cos(h); rx = -cos(h); rz = -sin(h); L = m:8; W = m:9;
  for ([[L, 0], [L, W * 0.9], [L, -W * 0.9], [-L, W * 0.9], [-L, -W * 0.9], [L * 0.5, W], [L * 0.5, -W], [-L * 0.5, W], [-L * 0.5, -W]],
    px = x + fx * _:0 + rx * _:1; pz = z + fz * _:0 + rz * _:1;
    if (_solid(floor(px), floor(y), floor(pz)) || _solid(floor(px), floor(y) + 1, floor(pz)), return(true)));
  false
);

// move every part; the chase camera sits exactly behind the car (same interpolation → the car never shakes on
// screen); only its HEADING follows the car's heading softly, so turns feel smooth
_place(c, t) -> (
  x = c:'x'; y = c:'y'; z = c:'z'; h = c:'h';
  e = entity_id(c:'body'); if (e, modify(e, 'location', x, y, z, h + global_MODEL_YAW, 0));
  e = entity_id(c:'hit'); if (e, modify(e, 'pos', x, y, z));
  e = entity_id(c:'seat'); if (e, modify(e, 'location', x - sin(h) * 0.15 + cos(h) * 0.45, y + 0.35, z + cos(h) * 0.15 + sin(h) * 0.45, h, 0));
  if (c:'cam',
    dh = ((h - c:'ch') % 360 + 540) % 360 - 180; c:'ch' = c:'ch' + dh * 0.18;
    m = global_M:(c:'model'); ch = c:'ch';
    pitch = atan2(m:7 - 1, m:6);
    e = entity_id(c:'cam'); if (e, modify(e, 'location', x + sin(ch) * m:6, y + m:7, z - cos(ch) * m:6, ch, pitch));
    if (c:'man', _man_fix(c:'man', h, ch, pitch * 0.6)))
);

// A riding mannequin ignores body_yaw; the game only keeps its body within 50° of its own yaw. Push the yaw 50° past
// the car's heading on the side the body lags: the clamp then drags the body exactly onto the heading.
_man_fix(u, h, yawcam, pitch) -> (
  e = entity_id(u); if (!e, return());
  d = ((h - query(e, 'body_yaw')) % 360 + 540) % 360 - 180;
  modify(e, 'yaw', h + if (abs(d) < 0.5, 0, d > 0, 50, -50));
  modify(e, 'head_yaw', yawcam); modify(e, 'pitch', pitch)
);
_cam_target(c) -> (m = global_M:(c:'model'); h = c:'h'; [c:'x' + sin(h) * m:6, c:'y' + m:7, c:'z' - cos(h) * m:6]);
