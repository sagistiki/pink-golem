// skinpaint.sc — the skin easel + the creators' gallery (Pink Golem character studio).
// Paint a real 64x64 player skin on a wall of pixels (five views: right side | front | left side | back | top of the
// head; base layer + second layer), then "save & wear": Key Bridge 1.3 /skinbake turns it into a PNG, MineSkin signs
// it, SkinRestorer puts it on the player for everyone. Saved skins go to the gallery (3 mannequins, ◀ ▶ pages);
// creators can hide/show/delete their own and always wear them; others may wear a skin if its creator allowed it.
// Pixels = text_displays with the pack font skinpaint:canvas (one glyph per pixel, any 24-bit colour), one display per
// view band, rebuilt only when a band changes. Painting = hold right-click with the brush (a never-ending consumable)
// and aim at the wall (a ray against the plane x = layout.plane_x).
// Data: skinpaint.data/ layout.json + templates.json (gen_skinpaint.py), config.json (places), gallery.json (runtime),
//       canvas.json (what the wall shows), drafts/<player>.json, bake/<id>.json (pixels of every saved skin),
//       keybridge.json (written by Key Bridge 1.3 at start = saving works).
// Commands: /skinpaint palette | tools | color <hex> | shade <lighter|darker> | tool <t> | layer | mirror | undo |
//   templates | template <id> | clear | savemenu | save <show> <pub> <name> | mine | wear <id> | edit <id> |
//   hide <id> | show <id> | delete <id> | deleteyes <id> | done | close | custom
// Admin: /script in skinpaint run status()

__config() -> {
  'stay_loaded' -> true, 'scope' -> 'global', 'command_permission' -> 'all',
  'commands' -> {
    'palette' -> '_cmd_palette', 'tools' -> '_cmd_tools', 'custom' -> '_cmd_custom',
    'color <hex>' -> '_cmd_color', 'shade <how>' -> '_cmd_shade', 'tool <t>' -> '_cmd_tool',
    'layer' -> '_cmd_layer', 'mirror' -> '_cmd_mirror', 'undo' -> '_cmd_undo',
    'templates' -> '_cmd_templates', 'template <id>' -> '_cmd_template', 'clear' -> '_cmd_clear',
    'savemenu' -> '_cmd_savemenu', 'save <show> <pub> <name>' -> '_cmd_save',
    'mine' -> '_cmd_mine', 'wear <id>' -> '_cmd_wear', 'edit <id>' -> '_cmd_edit',
    'hide <id>' -> '_cmd_hide', 'show <id>' -> '_cmd_show', 'delete <id>' -> '_cmd_delete', 'deleteyes <id>' -> '_cmd_deleteyes',
    'done' -> '_cmd_done', 'close' -> '_cmd_close'
  },
  'arguments' -> {
    'hex' -> {'type' -> 'text'}, 'how' -> {'type' -> 'term'}, 't' -> {'type' -> 'term'}, 'id' -> {'type' -> 'term'},
    'show' -> {'type' -> 'term'}, 'pub' -> {'type' -> 'term'}, 'name' -> {'type' -> 'text'}
  }
};

global_L = {};        // layout.json
global_views = [];    // layout views
global_T = {};        // templates.json
global_C = {};        // config.json
global_G = [];        // gallery entries (newest first)
global_img = [];      // the picture on the wall: 4096 ARGB numbers (0 = transparent, second layer only)
global_S = {'who' -> null};   // the painting session
global_dirty = {};    // 'view_band' -> true
global_ents = {};
global_cool = {};
global_pending = {};  // bake id -> {who, name, show, pub, t}
global_page = 0;
global_prev = {};     // button key -> powered at the last check
global_cd = {};       // 'save:<name>' / 'wear:<name>' -> unix_time()
global_kb = false;    // Key Bridge can bake (skinpaint.data/keybridge.json)
global_spin = 0;
global_resume = null;  // the painter before a reload (session.json)
global_resume_t = 0;
global_allow_fake = false;
global_OPAQUE = 4278190080;   // 0xFF000000
global_HEXV = {}; for (split('', '0123456789ABCDEF'), global_HEXV:_ = _i);

// ───────────── helpers ─────────────
_bar(p, text, color) -> run(str('title %s actionbar %s', p ~ 'name', encode_json({'text' -> text, 'color' -> color})));
_admin(p) -> (p ~ 'permission_level') >= 2;
_real(p) -> p && ((p ~ 'player_type') != 'fake' || global_allow_fake);
_d2(a, b) -> (a:0 - b:0) ^ 2 + (a:1 - b:1) ^ 2 + (a:2 - b:2) ^ 2;
_ent(tag) -> entity_id(global_ents:tag);
_today() -> (d = convert_date(unix_time()); str('%02d/%02d/%d', d:2, d:1, d:0));
_nick(p) -> p ~ 'name';
_hex(c) -> str('#%06X', bitwise_and(c, 16777215));
_rgb(c) -> [floor(c / 65536) % 256, floor(c / 256) % 256, c % 256];
_pack(r, g, b) -> floor(r) * 65536 + floor(g) * 256 + floor(b);
_dim(c) -> (q = _rgb(c); _pack((q:0 + 150) / 2, (q:1 + 150) / 2, (q:2 + 150) / 2));
_parse_hex(s) -> (
  s = upper(replace(replace(replace(s, '\\\\', ''), '"', ''), '^\\s*(N:)?#?|\\s+$', ''));
  if ((s ~ '^[0-9A-F]{6}$') == null, return(null));
  v = 0;
  for (split('', s), v = v * 16 + global_HEXV:_);
  v
);
_plain(text, color) -> {'type' -> 'minecraft:plain_message', 'contents' -> {'text' -> text, 'color' -> color}, 'width' -> 300};
_btn(label, cmd, w) -> {'label' -> label, 'width' -> w, 'action' -> {'type' -> 'run_command', 'command' -> cmd}};
_show(p, d) -> run(str('dialog show %s %s', p ~ 'name', encode_json(d)));
_dialog(title, body, actions, cols) -> {
  'type' -> 'minecraft:multi_action',
  'title' -> {'text' -> title, 'color' -> '#FF7AC6', 'bold' -> true},
  'body' -> body, 'can_close_with_escape' -> true, 'pause' -> false, 'after_action' -> 'none', 'columns' -> cols,
  'actions' -> actions,
  'exit_action' -> {'label' -> 'Close', 'width' -> 120, 'action' -> {'type' -> 'run_command', 'command' -> '/skinpaint close'}}
};
_cmd_close() -> (p = player(); if (p, run('dialog clear ' + p ~ 'name')); 1);
_tf(s) -> str('transformation:{left_rotation:[0f,0f,0f,1f],right_rotation:[0f,0f,0f,1f],translation:[0f,0f,0f],scale:[%.4ff,%.4ff,%.4ff]}', s, s, s);

// one entity per tag, spawned only where the chunk is loaded (lesson 26/9: never summon because a selector came back empty)
_one(tag, type, at, nbt) -> (
  e = _ent(tag); if (e, return(e));
  l = entity_selector(str('@e[type=%s,tag=%s]', type, tag));
  if (l, (global_ents:tag = query(l:0, 'uuid'); for (slice(l, 1), modify(_, 'remove')); return(l:0)));
  if (loaded_status(at) < 3 || tick_time() < (global_cool:tag || 0), return(null));
  global_cool:tag = tick_time() + 1200;
  e = spawn(type, at, str('{Tags:["skinpaint","%s"],%s}', tag, nbt));
  if (e, global_ents:tag = query(e, 'uuid'));
  e
);
_text(tag, pos, yaw, text, scale, bg) -> _textx(tag, pos, yaw, text, scale, bg, bg == 0);
_textx(tag, pos, yaw, text, scale, bg, shadow) -> _one(tag, 'text_display', pos,
  str('Rotation:[%.1ff,0f],billboard:"fixed",alignment:"center",line_width:1000,shadow:%s,background:%d,brightness:{sky:15,block:15},view_range:1.0f,%s,text:%s',
      yaw, if (shadow, '1b', '0b'), bg, _tf(scale), encode_json(text)));
