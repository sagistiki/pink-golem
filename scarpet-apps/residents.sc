// residents.sc — onboarding without client mods: new players stay in the lobby until they register (a dialog with a
// nickname box + the rules + an "I agree" checkbox), held there by an INVISIBLE barrier (a position check that puts them
// back inside with a message — works however they got out). Registered regular players get one fixed role look (a
// scoreboard team colour, no symbol, adventure mode); ops, bots and exempt names are never held. Plus a character studio:
// skin mannequins (SkinRestorer web skins by textures.minecraft.net address), a wardrobe of outfits, a fitting wall
// (a mannequin wears real clothes from resourcepacks/wardrobe: pick each piece with buttons, then put the look on), a
// clerk who resets your look, and a resident card item.
// Status = the scoreboard tag `resident`, so any app can check `query(p, 'has_tag', 'resident')`.
// Data: residents.data/config.json (lobby box, role, exempt, rules, seed), studio.json (entities, skins, outfits,
// fitting wall), wardrobe.json (the clothes catalogue, written by resourcepacks/wardrobe/gen_wardrobe_pack.py),
// registry.json (runtime: name -> {nick, n, joined, role}, plus _next), fitting.json (runtime: the wall's selection).
// Commands: /residents menu | register <agree> <nick> | card | skin <id> | skinreset | resetlook | outfit <id> | fitwear | close
//           /residents admin list | info <name> | unregister <name> | setnick <name> <nick> | reset   (ops)
// Admin: /script in residents run status()

__config() -> {
  'stay_loaded' -> true, 'scope' -> 'global', 'command_permission' -> 'all',
  'commands' -> {
    'menu' -> '_cmd_menu',
    'register <agree> <nick>' -> '_cmd_register',
    'card' -> '_cmd_card',
    'skin <id>' -> '_cmd_skin',
    'skinreset' -> '_cmd_skinreset',
    'resetlook' -> '_cmd_resetlook',
    'resetlookyes' -> '_cmd_resetlookyes',
    'outfit <id>' -> '_cmd_outfit',
    'fitwear' -> '_cmd_fitwear',
    'close' -> '_cmd_close',
    'admin list' -> '_adm_list',
    'admin info <name>' -> '_adm_info',
    'admin unregister <name>' -> '_adm_unregister',
    'admin setnick <name> <nick>' -> '_adm_setnick',
    'admin reset' -> '_adm_reset'
  },
  'arguments' -> {
    'agree' -> {'type' -> 'term'},
    'nick' -> {'type' -> 'text'},
    'id' -> {'type' -> 'term'},
    'name' -> {'type' -> 'term'}
  }
};

global_cfg = {};          // config.json
global_studio = {};       // studio.json
global_reg = {};          // registry.json
global_ents = {};         // unique tag -> uuid of the one entity carrying it
global_cool = {};         // unique tag -> tick before which no new spawn is tried
global_msg = {};          // player name -> unix_time() of the last barrier chat line
global_bar = {};          // player name -> unix_time() of the last barrier actionbar
global_skin_cd = {};      // player name -> unix_time() of the last skin change
global_wd = {};           // wardrobe.json (fitting wall catalogue)
global_fit = {'sel' -> {}, 'ang' -> 0, 'hold' -> 0};   // row key -> item index; dummy turn angle; hold-until tick
global_fit_btns = [];     // [key, [x,y,z], action, row key]
global_fit_prev = {};     // button key -> powered at the last check
global_allow_fake = false; // true only during tests (minecraft_playtest) — builder bots are fake players too

// ───────────── helpers ─────────────
_bar(p, text, color) -> run(str('title %s actionbar %s', p ~ 'name', encode_json({'text' -> text, 'color' -> color})));
_admin(p) -> (p ~ 'permission_level') >= 2;
_ent(tag) -> entity_id(global_ents:tag);
_tf(sx, sy, sz) -> str('transformation:{left_rotation:[0f,0f,0f,1f],right_rotation:[0f,0f,0f,1f],translation:[0f,0f,0f],scale:[%.3ff,%.3ff,%.3ff]}', sx, sy, sz);
_save() -> write_file('registry', 'json', global_reg);
_today() -> (d = convert_date(unix_time()); str('%02d/%02d/%d', d:2, d:1, d:0));
_resident(p) -> query(p, 'has_tag', 'resident');

// never held: fake players (unless testing), exempt names / patterns, ops
_exempt(p) -> (
  if ((p ~ 'player_type') == 'fake', return(!global_allow_fake));
  n = p ~ 'name';
  if (first(global_cfg:'exempt_names', _ == n) != null, return(true));
  if (first(global_cfg:'exempt_patterns', (n ~ _) != null) != null, return(true));
  _admin(p)
);

