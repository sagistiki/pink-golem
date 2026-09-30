// arcade.sc — the tower arcade & bowling floor, without client mods.
//  • Bowling: 3 lanes. Join/start with the two vanilla buttons on each lane's console; on your turn stand on the approach
//    with your ball (a dye-tinted item) — right-click starts the power meter, right-click again throws in the direction you
//    look (±7°). The ball rolls with light friction, drops into the gutter if it leaves the lane, hits pins by distance;
//    moving pins knock standing ones (with a little randomness). Real scoring (strikes, spares, the last frame), 5 frames,
//    a score screen above each lane.
//  • Claw machine (5 buttons, 3 tickets a play), whack-a-mole (left-click the moles, 30 s), rhythm dance floor (step on
//    the lit tile before the next beat). Every game pays tickets; the prize counter trades them; a high-score board.
// Data: arcade.data/layout.json (from the build generator), tickets.json, scores.json (runtime).
// Commands: /arcade tickets | prize <id> | close ;  ops: /arcade reset | give <name> <n>.  Admin: script in arcade run status()

__config() -> {
  'stay_loaded' -> true, 'scope' -> 'global', 'command_permission' -> 'all',
  'commands' -> {'tickets' -> '_cmd_tickets', 'prize <id>' -> '_cmd_prize', 'close' -> '_cmd_close',
                 'reset' -> '_cmd_reset', 'give <name> <n>' -> '_cmd_give'},
  'arguments' -> {'id' -> {'type' -> 'term'}, 'name' -> {'type' -> 'term'}, 'n' -> {'type' -> 'int'}}
};

global_L = {};
global_tickets = {};
global_best = {};
global_ents = {};
global_cool = {};
global_prev = {};
global_lanes = {};
global_claw = {'on' -> false};
global_whack = {'on' -> false};
global_rhythm = {'on' -> false};
global_use_cd = {};
global_allow_fake = false;
global_frames = 5;
global_colors = [16727717, 4113919, 8191066, 16765502];            // #FF3EA5 #3EC5FF #7CFC5A #FFD23E
global_pin_off = [[0, 0], [-0.36, -0.62], [0.36, -0.62], [-0.72, -1.24], [0, -1.24], [0.72, -1.24],
                  [-1.08, -1.86], [-0.36, -1.86], [0.36, -1.86], [1.08, -1.86]];
global_pin_y = 19.375;   // scale 0.75: the pin model's foot (y 0) sits on the floor at 19
global_ball_y = 19.175;  // scale 0.7: the ball model's bottom (y 4) on the floor
global_prizes = {
  'bunny' -> ['🐰 Bunny plush', 15, 'paper[item_model="arcade:plush_bunny",custom_name={text:"Bunny plush",color:"#FF96C8",italic:false}]', 1],
  'frog' -> ['🐸 Frog plush', 15, 'paper[item_model="arcade:plush_frog",custom_name={text:"Frog plush",color:"#6EC85A",italic:false}]', 1],
  'star' -> ['⭐ Star plush', 20, 'paper[item_model="arcade:plush_star",custom_name={text:"Star plush",color:"#FFD63C",italic:false}]', 1],
  'golem' -> ['💗 Pink Golem plush', 30, 'paper[item_model="arcade:plush_golem",custom_name={text:"Pink Golem plush",color:"#FF96C8",italic:false}]', 1],
  'cake' -> ['🎂 Cake', 6, 'cake', 1],
  'rockets' -> ['🎆 3 fireworks', 8, 'firework_rocket', 3],
  'cookies' -> ['🍪 5 cookies', 3, 'cookie', 5],
  'tulip' -> ['🌷 Pink tulip', 4, 'pink_tulip', 1]
};
global_claw_prizes = ['plush_bunny', 'plush_frog', 'plush_star', 'plush_golem', 'plush_bunny', 'plush_frog'];

// ───────────── helpers ─────────────
_bar(p, text, color) -> run(str('title %s actionbar %s', p ~ 'name', encode_json({'text' -> text, 'color' -> color})));
_real(p) -> p && ((p ~ 'player_type') != 'fake' || global_allow_fake);
_admin(p) -> (p ~ 'permission_level') >= 2;
_snd(q, s, v, pt) -> run(str('playsound %s master @a %.2f %.2f %.2f %.2f %.2f', s, q:0, q:1, q:2, v, pt));
_ent(tag) -> entity_id(global_ents:tag);
// one-off moves (a pin falls, a mole pops, a prize drops, the dance seat snaps) use vanilla tp, not modify(): Carpet's own
// position packet + the tracker's delta from the old spot left the entity drawn one move too far
_mv(e, x, y, z) -> run(str('tp %s %.4f %.4f %.4f', query(e, 'uuid'), x, y, z));
_tf(s) -> str('transformation:{left_rotation:[0f,0f,0f,1f],right_rotation:[0f,0f,0f,1f],translation:[0f,0f,0f],scale:[%.3ff,%.3ff,%.3ff]}', s, s, s);
_tfq(q, s) -> str('{transformation:{left_rotation:[%.4ff,%.4ff,%.4ff,%.4ff],right_rotation:[0f,0f,0f,1f],translation:[0f,0f,0f],scale:[%.3ff,%.3ff,%.3ff]},start_interpolation:0,interpolation_duration:3}', q:0, q:1, q:2, q:3, s, s, s);
_item(model) -> str('item:{id:"minecraft:paper",count:1,components:{"minecraft:item_model":"%s"}}', model);
_one(tag, type, at, nbt) -> (
  e = _ent(tag); if (e, return(e));
  l = entity_selector(str('@e[type=%s,tag=%s]', type, tag));
  if (l, (global_ents:tag = query(l:0, 'uuid'); for (slice(l, 1), modify(_, 'remove')); return(l:0)));
  if (loaded_status(at) < 3 || tick_time() < (global_cool:tag || 0), return(null));
  global_cool:tag = tick_time() + 600;
  e = spawn(type, at, str('{Tags:["arcade","%s"],%s}', tag, nbt));
  if (e, global_ents:tag = query(e, 'uuid'));
  e
);
_pressed(key, q) -> (
  if (loaded_status(q) < 3, return(false));
  on = str(block_state(block(q), 'powered')) == 'true';
  r = on && !global_prev:key; global_prev:key = on; r
);
_near(q, r) -> (
  best = null; bd = r * r;
  for (player('all'), if (_real(_), (d = reduce(pos(_) - (q + 0.5), _a + _ * _, 0); if (d < bd, (bd = d; best = _)))));
  best
);
_floor_busy() -> first(player('all'), _real(_) && abs(pos(_):1 - 23) < 12 && abs(pos(_):0 + 65) < 24 && abs(pos(_):2 + 105) < 24) != null;

