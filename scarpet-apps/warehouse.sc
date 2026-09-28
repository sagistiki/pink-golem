// warehouse.sc — "The Warehouse", the tower techno club (Berghain vibe, black, hard techno, selection at the
// door, a bar with a bartender, lighting that feels real).
//  • Music: club:techno_loop (150 BPM = exactly 8 ticks a beat, 51.2 s = 1024 ticks). Each player inside the club hears
//    it (only them — "@s") from the next beat on, re-triggered every 1024 ticks, stopped when they leave.
//  • Light show on the same 8-tick grid while anyone is inside: strobe light blocks flash on every kick, red laser beams
//    (thin block_displays) sweep from the ceiling rigs and the stage, a sparkle burst at the chandelier every bar,
//    smoke on the floor, the DJ moves on every beat.
//  • The door: the lift opens into a closed vestibule; the bouncer decides (black clothes and admins always get in,
//    otherwise ~70 %, a refusal means one minute's wait); the iron gate opens only for the approved, and always from
//    inside (nobody is locked in). The bartender pours drinks (one per minute).
// Data: warehouse.data/layout.json (from the build generator). Admin: /script in warehouse run status()

__config() -> {'stay_loaded' -> true, 'scope' -> 'global', 'command_permission' -> 'all',
  'commands' -> {'drink <id>' -> '_cmd_drink', 'close' -> '_cmd_close'},
  'arguments' -> {'id' -> {'type' -> 'term'}}};

global_L = {};
global_ents = {};
global_cool = {};
global_music = {};        // player name -> tick_time() their loop was (re)started
global_ok = {};           // player name -> tick_time() until which the gate opens for them
global_no = {};           // player name -> tick_time() of the last refusal
global_drink = {};        // player name -> unix_time() of the last drink
global_gate_open = false;
global_active = false;
global_allow_fake = false;
global_loop = 1024;
global_drinks = {
  'tonic' -> ['🍸 Techno tonic', 'honey_bottle'],
  'water' -> ['💧 Cold water', 'potion[potion_contents={potion:"minecraft:water"}]'],
  'energy' -> ['⚡ Energy', 'potion[potion_contents={potion:"minecraft:swiftness"}]']
};

_real(p) -> p && ((p ~ 'player_type') != 'fake' || global_allow_fake);
_admin(p) -> (p ~ 'permission_level') >= 2;
_bar(p, text, color) -> run(str('title %s actionbar %s', p ~ 'name', encode_json({'text' -> text, 'color' -> color})));
_ent(tag) -> entity_id(global_ents:tag);
_in(q, b) -> q:0 >= b:'min':0 && q:0 < b:'max':0 + 1 && q:1 >= b:'min':1 - 0.5 && q:1 < b:'max':1 + 1 && q:2 >= b:'min':2 && q:2 < b:'max':2 + 1;
// inside = in the hall: not in the vestibule, not in an excluded box (the lift shaft), not riding anything (the lift car
// seats riders on armor stands) — so passing the club in the lift never starts the music
_inside(p) -> (
  q = pos(p);
  _in(q, global_L:'box') && !_in(q, global_L:'vestibule') && !query(p, 'mount') && first(global_L:'exclude' || [], _in(q, _)) == null
);
_one(tag, type, at, nbt) -> (
  e = _ent(tag); if (e, return(e));
  l = entity_selector(str('@e[type=%s,tag=%s]', type, tag));
  if (l, (global_ents:tag = query(l:0, 'uuid'); for (slice(l, 1), modify(_, 'remove')); return(l:0)));
  if (loaded_status(at) < 3 || tick_time() < (global_cool:tag || 0), return(null));
  global_cool:tag = tick_time() + 600;
  e = spawn(type, at, str('{Tags:["warehouse","%s"],%s}', tag, nbt));
  if (e, global_ents:tag = query(e, 'uuid'));
  e
);
_npc(tag, c, skin, extra) -> _one(tag, 'mannequin', c:'pos',
  str('Rotation:[%.1ff,0f],pose:"standing",immovable:1b,hide_description:1b,Invulnerable:1b,Silent:1b,profile:{model:"wide",texture:"%s"},CustomName:%s,CustomNameVisible:0b%s',
      c:'yaw', skin, encode_json({'text' -> c:'name', 'color' -> '#FF2A2A'}), extra));

