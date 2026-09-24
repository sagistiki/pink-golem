// cu.sc — ClawdBlock utilities: fast world reads, snapshots (undo), previews and checks, used by the MCP and by you.
// Call from RCON / minecraft_run_command:   script in cu run <fn>(args)
//   count(x1,y1,z1,x2,y2,z2)            -> {block: n}  (any size, air skipped)
//   occupied(x1,y1,z1,x2,y2,z2)         -> {count, min, max, examples}  built blocks only (natural terrain and wild plants ignored)
//   surface(x1,z1,x2,z2)                -> {min, max, avg}  ground height (y of the top natural block) over an area
//   level(x1,z1,x2,z2, y)               -> flatten an area: terrain up to y (grass on top), air above (up to y+40)
//   snap('name', x1,y1,z1,x2,y2,z2)     -> save every block (with states) to cu.data/snap_name.json  (≤300k blocks)
//   restore('name')                     -> put the snapshot back (only changed blocks are set)  = undo for any build
//   snaps() / unsnap('name')            -> list / delete saved snapshots
//   dark(x1,y1,z1,x2,y2,z2)             -> {spots, examples}  enclosed floor spots with block AND sky light 0 (mobs spawn there)
//   find('block', x,y,z, r)             -> positions of that block within r (max 60 results)
//   show(x1,y1,z1,x2,y2,z2, 'label', seconds) -> glowing outline + label for everyone (preview a build site)
//   mark(x,y,z,'text', seconds)         -> floating label at a spot
//   ytop(x,z)                           -> y of the highest non-air block at x,z (stand at ytop+1)
//   bstr(block)                         -> 'oak_stairs[facing=east,half=bottom,...]'
// Notes: set() takes a state string: set(x,y,z,'oak_stairs[facing=east]'). Container / sign contents are not snapshotted.

__config() -> {'stay_loaded' -> true, 'scope' -> 'global'};

global_natural = {'grass_block','dirt','coarse_dirt','podzol','rooted_dirt','mud','mycelium','sand','red_sand','gravel','clay','stone','deepslate',
  'granite','diorite','andesite','tuff','calcite','bedrock','snow','snow_block','ice','packed_ice','water','lava','sandstone','red_sandstone',
  'terracotta','netherrack','end_stone','moss_block','moss_carpet','short_grass','tall_grass','fern','large_fern','dead_bush','bush',
  'short_dry_grass','tall_dry_grass','leaf_litter','wildflowers','pink_petals','dandelion','poppy','seagrass','tall_seagrass','kelp','kelp_plant'};


_lohi(x1,y1,z1,x2,y2,z2) -> [[min(x1,x2),min(y1,y2),min(z1,z2)], [max(x1,x2),max(y1,y2),max(z1,z2)]];

bstr(b) -> (
  s = block_state(b);
  if (length(s) == 0, str(b),
    str(b) + '[' + join(',', map(pairs(s), str(_:0) + '=' + str(_:1))) + ']')
);

count(x1,y1,z1,x2,y2,z2) -> (
  m = {};
  volume(x1,y1,z1,x2,y2,z2, b = str(_); if (b != 'air' && b != 'cave_air', m:b = m:b + 1));
  m
);

_ground(b, y) -> has(global_natural, b);

occupied(x1,y1,z1,x2,y2,z2) -> (
  n = 0; lo = null; hi = null; ex = [];
  volume(x1,y1,z1,x2,y2,z2,
    b = str(_); p = pos(_);
    if (b != 'air' && b != 'cave_air' && !_ground(b, p:1),
      n += 1;
      if (lo == null, lo = copy(p); hi = copy(p),
        lo = [min(lo:0,p:0), min(lo:1,p:1), min(lo:2,p:2)];
        hi = [max(hi:0,p:0), max(hi:1,p:1), max(hi:2,p:2)]
      );
      if (length(ex) < 12, ex += str('%d %d %d %s', p:0, p:1, p:2, b))
    )
  );
  {'count' -> n, 'min' -> lo, 'max' -> hi, 'examples' -> ex}
);

