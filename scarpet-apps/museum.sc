// museum.sc — the tower server-history museum. A timeline of the city's landmarks: each station is a
// framed photo (an item_display quad from the museum_pack, scaled [w,h,1] on the wall) with its number + date above and a
// plaque below; boards (title, hall of fame, "what's next") are text_displays; four spinning exhibits sit in glass cases;
// the guide (a mannequin by the lift) opens a dialog: every station → its story → a teleport there.
// Data: museum.data/museum.json (written by your build generator) —
//   stations[] {n, id, model, title, date, text, pos (photo centre, 0.05 in front of the wall), face, w, h, tp:[x,y,z]}
//   boards[]   {id, pos, face, scale, lines:[[text, colour, bold]]}
//   exhibits[] {id, model, pos, scale, spin, title, sub, plaque}
//   guide      {pos, yaw, name, skin}
// face = the side the VIEWERS stand on: south → yaw 0, east → -90, west → 90, north → 180 (gallery.sc / cinema.sc).
// Adding a station = one more screenshot + one line in the generator (gen_museum_pack.py IDS + S[]) → run both → reset.
// Commands: /museum guide · /museum info <n> · /museum go <n> · /museum reset (admin) · /museum list

__config() -> {
  'stay_loaded' -> true, 'scope' -> 'global', 'command_permission' -> 'all',
  'commands' -> {'guide' -> '_cmd_guide', 'info <n>' -> '_cmd_info', 'go <n>' -> '_cmd_go', 'close' -> '_cmd_close',
                 'reset' -> '_cmd_reset', 'list' -> '_cmd_list'},
  'arguments' -> {'n' -> {'type' -> 'int', 'min' -> 1, 'max' -> 99, 'suggest' -> []}}
};

global_M = {};
global_ents = {};
global_cool = {};
global_spin = {};
global_active = false;
global_go_cd = {};        // player name -> unix_time() of the last teleport
global_allow_fake = false;

_real(p) -> p && (global_allow_fake || (p ~ 'player_type') != 'fake') && (p ~ 'dimension') == 'overworld';
_admin(p) -> !p || (p ~ 'permission_level') >= 2;
_ent(tag) -> entity_id(global_ents:tag);
_yaw(face) -> if (face == 'east', -90, face == 'west', 90, face == 'north', 180, 0);
_tf(sx, sy, sz) -> str('transformation:{left_rotation:[0f,0f,0f,1f],right_rotation:[0f,0f,0f,1f],translation:[0f,0f,0f],scale:[%.3ff,%.3ff,%.3ff]}', sx, sy, sz);
_item(model) -> str('item:{id:"minecraft:paper",count:1,components:{"minecraft:item_model":"%s"}}', model);
_bar(p, text, color) -> run(str('title %s actionbar %s', p ~ 'name', encode_json({'text' -> text, 'color' -> color})));
_comp(lines) -> (
  out = [];
  for (lines, (
    if (_i > 0, out += '\n');
    out += {'text' -> _:0, 'color' -> _:1, 'bold' -> bool(_:2)}
  ));
  out
);
_text(tag, at, yaw, lines, sc, bg, billboard) -> [tag, 'text_display', at,
  str('Rotation:[%.1ff,0f],billboard:"%s",alignment:"center",line_width:260,shadow:1b,background:%d,brightness:{sky:15,block:15},%s,text:%s',
      yaw, billboard, bg, _tf(sc, sc, sc), encode_json(_comp(lines)))];