// ───────────── status sync: tag + (on join) the role's team and game mode ─────────────
_sync(p, full) -> (
  n = p ~ 'name';
  if (_exempt(p), (if (!_resident(p), modify(p, 'tag', 'resident')); return()));
  e = global_reg:n;
  if (e, (
    if (!_resident(p), modify(p, 'tag', 'resident'));
    if (full && e:'role' == global_cfg:'role':'name', (
      t = global_cfg:'role':'team';
      if ((p ~ 'team') != t, run(str('team join %s %s', t, n)));
      if ((p ~ 'gamemode') != 'adventure', run(str('gamemode adventure %s', n)))
    ))
  ), (
    if (_resident(p), modify(p, 'clear_tag', 'resident'))
  ))
);
_sync_all(full) -> for (player('all'), _sync(_, full));
_welcome(p) -> (
  n = p ~ 'name';
  run(str('title %s title %s', n, encode_json({'text' -> 'Welcome!', 'color' -> '#FF7AC6', 'bold' -> true})));
  run(str('title %s subtitle %s', n, encode_json({'text' -> 'Register at the reception to enter the city', 'color' -> 'white'})));
  print(p, format('#FF7AC6 ✦ Welcome to the server! ', 'w To leave the lobby, register first: /residents menu (or talk to the receptionist).'))
);

// ───────────── the invisible barrier ─────────────
_barrier() -> (
  L = global_cfg:'lobby'; mn = L:'min'; mx = L:'max';
  for (player('all'), (
    p = _;
    if (!_resident(p) && !_exempt(p) && (p ~ 'dimension') == 'overworld', (
      q = pos(p);
      inside = q:0 >= mn:0 && q:0 < mx:0 + 1 && q:2 >= mn:2 && q:2 < mx:2 + 1 && q:1 >= mn:1 && q:1 < mx:1 + 1;
      if (!inside, (
        n = p ~ 'name';
        if (query(p, 'mount'), run('ride ' + n + ' dismount'));
        if (q:1 < mn:1 || q:1 >= mx:1 + 1, (
          r = L:'return';
          modify(p, 'location', r:0, r:1, r:2, L:'yaw', 0)
        ), (
          modify(p, 'pos', max(mn:0 + 0.35, min(mx:0 + 0.65, q:0)), q:1, max(mn:2 + 0.35, min(mx:2 + 0.65, q:2)))
        ));
        modify(p, 'motion', 0, 0, 0);
        now = unix_time();
        if (now - (global_bar:n || 0) > 800, (
          global_bar:n = now;
          _bar(p, '✦ Register to leave the lobby · /residents menu', '#FF7AC6');
          run(str('playsound minecraft:block.note_block.bass master %s ~ ~ ~ 0.6 0.8', n))
        ));
        if (now - (global_msg:n || 0) > 30000, (
          global_msg:n = now;
          _menu(p, null); print(p, format('#FF7AC6 ✦ ', 'w You are not registered yet: type /residents menu (or right-click the receptionist), then the whole city is open.'))
        ))
      ))
    ))
  ))
);

// ───────────── registration dialog ─────────────
_plain(text, color) -> {'type' -> 'minecraft:plain_message', 'contents' -> {'text' -> text, 'color' -> color}, 'width' -> 300};
_btn(label, cmd) -> {'label' -> label, 'width' -> 220, 'action' -> {'type' -> 'run_command', 'command' -> cmd}};
_show(p, d) -> run(str('dialog show %s %s', p ~ 'name', encode_json(d)));
_dialog(title, body, actions) -> {
  'type' -> 'minecraft:multi_action',
  'title' -> {'text' -> title, 'color' -> '#FF7AC6', 'bold' -> true},
  'body' -> body, 'can_close_with_escape' -> true, 'pause' -> false, 'after_action' -> 'none', 'columns' -> 1,
  'actions' -> actions,
  'exit_action' -> {'label' -> 'Close', 'width' -> 120, 'action' -> {'type' -> 'run_command', 'command' -> '/residents close'}}
};
_menu(p, err) -> (
  n = p ~ 'name';
  if (global_reg:n, return(_card_dialog(p)));
  rules = join('\n', map(global_cfg:'rules', str('%d. %s', _i + 1, _)));
  body = [_plain('Welcome! Register once and the whole city is open.', 'white'),
          _plain('Our rules:\n' + rules, '#FFD6EC')];
  if (err, body += _plain(err, '#FF5555'));
  d = _dialog('◆ Registration ◆', body,
    [{'label' -> {'text' -> 'Register ✦', 'color' -> '#FF7AC6', 'bold' -> true}, 'width' -> 220,
      'action' -> {'type' -> 'dynamic/run_command', 'template' -> '/residents register $(agree) n:$(nick)'}}]);
  d:'inputs' = [
    {'type' -> 'minecraft:text', 'key' -> 'nick', 'label' -> 'Your nickname', 'width' -> 220, 'max_length' -> 16, 'initial' -> n},
    {'type' -> 'minecraft:boolean', 'key' -> 'agree', 'label' -> 'I have read the rules and I agree', 'initial' -> false}];
  _show(p, d)
);
_cmd_menu() -> (p = player(); if (p, _menu(p, null)); 1);
_cmd_close() -> (p = player(); if (p, run('dialog clear ' + p ~ 'name')); 1);

