// runway.sc — the character studio's live fashion show (Pink Golem).
// Sign up at the host podium with the look you are wearing (the four armour slots + the skin you wear now), press
// the black button, and every signed-up look walks the runway on a model mannequin: from backstage (north) to the
// audience (south), a pose with flashes and cheers and a spin, and back. A finale lines everyone up. Nobody signed
// up = a "house show" of random looks from the wardrobe on the studio skins. Music (lounge:runway.show, an original
// 64 s nu-disco loop) and titles go only to real players on the studio floor. The line-up clears after each show.
// The skin a player wears now comes from the shared file skins_now.json (written by residents.sc and skinpaint.sc):
// a signed MineSkin texture, a pack texture, or nothing (then the model asks for the player's own name).
// Data: runway.data/config.json (places), wardrobe.json (copy of the studio catalogue), lineup.json (runtime).
// Commands: /runway join | leave | close | start | stop (stop: ops)

__config() -> {
  'stay_loaded' -> true, 'scope' -> 'global', 'command_permission' -> 'all',
  'commands' -> {'join' -> '_cmd_join', 'leave' -> '_cmd_leave', 'close' -> '_cmd_close', 'start' -> '_cmd_start', 'stop' -> '_cmd_stop'}
};

global_C = {};
global_W = {};           // wardrobe.json
global_lineup = [];      // [{name, items:{head,chest,legs,feet: nbt string}, skin, look}]
global_show = null;      // the running show
global_prev = {};
global_ents = {};
global_cool = {};
global_last_end = 0;
global_allow_fake = false;

// ───────────── helpers ─────────────
_bar(p, text, color) -> run(str('title %s actionbar %s', p ~ 'name', encode_json({'text' -> text, 'color' -> color})));
_real(p) -> p && ((p ~ 'player_type') != 'fake' || global_allow_fake);
_d2(a, b) -> (a:0 - b:0) ^ 2 + (a:1 - b:1) ^ 2 + (a:2 - b:2) ^ 2;
_ent(tag) -> entity_id(global_ents:tag);
_in_floor(p) -> (f = global_C:'floor'; q = pos(p); (p ~ 'dimension') == 'overworld' &&
  q:0 >= f:'min':0 && q:0 < f:'max':0 && q:1 >= f:'min':1 && q:1 < f:'max':1 && q:2 >= f:'min':2 && q:2 < f:'max':2);
_audience() -> filter(player('all'), _real(_) && _in_floor(_));
_tf(s) -> str('transformation:{left_rotation:[0f,0f,0f,1f],right_rotation:[0f,0f,0f,1f],translation:[0f,0f,0f],scale:[%.3ff,%.3ff,%.3ff]}', s, s, s);
_plain(text, color) -> {'type' -> 'minecraft:plain_message', 'contents' -> {'text' -> text, 'color' -> color}, 'width' -> 300};
_btn(label, cmd) -> {'label' -> label, 'width' -> 200, 'action' -> {'type' -> 'run_command', 'command' -> cmd}};
_show(p, title, body, acts) -> run(str('dialog show %s %s', p ~ 'name', encode_json({
  'type' -> 'minecraft:multi_action', 'title' -> {'text' -> title, 'color' -> '#FF7AC6', 'bold' -> true},
  'body' -> body, 'can_close_with_escape' -> true, 'pause' -> false, 'after_action' -> 'none', 'columns' -> 1, 'actions' -> acts,
  'exit_action' -> {'label' -> 'Close', 'width' -> 120, 'action' -> {'type' -> 'run_command', 'command' -> '/runway close'}}})));
_cmd_close() -> (p = player(); if (p, run('dialog clear ' + p ~ 'name')); 1);
_one(tag, type, at, nbt) -> (
  e = _ent(tag); if (e, return(e));
  l = entity_selector(str('@e[type=%s,tag=%s]', type, tag));
  if (l, (global_ents:tag = query(l:0, 'uuid'); for (slice(l, 1), modify(_, 'remove')); return(l:0)));
  if (loaded_status(at) < 3 || tick_time() < (global_cool:tag || 0), return(null));
  global_cool:tag = tick_time() + 1200;
  e = spawn(type, at, str('{Tags:["runway","%s"],%s}', tag, nbt));
  if (e, global_ents:tag = query(e, 'uuid'));
  e
);
_text(tag, pos, yaw, text, scale, bg) -> _one(tag, 'text_display', pos,
  str('Rotation:[%.1ff,0f],billboard:"fixed",alignment:"center",line_width:240,shadow:%s,background:%d,brightness:{sky:15,block:15},view_range:0.8f,%s,text:%s',
      yaw, if (bg == 0, '1b', '0b'), bg, _tf(scale), encode_json(text)));
