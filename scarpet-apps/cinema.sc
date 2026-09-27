// cinema.sc — a screening room without client mods: the film is a list of item models (one per frame, pre-rendered into
// the resource pack) swapped on one big item_display quad by the wall clock, a subtitle strip under it, seats you sit
// on (invisible armor stands), a vanilla wall button (polled) / ticket seller that opens the programme dialog, a board over the door,
// posters, and `light` blocks that dim while the film runs. Music = one long Ogg in the pack ('record' channel).
// Everything is data: cinema.data/rooms.json (rooms, positions, yaw convention documented there) and
// cinema.data/films.json (written by the film generator: id, title, year, fps, frame_models[], cards[], music).
// Commands: /cinema play <film> · /cinema stop (admin) · /cinema reset (admin: respawn the room's entities) ·
// /cinema list · /cinema menu.  Admin: /script in cinema run status()
// Entities are tagged cinema, cinema_r_<room>, cinema_e_<what>: one per tag, guarded (never summon because a selector
// came back empty — the chunk may simply not have its entities loaded yet), extras removed when they load.

__config() -> {
  'stay_loaded' -> true, 'scope' -> 'global', 'command_permission' -> 'all',
  'commands' -> {
    'play <film>' -> '_cmd_play',
    'stop' -> '_cmd_stop',
    'reset' -> '_cmd_reset',
    'list' -> '_cmd_list',
    'menu' -> '_cmd_menu',
    'close' -> '_cmd_close'
  },
  'arguments' -> {'film' -> {'type' -> 'term'}}
};

global_rooms = {};        // room id -> its rooms.json entry
global_films = [];        // films.json
global_run = {};          // room id -> the running film {'film','t0','idx','model','card','n','fps','frames','cards','music'}
global_ents = {};         // unique tag -> uuid of the one entity carrying it
global_cool = {};         // unique tag -> tick_time() before which no new spawn is tried
global_idle = {};         // room id -> the idle look (black screen, lights on, board) has been applied
global_next = {};         // room id -> index of the film shown as "next" on the board
global_pick = {};         // player name -> the room whose button they used last
global_allow_fake = true; // fake players may sit and open the menu (tests)

// ───────────── small helpers ─────────────
_real(p) -> p && (global_allow_fake || (p ~ 'player_type') != 'fake') && (p ~ 'dimension') == 'overworld';
_admin(p) -> !p || (p ~ 'permission_level') >= 2;
_bar(p, text, color) -> run(str('title %s actionbar %s', p ~ 'name', encode_json({'text' -> text, 'color' -> color})));
_film(id) -> first(global_films, _:'id' == id);
_ent(tag) -> entity_id(global_ents:tag);
_in_box(q, b) -> q:0 >= b:'min':0 && q:0 < b:'max':0 + 1 && q:1 >= b:'min':1 - 0.5 && q:1 < b:'max':1 + 1.5 && q:2 >= b:'min':2 && q:2 < b:'max':2 + 1;
_centre(b) -> [(b:'min':0 + b:'max':0) / 2 + 0.5, (b:'min':1 + b:'max':1) / 2, (b:'min':2 + b:'max':2) / 2 + 0.5];
_near(rid, r) -> (
  c = _centre(global_rooms:rid:'box');
  first(player('all'), _real(_) && abs(pos(_):0 - c:0) < r && abs(pos(_):1 - c:1) < r && abs(pos(_):2 - c:2) < r) != null
);
// the room a player is in, else the one they last used a button of, else the nearest one
_room_of(p) -> (
  q = pos(p);
  rid = first(keys(global_rooms), _in_box(q, global_rooms:_:'box'));
  if (rid == null, rid = global_pick:(p ~ 'name'));
  if (rid == null || !global_rooms:rid, (
    best = null; bd = 1000000000;
    for (keys(global_rooms), c = _centre(global_rooms:_:'box'); d = reduce(q - c, _a + _ * _, 0); if (d < bd, (bd = d; best = _)));
    rid = best
  ));
  rid
);