// ───────────── tickets, records, prize counter ─────────────
_tk(n) -> global_tickets:n || 0;
_save_tk() -> write_file('tickets', 'json', global_tickets);
_pay(p, k) -> (
  n = p ~ 'name'; global_tickets:n = _tk(n) + k; _save_tk();
  if (k > 0, (_bar(p, str('+%d tickets ✦ you have %d', k, global_tickets:n), '#FFE14D');
              run(str('playsound minecraft:entity.experience_orb.pickup master %s ~ ~ ~ 0.8 1.2', n))))
);
_record(game, name, score) -> (
  l = global_best:game || [];
  // one line per player: their personal best only
  old = first(l, _:'name' == name);
  if (old != null && old:'score' >= score, return());
  l = filter(l, _:'name' != name);
  l += {'name' -> name, 'score' -> score};
  l = sort_key(l, -_:'score');
  if (length(l) > 5, l = slice(l, 0, 5));
  global_best:game = l;
  write_file('scores', 'json', global_best);
  _board()
);
_board() -> (
  e = _ent('arc_board'); if (!e, return());
  lines = [{'text' -> '✦ High scores ✦\n', 'color' -> '#FF3EA5', 'bold' -> true}];
  for ([['bowling', '🎳 Bowling'], ['whack', '🔨 Whack-a-mole'], ['rhythm', '💃 Dance']], (
    g = _:0;
    lines += {'text' -> _:1 + '\n', 'color' -> '#FFE14D', 'bold' -> true};
    l = global_best:g || [];
    if (!l, lines += {'text' -> '—\n', 'color' -> 'gray', 'bold' -> false});
    for (l, lines += {'text' -> str('%d. %s · %d\n', _i + 1, _:'name', _:'score'), 'color' -> 'white', 'bold' -> false})
  ));
  modify(e, 'nbt_merge', str('{text:%s}', encode_json(lines)))
);
_btn(label, cmd) -> {'label' -> label, 'width' -> 180, 'action' -> {'type' -> 'run_command', 'command' -> cmd}};
_counter(p) -> (
  acts = map(keys(global_prizes), _btn(str('%s · %d', global_prizes:_:0, global_prizes:_:1), '/arcade prize ' + _));
  d = {'type' -> 'minecraft:multi_action', 'title' -> {'text' -> '🎟 Prize counter', 'color' -> '#FF3EA5', 'bold' -> true},
       'body' -> [{'type' -> 'minecraft:plain_message', 'contents' -> {'text' -> str('You have %d tickets. Every game here pays tickets!', _tk(p ~ 'name')), 'color' -> 'white'}, 'width' -> 300}],
       'can_close_with_escape' -> true, 'pause' -> false, 'after_action' -> 'none', 'columns' -> 2, 'actions' -> acts,
       'exit_action' -> {'label' -> 'Close', 'width' -> 120, 'action' -> {'type' -> 'run_command', 'command' -> '/arcade close'}}};
  run(str('dialog show %s %s', p ~ 'name', encode_json(d)))
);
_cmd_prize(id) -> (
  p = player(); if (!p, return(0)); n = p ~ 'name'; z = global_prizes:id; if (!z, return(0));
  run('dialog clear ' + n);
  if (_tk(n) < z:1, return(_bar(p, str('You need %d more tickets', z:1 - _tk(n)), 'red')));
  global_tickets:n = _tk(n) - z:1; _save_tk();
  run(str('give %s %s %d', n, z:2, z:3));
  _bar(p, str('✦ %s is yours! %d tickets left', z:0, global_tickets:n), '#FF3EA5');
  run(str('playsound minecraft:entity.player.levelup master %s ~ ~ ~ 0.7 1.3', n));
  1
);
_cmd_tickets() -> (p = player(); if (p, print(p, str('🎟 You have %d tickets', _tk(p ~ 'name')))); 1);
_cmd_close() -> (p = player(); if (p, run('dialog clear ' + p ~ 'name')); 1);
_cmd_give(name, k) -> (p = player(); if (p && !_admin(p), return(0)); global_tickets:name = _tk(name) + k; _save_tk(); 1);

// ═════════════ BOWLING ═════════════
_lane_new(L) -> {'L' -> L, 'players' -> [], 'state' -> 'open', 'turn' -> 0, 'frame' -> 1, 'throw' -> 1, 'rolls' -> {},
                 'pins' -> [], 'ball' -> null, 'meter' -> null, 'phase' -> 'idle', 't' -> 0, 'before' -> 10, 'msg' -> ''};
_pin_home(st, i) -> [st:'L':'center' + global_pin_off:i:0, st:'L':'pin_near_z' - 0.3 + global_pin_off:i:1];
_pins_init(st) -> (
  st:'pins' = map(range(10), (h = _pin_home(st, _); {'x' -> h:0, 'z' -> h:1, 'vx' -> 0, 'vz' -> 0, 'up' -> true, 'gone' -> false, 'q' -> null}))
);
_pin_tag(st, i) -> str('arc_pin_%d_%d', st:'L':'id', i);
_pin_render(st, i) -> (
  pn = st:'pins':i;
  e = _one(_pin_tag(st, i), 'item_display', [pn:'x', global_pin_y, pn:'z'],
    str('teleport_duration:1,brightness:{sky:15,block:14},%s,%s', _item('arcade:pin'), _tf(0.75)));
  if (!e, return());
  if (pn:'gone', _mv(e, pn:'x', 18.2, pn:'z'),
      pn:'up', _mv(e, pn:'x', global_pin_y, pn:'z'),
      _mv(e, pn:'x', 19.12, pn:'z'))
);
_pin_upright(st, i) -> (e = _ent(_pin_tag(st, i)); if (e, modify(e, 'nbt_merge', _tfq([0, 0, 0, 1], 0.75))));
_pin_fall(st, i, dx, dz) -> (
  pn = st:'pins':i; pn:'up' = false;
  l = sqrt(dx * dx + dz * dz); if (l < 0.0001, (dx = 0; dz = -1; l = 1));
  k = [dz / l, 0, -dx / l];                                  // rotation axis ⟂ to the fall direction
  e = _ent(_pin_tag(st, i)); if (e, modify(e, 'nbt_merge', _tfq([k:0 * 0.7071, 0, k:2 * 0.7071, 0.7071], 0.75)))
);
_pins_reset(st) -> (
  for (range(10), (h = _pin_home(st, _); pn = st:'pins':_;
    pn:'x' = h:0; pn:'z' = h:1; pn:'vx' = 0; pn:'vz' = 0; pn:'up' = true; pn:'gone' = false;
    _pin_upright(st, _); _pin_render(st, _)));
  _snd([st:'L':'center', 20, st:'L':'pin_near_z' - 1], 'minecraft:block.piston.extend', 0.5, 1.4)
);
_sweep(st) -> for (range(10), if (!st:'pins':_:'up', (st:'pins':_:'gone' = true; _pin_render(st, _))));
_standing(st) -> length(filter(st:'pins', _:'up' && !_:'gone'));

_mark(v) -> if (v == 10, 'X', v == 0, '-', str(v));
_score(rolls, N) -> (
  tot = 0; i = 0; marks = []; done = true; n = length(rolls);
  for (range(N), (
    f = _;
    if (i >= n, (marks += '·'; done = false),
      f < N - 1, (
        r1 = rolls:i;
        if (r1 == 10, (
          marks += 'X';
          if (i + 2 < n, tot += 10 + rolls:(i + 1) + rolls:(i + 2), done = false);
          i += 1
        ), i + 1 >= n, (
          marks += _mark(r1); done = false; i += 1
        ), (
          r2 = rolls:(i + 1);
          if (r1 + r2 == 10, (
            marks += _mark(r1) + '/';
            if (i + 2 < n, tot += 10 + rolls:(i + 2), done = false)
          ), (
            marks += _mark(r1) + _mark(r2); tot += r1 + r2
          ));
          i += 2
        ))
      ), (
        rest = slice(rolls, i); m = '';
        for (rest, m += if (_i == 1 && rest:0 != 10 && rest:0 + _ == 10, '/', _i == 2 && rest:1 != 10 && rest:0 == 10 && rest:1 + _ == 10, '/', _mark(_)));
        marks += m;
        s = reduce(rest, _a + _, 0);
        if (length(rest) == 3 || (length(rest) == 2 && s < 10), tot += s, done = false)
      ))
  ));
  [tot, marks, done]
);
_last_frame(rolls, N) -> (
  i = 0; for (range(N - 1), if (i < length(rolls), if (rolls:i == 10, i += 1, i += 2)));
  if (i >= length(rolls), [], slice(rolls, i))
);

