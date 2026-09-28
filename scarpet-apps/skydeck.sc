// skydeck.sc — the tower : observation deck + sky bar.
//  · the bartender pours a drink (one per minute, no alcohol)
//  · 4 telescopes: click → pick a landmark → an 8-second locked camera flight view of it (spectator mode riding an
//    invisible marker = the view can't be moved), then back to the telescope in your own game mode
//  · copper-bulb lights on the glass railing switch on at dusk and off at dawn
//  · a fireworks button (shows only on the button — never automatic, the owner), one show per minute
// Data: skydeck.data/layout.json (written by your build generator) — bulbs, bartender,
//   bar_sign, telescopes[{id, block, look}], fireworks{button, spots}, landmarks[{id, title, centre, r}], box.
// A player who disconnects mid-view is restored when they come back (skydeck.data/cam_<uuid>.json).
// Commands: /skydeck drink <id> · /skydeck look <n> · /skydeck close · /skydeck reset (admin)

__config() -> {
  'stay_loaded' -> true, 'scope' -> 'global', 'command_permission' -> 'all',
  'commands' -> {'drink <id>' -> '_cmd_drink', 'look <n>' -> '_cmd_look', 'close' -> '_cmd_close', 'reset' -> '_cmd_reset'},
  'arguments' -> {'id' -> {'type' -> 'term', 'suggest' -> ['lemonade', 'water', 'sunset']}, 'n' -> {'type' -> 'int', 'min' -> 1, 'max' -> 99, 'suggest' -> []}}
};

global_L = {};
global_ents = {};
global_cool = {};
global_active = false;
global_drink = {};        // name -> unix_time() of the last drink
global_cam = {};          // name -> {'gm','back','yaw','pitch','marker','until','title'}
global_tele_of = {};      // name -> telescope id they last clicked
global_btn_prev = false;
global_fw_last = 0;
global_allow_fake = false;
global_view_ticks = 160;  // 8 s
global_drinks = {
  'lemonade' -> ['🍋 Iced lemonade', 'honey_bottle'],
  'water' -> ['💧 Mint water', 'potion[potion_contents={potion:"minecraft:water"}]'],
  'sunset' -> ['🌅 Sunset (orange & raspberry)', 'potion[potion_contents={potion:"minecraft:fire_resistance"}]']
};

_real(p) -> p && ((p ~ 'player_type') != 'fake' || global_allow_fake) && (p ~ 'dimension') == 'overworld';
_admin(p) -> !p || (p ~ 'permission_level') >= 2;
_bar(p, text, color) -> run(str('title %s actionbar %s', p ~ 'name', encode_json({'text' -> text, 'color' -> color})));
_ent(tag) -> entity_id(global_ents:tag);
_tf(s) -> str('transformation:{left_rotation:[0f,0f,0f,1f],right_rotation:[0f,0f,0f,1f],translation:[0f,0f,0f],scale:[%.3ff,%.3ff,%.3ff]}', s, s, s);
_in(q, b) -> q:0 >= b:'min':0 - 8 && q:0 < b:'max':0 + 9 && q:1 >= b:'min':1 - 12 && q:1 < b:'max':1 + 20 && q:2 >= b:'min':2 - 8 && q:2 < b:'max':2 + 9;
_near() -> (b = global_L:'box'; b && first(player('all'), _real(_) && _in(pos(_), b)) != null);

_one(tag, type, at, nbt) -> (
  e = _ent(tag); if (e, return(e));
  l = entity_selector(str('@e[type=%s,tag=%s]', type, tag));
  if (l, (global_ents:tag = query(l:0, 'uuid'); for (slice(l, 1), modify(_, 'remove')); return(l:0)));
  if (loaded_status(at) < 3 || tick_time() < (global_cool:tag || 0), return(null));
  global_cool:tag = tick_time() + 600;
  e = spawn(type, at, str('{Tags:["skydeck","%s"],%s}', tag, nbt));
  if (e, global_ents:tag = query(e, 'uuid'));
  e
);
_label(tag, at, lines, sc, billboard, yaw, range) -> _one(tag, 'text_display', at,
  str('Rotation:[%.1ff,0f],billboard:"%s",alignment:"center",line_width:220,shadow:1b,background:1342177280,brightness:{sky:15,block:15},view_range:%.2ff,%s,text:%s',
      yaw, billboard, range, _tf(sc), encode_json(lines)));