// ───────────── one entity per tag ─────────────
_one(rid, tag, type, at, nbt) -> (
  e = _ent(tag);
  if (e, return(e));
  l = entity_selector(str('@e[type=%s,tag=%s]', type, tag));
  if (l, (
    global_ents:tag = query(l:0, 'uuid');
    for (slice(l, 1), modify(_, 'remove'));
    return(l:0)
  ));
  if (loaded_status(at) < 3 || tick_time() < (global_cool:tag || 0), return(null));
  global_cool:tag = tick_time() + 1200;
  e = spawn(type, at, str('{Tags:["cinema","cinema_r_%s","%s"],%s}', rid, tag, nbt));
  if (e, global_ents:tag = query(e, 'uuid'));
  e
);
_dedupe(u) -> (
  e = entity_id(u); if (!e || !query(e, 'has_tag', 'cinema'), return());
  t = first(query(e, 'scoreboard_tags'), (_ ~ '^cinema_e_') != null);
  if (t == null, return());
  k = global_ents:t;
  if (!k || !entity_id(k), global_ents:t = u,
      k != u, modify(e, 'remove'))
);
_tf(sx, sy, sz) -> str('transformation:{left_rotation:[0f,0f,0f,1f],right_rotation:[0f,0f,0f,1f],translation:[0f,0f,0f],scale:[%.3ff,%.3ff,%.3ff]}', sx, sy, sz);
_item(model) -> str('item:{id:"minecraft:paper",count:1,components:{"minecraft:item_model":"%s"}}', model);

// spawns whatever is missing; returns true when the whole room stands
_ensure(rid) -> (
  r = global_rooms:rid; ok = true;
  s = r:'screen';
  if (!_one(rid, 'cinema_e_screen_' + rid, 'item_display', s:'pos',
        str('Rotation:[%.1ff,0f],brightness:{sky:15,block:15},%s,%s', s:'yaw', _item(r:'black'), _tf(s:'scale', s:'scale', 1))), ok = false);
  u = r:'subtitle';
  if (u && !_one(rid, 'cinema_e_sub_' + rid, 'text_display', u:'pos',
        str('Rotation:[%.1ff,0f],billboard:"fixed",alignment:"center",line_width:%d,background:0,shadow:1b,see_through:0b,brightness:{sky:15,block:15},%s,text:""',
            u:'yaw', u:'line_width' || 300, _tf(u:'scale' || 1.6, u:'scale' || 1.6, 1))), ok = false);
  dy = if (r:'seat_dy' == null, 0.5, r:'seat_dy');
  for (r:'seats', (
    i = _i; q = _;
    if (!_one(rid, str('cinema_e_seat_%s_%d', rid, i), 'armor_stand', [q:0, q:1 + dy, q:2],
          str('Marker:1b,Invisible:1b,NoGravity:1b,Invulnerable:1b,Silent:1b,DisabledSlots:4144959,Rotation:[%.1ff,0f]', r:'seat_yaw' || 0)), ok = false);
    if (!_one(rid, str('cinema_e_hit_%s_%d', rid, i), 'interaction', [q:0, q:1 + 0.5, q:2], 'width:0.7f,height:0.9f,response:1b'), ok = false)
  ));
  // a plain vanilla button block + a small label above it. Reserve a custom item-model button for one signature
  // ride or feature — reusing one custom model everywhere makes every button look and feel the same.
  b = r:'button';
  if (b && b:'block', (
    q = b:'block';
    if (loaded_status(q) >= 3 && (str(block(q)) ~ 'button') == null,
      run(str('setblock %d %d %d %s', q:0, q:1, q:2, b:'state' || 'polished_blackstone_button[face=wall,facing=south]')));
    lp = b:'label_pos';
    if (b:'label' && lp && !_one(rid, 'cinema_e_btnsign_' + rid, 'text_display', lp,
          str('Rotation:[%.1ff,0f],billboard:"fixed",alignment:"center",line_width:100,shadow:1b,background:1342177280,brightness:{sky:15,block:15},%s,text:%s',
              b:'yaw' || 0, _tf(0.32, 0.32, 0.32), encode_json({'text' -> b:'label', 'color' -> '#F5D77A', 'bold' -> true}))), ok = false)
  ));
  d = r:'board';
  if (d && !_one(rid, 'cinema_e_board_' + rid, 'text_display', d:'pos',
        str('Rotation:[%.1ff,0f],billboard:"fixed",alignment:"center",line_width:260,shadow:1b,background:1342177280,brightness:{sky:15,block:15},%s,text:""',
            d:'yaw', _tf(d:'scale' || 0.8, d:'scale' || 0.8, 1))), ok = false);
  n = r:'npc';
  if (n && !_one(rid, 'cinema_e_npc_' + rid, 'mannequin', n:'pos',
        str('Rotation:[%.1ff,0f],pose:"standing",immovable:1b,hide_description:1b,Invulnerable:1b,Silent:1b,profile:{model:"wide",texture:"%s"},CustomName:%s,CustomNameVisible:1b',
            n:'yaw' || 0, n:'skin', encode_json(n:'name'))), ok = false);
  for (r:'posters' || [], (
    i = _i; q = _;
    py = q:'yaw'; if (py == null, py = if (d, d:'yaw', 0));
    if (!_one(rid, str('cinema_e_poster_%s_%d', rid, i), 'item_display', q:'pos',
          str('Rotation:[%.1ff,0f],brightness:{sky:15,block:15},%s,%s', py, _item(q:'model'), _tf(q:'w', q:'h', 1))), ok = false)
  ));
  if (ok && !global_idle:rid && !global_run:rid, (
    _screen_set(rid, r:'black'); _sub(rid, ''); _lights(rid, false); _board(rid);
    global_idle:rid = true
  ));
  ok
);

