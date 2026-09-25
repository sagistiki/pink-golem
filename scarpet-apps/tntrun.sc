// tntrun.sc — TNT Run: every block you step on vanishes, the last player standing wins (arena: blueprints/tnt_run.py).
// The arena is read from tntrun.data/arena.json = {"cx": X, "gy": Y, "cz": Z} (the arena centre on the ground block).
// setup() writes it; blueprints/tnt_run.py ends with  script in tntrun run setup(X, Y, Z)  so you rarely call it by hand.
// Without an arena file the app idles and logs a hint. Everything else is derived from the centre: floors at Y+30,
// Y+23, Y+16, Y+9 (radius 16.4), the gold JOIN pad x X-2..X+2 z Z-32..Z-28, the viewing gallery at Y+16 to the north.
//
// Join: STAND on the gold pad (no clicking). A 10 s countdown starts (more players can step on), then everyone on the
// pad is teleported to the top floor. Every floor block you stand on turns red and vanishes after 0.4 s (0.2 s after
// one minute); after 90 s the floors crumble by themselves. Shift in the air = double jump (3 per game). Below the last
// floor (or over the wall) = out → viewing gallery. 2+ players: the last one standing wins. Alone: survival-time
// record. Players are in adventure mode with resistance (no fall damage) during a game; their game mode comes back
// after, also if they disconnect and come back later. Records: tntrun.data/records.json + the board in the lobby.
// The floors are rebuilt 5 s after every game, with a few random holes on the lower floors.
//
// Testing with fake players (Carpet): set global_allow_fake = true below, `script load tntrun`, then spawn two
//   /player Alice spawn at <X> <Y+1> <Z-30>      /player Bob spawn at <X+1> <Y+1> <Z-30>
// on the pad: countdown → top floor → they stand still, the blocks vanish under them, they fall floor by floor and the
// last one wins. `/player Alice kill` removes one. Set global_allow_fake back to false when done.
// Reload after editing arena.json:  script in tntrun run reload()      Reload the code: script load tntrun
// (never during a game: check  script in tntrun run global_state  first).

__config() -> {'stay_loaded' -> true, 'scope' -> 'global'};

global_allow_fake = false;
global_ready = false;
global_R = 16.4;
global_mats = {'pink_concrete' -> 1, 'white_concrete' -> 1, 'yellow_concrete' -> 1, 'orange_concrete' -> 1, 'lime_concrete' -> 1,
               'light_blue_concrete' -> 1, 'purple_concrete' -> 1, 'magenta_concrete' -> 1};
global_state = 'idle';
global_cd = 0;
global_t0 = 0;
global_grace = 0;
global_delay = 8;
global_alive = {};
global_all = [];
global_order = [];
global_restore = {};
global_rec = {'wins' -> {}, 'best' -> {}};

// ───────────── arena ─────────────
setup(cx, gy, cz) -> (
  if (global_state == 'playing' || global_state == 'countdown', return('a game is running — run setup again after it'));
  a = {'cx' -> cx, 'gy' -> gy, 'cz' -> cz};
  write_file('arena', 'json', a);
  _derive(a);
  _spawn_board();
  str('TNT Run arena at %d %d %d — stand on the gold pad at %d %d %d to play', cx, gy, cz, cx, gy + 1, cz - 30)
);

// re-read arena.json and records.json (after editing them by hand)
reload() -> (
  if (global_state == 'playing' || global_state == 'countdown', return('a game is running — reload after it'));
  r = read_file('records', 'json'); if (r, global_rec = r);
  a = read_file('arena', 'json');
  if (!a, return('no arena yet — run setup(x, y, z) with the arena centre on the ground block'));
  _derive(a);
  _spawn_board();
  str('arena at %d %d %d', a:'cx', a:'gy', a:'cz')
);

_derive(a) -> (
  cx = a:'cx'; gy = a:'gy'; cz = a:'cz';
  global_c = [cx, cz];
  global_floors = [gy + 30, gy + 23, gy + 16, gy + 9];                 // top → bottom
  global_pad = [cx - 2, gy, cz - 32, cx + 3, gy + 4, cz - 27];         // x1 y1 z1 (inclusive) → x2 y2 z2 (exclusive)
  global_pad_snd = [cx, gy + 2, cz - 30];
  global_lobby = [cx + 0.5, gy + 1, cz - 33.5];                        // just off the pad, under the canopy
  global_gallery = [cx + 0.5, gy + 17, cz - 20.5];
  global_board = [cx + 10.5, gy + 3.8, cz - 29.5];
  global_area = str('@a[x=%d,y=%d,z=%d,dx=70,dy=100,dz=75]', cx - 34, gy - 3, cz - 52);   // arena + lobby
  global_ready = true
);

