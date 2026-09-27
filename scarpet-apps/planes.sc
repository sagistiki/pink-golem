// planes.sc v3 — Air Bulbul flight (Claude 27/9, rewrite of Gemini's v2; backup: mcp-server/app-backups/planes.sc.gemini-20260927).
// Aircraft = an item_display body (model from planes_pack, gen_planes_pack.py) turned every tick by ONE quaternion
// (yaw · pitch · roll, left_rotation, interpolated over 2 ticks) + an interaction box (right-click = board) + one shared
// chase camera per aircraft (item_display, teleport_duration 2, far behind and above, heading smoothed) that every
// rider spectates. Up to 4 aboard; the first in flies, the others ride along (nobody is drawn — Sagi: "לא רואים אותם").
// Keys (Key Bridge → scoreboard `keys`): W throttle · S brake · Space nose up · Ctrl nose down · A/D bank + turn ·
// Shift = out (on the ground: beside the aircraft; in the air: parachute). Helicopter: Space/Ctrl up/down, W/S
// forward/back, A/D turn on the spot; the rotor is a second display the app spins.
// Flight model: lift = (v / stall speed)² caps gravity, so a slow aircraft sinks and a fast one holds height; holding
// W on the ground lifts the nose by itself above ~72 % of the top speed (comfortable take-off); banking turns;
// the ground is the real heightmap (roofs, the helipad), a wall stops the aircraft where it is; ceiling y 180.
// Fleet: spawned only when a real player is near the airport (generation tag + load handler remove stale copies);
// an empty aircraft away from its stand goes home after 3 min with nobody near. Test: set_keys(name, bits) feeds a
// fake player's keys (global_allow_fake = true lets fakes board through board(name, id)).

__config() -> {'stay_loaded' -> true, 'scope' -> 'global',
  'commands' -> {'home' -> 'cmd_home', 'out' -> 'cmd_out', 'list' -> 'cmd_list', 'fleet' -> 'cmd_fleet',
                 'here <type> <color>' -> 'cmd_here'},
  'arguments' -> {'type' -> {'type' -> 'term', 'suggest' -> ['fighter', 'private_jet', 'b737', 'helicopter']},
                  'color' -> {'type' -> 'term', 'suggest' -> ['white', 'pink', 'black', 'red', 'blue', 'gold', 'cyan', 'gray']}}};
import('hud', 'hud_show', 'hud_hide', 'hud_speedo', 'hud_compass', 'hud_text');

global_allow_fake = false;
global_G = 0.09;                  // gravity (blocks/tick²) that the lift has to cancel
global_CEIL = 180;
global_CENTER = [-215, 0];        // the fleet spawns when a real player is within 110 of it
// type -> [name, scale, top speed b/t, accel, turn deg/t, pitch deg/t, max bank, stall (fraction of top), cam distance,
//          cam height, heli, hit width, hit height, ground offset (fuselage axis above the wheels), mast height]
global_T = {
  'fighter'     -> ['BULBUL RAPTOR', 5.0, 2.4, 0.040, 3.0, 2.0, 45, 0.40, 13, 4.5, false, 7, 3, 1.125, 0],
  'private_jet' -> ['VIP JET', 6.0, 1.8, 0.028, 2.4, 1.6, 32, 0.40, 15, 5.0, false, 8, 3.5, 1.35, 0],
  'b737'        -> ['AIR BULBUL 737', 7.5, 1.5, 0.020, 1.8, 1.3, 26, 0.40, 20, 6.5, false, 11, 4.5, 2.156, 0],
  'helicopter'  -> ['VIP HELI', 5.0, 1.0, 0.030, 3.2, 0, 10, 0, 13, 5.0, true, 5, 3.5, 1.375, 1.4]};
global_COL = {'white' -> 15790320, 'pink' -> 16738740, 'black' -> 1908001, 'red' -> 12597547, 'blue' -> 3949738,
  'gold' -> 16766720, 'cyan' -> 1481884, 'gray' -> 8421504, 'silver' -> 12632256, 'green' -> 6192150};
// the airport fleet: [type, colour, x, y, z, yaw] — stands on the apron facing west (the runway), the heli on its pad
global_FLEET = [['fighter', 'gray', -230, -60, 8, 90], ['private_jet', 'white', -230, -60, -7, 90],
                ['b737', 'white', -230, -60, -20, 90], ['helicopter', 'pink', -205, -59, 24, 90]];