_cmd_register(agree, nick) -> (
  p = player(); if (!p, return(0)); n = p ~ 'name';
  run('dialog clear ' + n);
  if (global_reg:n, (_bar(p, 'You are already registered ✦', '#FF7AC6'); return(1)));
  s = replace(replace(nick, '\\\\', ''), '"', '');       // the dialog escapes the text like an SNBT string
  if (length(s) >= 2 && slice(s, 0, 2) == 'n:', s = slice(s, 2));
  s = replace(s, '^\\s+|\\s+$', '');
  if (agree != 'true', return(_menu(p, 'Tick the box to agree to the rules ✦')));
  if (length(s) < 2 || length(s) > 16 || (s ~ '^[\\p{L}0-9 _\\-]+$') == null,
    return(_menu(p, 'Nickname: 2 to 16 characters (letters, digits, space, _ or -)')));
  e = {'nick' -> s, 'n' -> global_reg:'_next', 'joined' -> _today(),
       'role' -> if (_admin(p), 'Admin', global_cfg:'role':'name')};
  global_reg:'_next' = global_reg:'_next' + 1;
  global_reg:n = e;
  _save();
  _sync(p, true);
  _give_card(p, e);
  run(str('execute at %s run particle minecraft:firework ~ ~1 ~ 0.6 0.8 0.6 0.05 80', n));
  run(str('playsound minecraft:ui.toast.challenge_complete master %s ~ ~ ~ 1 1', n));
  run('tellraw @a ' + encode_json({'text' -> str('✦ %s joined the city! Welcome', s), 'color' -> '#FF7AC6'}));
  _show(p, _dialog('◆ You are in! ◆', [
      _plain(str('Welcome, %s! You are resident no. %d.', s, e:'n'), 'white'),
      _plain(str('Visit %s for skins, outfits and a resident card. Your resident card is already in your inventory.', global_cfg:'studio_hint'), '#FFD6EC')],
    [_btn('Off to the city ✦', '/residents close')]));
  1
);

// ───────────── the resident card ─────────────
_give_card(p, e) -> (
  n = p ~ 'name';
  run(str('clear %s paper[custom_data={resident_card:1b}]', n));
  nm = encode_json({'text' -> 'Resident card · ' + e:'nick', 'color' -> '#FF7AC6', 'italic' -> false});
  lore = encode_json([{'text' -> str('Resident no. %d', e:'n'), 'color' -> 'white', 'italic' -> false},
                      {'text' -> 'Joined: ' + e:'joined', 'color' -> 'gray', 'italic' -> false},
                      {'text' -> 'Role: ' + e:'role', 'color' -> 'gold', 'italic' -> false}]);
  run(str('give %s paper[item_model="studio:resident_card",custom_data={resident_card:1b},custom_name=%s,lore=%s] 1', n, nm, lore))
);
_card_dialog(p) -> (
  e = global_reg:(p ~ 'name');
  if (!e, return(_show(p, _dialog('◆ Residents office ◆', [_plain('Not registered yet? /residents menu ✦', 'white'),
      _plain('You can also reset your look here: studio outfits off and back to your own skin.', '#FFD6EC')],
    [_btn('Register ✦', '/residents menu'), _btn('↺ Reset my look', '/residents resetlook')]))));
  card = {'type' -> 'minecraft:item', 'item' -> {'id' -> 'minecraft:paper', 'count' -> 1, 'components' -> {'minecraft:item_model' -> 'studio:resident_card'}},
          'description' -> {'contents' -> {'text' -> 'Resident card · ' + e:'nick', 'color' -> '#FF7AC6', 'bold' -> true}, 'width' -> 200}};
  _show(p, _dialog('◆ Resident card ◆', [card,
      _plain(str('Resident no. %d · joined: %s · role: %s', e:'n', e:'joined', e:'role'), 'white')],
    [_btn('Print a new card', '/residents card'), _btn('↺ Reset my look', '/residents resetlook')]))
);
// the clerk resets your look: studio clothes off (only pieces tagged studio_outfit) + the original skin back (SkinRestorer reset)
_cmd_resetlook() -> (
  p = player(); if (!p, return(0));
  _show(p, _dialog('◆ Reset my look ◆', [_plain('Take off every studio outfit and go back to your own skin? Your armor and other items are not touched.', 'white')],
    [_btn('✓ Yes, reset', '/residents resetlookyes')])); 1
);
_cmd_resetlookyes() -> (
  p = player(); if (!p, return(0)); n = p ~ 'name';
  run('dialog clear ' + n);
  if (unix_time() - (global_skin_cd:n || 0) < 10000, return(_bar(p, 'One moment… you can reset once every 10 seconds', 'yellow')));
  global_skin_cd:n = unix_time();
  for (['head', 'chest', 'legs', 'feet'], if (_is_outfit(query(p, 'holds', _)), run(str('item replace entity %s armor.%s with air', n, _))));
  run('skin reset ' + n);
  _skin_now(n, null);
  _bar(p, '↺ Look reset: back to your own skin', '#FF7AC6');
  run(str('playsound minecraft:block.amethyst_block.chime master %s ~ ~ ~ 0.8 1', n));
  run(str('execute at %s run particle minecraft:end_rod ~ ~1 ~ 0.4 0.9 0.4 0.02 25', n)); 1
);
_cmd_card() -> (
  p = player(); if (!p, return(0));
  e = global_reg:(p ~ 'name');
  if (!e, return(_menu(p, null)));
  run('dialog clear ' + p ~ 'name');
  _give_card(p, e);
  _bar(p, 'A new resident card is in your inventory ✦', '#FF7AC6');
  1
);