_set_text(tag, text) -> (e = _ent(tag); if (e, modify(e, 'nbt_merge', str('{text:%s}', encode_json(text)))));
_mannequin(tag, pos, yaw, name) -> _one(tag, 'mannequin', pos,
  str('Rotation:[%.1ff,0f],pose:"standing",immovable:1b,hide_description:1b,Invulnerable:1b,Silent:1b,profile:{texture:"wardrobe:entity/dummy",model:"wide"},CustomName:%s,CustomNameVisible:0b',
      yaw, encode_json({'text' -> name, 'color' -> '#FF7AC6'})));
// replace a mannequin's whole look: a signed MineSkin texture, or the fitting dummy when e is empty
_dress(tag, entry) -> (
  e = _ent(tag); if (!e, return());
  prof = if (entry, str('{properties:[{name:"textures",value:"%s",signature:"%s"}]}', entry:'value', entry:'sig'),
                    '{texture:"wardrobe:entity/dummy",model:"wide"}');
  run(str('data modify entity %s profile set value %s', query(e, 'uuid'), prof))
);

// ───────────── the canvas ─────────────
_band_of(vw, v) -> (i = 0; for (vw:'bands', if (v >= _:0 && v < _:1, i = _i)); i);
_band_tag(vi, bi) -> str('sp_c_%d_%d', vi, bi);
_cell_col(cell) -> (
  o = global_img:(cell:1);
  if (o != 0, return(_hex(o)));
  b = global_img:(cell:0);
  if (global_S:'who' && global_S:'layer' == 2, _hex(_dim(b)), _hex(b))
);
_band_text(vw, a, b) -> _grid_text(vw, a, b, 0, vw:'w');
_grid_text(vw, a, b, u0, u1) -> (
  px = global_L:'glyphs':'px'; em = global_L:'glyphs':'empty';
  ex = [];
  for (range(a, b), (
    r = _;
    if (r > a, ex += {'text' -> '\n'});
    cur = null; s = '';
    for (range(u0, u1), (
      c = vw:'cells':r:_;
      col = if (c == null, 'X', _cell_col(c));
      if (col != cur, (
        if (cur != null, ex += if (cur == 'X', {'text' -> s}, {'text' -> s, 'color' -> cur}));
        cur = col; s = ''
      ));
      s += if (col == 'X', em, px)
    ));
    if (cur != null, ex += if (cur == 'X', {'text' -> s}, {'text' -> s, 'color' -> cur}))
  ));
  {'text' -> '', 'font' -> 'skinpaint:canvas', 'extra' -> ex}
);
// ── zoom : a window of up to 16 x 10 cells of one view drawn 3x bigger in the
// middle of the canvas area; the normal bands are blanked while it is open, painting maps through the window
global_ZOOM = 3;
_zoom_geom() -> (
  Zw = global_S:'zoom'; P = global_L:'px' * global_ZOOM; vs = global_views; last = vs:(length(vs) - 1);
  zc = (vs:0:'z_left' + last:'z_left' - last:'w' * global_L:'px') / 2;
  H = 32 * global_L:'px';
  {'P' -> P, 'top' -> global_L:'y_top' - (H - Zw:'h' * P) / 2, 'zl' -> zc + Zw:'w' * P / 2}
);
_zoom_draw() -> (
  e = _ent('sp_zoom'); if (!e, return());
  Zw = global_S:'zoom';
  if (!Zw, return(modify(e, 'nbt_merge', '{text:""}')));
  g = _zoom_geom(); s = global_L:'scale' * global_ZOOM;
  modify(e, 'pos', global_L:'plane_x' + 0.004, g:'top' - Zw:'h' * g:'P' + 0.025 * s, g:'zl' - Zw:'w' * g:'P' / 2);
  modify(e, 'nbt_merge', str('{transformation:{left_rotation:[0f,0f,0f,1f],right_rotation:[0f,0f,0f,1f],translation:[0f,0f,0f],scale:[%.4ff,%.4ff,%.4ff]},text:%s}',
    s, s, s, encode_json(_grid_text(global_views:(Zw:'vi'), Zw:'v0', Zw:'v0' + Zw:'h', Zw:'u0', Zw:'u0' + Zw:'w'))))
);
_zoom_set(p, h) -> (
  vw = global_views:(h:0); w = min(16, vw:'w'); hh = min(10, vw:'h');
  global_S:'zoom' = {'vi' -> h:0, 'w' -> w, 'h' -> hh,
                     'u0' -> max(0, min(vw:'w' - w, h:1 - floor(w / 2))), 'v0' -> max(0, min(vw:'h' - hh, h:2 - floor(hh / 2)))};
  global_S:'zoom_pick' = false;
  for (global_views, (vi = _i; for (_:'bands', _set_text(_band_tag(vi, _i), {'text' -> ''}))));
  global_dirty = {}; _zoom_draw(); _ui_refresh();
  _bar(p, '✦ Zoomed 3x — paint as usual. Click the magnifier to go back', '#FF7AC6')
);
_zoom_off() -> (global_S:'zoom' = null; global_S:'zoom_pick' = false; _zoom_draw(); _mark_all(); _ui_refresh());
_band_pos(vw, bd) -> [global_L:'plane_x', global_L:'y_top' - bd:1 * global_L:'px' + global_L:'font_px',
                      vw:'z_left' - vw:'w' * global_L:'px' / 2];
_canvas_ensure() -> for (global_views, (
  vw = _; vi = _i;
  for (vw:'bands', _textx(_band_tag(vi, _i), _band_pos(vw, _), -90, _band_text(vw, _:0, _:1), global_L:'scale', 0, false))
));
_mark_all() -> for (global_views, (vi = _i; for (_:'bands', global_dirty:_band_tag(vi, _i) = true)));
_flush() -> (
  if (!global_dirty, return());
  if (global_S:'zoom', (global_dirty = {}; return(_zoom_draw())));
  for (keys(global_dirty), (
    k = _; parts = split('_', k); vi = number(parts:2); bi = number(parts:3);
    vw = global_views:vi; bd = vw:'bands':bi;
    _set_text(k, _band_text(vw, bd:0, bd:1))
  ));
  global_dirty = {}
);

