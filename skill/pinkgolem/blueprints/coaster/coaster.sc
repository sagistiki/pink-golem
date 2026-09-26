// coaster.sc — runs the train of a roller coaster built by blueprints/coaster/build.py (read README.md there).
// The track (block_display boxes) and the station are static builds; this app runs the train: single-seat cars
// (item_display with the models coaster:front / coaster:car from the train pack, pack.py), one rider each.
// Everything comes from <app>.data/track.json, written by build.py: the path, the station, the gates, the exit.
//
// Riding: right-click a seat → you become a spectator of a camera (item_display, teleport_duration 1 = smooth) at
// your eye, a little ahead of the head, facing along the track; a mannequin with your skin sits in the car for everyone
// else. Through the loop the camera keeps the entry heading and only pitches (Minecraft has no roll), so there is no
// 180° flip. Shift in the station = get out; mid-ride the camera takes you straight back. 8 s after the first rider
// the train dispatches; at the station you land on the exit platform with your ride stats. (A server can't widen the
// FOV of a spectated camera — FOV effects apply only when the camera is the player — so the frame comes from where
// the camera sits.)
// Shift: read from the scoreboard "keys" (bit 32) when the Key Bridge server mod is installed, otherwise from the
// vanilla sneak flag. Tests: set_keys('<fake player>', 32) feeds it.
//
// Physics = track.py: g 0.0245 b/t² (1 block = 1 m), quadratic drag + rolling resistance, the train's slope is the mean
// over its cars, a chain lift holds 0.30 b/t, tyres 0.2 b/t in the station, brakes → 0.22.
// Track data: one sample every 0.5 block: [x,y,z, qx,qy,qz,qw, ux,uy,uz, lx,ly,lz]; a car's transformation rotation
// is that quaternion (display x → left, y → up, z → forward), so it goes upside down in the loop.
// The seat entity sits at eye − 1.02 (measured: a rider's eye is 1.02 above the entity it rides), eye = seat + up·0.87.
//
// Reload-safe: riders carry the tag <app>_rider and their game mode is saved in restore.json (put back on the exit
// platform on start / join); the train has a generation tag and older copies are removed when their chunk loads; it
// spawns only with a real player near the station. The static parts carry <app>_b<build id> from track.json: parts of
// an older build are removed as their chunk loads. Every tag starts with this app's name, so a copy loaded under
// another name (coaster2.sc + coaster2.data) is a second, independent ride.
// Admin: /script in <app> run status() | show_run() | stop() | respawn() | remove()
// Test: script in <app> run global_allow_fake = true; board('<fake player>', 0); show_run()

__config() -> {'stay_loaded' -> true, 'scope' -> 'global', 'commands' -> {'' -> 'cmd_info'}};

global_allow_fake = false;
global_APP = system_info('app_name');                                      // tag prefix
global_TRAIN = global_APP + '_train'; global_RIDER = global_APP + '_rider'; global_STATIC = global_APP + '_static';
global_TR = read_file('track', 'json');                                    // written by build.py
global_OK = global_TR != null;
if (!global_OK, global_TR = {});                                           // no track: the app idles
global_REMOVED = false;
global_MODEL_READY = global_OK && global_TR:'models' != false;            // false = stand-in blocks until the train pack is live
global_TITLE = if (global_OK && global_TR:'title', global_TR:'title', 'COASTER');
global_P = global_TR:'p'; global_N = global_TR:'n'; global_DS = global_TR:'ds'; global_L = global_TR:'len';
global_NC = global_TR:'cars'; global_GAP = global_TR:'gap'; global_STOP = global_TR:'stop';
global_G = global_TR:'g'; global_DRAG = global_TR:'drag'; global_ROLL = global_TR:'roll';
global_LIFT = global_TR:'lift_v'; global_TYRE = global_TR:'tyre_v'; global_BRAKE = global_TR:'brake_v';
global_FX = if (global_OK && global_TR:'fx', global_TR:'fx', {}); global_EXIT = global_TR:'exit';
global_CENTER = global_TR:'center'; global_AREA = global_TR:'area';
global_GATES = global_TR:'gates'; global_SPC = global_TR:'seats_per_car';
global_GATE_BLOCK = global_TR:'gate_block'; global_GATE_FACING = global_TR:'gate_facing';
global_BUILD_TAG = if (global_OK && global_TR:'build', str('%s_b%s', global_APP, global_TR:'build'), null);
global_K_EYE = 1.02; global_EYE = 0.87; global_CAM_FWD = 0.6;   // camera ahead of the mannequin head (at 0.3 riders saw their own head)
global_SEAT = [0, 0.5625, -0.19];            // left / up / forward offsets of a seat point from the car's track point (pack.py)
global_gen = str('%s_g%d', global_APP, floor(rand(1000000000)));