// the skin each player wears now, shared with other apps (skins_now.json in the shared scripts folder; null = own skin).
// runway.sc dresses its models with it; skinpaint.sc writes it too.
_skin_now(n, rec) -> (m = read_file('skins_now', 'shared_json') || {}; if (rec, m:lower(n) = rec, delete(m, lower(n))); write_file('skins_now', 'shared_json', m));

// ───────────── studio: skins, wardrobe, clerk ─────────────
_skin(id) -> first(global_studio:'skins', _:'id' == id);
_skin_dialog(p, id) -> (
  s = _skin(id); if (!s, return());
  _show(p, _dialog('◆ ' + s:'name' + ' ◆', [_plain('Wear this skin? Everyone will see it.', 'white')],
    [_btn('✓ Yes, wear it', '/residents skin ' + id), _btn('↺ My own skin', '/residents skinreset')]))
);
_skin_ok(p) -> (
  n = p ~ 'name';
  if (!_resident(p), (_bar(p, 'Register first: /residents menu ✦', '#FF7AC6'); return(false)));
  if (unix_time() - (global_skin_cd:n || 0) < 10000, (_bar(p, 'One moment… you can change skin once every 10 seconds', 'yellow'); return(false)));
  global_skin_cd:n = unix_time();
  true
);
_cmd_skin(id) -> (
  p = player(); if (!p, return(0)); n = p ~ 'name';
  run('dialog clear ' + n);
  s = _skin(id); if (!s || !_skin_ok(p), return(0));
  r = run(str('skin set web classic %s %s', s:'url', n));   // a textures.minecraft.net address (studio.json) — no restart needed
  if (r:0 == 0, (_bar(p, 'Could not change the skin. Try again in a moment', 'red'); return(0)));
  _skin_now(n, {'texture' -> 'studio:entity/skin/' + id, 'label' -> s:'name'});
  _bar(p, str('✦ You are now %s', s:'name'), '#FF7AC6');
  run(str('playsound minecraft:entity.player.levelup master %s ~ ~ ~ 0.5 1.4', n));
  run(str('execute at %s run particle minecraft:end_rod ~ ~1 ~ 0.4 0.9 0.4 0.02 30', n));
  1
);
_cmd_skinreset() -> (
  p = player(); if (!p, return(0)); n = p ~ 'name';
  run('dialog clear ' + n);
  if (!_skin_ok(p), return(0));
  run('skin reset ' + n);
  _skin_now(n, null);
  _bar(p, 'Back to your own skin', 'white');
  1
);