_real(p) -> global_allow_fake || (p ~ 'player_type') != 'fake';
_mod(a, b) -> (r = a % b; if (r < 0, r + b, r));
_msg(p, t, c) -> run(str('title %s actionbar %s', p ~ 'name', encode_json({'text' -> t, 'color' -> c, 'bold' -> true})));
_say(t, c) -> run(str('tellraw %s %s', global_area, encode_json([{'text' -> '[TNT RUN] ', 'color' -> 'red', 'bold' -> true}, {'text' -> t, 'color' -> c}])));
_snd(s, p, v, pt) -> run(str('playsound %s master @a %.1f %.1f %.1f %.1f %.2f', s, p:0, p:1, p:2, v, pt));
_on_pad(p) -> (q = pos(p); b = global_pad; q:0 >= b:0 && q:0 < b:3 && q:2 >= b:2 && q:2 < b:5 && q:1 >= b:1 && q:1 < b:4);
_dist(q) -> sqrt((q:0 - global_c:0 - 0.5) ^ 2 + (q:2 - global_c:1 - 0.5) ^ 2);
_clock(s) -> str('%d:%02d', floor(s / 60), floor(s % 60));
_is_floor(y) -> (for (global_floors, if (_ == y, return(true))); false);
_save_restore() -> write_file('restore', 'json', global_restore);

__on_start() -> (
  r = read_file('records', 'json'); if (r, global_rec = r);
  rs = read_file('restore', 'json'); if (rs, global_restore = rs);
  run('bossbar add tntrun:bar ""');
  run('bossbar set tntrun:bar color red');
  run('bossbar set tntrun:bar style notched_10');
  run('bossbar set tntrun:bar visible false');
  a = read_file('arena', 'json');
  if (a,
    _derive(a);
    schedule(20, '_spawn_board');
    // players still in adventure mode from a game the server (or a reload) interrupted get their mode back
    for (keys(global_restore), if (player(_), schedule(20, '_restore_late', _))),
    logger('warn', '[tntrun] no arena yet: build blueprints/tnt_run.py, or run  script in tntrun run setup(x, y, z)  with the arena centre on the ground block')
  )
);

_spawn_board() -> (
  if (!global_ready, return());
  run('kill @e[tag=tr_board]');
  run(str('summon text_display %.1f %.1f %.1f {billboard:"center",Tags:["tr_board"],alignment:"center",background:1426063360,shadow:1b,line_width:220,brightness:{sky:15,block:15},transformation:{left_rotation:[0f,0f,0f,1f],right_rotation:[0f,0f,0f,1f],translation:[0f,0f,0f],scale:[0.55f,0.55f,0.55f]},text:""}',
    global_board:0, global_board:1, global_board:2));
  _board()
);

// the 5 best entries of a name -> number map, best first ([] for an empty map: sort/slice fail on nothing)
_top(m) -> (if (!m, return([])); l = sort_key(pairs(m), -(_:1)); if (length(l) > 5, slice(l, 0, 5), l));

_board() -> (
  c = [{'text' -> '★ TNT RUN RECORDS ★\n', 'color' -> 'gold', 'bold' -> true}, {'text' -> 'Wins\n', 'color' -> 'red', 'bold' -> true}];
  w = _top(global_rec:'wins');
  if (!w, c += {'text' -> '—\n', 'color' -> 'gray'});
  for (w, c += {'text' -> str('%d. %s  %d\n', _i + 1, _:0, _:1), 'color' -> if (_i == 0, 'yellow', 'white')});
  c += {'text' -> 'Longest run\n', 'color' -> 'aqua', 'bold' -> true};
  bt = _top(global_rec:'best');
  if (!bt, c += {'text' -> '—', 'color' -> 'gray'});
  for (bt, c += {'text' -> str('%d. %s  %s\n', _i + 1, _:0, _clock(_:1)), 'color' -> if (_i == 0, 'yellow', 'white')});
  for (entity_selector('@e[tag=tr_board]'), run(str('data merge entity %s {text:%s}', query(_, 'uuid'), encode_json(c))))
);