// per-sample tables: sin(pitch) and a bitmask of sections (1 lift, 2 brakes, 4 tyres, 8 station, 16 loop, 32 air, 64 helix)
global_SIN = []; global_FL = [];
_tables() -> (
  global_SIN = map(range(global_N), (global_P:((_ + 1) % global_N):1 - global_P:_:1) / global_DS);
  global_FL = map(range(global_N), 0);
  bits = {'lift' -> 1, 'brakes' -> 2, 'tyres' -> 4, 'station' -> 8, 'loop' -> 16, 'air' -> 32, 'helix' -> 64};
  for (global_TR:'tags',
    b = bits:(_:0); if (b == null, continue());
    for (range(floor(_:1 / global_DS), ceil(_:2 / global_DS) + 1), i = _ % global_N; global_FL:i = bitwise_or(global_FL:i, b));
  );
);

global_state = 'load';          // load | run | unload
global_s = global_STOP; global_v = 0; global_trav = 0;
global_cars = []; global_seats = []; global_hits = [];
global_riders = {};             // name -> seat index
global_count = -1; global_idle = 0; global_t_unload = 0;
global_ride = {};               // stats of the current ride
global_hist = [];               // last 3 head positions (G meter)
global_gf = 1; global_done = {};
global_stats = {};
global_cams = {}; global_mans = {};    // seat index -> camera / mannequin uuid
global_restore = {};                    // rider -> game mode before the ride (file restore.json)
global_grace = {}; global_shift = {}; global_fake_keys = {};
global_LOOP_YAW = 0;

__on_start() -> (
  global_REMOVED = !global_OK && read_file('removed', 'json') != null;
  if (global_OK || global_REMOVED,
    for (['block_display', 'text_display'], entity_load_handler(_, _(e, new) -> if (!new, schedule(0, '_stale_static', query(e, 'uuid'))))));
  if (!global_OK, return());
  _tables();
  s = read_file('stats', 'json'); global_stats = if (s, s, {'rides' -> {}, 'total' -> 0, 'best' -> {}});
  for (['item_display', 'interaction', 'mannequin'], entity_load_handler(_, _(e, new) -> if (!new, schedule(0, '_stale', query(e, 'uuid')))));
  for (entity_selector(str('@e[tag=%s]', global_TRAIN)), modify(_, 'remove'));
  r = read_file('restore', 'json'); if (r, global_restore = r);
  for (player('all'), if (query(_, 'has_tag', global_RIDER) || has(global_restore, _ ~ 'name'), _land(_ ~ 'name', false)));
  lp = global_FX:'loop'; if (lp, f = _fwd(_smp(lp:0)); global_LOOP_YAW = atan2(-f:0, f:2));
  _forceload('remove');
  _gates(true);
);
_stale(u) -> (e = entity_id(u); if (e && query(e, 'has_tag', global_TRAIN) && !query(e, 'has_tag', global_gen), modify(e, 'remove')));
// a static part (track, support, sign) of an older build — or of a removed ride — is removed as its chunk loads
_stale_static(u) -> (
  e = entity_id(u);
  if (e && query(e, 'has_tag', global_STATIC) && (global_REMOVED || (global_BUILD_TAG != null && !query(e, 'has_tag', global_BUILD_TAG))),
    modify(e, 'remove'))
);