global_planes = {};       // id -> aircraft
global_gen = str('plane_g%d', floor(rand(1000000000)));
global_next = 1;
global_spawned = false;
global_fake_keys = {};
global_restore = {};

__on_start() -> (
  r = read_file('restore', 'json'); if (r, global_restore = r);
  for (keys(global_restore), if (player(_), _restore_player(_)));
  for (entity_selector('@e[tag=plane]'), if (!query(_, 'has_tag', global_gen), modify(_, 'remove')));
  for (['item_display', 'interaction'],
    entity_load_handler(_, _(e, new) -> if (!new, schedule(0, '_stale', query(e, 'uuid')))))
);
_stale(u) -> (e = entity_id(u); if (e, t = query(e, 'scoreboard_tags'); if (t && (t ~ 'plane') != null && (t ~ global_gen) == null, modify(e, 'remove'))));

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
_wrap(a) -> ((a % 360) + 540) % 360 - 180;

// ───────────── quaternions (JOML [x,y,z,w]; the display's local frame = world frame: x left, y up, z forward) ─────────────
_qmul(a, b) -> [a:3 * b:0 + a:0 * b:3 + a:1 * b:2 - a:2 * b:1,
                a:3 * b:1 - a:0 * b:2 + a:1 * b:3 + a:2 * b:0,
                a:3 * b:2 + a:0 * b:1 - a:1 * b:0 + a:2 * b:3,
                a:3 * b:3 - a:0 * b:0 - a:1 * b:1 - a:2 * b:2];
// heading h (Minecraft yaw: 0 south, 90 west), pitch p (negative = nose up, like the game), roll r (positive = right wing down)
_quat(h, p, r) -> _qmul(_qmul([0, sin(-h / 2), 0, cos(-h / 2)], [sin(p / 2), 0, 0, cos(p / 2)]), [0, 0, sin(r / 2), cos(r / 2)]);
_qrot(q, v) -> (
  tx = 2 * (q:1 * v:2 - q:2 * v:1); ty = 2 * (q:2 * v:0 - q:0 * v:2); tz = 2 * (q:0 * v:1 - q:1 * v:0);
  [v:0 + q:3 * tx + (q:1 * tz - q:2 * ty), v:1 + q:3 * ty + (q:2 * tx - q:0 * tz), v:2 + q:3 * tz + (q:0 * ty - q:1 * tx)]
);
_qs(q) -> str('%.4ff,%.4ff,%.4ff,%.4ff', q:0, q:1, q:2, q:3);

// ───────────── spawning ─────────────
_spawn_fleet() -> (
  for (entity_selector('@e[tag=plane]'), if (!query(_, 'has_tag', global_gen), modify(_, 'remove')));
  for (values(global_planes), for (range(4), if (_:'riders':_, _out(_, _))));
  for (values(global_planes), _remove(_));
  global_planes = {};
  for (global_FLEET, s = _; _new(s:0, s:1, [s:2, s:3, s:4], s:5, true));
  global_spawned = true
);

_new(type, color, q, yaw, home) -> (
  T = global_T:type; if (!T, return(null));
  id = global_next; global_next += 1;
  rgb = global_COL:color; if (rgb == null, rgb = number(color)); if (rgb == null, rgb = 15790320);
  tags = str('"plane","plane_%d","%s"', id, global_gen);
  s = T:1;
  body = spawn('item_display', q, str('{Tags:[%s],item:{id:"minecraft:paper",count:1,components:{"minecraft:item_model":"planes:%s","minecraft:dyed_color":%d}},teleport_duration:1,interpolation_duration:1,view_range:6f,shadow_radius:%.1ff,shadow_strength:0.6f,transformation:{left_rotation:[%s],right_rotation:[0f,0f,0f,1f],translation:[0f,%.3ff,0f],scale:[%.2ff,%.2ff,%.2ff]}}',
    tags, type, rgb, s * 0.4, _qs(_quat(yaw, 0, 0)), T:13, s, s, s));
  hit = spawn('interaction', q, str('{Tags:[%s],width:%.1ff,height:%.1ff,response:1b}', tags, T:11, T:12));
  rotor = null;
  if (T:10,
    rotor = query(spawn('item_display', q, str('{Tags:[%s],item:{id:"minecraft:paper",count:1,components:{"minecraft:item_model":"planes:rotor"}},teleport_duration:1,interpolation_duration:1,view_range:6f,transformation:{left_rotation:[0f,0f,0f,1f],right_rotation:[0f,0f,0f,1f],translation:[0f,0f,0f],scale:[%.2ff,%.2ff,%.2ff]}}',
      tags, s, s, s)), 'uuid'));
  pl = {'id' -> id, 'type' -> type, 'color' -> color, 'heli' -> T:10,
        'body' -> query(body, 'uuid'), 'hit' -> query(hit, 'uuid'), 'rotor' -> rotor, 'cam' -> null,
        'x' -> q:0, 'y' -> q:1, 'z' -> q:2, 'h' -> yaw, 'p' -> 0, 'r' -> 0, 'v' -> 0, 'vy' -> 0, 'air' -> false,
        'riders' -> [null, null, null, null], 'ch' -> yaw, 'idle' -> 0, 'spin' -> 0, 'rpm' -> 0,
        'home' -> if (home, [q:0, q:1, q:2, yaw], null)};
  global_planes:id = pl;
  _place(pl);
  id
);