_screen(st) -> (
  L = st:'L';
  e = _one(str('arc_screen_%d', L:'id'), 'text_display', L:'screen',
    str('Rotation:[0f,0f],billboard:"fixed",alignment:"center",line_width:300,shadow:1b,background:-1442840576,brightness:{sky:15,block:15},%s,text:""', _tf(0.55)));
  if (!e, return());
  lines = [];
  if (st:'state' == 'open', (
    lines += {'text' -> str('🎳 Lane %d\n', L:'id'), 'color' -> '#FF3EA5', 'bold' -> true};
    lines += {'text' -> if (st:'players', 'Players: ' + join(', ', st:'players') + '\nPress the start button', 'Press the join button'), 'color' -> 'white', 'bold' -> false}
  ), (
    cur = st:'players':(st:'turn');
    lines += {'text' -> str('🎳 Lane %d · frame %d/%d · turn: %s\n', L:'id', min(st:'frame', global_frames), global_frames, cur), 'color' -> '#FF3EA5', 'bold' -> true};
    for (st:'players', (
      sc = _score(st:'rolls':_ || [], global_frames);
      lines += {'text' -> str('%s  %s  = %d\n', _, join(' | ', sc:1), sc:0), 'color' -> if (_ == cur, '#FFE14D', 'white'), 'bold' -> false}
    ))
  ));
  if (st:'msg', lines += {'text' -> st:'msg', 'color' -> '#7CFC5A', 'bold' -> true});
  modify(e, 'nbt_merge', str('{text:%s}', encode_json(lines)))
);
_announce(st, msg) -> (st:'msg' = msg; _screen(st));

_on_approach(st, p) -> (
  q = pos(p); L = st:'L';
  // the approach INCLUDES the red foul line (people stand on it — the owner) and a little of each gutter
  q:0 >= L:'x1' - 0.45 && q:0 < L:'x2' + 1.45 && q:2 >= L:'foul_z' && q:2 < L:'approach':1 + 1 && abs(q:1 - 19) < 1.5
);
_lane_join(st, p) -> (
  n = p ~ 'name';
  if (st:'state' != 'open', return(_bar(p, 'A game already started on this lane', 'yellow')));
  other = first(values(global_lanes), _ != st && first(_:'players', _ == n) != null);
  if (other, return(_bar(p, str('You are already on lane %d', other:'L':'id'), 'yellow')));
  if (first(st:'players', _ == n) != null, (st:'players' = filter(st:'players', _ != n); _bar(p, 'You left the lane', 'gray')),
      length(st:'players') >= 4, _bar(p, 'The lane is full (4 players)', 'yellow'),
      (st:'players' += n; _bar(p, str('You joined lane %d ✦ now press the start button', st:'L':'id'), '#FF3EA5')));
  _screen(st)
);
_lane_start(st, p) -> (
  if (st:'state' != 'open', return(_bar(p, 'The game is already running', 'yellow')));
  if (!st:'players', st:'players' = [p ~ 'name']);
  st:'state' = 'playing'; st:'turn' = 0; st:'frame' = 1; st:'throw' = 1; st:'rolls' = {}; st:'msg' = ''; st:'phase' = 'idle'; st:'last' = tick_time();
  for (st:'players', (p2 = player(_); if (p2, _ball_give(p2, global_colors:(_i % 4)))));
  _pins_reset(st);
  _turn_msg(st)
);
_turn_msg(st) -> (
  n = st:'players':(st:'turn'); p = player(n);
  _screen(st);
  if (p, (
    _ball_to_hand(p);
    _bar(p, str('🎳 Your turn! Frame %d · stand on the lane, hold right-click and release to throw', st:'frame'), '#FFE14D');
    run(str('playsound minecraft:block.note_block.bell master %s ~ ~ ~ 0.8 1.5', n))
  ))
);
// the ball is a "consumable" that never finishes: hold right-click = wind up (bow pose, no sound), release = throw
_ball_spec(c) -> str('paper[item_model="arcade:ball",dyed_color=%d,custom_data={arcade_ball:1b},max_stack_size=1,consumable={consume_seconds:100000,animation:"bow",sound:"minecraft:intentionally_empty",has_consume_particles:false},custom_name={text:"Bowling ball",color:"#FF3EA5",italic:false},lore=[{text:"Hold right-click = power · release = throw",color:"gray",italic:false}]]', c);
_is_ball(it) -> it != null && (str(it:2) ~ 'arcade_ball') != null;
_ball_give(p, c) -> (
  n = p ~ 'name';
  run(str('clear %s paper[custom_data={arcade_ball:1b}]', n));
  sel = query(p, 'selected_slot');
  slot = if (inventory_get(p, sel) == null, sel, first(range(9), inventory_get(p, _) == null));
  if (slot == null, (                                         // full hotbar: move the held item into the backpack
    free = first(range(9, 36), inventory_get(p, _) == null);
    if (free != null, (run(str('item replace entity %s inventory.%d from entity %s hotbar.%d', n, free - 9, n, sel)); slot = sel))
  ));
  if (slot == null, return(run(str('give %s %s 1', n, _ball_spec(c)))));
  run(str('item replace entity %s hotbar.%d with %s', n, slot, _ball_spec(c)));
  modify(p, 'selected_slot', slot)
);
_ball_color(n) -> (
  st = first(values(global_lanes), first(_:'players', _ == n) != null);
  if (!st, global_colors:0, global_colors:(first(range(length(st:'players')), st:'players':_ == n) % 4))
);
_ball_to_hand(p) -> (
  n = p ~ 'name'; s = first(range(36), _is_ball(inventory_get(p, _)));
  if (s == null, return(_ball_give(p, _ball_color(n))));          // lost it somehow — a new one
  if (s < 9, return(modify(p, 'selected_slot', s)));
  sel = query(p, 'selected_slot');                                // in the backpack: swap with the held item
  run(str('item replace entity %s inventory.%d from entity %s hotbar.%d', n, s - 9, n, sel));
  run(str('item replace entity %s hotbar.%d with %s', n, sel, _ball_spec(_ball_color(n))))
);
_power(dt) -> (ph = (dt % 36) / 18; if (ph > 1, 2 - ph, ph));