_wardrobe(p) -> (
  acts = [];
  for (global_studio:'outfits', acts += _btn(if (_:'hat', '🎩 ', '✦ ') + _:'name', '/residents outfit ' + _:'id'));
  acts += _btn('✕ Remove outfit', '/residents outfit none');
  _show(p, _dialog('◆ Wardrobe ◆', [_plain('Pick a look. Hats swap without taking off the rest.', 'white')], acts))
);
_is_outfit(item) -> item != null && (str(item:2) ~ 'studio_outfit') != null;
_cmd_outfit(id) -> (
  p = player(); if (!p, return(0)); n = p ~ 'name';
  run('dialog clear ' + n);
  if (!_resident(p), return(_bar(p, 'Register first: /residents menu ✦', '#FF7AC6')));
  slots = {'head' -> 'armor.head', 'chest' -> 'armor.chest', 'legs' -> 'armor.legs', 'feet' -> 'armor.feet'};
  if (id == 'none', (
    for (keys(slots), if (_is_outfit(query(p, 'holds', _)), run(str('item replace entity %s %s with air', n, slots:_))));
    return(_bar(p, 'Outfit removed', 'white'))
  ));
  o = first(global_studio:'outfits', _:'id' == id); if (!o, return(0));
  kept = 0;
  for (keys(o:'pieces'), (
    s = _; cur = query(p, 'holds', s);
    if (cur != null && !_is_outfit(cur), kept += 1,
      run(str('item replace entity %s %s with %s', n, slots:s, o:'pieces':s)))
  ));
  _bar(p, str('✦ %s', o:'name') + if (kept, ' (your armor stays on)', ''), '#FF7AC6');
  run(str('playsound minecraft:item.armor.equip_leather master %s ~ ~ ~ 1 1', n));
  1
);

// ───────────── fitting wall: a mannequin wears the picked look, ◀ ▶ per row, then ✓ puts it on you ─────────────
// Rows and item strings come from residents.data/wardrobe.json (resourcepacks/wardrobe/gen_wardrobe_pack.py: real
// clothes = pack equipment assets, 3D hats = item models on the head, wings = the elytra layer of the chest item, so
// a top and wings share one chest item: wardrobe.json chest['<top>|<wings>']). One shared selection for everyone.
// The buttons are plain vanilla button blocks polled every 2 ticks (no client mod); the wall runs along z and its
// glyphs face studio.json fitting.yaw (-90 = east). Picking wings turns the dummy around, since wings are on the back.
// Mannequins render like players, so `item replace entity <uuid> armor.<slot>` dresses the dummy with anything.
// query(e, 'holds', slot) is null on mannequins, so the dummy is always fully re-dressed from the selection.
_d2(a, b) -> (a:0 - b:0) ^ 2 + (a:1 - b:1) ^ 2 + (a:2 - b:2) ^ 2;
_fit_row(k) -> first(global_wd:'rows', _:'key' == k);
_fit_cur(k) -> (r = _fit_row(k); r:'items':(global_fit:'sel':k || 0));
_fit_items() -> (
  t = _fit_cur('top'):'id'; w = _fit_cur('wings'):'id';
  {'head' -> _fit_cur('head'):'item', 'chest' -> global_wd:'chest':(t + '|' + w),
   'legs' -> _fit_cur('legs'):'item', 'feet' -> _fit_cur('feet'):'item'}
);
_fit_btn_list() -> (
  F = global_studio:'fitting'; l = [];
  for (global_wd:'rows', (
    y = F:'rows_y':(_:'key');
    l += ['p_' + _:'key', [F:'button_x', y, F:'prev_z'], 'prev', _:'key'];
    l += ['n_' + _:'key', [F:'button_x', y, F:'next_z'], 'next', _:'key']
  ));
  for (F:'actions', l += ['a_' + _:'id', _:'pos', _:'id', null]);
  l
);
_fit_dress() -> (
  e = _ent('res_fit_model'); if (!e, return());
  u = query(e, 'uuid'); it = _fit_items();
  for (['head', 'chest', 'legs', 'feet'], run(str('item replace entity %s armor.%s with %s', u, _, it:_ || 'air')))
);
_fit_row_text(r) -> (
  i = global_fit:'sel':(r:'key') || 0; n = length(r:'items') - 1;
  ['', {'text' -> r:'name', 'color' -> '#FF7AC6', 'bold' -> true},
   {'text' -> '\n' + if (i == 0, '—', r:'items':i:'name'), 'color' -> 'white'},
   {'text' -> if (i == 0, '', str('  %d/%d', i, n)), 'color' -> 'gray'}]
);
_fit_labels() -> for (global_wd:'rows', (
  e = _ent('res_fit_row_' + _:'key');
  if (e, modify(e, 'nbt_merge', str('{text:%s}', encode_json(_fit_row_text(_)))))
));
_fit_save() -> write_file('fitting', 'json', global_fit:'sel');
_fit_refresh() -> (_fit_dress(); _fit_labels(); _fit_save());

