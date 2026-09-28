// protect.sc — build protection for players' own builds (a player asked that only they may add to and edit their tower). A zone is a box with an owner; inside it only the owner (and players the owner trusts) can
// break, place, pour buckets, strip/till, edit signs or touch item frames / armor stands. Everyone else can still walk
// in, open doors, gates and trapdoors, and press buttons and levers — visiting is fine, changing is not.
// Data: protect.data/zones.json = {"zones":[{name, owner (MC name), trusted:[names], min:[x,y,z], max:[x,y,z]}]}
// (inclusive block bounds; use the whole height -64..320 so the owner can keep building up).
// How: Carpet lets these events be cancelled by returning 'cancel' (checked in the 26.2 jar's mixins):
//   player_breaks_block · player_placing_block (BEFORE the block goes in) · player_right_clicks_block ·
//   player_uses_item (buckets aim with a raycast, not at a block) · player_interacts_with_entity · player_attacks_entity.
// NOT covered (they don't go through these events): WorldEdit / Axiom / commands like /fill, TNT, fire, pistons —
// Ledger (/ledger rollback) undoes those if it ever happens.
// Commands: /protect (what zone am I in) · /protect list · /protect trust <player> · /protect untrust <player> (owner) ·
//   /protect show (outline for 10 s) · /protect bypass (op only, toggled per op, the owner is told) · /protect reload (op).

__config() -> {
  'stay_loaded' -> true, 'scope' -> 'global', 'command_permission' -> 'all',
  'commands' -> {
    '' -> '_cmd_here', 'list' -> '_cmd_list', 'show' -> '_cmd_show', 'reload' -> '_cmd_reload', 'bypass' -> '_cmd_bypass',
    'trust <who>' -> _(w) -> _cmd_trust(w, true), 'untrust <who>' -> _(w) -> _cmd_trust(w, false)
  },
  'arguments' -> {'who' -> {'type' -> 'term', 'suggester' -> _(args) -> map(player('all'), str(_))}}
};

global_zones = [];
global_bypass = {};    // op name -> true while they bypass (never saved: a restart turns it off)
global_warned = {};    // player name -> tick_time() of the last warning (one actionbar per 2 s)

_load() -> (
  d = read_file('zones', 'json');
  global_zones = if (type(d) == 'map' && d:'zones', d:'zones', []);
  length(global_zones)
);
_save() -> write_file('zones', 'json', {'zones' -> global_zones});

_inside(q, z) -> (
  a = z:'min'; b = z:'max';
  q:0 >= a:0 && q:0 < b:0 + 1 && q:1 >= a:1 && q:1 < b:1 + 1 && q:2 >= a:2 && q:2 < b:2 + 1
);
_zone_at(q) -> first(global_zones, _inside(q, _));
_lc(s) -> lower(str(s));
_may(p, z) -> (
  n = _lc(p ~ 'name');
  n == _lc(z:'owner') || first(z:'trusted' || [], _lc(_) == n) != null || global_bypass:(p ~ 'name')
);
// the check every handler uses: true = let it happen
_ok(p, q) -> (
  z = _zone_at(q);
  if (!z || _may(p, z), return(true));
  n = p ~ 'name'; t = tick_time();
  if (t - (global_warned:n || -100) > 40, (
    global_warned:n = t;
    msg = z:'msg' || str('only %s can build or change things here', z:'label' || z:'owner');
    run(str('title %s actionbar %s', n, encode_json({'text' -> str('🔒 %s — %s', z:'name', msg), 'color' -> '#FF8FC8'})));
    run(str('execute as %s at @s run playsound minecraft:block.note_block.bass master @s ~ ~ ~ 0.6 0.7', n))
  ));
  false
);

// ── the guarded actions ─────────────────────────────────────────────────────
__on_player_breaks_block(p, b) -> if (!_ok(p, pos(b)), 'cancel');
__on_player_placing_block(p, item, hand, b) -> if (!_ok(p, pos(b)), 'cancel');

// right-click on a block: visitors may use doors / gates / trapdoors / buttons / levers (not while sneaking with an
// item — that skips the block and uses the item on it); everything else (signs, pots, axes, hoes, bone meal, flint,
// lecterns, note blocks, repeaters...) is the owner's
global_visitor_ok = '(_door|_trapdoor|_fence_gate|_button|^lever|_pressure_plate)$';
__on_player_right_clicks_block(p, item, hand, b, face, hitvec) -> (
  q = pos(b);
  z = _zone_at(q);
  if (!z || _may(p, z), return());
  if ((str(b) ~ global_visitor_ok) != null && !(query(p, 'sneaking') && item), return());
  if (!_ok(p, q), 'cancel')
);

