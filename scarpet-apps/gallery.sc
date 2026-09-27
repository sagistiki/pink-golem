// gallery.sc — an art gallery without client mods: paintings are item_display quads (a 16×16 quad model per picture in
// the resource pack, scaled [w,h,1] on the wall), each with a small plaque; exhibits are spinning item models on plinths;
// sculptures (built from blocks) get a plaque; quiet zones whisper once to whoever walks in.
// Everything is data: gallery.data/art.json (written by the art generator) —
//   paintings[]  {id, model, title, artist, year, pos:[x,y,z] (quad centre, ~0.05 in front of the wall face), face, w, h}
//   exhibits[]   {id, model, pos, scale, spin (deg per tick), title, sub}
//   sculptures[] {id, title, sub?, plaque:[x,y,z], face}
//   quiet_zones[] {name, min, max, msg}
// `face` = the side the VIEWERS stand on: south → yaw 0, east → -90, west → 90, north → 180 (same convention as cinema.sc).
// Commands: /gallery reset (admin: respawn every gallery entity) · /gallery list.  Admin: /script in gallery run status()
// Entities are tagged gallery + gallery_e_<what>: one per tag, guarded, extras removed when they load.

__config() -> {
  'stay_loaded' -> true, 'scope' -> 'global', 'command_permission' -> 'all',
  'commands' -> {'reset' -> '_cmd_reset', 'list' -> '_cmd_list'}
};

global_art = {};          // art.json
global_ents = {};         // unique tag -> uuid
global_cool = {};         // unique tag -> tick_time() before which no new spawn is tried
global_spin = {};         // exhibit id -> current yaw
global_zone_in = {};      // player name -> {zone name -> inside}
global_active = false;    // someone is near the gallery (checked once a second)
global_allow_fake = false;

_real(p) -> p && (global_allow_fake || (p ~ 'player_type') != 'fake') && (p ~ 'dimension') == 'overworld';
_admin(p) -> !p || (p ~ 'permission_level') >= 2;
_ent(tag) -> entity_id(global_ents:tag);
_yaw(face) -> if (face == 'east', -90, face == 'west', 90, face == 'north', 180, 0);
_tf(sx, sy, sz) -> str('transformation:{left_rotation:[0f,0f,0f,1f],right_rotation:[0f,0f,0f,1f],translation:[0f,0f,0f],scale:[%.3ff,%.3ff,%.3ff]}', sx, sy, sz);
_item(model) -> str('item:{id:"minecraft:paper",count:1,components:{"minecraft:item_model":"%s"}}', model);
_in_box(q, mn, mx) -> q:0 >= mn:0 && q:0 < mx:0 + 1 && q:1 >= mn:1 && q:1 < mx:1 + 1 && q:2 >= mn:2 && q:2 < mx:2 + 1;

// everything the gallery owns, as [tag, type, pos, nbt] — computed from art.json each time (cheap, ~30 entries)
_plaque(tag, at, yaw, lines) -> [tag, 'text_display', at,
  str('Rotation:[%.1ff,0f],billboard:"fixed",alignment:"center",line_width:200,shadow:0b,see_through:0b,background:-1442840576,brightness:{sky:15,block:15},%s,text:%s',
      yaw, _tf(0.3, 0.3, 0.3), encode_json(lines))];