_remove(pl) -> (
  for (['body', 'hit', 'rotor', 'cam'], u = pl:_; if (u, e = entity_id(u); if (e, modify(e, 'remove'))));
  delete(global_planes, pl:'id')
);

_id_of(e) -> (t = query(e, 'scoreboard_tags'); if (!t, return(null)); for (t, if (_ ~ '^plane_\\d+$', return(number(slice(_, 6))))); null);
_seat_of(n) -> (for (values(global_planes), pl = _; for (range(4), if (pl:'riders':_ == n, return([pl, _])))); null);
_ground(x, z) -> top('motion', floor(x), 0, floor(z));

// ───────────── boarding / leaving ─────────────
__on_player_interacts_with_entity(p, e, hand) -> (
  if (hand != 'mainhand' || query(e, 'type') != 'interaction', return());
  id = _id_of(e); if (id == null, return());
  if (!_real(p), return());
  board(p ~ 'name', id)
);

board(n, id) -> (
  p = player(n); pl = global_planes:id;
  if (!p || !pl || _seat_of(n) != null, return('no'));
  slot = null; for (range(4), if (slot == null && pl:'riders':_ == null, slot = _));
  if (slot == null, _msg(n, 'המטוס מלא', 'red'); return('full'));
  global_restore:n = {'mode' -> p ~ 'gamemode'}; write_file('restore', 'json', global_restore);
  pl:'riders':slot = n; pl:'idle' = 0;
  _cam(pl);
  if (query(p, 'mount'), run(str('ride %s dismount', n)));
  run(str('gamemode spectator %s', n));
  schedule(2, '_spectate', n, pl:'cam');
  name = global_T:(pl:'type'):0;
  if (slot == 0,
    _msg(n, if (pl:'heli', str('%s · W/S קדימה-אחורה · רווח/Ctrl למעלה-למטה · A/D סיבוב · החזק Shift 1.5 שניות = לצאת', name),
                          str('%s · W גז · S בלם · רווח = אף למעלה · Ctrl = אף למטה · A/D פנייה · החזק Shift 1.5 שניות = לצאת', name)), 'aqua'),
    _msg(n, str('%s · נוסע %d · הטייס: %s · החזק Shift 1.5 שניות = לצאת', name, slot, pl:'riders':0), 'yellow');
    _msg(pl:'riders':0, str('%s עלה למטוס', n), 'light_purple'));
  run(str('playsound minecraft:block.iron_door.close master @a %.1f %.1f %.1f 0.8 1.2', pl:'x', pl:'y', pl:'z'));
  'ok'
);
_spectate(n, u) -> run(str('spectate %s %s', u, n));