// buckets (and anything else that aims by raycast): check where the player is looking and where they stand
__on_player_uses_item(p, item, hand) -> (
  if (!item || (item:0 ~ 'bucket$|^boat$|_boat$|_raft$|end_crystal|armor_stand|minecart$') == null, return());
  tr = query(p, 'trace', 6, 'blocks', 'liquids');
  q = if (tr, pos(tr), pos(p));
  if (!_ok(p, q) || !_ok(p, pos(p)), 'cancel')
);

// decorations that are entities
global_deco = {'item_frame', 'glow_item_frame', 'armor_stand', 'painting', 'leash_knot', 'minecart', 'chest_minecart', 'boat'};
_is_deco(e) -> has(global_deco, e ~ 'type') || (e ~ 'type' ~ '_boat$|_raft$|_chest_boat$') != null;
__on_player_interacts_with_entity(p, e, hand) -> if (_is_deco(e) && !_ok(p, pos(e)), 'cancel');
__on_player_attacks_entity(p, e) -> if (_is_deco(e) && !_ok(p, pos(e)), 'cancel');

// ── commands ────────────────────────────────────────────────────────────────
_say(p, t) -> if (p, print(p, format('#FF8FC8 ' + t)), print(t));
_cmd_here() -> (
  p = player(); if (!p, return(_cmd_list()));
  z = _zone_at(pos(p));
  if (!z, return(_say(p, 'No protected zone here. /protect list shows them all')));
  _say(p, str('🔒 %s · owner: %s%s. %s', z:'name', z:'label' || z:'owner',
    if (z:'trusted', ' · trusted: ' + join(', ', z:'trusted'), ''),
    if (_may(p, z), 'You can build here ✔', 'You can visit, not change')));
  1
);
_cmd_list() -> (
  p = player();
  if (!global_zones, return(_say(p, 'No protected zones')));
  for (global_zones, _say(p, str('🔒 %s — %s · %d,%d,%d → %d,%d,%d', _:'name', _:'label' || _:'owner', _:'min':0, _:'min':1, _:'min':2, _:'max':0, _:'max':1, _:'max':2)));
  1
);
_cmd_trust(who, on) -> (
  p = player(); if (!p, return(0));
  mine = filter(global_zones, _lc(_:'owner') == _lc(p ~ 'name'));
  if (!mine, return(_say(p, 'Only a zone owner can trust builders')));
  for (mine, (
    z = _; l = filter(z:'trusted' || [], _lc(_) != _lc(who));
    if (on, l += who);
    z:'trusted' = l
  ));
  _save();
  _say(p, str(if (on, '✔ %s can now build in your zone', '✖ %s can no longer build in your zone'), who));
  1
);
_cmd_show() -> (
  p = player(); if (!p, return(0));
  z = _zone_at(pos(p)) || first(sort_key(copy(global_zones), _d(p, _)), true);
  if (!z, return(_say(p, 'No zones')));
  y = floor(pos(p):1);
  lo = [z:'min':0, max(z:'min':1, y - 2), z:'min':2]; hi = [z:'max':0 + 1, min(z:'max':1 + 1, y + 10), z:'max':2 + 1];
  for (range(10), schedule(_ * 20, _(outer(lo), outer(hi)) -> particle_rect('end_rod', lo, hi, 2)));
  _say(p, '✨ Outlining ' + z:'name' + ' for 10 seconds');
  1
);
_d(p, z) -> (q = pos(p); c = (z:'min' + z:'max') / 2; (q:0 - c:0) ^ 2 + (q:2 - c:2) ^ 2);
_cmd_reload() -> (
  p = player(); if (p && (p ~ 'permission_level') < 2, return(_say(p, 'Admins only')));
  _say(p, str('Loaded %d zones', _load()));
  1
);
_cmd_bypass() -> (
  p = player(); if (!p || (p ~ 'permission_level') < 2, return(_say(p, 'Admins only')));
  n = p ~ 'name';
  if (global_bypass:n, delete(global_bypass, n), global_bypass:n = true);
  st = if (global_bypass:n, 'now bypasses the protection', 'respects the protection again');
  _say(p, n + ' ' + st);
  // transparency: owners who are online hear about it
  for (global_zones, o = player(_:'owner'); if (o && o != p, _say(o, str('ℹ %s %s', n, st))));
  1
);

__on_start() -> _load();
status() -> {'busy' -> false, 'zones' -> map(global_zones, _:'name'), 'bypass' -> keys(global_bypass)};