// ───────────── the screen, strip, lights, board ─────────────
_screen_set(rid, model) -> (e = _ent('cinema_e_screen_' + rid); if (e, modify(e, 'nbt_merge', '{' + _item(model) + '}')));
_sub(rid, txt) -> (e = _ent('cinema_e_sub_' + rid); if (e, modify(e, 'nbt_merge', str('{text:%s}', encode_json({'text' -> txt, 'color' -> '#F5E6C8'})))));
_lights(rid, dim) -> (
  L = global_rooms:rid:'lights'; if (!L, return());
  run(str('fill %d %d %d %d %d %d light[level=%d] replace light', L:'min':0, L:'min':1, L:'min':2, L:'max':0, L:'max':1, L:'max':2, if (dim, L:'dim', L:'on')))
);
_board(rid) -> (
  e = _ent('cinema_e_board_' + rid); if (!e, return());
  r = global_rooms:rid; R = global_run:rid;
  lines = [{'text' -> r:'name', 'color' -> '#F5D77A', 'bold' -> true}, {'text' -> '\n'}];
  if (R, (
    f = _film(R:'film');
    lines += {'text' -> 'Now showing: ' + if (f, f:'title', R:'film'), 'color' -> '#FFC1E0', 'bold' -> true}
  ), (
    f = global_films:(global_next:rid || 0);
    if (f, lines += {'text' -> str('Next: %s · %s', f:'title', f:'year'), 'color' -> 'white'},
           lines += {'text' -> 'Nothing on the programme today', 'color' -> 'gray'})
  ));
  modify(e, 'nbt_merge', str('{text:%s}', encode_json(lines)))
);

// ───────────── playing ─────────────
_secs_left(R) -> max(0, ceil(R:'n' / R:'fps' - (unix_time() - R:'t0') / 1000));
_play(rid, fid) -> (
  r = global_rooms:rid; f = _film(fid);
  if (!r, return('no such room'));
  if (!f, return('no such film'));
  if (global_run:rid, return('busy'));
  fr = f:'frame_models';
  if (!fr, return('the film has no frames'));
  fps = f:'fps' || 4;
  global_run:rid = {'film' -> fid, 't0' -> unix_time(), 'idx' -> -1, 'model' -> null, 'card' -> null,
                    'n' -> length(fr), 'fps' -> fps, 'frames' -> fr, 'cards' -> f:'cards' || [], 'music' -> f:'music'};
  _lights(rid, true);
  if (f:'music', (s = r:'sound'; sound(f:'music', s:'pos', s:'volume' || 1, 1, 'record')));
  _board(rid);
  _frame(rid);
  'ok'
);
// wall-clock frame index, not a tick counter: lag or a slow tick never desyncs the picture from the music.
_frame(rid) -> (
  R = global_run:rid; if (!R, return());
  idx = floor((unix_time() - R:'t0') * R:'fps' / 1000);
  if (idx >= R:'n', return(_end(rid, true)));
  if (idx == R:'idx', return());
  R:'idx' = idx;
  m = R:'frames':idx;
  if (m != R:'model', (R:'model' = m; _screen_set(rid, m)));
  c = first(R:'cards', idx >= _:'from' && idx <= _:'to');
  txt = if (c, c:'text', '');
  if (txt != R:'card', (R:'card' = txt; _sub(rid, txt)))
);
_end(rid, natural) -> (
  R = global_run:rid; if (!R, return());
  delete(global_run, rid);
  r = global_rooms:rid;
  _screen_set(rid, r:'black'); _sub(rid, '');
  if (R:'music', run(str('stopsound @a record %s', R:'music')));
  _lights(rid, false);
  k = first(range(length(global_films)), global_films:_:'id' == R:'film');
  global_next:rid = if (k == null || !global_films, 0, (k + 1) % length(global_films));
  _board(rid);
  if (natural, for (player('all'), if (_real(_) && _in_box(pos(_), r:'box'), _bar(_, 'THE END ♥ thanks for watching', 'gold'))))
);

