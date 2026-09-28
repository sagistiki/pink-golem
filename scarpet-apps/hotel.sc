// hotel.sc — a boutique hotel floor: a receptionist mannequin you click for a check-in dialog
// (one free suite = one button), a plaque beside every suite door ("<name>" + free/taken, never the guest's name), and
// iron doors that open by themselves for the guest who booked the room (or for anyone already inside — nobody is
// ever locked in) and stay shut for everyone else, with a rate-limited hint at the door for non-guests.
// Everything numeric is data: hotel.data/hotel.json (rooms, doors, boxes, spawns, plaques — written by your build
// generator) and hotel.data/guests.json (persisted booking state: {name:{room,since,seen}}, app-owned).
// Commands: /hotel menu · /hotel checkout · /hotel reset (admin: respawn entities) · /hotel free <room> (admin).
// Admin: /script in hotel run status()
// Entities are tagged hotel, hotel_e_npc, hotel_e_plaque_<id>: one per tag, guarded (never summon because a selector
// came back empty — the chunk may simply not have its entities loaded yet), extras removed when they load.

__config() -> {
  'stay_loaded' -> true, 'scope' -> 'global', 'command_permission' -> 'all',
  'commands' -> {
    'menu' -> '_cmd_menu',
    'checkin <room>' -> '_cmd_checkin',
    'checkout' -> '_cmd_checkout',
    'reset' -> '_cmd_reset',
    'free <room>' -> '_cmd_free',
    'guests' -> '_cmd_guests',
    'close' -> '_cmd_close'
  },
  'arguments' -> {'room' -> {'type' -> 'term'}}
};

global_h = {};            // hotel.json
global_guests = {};       // guests.json: player name -> {room, since, seen}
global_ents = {};         // unique tag -> uuid of the one entity carrying it
global_cool = {};         // unique tag -> tick_time() before which no new spawn is tried
global_door_open = {};    // room id -> is its door open right now
global_hint_cd = {};      // player name -> unix_time() of the last "occupied/check in" hint we showed them
global_welcomed = {};     // player name -> {room id -> already got the "welcome" this session}
global_allow_fake = false; // true only during tests (minecraft_playtest sets it) — builder bots are fake players too

// ───────────── small helpers ─────────────
_real(p) -> p && (global_allow_fake || (p ~ 'player_type') != 'fake') && (p ~ 'dimension') == 'overworld';
_admin(p) -> !p || (p ~ 'permission_level') >= 2;
_bar(p, text, color) -> run(str('title %s actionbar %s', p ~ 'name', encode_json({'text' -> text, 'color' -> color})));
_ent(tag) -> entity_id(global_ents:tag);
_room(id) -> first(global_h:'rooms', _:'id' == id);
_guest_of(id) -> first(keys(global_guests), global_guests:_:'room' == id);
_room_of_player(p) -> (g = global_guests:(p ~ 'name'); if (g, g:'room', null));
_dist(a, b) -> sqrt(reduce(a - b, _a + _ * _, 0));
_door_lo(r) -> r:'door';
_door_hi(r) -> [r:'door':0, r:'door':1 + 1, r:'door':2];
_door_centre(r) -> [r:'door':0 + 0.5, r:'door':1 + 0.5, r:'door':2 + 0.5];
_in_box(q, b) -> q:0 >= b:'min':0 && q:0 < b:'max':0 + 1 && q:1 >= b:'min':1 - 0.5 && q:1 < b:'max':1 + 1.5 && q:2 >= b:'min':2 && q:2 < b:'max':2 + 1;

// ───────────── one entity per tag ─────────────
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
  e = spawn(type, at, str('{Tags:["hotel","%s"],%s}', tag, nbt));
  if (e, global_ents:tag = query(e, 'uuid'));
  e
);
_dedupe(u) -> (
  e = entity_id(u); if (!e || !query(e, 'has_tag', 'hotel'), return());
  t = first(query(e, 'scoreboard_tags'), (_ ~ '^hotel_e_') != null);
  if (t == null, return());
  k = global_ents:t;
  if (!k || !entity_id(k), global_ents:t = u,
      k != u, modify(e, 'remove'))
);
_tf(sx, sy, sz) -> str('transformation:{left_rotation:[0f,0f,0f,1f],right_rotation:[0f,0f,0f,1f],translation:[0f,0f,0f],scale:[%.3ff,%.3ff,%.3ff]}', sx, sy, sz);