// ───────────── painting ─────────────
_hit_yz(q) -> (
  if (!q, return(null));
  Zw = global_S:'zoom';
  if (Zw, (
    g = _zoom_geom(); u = floor((g:'zl' - q:1) / g:'P'); v = floor((g:'top' - q:0) / g:'P');
    return(if (u >= 0 && u < Zw:'w' && v >= 0 && v < Zw:'h', [Zw:'vi', Zw:'u0' + u, Zw:'v0' + v], null))
  ));
  P = global_L:'px'; v = floor((global_L:'y_top' - q:0) / P); z = q:1; hit = null;
  for (global_views, (u = floor((_:'z_left' - z) / P); if (u >= 0 && u < _:'w' && v >= 0 && v < _:'h', hit = [_i, u, v])));
  hit
);
_hit(p) -> _hit_yz(_ray(p));
_mirror(h) -> (
  vi = h:0; w = global_views:vi:'w';
  if (vi == 0, [2, 7 - h:1, h:2], vi == 2, [0, 7 - h:1, h:2], [vi, w - 1 - h:1, h:2])
);
_set_cell(vi, u, v, new) -> (
  vw = global_views:vi;
  if (u < 0 || u >= vw:'w' || v < 0 || v >= vw:'h', return());
  cell = vw:'cells':v:u; if (!cell, return());
  // layer 0 = automatic : the second layer where it covers this pixel, else the body
  L = global_S:'layer'; has2 = global_img:(cell:1) != 0;
  if (new == 0 && (L == 1 || (L == 0 && !has2)), return());
  idx = if (L == 1, cell:0, L == 2, cell:1, has2, cell:1, cell:0);
  old = global_img:idx;
  if (old == new, return());
  st = global_S:'stroke'; st += [idx, old]; global_S:'stroke' = st;
  global_img:idx = new; global_S:'unsaved' = true;
  global_dirty:_band_tag(vi, _band_of(vw, v)) = true
);
_dab(h) -> (
  if (global_S:'tool' == 'erase' && global_S:'layer' == 1, return(_hint('The eraser removes only the top layer — on layer 1 paint over it')));
  new = if (global_S:'tool' == 'erase', 0, global_OPAQUE + global_S:'color');
  n = if (global_S:'tool' == 'big', 2, 1);
  targets = [h]; if (global_S:'mirror', targets += _mirror(h));
  for (targets, (t = _; for (range(n), (du = _; for (range(n), _set_cell(t:0, t:1 + du, t:2 + _, new))))))
);
_stroke_to(h) -> (
  l = global_S:'last';
  if (l && l:0 == h:0, (
    du = h:1 - l:1; dv = h:2 - l:2; n = max(abs(du), abs(dv));
    for (range(1, n + 1), _dab([h:0, round(l:1 + du * _ / n), round(l:2 + dv * _ / n)]))
  ), _dab(h));
  global_S:'last' = h
);
_fill(h) -> (
  vw = global_views:(h:0);
  start = vw:'cells':(h:2):(h:1); if (!start, return());
  L = global_S:'layer'; if (L == 0, L = if (global_img:(start:1) != 0, 2, 1));
  key = global_img:(start:(L - 1));
  new = if (global_S:'tool' == 'erase', 0, global_OPAQUE + global_S:'color');
  if (key == new || (L == 1 && new == 0), return());
  keepL = global_S:'layer'; global_S:'layer' = L;
  todo = [[h:1, h:2]]; seen = {}; count = 0;
  while (todo && count < 700, 700, (
    q = todo:(-1); delete(todo, -1);
    k = str('%d,%d', q:0, q:1);
    if (!seen:k, (
      seen:k = true;
      if (q:0 >= 0 && q:0 < vw:'w' && q:1 >= 0 && q:1 < vw:'h', (
        cell = vw:'cells':(q:1):(q:0);
        if (cell && global_img:(cell:(L - 1)) == key, (
          _set_cell(h:0, q:0, q:1, new); count += 1;
          todo += [q:0 + 1, q:1]; todo += [q:0 - 1, q:1]; todo += [q:0, q:1 + 1]; todo += [q:0, q:1 - 1]
        ))
      ))
    ))
  ));
  global_S:'layer' = keepL
);
_pick(p, h) -> (
  cell = global_views:(h:0):'cells':(h:2):(h:1); if (!cell, return());
  o = global_img:(cell:1); c = if (o != 0, o, global_img:(cell:0));
  global_S:'color' = bitwise_and(c, 16777215);
  global_S:'tool' = 'brush';
  _recent(global_S:'color');
  _status();
  _bar(p, str('Eyedropper: %s — back to the brush', _hex(c)), '#FF7AC6')
);
_recent(c) -> (r = [c]; for (global_S:'recent' || [], if (_ != c && length(r) < 8, r += _)); global_S:'recent' = r);
_end_stroke() -> (
  st = global_S:'stroke';
  if (st, (u = global_S:'undo' || []; u += {'pairs' -> st}; if (length(u) > 30, delete(u, 0)); global_S:'undo' = u));
  global_S:'stroke' = []; global_S:'holding' = false; global_S:'last' = null;
  global_S:'changed' = true
);

// ───────────── session: claim / release ─────────────
_kit_item(kind, model, name, anim) -> str('paper[item_model="skinpaint:%s",custom_data={skinpaint_kit:1b,skinpaint:"%s"},max_stack_size=1,custom_name=%s,consumable={consume_seconds:72000,animation:"%s",sound:"minecraft:intentionally_empty",has_consume_particles:false},lore=[{text:"Skin easel · character studio",color:"gray",italic:false}]]',
  model, kind, encode_json({'text' -> name, 'color' -> '#FF7AC6', 'italic' -> false}), anim);
// the brush is FORCED into the last hotbar slot and selected ; whatever was
// there waits in stash/<name>.json and goes back when the easel is released, or at the next join
_stash_file(n) -> 'stash/' + lower(n);
_give_kit(p) -> (
  n = p ~ 'name';
  run(str('clear %s paper[custom_data~{skinpaint_kit:1b}]', n));
  cur = inventory_get(p, 8);
  if (cur && !read_file(_stash_file(n), 'json'),
    write_file(_stash_file(n), 'json', {'id' -> cur:0, 'count' -> cur:1, 'nbt' -> if (cur:2, str(cur:2), null)}));
  inventory_set(p, 8, 0);
  run(str('item replace entity %s hotbar.8 with %s', n, _kit_item('brush', 'brush', 'Brush · right-click the wall', 'brush')));
  modify(p, 'selected_slot', 8)
);
_restore_stash(p) -> (
  n = p ~ 'name'; st = read_file(_stash_file(n), 'json'); if (!st, return());
  slot = if (inventory_get(p, 8) == null, 8, first(range(0, 36), inventory_get(p, _) == null));
  if (slot == null, return(_bar(p, 'The item from your hand is waiting — make room in your inventory', 'yellow')));
  if (st:'nbt', inventory_set(p, slot, st:'count', st:'id', st:'nbt'), inventory_set(p, slot, st:'count', st:'id'));
  delete_file(_stash_file(n), 'json')
);
_kit_of(item) -> (
  if (!item || !item:2, return(null));
  m = str(item:2) ~ 'skinpaint:"(brush|palette|menu)"';
  m
);
_draft_file(n) -> 'drafts/' + lower(n);
_save_draft() -> (
  if (!global_S:'who', return());
  write_file(_draft_file(global_S:'who'), 'json', {'img' -> global_img, 'color' -> global_S:'color'});
  write_file('canvas', 'json', {'img' -> global_img});
  global_S:'changed' = false
);
_claim(p, img) -> (
  n = p ~ 'name';
  if (global_S:'who' && global_S:'who' != n, _release('switch'));
  d = read_file(_draft_file(n), 'json');
  global_img = if (img, img, d && d:'img', d:'img', copy(global_T:'basic':'img'));
  global_S = {'who' -> n, 'layer' -> 0, 'tool' -> 'brush', 'color' -> if (d && d:'color' != null, d:'color', 16730016),
              'mirror' -> false, 'undo' -> [], 'stroke' -> [], 'holding' -> false, 'last' -> null,
              'active' -> unix_time(), 'away' -> 0, 'changed' -> true, 'recent' -> []};
  _give_kit(p);
  _mark_all(); _status(); _ui_refresh();
  run(str('title %s actionbar %s', n, encode_json({'text' -> '✎ The easel is yours! Colours on top, tools on the left — hold right-click with the brush', 'color' -> '#FF7AC6'})));
  run(str('playsound minecraft:block.note_block.chime master %s ~ ~ ~ 0.6 1.4', n));
  _show_preview_of(n)
);
_release(why) -> (
  n = global_S:'who'; if (!n, return());
  _end_stroke(); _save_draft();
  p = player(n);
  if (p, (
    run(str('clear %s paper[custom_data~{skinpaint_kit:1b}]', n));
    _restore_stash(p);
    _bar(p, if (why == 'left_area', 'You left the studio — your painting is in "My skins" and the easel is free',
               why == 'away', 'You walked away from the easel — your painting was kept as a draft',
               why == 'saved', '✦ Skin saved and the easel is free. To paint again, step off the stage and back on',
               'Your painting was kept as a draft ✦ · the easel is free'), '#FF7AC6')
  ));
  global_leave:n = true;          // stepping onto the stage claims the easel again only after stepping off it
  global_S = {'who' -> null}; _zoom_draw();
  _mark_all(); _status(); _ui_refresh()
);
_holder(p) -> global_S:'who' && global_S:'who' == p ~ 'name';
global_leave = {};
_on_stage(p) -> (st = global_C:'stage'; if (!st, return(false)); q = pos(p);
  q:0 >= st:'min':0 && q:0 < st:'max':0 && q:1 >= st:'min':1 && q:1 < st:'max':1 && q:2 >= st:'min':2 && q:2 < st:'max':2);