// ───────────── quaternion helpers (the lasers) ─────────────
_qmul(a, b) -> [a:3 * b:0 + a:0 * b:3 + a:1 * b:2 - a:2 * b:1, a:3 * b:1 - a:0 * b:2 + a:1 * b:3 + a:2 * b:0,
                a:3 * b:2 + a:0 * b:1 - a:1 * b:0 + a:2 * b:3, a:3 * b:3 - a:0 * b:0 - a:1 * b:1 - a:2 * b:2];
// the rotation that turns +z into the direction (dx,dy,dz)
_aim(dx, dy, dz) -> (
  l = sqrt(dx * dx + dy * dy + dz * dz); dx = dx / l; dy = dy / l; dz = dz / l;
  yw = atan2(dx, dz); pt = asin(-dy);
  _qmul([0, sin(yw / 2), 0, cos(yw / 2)], [sin(pt / 2), 0, 0, cos(pt / 2)])
);

// ───────────── entities ─────────────
_ensure() -> (
  L = global_L; if (!L:'box', return());
  _npc('wh_bouncer', L:'bouncer', 'minecraft:entity/player/wide/steve',
    ',equipment:{chest:{id:"minecraft:leather_chestplate",components:{"minecraft:dyed_color":1315860}},legs:{id:"minecraft:leather_leggings",components:{"minecraft:dyed_color":1315860}},feet:{id:"minecraft:leather_boots",components:{"minecraft:dyed_color":1315860}}}');
  _npc('wh_dj', L:'dj', 'studio:entity/skin/bubblegum_punk', '');
  _npc('wh_bar', L:'bartender', 'studio:entity/skin/neon_diva', '');
  for (L:'beams', (
    i = _i; w = _:2;
    _one('wh_laser_' + i, 'block_display', _:0, str('teleport_duration:0,brightness:{sky:15,block:15},block_state:{Name:"minecraft:%s"},transformation:{left_rotation:[0f,0f,0f,1f],right_rotation:[0f,0f,0f,1f],translation:[%.3ff,%.3ff,0f],scale:[%.3ff,%.3ff,24f]}',
      _:1, -w / 2, -w / 2, w, w))
  ));
  W = L:'led_wall';
  if (W, _one('wh_led', 'text_display', W:'pos', str('Rotation:[0f,0f],billboard:"fixed",alignment:"center",line_width:2000,shadow:0b,background:-16777216,brightness:{sky:15,block:15},transformation:{left_rotation:[0f,0f,0f,1f],right_rotation:[0f,0f,0f,1f],translation:[0f,0f,0f],scale:[%.2ff,%.2ff,%.2ff]},text:""', W:'scale', W:'scale', W:'scale')));
  B = L:'ledbars';
  if (B, for (B:'cols', (
    sc = B:'scale';
    _one('wh_ledbar_' + _i, 'text_display', _, str('billboard:"vertical",alignment:"center",line_width:40,shadow:0b,background:0,brightness:{sky:15,block:15},transformation:{left_rotation:[0f,0f,0f,1f],right_rotation:[0f,0f,0f,1f],translation:[0f,0f,0f],scale:[%.2ff,%.2ff,%.2ff]},text:""', sc:0, sc:1, sc:2))
  )));
  for (L:'strips' || [], (
    i = _i; sc = _:'scale';
    _one('wh_strip_' + i, 'block_display', _:'pos', str('brightness:{sky:15,block:15},block_state:{Name:"minecraft:red_concrete"},transformation:{left_rotation:[0f,0f,0f,1f],right_rotation:[0f,0f,0f,1f],translation:[%.2ff,0f,%.2ff],scale:[%.2ff,%.2ff,%.2ff]}', -sc:0 / 2, -sc:2 / 2, sc:0, sc:1, sc:2))
  ));
  for (L:'crowd' || [], (
    i = _i; c = _; tag = 'wh_crowd_' + i;
    eq = if (c:'black', ',equipment:{chest:{id:"minecraft:leather_chestplate",components:{"minecraft:dyed_color":1315860}},legs:{id:"minecraft:leather_leggings",components:{"minecraft:dyed_color":1315860}}}', '');
    m = _one(tag, 'mannequin', c:'pos', str('Rotation:[%.1ff,0f],pose:"standing",immovable:1b,hide_description:1b,Invulnerable:1b,Silent:1b,profile:{model:"wide",texture:"%s"}%s', c:'yaw', c:'skin', eq));
    if (m && c:'kind' == 'sit' && !query(m, 'mount'), (                  // sitting = riding an invisible marker stand on the sofa
      st = _one(tag + '_seat', 'armor_stand', [c:'pos':0, c:'pos':1 + 0.5, c:'pos':2], str('Marker:1b,Invisible:1b,NoGravity:1b,Invulnerable:1b,Silent:1b,Rotation:[%.1ff,0f]', c:'yaw'));
      if (st, run(str('ride %s mount %s', query(m, 'uuid'), query(st, 'uuid'))))
    ))
  ))
);