// the shared chase camera: made when the first rider boards, removed when the last one leaves
_cam(pl) -> (
  if (pl:'cam' && entity_id(pl:'cam'), return());
  T = global_T:(pl:'type');
  pl:'ch' = pl:'h';
  cq = _cam_pos(pl);
  cam = spawn('item_display', [cq:0, cq:1, cq:2], str('{Tags:["plane","plane_%d","%s"],teleport_duration:1,Rotation:[%.1ff,%.1ff]}', pl:'id', global_gen, cq:3, cq:4));
  pl:'cam' = query(cam, 'uuid')
);
_cam_pos(pl) -> (
  T = global_T:(pl:'type'); d = T:8; hh = T:9; h = pl:'h'; ch = pl:'ch';
  // the aircraft as the client draws it now = its position one tick ago (the display interpolates one tick behind)
  ax = if (pl:'px' != null, pl:'px', pl:'x'); ay = if (pl:'py' != null, pl:'py', pl:'y'); az = if (pl:'pz' != null, pl:'pz', pl:'z');
  cx = ax + sin(ch) * d; cz = az - cos(ch) * d; cy = ay + T:13 + hh;
  tx = ax - sin(h) * 4; tz = az + cos(h) * 4; ty = ay + T:13 + 0.5;               // look a little ahead of the aircraft
  dx = tx - cx; dz = tz - cz; dy = ty - cy;
  [cx, cy, cz, atan2(-dx, dz), atan2(-dy, sqrt(dx * dx + dz * dz))]
);
_cam_check(pl) -> (if (pl:'cam' && first(pl:'riders', _ != null) == null, e = entity_id(pl:'cam'); if (e, modify(e, 'remove')); pl:'cam' = null));

_compact(pl) -> (
  r = []; for (pl:'riders', if (_, r += _));
  while (length(r) < 4, 4, r += null);
  pl:'riders' = r
);

// slot -> out; the next rider becomes the pilot
_out(pl, slot) -> (
  n = pl:'riders':slot; if (!n, return());
  p = player(n);
  had_pilot = slot == 0;
  pl:'riders':slot = null; _compact(pl);
  hud_hide(n);
  if (p,
    run(str('execute as %s run spectate', n));
    rs = global_restore:n; if (rs, run(str('gamemode %s %s', rs:'mode', n)); delete(global_restore, n); write_file('restore', 'json', global_restore));
    modify(p, 'flying', false);
    T = global_T:(pl:'type');
    if (pl:'air' && pl:'y' > _ground(pl:'x', pl:'z') + 3,
      schedule(2, '_chute', n, pl:'x', pl:'y' - 1, pl:'z', pl:'h'),
      h = pl:'h'; d = T:11 / 2 + 1.5;
      schedule(2, '_put_down', n, pl:'x' + cos(h) * d, pl:'y', pl:'z' + sin(h) * d, h)));
  if (had_pilot && pl:'riders':0, _msg(pl:'riders':0, 'הטייס ירד — אתה מטיס עכשיו', 'aqua'));
  _cam_check(pl);
  run(str('playsound minecraft:block.iron_door.open master @a %.1f %.1f %.1f 0.8 1.1', pl:'x', pl:'y', pl:'z'))
);
_gone(pl, slot) -> (n = pl:'riders':slot; if (n, hud_hide(n); pl:'riders':slot = null; _compact(pl); _cam_check(pl)));

_chute(n, x, y, z, h) -> (
  p = player(n); if (!p, return());
  modify(p, 'flying', false);
  run(str('tp %s %.2f %.2f %.2f %.1f 10', n, x, y, z, h));
  run(str('effect give %s slow_falling 120 0 true', n));
  _msg(n, 'צניחה! ★', 'aqua')
);
_put_down(n, x, y, z, h) -> (
  p = player(n); if (!p, return());
  gy = floor(y); while (_solid(floor(x), gy, floor(z)) || _solid(floor(x), gy + 1, floor(z)), 6, gy += 1);
  while (!_solid(floor(x), gy - 1, floor(z)) && gy > y - 6, 6, gy += -1);
  modify(p, 'flying', false);
  run(str('tp %s %.2f %d %.2f %.1f 0', n, x, gy, z, h))
);
_solid(x, y, z) -> (b = block(x, y, z); !air(b) && solid(b));
_restore_player(n) -> (r = global_restore:n; if (r && player(n), run(str('gamemode %s %s', r:'mode', n)); delete(global_restore, n); write_file('restore', 'json', global_restore)));

__on_player_disconnects(p, r) -> (s = _seat_of(p ~ 'name'); if (s, _gone(s:0, s:1)));
__on_player_connects(p) -> (n = p ~ 'name'; if (has(global_restore, n), schedule(20, '_restore_player', n)));