// every 10 ticks: whoever steps onto the stage gets the easel when it is free
_stage_check() -> (
  if (global_resume && unix_time() - global_resume_t > 15000, global_resume = null);
  if (global_resume && !global_S:'who', (
    rp = player(global_resume);
    if (rp && _on_stage(rp), (global_resume = null; _claim(rp, null)), return())
  ));
  for (player('all'), (
    p = _; n = p ~ 'name';
    if (_real(p) && (p ~ 'dimension') == 'overworld', (
      if (!_on_stage(p), delete(global_leave, n),
        !_holder(p) && !global_leave:n, (
          if (!global_S:'who' || !player(global_S:'who'), _claim(p, null),
            (global_leave:n = true; _bar(p, str('%s is painting now — the easel frees up when they finish', global_S:'who'), '#FF7AC6')))
        ))
    ))
  ))
);
_need_holder(p) -> (
  if (_holder(p), return(true));
  _bar(p, if (global_S:'who', str('%s is painting at the easel now', global_S:'who'), 'Step onto the stage in front of the easel to paint'), '#FF7AC6');
  false
);
_status() -> (
  S = global_S;
  t = if (!S:'who', ['', {'text' -> '✦ Skin easel ✦', 'color' -> '#FF7AC6', 'bold' -> true},
                    {'text' -> '\nThe easel is free', 'color' -> '#6B3A5A'}, {'text' -> '\nStep onto the stage to paint', 'color' -> '#6B3A5A'}],
    ['', {'text' -> '✦ Skin easel ✦', 'color' -> '#FF7AC6', 'bold' -> true},
     {'text' -> '\nPainting: ' + S:'who', 'color' -> '#6B3A5A'},
     {'text' -> str('\n%s · %s%s', {'brush' -> 'Brush', 'big' -> 'Big brush', 'fill' -> 'Fill', 'pick' -> 'Eyedropper', 'erase' -> 'Eraser'}:(S:'tool'),
                   _layer_name(S:'layer'), if (S:'mirror', ' · mirror', '')), 'color' -> '#6B3A5A'}]);
  _set_text('sp_status', t)
);

// ───────────── items: brush / palette / menu ─────────────
__on_player_uses_item(p, item, hand) -> (
  if (hand != 'mainhand', return());
  k = _kit_of(item); if (!k, return());
  if (!_real(p), return());
  if (!_holder(p), (
    if (_d2(pos(p), global_C:'easel_centre') < 196 && (!global_S:'who' || !player(global_S:'who')), (_claim(p, null); return()),
      return(_need_holder(p)))
  ));
  global_S:'active' = unix_time();
  if (k == 'palette', return(_bar(p, 'Pick a colour from the strip above the painting', '#FF7AC6')));
  if (k == 'menu', return(_templates_dialog(p)));
  q = _ray(p);
  ui = _ui_hit(q);
  if (ui, return(_ui_act(p, ui)));
  h = _hit_yz(q);
  if (global_S:'zoom_pick', return(if (h, _zoom_set(p, h), _bar(p, 'Click on the character itself to zoom in', 'yellow'))));
  tool = global_S:'tool';
  if (tool == 'fill', (if (h, (global_S:'stroke' = []; _fill(h); _end_stroke())); return()));
  if (tool == 'pick', (if (h, _pick(p, h)); return()));
  global_S:'stroke' = []; global_S:'last' = null; global_S:'holding' = true;
  if (h, _stroke_to(h))
);
__on_player_releases_item(p, item, hand) -> if (_holder(p) && global_S:'holding', _end_stroke());
__on_player_switches_slot(p, from, to) -> if (_holder(p) && global_S:'holding', _end_stroke());
__on_player_disconnects(p, reason) -> if (_holder(p), (_end_stroke(); _autosave(); _release('left')));
_in_area(p) -> (a = global_C:'area'; if (!a, return(true)); q = pos(p); (p ~ 'dimension') == 'overworld' &&
  q:0 >= a:'min':0 && q:0 < a:'max':0 && q:1 >= a:'min':1 && q:1 < a:'max':1 && q:2 >= a:'min':2 && q:2 < a:'max':2);
__on_player_connects(p) -> schedule(40, '_joined', p ~ 'name');
_joined(n) -> (p = player(n); if (p && !_holder(p), (run(str('clear %s paper[custom_data~{skinpaint_kit:1b}]', n)); _restore_stash(p))));

_paint_tick() -> (
  if (!global_S:'holding', return());
  p = player(global_S:'who');
  if (!p || _kit_of(query(p, 'holds', 'mainhand')) != 'brush', return(_end_stroke()));   // release event ends it normally
  h = _hit(p);
  if (h, _stroke_to(h), global_S:'last' = null);
  global_S:'active' = unix_time()
);

// ───────────── dialogs: palette, tools, templates, save, my skins ─────────────
// ───────────── actions (one function per action: the wall toolbar, the colour strip and the commands all use them) ─────────────
_set_color(p, c) -> (
  if (c == null, return(_bar(p, 'Not a valid colour code — 6 characters 0-9 A-F', 'red')));
  global_S:'color' = c; _recent(c);
  if (global_S:'tool' == 'pick' || global_S:'tool' == 'erase', global_S:'tool' = 'brush');
  _ui_refresh(); _status();
  _bar(p, '■■■ ' + _hex(c), _hex(c))
);
_shade(p, how) -> (
  q = _rgb(global_S:'color');
  _set_color(p, if (how == 'lighter', _pack(q:0 + (255 - q:0) * 0.2, q:1 + (255 - q:1) * 0.2, q:2 + (255 - q:2) * 0.2),
                                       _pack(q:0 * 0.8, q:1 * 0.8, q:2 * 0.8)))
);
_custom_dialog(p) -> (
  d = _dialog('◆ Your own colour ◆', [_plain('Type a 6-character colour code, e.g. FF7AC6', 'white')],
    [{'label' -> 'Set colour', 'width' -> 160, 'action' -> {'type' -> 'dynamic/run_command', 'template' -> '/skinpaint color N:$(hex)'}}], 1);
  d:'inputs' = [{'type' -> 'minecraft:text', 'key' -> 'hex', 'label' -> 'Colour code', 'width' -> 160, 'max_length' -> 7,
                 'initial' -> slice(_hex(global_S:'color'), 1)}];
  _show(p, d)
);
global_TOOLNAME = {'brush' -> 'Brush', 'big' -> 'Big brush (2x2)', 'fill' -> 'Fill — a click fills an area', 'pick' -> 'Eyedropper — a click takes a colour from the painting', 'erase' -> 'Eraser — layer 2 only'};
_set_tool(p, t) -> (
  if (global_TOOLNAME:t == null, return());
  global_S:'tool' = t; _ui_refresh(); _status();
  _bar(p, global_TOOLNAME:t, '#FF7AC6')
);
_toggle_layer(p) -> (
  global_S:'layer' = (global_S:'layer' + 1) % 3; _mark_all(); _ui_refresh(); _status();
  _bar(p, if (global_S:'layer' == 0, 'Layers: automatic — you paint what you see',
              global_S:'layer' == 1, 'Layer 1 only: the body (what is under the hair and clothes)',
              'Layer 2 only: clothes, hair and accessories — the body is shown dimmed'), '#FF7AC6')
);
_layer_name(L) -> if (L == 0, 'automatic', L == 1, 'layer 1', 'layer 2');
global_hint_t = 0;
_hint(text) -> (p = player(global_S:'who'); if (p && unix_time() - global_hint_t > 2500, (global_hint_t = unix_time(); _bar(p, text, 'yellow'))));
_toggle_mirror(p) -> (
  global_S:'mirror' = !global_S:'mirror'; _ui_refresh(); _status();
  _bar(p, if (global_S:'mirror', 'Mirror on — one side also paints the other', 'Mirror off'), '#FF7AC6')
);
_undo(p) -> (
  u = global_S:'undo';
  if (!u, return(_bar(p, 'Nothing to undo', 'white')));
  last = u:(-1); delete(u, -1); global_S:'undo' = u;
  if (last:'full', global_img = last:'full',
    (pr = last:'pairs'; for (range(length(pr) - 1, -1, -1), global_img:(pr:_:0) = pr:_:1)));
  _mark_all(); global_S:'changed' = true; _bar(p, '↶ Undone', 'white')
);
_templates_dialog(p) -> (
  acts = map(keys(global_T), _btn(global_T:_:'name', '/skinpaint template ' + _, 150));
  _show(p, _dialog('◆ Templates ◆', [_plain('Start from a template and change it. ↶ undoes it.', 'white')], acts, 2))
);
_clear_dialog(p) -> _show(p, _dialog('◆ Clear? ◆', [_plain('The painting becomes a blank character. ↶ undoes it.', 'white')],
                                       [_btn('Yes, clear it', '/skinpaint clear', 150)], 1));
_replace_img(img) -> (
  u = global_S:'undo'; u += {'full' -> copy(global_img)}; if (length(u) > 30, delete(u, 0)); global_S:'undo' = u;
  global_img = copy(img); global_S:'changed' = true; global_S:'unsaved' = true; _mark_all()
);
_tools(p) -> _templates_dialog(p);   // the old menu item (kits from before 28/9) now opens the templates