_wanted() -> (
  W = [];
  for (global_M:'stations' || [], (
    s = _; yaw = _yaw(s:'face'); q = s:'pos';
    W += ['museum_e_ph_' + s:'id', 'item_display', q, str('Rotation:[%.1ff,0f],brightness:{sky:15,block:15},%s,%s', yaw, _item(s:'model'), _tf(s:'w', s:'h', 1))];
    W += _text('museum_e_dt_' + s:'id', [q:0, q:1 + s:'h' / 2 + 0.12, q:2], yaw, [[str('%d · %s', s:'n', s:'date'), '#F5D77A', true]], 0.6, 0, 'fixed');
    W += _text('museum_e_pl_' + s:'id', [q:0, q:1 - s:'h' / 2 - 0.5, q:2], yaw,
               [[s:'title', '#F5D77A', true], [s:'text', '#EEEEEE', false]], 0.42, -1442840576, 'fixed')
  ));
  for (global_M:'boards' || [], W += _text('museum_e_b_' + _:'id', _:'pos', _yaw(_:'face'), _:'lines', _:'scale', 0, 'fixed'));
  for (global_M:'exhibits' || [], (
    a = _; sc = a:'scale' || 1;
    W += ['museum_e_x_' + a:'id', 'item_display', a:'pos', str('teleport_duration:2,brightness:{sky:15,block:15},%s,%s', _item(a:'model'), _tf(sc, sc, sc))];
    W += _text('museum_e_xp_' + a:'id', a:'plaque', 0, [[a:'title', '#F5D77A', true], [a:'sub', '#DDDDDD', false]], 0.32, -1442840576, 'fixed')
  ));
  G = global_M:'guide';
  if (G, (
    W += ['museum_e_guide', 'mannequin', G:'pos',
      str('Rotation:[%.1ff,0f],pose:"standing",immovable:1b,hide_description:1b,Invulnerable:1b,Silent:1b,profile:{model:"wide",texture:"%s"},CustomName:%s,CustomNameVisible:0b',
          G:'yaw', G:'skin', encode_json({'text' -> G:'name', 'color' -> '#F5D77A'}))];
    W += ['museum_e_guide_lbl', 'text_display', [G:'pos':0, G:'pos':1 + 2.15, G:'pos':2],
      str('billboard:"vertical",alignment:"center",line_width:200,shadow:1b,background:1342177280,brightness:{sky:15,block:15},view_range:0.2f,%s,text:%s',
          _tf(0.4, 0.4, 0.4), encode_json(_comp([[G:'name', '#F5D77A', true], ['Click me for a tour', '#DDDDDD', false]])))]
  ));
  W
);

_one(tag, type, at, nbt) -> (
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
  e = spawn(type, at, str('{Tags:["museum","%s"],%s}', tag, nbt));
  if (e, global_ents:tag = query(e, 'uuid'));
  e
);
_dedupe(u) -> (
  e = entity_id(u); if (!e || !query(e, 'has_tag', 'museum'), return());
  t = first(query(e, 'scoreboard_tags'), (_ ~ '^museum_e_') != null);
  if (t == null, return());
  k = global_ents:t;
  if (!k || !entity_id(k), global_ents:t = u,
      k != u, modify(e, 'remove'))
);
_ensure() -> (
  ok = true;
  for (_wanted(), if (!_one(_:0, _:1, _:2, _:3), ok = false));
  ok
);
_in_box(q, b) -> q:0 >= b:'min':0 && q:0 < b:'max':0 + 1 && q:1 >= b:'min':1 - 1 && q:1 < b:'max':1 + 1 && q:2 >= b:'min':2 && q:2 < b:'max':2 + 1;
_someone_near() -> (
  b = global_M:'box'; if (!b, return(false));
  big = {'min' -> b:'min' - [16, 16, 16], 'max' -> b:'max' + [16, 16, 16]};
  first(player('all'), _real(_) && _in_box(pos(_), big)) != null
);
_spin() -> for (global_M:'exhibits' || [], (
  a = _; e = _ent('museum_e_x_' + a:'id');
  if (e, (
    y = ((global_spin:(a:'id') || 0) + 2 * (a:'spin' || 2)) % 360;
    global_spin:(a:'id') = y;
    modify(e, 'yaw', y)
  ))
));