__on_player_connects(p) -> (
  n = p ~ 'name';
  if (has(global_restore, n), schedule(20, '_restore_late', n))
);
_restore_late(n) -> (
  p = player(n); g = global_restore:n;
  if (p && g && global_ready && !has(global_alive, n),
    run(str('gamemode %s %s', g, n));
    run(str('effect clear %s minecraft:resistance', n));
    run(str('tp %s %.1f %.1f %.1f', n, global_lobby:0, global_lobby:1, global_lobby:2));
    delete(global_restore, n);
    _save_restore()
  )
);

// ───────────── tick ─────────────
__on_tick() -> (
  if (!global_ready, return());
  t = tick_time();
  if (global_state == 'playing', _play_tick(t));
  if (t % 10 == 0, _lobby_tick(t));
  if (t % 20 == 0, _bar(t));
);

_lobby_tick(t) -> (
  if (global_state != 'idle' && global_state != 'countdown', return());
  pad = filter(player('all'), _real(_) && _on_pad(_));
  if (!pad,
    if (global_state == 'countdown', global_state = 'idle'; _say('Everyone left the pad — game cancelled', 'gray'));
    return()
  );
  if (global_state == 'idle',
    global_state = 'countdown'; global_cd = t + 200;
    _say((pad:0 ~ 'name') + ' is on the pad! Starting in 10 seconds — who else is in?', 'yellow');
    _snd('block.note_block.pling', global_pad_snd, 1, 1.2)
  );
  left = ceil((global_cd - t) / 20);
  n = length(pad);
  for (pad, _msg(_, str('⏱ Starting in %d s · %d player%s', left, n, if (n == 1, '', 's')), 'yellow'));
  if (left <= 3 && left > 0 && t % 20 == 0,
    for (pad, run(str('title %s title %s', _ ~ 'name', encode_json({'text' -> str('%d', left), 'color' -> 'red', 'bold' -> true}))));
    _snd('block.note_block.hat', global_pad_snd, 1, 1.0)
  );
  if (t >= global_cd, _start(pad))
);

_bar(t) -> (
  if (global_state == 'playing',
    el = (t - global_t0) / 20;
    run(str('bossbar set tntrun:bar name %s', encode_json([{'text' -> 'TNT RUN', 'color' -> 'red', 'bold' -> true},
      {'text' -> str('  ·  %d left  ·  %s', length(global_alive), _clock(el)), 'color' -> 'white'},
      {'text' -> if (el >= 90, '  ·  the floor is crumbling!', el >= 60, '  ·  double speed!', ''), 'color' -> 'gold'}])));
    run(str('bossbar set tntrun:bar value %d', min(100, floor(el * 100 / 120))));
    run('bossbar set tntrun:bar visible true'),
    global_state == 'countdown',
    run(str('bossbar set tntrun:bar name %s', encode_json({'text' -> str('TNT RUN starts in %d s — step on the gold pad!', max(0, ceil((global_cd - t) / 20))), 'color' -> 'yellow', 'bold' -> true})));
    run(str('bossbar set tntrun:bar value %d', max(0, floor((global_cd - t) / 2))));
    run('bossbar set tntrun:bar visible true'),
    run('bossbar set tntrun:bar visible false')
  );
  run('bossbar set tntrun:bar players ' + global_area)
);

// ───────────── game ─────────────
_start(ps) -> (
  global_state = 'playing';
  global_t0 = tick_time(); global_grace = global_t0 + 50; global_delay = 8;
  global_alive = {}; global_all = map(ps, _ ~ 'name'); global_order = [];
  n = length(ps);
  for (ps,
    p = _; nm = p ~ 'name';
    global_alive:nm = {'gm' -> (p ~ 'gamemode'), 'jumps' -> 3, 'sneak' -> false};
    global_restore:nm = p ~ 'gamemode';
    run(str('gamemode adventure %s', nm));
    run(str('effect give %s minecraft:resistance infinite 255 true', nm));
    a = 360 * _i / n + rand(25); r = 3 + rand(8);
    run(str('tp %s %.2f %d %.2f %.0f 0', nm, global_c:0 + 0.5 + r * cos(a), global_floors:0 + 1, global_c:1 + 0.5 + r * sin(a), rand(360)));
    run(str('title %s title %s', nm, encode_json({'text' -> 'RUN!', 'color' -> 'red', 'bold' -> true})));
    run(str('title %s subtitle %s', nm, encode_json({'text' -> 'Keep moving · Shift in the air = double jump', 'color' -> 'yellow'})))
  );
  _save_restore();
  _snd('entity.tnt.primed', [global_c:0, global_floors:0 + 2, global_c:1], 2, 1.0);
  _say(str('▶ Game on! %d player%s: %s', n, if (n == 1, '', 's'), join(', ', global_all)), 'gold')
);