snap(name, x1,y1,z1,x2,y2,z2) -> (
  [lo, hi] = _lohi(x1,y1,z1,x2,y2,z2);
  vol = (hi:0-lo:0+1) * (hi:1-lo:1+1) * (hi:2-lo:2+1);
  if (vol > 300000, return(str('too big: %d blocks (max 300000)', vol)));
  pal = {}; pl = []; data = [];
  for (range(lo:0, hi:0+1), x = _;
    for (range(lo:1, hi:1+1), y = _;
      for (range(lo:2, hi:2+1),
        s = bstr(block(x, y, _));
        if (!has(pal, s), pal:s = length(pl); pl += s);
        data += pal:s
      )
    )
  );
  write_file('snap_' + name, 'json', {'lo' -> lo, 'hi' -> hi, 'pal' -> pl, 'data' -> data});
  str('saved %s: %d blocks, %d kinds', name, vol, length(pl))
);

restore(name) -> (
  d = read_file('snap_' + name, 'json');
  if (!d, return('no snapshot ' + name));
  lo = d:'lo'; hi = d:'hi'; pl = d:'pal'; data = d:'data'; i = 0; n = 0;
  for (range(lo:0, hi:0+1), x = _;
    for (range(lo:1, hi:1+1), y = _;
      for (range(lo:2, hi:2+1),
        s = pl:(data:i); i += 1;
        if (bstr(block(x, y, _)) != s, set(x, y, _, s); n += 1)
      )
    )
  );
  str('restored %s: %d blocks changed', name, n)
);

snaps() -> map(filter(list_files('', 'json'), _ ~ 'snap_'), replace(_, '^snap_', ''));

dark(x1,y1,z1,x2,y2,z2) -> (
  n = 0; ex = [];
  volume(x1,y1,z1,x2,y2,z2,
    p = pos(_);
    if (air(_) && air(p:0, p:1+1, p:2) && solid(p:0, p:1-1, p:2) && block_light(_) == 0 && sky_light(_) == 0,
      n += 1; if (length(ex) < 15, ex += p)
    )
  );
  {'spots' -> n, 'examples' -> ex}
);

find(name, x, y, z, r) -> (
  l = [];
  volume(x-r, y-r, z-r, x+r, y+r, z+r, if (str(_) == name && length(l) < 60, l += pos(_)));
  l
);

show(x1,y1,z1,x2,y2,z2, label, secs) -> (
  [lo, hi] = _lohi(x1,y1,z1,x2,y2,z2);
  t = max(20, min(1200, secs * 20));
  draw_shape('box', t, {'from' -> lo, 'to' -> [hi:0+1, hi:1+1, hi:2+1], 'color' -> 0x55FFFFFF, 'fill' -> 0x55FFFF22, 'line' -> 3});
  draw_shape('label', t, {'pos' -> [(lo:0+hi:0+1)/2, hi:1+2, (lo:2+hi:2+1)/2], 'text' -> label, 'color' -> 0x55FFFFFF});
  'shown'
);

mark(x, y, z, text, secs) -> (
  draw_shape('label', max(20, min(1200, secs * 20)), {'pos' -> [x+0.5, y+0.5, z+0.5], 'text' -> text, 'color' -> 0xFFAA00FF});
  'marked'
);

ytop(x, z) -> (y = 319; while (y > -64 && air(x, y, z), 400, y += -1); y);

// ground height = top natural block (ignores builds on top of it)
_gy(x, z) -> (y = top('surface', x, 0, z) - 1; while (y > -64 && !has(global_natural, str(block(x, y, z))), 400, y += -1); y);
surface(x1, z1, x2, z2) -> (
  lo = 999; hi = -999; s = 0; n = 0;
  for (range(min(x1,x2), max(x1,x2)+1), x = _; for (range(min(z1,z2), max(z1,z2)+1), g = _gy(x, _); lo = min(lo, g); hi = max(hi, g); s += g; n += 1));
  {'min' -> lo, 'max' -> hi, 'avg' -> round(s / n)}
);
level(x1, z1, x2, z2, y) -> (
  [lo, hi] = _lohi(x1, y, z1, x2, y, z2);
  if ((hi:0-lo:0+1) * (hi:2-lo:2+1) > 40000, return('too big: max 40000 columns'));
  n = 0;
  for (range(lo:0, hi:0+1), x = _; for (range(lo:2, hi:2+1), z = _;
    for (range(y + 1, y + 41), if (!air(x, _, z), set(x, _, z, 'air'); n += 1));
    for (range(y - 3, y), if (air(x, _, z) || str(block(x, _, z)) == 'water', set(x, _, z, 'dirt'); n += 1));
    if (str(block(x, y, z)) != 'grass_block', set(x, y, z, 'grass_block'); n += 1)
  ));
  str('levelled %d columns at y %d (%d blocks changed)', (hi:0-lo:0+1) * (hi:2-lo:2+1), y, n)
);