// spawns the receptionist + all plaques; returns true when everything stands
_ensure() -> (
  ok = true;
  n = global_h:'reception':'npc';
  if (n && !_one('hotel_e_npc', 'mannequin', n:'pos',
        str('Rotation:[%.1ff,0f],pose:"standing",immovable:1b,hide_description:1b,Invulnerable:1b,Silent:1b,profile:{model:"wide",texture:"%s"},CustomName:%s,CustomNameVisible:0b',
            n:'yaw' || 0, n:'skin', encode_json(n:'name'))), ok = false);
  for (global_h:'rooms', (
    r = _;
    pl = r:'plaque';
    if (pl && !_one('hotel_e_plaque_' + r:'id', 'text_display', pl:'pos',
          str('Rotation:[%.1ff,0f],billboard:"fixed",alignment:"center",line_width:200,shadow:1b,see_through:0b,background:1342177280,brightness:{sky:15,block:15},%s,text:""',
              pl:'yaw', _tf(0.55, 0.55, 0.55))), ok = false)
  ));
  if (ok, for (global_h:'rooms', _plaque_update(_)));
  ok
);

// ───────────── plaques ─────────────
_plaque_update(r) -> (
  e = _ent('hotel_e_plaque_' + r:'id'); if (!e, return());
  busy = _guest_of(r:'id') != null;
  lines = [{'text' -> r:'name', 'color' -> '#E8A33D', 'bold' -> true}, {'text' -> '\n'},
           {'text' -> if (busy, 'taken', 'free'), 'color' -> if (busy, '#FF9AA2', 'green')}];
  modify(e, 'nbt_merge', str('{text:%s}', encode_json(lines)))
);

// ───────────── doors: never trap anyone (SPEC's safety valve, cinema/lobby style) ─────────────
// preserves facing/hinge/half by reading the live block state back off block() and overriding only 'open';
// verified live: `set(pos, block(pos), 'open', str(bool))` keeps every other property (facing, hinge, half, powered).
// a door is switched with plain setblock on BOTH halves (the earlier without_updates + set() of each half
// left some doors as air). Vanilla keeps the halves in sync; a missing door is simply rebuilt from hotel.json's facing.
_toggle_door(r, open) -> (
  lo = _door_lo(r); hi = _door_hi(r);
  if (loaded_status(lo) < 3, return());
  f = r:'facing' || 'south'; o = if (open, 'true', 'false');
  run(str('setblock %d %d %d iron_door[facing=%s,hinge=left,half=lower,open=%s]', lo:0, lo:1, lo:2, f, o));
  run(str('setblock %d %d %d iron_door[facing=%s,hinge=left,half=upper,open=%s]', hi:0, hi:1, hi:2, f, o));
  run(str('playsound minecraft:block.iron_door.%s master @a %.1f %.1f %.1f 0.8 %.1f',
          if (open, 'open', 'close'), lo:0, lo:1, lo:2, if (open, 1.2, 1.4)));
  global_door_open:(r:'id') = open
);

_doors_poll() -> (
  for (global_h:'rooms', (
    r = _; id = r:'id';
    gname = _guest_of(id);
    centre = _door_centre(r);
    gp = if (gname, player(gname), null);
    guest_near = gp != null && _real(gp) && _dist(pos(gp), centre) <= 2.5;
    // inside the suite the door stays shut unless you walk up to it — anyone inside who comes within 2.5
    // blocks of the door gets it opened (so nobody is ever locked in), the rest of the room is private
    inside_near = first(player('all'), _real(_) && _in_box(pos(_), r:'box') && _dist(pos(_), centre) <= 2.5) != null;
    open = guest_near || inside_near;
    if (open != (global_door_open:id == true), _toggle_door(r, open));
    for (player('all'), (
      p = _;
      if (_real(p), (
        n = p ~ 'name';
        d = _dist(pos(p), centre);
        if (d <= 1.5 && n != gname, (
          last = global_hint_cd:n;
          if (!last || unix_time() - last > 4000, (
            global_hint_cd:n = unix_time();
            _bar(p, if (gname, 'This suite is taken', 'Check in at the reception'), if (gname, '#FF9AA2', 'yellow'))
          ))
        ));
        if (n == gname && _in_box(pos(p), r:'box'), (
          if (!global_welcomed:n, global_welcomed:n = {});
          if (!global_welcomed:n:id, (
            global_welcomed:n:id = true;
            _bar(p, 'Welcome to ' + r:'name' + ' ✦', 'gold')
          ))
        ))
      ))
    ))
  ))
);