_set_text(tag, text) -> (e = _ent(tag); if (e, modify(e, 'nbt_merge', str('{text:%s}', encode_json(text)))));
_item_name(nbt) -> (m = str(nbt) ~ 'custom_name":\\{[^}]*text:"([^"]*)"'; if (m, m, null));

// ───────────── sign-up: the look you wear now ─────────────
_snapshot(p) -> (
  items = {}; names = [];
  for ([['head', 39], ['chest', 38], ['legs', 37], ['feet', 36]], (
    it = inventory_get(p, _:1);
    if (it, (items:(_:0) = str(it:2); nm = _item_name(it:2); if (nm, names += nm, names += replace(it:0, '_', ' '))))
  ));
  skins = read_file('skins_now', 'shared_json') || {};
  sk = skins:lower(p ~ 'name');
  {'name' -> p ~ 'name', 'items' -> items, 'skin' -> sk, 'look' -> join(' · ', names),
   'skin_label' -> if (sk && sk:'label', sk:'label', 'Your own skin')}
);
_join_dialog(p) -> (
  s = _snapshot(p); n = p ~ 'name';
  inl = first(global_lineup, _:'name' == n) != null;
  _show(p, '◆ Fashion show ◆', [
      _plain(if (s:'look', 'Your look now: ' + s:'look', 'You\'re not wearing studio clothes — dress up at the fitting wall and come back'), 'white'),
      _plain('Skin: ' + s:'skin_label', '#FFD6EC'),
      _plain(if (s:'skin', '', 'Tip: for the model to wear exactly your skin, put it on again from the studio or "My skins", then sign up'), 'gray'),
      _plain(if (inl, 'You\'re already in the line-up — you can update it to your current look.', str('In the line-up now: %d', length(global_lineup))), 'gray')],
    [_btn(if (inl, '✓ Update to this look', '✓ Sign up with this look'), '/runway join'), _btn('✕ Leave the line-up', '/runway leave')])
);
_cmd_join() -> (
  p = player(); if (!p, return(0)); n = p ~ 'name'; run('dialog clear ' + n);
  if (global_show, return(_bar(p, 'The show is running — sign up for the next one after it', 'yellow')));
  s = _snapshot(p);
  l = filter(global_lineup, _:'name' != n);
  if (length(l) >= global_C:'max_models', return(_bar(p, 'The line-up is full for this show', 'yellow')));
  l += s; global_lineup = l; _save(); _board();
  _bar(p, str('✦ You\'re in the show! Number %d in line', length(l)), '#FF7AC6');
  run(str('playsound minecraft:block.amethyst_block.chime master %s ~ ~ ~ 0.8 1.3', n)); 1
);
_cmd_leave() -> (
  p = player(); if (!p, return(0)); n = p ~ 'name'; run('dialog clear ' + n);
  global_lineup = filter(global_lineup, _:'name' != n); _save(); _board();
  _bar(p, 'You left the line-up', 'white'); 1
);
_save() -> write_file('lineup', 'json', global_lineup);
_board() -> (
  names = map(global_lineup, _:'name');
  _set_text('rw_board', ['', {'text' -> '✦ Fashion show ✦', 'color' -> '#FF7AC6', 'bold' -> true},
    {'text' -> if (global_show, '\nThe show is on!', names, '\nSigned up: ' + join(', ', names), '\nNobody yet — be the first'), 'color' -> 'white'},
    {'text' -> '\nPink = sign up · black = start', 'color' -> '#FFD6EC'}])
);