_play_tick(t) -> (
  el = t - global_t0;
  if (el == 1200, global_delay = 4; _say('One minute in — the floor vanishes twice as fast!', 'gold'));
  if (el == 1800, _say('90 seconds — the floor is crumbling!', 'red'));
  if (el > 1800 && t % 10 == 0, _crumble());
  for (keys(global_alive),
    nm = _;
    // an earlier player in this loop may have ended the game (or this one already won)
    if (global_state != 'playing' || !has(global_alive, nm), continue());
    p = player(nm);
    if (!p, _out(nm, 'left the server'); continue());
    q = pos(p);
    if (q:1 < global_floors:3 - 3 || _dist(q) > 18.5 || (p ~ 'dimension') != 'overworld', _out(nm, 'fell'); continue());
    st = global_alive:nm; sn = p ~ 'sneaking';
    if (sn && !st:'sneak' && !(p ~ 'on_ground') && st:'jumps' > 0,
      lk = p ~ 'look';
      modify(p, 'motion', lk:0 * 0.6, 0.85, lk:2 * 0.6);
      st:'jumps' = st:'jumps' - 1;
      _snd('entity.breeze.jump', q, 1, 1.2);
      particle('cloud', q, 16, 0.3);
      _msg(p, str('✦ Double jump! %d left', st:'jumps'), 'aqua')
    );
    st:'sneak' = sn; global_alive:nm = st;
    if (t >= global_grace && (p ~ 'on_ground'), _step(q))
  )
);

// the (up to 4) floor blocks under the player's feet turn red, then vanish global_delay ticks later
_step(q) -> (
  by = floor(q:1 - 0.1);
  if (!_is_floor(by), return());
  for ([[-0.3, -0.3], [0.3, -0.3], [-0.3, 0.3], [0.3, 0.3]],
    bx = floor(q:0 + _:0); bz = floor(q:2 + _:1);
    if (has(global_mats, str(block(bx, by, bz))),
      set(bx, by, bz, 'red_concrete');
      schedule(global_delay, '_vanish', bx, by, bz)
    )
  )
);

_vanish(x, y, z) -> (
  if (str(block(x, y, z)) == 'red_concrete',
    set(x, y, z, 'air');
    if (str(block(x, y - 1, z)) == 'tnt', set(x, y - 1, z, 'air'));
    particle('poof', [x + 0.5, y + 0.5, z + 0.5], 2, 0.2);
    if (rand(1) < 0.3, _snd('block.wool.break', [x, y, z], 0.4, 0.8 + rand(0.4)))
  )
);

_crumble() -> (
  c = global_c;
  for (global_floors,
    y = _;
    loop(4,
      a = rand(360); r = sqrt(rand(1)) * 16;
      x = c:0 + round(r * cos(a)); z = c:1 + round(r * sin(a));
      if (has(global_mats, str(block(x, y, z))), set(x, y, z, 'red_concrete'); schedule(6, '_vanish', x, y, z))
    )
  )
);

_back(nm, st, to) -> (
  p = player(nm);
  if (p,
    run(str('gamemode %s %s', st:'gm', nm));
    run(str('effect clear %s minecraft:resistance', nm));
    run(str('tp %s %.1f %.1f %.1f 0 0', nm, to:0, to:1, to:2));
    delete(global_restore, nm);
    _save_restore()
  )
);

_secs() -> (tick_time() - global_t0) / 20;

// personal best survival time; nested maps are updated through a local copy, then stored back
_best(nm, s) -> (
  bm = global_rec:'best'; b = bm:nm;
  if (b == null || s > b, bm:nm = round(s * 10) / 10; global_rec:'best' = bm; true, false)
);