_fit_press(b, near) -> (
  bp = [b:1:0 + 0.5, b:1:1 + 0.5, b:1:2 + 0.5];
  p = null; bd = 30;
  for (near, (d = _d2(pos(_), bp); if (d < bd, (bd = d; p = _))));
  if (!p, return());
  n = p ~ 'name'; act = b:2; key = b:3;
  run(str('playsound minecraft:ui.button.click master %s ~ ~ ~ 0.35 1.6', n));
  if (act == 'prev' || act == 'next', (
    r = _fit_row(key); c = length(r:'items');
    global_fit:'sel':key = ((global_fit:'sel':key || 0) + if (act == 'next', 1, c - 1)) % c;
    global_fit:'ang' = if (key == 'wings', 180, 0);
    global_fit:'hold' = tick_time() + 100;
    _fit_refresh();
    i = global_fit:'sel':key;
    _bar(p, str('%s: %s', r:'name', if (i == 0, 'none', r:'items':i:'name')), '#FF7AC6')
  ), act == 'random', (
    for (global_wd:'rows', (
      k = _:'key'; c = length(_:'items');
      global_fit:'sel':k = if (k == 'wings', if (rand(1) < 0.35, 1 + floor(rand(c - 1)), 0),
                               k == 'head', if (rand(1) < 0.8, 1 + floor(rand(c - 1)), 0),
                               1 + floor(rand(c - 1)))
    ));
    global_fit:'ang' = 0; global_fit:'hold' = tick_time() + 60;
    _fit_refresh();
    run(str('execute at %s run particle minecraft:end_rod %.2f %.2f %.2f 0.3 0.8 0.3 0.02 20', n,
            global_studio:'fitting':'model':'pos':0, global_studio:'fitting':'model':'pos':1 + 1, global_studio:'fitting':'model':'pos':2));
    _bar(p, '↻ A new look on the dummy · press ✓ Wear to put it on', '#FF7AC6')
  ), act == 'wear', _fit_wear(p),
  act == 'off', _undress(p)
));

_fit_wear(p) -> (
  n = p ~ 'name';
  if (!_resident(p), return(_bar(p, 'Register first: /residents menu ✦', '#FF7AC6')));
  it = _fit_items(); kept = 0; put = 0;
  for (['head', 'chest', 'legs', 'feet'], (
    s = _; cur = query(p, 'holds', s);
    if (cur != null && !_is_outfit(cur), kept += 1,
      if (it:s, (run(str('item replace entity %s armor.%s with %s', n, s, it:s)); put += 1),
        cur != null, run(str('item replace entity %s armor.%s with air', n, s))))
  ));
  _bar(p, if (put, '✦ The look is yours!', 'The dummy has nothing on. Pick something with the arrows') + if (kept, ' (your armor stays on)', ''), '#FF7AC6');
  run(str('playsound minecraft:item.armor.equip_leather master %s ~ ~ ~ 1 1', n));
  run(str('execute at %s run particle minecraft:end_rod ~ ~1 ~ 0.4 0.9 0.4 0.02 25', n))
);
_undress(p) -> (
  n = p ~ 'name';
  for (['head', 'chest', 'legs', 'feet'], if (_is_outfit(query(p, 'holds', _)), run(str('item replace entity %s armor.%s with air', n, _))));
  _bar(p, 'Outfit removed', 'white')
);
_cmd_fitwear() -> (p = player(); if (p, (run('dialog clear ' + p ~ 'name'); _fit_wear(p))); 1);

_fit_spin() -> (
  e = _ent('res_fit_model'); if (!e, return());
  if (tick_time() >= global_fit:'hold', global_fit:'ang' = (global_fit:'ang' + 4) % 360);
  a = global_studio:'fitting':'model':'yaw' + global_fit:'ang';
  modify(e, 'yaw', a); modify(e, 'body_yaw', a); modify(e, 'head_yaw', a)
);
_fit_tick() -> (
  F = global_studio:'fitting'; if (!F || !global_wd:'rows', return());
  m = F:'model':'pos';
  near = filter(player('all'), ((_ ~ 'player_type') != 'fake' || global_allow_fake) && _d2(pos(_), m) < 81);
  if (!near, return());
  for (global_fit_btns, (
    b = _; bp = b:1;
    on = str(block_state(block(bp:0, bp:1, bp:2), 'powered')) == 'true';
    if (on && !global_fit_prev:(b:0), _fit_press(b, near));
    global_fit_prev:(b:0) = on
  ));
  _fit_spin()
);
_glyph(tag, pos, text, scale) -> _one(tag, 'text_display', pos,
  str('Rotation:[%.1ff,0f],billboard:"fixed",alignment:"center",line_width:120,shadow:1b,background:0,brightness:{sky:15,block:15},view_range:0.8f,%s,text:%s',
      if (global_studio:'fitting':'yaw' == null, -90, global_studio:'fitting':'yaw'), _tf(scale, scale, scale), encode_json(text)));