// commands (dialogs send these; the painter must hold the easel)
_cmd_palette() -> (p = player(); if (p && _need_holder(p), _bar(p, 'Pick a colour from the strip above the painting or from the side', '#FF7AC6')); 1);
_cmd_tools() -> 1;
_cmd_custom() -> (p = player(); if (p && _need_holder(p), _custom_dialog(p)); 1);
_cmd_color(hex) -> (p = player(); if (p && _need_holder(p), (run('dialog clear ' + p ~ 'name'); _set_color(p, _parse_hex(hex)))); 1);
_cmd_shade(how) -> (p = player(); if (p && _need_holder(p), _shade(p, how)); 1);
_cmd_tool(t) -> (p = player(); if (p && _need_holder(p), _set_tool(p, t)); 1);
_cmd_layer() -> (p = player(); if (p && _need_holder(p), _toggle_layer(p)); 1);
_cmd_mirror() -> (p = player(); if (p && _need_holder(p), _toggle_mirror(p)); 1);
_cmd_undo() -> (p = player(); if (p && _need_holder(p), _undo(p)); 1);
_cmd_templates() -> (p = player(); if (p && _need_holder(p), _templates_dialog(p)); 1);
_cmd_template(id) -> (
  p = player(); if (!p || !_need_holder(p), return(0));
  t = global_T:id; if (!t, return(0));
  _replace_img(t:'img'); run('dialog clear ' + p ~ 'name'); _bar(p, 'Template: ' + t:'name', '#FF7AC6'); 1
);
_cmd_clear() -> (p = player(); if (p && _need_holder(p), (run('dialog clear ' + p ~ 'name'); _replace_img(global_T:'blank':'img'))); 1);
_cmd_done() -> (p = player(); if (p && _holder(p), (run('dialog clear ' + p ~ 'name'); _release('done'))); 1);

// ───────────── the wall UI: colour strip above the canvas + MS-Paint-like toolbar on its left ─────────────
_ray(p) -> (
  e = pos(p) + [0, p ~ 'eye_height', 0];
  yaw = p ~ 'yaw'; pitch = p ~ 'pitch'; c = cos(pitch);
  d = [-sin(yaw) * c, -sin(pitch), cos(yaw) * c];
  if (d:0 > -0.05, return(null));
  t = (global_L:'plane_x' - e:0) / d:0;
  if (t < 0 || t > 14, return(null));
  [e:1 + t * d:1, e:2 + t * d:2]
);
_grid(g, q) -> [floor((g:'z_left' - q:1) / g:'cell'), floor((g:'y_top' - q:0) / g:'cell')];
_ui_hit(q) -> (
  if (!q || !global_L:'strip', return(null));
  ST = global_L:'strip'; c = _grid(ST, q);
  if (c:0 >= 0 && c:0 < ST:'cols' && c:1 >= 0 && c:1 < ST:'rows', return(['color', ST:'colors':(c:1):(c:0)]));
  TB = global_L:'toolbar'; c = _grid(TB, q); col = c:0; row = c:1;
  if (col < 0 || row < 0 || row > 7 || col > 4, return(null));
  if (col <= 1 && row <= 1, return(['custom']));
  if (col <= 1 && row == 2, return(['shade', if (col == 0, 'lighter', 'darker')]));
  if (col <= 1 && row >= 3 && row <= 6, return(['recent', (row - 3) * 2 + col]));
  t = first(TB:'tools', _:'col' == col && _:'row' == row);
  if (t, [t:'action', t:'tip'], null)
);
_ui_act(p, ui) -> (
  a = ui:0;
  run(str('playsound minecraft:ui.button.click master %s ~ ~ ~ 0.3 1.8', p ~ 'name'));
  if (a == 'color', _set_color(p, _parse_hex(ui:1)),
      a == 'recent', (r = global_S:'recent' || []; if (ui:1 < length(r), _set_color(p, r:(ui:1)))),
      a == 'shade', _shade(p, ui:1),
      a == 'custom', _custom_dialog(p),
      (a ~ '^tool:') != null, _set_tool(p, slice(a, 5)),
      a == 'mirror', _toggle_mirror(p),
      a == 'layer', _toggle_layer(p),
      a == 'undo', _undo(p),
      a == 'templates', _templates_dialog(p),
      a == 'mine', _mine_dialog(p),
      a == 'save', _savemenu(p),
      a == 'done', _release('done'),
      a == 'clear', _clear_dialog(p),
      a == 'zoom', if (global_S:'zoom', (_zoom_off(); _bar(p, 'Back to the full view', '#FF7AC6')),
                     (global_S:'zoom_pick' = true; _ui_refresh(); _bar(p, 'Click the spot in the painting you want to zoom into', '#FF7AC6'))))
);
_cursor(p) -> (
  e = _ent('sp_cursor'); if (!e, return());
  h = if (p, _hit(p), null);
  cell = if (h, global_views:(h:0):'cells':(h:2):(h:1), null);
  n = if (global_S:'tool' == 'big', 2, 1);
  k = if (cell, str('%d_%d_%d_%d_%d_%s_%s', h:0, h:1, h:2, n, global_S:'color', global_S:'tool', global_S:'zoom' != null), '');
  if (k == global_S:'cur', return());
  global_S:'cur' = k;
  if (!cell, (
    modify(e, 'nbt_merge', '{text:""}');
    if (h, _hint('No skin here — only the character is painted'))
  ), (
    Zw = global_S:'zoom';
    if (Zw, (g = _zoom_geom(); P = g:'P'; s = global_L:'scale' * global_ZOOM * n;
             z = g:'zl' - (h:1 - Zw:'u0' + n / 2) * P; y = g:'top' - (h:2 - Zw:'v0' + n) * P + 0.025 * s),
      (P = global_L:'px'; vw = global_views:(h:0); s = global_L:'scale' * n;
       z = vw:'z_left' - (h:1 + n / 2) * P; y = global_L:'y_top' - (h:2 + n) * P + 0.025 * s));
    modify(e, 'pos', global_L:'plane_x' + 0.012, y, z);
    col = if (global_S:'tool' == 'erase', '#FFFFFF', global_S:'tool' == 'pick', '#FFFFFF', _hex(global_S:'color'));
    modify(e, 'nbt_merge', str('{transformation:{left_rotation:[0f,0f,0f,1f],right_rotation:[0f,0f,0f,1f],translation:[0f,0f,0f],scale:[%.4ff,%.4ff,%.4ff]},text:%s}',
      s, s, s, encode_json({'text' -> global_L:'glyphs':'px', 'font' -> 'skinpaint:canvas', 'color' -> col})))
  ))
);
_ui_tip(p) -> (
  q = _ray(p); ui = _ui_hit(q);
  tip = if (!ui, null,
    ui:0 == 'color', ['■■■ ' + ui:1, ui:1],
    ui:0 == 'recent', (r = global_S:'recent' || []; if (ui:1 < length(r), ['Recent colour ■■■', _hex(r:(ui:1))], null)),
    ui:0 == 'shade', [if (ui:1 == 'lighter', 'Lighter', 'Darker'), _hex(_shade_of(ui:1))],
    ui:0 == 'custom', ['Your colour — click: type your own code', _hex(global_S:'color')],
    [ui:1, '#FFE3F1']);
  k = if (tip, tip:0, '');
  if (k != global_S:'tip', (global_S:'tip' = k; if (tip, _bar(p, tip:0, tip:1))))
);
_shade_of(how) -> (q = _rgb(global_S:'color');
  if (how == 'lighter', _pack(q:0 + (255 - q:0) * 0.2, q:1 + (255 - q:1) * 0.2, q:2 + (255 - q:2) * 0.2), _pack(q:0 * 0.8, q:1 * 0.8, q:2 * 0.8)));
_sw(cols) -> if (cols, {'text' -> '', 'font' -> 'skinpaint:canvas', 'extra' -> cols}, {'text' -> ''});   // an empty 'extra' is invalid
_glyphs(hexes) -> map(hexes, if (_ == null, {'text' -> global_L:'glyphs':'empty'}, {'text' -> global_L:'glyphs':'swatch', 'color' -> _}));
_tb_pos(col, row, w, h, s) -> (TB = global_L:'toolbar';   // bottom-centre of a text block covering w x h cells at scale s
  [global_L:'plane_x', TB:'y_top' - (row + h) * TB:'cell' + 0.025 * s, TB:'z_left' - (col + w / 2) * TB:'cell']);