// ───────────── the loop ─────────────
__on_tick() -> (
  t = tick_time();
  if (!global_spawned,
    if (t % 20 == 0 && first(player('all'), _real(_) && abs(pos(_):0 - global_CENTER:0) < 110 && abs(pos(_):2 - global_CENTER:1) < 110) != null, _spawn_fleet());
    return());
  for (values(global_planes),
    pl = _;
    for (range(4), n = pl:'riders':_; if (n && !player(n), _gone(pl, _)));
    pilot = pl:'riders':0;
    // a Shift TAP makes the game stop spectating the camera: put it back at once; only a HELD Shift gets you out
    for (range(4), n = pl:'riders':_; if (n && pl:'cam' && _bit(_keys(n), 32), _spectate(n, pl:'cam')));
    if (pilot,
      k = _keys(pilot);
      if (_hold(pilot, k), _out(pl, 0); continue());
      for (range(1, 4), n = pl:'riders':_; if (n && _hold(n, _keys(n)), _out(pl, _)));
      if (pl:'heli', _hover(pl, k, t), _fly(pl, k, t));
      pl:'idle' = 0,
      if (pl:'v' > 0.01 || pl:'air' || pl:'rpm' > 0.5 || pl:'vy' != 0,
        if (pl:'heli', _hover(pl, 0, t), _fly(pl, 0, t)),
        if (pl:'home' && t % 200 == 0, _maybe_home(pl))));
    moving = pl:'v' > 0.01 || pl:'air' || pl:'rpm' > 0.5;
    if (pilot || moving,
      _place(pl); _fx(pl, t);
      if (t % 4 == 0 && first(pl:'riders', _ != null) != null, _hud(pl)))
  )
);

_maybe_home(pl) -> (
  hm = pl:'home';
  if ((pl:'x' - hm:0) ^ 2 + (pl:'z' - hm:2) ^ 2 < 4, pl:'idle' = 0; return());
  pl:'idle' = pl:'idle' + 200;
  if (pl:'idle' >= 3600 && first(player('all'), sqrt((pos(_):0 - pl:'x') ^ 2 + (pos(_):2 - pl:'z') ^ 2) < 24) == null, _go_home(pl))
);
_go_home(pl) -> (hm = pl:'home'; if (!hm, return()); pl:'x' = hm:0; pl:'y' = hm:1; pl:'z' = hm:2; pl:'h' = hm:3; pl:'ch' = hm:3; pl:'px' = null; pl:'py' = null; pl:'pz' = null;
  pl:'p' = 0; pl:'r' = 0; pl:'v' = 0; pl:'vy' = 0; pl:'air' = false; pl:'idle' = 0; pl:'rpm' = 0; _place(pl));