_fit_ensure() -> (
  F = global_studio:'fitting'; if (!F || !global_wd:'rows', return());
  M = F:'model';
  if (!_ent('res_fit_model') && _mannequin('res_fit_model', M:'pos', M:'yaw', M:'skin', M:'name'), _fit_dress());
  for (global_wd:'rows', (
    y = F:'rows_y':(_:'key');
    _glyph('res_fit_p_' + _:'key', [F:'face_x', y + 0.5 - 0.125, F:'prev_z' + 0.5], {'text' -> '◀', 'color' -> '#FFFFFF'}, 1.0);
    _glyph('res_fit_n_' + _:'key', [F:'face_x', y + 0.5 - 0.125, F:'next_z' + 0.5], {'text' -> '▶', 'color' -> '#FFFFFF'}, 1.0);
    _glyph('res_fit_row_' + _:'key', [F:'label_x', y + 0.22, F:'label_z'], _fit_row_text(_), 0.42)
  ));
  for (F:'actions', _glyph('res_fit_a_' + _:'id', [F:'face_x', _:'pos':1 + 0.5 - 0.06, _:'pos':2 + 0.5],
                            {'text' -> _:'text', 'color' -> '#FFE3F1', 'bold' -> true}, 0.45));
  t = F:'title';
  _glyph('res_fit_title', t, ['', {'text' -> '✦ Fitting wall ✦', 'color' -> '#FF7AC6', 'bold' -> true},
                              {'text' -> '\nPick with the arrows · ✓ to wear', 'color' -> 'white'}], 0.6)
);

// ───────────── studio entities (one per tag, spawned only where loaded) ─────────────
_one(tag, type, at, nbt) -> (
  e = _ent(tag); if (e, return(e));
  l = entity_selector(str('@e[type=%s,tag=%s]', type, tag));
  if (l, (
    global_ents:tag = query(l:0, 'uuid');
    for (slice(l, 1), modify(_, 'remove'));
    return(l:0)
  ));
  if (loaded_status(at) < 3 || tick_time() < (global_cool:tag || 0), return(null));
  global_cool:tag = tick_time() + 1200;
  e = spawn(type, at, str('{Tags:["residents","%s"],%s}', tag, nbt));
  if (e, global_ents:tag = query(e, 'uuid'));
  e
);
// no floating nametag (it shows through floors); the plaques are text_displays (hidden behind blocks) readable
// from across the studio (view_range 0.7 ≈ 45 blocks)
_mannequin(tag, pos, yaw, texture, name) -> _one(tag, 'mannequin', pos,
  str('Rotation:[%.1ff,0f],pose:"standing",immovable:1b,hide_description:1b,Invulnerable:1b,Silent:1b,profile:{model:"wide",texture:"%s"},CustomName:%s,CustomNameVisible:0b',
      yaw, texture, encode_json({'text' -> name, 'color' -> '#FF7AC6'})));
_label(tag, pos, yaw, lines, scale, billboard) -> _one(tag, 'text_display', pos,
  str('Rotation:[%.1ff,0f],billboard:"%s",alignment:"center",line_width:200,shadow:1b,background:1342177280,brightness:{sky:15,block:15},view_range:0.7f,%s,text:%s',
      yaw, billboard, _tf(scale, scale, scale), encode_json(lines)));
_ensure() -> (
  S = global_studio; if (!S:'skins', return());
  for (S:'skins', (
    s = _;
    _mannequin('res_skin_' + s:'id', s:'pos', s:'yaw', 'studio:entity/skin/' + s:'id', s:'name');
    pl = s:'plaque';
    _label('res_plaque_' + s:'id', pl:'pos', pl:'yaw',
      [{'text' -> s:'name', 'color' -> '#FF7AC6', 'bold' -> true}, {'text' -> '\nClick to wear', 'color' -> 'white'}], 0.4, 'fixed')
  ));
  w = S:'wardrobe';
  if (w, (
    _one('res_wardrobe', 'interaction', w:'pos', str('width:%.2ff,height:%.2ff,response:1b', w:'w', w:'h'));
    _label('res_wardrobe_label', w:'label', 0,
      [{'text' -> '✦ Wardrobe ✦', 'color' -> '#FF7AC6', 'bold' -> true}, {'text' -> '\nClick to dress up', 'color' -> 'white'}], 0.55, 'center')
  ));
  _fit_ensure();
  c = S:'clerk';
  if (c, _mannequin('res_clerk', c:'pos', c:'yaw', c:'skin', c:'name'));
  d = S:'card_display';
  if (d, _one('res_card_display', 'item_display', d:'pos',
    str('Rotation:[%.1ff,0f],brightness:{sky:15,block:15},item:{id:"minecraft:paper",count:1,components:{"minecraft:item_model":"%s"}},%s',
        d:'yaw', d:'model', _tf(d:'scale':0, d:'scale':1, d:'scale':2))))
);