_real(p) -> p && (global_allow_fake || (p ~ 'player_type') != 'fake');
_near(r) -> first(player('all'), _real(_) && (_ ~ 'dimension') == 'overworld' && _dist(pos(_), global_CENTER) < r);
_dist(a, b) -> sqrt((a:0 - b:0) ^ 2 + (a:2 - b:2) ^ 2);
_act(n, t, c) -> run(str('title %s actionbar %s', n, encode_json({'text' -> t, 'color' -> c, 'bold' -> true})));
_title(n, t, sub, c) -> (
  run(str('title %s times 5 45 15', n));
  run(str('title %s subtitle %s', n, encode_json({'text' -> sub, 'color' -> 'white'})));
  run(str('title %s title %s', n, encode_json({'text' -> t, 'color' -> c, 'bold' -> true})));
);
_snd_riders(s, v, pt) -> for (keys(global_riders), run(str('execute as %s at @s run playsound %s master @s ~ ~ ~ %.2f %.2f', _, s, v, pt)));
_snd_at(q, s, v, pt) -> run(str('playsound %s block @a %.1f %.1f %.1f %.2f %.2f', s, q:0, q:1, q:2, v, pt));
_forceload(mode) -> (a = global_AREA; if (a, run(str('forceload %s %d %d %d %d', mode, a:0, a:1, a:2, a:3))));
// Shift = get out. Key Bridge writes each player's keys into the scoreboard "keys" (32 = Shift); without the mod the
// vanilla sneak flag is used. set_keys() stands in for both in tests with fake players.
_shift(p, n) -> (
  f = global_fake_keys:n; if (f != null, return(bitwise_and(f, 32) != 0));
  k = scoreboard('keys', n);
  if (k != null, bitwise_and(k, 32) != 0, query(p, 'sneaking') == true)
);
set_keys(n, bits) -> (global_fake_keys:n = bits; bits);

// ─────────────────────────────── track sampling ───────────────────────────────
_smp(s) -> (
  f = s / global_DS; i0 = floor(f); k = f - i0;
  a = global_P:(i0 % global_N); b = global_P:((i0 + 1) % global_N);
  if (a:3 * b:3 + a:4 * b:4 + a:5 * b:5 + a:6 * b:6 < 0, b = [b:0, b:1, b:2, -b:3, -b:4, -b:5, -b:6, b:7, b:8, b:9, b:10, b:11, b:12]);
  r = map(range(13), a:_ + (b:_ - a:_) * k);
  r += global_FL:(i0 % global_N);
  qn = sqrt(r:3 ^ 2 + r:4 ^ 2 + r:5 ^ 2 + r:6 ^ 2);
  r:3 = r:3 / qn; r:4 = r:4 / qn; r:5 = r:5 / qn; r:6 = r:6 / qn;
  r
);
_flag(s) -> global_FL:(floor(s / global_DS) % global_N);
_sin(s) -> global_SIN:(floor(s / global_DS) % global_N);
_fwd(r) -> [r:11 * r:9 - r:12 * r:8, r:12 * r:7 - r:10 * r:9, r:10 * r:8 - r:11 * r:7];      // f = l × u

_cam_at(r, j) -> (
  sp = _seat_pt(r, j); f = _fwd(r);
  q = map(range(3), sp:_ + r:(7 + _) * global_EYE + f:_ * global_CAM_FWD);
  hz = sqrt(f:0 ^ 2 + f:2 ^ 2);
  yaw = if (bitwise_and(_flag_at(r), 16) || hz < 0.2, global_LOOP_YAW, atan2(-f:0, f:2));
  [q:0, q:1, q:2, yaw, -asin(max(-1, min(1, f:1)))]
);
_flag_at(r) -> r:13;

_seat_pt(r, j) -> (
  f = _fwd(r); sl = if (global_SPC == 1, 0, j == 0, global_SEAT:0, -global_SEAT:0);
  map(range(3), r:_ + r:(10 + _) * sl + r:(7 + _) * global_SEAT:1 + f:_ * global_SEAT:2)
);

// ─────────────────────────────── the train ───────────────────────────────
_car_nbt(k) -> if (global_MODEL_READY,
  str('item:{id:"minecraft:paper",count:1,components:{"minecraft:item_model":"coaster:%s"}}', if (k == 0, 'front', 'car')),
  str('item:{id:"minecraft:%s",count:1}', if (k == 0, 'orange_concrete', 'red_concrete')));
_car_scale() -> if (global_MODEL_READY, [2, 2, 2], [1.3, 0.7, 2.1]);
_hit_nbt(i) -> str('{Tags:["%s","%s","%s_hit","%s_hit_%d","%s"],width:0.8f,height:1.1f,response:1b}', global_APP, global_TRAIN, global_APP, global_APP, i, global_gen);