_ensure() -> (
  L = global_L; if (!L:'box', return());
  B = L:'bartender';
  _one('sky_bar', 'mannequin', B:'pos',
    str('Rotation:[%.1ff,0f],pose:"standing",immovable:1b,hide_description:1b,Invulnerable:1b,Silent:1b,profile:{model:"wide",texture:"%s"},CustomName:%s,CustomNameVisible:0b',
        B:'yaw', B:'skin', encode_json({'text' -> B:'name', 'color' -> '#FF8FC8'})));
  _label('sky_bar_lbl', B:'pos' + [0, 2.15, 0], [{'text' -> B:'name', 'color' -> '#FF8FC8', 'bold' -> true}, {'text' -> '\nClick to order', 'color' -> '#DDDDDD'}], 0.4, 'vertical', 0, 0.2);
  S = L:'bar_sign';
  _label('sky_bar_sign', S:'pos', [{'text' -> '☀ Sky bar ☀', 'color' -> '#FFB86B', 'bold' -> true}], 1.1, 'fixed', S:'yaw', 1.0);
  for (L:'telescopes', (
    t = _; q = t:'block';
    _one('sky_tele_' + t:'id', 'item_display', q + [0.5, 1.3, 0.5],
      str('Rotation:[%.1ff,-18f],item_display:"fixed",brightness:{sky:15,block:15},item:{id:"minecraft:spyglass",count:1},%s', t:'look', _tf(1.1)));
    _one('sky_tele_hit_' + t:'id', 'interaction', q + [0.5, 0.9, 0.5], 'width:0.9f,height:1.0f,response:1b');
    _label('sky_tele_lbl_' + t:'id', q + [0.5, 1.95, 0.5], [{'text' -> '🔭 Telescope', 'color' -> '#7EC8FF', 'bold' -> true}], 0.4, 'vertical', 0, 0.3)
  ));
  F = L:'fireworks';
  if (F, _label('sky_fw_lbl', F:'button' + [0.5, 0.75, 0.5], [{'text' -> '🎆 Fireworks', 'color' -> '#FFD24A', 'bold' -> true}, {'text' -> '\nPress the button', 'color' -> '#DDDDDD'}], 0.45, 'vertical', 0, 0.4))
);

// ───────────── the bar ─────────────
_bar_menu(p) -> (
  acts = map(keys(global_drinks), {'label' -> global_drinks:_:0, 'width' -> 170, 'action' -> {'type' -> 'run_command', 'command' -> '/skydeck drink ' + _}});
  d = {'type' -> 'minecraft:multi_action', 'title' -> {'text' -> '☀ Sky bar', 'color' -> '#FFB86B', 'bold' -> true},
       'body' -> [{'type' -> 'minecraft:plain_message', 'contents' -> {'text' -> 'The highest bar in town. What can I get you? (all alcohol-free)', 'color' -> 'white'}, 'width' -> 280}],
       'can_close_with_escape' -> true, 'pause' -> false, 'after_action' -> 'none', 'columns' -> 3, 'actions' -> acts,
       'exit_action' -> {'label' -> 'Close', 'width' -> 120, 'action' -> {'type' -> 'run_command', 'command' -> '/skydeck close'}}};
  run(str('dialog show %s %s', p ~ 'name', encode_json(d)))
);
_cmd_drink(id) -> (
  p = player(); if (!p, return(0)); n = p ~ 'name'; d = global_drinks:id; if (!d, return(0));
  run('dialog clear ' + n);
  if (unix_time() - (global_drink:n || 0) < 60000, return(_bar(p, 'Bartender: "One a minute, love."', 'gray')));
  global_drink:n = unix_time();
  item = d:1;
  it = if (item ~ '\\[', replace(item, '\\]$', str(',custom_name={text:"%s",color:"#FFB86B",italic:false}]', d:0)), str('%s[custom_name={text:"%s",color:"#FFB86B",italic:false}]', item, d:0));
  run(str('give %s %s 1', n, it));
  bt = _ent('sky_bar'); if (bt, modify(bt, 'swing'));
  _bar(p, d:0 + ' ✦', '#FFB86B'); 1
);
_cmd_close() -> (p = player(); if (p, run('dialog clear ' + p ~ 'name')); 1);