// ───────────── the programme dialog ─────────────
_dialog(title, body, actions, columns) -> ({
  'type' -> 'minecraft:multi_action', 'title' -> title,
  'body' -> [{'type' -> 'minecraft:plain_message', 'contents' -> body, 'width' -> 320}],
  'can_close_with_escape' -> true, 'pause' -> false, 'after_action' -> 'none', 'columns' -> columns,
  'actions' -> actions,
  'exit_action' -> {'label' -> 'Close', 'width' -> 120, 'action' -> {'type' -> 'run_command', 'command' -> '/cinema close'}}
});
_btn(label, cmd) -> ({'label' -> label, 'width' -> 200, 'action' -> {'type' -> 'run_command', 'command' -> cmd}});
_menu(p, rid) -> (
  r = global_rooms:rid; if (!r, return());
  global_pick:(p ~ 'name') = rid;
  R = global_run:rid; acts = [];
  if (R, (
    f = _film(R:'film');
    body = str('Now showing: %s · %d seconds left', if (f, f:'title', R:'film'), _secs_left(R));
    if (_admin(p), acts += _btn('Stop', '/cinema stop'))
  ), (
    body = if (global_films, 'Pick a film — the lights will dim and the show will start. Take a seat!', 'Nothing on the programme right now.');
    for (global_films, acts += _btn(str('▶ %s · %s', _:'title', _:'year'), '/cinema play ' + _:'id'))
  ));
  run(str('dialog show %s %s', p ~ 'name', encode_json(_dialog('◆ ' + r:'name' + ' ◆', body, acts, 1))))
);

// ───────────── the vanilla button: powered rising edge → menu for the nearest real player ─────────────
global_btn_prev = {};     // room id -> was the button powered on the previous poll
global_btn_cd = {};       // player name -> unix_time() of the last press we served
_btn_poll() -> (
  for (keys(global_rooms), (
    rid = _; b = global_rooms:rid:'button';
    if (b && b:'block' && loaded_status(b:'block') >= 3, (
      q = b:'block';
      on = str(block_state(block(q), 'powered')) == 'true';
      if (on && !global_btn_prev:rid, (
        best = null; bd = 25;
        for (player('all'), if (_real(_), (d = reduce(pos(_) - (q + 0.5), _a + _ * _, 0); if (d < bd, (bd = d; best = _)))));
        if (best, (
          n = best ~ 'name';
          if (unix_time() - (global_btn_cd:n || 0) > 3000, (global_btn_cd:n = unix_time(); global_pick:n = rid; _menu(best, rid)))
        ))
      ));
      global_btn_prev:rid = on
    ))
  ))
);

// ───────────── clicks: ticket seller → menu, seat → sit ─────────────
__on_player_interacts_with_entity(p, e, hand) -> (
  if (hand != 'mainhand' || !_real(p) || !query(e, 'has_tag', 'cinema'), return());
  tags = query(e, 'scoreboard_tags');
  rid = null;
  for (keys(global_rooms), k = _; if (first(tags, _ == 'cinema_r_' + k) != null, rid = k));
  if (rid == null, return());
  if (first(tags, _ == 'cinema_e_btnhit_' + rid || _ == 'cinema_e_npc_' + rid) != null, return(_menu(p, rid)));
  hit = first(tags, (_ ~ ('^cinema_e_hit_' + rid + '_\\d+$')) != null);
  if (hit, _sit(p, rid, number(slice(hit, length('cinema_e_hit_' + rid) + 1))))
);
_sit(p, rid, i) -> (
  st = _ent(str('cinema_e_seat_%s_%d', rid, i));
  if (!st, return());
  if (query(p, 'mount'), return());
  if (query(st, 'passengers'), return(_bar(p, 'seat taken', 'red')));
  run(str('ride %s mount %s', p ~ 'name', query(st, 'uuid')));
  yaw = global_rooms:rid:'seat_yaw';
  if (yaw != null, run(str('rotate %s %.1f 0', p ~ 'name', yaw)));
  _bar(p, if (global_run:rid, 'Enjoy the film! Shift = stand up', 'Have a seat — press the button at the box office to start the show. Shift = stand up'), 'light_purple');
  run(str('playsound minecraft:block.wool.place master %s ~ ~ ~ 0.6 0.8', p ~ 'name'))
);