_spawn() -> (
  for (entity_selector(str('@e[tag=%s]', global_TRAIN)), modify(_, 'remove'));
  global_gen = str('%s_g%d', global_APP, floor(rand(1000000000)));
  global_cars = []; global_seats = []; global_hits = [];
  sc = _car_scale();
  for (range(global_NC),
    k = _;
    r = _smp(global_STOP - k * global_GAP);
    e = spawn('item_display', [r:0, r:1, r:2], str('{Tags:["%s","%s","%s"],%s,teleport_duration:1,interpolation_duration:1,view_range:3f,shadow_radius:0.9f,shadow_strength:0.5f,brightness:{sky:15,block:9},transformation:{left_rotation:[%.4ff,%.4ff,%.4ff,%.4ff],right_rotation:[0f,0f,0f,1f],translation:[0f,0f,0f],scale:[%.2ff,%.2ff,%.2ff]}}',
      global_APP, global_TRAIN, global_gen, _car_nbt(k), r:3, r:4, r:5, r:6, sc:0, sc:1, sc:2));
    global_cars += query(e, 'uuid');
    for (range(global_SPC),
      sp = _seat_pt(r, _);
      q = [sp:0 + r:7 * global_EYE, sp:1 + r:8 * global_EYE - global_K_EYE, sp:2 + r:9 * global_EYE];
      s = spawn('item_display', q, str('{Tags:["%s","%s","%s_seat","%s"],item:{id:"minecraft:stone",count:1},teleport_duration:1,transformation:{left_rotation:[0f,0f,0f,1f],right_rotation:[0f,0f,0f,1f],translation:[0f,0f,0f],scale:[0.001f,0.001f,0.001f]}}', global_APP, global_TRAIN, global_APP, global_gen));
      global_seats += query(s, 'uuid');
      h = spawn('interaction', [sp:0, sp:1 - 0.35, sp:2], _hit_nbt(length(global_hits)));
      global_hits += query(h, 'uuid');
    );
  );
  _place(global_STOP);
);

_ready() -> global_cars && all(global_cars, entity_id(_)) && all(global_seats, entity_id(_));

_place(s) -> (
  sc = _car_scale();
  for (range(global_NC),
    k = _;
    r = _smp(s - k * global_GAP);
    e = entity_id(global_cars:k);
    if (e,
      tr = if (global_MODEL_READY, [0, 0, 0], [r:7 * 0.42, r:8 * 0.42, r:9 * 0.42]);
      modify(e, 'pos', r:0, r:1, r:2);
      modify(e, 'nbt_merge', str('{transformation:{left_rotation:[%.4ff,%.4ff,%.4ff,%.4ff],right_rotation:[0f,0f,0f,1f],translation:[%.3ff,%.3ff,%.3ff],scale:[%.2ff,%.2ff,%.2ff]},start_interpolation:0}',
        r:3, r:4, r:5, r:6, tr:0, tr:1, tr:2, sc:0, sc:1, sc:2));
    );
    for (range(global_SPC),
      i = global_SPC * k + _;
      se = entity_id(global_seats:i);
      if (se,
        sp = _seat_pt(r, _);
        modify(se, 'pos', sp:0 + r:7 * global_EYE, sp:1 + r:8 * global_EYE - global_K_EYE, sp:2 + r:9 * global_EYE);
      );
      u = global_cams:i;
      if (u, ce = entity_id(u); if (ce, cq = _cam_at(r, _); modify(ce, 'location', cq:0, cq:1, cq:2, cq:3, cq:4);
        me = entity_id(global_mans:i); if (me, _man_fix(me, cq:3, cq:4))));
    );
  );
);

// the mannequin rides, so the game ignores body_yaw: turn the entity ±50° and the body clamp drags it (vehicles.md)
_man_fix(e, h, pitch) -> (
  d = ((h - query(e, 'body_yaw')) % 360 + 540) % 360 - 180;
  modify(e, 'yaw', h + if (abs(d) < 0.5, 0, d > 0, 50, -50));
  modify(e, 'head_yaw', h); modify(e, 'pitch', max(-60, min(60, pitch)));
);

// ─────────────────────────────── boarding ───────────────────────────────
__on_player_interacts_with_entity(p, e, hand) -> (
  if (!global_OK || hand != 'mainhand' || query(e, 'type') != 'interaction' || !query(e, 'has_tag', global_APP + '_hit'), return());
  if (!_real(p), return());
  n = p ~ 'name';
  if (global_state != 'load', _act(n, 'The train is out, wait for it to come back', '#FFD166'); return());
  if (has(global_riders, n), return());
  i = first(range(length(global_hits)), query(e, 'has_tag', str('%s_hit_%d', global_APP, _)));
  if (i == null, return());
  if ((values(global_riders) ~ i) != null, _act(n, 'That seat is taken', 'red'); return());
  board(n, i)
);