__on_player_uses_item(p, item, hand) -> (
  if (hand != 'mainhand' || !item || (str(item:2) ~ 'arcade_ball') == null, return());
  n = p ~ 'name'; now = tick_time();
  if (now - (global_use_cd:n || -99) < 4, return());
  global_use_cd:n = now;
  st = null;
  for (values(global_lanes), if (_:'state' == 'playing' && first(_:'players', _ == n) != null, st = _));
  if (!st, return(_bar(p, 'Join a lane with its join button', 'yellow')));
  if (st:'players':(st:'turn') != n, return(_bar(p, 'Now it is the turn of ' + st:'players':(st:'turn'), 'yellow')));
  if (st:'ball' || st:'phase' != 'idle', return(_bar(p, 'One moment… setting the pins', 'gray')));
  if (!_on_approach(st, p), return(_bar(p, 'Stand in the approach of your lane (up to the red line)', 'yellow')));
  st:'meter' = {'t0' -> now}                                   // winding up while the button is held
);
__on_player_releases_item(p, item, hand) -> (
  if (!_is_ball(item), return());
  n = p ~ 'name'; st = first(values(global_lanes), _:'state' == 'playing' && _:'meter' && _:'players':(_:'turn') == n);
  if (!st, return());
  dt = tick_time() - st:'meter':'t0';
  if (dt < 6, (st:'meter' = null; return(_bar(p, 'Hold right-click to charge, release at the right moment', 'yellow'))));
  if (!_on_approach(st, p), (st:'meter' = null; return(_bar(p, 'Stand in the approach of your lane (up to the red line)', 'yellow'))));
  _throw(st, p, _power(dt))
);
_throw(st, p, power) -> (
  L = st:'L'; st:'meter' = null;
  yaw = p ~ 'yaw'; d = ((yaw - 180 + 540) % 360) - 180; d = max(-7, min(7, d)); ye = 180 + d;
  sp = 0.28 + 0.42 * power;
  x = max(L:'x1' + 0.3, min(L:'x2' + 0.7, pos(p):0)); z = min(L:'foul_z' + 0.7, pos(p):2 - 0.6);   // just in front of the bowler
  st:'ball' = {'x' -> x, 'z' -> z, 'vx' -> -sin(ye) * sp, 'vz' -> cos(ye) * sp, 'gutter' -> false, 't' -> 0};
  c = global_colors:(st:'turn' % 4);                           // the same colour the player's ball item has
  e = spawn('item_display', [x, global_ball_y, z], str('{Tags:["arcade","arc_ball"],teleport_duration:1,brightness:{sky:15,block:14},item:{id:"minecraft:paper",count:1,components:{"minecraft:item_model":"arcade:ball","minecraft:dyed_color":%d}},%s}', c, _tf(0.7)));
  st:'ball':'e' = query(e, 'uuid');
  st:'before' = _standing(st); st:'phase' = 'roll'; st:'t' = 0; st:'msg' = ''; st:'last' = tick_time();
  _bar(p, str('🎳 Throw! Power %d%%', round(power * 100)), '#FF3EA5');
  _snd([x, 19.5, z], 'minecraft:entity.player.attack.sweep', 0.7, 0.6)
);
_meter_show(st) -> (
  m = st:'meter'; if (!m, return());
  p = player(st:'players':(st:'turn')); if (!p, return());
  pw = _power(tick_time() - m:'t0'); k = round(pw * 20);
  bar = ''; for (range(20), bar += if (_ < k, '▮', '▯'));
  _bar(p, str('Power %s  · release to throw', bar), if (pw > 0.75, '#FF5555', pw > 0.4, '#FFD23E', '#7CFC5A'));
  yaw = p ~ 'yaw'; d = ((yaw - 180 + 540) % 360) - 180; d = max(-7, min(7, d)); ye = 180 + d;   // aim line on the lane
  x0 = max(st:'L':'x1' + 0.3, min(st:'L':'x2' + 0.7, pos(p):0)); z0 = st:'L':'foul_z' + 0.5;
  for (range(1, 8), particle('dust{color:[1.0,0.24,0.65],scale:0.6}', [x0 - sin(ye) * _ * 1.6, 19.1, z0 + cos(ye) * _ * 1.6], 1, 0, 0))
);

_lane_tick(st) -> (
  L = st:'L'; b = st:'ball'; lx1 = L:'x1'; lx2 = L:'x2' + 1; pins = st:'pins';
  if (b, (
    b:'x' = b:'x' + b:'vx'; b:'z' = b:'z' + b:'vz'; b:'vx' = b:'vx' * 0.998; b:'vz' = b:'vz' * 0.998; b:'t' = b:'t' + 1;
    if (!b:'gutter' && (b:'x' < lx1 + 0.14 || b:'x' > lx2 - 0.14), (
      b:'gutter' = true; b:'x' = if (b:'x' < L:'center', lx1 - 0.5, lx2 + 0.5); b:'vx' = 0;
      _snd([b:'x', 19.2, b:'z'], 'minecraft:block.wood.hit', 0.6, 0.6)
    ));
    if (!b:'gutter', for (range(10), (
      pn = pins:_; i = _;
      if (pn:'up' && !pn:'gone', (
        dx = pn:'x' - b:'x'; dz = pn:'z' - b:'z'; d2 = dx * dx + dz * dz;
        if (d2 < 0.09, (
          d = max(sqrt(d2), 0.01); nx = dx / d; nz = dz / d; sp = sqrt(b:'vx' ^ 2 + b:'vz' ^ 2);
          pn:'vx' = nx * sp * 0.85 + b:'vx' * 0.3 + (rand(0.1) - 0.05); pn:'vz' = nz * sp * 0.85 + b:'vz' * 0.3 + (rand(0.1) - 0.05);
          _pin_fall(st, i, pn:'vx', pn:'vz');
          dot = b:'vx' * nx + b:'vz' * nz; b:'vx' = b:'vx' - nx * dot * 0.3; b:'vz' = b:'vz' - nz * dot * 0.3;
          _snd([pn:'x', 19.5, pn:'z'], 'minecraft:entity.zombie.attack_wooden_door', 0.35, 1.7 + rand(0.3))
        ))
      ))
    )));
    e = entity_id(b:'e'); if (e, modify(e, 'pos', b:'x', global_ball_y, b:'z'));
    if (b:'z' < L:'pit_z' + 1 || b:'t' > 260 || sqrt(b:'vx' ^ 2 + b:'vz' ^ 2) < 0.015, (
      if (e, modify(e, 'remove')); st:'ball' = null; st:'phase' = 'settle'; st:'t' = 0
    ))
  ));
  moving = false;
  for (range(10), (
    pn = pins:_; i = _;
    if (!pn:'gone' && (abs(pn:'vx') > 0.004 || abs(pn:'vz') > 0.004), (
      moving = true;
      pn:'x' = pn:'x' + pn:'vx'; pn:'z' = pn:'z' + pn:'vz'; pn:'vx' = pn:'vx' * 0.9; pn:'vz' = pn:'vz' * 0.9;
      if (pn:'x' < lx1 - 0.9 || pn:'x' > lx2 + 0.9, (pn:'vx' = -pn:'vx' * 0.4; pn:'x' = max(lx1 - 0.9, min(lx2 + 0.9, pn:'x'))));
      if (pn:'z' < L:'pit_z' + 1.4, (pn:'gone' = true; pn:'up' = false; pn:'vx' = 0; pn:'vz' = 0));
      sp = sqrt(pn:'vx' ^ 2 + pn:'vz' ^ 2);
      for (range(10), (
        q = pins:_; j = _;
        if (j != i && q:'up' && !q:'gone', (
          dx = q:'x' - pn:'x'; dz = q:'z' - pn:'z'; d2 = dx * dx + dz * dz;
          if (d2 < 0.07 || (d2 < 0.2 && rand(1) < 0.06), (
            d = max(sqrt(d2), 0.01);
            q:'vx' = dx / d * sp * 0.75 + pn:'vx' * 0.25 + (rand(0.06) - 0.03); q:'vz' = dz / d * sp * 0.75 + pn:'vz' * 0.25 + (rand(0.06) - 0.03);
            _pin_fall(st, j, q:'vx', q:'vz');
            pn:'vx' = pn:'vx' * 0.55; pn:'vz' = pn:'vz' * 0.55;
            _snd([q:'x', 19.5, q:'z'], 'minecraft:entity.zombie.attack_wooden_door', 0.3, 1.8 + rand(0.2))
          ))
        ))
      ));
      _pin_render(st, i)
    ))
  ));
  if (st:'phase' == 'settle', (
    st:'t' = st:'t' + 1;
    if ((!moving && st:'t' > 12) || st:'t' > 60, _after_throw(st))
  ))
);