// ───────────── music + show ─────────────
_music(t) -> (
  for (player('all'), (
    p = _; n = p ~ 'name';
    if (_real(p) && _inside(p), (
      s = global_music:n;
      if (s == null && t % 8 == 0, (                               // start on a beat → the kick lines up with the lights
        run(str('execute as %s at @s run playsound club:techno_loop record @s ~ ~ ~ 3 1', n)); global_music:n = t
      ), s != null && t - s >= global_loop, (
        run(str('execute as %s at @s run playsound club:techno_loop record @s ~ ~ ~ 3 1', n)); global_music:n = t
      ))
    ), global_music:n != null, (
      run(str('stopsound %s record club:techno_loop', n)); delete(global_music, n)
    ))
  ));
  for (keys(global_music), if (!player(_), delete(global_music, _)))
);
_show(t) -> (
  L = global_L;
  if (t % 8 == 0, (                                               // the kick
    k = floor(t / 8); ns = length(L:'strobes');
    if (k % 4 == 0, for (L:'strobes', set(_, 'light', 'level', '15')),           // bar downbeat: every strobe
      for (range(4), (q = L:'strobes':((k * 7 + _ * 5) % ns); set(q, 'light', 'level', '15'))));
    dj = _ent('wh_dj'); if (dj, modify(dj, 'swing'));
    _crowd(k); _led(k)
  ));
  if (t % 8 == 4, _led(floor(t / 8) + 0.5));
  if (t % 32 == 0, _strips(floor(t / 32)));
  if (t % 8 == 2, for (L:'strobes', set(_, 'light', 'level', '0')));
  if (t % 32 == 0, particle('end_rod', L:'chandelier', 40, 1.6, 0.08));
  if (t % 16 == 0, (                                              // the lasers pick new targets; the client glides there
    ph = t / 16;
    for (L:'beams', (
      i = _i; r = _:0; e = _ent('wh_laser_' + i); w = _:2;
      if (e, (
        tx = -64.5 + 8 * sin(ph * 37 + i * 60); tz = -107 + 6 * cos(ph * 29 + i * 45); ty = 31.2;
        q = _aim(tx - r:0, ty - r:1, tz - r:2);
        modify(e, 'nbt_merge', str('{start_interpolation:0,interpolation_duration:16,transformation:{left_rotation:[%.4ff,%.4ff,%.4ff,%.4ff],right_rotation:[0f,0f,0f,1f],translation:[%.3ff,%.3ff,0f],scale:[%.3ff,%.3ff,24f]}}', q:0, q:1, q:2, q:3, -w / 2, -w / 2, w, w))
      ))
    ))
  ));
  if (t % 6 == 0, for (L:'smoke', particle('white_smoke', _, 3, 1.4, 0.004)));
  if (t % 2 == 0, _ledbars(t))
);
_dark() -> for (global_L:'strobes', set(_, 'light', 'level', '0'));