// tool icon tags use '_' instead of ':' (a tag with ':' breaks @e[tag=..] and stops the whole spawn pass)
_ui_ensure() -> (
  ST = global_L:'strip'; TB = global_L:'toolbar'; if (!ST, return());
  ex = [];
  for (ST:'colors', (if (_i > 0, ex += {'text' -> '\n'}); for (_glyphs(_), ex += _)));
  s = ST:'cell' / 0.25;
  _textx('sp_strip', [global_L:'plane_x', ST:'y_top' - ST:'rows' * ST:'cell' + 0.025 * s, ST:'z_left' - ST:'cols' * ST:'cell' / 2],
         -90, _sw(ex), s, 0, false);
  k = TB:'cell' / 0.25;
  _textx('sp_tb_cur', _tb_pos(0, 0, 2, 2, 2 * k), -90, _sw([]), 2 * k, 0, false);
  _textx('sp_tb_shades', _tb_pos(0, 2, 2, 1, k), -90, _sw([]), k, 0, false);
  _textx('sp_tb_recent', _tb_pos(0, 3, 2, 4, k), -90, _sw([]), k, 0, false);
  hs = k * 0.96;
  _textx('sp_tb_sel', _tb_pos(3, 0, 1, 1, hs), -90, _sw([{'text' -> ''}]), hs, 0, false);
  _textx('sp_tb_mir', _tb_pos(3, 0, 1, 1, hs), -90, _sw([]), hs, 0, false);
  _textx('sp_zoom', [global_L:'plane_x' + 0.004, global_L:'y_top', global_L:'views':0:'z_left'], -90, '', global_L:'scale' * global_ZOOM, 0, false);
  _textx('sp_tb_zm', _tb_pos(3, 7, 1, 1, hs), -90, _sw([]), hs, 0, false);
  if (!_ent('sp_cursor'), (_textx('sp_cursor', [global_L:'plane_x' + 0.012, global_L:'y_top', global_L:'views':0:'z_left'], -90, '', global_L:'scale', 0, false);
    e = _ent('sp_cursor'); if (e, modify(e, 'nbt_merge', '{text_opacity:-106b,interpolation_duration:0}'))));
  for (TB:'tools', (
    t = _;
    _one('sp_tbi_' + replace(t:'action', ':', '_'), 'item_display', [global_L:'plane_x' + 0.015, TB:'y_top' - (t:'row' + 0.5) * TB:'cell', TB:'z_left' - (t:'col' + 0.5) * TB:'cell'],
      str('Rotation:[-90f,0f],brightness:{sky:15,block:15},view_range:1.0f,item:{id:"minecraft:paper",count:1,components:{"minecraft:item_model":"skinpaint:tb_%s"}},%s',
          t:'icon', _tf(TB:'cell' * 0.86)))
  ))
);
_ui_refresh() -> (
  TB = global_L:'toolbar'; if (!TB, return());
  S = global_S; on = S:'who' != null;
  c = if (on, _hex(S:'color'), '#DDDDDD');
  _set_text('sp_tb_cur', _sw(_glyphs([c])));
  _set_text('sp_tb_shades', _sw(if (on, _glyphs([_hex(_shade_of('lighter')), _hex(_shade_of('darker'))]), [])));
  r = if (on, S:'recent' || [], []); ex = [];
  for (range(4), (row = _; if (row > 0, ex += {'text' -> '\n'}); for (range(2), (i = row * 2 + _; for (_glyphs([if (i < length(r), _hex(r:i), null)]), ex += _)))));
  _set_text('sp_tb_recent', _sw(ex));
  sel = first(TB:'tools', _:'action' == 'tool:' + (S:'tool' || 'brush'));
  k = TB:'cell' / 0.25 * 0.96;
  e = _ent('sp_tb_sel');
  if (e, (p0 = _tb_pos(sel:'col', sel:'row', 1, 1, k); modify(e, 'pos', p0:0 - 0.005, p0:1 + TB:'cell' * 0.02, p0:2);
          _set_text('sp_tb_sel', _sw([{'text' -> '', 'color' -> if (on, '#FF4FA0', '#E8D0DD')}]))));
  m = first(TB:'tools', _:'action' == 'mirror');
  e = _ent('sp_tb_mir');
  if (e, (p0 = _tb_pos(m:'col', m:'row', 1, 1, k); modify(e, 'pos', p0:0 - 0.005, p0:1 + TB:'cell' * 0.02, p0:2);
          _set_text('sp_tb_mir', _sw(if (on && S:'mirror', [{'text' -> '', 'color' -> '#5BCEFA'}], [])))));
  zt = first(TB:'tools', _:'action' == 'zoom');
  e = _ent('sp_tb_zm');
  if (e && zt, (p0 = _tb_pos(zt:'col', zt:'row', 1, 1, k); modify(e, 'pos', p0:0 - 0.005, p0:1 + TB:'cell' * 0.02, p0:2);
          _set_text('sp_tb_zm', _sw(if (on && (S:'zoom' || S:'zoom_pick'), [{'text' -> global_L:'glyphs':'px', 'color' -> '#FFD23F'}], [])))));
  e = _ent('sp_tbi_layer');
  if (e, modify(e, 'nbt_merge', str('{item:{id:"minecraft:paper",count:1,components:{"minecraft:item_model":"skinpaint:tb_layer%d"}}}', if (on && S:'layer' == 2, 2, 1))))
);