_after_throw(st) -> (
  st:'phase' = 'wait';                                        // blocks throws until _second/_last_next/_next_turn
  n = st:'players':(st:'turn'); fallen = max(0, st:'before' - _standing(st));
  r = st:'rolls':n || []; r += fallen; st:'rolls':n = r;
  N = global_frames; standing = _standing(st); t = st:'throw';
  if (st:'frame' < N, (
    if (t == 1 && standing == 0, (_announce(st, 'Strike! ✦'); _fx(st, 'strike'); schedule(40, '_next_turn', st:'L':'id')),
        t == 1, (_announce(st, str('%d pins', fallen)); schedule(30, '_second', st:'L':'id')),
        (_announce(st, if (standing == 0, 'Spare! ✦', str('%d pins', fallen))); if (standing == 0, _fx(st, 'spare')); schedule(40, '_next_turn', st:'L':'id')))
  ), (
    fr = _last_frame(r, N); k = length(fr);
    if (k == 1, (_announce(st, if (fallen == 10, 'Strike! ✦', str('%d pins', fallen))); schedule(30, '_last_next', st:'L':'id')),
        k == 2 && (fr:0 == 10 || fr:0 + fr:1 == 10), (_announce(st, 'One more throw!'); schedule(30, '_last_next', st:'L':'id')),
        (_announce(st, str('%d pins', fallen)); schedule(40, '_next_turn', st:'L':'id')))
  ));
  _screen(st)
);
_fx(st, kind) -> (
  c = [st:'L':'center', 20.5, st:'L':'pin_near_z' - 1];
  _snd(c, if (kind == 'strike', 'minecraft:ui.toast.challenge_complete', 'minecraft:entity.player.levelup'), 0.8, 1.2);
  particle('firework', c, 40, 0.8, 0.5)
);
_second(lid) -> (st = global_lanes:lid; if (st:'state' != 'playing', return()); _sweep(st); st:'throw' = 2; _ready(st); _turn_msg(st));
_ready(st) -> (st:'phase' = 'idle'; st:'last' = tick_time());
_last_next(lid) -> (st = global_lanes:lid; if (st:'state' != 'playing', return()); if (_standing(st) == 0, _pins_reset(st), _sweep(st)); st:'throw' = st:'throw' + 1; _ready(st); _turn_msg(st));
_next_turn(lid) -> (
  st = global_lanes:lid; if (st:'state' != 'playing', return()); st:'throw' = 1; st:'msg' = '';
  st:'turn' = st:'turn' + 1;
  if (st:'turn' >= length(st:'players'), (st:'turn' = 0; st:'frame' = st:'frame' + 1));
  if (st:'frame' > global_frames, return(_game_over(st)));
  _pins_reset(st);
  n = st:'players':(st:'turn');
  if (!player(n), (   // offline: an empty frame, move on
    r = st:'rolls':n || []; r += 0; r += 0; st:'rolls':n = r; return(schedule(5, '_next_turn', lid))
  ));
  _ready(st);
  _turn_msg(st)
);
_cancel(st, why) -> (
  for (st:'players', run(str('clear %s paper[custom_data={arcade_ball:1b}]', _)));
  if (st:'ball', (e = entity_id(st:'ball':'e'); if (e, modify(e, 'remove'))));
  st:'state' = 'open'; st:'players' = []; st:'phase' = 'idle'; st:'ball' = null; st:'meter' = null; st:'msg' = why;
  _pins_reset(st); _screen(st)
);
_lanes_watch() -> for (values(global_lanes), if (_:'state' == 'playing' && _:'phase' == 'idle' && !_:'ball', (
  st = _;
  if (first(st:'players', player(_)) == null, _cancel(st, 'Game cancelled: every player left'),
      tick_time() - (st:'last' || 0) > 1200, _cancel(st, 'Game cancelled: a minute without a throw'))
)));
_game_over(st) -> (
  best = null; bs = -1; res = [];
  for (st:'players', (
    sc = _score(st:'rolls':_ || [], global_frames):0; res += str('%s %d', _, sc);
    if (sc > bs, (bs = sc; best = _));
    p = player(_);
    strikes = length(filter(st:'rolls':_ || [], _ == 10));
    if (p, (_pay(p, max(1, floor(sc / 8)) + 2 * strikes); run(str('clear %s paper[custom_data={arcade_ball:1b}]', _))));
    _record('bowling', _, sc)
  ));
  if (length(st:'players') > 1, run('tellraw @a ' + encode_json({'text' -> str('🎳 %s won on lane %d with %d points!', best, st:'L':'id', bs), 'color' -> '#FF3EA5'})));
  st:'msg' = 'Final! ' + join(' · ', res);
  st:'state' = 'open'; st:'players' = []; st:'phase' = 'idle';
  _screen(st);
  _fx(st, 'strike')
);