// ───────────── the show ─────────────
_cmd_start() -> (p = player(); if (p, _start(p)); 1);
_cmd_stop() -> (p = player(); if (p && (p ~ 'permission_level') >= 2, _finish(true)); 1);
_house_lineup() -> (
  rows = global_W:'rows'; l = [];
  for (range(3), (
    items = {};
    hr = first(rows, _:'key' == 'head'); tr = first(rows, _:'key' == 'top'); wr = first(rows, _:'key' == 'wings');
    lr = first(rows, _:'key' == 'legs'); fr = first(rows, _:'key' == 'feet');
    h = hr:'items':(1 + floor(rand(length(hr:'items') - 1))); t = tr:'items':(1 + floor(rand(length(tr:'items') - 1)));
    w = if (rand(1) < 0.4, wr:'items':(1 + floor(rand(length(wr:'items') - 1))), {'id' -> 'none'});
    lg = lr:'items':(1 + floor(rand(length(lr:'items') - 1))); f = fr:'items':(1 + floor(rand(length(fr:'items') - 1)));
    sk = global_C:'studio_skins':(floor(rand(length(global_C:'studio_skins'))));
    l += {'name' -> '✦', 'nick' -> 'House model', 'skin' -> {'texture' -> 'studio:entity/skin/' + sk}, 'look' -> str('%s · %s · %s', h:'name', t:'name', lg:'name'),
          'items_str' -> {'head' -> h:'item', 'chest' -> global_W:'chest':(t:'id' + '|' + w:'id'), 'legs' -> lg:'item', 'feet' -> f:'item'}}
  ));
  l
);
_start(p) -> (
  if (global_show, return(_bar(p, 'The show is already running', 'yellow')));
  if (unix_time() - global_last_end < global_C:'cooldown_s' * 1000, return(_bar(p, 'One moment… the next show starts in a few seconds', 'yellow')));
  l = if (global_lineup, slice(global_lineup, 0, min(length(global_lineup), global_C:'max_models')), _house_lineup());
  global_show = {'list' -> l, 'i' -> 0, 'phase' -> 'intro', 't' -> 0, 'music' -> -1, 'listeners' -> {}, 'house' -> !global_lineup};
  _board();
  for (_audience(), (
    run(str('title %s times 10 50 15', _ ~ 'name'));
    run(str('title %s subtitle %s', _ ~ 'name', encode_json({'text' -> if (global_show:'house', 'House show', str('%d models', length(l))), 'color' -> 'white'})));
    run(str('title %s title %s', _ ~ 'name', encode_json({'text' -> '✦ Fashion show ✦', 'color' -> '#FF7AC6', 'bold' -> true})))
  ))
);
_music(S) -> (
  for (_audience(), (
    n = _ ~ 'name';
    if (S:'music' < 0 || tick_time() - S:'music' >= 1280 || !S:'listeners':n, (
      run(str('execute as %s at @s run playsound lounge:runway.show record @s ~ ~ ~ 0.8 1 0.8', n));
      S:'listeners':n = true
    ))
  ));
  if (S:'music' < 0 || tick_time() - S:'music' >= 1280, (
    S:'music' = tick_time();
    for (keys(S:'listeners'), if (!player(_) || !_in_floor(player(_)), delete(S:'listeners', _)))
  ))
);
_model_spawn(m, z, yaw, tag) -> (
  R = global_C:'runway';
  e = spawn('mannequin', [R:'x', R:'y', z], str('{Tags:["runway","rw_model","%s"],Rotation:[%.1ff,0f],pose:"standing",immovable:1b,hide_description:1b,Invulnerable:1b,Silent:1b,CustomNameVisible:0b}', tag, yaw));
  if (!e, return(null));
  u = query(e, 'uuid'); sk = m:'skin';
  prof = if (sk && sk:'value', str('{properties:[{name:"textures",value:"%s",signature:"%s"}]}', sk:'value', sk:'sig'),
             sk && sk:'texture', str('{texture:"%s",model:"wide"}', sk:'texture'),
             str('{name:"%s"}', m:'name'));
  run(str('data modify entity %s profile set value %s', u, prof));
  if (m:'items', for (keys(m:'items'), run(str('data modify entity %s equipment.%s set value %s', u, _, m:'items':_))));
  if (m:'items_str', for (keys(m:'items_str'), if (m:'items_str':_, run(str('item replace entity %s armor.%s with %s', u, _, m:'items_str':_)))));
  e
);
_announce(m) -> (
  who = if (m:'nick', m:'nick', m:'name');
  for (_audience(), (
    run(str('title %s times 5 70 10', _ ~ 'name'));
    run(str('title %s title %s', _ ~ 'name', encode_json({'text' -> ''})));
    run(str('title %s subtitle %s', _ ~ 'name', encode_json({'text' -> '✦ ' + who + ' ✦', 'color' -> '#FF7AC6', 'bold' -> true})));
    _bar(_, if (m:'look', m:'look', 'Their own look'), 'white')
  ))
);
_flash(pos) -> (
  run(str('particle minecraft:flash %.2f %.2f %.2f 0 0 0 0 1 force', pos:0, pos:1 + 1.2, pos:2));
  run(str('particle minecraft:end_rod %.2f %.2f %.2f 1.2 0.8 1.2 0.05 30 force', pos:0, pos:1 + 1, pos:2));
  for (_audience(), run(str('execute as %s at @s run playsound lounge:runway.pose record @s %.2f %.2f %.2f 1 1 0.6', _ ~ 'name', pos:0, pos:1, pos:2)))
);
_show_tick() -> (
  S = global_show; R = global_C:'runway';
  S:'t' = S:'t' + 1; t = S:'t';
  _music(S);
  ph = S:'phase';
  if (ph == 'intro', (if (t >= 60, (S:'phase' = 'walk_in'; S:'t' = 0)); return()));
  if (ph == 'finale', return(_finale_tick(S)));
  m = S:'list':(S:'i');
  e = entity_id(S:'e');
  if (ph == 'walk_in', (
    if (t == 1, (e = _model_spawn(m, R:'z_back', 0, 'rw_walk'); S:'e' = if (e, query(e, 'uuid'), null); _announce(m)));
    if (!e, return(_next(S)));
    z = min(R:'z_front', R:'z_back' + t * R:'speed');
    modify(e, 'pos', R:'x', R:'y', z);
    if (z >= R:'z_front', (S:'phase' = 'pose'; S:'t' = 0; _flash([R:'x', R:'y', z])))
  ), ph == 'pose', (
    if (!e, return(_next(S)));
    // a spin, a dip, flashes
    a = if (t <= 40, t * 9, 0); modify(e, 'yaw', a); modify(e, 'body_yaw', a); modify(e, 'head_yaw', a);
    if (t == 20, modify(e, 'nbt_merge', '{pose:"crouching"}'));
    if (t == 28, modify(e, 'nbt_merge', '{pose:"standing"}'));
    if (t == 30, _flash(pos(e)));
    if (t >= 60, (S:'phase' = 'walk_out'; S:'t' = 0; modify(e, 'yaw', 180); modify(e, 'body_yaw', 180); modify(e, 'head_yaw', 180)))
  ), ph == 'walk_out', (
    if (!e, return(_next(S)));
    z = max(R:'z_back', R:'z_front' - t * R:'speed');
    modify(e, 'pos', R:'x', R:'y', z);
    if (z <= R:'z_back', (modify(e, 'remove'); _next(S)))
  ))
);
_next(S) -> (
  S:'i' = S:'i' + 1; S:'t' = 0; S:'e' = null;
  S:'phase' = if (S:'i' >= length(S:'list'), 'finale', 'walk_in')
);
_finale_tick(S) -> (
  R = global_C:'runway'; t = S:'t'; l = S:'list'; n = min(5, length(l));
  if (t == 1, (
    S:'fin' = [];
    for (range(n), (
      e = _model_spawn(l:_, R:'z_front' - 1, 0, 'rw_fin');
      if (e, (modify(e, 'pos', R:'x' + (_ - (n - 1) / 2) * 1.0, R:'y', R:'z_front' - 1); f = S:'fin'; f += query(e, 'uuid'); S:'fin' = f))
    ));
    for (_audience(), (
      run(str('title %s times 10 60 20', _ ~ 'name'));
      run(str('title %s subtitle %s', _ ~ 'name', encode_json({'text' -> 'Thank you, models!', 'color' -> 'white'})));
      run(str('title %s title %s', _ ~ 'name', encode_json({'text' -> '✦ Finale ✦', 'color' -> '#FF7AC6', 'bold' -> true})))
    ))
  ));
  if (t % 20 == 5 && t < 100, _flash([R:'x' + (rand(4) - 2), R:'y', R:'z_front' - 1]));
  if (t == 60, for (S:'fin', (e = entity_id(_); if (e, modify(e, 'nbt_merge', '{pose:"crouching"}')))));
  if (t == 70, for (S:'fin', (e = entity_id(_); if (e, modify(e, 'nbt_merge', '{pose:"standing"}')))));
  if (t >= 140, _finish(false))
);
_finish(stopped) -> (
  S = global_show; if (!S, return());
  for (entity_selector('@e[type=mannequin,tag=rw_model]'), modify(_, 'remove'));
  for (keys(S:'listeners'), if (player(_), run(str('stopsound %s record lounge:runway.show', _))));
  global_show = null; global_last_end = unix_time();
  if (!stopped && !S:'house', (global_lineup = []; _save()));
  _board()
);