_out(nm, why) -> (
  st = global_alive:nm; delete(global_alive, nm);
  s = _secs();
  global_order += nm;
  rec = _best(nm, s);
  _back(nm, st, global_gallery);
  p = player(nm);
  if (p, _msg(p, str('You fell! You lasted %s%s', _clock(s), if (rec, ' — new personal best!', '')), 'red'));
  _snd('entity.generic.explode', [global_c:0, global_floors:3, global_c:1], 0.6, 1.4);
  if (global_alive, _say(str('%s %s after %s · %d left', nm, why, _clock(s), length(global_alive)), 'white'));
  _check_end()
);

_check_end() -> (
  if (global_state != 'playing', return());
  k = length(global_alive); tot = length(global_all);
  if (tot >= 2 && k == 1, _win(keys(global_alive):0),
      k == 0, if (tot >= 2, _win(global_order:(-1)), _solo_end(global_order:(-1))))
);

_win(nm) -> (
  global_state = 'ending';
  s = _secs();
  st = global_alive:nm;
  if (st, delete(global_alive, nm); _best(nm, s); _back(nm, st, global_lobby));
  wm = global_rec:'wins'; wm:nm = if (wm:nm, wm:nm + 1, 1); global_rec:'wins' = wm;
  write_file('records', 'json', global_rec);
  nw = global_rec:'wins':nm;
  for (global_all,
    run(str('title %s title %s', _, encode_json({'text' -> nm + ' wins!', 'color' -> 'gold', 'bold' -> true})));
    run(str('title %s subtitle %s', _, encode_json({'text' -> str('TNT RUN · %s · %d win%s', _clock(s), nw, if (nw == 1, '', 's')), 'color' -> 'yellow'})))
  );
  _say(str('★ %s wins TNT RUN after %s! ★', nm, _clock(s)), 'gold');
  for (range(6), schedule(_ * 8, '_fw'));
  schedule(100, '_reset');
  _board()
);

_solo_end(nm) -> (
  global_state = 'ending';
  write_file('records', 'json', global_rec);
  b = global_rec:'best':nm;
  run(str('title %s title %s', nm, encode_json({'text' -> 'Game over', 'color' -> 'red', 'bold' -> true})));
  run(str('title %s subtitle %s', nm, encode_json({'text' -> 'Your best: ' + _clock(b) + ' · try it with friends!', 'color' -> 'yellow'})));
  schedule(100, '_reset');
  _board()
);

_fw() -> run(str('summon firework_rocket %.1f %.1f %.1f {LifeTime:25,FireworksItem:{id:"minecraft:firework_rocket",count:1,components:{"minecraft:fireworks":{flight_duration:1,explosions:[{shape:"large_ball",colors:[I;16711680,16777215,16755200],has_twinkle:true}]}}}}',
  global_c:0 + rand(20) - 10, global_floors:0 + 1, global_c:1 + rand(20) - 10));

_reset() -> (
  _build_floors();
  global_state = 'idle';
  _say('Floors rebuilt — step on the gold pad for the next round!', 'green')
);

// top block of floor k at offset (dx, dz) — identical to pattern() in blueprints/tnt_run.py
_pat(k, dx, dz) -> (
  r = sqrt(dx * dx + dz * dz); a = _mod(atan2(dz, dx), 360);
  if (k == 0, if (floor(r) % 4 < 2, 'pink_concrete', 'white_concrete'),
      k == 1, if (_mod(floor(dx / 2) + floor(dz / 2), 2) == 0, 'yellow_concrete', 'orange_concrete'),
      k == 2, if (floor((a + r * 14) / 30) % 2 == 0, 'lime_concrete', 'light_blue_concrete'),
      if (floor(a / 22.5) % 2 == 0, 'purple_concrete', 'magenta_concrete'))
);

// rebuild all four floors over their TNT; every game after the first gets a few random holes on the lower floors
_build_floors() -> (
  if (!global_ready, return('no arena yet — run setup(x, y, z) first'));
  c = global_c; holes = [0, 0.03, 0.06, 0.1];
  for (range(4),
    k = _; y = global_floors:k;
    for (range(-17, 18),
      dx = _;
      for (range(-17, 18),
        dz = _;
        if (sqrt(dx * dx + dz * dz) <= global_R,
          if (rand(1) < holes:k,
            set(c:0 + dx, y, c:1 + dz, 'air'); set(c:0 + dx, y - 1, c:1 + dz, 'air'),
            set(c:0 + dx, y, c:1 + dz, _pat(k, dx, dz)); set(c:0 + dx, y - 1, c:1 + dz, 'tnt')
          )
        )
      )
    )
  );
  'floors rebuilt'
);