// ═════════════ CLAW MACHINE ═════════════
_claw_tick() -> (
  c = global_claw; C = global_L:'claw'; B = C:'box';
  e = _one('arc_claw', 'item_display', [B:'x2' - 0.5, C:'top_y', B:'z2' - 0.5], str('teleport_duration:2,brightness:{sky:15,block:15},%s,%s', _item('arcade:claw_open'), _tf(0.55)));
  if (!c:'on', return());
  c:'t' = c:'t' + 1; ph = c:'phase'; p = player(c:'player');
  if (ph == 'move', (
    if (c:'t' % 10 == 0 && p, _bar(p, str('🕹 Claw machine · %d s · ← ↑ ● ↓ →', max(0, 20 - floor(c:'t' / 20))), '#FF3EA5'));
    if (c:'t' > 400, (c:'phase' = 'down'; c:'t' = 0))
  ), ph == 'down', (
    c:'y' = C:'top_y' - (C:'top_y' - 20.35) * min(1, c:'t' / 16);
    if (c:'t' >= 16, (c:'phase' = 'close'; c:'t' = 0; if (e, modify(e, 'nbt_merge', '{' + _item('arcade:claw_closed') + '}'));
      best = -1; bd = 0.35;
      for (range(length(global_claw_prizes)), (pe = _ent('arc_prize_' + _); if (pe && !c:'lost':_, (q = pos(pe); d = sqrt((q:0 - c:'x') ^ 2 + (q:2 - c:'z') ^ 2); if (d < bd, (bd = d; best = _))))));
      c:'held' = if (best >= 0 && rand(1) < if (bd < 0.18, 0.8, 0.55), best, -1);
      _snd([c:'x', 21, c:'z'], 'minecraft:block.chain.place', 0.8, 1)))
  ), ph == 'close', (
    if (c:'t' >= 6, (c:'phase' = 'up'; c:'t' = 0))
  ), ph == 'up', (
    c:'y' = 20.35 + (C:'top_y' - 20.35) * min(1, c:'t' / 16);
    if (c:'t' >= 16, (c:'phase' = 'carry'; c:'t' = 0; c:'sx' = c:'x'; c:'sz' = c:'z'))
  ), ph == 'carry', (
    f = min(1, c:'t' / 20); c:'x' = c:'sx' + (C:'chute':0 - c:'sx') * f; c:'z' = c:'sz' + (C:'chute':2 - c:'sz') * f;
    if (c:'t' == 10 && c:'held' >= 0 && rand(1) < 0.12, (
      pe = _ent('arc_prize_' + c:'held'); if (pe, _mv(pe, c:'x', C:'floor_y', c:'z'));
      c:'held' = -1; if (p, _bar(p, 'Oh no! It slipped…', '#FFD23E'))));
    if (c:'t' >= 20, (c:'phase' = 'drop'; c:'t' = 0))
  ), ph == 'drop', (
    if (e, modify(e, 'nbt_merge', '{' + _item('arcade:claw_open') + '}'));
    if (c:'held' >= 0, (
      k = c:'held'; m = global_claw_prizes:k;
      z = first(values(global_prizes), (_:2 ~ m) != null);
      if (p && z, (run(str('give %s %s 1', c:'player', z:2)); _bar(p, '🎉 You got ' + z:0 + '!', '#FF3EA5');
        _snd(pos(p), 'minecraft:ui.toast.challenge_complete', 0.8, 1.3)));
      c:'lost':k = true; pe = _ent('arc_prize_' + k); if (pe, _mv(pe, c:'x', 17.6, c:'z'));
      schedule(200, '_claw_restock', k)
    ), p, _bar(p, 'So close! Try again ✦', '#FFD23E'));
    c:'on' = false; c:'held' = -1
  ));
  if (c:'on' || ph == 'drop', (
    if (e, modify(e, 'pos', c:'x', c:'y', c:'z'));
    if (c:'held' >= 0, (pe = _ent('arc_prize_' + c:'held'); if (pe, modify(pe, 'pos', c:'x', c:'y' - 0.45, c:'z'))))
  ))
);
_claw_restock(k) -> (
  global_claw:'lost':k = false; B = global_L:'claw':'box';
  pe = _ent('arc_prize_' + k);
  if (pe, _mv(pe, B:'x1' + 1.5 + (k % 3), global_L:'claw':'floor_y', B:'z1' + 1.5 + floor(k / 3)))
);
_claw_button(which, p) -> (
  c = global_claw; C = global_L:'claw'; B = C:'box'; n = p ~ 'name';
  if (!c:'on', (
    if (_tk(n) < 3, return(_bar(p, 'The claw costs 3 tickets. Play bowling, whack-a-mole or dance to earn them', 'yellow')));
    global_tickets:n = _tk(n) - 3; _save_tk();
    global_claw = {'on' -> true, 'player' -> n, 'phase' -> 'move', 't' -> 0, 'x' -> B:'x2' - 0.5, 'z' -> B:'z2' - 0.5,
                   'y' -> C:'top_y', 'held' -> -1, 'lost' -> c:'lost' || {}};
    return(_bar(p, '🕹 Paid 3 tickets · move with the arrows and press ● to grab', '#FF3EA5'))
  ));
  if (c:'player' != n || c:'phase' != 'move', return());
  step = 0.3;
  if (which == 'left', c:'x' = max(B:'x1' + 1.3, c:'x' - step),
      which == 'right', c:'x' = min(B:'x2' - 0.3, c:'x' + step),
      which == 'up', c:'z' = max(B:'z1' + 1.3, c:'z' - step),
      which == 'down', c:'z' = min(B:'z2' - 0.3, c:'z' + step),
      which == 'grab', (c:'phase' = 'down'; c:'t' = 0));
  _snd([c:'x', 22, c:'z'], 'minecraft:block.note_block.hat', 0.5, 1.6)
);

// ═════════════ WHACK-A-MOLE ═════════════
_whack_ents() -> (
  for (global_L:'whack':'holes', (
    h = _; i = _i;
    _one('arc_mole_' + i, 'item_display', [h:0, 18.6, h:2], str('teleport_duration:3,brightness:{sky:15,block:15},%s,%s', _item('arcade:mole'), _tf(0.55)));
    _one('arc_hole_' + i, 'interaction', [h:0, 18.95, h:2], 'width:0.9f,height:0.9f,response:1b')
  ))
);
_mole(i, up) -> (h = global_L:'whack':'holes':i; e = _ent('arc_mole_' + i); if (e, _mv(e, h:0, if (up, 19.3, 18.6), h:2)));
_whack_start(p) -> (
  if (global_whack:'on', return(_bar(p, 'Someone is playing: one moment', 'yellow')));
  global_whack = {'on' -> true, 'player' -> p ~ 'name', 't' -> 0, 'score' -> 0, 'up' -> map(range(9), 0), 'next' -> 20};
  _bar(p, '🔨 Whack the moles! Left-click them · 30 seconds', '#7CFC5A');
  _snd(global_L:'whack':'stand', 'minecraft:block.note_block.bell', 0.8, 1)
);
_whack_tick() -> (
  w = global_whack; if (!w:'on', return());
  w:'t' = w:'t' + 1; p = player(w:'player');
  for (range(9), if (w:'up':_ > 0, (w:'up':_ = w:'up':_ - 1; if (w:'up':_ == 0, _mole(_, false)))));
  w:'next' = w:'next' - 1;
  if (w:'next' <= 0, (
    free = filter(range(9), w:'up':_ == 0);
    if (free, (i = free:floor(rand(length(free))); w:'up':i = if (w:'t' > 400, 16, 24); _mole(i, true);
      h = global_L:'whack':'holes':i; _snd(h, 'minecraft:entity.rabbit.jump', 0.6, 1.2)));
    w:'next' = if (w:'t' > 400, 6 + floor(rand(6)), 9 + floor(rand(8)))
  ));
  if (p && w:'t' % 10 == 0, _bar(p, str('🔨 %d points · %d s', w:'score', max(0, 30 - floor(w:'t' / 20))), '#7CFC5A'));
  if (w:'t' >= 600, (
    for (range(9), _mole(_, false)); w:'on' = false;
    if (p, (_bar(p, str('🔨 Done! %d points', w:'score'), '#7CFC5A'); _pay(p, max(1, floor(w:'score' / 2)))));
    _record('whack', w:'player', w:'score')
  ))
);
_whack_hit(p, e) -> (
  w = global_whack; if (!w:'on' || (p ~ 'name') != w:'player', return());
  t = first(query(e, 'scoreboard_tags'), (_ ~ '^arc_hole_') != null); if (t == null, return());
  i = number(slice(t, 9));
  if (w:'up':i > 0, (
    w:'up':i = 0; _mole(i, false); w:'score' = w:'score' + 1;
    h = global_L:'whack':'holes':i;
    _snd(h, 'minecraft:entity.player.attack.crit', 0.8, 1.3); particle('crit', [h:0, 19.4, h:2], 8, 0.2, 0.1)
  ))
);
__on_player_attacks_entity(p, e) -> if (query(e, 'has_tag', 'arcade'), _whack_hit(p, e));

// ═════════════ DANCE (DDR-style, the owner) ═════════════
// A 3×3 pad in the floor: the centre never lights; the four arrows are magenta glazed terracotta. The screen in front
// shows arrows falling down four columns to the hit line (right) and a dancing plush golem (left). Step on the arrow's
// tile when it reaches the line (it lights up): within 2 ticks = PERFECT (2), within 4 = GOOD (1), later = MISS.
global_dirs = ['left', 'down', 'up', 'right'];
global_dir_glyph = {'left' -> '⬅', 'down' -> '⬇', 'up' -> '⬆', 'right' -> '➡'};
global_dir_color = {'left' -> '#C77DFF', 'down' -> '#3EC5FF', 'up' -> '#7CFC5A', 'right' -> '#FF3EA5'};
global_melody = [12, 14, 16, 19, 21, 19, 16, 14, 12, 16, 19, 24, 21, 19, 16, 14];
global_ddr_rows = 8;          // screen rows
global_ddr_beat = 11;         // ticks per beat (14 was comfortable, then "faster" → ~109 bpm)
global_ddr_fall = 4;          // ticks per screen row → an arrow is visible 32 ticks (1.6 s) before its beat