// ───────────── telescopes ─────────────
_tele_menu(p) -> (
  acts = map(global_L:'landmarks' || [], {'label' -> _:'title', 'width' -> 150, 'action' -> {'type' -> 'run_command', 'command' -> '/skydeck look ' + (_i + 1)}});
  d = {'type' -> 'minecraft:multi_action', 'title' -> {'text' -> '🔭 Telescope', 'color' -> '#7EC8FF', 'bold' -> true},
       'body' -> [{'type' -> 'minecraft:plain_message', 'width' -> 300, 'contents' -> {'text' -> 'What do you want to look at? (an 8-second view, then you are back here)', 'color' -> 'white'}}],
       'can_close_with_escape' -> true, 'pause' -> false, 'after_action' -> 'none', 'columns' -> 2, 'actions' -> acts,
       'exit_action' -> {'label' -> 'Close', 'width' -> 120, 'action' -> {'type' -> 'run_command', 'command' -> '/skydeck close'}}};
  run(str('dialog show %s %s', p ~ 'name', encode_json(d)))
);
// the camera: from the landmark's centre step toward the tower (so you see its tower-facing side), up by 0.75 r
_cam_for(lm) -> (
  c = lm:'centre'; r = lm:'r';
  h = global_L:'home' || [0, 0]; dx = h:0 - c:0; dz = h:1 - c:2;   // home = the deck's own x, z l = sqrt(dx * dx + dz * dz);
  if (l < 20, (dx = 0.7; dz = 0.7; l = 1));                            // the tower itself: from the south-east
  cam = [c:0 + dx / l * r * 1.15, c:1 + r * 0.75, c:2 + dz / l * r * 1.15];
  tx = c:0 - cam:0; ty = c:1 - cam:1; tz = c:2 - cam:2;
  [cam, atan2(-tx, tz), atan2(-ty, sqrt(tx * tx + tz * tz))]
);
_cmd_look(n) -> (
  p = player(); if (!p, return(0)); nm = p ~ 'name';
  run('dialog clear ' + nm);
  lm = (global_L:'landmarks' || []):(n - 1); if (!lm, return(0));
  if (global_cam:nm || query(p, 'mount'), return(0));
  tid = global_tele_of:nm; t = first(global_L:'telescopes', _:'id' == tid) || global_L:'telescopes':0;
  back = t:'block' + [0.5, 0, 0.5];
  back = [back:0 + if (t:'look' > 0, 1, -1), back:1, back:2];      // stand behind the telescope, facing its way
  C = _cam_for(lm);
  st = {'gm' -> query(p, 'gamemode'), 'back' -> back, 'yaw' -> t:'look', 'title' -> lm:'title', 'cam' -> C:0, 'yw' -> C:1, 'pt' -> C:2,
        'until' -> tick_time() + global_view_ticks, 'marker' -> null};
  global_cam:nm = st;
  write_file('cam_' + query(p, 'uuid'), 'json', {'gm' -> st:'gm', 'back' -> back, 'yaw' -> st:'yaw'});
  run(str('forceload add %d %d', floor(C:0:0), floor(C:0:2)));
  run(str('gamemode spectator %s', nm));
  run(str('tp %s %.2f %.2f %.2f %.1f %.1f', nm, C:0:0, C:0:1, C:0:2, C:1, C:2));
  run(str('execute as %s at @s run playsound minecraft:item.spyglass.use master @s ~ ~ ~ 1 1', nm));
  schedule(3, '_cam_attach', nm, 0);
  1
);
_cam_attach(nm, tries) -> (
  st = global_cam:nm; p = player(nm);
  if (!st || !p, return());
  q = st:'cam';
  if (loaded_status(q) < 3, return(if (tries < 20, schedule(2, '_cam_attach', nm, tries + 1))));
  m = spawn('armor_stand', q, str('{Tags:["skydeck","sky_cam"],Marker:1b,Invisible:1b,NoGravity:1b,Invulnerable:1b,Silent:1b,Rotation:[%.1ff,%.1ff]}', st:'yw', st:'pt'));
  if (m, (
    st:'marker' = query(m, 'uuid');
    run(str('spectate %s %s', query(m, 'uuid'), nm))
  ))
);
_cam_tick() -> for (keys(global_cam), (
  nm = _; st = global_cam:nm; p = player(nm);
  if (!p, (delete(global_cam, nm); continue()));
  left = st:'until' - tick_time();
  if (left % 20 == 0 && left > 0, _bar(p, str('🔭 %s · %d', st:'title', ceil(left / 20)), '#7EC8FF'));
  if (left <= 0, _cam_end(p))
));
_cam_end(p) -> (
  nm = p ~ 'name'; st = global_cam:nm; if (!st, return());
  run(str('execute as %s run spectate', nm));
  m = entity_id(st:'marker'); if (m, modify(m, 'remove'));
  b = st:'back';
  run(str('tp %s %.2f %.2f %.2f %.1f 0', nm, b:0, b:1, b:2, st:'yaw'));
  run(str('gamemode %s %s', st:'gm', nm));
  run(str('forceload remove %d %d', floor(st:'cam':0), floor(st:'cam':2)));
  delete_file('cam_' + query(p, 'uuid'), 'json');
  delete(global_cam, nm);
  _bar(p, 'Back on the roof ☀', '#7EC8FF')
);
// came back after leaving mid-view → put them back on the deck in their own game mode
__on_player_connects(p) -> schedule(20, '_restore', p ~ 'name');
_restore(nm) -> (
  p = player(nm); if (!p, return());
  f = read_file('cam_' + query(p, 'uuid'), 'json'); if (!f, return());
  run(str('execute as %s run spectate', nm));
  run(str('tp %s %.2f %.2f %.2f %.1f 0', nm, f:'back':0, f:'back':1, f:'back':2, f:'yaw'));
  run(str('gamemode %s %s', f:'gm', nm));
  delete_file('cam_' + query(p, 'uuid'), 'json')
);
__on_player_disconnects(p, reason) -> (
  st = global_cam:(p ~ 'name');
  if (st, (m = entity_id(st:'marker'); if (m, modify(m, 'remove')); delete(global_cam, p ~ 'name')))
);