// Key Bridge writes its marker at SERVER_STARTED, after the apps load -> look again whenever someone saves
_kb_ready() -> (if (!global_kb, (kb = read_file('keybridge', 'json'); global_kb = kb != null && kb:'skinbake')); global_kb);
_cmd_savemenu() -> (p = player(); if (p && _need_holder(p), _savemenu(p)); 1);
_savemenu(p) -> (
  _kb_ready();
  if (!global_kb, return(_show(p, _dialog('◆ Saving ◆', [_plain('Saving to a real skin works after the server restarts (Key Bridge 1.3). Your painting is kept as a draft.', 'white')], [], 1))));
  d = _dialog('◆ Save and wear ◆', [_plain('The skin goes on you right away and everyone sees it. It takes a few seconds.', 'white')],
    [{'label' -> {'text' -> '✦ Save', 'color' -> '#FF7AC6', 'bold' -> true}, 'width' -> 200,
      'action' -> {'type' -> 'dynamic/run_command', 'template' -> '/skinpaint save $(show) $(pub) N:$(name)'}}], 1);
  d:'inputs' = [
    {'type' -> 'minecraft:text', 'key' -> 'name', 'label' -> 'Skin name', 'width' -> 220, 'max_length' -> 20, 'initial' -> _nick(p) + '\'s skin'},
    {'type' -> 'minecraft:boolean', 'key' -> 'show', 'label' -> 'Show it in the creators\' gallery', 'initial' -> true},
    {'type' -> 'minecraft:boolean', 'key' -> 'pub', 'label' -> 'Others may wear it too', 'initial' -> true}];
  _show(p, d)
);
_clean_name(s) -> (
  s = replace(replace(s, '\\\\', ''), '"', '');
  if (length(s) >= 2 && slice(s, 0, 2) == 'N:', s = slice(s, 2));
  s = replace(s, '^\\s+|\\s+$', '');
  s = replace(s, '[^\\p{L}0-9 _\\-\'!?.]', '');
  if (length(s) > 20, s = slice(s, 0, 20));
  s
);
_cmd_save(show, pub, name) -> (
  p = player(); if (!p || !_need_holder(p), return(0)); n = p ~ 'name';
  run('dialog clear ' + n);
  if (!_kb_ready(), return(_bar(p, 'Saving works after the server restarts', 'yellow')));
  if (unix_time() - (global_cd:('save:' + n) || 0) < global_C:'save_cooldown_s' * 1000,
    return(_bar(p, 'One moment… you can save once every 30 seconds', 'yellow')));
  if (global_pending, return(_bar(p, 'Another skin is being saved — try again in a few seconds', 'yellow')));
  nm = _clean_name(name); if (length(nm) < 1, nm = 'Skin');
  global_cd:('save:' + n) = unix_time();
  _end_stroke(); _save_draft();
  _bake(n, _nick(p), nm, show == 'true', pub == 'true', true);
  _bar(p, '✦ Saving your skin… (a few seconds)', '#FF7AC6');
  run(str('playsound minecraft:block.amethyst_block.chime master %s ~ ~ ~ 0.8 1.2', n));
  1
);
// the canvas -> a bake file -> Key Bridge /skinbake; wear = put it on the painter when it comes back
_bake(n, nick, nm, show, pub, wear) -> (
  img = copy(global_img);
  for (global_L:'derive', img:(_:0) = img:(_:1));
  for (global_L:'base_texels', if (img:_ == 0, img:_ = global_OPAQUE + 15846821));
  id = str('sk%d', unix_time());
  write_file('bake/' + id, 'json', {'img' -> img, 'variant' -> 'classic', 'name' -> 'pinkgolem ' + id});
  global_pending:id = {'who' -> n, 'nick' -> nick, 'name' -> nm, 'show' -> show, 'pub' -> pub, 'wear' -> wear, 't' -> unix_time()};
  global_S:'unsaved' = false;
  run('skinbake ' + id);
  id
);
// leaving the studio : unsaved work becomes a private skin in "my skins" (not shown, not worn)
_autosave() -> (
  S = global_S;
  if (!S:'who' || !S:'unsaved' || !_kb_ready() || global_pending, return(false));
  d = convert_date(unix_time());
  _bake(S:'who', S:'who', str('Autosave %02d/%02d %02d:%02d', d:2, d:1, d:3, d:4), false, false, false);
  true
);
// called by Key Bridge on the server thread
_baked(id, url, value, sig) -> (
  P = global_pending:id; delete(global_pending, id);
  if (!P, P = {'who' -> '?', 'nick' -> '?', 'name' -> id, 'show' -> false, 'pub' -> false, 'wear' -> false});
  e = {'id' -> id, 'name' -> P:'name', 'by' -> P:'who', 'nick' -> P:'nick', 'date' -> _today(),
       'url' -> url, 'value' -> value, 'sig' -> sig, 'pub' -> P:'pub', 'shown' -> P:'show'};
  ng = [e]; for (global_G, if (_:'id' != id, ng += _)); global_G = ng;
  _save_gallery();
  p = player(P:'who');
  if (p && !P:'wear', _bar(p, str('✦ "%s" is in "My skins" (private) — wear it from your mannequin or the easel', P:'name'), '#FF7AC6'));
  if (p && P:'wear', (
    run(str('skin set web classic %s %s', url, P:'who'));
    _skin_now(P:'who', {'value' -> value, 'sig' -> sig, 'label' -> P:'name'});
    _bar(p, str('✦ "%s" is saved and you\'re wearing it!', P:'name'), '#FF7AC6');
    run(str('playsound minecraft:ui.toast.challenge_complete master %s ~ ~ ~ 0.8 1.2', P:'who'));
    run(str('execute at %s run particle minecraft:end_rod ~ ~1 ~ 0.4 0.9 0.4 0.03 40', P:'who'))
  ));
  if (e:'shown', (
    global_page = 0;
    run('tellraw @a ' + encode_json({'text' -> str('✦ %s painted a new skin: "%s" — in the creators\' gallery', P:'nick', P:'name'), 'color' -> '#FF7AC6'}))
  ));
  _gallery_refresh();
  _show_preview_of(P:'who');
  if (P:'wear' && global_S:'who' == P:'who', _release('saved'))      // done painting = the easel is free again 
);
_bake_failed(id, why) -> (
  P = global_pending:id; delete(global_pending, id);
  if (P && player(P:'who'), _bar(player(P:'who'), 'Saving failed (' + why + ') — try again in a minute', 'red'));
  logger('warn', str('[skinpaint] bake %s failed: %s', id, why))
);

// the skin each player wears now, shared with other apps (the runway show dresses its models with it)
_skin_now(n, rec) -> (m = read_file('skins_now', 'shared_json') || {}; m:lower(n) = rec; write_file('skins_now', 'shared_json', m));

// ───────────── gallery + "my skins" ─────────────
_save_gallery() -> write_file('gallery', 'json', global_G);
_entry(id) -> first(global_G, _:'id' == id);
_mine(p) -> filter(global_G, _:'by' == p ~ 'name');
_shown() -> filter(global_G, _:'shown');
_can_wear(p, e) -> e:'pub' || e:'by' == p ~ 'name' || _admin(p);
_can_edit(p, e) -> e:'by' == p ~ 'name' || _admin(p);
_gallery_refresh() -> (
  G = global_C:'gallery'; l = _shown(); n = length(l);
  pages = max(1, ceil(n / 3)); if (global_page >= pages, global_page = pages - 1); if (global_page < 0, global_page = 0);
  for (range(3), (
    k = global_page * 3 + _;
    e = if (k < n, l:k, null);
    _dress('sp_gal_' + _, e);
    global_gal_ids:_ = if (e, e:'id', null);
    _set_text('sp_gplq_' + _, if (e, ['', {'text' -> e:'name', 'color' -> '#FF7AC6', 'bold' -> true},
                                         {'text' -> '\nby ' + e:'nick', 'color' -> 'white'}],
                                       ['', {'text' -> 'Free spot', 'color' -> 'gray'}, {'text' -> '\nPaint a skin at the easel ✎', 'color' -> 'white'}]))
  ));
  _set_text('sp_gpage', {'text' -> if (n, str('Page %d/%d · %d skins', global_page + 1, pages, n), 'No skins yet — be the first!'), 'color' -> 'white'})
);
global_gal_ids = [null, null, null];
_gallery_dialog(p, e) -> (
  acts = [];
  if (_can_wear(p, e), acts += _btn('✓ Wear it', '/skinpaint wear ' + e:'id', 150));
  acts += _btn('✎ Edit a copy at the easel', '/skinpaint edit ' + e:'id', 150);
  if (_can_edit(p, e), acts += _btn(if (e:'shown', 'Hide from the gallery', 'Show in the gallery'), '/skinpaint ' + if (e:'shown', 'hide ', 'show ') + e:'id', 150));
  if (_can_edit(p, e), acts += _btn('✕ Delete for good', '/skinpaint delete ' + e:'id', 150));
  _show(p, _dialog('◆ ' + e:'name' + ' ◆', [_plain(str('by %s · %s', e:'nick', e:'date'), 'white'),
      _plain(if (e:'pub', 'Anyone may wear it', 'Only its creator may wear it'), 'gray')], acts, 2))
);
_cmd_mine() -> (p = player(); if (p, _mine_dialog(p)); 1);
_mine_dialog(p) -> (
  l = _mine(p);
  if (!l, return(_show(p, _dialog('◆ My skins ◆', [_plain('You haven\'t saved a skin yet. Paint at the easel and press "Save and wear".', 'white')], [], 1))));
  acts = [];
  for (slice(l, 0, min(length(l), 12)), (
    acts += _btn('✓ ' + _:'name', '/skinpaint wear ' + _:'id', 130);
    acts += _btn('✎ Edit', '/skinpaint edit ' + _:'id', 70);
    acts += _btn(if (_:'shown', 'Hide', 'Show'), '/skinpaint ' + if (_:'shown', 'hide ', 'show ') + _:'id', 70);
    acts += _btn('✕', '/skinpaint delete ' + _:'id', 40)
  ));
  _show(p, _dialog('◆ My skins ◆', [_plain('✓ = wear · ✎ = edit a copy at the easel · hide = not in the gallery but still yours', 'white')], acts, 4))
);
_cmd_wear(id) -> (
  p = player(); if (!p, return(0)); n = p ~ 'name'; run('dialog clear ' + n);
  e = _entry(id); if (!e, return(0));
  if (!_can_wear(p, e), return(_bar(p, 'Its creator chose to keep this skin to themselves', '#FF7AC6')));
  if (unix_time() - (global_cd:('wear:' + n) || 0) < global_C:'wear_cooldown_s' * 1000, return(_bar(p, 'One moment… you can change skin once every 10 seconds', 'yellow')));
  global_cd:('wear:' + n) = unix_time();
  run(str('skin set web classic %s %s', e:'url', n));
  _skin_now(n, {'value' -> e:'value', 'sig' -> e:'sig', 'label' -> e:'name'});
  _bar(p, str('✦ You are now "%s"', e:'name'), '#FF7AC6');
  run(str('playsound minecraft:entity.player.levelup master %s ~ ~ ~ 0.5 1.4', n)); 1
);
_cmd_edit(id) -> (
  p = player(); if (!p, return(0)); n = p ~ 'name'; run('dialog clear ' + n);
  f = read_file('bake/' + id, 'json'); if (!f || !f:'img', return(_bar(p, 'I couldn\'t find that painting', 'red')));
  if (global_S:'who' && global_S:'who' != n && player(global_S:'who'), return(_bar(p, str('%s is painting at the easel now — try later', global_S:'who'), '#FF7AC6')));
  if (_holder(p), _replace_img(f:'img'), _claim(p, f:'img'));
  _bar(p, '✎ A copy is on the easel — change it and save under a new name', '#FF7AC6'); 1
);
_set_shown(id, v) -> (
  p = player(); if (!p, return(0)); run('dialog clear ' + p ~ 'name');
  e = _entry(id); if (!e || !_can_edit(p, e), return(0));
  e:'shown' = v; _save_gallery(); _gallery_refresh();
  _bar(p, if (v, 'Shown in the gallery ✦', 'Hidden from the gallery — still yours in "My skins"'), '#FF7AC6'); 1
);
_cmd_hide(id) -> _set_shown(id, false);
_cmd_show(id) -> _set_shown(id, true);
_cmd_delete(id) -> (
  p = player(); if (!p, return(0)); e = _entry(id); if (!e || !_can_edit(p, e), return(0));
  _show(p, _dialog('◆ Delete? ◆', [_plain(str('"%s" will be deleted for good (from your skins too). Whoever wears it now keeps it.', e:'name'), 'white')],
    [_btn('✕ Yes, delete', '/skinpaint deleteyes ' + id, 150)], 1)); 1
);
_cmd_deleteyes(id) -> (
  p = player(); if (!p, return(0)); run('dialog clear ' + p ~ 'name');
  e = _entry(id); if (!e || !_can_edit(p, e), return(0));
  global_G = filter(global_G, _:'id' != id); _save_gallery();
  delete_file('bake/' + id, 'json');
  _gallery_refresh(); _bar(p, 'Deleted', 'white'); 1
);