// ───────────── fixed wing ─────────────
_fly(pl, k, t) -> (
  T = global_T:(pl:'type'); vmax = T:2; acc = T:3; turn = T:4; prate = T:5; bank = T:6; stall = T:7 * vmax;
  gas = _bit(k, 1); brk = _bit(k, 2); left = _bit(k, 4); right = _bit(k, 8); up = _bit(k, 16); down = _bit(k, 64);
  x = pl:'x'; y = pl:'y'; z = pl:'z'; h = pl:'h'; p = pl:'p'; r = pl:'r'; v = pl:'v'; air = pl:'air';
  pl:'px' = x; pl:'py' = y; pl:'pz' = z;
  // throttle
  if (gas, v = min(vmax, v + acc * (1.1 - 0.6 * v / vmax)), brk, v = max(0, v - acc * if (air, 0.9, 1.6)), v = v * if (air, 0.997, 0.975));
  if (air, v = max(0, min(vmax * 1.15, v + sin(p) * 0.03)));           // a dive gains speed, a climb bleeds it
  if (v < 0.003, v = 0);
  // pitch
  nobody = pl:'riders':0 == null;
  if (air,
    if (nobody, p = min(28, p + 0.5),                                  // abandoned: it comes down
      up, p = max(-50, p - prate), down, p = min(45, p + prate),
      v < stall * 0.7 && y - _ground(x, z) > 10, p = min(14, p + 0.4),  // stalled high up: the nose drops, the dive brings speed back
      p = p - p * 0.02),
    if (up && v > stall * 0.9, p = max(-14, p - prate),
      v >= vmax * 0.72 && !down, p = max(-10, p - 0.6),                // rotate by itself
      p = min(0, p + 1.0)));                                            // nose wheel on the ground
  // bank and turn
  want = if (right, 1, 0) - if (left, 1, 0);
  tr = if (air, want * bank * min(1, v / (stall * 1.2)), 0);
  r = r + (tr - r) * 0.10;
  if (air, h = h + (r / bank) * turn * min(1.2, v / stall * 0.8),
           h = h + want * turn * 0.9 * min(1, v / 0.45));
  // lift, vertical motion
  lift = if (air, min(1, (v / stall) ^ 2), 1);
  vy = -v * sin(p) - global_G * (1 - lift);
  if (!air && p <= -8 && v > stall * 0.9, air = true);                  // lifts off once the nose is up
  if (!air, vy = 0);                                                    // on the ground it rolls
  nx = x - sin(h) * v * cos(p); nz = z + cos(h) * v * cos(p); ny = y + vy;
  // the ground and the buildings
  g = _ground(nx, nz);
  if (ny <= g,
    if (y >= g - 1.2,
      ny = g; if (air && nobody, pl:'x' = nx; pl:'y' = g; pl:'z' = nz; _wreck(pl); return());
      if (air, _land(pl, vy, p, v)); air = false; if (p > 0, p = 0); vy = 0,
      nx = x; nz = z; ny = y; v = 0; if (nobody && air, pl:'y' = y; _wreck(pl); return()); _crash(pl)),
    if (!air && ny > g + 0.5, air = true));                             // rolled off an edge (a roof, the helipad)
  if (ny > global_CEIL, ny = global_CEIL; p = max(p, 0));
  pl:'x' = nx; pl:'y' = ny; pl:'z' = nz; pl:'h' = h; pl:'p' = p; pl:'r' = r; pl:'v' = v; pl:'vy' = vy; pl:'air' = air
);

_land(pl, vy, p, v) -> (
  hard = vy < -0.6 || p > 26;
  run(str('playsound minecraft:%s master @a %.1f %.1f %.1f %.2f %.2f', if (hard, 'entity.generic.explode', 'block.stone.break'),
    pl:'x', pl:'y', pl:'z', if (hard, 0.7, 0.6), if (hard, 1.6, 0.5)));
  run(str('particle minecraft:cloud %.2f %.2f %.2f 1.5 0.2 1.5 0.02 %d', pl:'x', pl:'y' + 0.2, pl:'z', if (hard, 30, 10)));
  if (hard, pl:'v' = v * 0.5; for (pl:'riders', if (_, _msg(_, 'נחיתה קשה!', 'red'))))
);
// nobody aboard and it hit the ground: a fireball, then the aircraft is back on its stand (Sagi 27/9)
_wreck(pl) -> (
  x = pl:'x'; y = pl:'y'; z = pl:'z';
  run(str('playsound minecraft:entity.generic.explode master @a[x=%d,y=%d,z=%d,distance=..160] %.1f %.1f %.1f 2.5 0.8', x, y, z, x, y, z));
  run(str('particle minecraft:explosion_emitter %.1f %.1f %.1f 1.5 0.5 1.5 0 3', x, y + 1, z));
  run(str('particle minecraft:flame %.1f %.1f %.1f 2.0 0.6 2.0 0.08 60', x, y + 0.5, z));
  run(str('particle minecraft:large_smoke %.1f %.1f %.1f 2.5 1.5 2.5 0.03 80', x, y + 1, z));
  pl:'air' = false; pl:'v' = 0; pl:'vy' = 0;
  if (pl:'home', _go_home(pl), pl:'p' = 0; pl:'r' = 0; _place(pl))
);
_crash(pl) -> (
  run(str('playsound minecraft:entity.generic.explode master @a %.1f %.1f %.1f 0.6 1.5', pl:'x', pl:'y', pl:'z'));
  run(str('particle minecraft:large_smoke %.2f %.2f %.2f 1.0 1.0 1.0 0.05 25', pl:'x', pl:'y' + 1, pl:'z'))
);