unsnap(name) -> delete_file('snap_' + name, 'json');

// ───── used by the MCP ─────
// verify('id', k): compare the world with the expected blocks the MCP wrote to cu.data/verify_<id>_<k>.json
//   {pts: [[x,y,z,'name'], ...]}   -> {checked, mismatches, by_type, examples}
verify(id, k) -> (
  f = 'verify_' + id + '_' + k;
  d = read_file(f, 'json');
  if (!d, return({'error' -> 'no file ' + f}));
  bad = 0; ex = []; bt = {};
  for (d:'pts',
    p = _; b = str(block(p:0, p:1, p:2)); w = p:3;
    if (b != w && !(w == 'air' && (b == 'cave_air' || b == 'light')) && !(w == 'light' && b == 'air'),
      bad += 1; key = w + '>' + b; bt:key = bt:key + 1;
      if (length(ex) < 30, ex += str('%d %d %d want %s got %s', p:0, p:1, p:2, w, b))
    )
  );
  delete_file(f, 'json');
  {'checked' -> length(d:'pts'), 'mismatches' -> bad, 'by_type' -> bt, 'examples' -> ex}
);
// vfluid('id', box): water/lava in the box that the build did not place. Sources = real problems (a leak, a spill);
// flowing = usually intended (a fountain jet, a waterfall) unless it runs somewhere it shouldn't.
vfluid(id, x1, y1, z1, x2, y2, z2) -> (
  d = read_file('verify_' + id + '_wet', 'json');
  wet = {}; if (d, for (d:'pts', wet:_ = 1));
  n = 0; fl = 0; ex = [];
  volume(x1, y1, z1, x2, y2, z2,
    b = str(_);
    if ((b == 'water' || b == 'lava') && !has(wet, str('%d,%d,%d', pos(_):0, pos(_):1, pos(_):2)),
      if (str(block_state(_, 'level')) == '0',
        n += 1; if (length(ex) < 12, ex += str('%d %d %d %s source', pos(_):0, pos(_):1, pos(_):2, b)),
        fl += 1
      )
    )
  );
  {'stray_fluids' -> n, 'flowing' -> fl, 'examples' -> ex}
);
// monitor: mon_start('id') reads cu.data/mon_<id>.json
//   {every: ticks, count: n, track: ['BotName'], blocks: [[x,y,z,'label']], entities: [['@e[tag=x]','label']]}
// and writes cu.data/mon_<id>_out.json when done: {samples: [{t, p:{name:[x,y,z,mount]}, b:{label:state}, e:{label:[n,[x,y,z]]}}]}
global_mon = {};
mon_start(id) -> (
  spec = read_file('mon_' + id, 'json');
  if (!spec, return('no spec'));
  global_mon:id = {'spec' -> spec, 'out' -> [], 't0' -> tick_time()};
  _mon_tick(id, 0);
  'started'
);
_mon_tick(id, i) -> (
  m = global_mon:id; spec = m:'spec';
  s = {'t' -> tick_time() - m:'t0'};
  p = {}; for (spec:'track', q = player(_); if (q, v = query(q, 'mount'); p:_ = [pos(q):0, pos(q):1, pos(q):2, if(v, str(v), null)]));
  s:'p' = p;
  b = {}; for (spec:'blocks', b:(_:3) = bstr(block(_:0, _:1, _:2))); s:'b' = b;
  e = {}; for (spec:'entities', l = entity_selector(_:0); e:(_:1) = [length(l), if(length(l), pos(l:0), null)]); s:'e' = e;
  m:'out' += s;
  if (i + 1 < spec:'count',
    schedule(spec:'every', '_mon_tick', id, i + 1),
    write_file('mon_' + id + '_out', 'json', {'samples' -> m:'out'}); delete(global_mon, id); delete_file('mon_' + id, 'json')
  )
);