_ddr_tile(d, blk) -> (
  R = global_L:'rhythm'; q = R:'pad':d;
  if (blk == 'arrow', set(q, 'magenta_glazed_terracotta', 'facing', R:'facing':d), set(q, blk))
);
_ddr_restore(d) -> _ddr_tile(d, 'arrow');
_ddr_chart() -> (
  notes = []; prev = null;
  for (range(36), (
    b = _;
    if (b >= 12 || b % 2 == 0, (                               // first 12 beats: every other beat, then every beat
      d = global_dirs:floor(rand(4)); if (d == prev && rand(1) < 0.6, d = global_dirs:floor(rand(4))); prev = d;
      notes += {'t' -> 50 + b * global_ddr_beat, 'd' -> d, 'j' -> null}
    ))
  ));
  notes
);
_rhythm_start(p) -> (
  if (global_rhythm:'on', return(_bar(p, 'The dance floor is busy: one moment', 'yellow')));
  global_rhythm = {'on' -> true, 'player' -> p ~ 'name', 't' -> 0, 'notes' -> _ddr_chart(), 'score' -> 0,
                   'combo' -> 0, 'best' -> 0, 'fb' -> 'Ready…', 'fbc' -> 'white'};
  global_rhythm:'last' = reduce(global_rhythm:'notes', max(_a, _:'t'), 0);
  c0 = global_L:'rhythm':'pad':'center';
  for (entity_selector('@e[tag=arc_ddr_seat]'), modify(_, 'remove'));
  seat = spawn('item_display', [c0:0 + 0.5, 19.6, c0:2 + 0.5], '{Tags:["arcade","arc_ddr_seat"],teleport_duration:1,Rotation:[180f,0f]}');
  global_rhythm:'seat' = query(seat, 'uuid'); global_rhythm:'dir' = null; global_rhythm:'shift' = 0;
  run(str('ride %s mount %s', p ~ 'name', global_rhythm:'seat'));
  _bar(p, '💃 W ↑ · S ↓ · A ← · D → on the beat, when the arrow reaches the line · hold Shift = quit', '#FF3EA5')
);
global_ddr_fake = {};
_ddr_keys(n) -> (f = global_ddr_fake:n; if (f != null, f, (k = scoreboard('keys', n); if (k == null, 0, k))));
_dancer(b) -> (
  e = _ent('arc_ddr_dancer'); if (!e, return());
  a = if (b % 2, 12, -12); h = if (b % 2, 0.16, 0.0);
  modify(e, 'nbt_merge', str('{transformation:{left_rotation:[0f,0f,%.4ff,%.4ff],right_rotation:[0f,0f,0f,1f],translation:[0f,%.2ff,0f],scale:[1.3f,1.3f,1.3f]},start_interpolation:0,interpolation_duration:4}', sin(a / 2), cos(a / 2), h));
  particle('note', pos(e) + [0, 1.1, 0], 1, 0.2, 1)
);
_rhythm_tick() -> (
  r = global_rhythm; if (!r:'on', return());
  r:'t' = r:'t' + 1; t = r:'t'; p = player(r:'player'); R = global_L:'rhythm'; c = R:'centre';
  if (t >= 50 && (t - 50) % global_ddr_beat == 0, (
    b = (t - 50) / global_ddr_beat; note = global_melody:(b % 16);
    _snd(c, 'minecraft:block.note_block.harp', 0.9, 2 ^ ((note - 12) / 12));
    if (b % 2 == 0, _snd(c, 'minecraft:block.note_block.bass', 1, 2 ^ ((note - 24) / 12)));
    _snd(c, 'minecraft:block.note_block.hat', 0.35, 1.3);
    _dancer(b)
  ));
  // you are LOCKED on the pad (an invisible seat). W/S/A/D (Key Bridge → scoreboard keys: 1/2/4/8) snap the
  // seat onto that arrow while held and back to the centre on release — you press in rhythm instead of walking.
  k = if (p, _ddr_keys(r:'player'), 0);
  dirs = filter([['up', 1], ['down', 2], ['left', 4], ['right', 8]], bitwise_and(k, _:1) != 0);
  on = if (length(dirs) == 1, dirs:0:0, null);
  seat = entity_id(r:'seat');
  if (seat && on != r:'dir', (
    q = if (on, R:'pad':on, R:'pad':'center');
    _mv(seat, q:0 + 0.5, 19.6, q:2 + 0.5);
    r:'dir' = on
  ));
  if (p && seat && !query(p, 'mount'), run(str('ride %s mount %s', r:'player', r:'seat')));   // a Shift tap can't knock you off
  r:'shift' = if (bitwise_and(k, 32) != 0, (r:'shift' || 0) + 1, 0);
  if (r:'shift' >= 30 || !p, r:'last' = min(r:'last', t - 21));                                // hold Shift 1.5 s (or leave) = stop
  for (r:'notes', (
    n = _;
    if (!n:'j', (
      dt = t - n:'t';
      if (dt == -2, _ddr_tile(n:'d', 'pearlescent_froglight'));
      if (dt >= -5 && dt <= 5 && on == n:'d', (
        n:'j' = if (abs(dt) <= 2, 'perfect', 'good');
        r:'score' = r:'score' + if (n:'j' == 'perfect', 2, 1); r:'combo' = r:'combo' + 1; r:'best' = max(r:'best', r:'combo');
        r:'fb' = if (n:'j' == 'perfect', 'PERFECT ✦', 'GOOD'); r:'fbc' = if (n:'j' == 'perfect', '#FFE14D', '#7CFC5A');
        _ddr_tile(n:'d', 'verdant_froglight'); schedule(4, '_ddr_restore', n:'d');
        _snd(R:'pad':(n:'d') + [0.5, 1, 0.5], 'minecraft:block.note_block.pling', 0.7, if (n:'j' == 'perfect', 1.8, 1.4))
      ), dt > 5, (
        n:'j' = 'miss'; r:'combo' = 0; r:'fb' = 'MISS'; r:'fbc' = '#FF5555';
        _ddr_tile(n:'d', 'red_concrete'); schedule(4, '_ddr_restore', n:'d')
      ))
    ))
  ));
  if (t % 2 == 0, _ddr_screen());
  if (t > r:'last' + 20, (
    r:'on' = false; for (global_dirs, _ddr_tile(_, 'arrow'));
    seat = entity_id(r:'seat');
    if (p, (run('ride ' + r:'player' + ' dismount'); c0 = R:'pad':'center'; modify(p, 'pos', c0:0 + 0.5, 19, c0:2 + 1.6)));
    if (seat, modify(seat, 'remove'));
    r:'fb' = str('Done! %d points · combo %d', r:'score', r:'best'); r:'fbc' = '#FF3EA5'; _ddr_screen();
    e = _ent('arc_ddr_dancer'); if (e, modify(e, 'nbt_merge', _tfq([0, 0, 0, 1], 1.3)));
    if (p, (_bar(p, str('💃 Done! %d points · longest combo %d', r:'score', r:'best'), '#FF3EA5'); _pay(p, max(1, floor(r:'score' / 4)))));
    _record('rhythm', r:'player', r:'score')
  ))
);
_ddr_screen() -> (
  e = _ent('arc_ddr_screen'); if (!e, return());
  r = global_rhythm; rows = global_ddr_rows;
  lines = [{'text' -> '♪ DANCE ♪\n', 'color' -> '#FF3EA5', 'bold' -> true}];
  if (!r:'on' && !r:'notes', (
    lines += {'text' -> 'Press start\nW ↑ · S ↓ · A ← · D →', 'color' -> 'white', 'bold' -> false};
    return(modify(e, 'nbt_merge', str('{text:%s}', encode_json(lines))))
  ));
  grid = {};
  if (r:'on', for (r:'notes', (
    n = _;
    if (!n:'j', (dt = n:'t' - r:'t'; if (dt >= 0 && dt < rows * global_ddr_fall, grid:str('%d_%s', rows - 1 - floor(dt / global_ddr_fall), n:'d') = true)))
  )));
  for (range(rows), (
    row = _;
    for (global_dirs, (
      d = _; hit = row == rows - 1;
      if (grid:str('%d_%s', row, d),
        lines += {'text' -> global_dir_glyph:d + ' ', 'color' -> global_dir_color:d, 'bold' -> true},
        lines += {'text' -> if (hit, '◇ ', '· '), 'color' -> if (hit, '#AAAAAA', '#444444'), 'bold' -> false})
    ));
    lines += {'text' -> '\n', 'color' -> 'white'}
  ));
  lines += {'text' -> str('%s  x%d\n', r:'fb', r:'combo'), 'color' -> r:'fbc', 'bold' -> true};
  lines += {'text' -> str('%d pts', r:'score'), 'color' -> 'white', 'bold' -> false};
  modify(e, 'nbt_merge', str('{text:%s}', encode_json(lines)))
);