// ───────────── lights at dusk ─────────────
_night() -> (t = day_time() % 24000; t >= 12300 || t < 200);
_lights() -> (
  B = global_L:'bulbs' || []; if (!B || loaded_status(B:0) < 2, return());
  want = if (_night(), 'true', 'false');
  for (B, if (block(_) == 'waxed_copper_bulb' && str(block_state(block(_), 'lit')) != want, set(_, 'waxed_copper_bulb', 'lit', want)))
);

// ───────────── fireworks (button only) ─────────────
_fw_poll() -> (
  F = global_L:'fireworks'; if (!F, return());
  q = F:'button'; if (loaded_status(q) < 3, return());
  on = str(block_state(block(q), 'powered')) == 'true';
  if (on && !global_btn_prev, (
    best = null; bd = 36;
    for (player('all'), if (_real(_), (d = reduce(pos(_) - (q + 0.5), _a + _ * _, 0); if (d < bd, (bd = d; best = _)))));
    if (unix_time() - global_fw_last < 60000,
      if (best, _bar(best, 'The fireworks are reloading… one moment', 'gray')),
      (global_fw_last = unix_time(); _show(); if (best, _bar(best, '🎆 !!!', '#FFD24A')))
    )
  ));
  global_btn_prev = on
);
global_colors = [16738740, 16777215, 16766720, 8309759, 16711935, 65535, 16729344];
_rocket(i) -> (
  S = global_L:'fireworks':'spots'; s = S:(i % length(S)) + [rand(3) - 1.5, 0, rand(3) - 1.5];
  c1 = global_colors:(floor(rand(length(global_colors)))); c2 = global_colors:(floor(rand(length(global_colors))));
  shape = ['large_ball', 'star', 'burst', 'small_ball']:(floor(rand(4)));
  run(str('summon firework_rocket %.2f %.2f %.2f {LifeTime:%d,FireworksItem:{id:"minecraft:firework_rocket",count:1,components:{"minecraft:fireworks":{flight_duration:2,explosions:[{shape:"%s",colors:[I;%d,%d],fade_colors:[I;16777215],has_trail:true,has_twinkle:true}]}}}}',
    s:0, s:1, s:2, 25 + floor(rand(15)), shape, c1, c2))
);
_show() -> for (range(28), schedule(_ * 4 + floor(rand(3)), '_rocket', _));

// ───────────── events / lifecycle ─────────────
__on_player_interacts_with_entity(p, e, hand) -> (
  if (hand != 'mainhand' || !query(e, 'has_tag', 'skydeck'), return());
  if (query(e, 'has_tag', 'sky_bar'), return(_bar_menu(p)));
  t = first(query(e, 'scoreboard_tags'), (_ ~ '^sky_tele_hit_') != null);
  if (t, (global_tele_of:(p ~ 'name') = replace(t, 'sky_tele_hit_', ''); _tele_menu(p)))
);
_cmd_reset() -> (
  p = player(); if (!_admin(p), return(if (p, print(p, 'Admins only'), 0)));
  for (entity_selector('@e[tag=skydeck]'), if (!query(_, 'has_tag', 'sky_cam'), modify(_, 'remove')));
  global_ents = {}; global_cool = {};
  _ensure(); 1
);
__on_start() -> (
  global_L = read_file('layout', 'json') || {};
  for (entity_selector('@e[tag=sky_cam]'), modify(_, 'remove'));
  schedule(10, '_ensure')
);
__on_tick() -> (
  t = tick_time();
  if (global_cam, _cam_tick());
  if (t % 20 == 11, global_active = _near());
  if (!global_active, return());
  if (t % 2 == 0, _fw_poll());
  if (t % 100 == 13, (_ensure(); _lights()))
);
status() -> {'busy' -> length(global_cam) > 0, 'active' -> global_active, 'viewing' -> keys(global_cam),
             'ents' -> length(filter(keys(global_ents), entity_id(global_ents:_))), 'night' -> _night()};