__on_player_interacts_with_entity(p, e, hand) -> (
  if (hand != 'mainhand' || !query(e, 'has_tag', 'residents'), return());
  tags = query(e, 'scoreboard_tags');
  if (first(tags, _ == 'res_wardrobe') != null, return(_wardrobe(p)));
  if (first(tags, _ == 'res_clerk') != null, return(_card_dialog(p)));
  if (first(tags, _ == 'res_fit_model') != null, return(_show(p, _dialog('◆ Fitting dummy ◆',
    [_plain('Wear the look on the dummy? Change it with the arrows on the wall.', 'white')],
    [_btn('✓ Yes, wear it', '/residents fitwear'), _btn('✕ Take the outfit off', '/residents outfit none')]))));
  t = first(tags, (_ ~ '^res_skin_') != null);
  if (t != null, _skin_dialog(p, slice(t, 9)))
);

// ───────────── admin ─────────────
_adm(p) -> (if (p && !_admin(p), (print(p, 'Admins only'); return(false))); true);
_adm_list() -> (
  p = player(); if (!_adm(p), return(0));
  for (sort(filter(keys(global_reg), _ != '_next')), e = global_reg:_; print(p, str('#%d %s (%s) · %s · %s', e:'n', _, e:'nick', e:'role', e:'joined')));
  1
);
_adm_info(name) -> (p = player(); if (!_adm(p), return(0)); print(p, str('%s: %s', name, global_reg:name)); 1);
_adm_unregister(name) -> (
  p = player(); if (!_adm(p), return(0));
  if (!global_reg:name, return(print(p, 'Not registered: ' + name)));
  delete(global_reg, name); _save();
  q = player(name);
  if (q, (modify(q, 'clear_tag', 'resident'); if ((q ~ 'team') == global_cfg:'role':'team', run('team leave ' + name))));
  print(p, 'Removed: ' + name); 1
);
_adm_setnick(name, nick) -> (
  p = player(); if (!_adm(p), return(0));
  if (!global_reg:name, return(print(p, 'Not registered: ' + name)));
  global_reg:name:'nick' = nick; _save(); print(p, str('%s → %s', name, nick)); 1
);
_adm_reset() -> (
  p = player(); if (!_adm(p), return(0));
  for (entity_selector('@e[tag=residents]'), modify(_, 'remove'));
  global_ents = {}; global_cool = {};
  _ensure(); 1
);

// ───────────── lifecycle ─────────────
_load() -> (
  global_cfg = read_file('config', 'json') || {};
  global_studio = read_file('studio', 'json') || {};
  delete(global_cfg, '_doc'); delete(global_studio, '_doc');
  global_wd = read_file('wardrobe', 'json') || {};
  global_fit:'sel' = read_file('fitting', 'json') || {};
  global_fit_btns = if (global_studio:'fitting' && global_wd:'rows', _fit_btn_list(), []);
  global_reg = read_file('registry', 'json');
  if (!global_reg, (
    global_reg = {'_next' -> 1};
    for (global_cfg:'seed' || [], (
      global_reg:(_:'name') = {'nick' -> _:'nick', 'n' -> _:'n', 'joined' -> _today(), 'role' -> 'Admin'};
      global_reg:'_next' = max(global_reg:'_next', _:'n' + 1)
    ));
    _save()
  ))
);
_team() -> (
  r = global_cfg:'role'; t = r:'team';
  run('team add ' + t);
  run(str('team modify %s color %s', t, r:'color'));
  run(str('team modify %s prefix ""', t));
  run(str('team modify %s suffix ""', t))
);
__on_start() -> (
  _load();
  _team();
  _sync_all(true);
  schedule(10, '_ensure')
);
__on_player_connects(p) -> schedule(20, '_joined', p ~ 'name');
_joined(n) -> (
  p = player(n); if (!p, return());
  _sync(p, true);
  if (!_resident(p) && !_exempt(p), _welcome(p))
);
__on_tick() -> (
  t = tick_time();
  if (t % 5 == 0, _barrier());
  if (t % 2 == 0, _fit_tick());
  if (t % 100 == 13, (_sync_all(false); _ensure()))
);

status() -> {
  'busy' -> false,
  'registered' -> length(filter(keys(global_reg), _ != '_next')),
  'online_unregistered' -> map(filter(player('all'), !_resident(_) && !_exempt(_)), _ ~ 'name'),
  'ents' -> length(filter(keys(global_ents), entity_id(global_ents:_)))
};