// ───────────── helicopter ─────────────
_hover(pl, k, t) -> (
  T = global_T:(pl:'type'); vmax = T:2; acc = T:3; turn = T:4;
  gas = _bit(k, 1); brk = _bit(k, 2); left = _bit(k, 4); right = _bit(k, 8); up = _bit(k, 16); down = _bit(k, 64);
  x = pl:'x'; y = pl:'y'; z = pl:'z'; h = pl:'h'; p = pl:'p'; r = pl:'r'; v = pl:'v'; vy = pl:'vy'; air = pl:'air';
  pl:'px' = x; pl:'py' = y; pl:'pz' = z;
  pilot = pl:'riders':0 != null;
  // rotor spins up with a pilot, winds down without
  pl:'rpm' = pl:'rpm' + (if (pilot, 42, 0) - pl:'rpm') * 0.04; if (pl:'rpm' < 0.5, pl:'rpm' = 0);
  pl:'spin' = (pl:'spin' + pl:'rpm') % 360;
  ready = pl:'rpm' > 30;
  if (!pilot && air, vy = max(-0.25, vy - 0.015),
    up && ready, vy = min(0.30, vy + 0.03), down, vy = max(-0.30, vy - 0.03), vy = vy * 0.85);
  if (!air && !up, vy = 0);
  if (gas && ready, v = min(vmax, v + acc), brk && ready, v = max(-vmax * 0.4, v - acc), v = v * 0.96);
  if (!air, v = v * 0.85);
  if (abs(v) < 0.003, v = 0);
  want = if (right, 1, 0) - if (left, 1, 0);
  if (air, h = h + want * turn);
  p = p + ((v / vmax) * 12 - p) * 0.1;
  r = r + (want * 8 * if (air, 1, 0) - r) * 0.1;
  nx = x - sin(h) * v; nz = z + cos(h) * v; ny = y + vy;
  g = _ground(nx, nz);
  if (ny <= g,
    if (y >= g - 1.2,
      ny = g; if (air && !pilot, pl:'x' = nx; pl:'y' = g; pl:'z' = nz; _wreck(pl); return());
      if (air && vy < -0.2, run(str('playsound minecraft:block.stone.break master @a %.1f %.1f %.1f 0.5 0.5', nx, ny, nz)));
      air = false; vy = 0; v = v * 0.5,
      nx = x; nz = z; ny = y; v = 0; vy = 0; if (!pilot && air, pl:'y' = y; _wreck(pl); return()); _crash(pl)),
    if (ny > g + 0.05, air = true));
  if (ny > global_CEIL, ny = global_CEIL; vy = 0);
  pl:'x' = nx; pl:'y' = ny; pl:'z' = nz; pl:'h' = h; pl:'p' = p; pl:'r' = r; pl:'v' = v; pl:'vy' = vy; pl:'air' = air
);

// ───────────── placing the parts + the camera ─────────────
_place(pl) -> (
  T = global_T:(pl:'type'); s = T:1;
  x = pl:'x'; y = pl:'y'; z = pl:'z';
  q = _quat(pl:'h', pl:'p', pl:'r');
  e = entity_id(pl:'body');
  if (e,
    modify(e, 'pos', [x, y, z]);
    modify(e, 'nbt_merge', str('{transformation:{left_rotation:[%s],right_rotation:[0f,0f,0f,1f],translation:[0f,%.3ff,0f],scale:[%.2ff,%.2ff,%.2ff]},start_interpolation:0}', _qs(q), T:13, s, s, s)));
  e = entity_id(pl:'hit'); if (e, modify(e, 'pos', [x, y, z]));
  if (pl:'rotor',
    e = entity_id(pl:'rotor');
    if (e,
      up = _qrot(q, [0, T:13 + T:14, 0]);
      qr = _qmul(q, [0, sin(pl:'spin' / 2), 0, cos(pl:'spin' / 2)]);
      modify(e, 'pos', [x + up:0, y + up:1, z + up:2]);
      modify(e, 'nbt_merge', str('{transformation:{left_rotation:[%s],right_rotation:[0f,0f,0f,1f],translation:[0f,0f,0f],scale:[%.2ff,%.2ff,%.2ff]},start_interpolation:0}', _qs(qr), s, s, s))));
  if (pl:'cam',
    pl:'ch' = pl:'ch' + _wrap(pl:'h' - pl:'ch') * 0.15;
    cq = _cam_pos(pl);
    e = entity_id(pl:'cam'); if (e, modify(e, 'location', cq:0, cq:1, cq:2, cq:3, cq:4)))
);