// ═════════════ entities, buttons, clicks, lifecycle ═════════════
_ensure() -> (
  if (!_floor_busy(), return());
  for (values(global_lanes), (st = _; for (range(10), _pin_render(st, _)); _screen(st)));
  c = global_L:'counter';
  _one('arc_clerk', 'mannequin', c:'npc', str('Rotation:[%.1ff,0f],pose:"standing",immovable:1b,hide_description:1b,Invulnerable:1b,Silent:1b,profile:{model:"wide",texture:"studio:entity/skin/rainbow_skater"},CustomName:%s,CustomNameVisible:0b', c:'yaw', encode_json({'text' -> 'Prize counter'})));
  s = global_L:'scoreboard';
  if (!_ent('arc_board'), (_one('arc_board', 'text_display', s:'pos', str('Rotation:[%.1ff,0f],billboard:"fixed",alignment:"center",line_width:260,shadow:1b,background:-1442840576,brightness:{sky:15,block:15},%s,text:""', s:'yaw', _tf(0.55))); _board()));
  B = global_L:'claw':'box';
  for (range(length(global_claw_prizes)), (
    k = _;
    if (!(global_claw:'lost' || {}):k, _one('arc_prize_' + k, 'item_display', [B:'x1' + 1.5 + (k % 3), global_L:'claw':'floor_y', B:'z1' + 1.5 + floor(k / 3)],
      str('Rotation:[%df,0f],brightness:{sky:15,block:15},%s,%s', floor(rand(360)), _item('arcade:' + global_claw_prizes:k), _tf(0.45))))
  ));
  _whack_ents();
  R = global_L:'rhythm';
  if (R:'screen', (
    if (!_ent('arc_ddr_screen'), (_one('arc_ddr_screen', 'text_display', R:'screen', str('Rotation:[0f,0f],billboard:"fixed",alignment:"center",line_width:160,shadow:1b,background:-1442840576,brightness:{sky:15,block:15},%s,text:""', _tf(0.75))); _ddr_screen()));
    _one('arc_ddr_dancer', 'item_display', R:'dancer', str('teleport_duration:2,brightness:{sky:15,block:15},%s,%s', _item('arcade:plush_golem'), _tf(1.3)))
  ))
);
_buttons() -> (
  for (values(global_lanes), (
    st = _; L = st:'L';
    if (_pressed('j' + L:'id', L:'join'), (p = _near(L:'join', 3); if (p, _lane_join(st, p))));
    if (_pressed('s' + L:'id', L:'start'), (p = _near(L:'start', 3); if (p, _lane_start(st, p))))
  ));
  for (pairs(global_L:'claw':'buttons'), if (_pressed('c' + _:0, _:1), (p = _near(_:1, 3); if (p, _claw_button(_:0, p)))));
  if (_pressed('whack', global_L:'whack':'start'), (p = _near(global_L:'whack':'start', 3); if (p, _whack_start(p))));
  if (_pressed('rhythm', global_L:'rhythm':'start'), (p = _near(global_L:'rhythm':'start', 3); if (p, _rhythm_start(p))))
);
__on_player_interacts_with_entity(p, e, hand) -> (
  if (hand != 'mainhand' || !query(e, 'has_tag', 'arcade'), return());
  if (query(e, 'has_tag', 'arc_clerk'), return(_counter(p)));
  _whack_hit(p, e)
);
_cmd_reset() -> (
  p = player(); if (p && !_admin(p), return(0));
  for (entity_selector('@e[tag=arcade]'), modify(_, 'remove'));
  global_ents = {}; global_cool = {};
  for (keys(global_lanes), (global_lanes:_ = _lane_new(global_lanes:_:'L'); _pins_init(global_lanes:_)));
  global_claw = {'on' -> false}; global_whack = {'on' -> false}; global_rhythm = {'on' -> false};
  for (global_dirs, _ddr_tile(_, 'arrow'));
  _ensure(); 1
);
// a ball left over from a game that ended while you were away is removed when you come back
__on_player_connects(p) -> schedule(40, '_clear_ball', p ~ 'name');
_clear_ball(n) -> if (player(n) && first(values(global_lanes), _:'state' == 'playing' && first(_:'players', _ == n) != null) == null,
  run(str('clear %s paper[custom_data={arcade_ball:1b}]', n)));
__on_start() -> (
  global_L = read_file('layout', 'json') || {};
  global_tickets = read_file('tickets', 'json') || {};
  global_best = read_file('scores', 'json') || {};
  global_lanes = {};
  for (global_L:'lanes' || [], (global_lanes:(_:'id') = _lane_new(_); _pins_init(global_lanes:(_:'id'))));
  schedule(10, '_ensure')
);
__on_tick() -> (
  t = tick_time();
  for (values(global_lanes), if (_:'ball' || _:'phase' == 'settle' || first(_:'pins', abs(_:'vx') > 0.004 || abs(_:'vz') > 0.004) != null, _lane_tick(_)));
  if (t % 2 == 0, (_buttons(); for (values(global_lanes), if (_:'meter', _meter_show(_)))));
  if (global_claw:'on' || t % 20 == 0, _claw_tick());
  if (global_whack:'on', _whack_tick());
  if (global_rhythm:'on', _rhythm_tick());
  if (t % 20 == 3, _lanes_watch());
  if (t % 100 == 29, _ensure())
);
status() -> {
  'busy' -> first(values(global_lanes), _:'state' == 'playing') != null || global_claw:'on' || global_whack:'on' || global_rhythm:'on',
  'lanes' -> map(values(global_lanes), [_:'L':'id', _:'state', _:'players']),
  'tickets' -> global_tickets, 'ents' -> length(filter(keys(global_ents), entity_id(global_ents:_)))
};