board(n, i) -> (
  p = player(n); se = entity_id(global_seats:i);
  if (!p || !se, return('no'));
  global_riders:n = i;
  modify(p, 'tag', global_RIDER);
  global_restore:n = p ~ 'gamemode'; write_file('restore', 'json', global_restore);
  k = floor(i / global_SPC); r = _smp(global_s - k * global_GAP); cq = _cam_at(r, i % global_SPC);
  cam = spawn('item_display', [cq:0, cq:1, cq:2], str('{Tags:["%s","%s","%s_cam","%s"],teleport_duration:1,Rotation:[%.1ff,%.1ff]}', global_APP, global_TRAIN, global_APP, global_gen, cq:3, cq:4));
  global_cams:i = query(cam, 'uuid');
  prof = if ((p ~ 'player_type') != 'fake', str(',profile:{name:"%s"}', n), '');
  man = spawn('mannequin', pos(se), str('{Tags:["%s","%s","%s_man","%s"],immovable:1b,hide_description:1b,Invulnerable:1b%s}', global_APP, global_TRAIN, global_APP, global_gen, prof));
  global_mans:i = query(man, 'uuid');
  run(str('ride %s mount %s', global_mans:i, global_seats:i));
  if (query(p, 'mount'), run(str('ride %s dismount', n)));
  run(str('gamemode spectator %s', n));
  schedule(2, '_spectate', n, global_cams:i); global_grace:n = tick_time() + 10;
  _snd_at(pos(p), 'minecraft:block.piston.extend', 0.6, 1.4);
  if (global_count < 0, global_count = 160);
  _title(n, global_TITLE, 'Hold on tight! · SHIFT in the station = get out', '#FF5A1F');
  'boarded'
);

_spectate(n, u) -> if (player(n) && entity_id(u), run(str('spectate %s %s', u, n)));

_leave_seat(n) -> (
  if (!has(global_riders, n), return());
  _land(n, false);
  if (!global_riders && global_state == 'load', global_count = -1);
);

_drop_rig(i) -> (
  for ([global_cams, global_mans], u = _:i; if (u, e = entity_id(u); if (e, modify(e, 'remove'))));
  delete(global_cams, i); delete(global_mans, i);
);

// put a rider down on the exit platform
_land(n, stats) -> (
  i = global_riders:n; if (i != null, _drop_rig(i); delete(global_riders, n));
  p = player(n); if (!p, return());
  if (query(p, 'mount'), run(str('ride %s dismount', n)));
  run(str('execute as %s run spectate', n));                               // stop following the camera first
  m = global_restore:n; if (m == null, m = if (query(p, 'permission_level') >= 2, 'creative', 'adventure'));
  if (query(p, 'gamemode') == 'spectator', run(str('gamemode %s %s', m, n)));
  delete(global_restore, n); write_file('restore', 'json', global_restore);
  modify(p, 'flying', false);
  modify(p, 'clear_tag', global_RIDER);
  for (['invisibility', 'resistance', 'slow_falling'], run(str('effect clear %s %s', n, _)));
  schedule(2, '_put', n);
);
_put(n) -> (p = player(n); if (p, modify(p, 'flying', false); run(str('tp %s %.1f %.1f %.1f %.1f 0', n, global_EXIT:0, global_EXIT:1, global_EXIT:2, global_EXIT:3))));

_gates(open) -> for (global_GATES, run(str('setblock %d %d %d %s[facing=%s,open=%s]', _:0, _:1, _:2, global_GATE_BLOCK, global_GATE_FACING, if (open, 'true', 'false'))));

// ─────────────────────────────── ride control ───────────────────────────────
_dispatch() -> (
  global_state = 'run'; global_v = 0; global_trav = 0; global_s = global_STOP; global_count = -1;
  global_ride = {'vmax' -> 0, 'gmax' -> 1, 'gmin' -> 1, 't0' -> tick_time()};
  global_hist = []; global_gf = 1; global_done = {};
  _forceload('add');
  _gates(false);
  for (map(global_hits, entity_id(_)), if (_, modify(_, 'remove')));
  global_hits = [];
  for (keys(global_riders),
    run(str('effect give %s resistance infinite 4 true', _)); run(str('effect give %s slow_falling infinite 0 true', _));
  );
  _snd_at(global_CENTER, 'minecraft:block.bell.use', 1.5, 0.7);
  _snd_at(global_CENTER, 'minecraft:block.piston.contract', 1, 0.8);
  if (global_riders, _snd_riders('minecraft:entity.blaze.ambient', 0.8, 0.8));
);