// the crowd moves on the kick: dancers bob (standing/crouching), swing their arms and turn a little; couples sway
// together; seated people nod; a heart now and then
_crowd(k) -> (
  for (global_L:'crowd' || [], (
    c = _; i = _i; e = _ent('wh_crowd_' + i); if (!e, continue());
    kind = c:'kind';
    if (kind == 'dance', (
      down = (k + i) % 2 == 0;
      modify(e, 'nbt_merge', str('{pose:"%s"}', if (down, 'crouching', 'standing')));
      if ((k + i) % 2 == 1, modify(e, 'swing', if ((k + i) % 4 == 1, 'mainhand', 'offhand')));
      modify(e, 'yaw', c:'yaw' + 22 * sin(k * 47 + i * 83))
    ), kind == 'hug', (
      modify(e, 'yaw', c:'yaw' + 8 * sin(k * 45 + c:'pair' * 90));
      if (k % 8 == c:'pair' * 4 && i % 2 == 0, particle('heart', pos(e) + [0, 2.1, 0], 1, 0.1, 0))
    ), kind == 'sit', (
      if ((k + i) % 4 == 0, modify(e, 'swing'))
    ), kind == 'bar', (
      modify(e, 'yaw', c:'yaw' + 12 * sin(k * 31 + i * 90))
    ))
  ))
);
// LED bars hanging from the ceiling: each is ONE text_display of stacked "█" (billboard vertical, squeezed
// thin and tall), recoloured every 2 ticks. The bar decides the effect: waves red↔white, a rainbow, a white chase on the
// beat, and now and then one bar of fast strobe.
_hex(r, g, b) -> str('#%02X%02X%02X', max(0, min(255, round(r))), max(0, min(255, round(g))), max(0, min(255, round(b))));
_hsv(h) -> (h = h % 360; x = 1 - abs((h / 60) % 2 - 1);
  c = if (h < 60, [1, x, 0], h < 120, [x, 1, 0], h < 180, [0, 1, x], h < 240, [0, x, 1], h < 300, [x, 0, 1], [1, 0, x]);
  _hex(c:0 * 255, c:1 * 255, c:2 * 255));
_ledbar_mode(bar) -> (m = bar % 8; if (m == 7, 'strobe', m == 3 || m == 4, 'rainbow', m == 6, 'chase', 'wave'));
_ledbars(t) -> (
  B = global_L:'ledbars'; if (!B, return());
  n = B:'segs'; bar = floor(t / 32); mode = _ledbar_mode(bar); beatpos = (t % 8) / 8;
  for (B:'cols', (
    ci = _i; e = _ent('wh_ledbar_' + ci); if (!e, continue());
    comps = [];
    for (range(n), (
      sg = _;
      col = if (mode == 'strobe', if ((floor(t / 2) + ci) % 2 == 0, '#FFFFFF', '#000000'),
        mode == 'rainbow', _hsv(sg * 28 + t * 9 + ci * 23),
        mode == 'chase', (head = floor(beatpos * (n + 3)); if (abs(sg - head) < 1, '#FFFFFF', abs(sg - head) < 2.5, '#FF2A2A', '#140000')),
        (w = 0.5 + 0.5 * sin(sg * 40 - t * 22 + ci * 37); _hex(255, 42 + 213 * w * w, 42 + 213 * w * w)));
      comps += {'text' -> '█', 'color' -> col};
      if (sg < n - 1, comps += {'text' -> '\n'})
    ));
    modify(e, 'nbt_merge', str('{text:%s}', encode_json(comps)))
  ))
);