// ───────────── preview mannequin (your last saved skin) ─────────────
_show_preview_of(n) -> (e = first(global_G, _:'by' == n); _dress('sp_preview', e));

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
_buttons() -> (
  G = global_C:'gallery';
  p = _press(G:'prev_button', 'prev'); if (p, (global_page += -1; _gallery_refresh()));
  p = _press(G:'next_button', 'next'); if (p, (global_page += 1; _gallery_refresh()))
);
__on_player_interacts_with_entity(p, e, hand) -> (
  if (hand != 'mainhand' || !query(e, 'has_tag', 'skinpaint'), return());
  if (query(e, 'has_tag', 'sp_preview'), return(_mine_dialog(p)));
  for (range(3), if (query(e, 'has_tag', 'sp_gal_' + _), (
    id = global_gal_ids:_;
    if (id && _entry(id), _gallery_dialog(p, _entry(id)), _bar(p, 'Free spot — paint a skin at the easel and save it', '#FF7AC6'))
  )))
);

_ensure() -> (
  if (!global_views, return());
  _canvas_ensure();
  C = global_C;
  _textx('sp_status', C:'status', -90, '', 0.45, -855646223, false);   // plum text on a light pink card (0xCCFFE3F1)
  for (global_views, (
    vw = _;
    _text('sp_lbl_' + _i, [global_L:'plane_x', C:'labels_y', vw:'z_left' - vw:'w' * global_L:'px' / 2], -90,
          {'text' -> vw:'name', 'color' -> '#6B3A5A'}, 0.32, 0)
  ));
  _ui_ensure();
  pv = C:'preview';
  if (!_ent('sp_preview') && _mannequin('sp_preview', pv:'pos', pv:'yaw', 'Your skin'), _show_preview_of(global_S:'who'));
  _text('sp_preview_lbl', pv:'label', pv:'yaw', ['', {'text' -> 'Your mannequin', 'color' -> '#FFFFFF', 'bold' -> true},
                                             {'text' -> '\nThe last skin you saved · click = my skins', 'color' -> '#FFE3F1'}], 0.36, 0);
  G = C:'gallery'; spawned = false;
  for (G:'slots', (
    if (!_ent('sp_gal_' + _i) && _mannequin('sp_gal_' + _i, _, 0, 'Creators\' gallery'), spawned = true);
    _text('sp_gplq_' + _i, [_:0, G:'plaque_y', G:'plaque_z'], 0, '', 0.4, 1342177280)
  ));
  _text('sp_gtitle', G:'title', 0, ['', {'text' -> '✦ Creators\' gallery ✦', 'color' -> '#FF7AC6', 'bold' -> true},
                                        {'text' -> '\nSkins painted on this server · click a mannequin to wear it', 'color' -> '#6B3A5A'}], 0.55, 0);
  _text('sp_gpage', G:'page', 0, '', 0.4, 0);
  _text('sp_garr_p', G:'prev_label', 0, {'text' -> '◀', 'color' -> '#FFFFFF'}, 1.0, 0);
  _text('sp_garr_n', G:'next_label', 0, {'text' -> '▶', 'color' -> '#FFFFFF'}, 1.0, 0);
  if (spawned || !global_gal_ready, (global_gal_ready = true; _gallery_refresh(); _status(); _ui_refresh()))
);
global_gal_ready = false;

// ───────────── lifecycle ─────────────
_load() -> (
  global_L = read_file('layout', 'json') || {};
  global_views = global_L:'views' || [];
  global_T = read_file('templates', 'json') || {};
  global_C = read_file('config', 'json') || {};
  global_G = read_file('gallery', 'json') || [];
  ss = read_file('session', 'json'); delete_file('session', 'json');
  // a reload hands the easel back to whoever held it (two people on the stage: the first in the list used to win)
  global_resume = if (ss && unix_time() - ss:'t' < 60000, ss:'who', null); global_resume_t = unix_time();
  kb = read_file('keybridge', 'json');
  global_kb = kb != null && kb:'skinbake';
  c = read_file('canvas', 'json');
  global_img = if (c && c:'img', c:'img', global_T:'basic' && global_T:'basic':'img', copy(global_T:'basic':'img'), []);
  _mark_all()
);
__on_start() -> (_load(); schedule(10, '_ensure'));
__on_tick() -> (
  t = tick_time();
  near = false;
  c = global_C:'easel_centre';
  if (c, for (player('all'), if (_real(_) && _d2(pos(_), c) < 400, near = true)));
  if (t % 2 == 0, (hp = if (global_S:'who', player(global_S:'who'), null);
    _cursor(if (hp && _kit_of(query(hp, 'holds', 'mainhand')) == 'brush', hp, null))));
  if (global_S:'holding', _paint_tick(),
      global_S:'who' && t % 4 == 0, (hp = player(global_S:'who'); if (hp && _kit_of(query(hp, 'holds', 'mainhand')) == 'brush', _ui_tip(hp))));
  if (near && t % 10 == 3, _stage_check());
  if (t % 2 == 0 && global_dirty, _flush());
  if (near && t % 2 == 0, _buttons());
  if (near && t % 2 == 1, (
    e = _ent('sp_preview');
    if (e, (global_spin = (global_spin + 3) % 360; a = global_C:'preview':'yaw' + global_spin;
            modify(e, 'yaw', a); modify(e, 'body_yaw', a); modify(e, 'head_yaw', a)))
  ));
  if (t % 20 == 7, _second());
  if (t % 100 == 41, _ensure())
);
_second() -> (
  S = global_S; now = unix_time();
  for (keys(global_pending), if (now - global_pending:_:'t' > 120000, _bake_failed(_, 'timeout')));
  if (!S:'who', return());
  p = player(S:'who');
  if (!p, (_autosave(); return(_release('left'))));
  if (!_in_area(p), (_end_stroke(); _autosave(); return(_release('left_area'))));
  S:'away' = if (_on_stage(p), 0, S:'away' + 1);
  if (S:'away' > global_C:'away_release_s', return(_release('away')));
  if (now - S:'active' > global_C:'idle_release_s' * 1000, return(_release('idle')));
  if (S:'changed' && now % 30000 < 1000, _save_draft())
);
__on_close() -> if (global_S:'who', (_save_draft(); write_file('session', 'json', {'who' -> global_S:'who', 't' -> unix_time()})));

status() -> {
  'busy' -> global_S:'who' != null,
  'painter' -> global_S:'who',
  'can_bake' -> global_kb,
  'pending' -> keys(global_pending),
  'gallery' -> length(global_G),
  'ents' -> length(filter(keys(global_ents), entity_id(global_ents:_)))
};