_arrive() -> (
  global_state = 'unload'; global_v = 0; global_t_unload = tick_time(); global_count = -1;
  dur = (tick_time() - global_ride:'t0') / 20;
  for (keys(global_riders),
    n = _;
    global_stats:'rides':n = (global_stats:'rides':n || 0) + 1;
    b = global_stats:'best':n || 0;
    kmh = round(global_ride:'vmax' * 72);
    if (kmh > b, global_stats:'best':n = kmh);
    _title(n, global_TITLE, str('%d km/h · %.1fG · airtime %.1fG · %d s', kmh, global_ride:'gmax', global_ride:'gmin', dur), '#FF5A1F');
  );
  who = keys(global_riders);
  for (who, _land(_, true));
  if (who,
    global_stats:'total' = (global_stats:'total' || 0) + 1;
    global_stats:'last' = [who, round(global_ride:'vmax' * 72), round(global_ride:'gmax' * 10) / 10];
    write_file('stats', 'json', global_stats);
    _board();
  );
  global_riders = {};
  _snd_at(global_CENTER, 'minecraft:block.fire.extinguish', 1, 0.8);
  _forceload('remove');
);

_board() -> (
  l = global_stats:'last';
  rides = global_stats:'rides' || {};
  top = if (rides, sort_key(pairs(rides), -(_:1)), []);
  if (length(top) > 5, top = slice(top, 0, 5));
  txt = [{'text' -> global_TITLE + '\n', 'color' -> '#FF5A1F', 'bold' -> true}];
  if (l, txt += {'text' -> str('Last ride: %s\n%d km/h · %.1fG\n', join(', ', l:0), l:1, l:2), 'color' -> 'white'});
  txt += {'text' -> str('Rides: %d\n', global_stats:'total' || 0), 'color' -> '#FFD166'};
  for (top, txt += {'text' -> str('%s  ·  %d\n', _:0, _:1), 'color' -> 'gray'});
  for (entity_selector(str('@e[tag=%s_board]', global_APP)), modify(_, 'nbt_merge', str('{text:%s}', encode_json(txt))));
);

_step() -> (
  s = global_s; v = global_v;
  a = 0; for (range(global_NC), a += _sin(s - _ * global_GAP));
  v = v - global_G * a / global_NC - global_DRAG * v * abs(v) - global_ROLL * if (v > 0, 1, 0);
  fl = 0; for (range(global_NC), fl = bitwise_or(fl, _flag(s - _ * global_GAP)));
  if (bitwise_and(fl, 1), v = global_LIFT,
      bitwise_and(_flag(s), 2) && v > global_BRAKE, v = max(global_BRAKE, v * 0.93),
      bitwise_and(fl, 12) && v < global_TYRE, v = min(global_TYRE, v + 0.02));
  rem = global_L - global_trav;
  if (rem < 7, v = min(v, max(0.02, rem * 0.1)));
  if (v < 0.01 && !bitwise_and(fl, 13), v = 0.05);          // never roll back
  if (rem <= v + 0.005,
    global_trav = global_L; global_s = global_STOP; _place(global_STOP); _arrive(); return());
  global_s = s + v; global_trav += v; global_v = v;
  _place(global_s);
);

// rider view: speed + felt G (along the car's up) from the head car's path
_meter(t) -> (
  r = _smp(global_s);
  global_hist += [r:0, r:1, r:2];
  if (length(global_hist) > 3, global_hist = slice(global_hist, length(global_hist) - 3));
  if (length(global_hist) == 3,
    h = global_hist;
    acc = map(range(3), h:2:_ - 2 * h:1:_ + h:0:_);
    g = (acc:0 * r:7 + (acc:1 + global_G) * r:8 + acc:2 * r:9) / global_G;
    global_gf = global_gf * 0.7 + g * 0.3;
  );
  v = global_v;
  global_ride:'vmax' = max(global_ride:'vmax', v);
  if (v > 0.35, global_ride:'gmax' = max(global_ride:'gmax', global_gf); global_ride:'gmin' = min(global_ride:'gmin', global_gf));
);

_once(k, cond, fn) -> if (cond && !global_done:k, global_done:k = true; call(fn));