// the neon strips change colour every bar
global_strip_cols = ['red_concrete', 'magenta_concrete', 'white_concrete', 'light_blue_concrete', 'red_concrete', 'purple_concrete'];
_strips(bar) -> for (global_L:'strips' || [], (e = _ent('wh_strip_' + _i); if (e, modify(e, 'nbt_merge', str('{block_state:{Name:"minecraft:%s"}}', global_strip_cols:((bar + _i) % length(global_strip_cols)))))));
// the LED wall behind the DJ: one text_display of coloured "█" runs, a new frame twice per beat.
// Each bar picks a pattern: 0 equaliser bars · 1 expanding rings · 2 red chevrons · 3 strobe grid; every bar's first
// kick is a full white flash.
_led(k) -> (
  e = _ent('wh_led'); if (!e, return());
  W = global_L:'led_wall'; C = W:'cols'; R = W:'rows';
  half = k != floor(k); kk = floor(k); mode = floor(kk / 4) % 4;
  comps = [];
  for (range(R), (
    r = _; last = null; cnt = 0;
    for (range(C), (
      col = _led_px(kk, half, mode, _, r, C, R);
      if (col == last, cnt += 1, (
        if (last != null, comps += {'text' -> _blocks(cnt), 'color' -> last});
        last = col; cnt = 1))
    ));
    comps += {'text' -> _blocks(cnt), 'color' -> last};
    if (r < R - 1, comps += {'text' -> '\n'})
  ));
  modify(e, 'nbt_merge', str('{text:%s}', encode_json(comps)))
);
_blocks(n) -> (s = ''; loop(n, s += '█'); s);
_led_px(k, half, mode, x, r, C, R) -> (
  h2 = if (half, 1, 0);
  if (!half && k % 4 == 0, return(if (r % 2 == 0, '#FFFFFF', '#FFD6D6')));
  if (mode == 0, (
      h = floor(R * (0.3 + 0.65 * abs(sin(k * 53 + x * 29 + h2 * 17))));
      if (R - r <= h, if (R - r > h - 2, '#FF2A2A', '#7A0000'), '#000000')),
    mode == 1, (
      d = sqrt((x - C / 2) ^ 2 + ((r - R / 2) * 2) ^ 2); ph = (k * 2 + h2) * 1.5;
      if (abs(d - ph % 18) < 1.5, '#FF2A2A', abs(d - (ph + 9) % 18) < 1.2, '#4A6BFF', '#000000')),
    mode == 2, if ((x + abs(r - R / 2) + k * 2 + h2) % 8 < 2, '#FF2A2A', '#000000'),
    if ((x + r + k + h2) % 3 == 0, '#FFFFFF', '#000000'))
);

// ───────────── the door ─────────────
_gate(open) -> (
  o = if (open, 'true', 'false');
  for (global_L:'gate', (
    q = _:'pos';
    run(str('setblock %d %d %d iron_door[facing=%s,hinge=%s,half=lower,open=%s]', q:0, q:1, q:2, _:'facing', _:'hinge', o));
    run(str('setblock %d %d %d iron_door[facing=%s,hinge=%s,half=upper,open=%s]', q:0, q:1 + 1, q:2, _:'facing', _:'hinge', o))
  ));
  q = global_L:'gate':0:'pos';
  run(str('playsound minecraft:block.iron_door.%s master @a %d %d %d 0.8 0.9', if (open, 'open', 'close'), q:0, q:1, q:2));
  global_gate_open = open
);
_gate_poll(t) -> (
  g = global_L:'gate':0:'pos'; c = [g:0 + 1, g:1, g:2 + 0.5];
  want = first(player('all'), _real(_) && (d = sqrt(reduce(pos(_) - c, _a + _ * _, 0)); d < 2.6)
                             && ((global_ok:(_ ~ 'name') || 0) > t || _admin(_) || pos(_):2 < g:2)) != null;   // approved, admins, or leaving
  if (want != global_gate_open, _gate(want))
);
_black(p) -> (
  it = query(p, 'holds', 'chest'); if (!it, return(false));
  if (it:0 == 'netherite_chestplate', return(true));
  m = str(it:2) ~ 'dyed_color[^0-9-]*(-?\\d+)'; if (m == null, return(false));
  c = number(m); c = if (c < 0, c + 16777216, c);
  (floor(c / 65536) % 256) + (floor(c / 256) % 256) + (c % 256) < 180
);
_select(p) -> (
  n = p ~ 'name'; t = tick_time();
  if ((global_ok:n || 0) > t, return(_bar(p, 'Bouncer: "Go on in."', '#FF2A2A')));
  if (t - (global_no:n || -99999) < 1200, return(_bar(p, str('The bouncer is not looking at you. %d more seconds.', ceil((1200 - (t - global_no:n)) / 20)), 'gray')));
  run(str('title %s times 5 50 15', n));
  if (_admin(p) || _black(p) || rand(1) < 0.7, (
    global_ok:n = t + 1200;
    run(str('title %s title %s', n, encode_json({'text' -> 'Come in.', 'color' -> '#FF2A2A', 'bold' -> true})));
    run(str('title %s subtitle %s', n, encode_json({'text' -> if (_black(p), 'All black. Nice.', 'The gate is open for you for a minute'), 'color' -> 'gray'})))
  ), (
    global_no:n = t;
    run(str('title %s title %s', n, encode_json({'text' -> 'Not tonight.', 'color' -> '#FF2A2A', 'bold' -> true})));
    run(str('title %s subtitle %s', n, encode_json({'text' -> 'Try again in a minute · tip: wear black', 'color' -> 'gray'})))
  ))
);