// ───────────── commands ─────────────
_cmd_play(film) -> (
  p = player();
  rid = if (p, _room_of(p), first(keys(global_rooms), true));
  if (p, run('dialog clear ' + p ~ 'name'));
  if (rid == null, return(if (p, _bar(p, 'No screening room here', 'red'), print('no rooms'))));
  res = _play(rid, film);
  if (p, (
    if (res == 'ok', _bar(p, 'The show is starting — take a seat!', 'gold'),
        res == 'busy', _bar(p, 'A film is already playing — wait for it to end', 'yellow'),
        _bar(p, 'Film not found', 'red'))
  ), print(res));
  1
);
_cmd_stop() -> (
  p = player();
  if (p, run('dialog clear ' + p ~ 'name'));
  if (!_admin(p), return(_bar(p, 'Only admins can stop a screening', 'red')));
  rids = if (p, [_room_of(p)], keys(global_run));
  for (rids, if (_ != null && global_run:_, _end(_, false)));
  if (p, _bar(p, 'Screening stopped', 'gray'), print('stopped'));
  1
);
_cmd_reset() -> (
  p = player();
  if (!_admin(p), return(_bar(p, 'Admins only', 'red')));
  rids = if (p, [_room_of(p)], keys(global_rooms));
  for (rids, if (_ != null, reset(_)));
  if (p, _bar(p, 'Room rebuilt', 'gray'), print('reset'));
  1
);
_cmd_list() -> (
  p = player();
  for (global_films, t = str('▶ %s · %s (%s) — %d frames @ %s fps', _:'title', _:'year', _:'id', length(_:'frame_models' || []), _:'fps' || 4);
    if (p, print(p, t), print(t)));
  if (!global_films, if (p, print(p, 'No films'), print('no films')));
  1
);
_cmd_menu() -> (p = player(); if (p && _real(p), (rid = _room_of(p); if (rid != null, _menu(p, rid)))); 1);
_cmd_close() -> (p = player(); if (p, run('dialog clear ' + p ~ 'name')); 1);

// kill + respawn one room's entities (riders are put on the floor first)
reset(rid) -> (
  r = global_rooms:rid; if (!r, return('no such room'));
  if (global_run:rid, _end(rid, false));
  for (entity_selector('@e[tag=cinema_r_' + rid + ']'), (
    for (query(_, 'passengers'), if (query(_, 'type') == 'player', run('ride ' + (_ ~ 'name') + ' dismount')));
    modify(_, 'remove')
  ));
  for (keys(global_ents), if ((_ ~ ('_' + rid + '(_|$)')) != null, delete(global_ents, _)));
  global_cool = {}; global_idle:rid = false;
  if (_ensure(rid), 'ok', 'partial — the room is not loaded, it completes when someone comes near')
);

// ───────────── lifecycle ─────────────
_load() -> (
  global_rooms = read_file('rooms', 'json') || {};
  delete(global_rooms, '_doc');
  global_films = read_file('films', 'json') || [];
  if (type(global_films) != 'list', global_films = []);
  global_films = filter(global_films, _:'id' != null)
);
__on_start() -> (
  _load();
  global_run = {}; global_idle = {};
  for (['item_display', 'text_display', 'armor_stand', 'interaction', 'mannequin'],
    entity_load_handler(_, _(e, new) -> if (!new, schedule(0, '_dedupe', query(e, 'uuid')))));
  schedule(5, '_ensure_all')
);
_ensure_all() -> for (keys(global_rooms), if (_near(_, 96), _ensure(_)));
__on_tick() -> (
  t = tick_time();
  if (global_run, for (keys(global_run), _frame(_)));
  if (t % 2 == 0, _btn_poll());
  if (t % 100 == 7, _ensure_all())
);

status() -> (
  m = {'busy' -> length(global_run) > 0, 'rooms' -> keys(global_rooms), 'films' -> map(global_films, _:'id'), 'running' -> {}};
  for (keys(global_run), R = global_run:_; m:'running':_ = {'film' -> R:'film', 'frame' -> R:'idx', 'of' -> R:'n', 'left_s' -> _secs_left(R), 'card' -> R:'card'});
  m:'ents' = length(filter(keys(global_ents), entity_id(global_ents:_)));
  m
);