// effects at the sections the layout has (build.py writes only those into fx)
_effects(t) -> (
  s = global_s; fx = global_FX; head = _smp(s);
  fl = _flag(s);
  if (bitwise_and(fl, 1) && t % 5 == 0,
    _snd_at(head, 'minecraft:block.wooden_trapdoor.close', 0.7, 0.55);
    _snd_at(head, 'minecraft:block.chain.step', 0.6, 0.7));
  if (fx:'crest' != null, _once('crest', s > fx:'crest' - 2, _() -> (
    _snd_riders('minecraft:item.trident.riptide_3', 0.9, 0.8);
    _snd_riders('minecraft:item.elytra.flying', 0.5, 1.0))));
  if (fx:'tunnel' != null, _once('tunnel', s > fx:'tunnel':0, _() -> (
    a = _smp(global_FX:'tunnel':0); b = _smp(global_FX:'tunnel':1);
    for (range(11),
      k = _ / 10; q = map(range(3), a:_ + (b:_ - a:_) * k);
      run(str('particle minecraft:flame %.1f %.1f %.1f 1.6 0.4 0.3 0.06 25 force', q:0, q:1 + 1.5, q:2));
      run(str('particle minecraft:lava %.1f %.1f %.1f 2 0.3 0.3 0 3 force', q:0, q:1, q:2)));
    _snd_at(a, 'minecraft:entity.blaze.shoot', 1.5, 0.7); _snd_at(b, 'minecraft:item.firecharge.use', 1.5, 0.6))));
  if (fx:'loop' != null,
    _once('loop', s > fx:'loop':0 - 3, _() -> (
      for (values(global_mans), run(str('effect give %s invisibility 4 0 true', _)));
      for (range(global_FX:'loop':0, global_FX:'loop':1, 2.5),
        r = _smp(_);
        for ([1.6, -1.6], run(str('particle minecraft:flame %.2f %.2f %.2f 0.1 0.1 0.1 0.02 6 force', r:0 + r:10 * _, r:1 + r:11 * _, r:2 + r:12 * _))));
      _snd_at(_smp(global_FX:'loop_top'), 'minecraft:entity.blaze.shoot', 2, 0.6)));
    _once('loop_top', s > fx:'loop_top', _() -> (
      c = global_FX:'loop_c';
      run(str('particle minecraft:flame %.1f %.1f %.1f 3 0.5 3 0.1 120 force', c:0, c:1, c:2));
      _snd_at(_smp(global_FX:'loop_top'), 'minecraft:item.firecharge.use', 2, 0.7)));
  );
  if (fx:'helix' != null, _once('helix', s > fx:'helix':0, _() -> (
    c = global_FX:'helix_c';
    run(str('particle minecraft:flame %.1f %.1f %.1f 1 2 1 0.05 80 force', c:0, c:1, c:2));
    run(str('particle minecraft:lava %.1f %.1f %.1f 1 1 1 0 12 force', c:0, c:1, c:2)))));
  if (global_v > 0.6 && t % 10 == 0, _snd_at(head, 'minecraft:entity.minecart.riding', min(2, global_v), 0.6 + global_v * 0.4));
  if (global_v > 0.9 && t % 30 == 0, _snd_riders('minecraft:entity.minecart.inside', min(1, global_v * 0.5), 1.2));
);

// ─────────────────────────────── tick ───────────────────────────────
__on_tick() -> (
  if (!global_OK, return());
  t = tick_time();
  if (global_state == 'run',
    _step();
    if (global_state == 'run', _meter(t); _effects(t); _hold());
    return();
  );
  if (t % 20 == 0, _ensure());
  if (global_state == 'load',
    if (global_riders, _hold(), global_count >= 0, global_count = -1);      // an empty train never counts down
    if (global_count > 0,
      global_count += -1;
      if (global_count % 20 == 0, for (keys(global_riders), _act(_, str('Leaving in %d', global_count / 20), '#FFD166')));
      if (global_count == 0 && global_riders && _ready(), _dispatch());
    );
    if (!global_riders && t % 20 == 0,
      global_idle += 1;
      if (global_idle > 45 && _ready() && _near(100), global_idle = 0; _dispatch());      // a show run for people watching
    , global_riders, global_idle = 0);
  );
  if (global_state == 'unload' && tick_time() - global_t_unload > 40,
    global_state = 'load'; _gates(true); _spawn_hits());
);

