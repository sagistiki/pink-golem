// bubble.sc — speech bubbles that float above a player's head (Claude and the helper builders).
// script in bubble run say('Golem', 'text', seconds)      clear('Golem')
__config() -> {'stay_loaded' -> true, 'scope' -> 'global'};

global_b = {};   // name -> [uuid, until_tick]
global_h = 2.45; // height above feet

__on_start() -> run('kill @e[type=text_display,tag=bubble]');

say(name, text, secs) -> (
  p = player(name);
  if (!p, return('no player ' + name));
  clear(name);
  nbt = str('{billboard:"center",Tags:["bubble"],alignment:"center",line_width:170,teleport_duration:3,see_through:0b,shadow:1b,background:-1439485133,transformation:{left_rotation:[0f,0f,0f,1f],right_rotation:[0f,0f,0f,1f],translation:[0f,0f,0f],scale:[0.62f,0.62f,0.62f]},text:%s}', encode_json({'text' -> text, 'color' -> 'white'}));
  e = spawn('text_display', pos(p) + [0, global_h, 0], nbt);
  global_b:name = [query(e, 'uuid'), tick_time() + max(40, round(secs * 20))];
  'ok'
);

clear(name) -> (
  v = global_b:name;
  if (v, e = entity_id(v:0); if (e, modify(e, 'remove')); delete(global_b, name));
  'cleared'
);

__on_tick() -> (
  for (keys(global_b),
    n = _; v = global_b:n; e = entity_id(v:0); p = player(n);
    if (!e || !p || tick_time() > v:1,
      if (e, modify(e, 'remove')); delete(global_b, n),
      modify(e, 'pos', pos(p) + [0, global_h, 0])
    )
  )
);