_touch_seen() -> for (player('all'), if (_real(_), (
  n = _ ~ 'name'; g = global_guests:n; if (g, g:'seen' = unix_time())
)));

// ───────────── check-in / check-out ─────────────
_save_guests() -> write_file('guests', 'json', global_guests);
_checkin(p, id) -> (
  n = p ~ 'name'; r = _room(id);
  global_guests:n = {'room' -> id, 'since' -> unix_time(), 'seen' -> unix_time()};
  _save_guests();
  _plaque_update(r);
  _bar(p, r:'name' + ' is yours ✦', 'gold');
  run(str('playsound minecraft:block.note_block.bell master %s ~ ~ ~ 1 1', n));
  print(p, str('%s is yours. The suites are up the stairs', r:'name'));
  1
);
_do_checkout(name) -> (
  g = global_guests:name; if (!g, return(false));
  id = g:'room';
  delete(global_guests, name);
  _save_guests();
  r = _room(id);
  if (r, (
    _plaque_update(r);
    if (global_door_open:id, _toggle_door(r, false))
  ));
  if (global_welcomed:name, delete(global_welcomed, name));
  q = player(name); if (q, _fix_spawn(q, true));
  true
);
_auto_checkout() -> (
  days = global_h:'checkout_days'; if (!days, return());
  cutoff = unix_time() - days * 86400000;
  for (keys(global_guests), if (global_guests:_:'seen' < cutoff, _do_checkout(_)))
);

// ───────────── the reception dialog ─────────────
_dialog(title, body, actions, columns) -> ({
  'type' -> 'minecraft:multi_action', 'title' -> title,
  'body' -> [{'type' -> 'minecraft:plain_message', 'contents' -> body, 'width' -> 320}],
  'can_close_with_escape' -> true, 'pause' -> false, 'after_action' -> 'none', 'columns' -> columns,
  'actions' -> actions,
  'exit_action' -> {'label' -> 'Close', 'width' -> 120, 'action' -> {'type' -> 'run_command', 'command' -> '/hotel close'}}
});
_btn(label, cmd) -> ({'label' -> label, 'width' -> 220, 'action' -> {'type' -> 'run_command', 'command' -> cmd}});
_menu(p) -> (
  id = _room_of_player(p); acts = [];
  if (id != null, (
    r = _room(id); sp = r:'spawn';
    body = str('Your suite: %s · its door opens only for you', r:'name');
    acts += _btn('Make it my respawn point', str('spawnpoint %s %.1f %.1f %.1f', p ~ 'name', sp:0, sp:1, sp:2));
    acts += _btn('Check out', '/hotel checkout')
  ), (
    free = filter(global_h:'rooms', _guest_of(_:'id') == null);
    if (free, (
      body = str('Welcome! %d of %d suites are free', length(free), length(global_h:'rooms'));
      for (free, acts += _btn('✦ ' + _:'name', '/hotel checkin ' + _:'id'))
    ), body = 'The hotel is full right now')
  ));
  if (_admin(p), acts += _btn('Guest list', '/hotel guests'));
  run(str('dialog show %s %s', p ~ 'name', encode_json(_dialog('◆ ' + global_h:'name' + ' ◆', body, acts, 1))))
);

// ───────────── clicks: the receptionist opens the menu ─────────────
__on_player_interacts_with_entity(p, e, hand) -> (
  if (hand != 'mainhand' || !_real(p) || !query(e, 'has_tag', 'hotel'), return());
  if (query(e, 'has_tag', 'hotel_e_npc'), _menu(p))
);