// keep riders in their seats (Shift would free the camera) and forget the ones who left. A fake player's position
// drifts away from the camera it spectates, so distance only ever re-attaches — it never means "got off".
_hold() -> for (keys(global_riders),
  n = _; p = player(n); i = global_riders:n;
  if (!p, _drop_rig(i); delete(global_riders, n); continue());
  cu = global_cams:i; ce = entity_id(cu);
  if (!ce, continue());
  sh = _shift(p, n);
  was = global_shift:n; global_shift:n = sh;
  if (sh && !was && global_state == 'load', _leave_seat(n); continue());
  if (tick_time() < (global_grace:n || 0), continue());
  if (query(p, 'gamemode') != 'spectator' || _dist3(pos(p), pos(ce)) > 2.5 || (sh && !was),
    if (query(p, 'gamemode') != 'spectator', run(str('gamemode spectator %s', n)));
    run(str('spectate %s %s', cu, n)); global_grace:n = tick_time() + 2;
  );
);
_dist3(a, b) -> sqrt((a:0 - b:0) ^ 2 + (a:1 - b:1) ^ 2 + (a:2 - b:2) ^ 2);

_spawn_hits() -> (
  for (map(global_hits, entity_id(_)), if (_, modify(_, 'remove')));
  global_hits = [];
  for (range(global_NC),
    r = _smp(global_STOP - _ * global_GAP);
    for (range(global_SPC),
      sp = _seat_pt(r, _);
      h = spawn('interaction', [sp:0, sp:1 - 0.35, sp:2], _hit_nbt(length(global_hits)));
      global_hits += query(h, 'uuid');
    );
  );
);

// the train exists only while someone real is around the station (never "spawn because a selector found nothing")
_ensure() -> (
  if (global_state != 'load' || _ready(), return());
  if (!_near(96), return());
  c = global_CENTER;
  if (!loaded(c:0, c:1, c:2), return());
  _spawn();
);

__on_player_connects(p) -> if (global_OK && (query(p, 'has_tag', global_RIDER) || has(global_restore, p ~ 'name')), schedule(40, '_land', p ~ 'name', false));
__on_player_disconnects(p, reason) -> (n = p ~ 'name'; i = global_riders:n; if (i != null, _drop_rig(i); delete(global_riders, n)));

// ─────────────────────────────── commands / admin ───────────────────────────────
cmd_info() -> (
  if (!global_OK, print('No track yet: build it with blueprints/coaster/build.py'); return());
  p = player();
  n = if (p, p ~ 'name', '');
  print(format('b#FF5A1F ' + global_TITLE, 'w  · roller coaster'));
  print(str('Your rides: %d · your top speed: %d km/h · rides in total: %d',
    global_stats:'rides':n || 0, global_stats:'best':n || 0, global_stats:'total' || 0));
);
status() -> if (!global_OK, {'busy' -> false, 'state' -> if (global_REMOVED, 'removed', 'no track')},
  {'busy' -> global_state == 'run' || global_riders != {}, 'state' -> global_state, 's' -> round(global_s * 10) / 10, 'v' -> round(global_v * 100) / 100,
  'riders' -> global_riders, 'ready' -> _ready(), 'count' -> global_count, 'gen' -> global_gen, 'build' -> global_BUILD_TAG, 'model' -> global_MODEL_READY});
show_run() -> if (global_OK && global_state == 'load' && _ready(), _dispatch(); 'go', 'not ready');
stop() -> (
  if (!global_OK, return('no track'));
  for (keys(global_riders), _land(_, false));
  global_riders = {}; global_state = 'load'; global_v = 0; global_s = global_STOP; global_trav = 0;
  _forceload('remove');
  if (_ready(), _place(global_STOP)); _gates(true); _spawn_hits();
  'stopped'
);
respawn() -> (if (global_OK && global_state == 'load', _spawn(); 'ok', 'busy'));
// take the ride down: the train and every loaded part now, the rest of the track as its chunks load (the station's
// blocks stay: undo its build job for those)
remove() -> (
  if (!global_OK, return('no track'));
  if (global_state == 'run' || global_riders, return('busy: wait until the train is back (or stop() first)'));
  stop();
  for (entity_selector(str('@e[tag=%s]', global_APP)), modify(_, 'remove'));
  write_file('removed', 'json', {'build' -> global_TR:'build'}); delete_file('track', 'json');
  global_OK = false; global_REMOVED = true;
  'removed — static parts in unloaded chunks disappear when their chunk loads (keep this app loaded)'
);