// ───────────── the guide: list → story → teleport ─────────────
_station(n) -> first(global_M:'stations' || [], _:'n' == n);
_cmd_guide() -> (
  p = player(); if (!p, return(0));
  acts = map(global_M:'stations' || [], {'label' -> str('%d · %s', _:'n', _:'title'), 'width' -> 150,
    'action' -> {'type' -> 'run_command', 'command' -> '/museum info ' + _:'n'}});
  d = {'type' -> 'minecraft:multi_action', 'title' -> {'text' -> '🏛 Server history museum', 'color' -> '#F5D77A', 'bold' -> true},
       'body' -> [{'type' -> 'minecraft:plain_message', 'width' -> 300,
                   'contents' -> {'text' -> 'Hi! I am your guide. Every photo here is a real place in the city, in the order it was built. Which one shall I tell you about?', 'color' -> 'white'}}],
       'can_close_with_escape' -> true, 'pause' -> false, 'after_action' -> 'none', 'columns' -> 2, 'actions' -> acts,
       'exit_action' -> {'label' -> 'Thanks, I will look around', 'width' -> 150, 'action' -> {'type' -> 'run_command', 'command' -> '/museum close'}}};
  run(str('dialog show %s %s', p ~ 'name', encode_json(d)));
  1
);
_cmd_info(n) -> (
  p = player(); if (!p, return(0));
  s = _station(n); if (!s, return(0));
  d = {'type' -> 'minecraft:multi_action', 'title' -> {'text' -> str('%d · %s', s:'n', s:'title'), 'color' -> '#F5D77A', 'bold' -> true},
       'body' -> [{'type' -> 'minecraft:plain_message', 'width' -> 300,
                   'contents' -> [{'text' -> s:'date' + '\n', 'color' -> '#F5D77A'}, {'text' -> s:'text', 'color' -> 'white'}]}],
       'can_close_with_escape' -> true, 'pause' -> false, 'after_action' -> 'none', 'columns' -> 2,
       'actions' -> [{'label' -> '✈ Take me there', 'width' -> 150, 'action' -> {'type' -> 'run_command', 'command' -> '/museum go ' + n}},
                     {'label' -> '← All stations', 'width' -> 150, 'action' -> {'type' -> 'run_command', 'command' -> '/museum guide'}}],
       'exit_action' -> {'label' -> 'Close', 'width' -> 120, 'action' -> {'type' -> 'run_command', 'command' -> '/museum close'}}};
  run(str('dialog show %s %s', p ~ 'name', encode_json(d)));
  1
);
// the first spot at or above the entrance with a solid floor and two free blocks (never inside a wall)
_safe(t) -> (
  x = floor(t:0); z = floor(t:2);
  for (range(floor(t:1) - 1, floor(t:1) + 40), (
    y = _;
    if (solid([x, y - 1, z]) && !solid([x, y, z]) && !solid([x, y + 1, z]) && !liquid([x, y, z]) && !liquid([x, y + 1, z]),
      return([t:0 + if (t:0 == x, 0.5, 0), y, t:2 + if (t:2 == z, 0.5, 0)]))
  ));
  t
);
_cmd_go(n) -> (
  p = player(); if (!p, return(0));
  s = _station(n); if (!s, return(0));
  nm = p ~ 'name';
  run('dialog clear ' + nm);
  if (unix_time() - (global_go_cd:nm || 0) < 3000, return(0));
  global_go_cd:nm = unix_time();
  t = s:'tp';
  run(str('forceload add %d %d', floor(t:0), floor(t:2)));
  schedule(2, '_go2', nm, t, s:'title')
);
_go2(nm, t, title) -> (
  p = player(nm); if (!p, return());
  q = _safe(t);
  run(str('tp %s %.2f %.2f %.2f', nm, q:0, q:1, q:2));
  run(str('execute as %s at @s run playsound minecraft:entity.enderman.teleport master @s ~ ~ ~ 0.6 1.2', nm));
  _bar(p, '✦ ' + title + ' · to come back, take the lift to the museum', '#F5D77A');
  schedule(40, _(t) -> run(str('forceload remove %d %d', floor(t:0), floor(t:2))), t)
);
_cmd_close() -> (p = player(); if (p, run('dialog clear ' + p ~ 'name')); 1);

__on_player_interacts_with_entity(p, e, hand) -> (
  if (hand != 'mainhand' || !query(e, 'has_tag', 'museum_e_guide'), return());
  _cmd_guide_for(p)
);
_cmd_guide_for(p) -> run(str('execute as %s run museum guide', p ~ 'name'));

// ───────────── admin / lifecycle ─────────────
_cmd_reset() -> (
  p = player();
  if (!_admin(p), return(if (p, print(p, 'Admins only'), 0)));
  r = reset();
  if (p, print(p, 'museum: ' + r), print(r));
  1
);
_cmd_list() -> (
  p = player(); out = _(t) -> if (p, print(p, t), print(t));
  for (global_M:'stations' || [], call(out, str('%d · %s — %s', _:'n', _:'title', _:'date')));
  1
);
reset() -> (
  _load();
  for (entity_selector('@e[tag=museum]'), modify(_, 'remove'));
  global_ents = {}; global_cool = {};
  if (_ensure(), 'ok', 'partial — completes when someone comes near')
);
_load() -> (
  global_M = read_file('museum', 'json') || {};
  if (type(global_M) != 'map', global_M = {})
);
__on_start() -> (
  _load();
  for (['item_display', 'text_display', 'mannequin'], entity_load_handler(_, _(e, new) -> if (!new, schedule(0, '_dedupe', query(e, 'uuid')))));
  schedule(5, '_ensure_all')
);
_ensure_all() -> if (_someone_near(), _ensure());
__on_tick() -> (
  t = tick_time();
  if (t % 20 == 3, global_active = _someone_near());
  if (!global_active, return());
  if (t % 2 == 0, _spin());
  if (t % 100 == 7, _ensure())
);
status() -> {
  'busy' -> false, 'active' -> global_active, 'stations' -> length(global_M:'stations' || []),
  'ents' -> length(filter(keys(global_ents), entity_id(global_ents:_))), 'wanted' -> length(_wanted())
};