_fx(pl, t) -> (
  T = global_T:(pl:'type'); x = pl:'x'; y = pl:'y'; z = pl:'z'; v = abs(pl:'v');
  riders = filter(pl:'riders', _ != null);
  // the people aboard hear the engine at their own ears from the moment they board (their body is at the camera,
  // 13-20 blocks behind the aircraft, so a sound at the aircraft alone starts too late — Sagi 27/9)
  // everyone within 160 hears it at their own ears, quieter with distance (a low background hum far away — Sagi 27/9)
  loud = if (pl:'heli', pl:'rpm' > 2, v > 0.15);
  if (loud && t % if (pl:'heli', 3, 12) == 0,
    snd = if (pl:'heli', 'entity.phantom.flutter', 'item.elytra.flying');
    ptc = if (pl:'heli', 0.45 + pl:'rpm' / 42 * 0.35, 0.45 + v / T:2 * 0.6);
    for (player('all'),
      n = _ ~ 'name'; q = pos(_);
      d = sqrt((q:0 - x) ^ 2 + (q:1 - y) ^ 2 + (q:2 - z) ^ 2);
      vol = if (first(riders, _ == n) != null, 0.4, d > 160, 0, max(0.05, 0.45 * (1 - d / 160)));
      if (vol > 0, run(str('execute as %s at @s run playsound minecraft:%s master @s ~ ~ ~ %.2f %.2f', n, snd, vol, ptc)))));
  if (pl:'heli',
    if (pl:'air' && y - _ground(x, z) < 4 && t % 2 == 0,
      run(str('particle minecraft:cloud %.2f %.2f %.2f 2.0 0.1 2.0 0.01 4', x, _ground(x, z) + 0.2, z))),
    if (pl:'air' && v > T:2 * 0.5 && t % 2 == 0,
      h = pl:'h'; w = T:11 * 0.45; q = _quat(h, pl:'p', pl:'r');
      l = _qrot(q, [w, T:13, 3]); rr = _qrot(q, [-w, T:13, 3]);
      run(str('particle minecraft:cloud %.2f %.2f %.2f 0.05 0.05 0.05 0 1', x + l:0, y + l:1, z + l:2));
      run(str('particle minecraft:cloud %.2f %.2f %.2f 0.05 0.05 0.05 0 1', x + rr:0, y + rr:1, z + rr:2))))
);

_hud(pl) -> (
  T = global_T:(pl:'type');
  kmh = round(abs(pl:'v') * 72); alt = max(0, round(pl:'y' + 60));
  els = [hud_speedo(kmh, 200, 'KM/H', 'bottom_right'), hud_compass(pl:'h', 'top_centre'),
         hud_text(str('ALT %dM', alt), 'big', 0xFFFFFF, 'bottom_left', 0, 'left')];
  for (pl:'riders', if (_, hud_show(_, els)))
);

// ───────────── commands ─────────────
cmd_home() -> (p = player(); s = _seat_of(p ~ 'name'); if (!s || s:1 != 0, return('רק הטייס')); pl = s:0;
  for (range(4), if (pl:'riders':0, _out(pl, 0))); _go_home(pl); 'המטוס חזר לשדה');
cmd_out() -> (p = player(); s = _seat_of(p ~ 'name'); if (!s, return('אתה לא במטוס')); _out(s:0, s:1); 'ירדת');
cmd_list() -> map(values(global_planes), str('%d %s %s @ %.0f,%.0f,%.0f v %.2f %s riders %s', _:'id', _:'type', _:'color', _:'x', _:'y', _:'z', _:'v', if (_:'air', 'AIR', 'GND'), join(',', filter(_:'riders', _ != null))));
cmd_fleet() -> (_spawn_fleet(); str('fleet: %d aircraft', length(global_planes)));
cmd_here(type, color) -> (p = player(); q = pos(p); if (!global_T:type, return('types: ' + join(', ', keys(global_T)))); global_spawned = true; id = _new(type, color, [q:0, _ground(q:0, q:2), q:2], query(p, 'yaw'), false); str('aircraft %d', id));
status() -> (
  aboard = []; for (values(global_planes), for (_:'riders', if (_, aboard += _)));
  {'busy' -> length(aboard) > 0, 'aboard' -> aboard, 'aircraft' -> length(global_planes), 'spawned' -> global_spawned}
);