// ───────────── buttons + entities ─────────────
_press(pos, key) -> (
  b = block(pos:0, pos:1, pos:2);
  on = str(block_state(b, 'powered')) == 'true';
  was = global_prev:key; global_prev:key = on;
  if (!on || was, return(null));
  c = [pos:0 + 0.5, pos:1 + 0.5, pos:2 + 0.5]; best = null; bd = 30;
  for (player('all'), if (_real(_) && _d2(pos(_), c) < bd, (bd = _d2(pos(_), c); best = _)));
  if (best, run(str('playsound minecraft:ui.button.click master %s ~ ~ ~ 0.35 1.6', best ~ 'name')));
  best
);
_ensure() -> (
  C = global_C; if (!C:'runway', return());
  _text('rw_board', C:'board', 0, '', 0.42, 1342177280);
  _text('rw_join_lbl', C:'join_label', 0, {'text' -> '✦ Sign up', 'color' -> '#FFE3F1', 'bold' -> true}, 0.32, 0);
  _text('rw_start_lbl', C:'start_label', 90, {'text' -> '▶ Show', 'color' -> '#FFE3F1', 'bold' -> true}, 0.32, 0);
  // a billboard over the podium, readable from anywhere on the floor (the board itself faces the lift)
  b = C:'board'; _one('rw_float', 'text_display', [b:0, b:1 + 1.25, b:2 - 0.05],
    str('billboard:"center",alignment:"center",shadow:1b,background:0,brightness:{sky:15,block:15},view_range:1.0f,%s,text:%s', _tf(0.6),
        encode_json(['', {'text' -> '✦ Fashion show ✦', 'color' -> '#FF7AC6', 'bold' -> true}, {'text' -> '\npink = sign up · black = start', 'color' -> 'white'}])));
  sp = C:'signpost';
  signs = [['rw_sign_0', '◀ Fitting wall · clothes'], ['rw_sign_1', '◀ Skin easel · creators\' gallery'],
           ['rw_sign_2', '▲ The runway · fashion show'], ['rw_sign_3', '▶ Lounge · residents office']];
  for (signs, _text(_:0, [sp:'x', sp:'y0' - _i * 0.36, sp:'z'], 0, {'text' -> _:1, 'color' -> '#FFFFFF', 'bold' -> true}, 0.36, -2130740538));
  _board()
);

__on_start() -> (
  global_C = read_file('config', 'json') || {};
  global_W = read_file('wardrobe', 'json') || {};
  global_lineup = read_file('lineup', 'json') || [];
  for (entity_selector('@e[type=mannequin,tag=rw_model]'), modify(_, 'remove'));   // a reload mid-show leaves no models behind
  schedule(10, '_ensure')
);
__on_tick() -> (
  t = tick_time();
  if (global_show, _show_tick());
  if (t % 2 == 0 && global_C:'join_button' && _audience(), (
    p = _press(global_C:'join_button', 'join'); if (p, _join_dialog(p));
    p = _press(global_C:'start_button', 'start'); if (p, _start(p))
  ));
  if (t % 100 == 57, _ensure())
);
__on_player_disconnects(p, reason) -> null;

status() -> {'busy' -> global_show != null, 'lineup' -> map(global_lineup, _:'name'), 'phase' -> if (global_show, global_show:'phase', null)};