// ───────────── the bar ─────────────
_bar_menu(p) -> (
  acts = map(keys(global_drinks), {'label' -> global_drinks:_:0, 'width' -> 160, 'action' -> {'type' -> 'run_command', 'command' -> '/warehouse drink ' + _}});
  d = {'type' -> 'minecraft:multi_action', 'title' -> {'text' -> '🍸 The bar', 'color' -> '#FF2A2A', 'bold' -> true},
       'body' -> [{'type' -> 'minecraft:plain_message', 'contents' -> {'text' -> 'What can I get you? (all alcohol-free)', 'color' -> 'white'}, 'width' -> 260}],
       'can_close_with_escape' -> true, 'pause' -> false, 'after_action' -> 'none', 'columns' -> 3, 'actions' -> acts,
       'exit_action' -> {'label' -> 'Close', 'width' -> 120, 'action' -> {'type' -> 'run_command', 'command' -> '/warehouse close'}}};
  run(str('dialog show %s %s', p ~ 'name', encode_json(d)))
);
_cmd_drink(id) -> (
  p = player(); if (!p, return(0)); n = p ~ 'name'; d = global_drinks:id; if (!d, return(0));
  run('dialog clear ' + n);
  if (unix_time() - (global_drink:n || 0) < 60000, return(_bar(p, 'Bartender: "One a minute, friend."', 'gray')));
  global_drink:n = unix_time();
  item = d:1;
  it = if (item ~ '\\[', replace(item, '\\]$', str(',custom_name={text:"%s",color:"#FF2A2A",italic:false}]', d:0)), str('%s[custom_name={text:"%s",color:"#FF2A2A",italic:false}]', item, d:0));
  run(str('give %s %s 1', n, it));
  bt = _ent('wh_bar'); if (bt, modify(bt, 'swing'));
  _bar(p, d:0 + ' ✦', '#FF2A2A'); 1
);
_cmd_close() -> (p = player(); if (p, run('dialog clear ' + p ~ 'name')); 1);

__on_player_interacts_with_entity(p, e, hand) -> (
  if (hand != 'mainhand' || !query(e, 'has_tag', 'warehouse'), return());
  if (query(e, 'has_tag', 'wh_bouncer'), return(_select(p)));
  if (query(e, 'has_tag', 'wh_bar'), return(_bar_menu(p)))
);

// ───────────── lifecycle ─────────────
__on_start() -> (global_L = read_file('layout', 'json') || {}; schedule(10, '_ensure'));
__on_tick() -> (
  t = tick_time(); L = global_L; if (!L:'box', return());
  if (t % 4 == 0, _gate_poll(t));
  _music(t);
  on = first(player('all'), _real(_) && _inside(_)) != null;
  if (on, _show(t), global_active, _dark());
  global_active = on;
  if (t % 100 == 41 && on, _ensure())
);
status() -> {'busy' -> false, 'active' -> global_active, 'listening' -> keys(global_music), 'gate_open' -> global_gate_open,
             'ents' -> length(filter(keys(global_ents), entity_id(global_ents:_)))};