_lines(title, sub) -> (
  l = [{'text' -> str('«%s»', title), 'color' -> '#F5D77A', 'bold' -> true}];
  if (sub, l += {'text' -> '\n' + sub, 'color' -> '#DDDDDD'});
  l
);
_wanted() -> (
  W = [];
  for (global_art:'paintings' || [], (
    a = _; yaw = _yaw(a:'face'); q = a:'pos';
    W += ['gallery_e_p_' + a:'id', 'item_display', q, str('Rotation:[%.1ff,0f],brightness:{sky:15,block:15},%s,%s', yaw, _item(a:'model'), _tf(a:'w', a:'h', 1))];
    sub = join(' · ', filter([a:'artist', a:'year'], _));
    W += _plaque('gallery_e_pl_' + a:'id', [q:0, q:1 - a:'h' / 2 - 0.35, q:2], yaw, _lines(a:'title', sub))
  ));
  for (global_art:'exhibits' || [], (
    a = _; q = a:'pos'; sc = a:'scale' || 1;
    W += ['gallery_e_x_' + a:'id', 'item_display', q, str('teleport_duration:2,brightness:{sky:15,block:15},%s,%s', _item(a:'model'), _tf(sc, sc, sc))];
    if (a:'title', (
      pq = a:'plaque' || [q:0, q:1 - 0.45, q:2];
      W += ['gallery_e_xp_' + a:'id', 'text_display', pq,
        str('billboard:"vertical",alignment:"center",line_width:200,background:-1442840576,brightness:{sky:15,block:15},%s,text:%s', _tf(0.3, 0.3, 0.3), encode_json(_lines(a:'title', a:'sub')))]
    ))
  ));
  for (global_art:'sculptures' || [], (
    a = _;
    if (a:'plaque', W += _plaque('gallery_e_s_' + a:'id', a:'plaque', _yaw(a:'face'), _lines(a:'title', a:'sub' || join(' · ', filter([a:'artist', a:'year'], _)))))
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
  e = spawn(type, at, str('{Tags:["gallery","%s"],%s}', tag, nbt));
  if (e, global_ents:tag = query(e, 'uuid'));
  e
);
_dedupe(u) -> (
  e = entity_id(u); if (!e || !query(e, 'has_tag', 'gallery'), return());
  t = first(query(e, 'scoreboard_tags'), (_ ~ '^gallery_e_') != null);
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
_centre() -> (
  W = _wanted(); if (!W, return(null));
  c = [0, 0, 0]; for (W, c = c + _:2);
  c / length(W)
);
_someone_near(r) -> (
  c = _centre(); if (!c, return(false));
  first(player('all'), _real(_) && abs(pos(_):0 - c:0) < r && abs(pos(_):1 - c:1) < r && abs(pos(_):2 - c:2) < r) != null
);

// ───────────── the spinning exhibits ─────────────
_spin() -> for (global_art:'exhibits' || [], (
  a = _; e = _ent('gallery_e_x_' + a:'id');
  if (e, (
    y = ((global_spin:(a:'id') || 0) + 2 * (a:'spin' || 3)) % 360;
    global_spin:(a:'id') = y;
    modify(e, 'yaw', y)
  ))
));

// ───────────── quiet zones ─────────────
_quiet() -> (
  Z = global_art:'quiet_zones' || []; if (!Z, return());
  seen = {};
  for (player('all'), (
    p = _; if (!_real(p), continue());
    n = p ~ 'name'; seen:n = true; q = pos(p);
    st = global_zone_in:n || {};
    for (Z, (
      z = _; inside = _in_box(q, z:'min', z:'max');
      if (inside && !st:(z:'name'), (
        run(str('title %s actionbar %s', n, encode_json({'text' -> z:'msg' || z:'name', 'color' -> '#C8B6FF', 'italic' -> true})));
        run(str('execute as %s at @s run playsound minecraft:item.book.page_turn master @s ~ ~ ~ 0.35 1', n))
      ));
      st:(z:'name') = inside
    ));
    global_zone_in:n = st
  ));
  for (keys(global_zone_in), if (!seen:_, delete(global_zone_in, _)))
);

// ───────────── commands / lifecycle ─────────────
_cmd_reset() -> (
  p = player();
  if (!_admin(p), return(if (p, print(p, 'admins only'), 0)));
  r = reset();
  if (p, print(p, 'gallery: ' + r), print(r));
  1
);
_cmd_list() -> (
  p = player(); out = _(t) -> if (p, print(p, t), print(t));
  for (global_art:'paintings' || [], call(out, str('🖼 %s — «%s» %s %s', _:'id', _:'title', _:'artist' || '', _:'year' || '')));
  for (global_art:'exhibits' || [], call(out, str('◆ %s — %s', _:'id', _:'title' || '')));
  1
);
reset() -> (
  _load();
  for (entity_selector('@e[tag=gallery]'), modify(_, 'remove'));
  global_ents = {}; global_cool = {};
  if (_ensure(), 'ok', 'partial — the gallery is not loaded, it completes when someone comes near')
);
_load() -> (
  global_art = read_file('art', 'json') || {};
  if (type(global_art) != 'map', global_art = {})
);
__on_start() -> (
  _load();
  for (['item_display', 'text_display'], entity_load_handler(_, _(e, new) -> if (!new, schedule(0, '_dedupe', query(e, 'uuid')))));
  schedule(5, '_ensure_all')
);
_ensure_all() -> if (_someone_near(96), _ensure());
__on_tick() -> (
  t = tick_time();
  if (t % 20 == 3, global_active = _someone_near(64));
  if (!global_active, return());
  if (t % 2 == 0, _spin());
  if (t % 10 == 5, _quiet());
  if (t % 100 == 7, _ensure())
);
status() -> {
  'busy' -> false, 'active' -> global_active,
  'paintings' -> length(global_art:'paintings' || []), 'exhibits' -> length(global_art:'exhibits' || []),
  'sculptures' -> length(global_art:'sculptures' || []), 'quiet_zones' -> length(global_art:'quiet_zones' || []),
  'ents' -> length(filter(keys(global_ents), entity_id(global_ents:_))), 'wanted' -> length(_wanted())
};