// ───────────── commands ─────────────
_cmd_menu() -> (p = player(); if (p && _real(p), _menu(p)); 1);
_cmd_checkin(room) -> (
  p = player(); if (!p, return(0));
  run('dialog clear ' + p ~ 'name');
  id = number(room); r = _room(id);
  if (!r, return(_bar(p, 'No such room', 'red')));
  if (_room_of_player(p) != null, return(_bar(p, 'You already have a suite', 'yellow')));
  if (_guest_of(id) != null, return(_bar(p, 'Someone just took that suite', 'red')));
  _checkin(p, id)
);
_cmd_checkout() -> (
  p = player(); if (!p, return(0));
  run('dialog clear ' + p ~ 'name');
  n = p ~ 'name';
  if (!global_guests:n, return(_bar(p, 'You have no suite', 'yellow')));
  _do_checkout(n);
  _bar(p, 'Checked out. Thanks for staying!', 'gray');
  1
);
_cmd_reset() -> (
  p = player();
  if (!_admin(p), return(_bar(p, 'Admins only', 'red')));
  reset();
  if (p, _bar(p, 'Hotel entities respawned', 'gray'), print('reset'));
  1
);
_cmd_free(room) -> (
  p = player();
  if (!_admin(p), return(_bar(p, 'Admins only', 'red')));
  id = number(room); r = _room(id);
  if (!r, return(_bar(p, 'No such room', 'red')));
  name = _guest_of(id);
  if (name, _do_checkout(name));
  _bar(p, r:'name' + ' is free now', 'gray');
  1
);
_cmd_guests() -> (
  p = player();
  if (!_admin(p), return(_bar(p, 'Admins only', 'red')));
  if (p, run('dialog clear ' + p ~ 'name'));
  body = if (!global_guests, 'No guests right now', join('\n', map(keys(global_guests), (
    n = _; g = global_guests:n; r = _room(g:'room'); d = convert_date(g:'since');
    str('%s · %s · since %02d/%02d %02d:%02d', n, if (r, r:'name', g:'room'), d:2, d:1, d:3, d:4)
  ))));
  if (p, run(str('dialog show %s %s', p ~ 'name', encode_json(_dialog('◆ Guests ◆', body, [], 1)))), print(body));
  1
);
_cmd_close() -> (p = player(); if (p, run('dialog clear ' + p ~ 'name')); 1);

// kill + respawn every hotel entity
reset() -> (
  for (entity_selector('@e[tag=hotel]'), modify(_, 'remove'));
  global_ents = {}; global_cool = {};
  _ensure()
);

// ───────────── lifecycle ─────────────
_load() -> (
  global_h = read_file('hotel', 'json') || {};
  delete(global_h, '_doc');
  global_guests = read_file('guests', 'json') || {}
);
__on_start() -> (
  _load();
  global_door_open = {}; global_welcomed = {}; global_hint_cd = {};
  for (['text_display', 'mannequin'], entity_load_handler(_, _(e, new) -> if (!new, schedule(0, '_dedupe', query(e, 'uuid')))));
  schedule(5, '_ensure');
  schedule(100, '_auto_checkout');
  schedule(20, '_checkout_offline')     // rooms held by players who left before this rule existed
);
__on_player_connects(p) -> (delete(global_welcomed, p ~ 'name'); schedule(40, '_fix_spawn_n', p ~ 'name'));
_fix_spawn_n(n) -> (p = player(n); if (p, _fix_spawn(p, true)));
// leaving the server checks you out — a suite is only yours while you're online
__on_player_disconnects(p, reason) -> (_do_checkout(p ~ 'name'); _fix_spawn(p, false));
// a respawn point inside a suite that isn't yours (any more) moves to the hotel lobby — someone else may have it now
_fix_spawn(p, tell) -> (
  sp = query(p, 'spawn_point'); if (!sp, return());
  q = sp:0; r = first(global_h:'rooms', _in_box([q:0 + 0.5, q:1, q:2 + 0.5], _:'box'));
  if (r == null || _room_of_player(p) == r:'id', return());
  L = global_h:'lobby_spawn'; if (!L, return());
  run(str('spawnpoint %s %d %d %d', p ~ 'name', L:0, L:1, L:2));
  if (tell, print(p, format('#E8A33D ✦ ', 'w Your respawn point moved to the hotel lobby: that suite is not yours any more')))
);
_checkout_offline() -> for (keys(global_guests), if (!player(_), _do_checkout(_)));
__on_tick() -> (
  t = tick_time();
  if (t % 4 == 0, _doors_poll());
  if (t % 20 == 0, _touch_seen());
  if (t % 100 == 7, _ensure());
  if (t % 24000 == 100, _auto_checkout())
);

status() -> (
  rooms = {};
  for (global_h:'rooms', id = _:'id'; rooms:id = {'guest' -> _guest_of(id), 'open' -> (global_door_open:id == true)});
  {'busy' -> false, 'rooms' -> rooms, 'ents' -> length(filter(keys(global_ents), entity_id(global_ents:_)))}
);
