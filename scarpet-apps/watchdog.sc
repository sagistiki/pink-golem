// watchdog.sc — lag watchdog: names what makes the server slow, tells the ops once, removes only obvious junk.
// Cheap by design: once a second it reads the last 20 tick times (system_info) and nothing else.
// When the average tick stays above lag_mspt for lag_seconds it opens an INCIDENT: one entity census
// (by type, by chunk, by scoreboard tag = which app or build owns them), names the likely culprit, appends one
// JSON line to watchdog.data/incidents.txt and tells the ops who are online (one message per issue per
// alert_minutes). Every baseline_minutes (while people are online) it also takes a quiet census, so a later
// incident can say what CHANGED, and it reports stacks of identical copies of one entity on one block (a leak:
// something re-creates it). The ONLY thing it removes by itself: over junk_items dropped items (or junk_xp xp
// orbs) in ONE chunk, never named or tagged ones. Everything else is report-only.
// Used by the MCP tool minecraft_watchdog. By hand: script in watchdog run status() | census(8) | cost()
// | config_set('lag_mspt', 40). watchdog.data/config.json overrides the defaults below
// (e.g. {"alerts": "dry"} keeps the messages in status() instead of chat — for testing).

__config() -> {'stay_loaded' -> true, 'scope' -> 'global'};

global_cfg = {
    'lag_mspt' -> 45,          // mean tick time over lag_seconds above this = incident (50 = the server falls behind)
    'lag_seconds' -> 15,
    'recover_mspt' -> 30,      // incident closes when the mean over recover_seconds drops below this
    'recover_seconds' -> 30,
    'min_gap_s' -> 120,        // no new incident this soon after the last one closed
    'freeze_ms' -> 2000,       // a single tick this long = a freeze (logged, no chat)
    'baseline_minutes' -> 10,  // a quiet census this often, to tell what changed when lag starts
    'junk_items' -> 1000,      // dropped items in ONE chunk above this are removed
    'junk_xp' -> 500,          // same for experience orbs
    'alert_minutes' -> 10,     // at most one chat message per issue per this many minutes
    'alerts' -> true,          // true | false | 'dry' (keep them in status() instead of chat)
    'mitigate' -> true,        // false = report junk, never remove it
    'census_top' -> 8,
    'stack_alert' -> 100,      // this many copies of one entity on one block = tell the ops (report only)
    'stack_repeat_hours' -> 6
};
global_hist = [];              // [mean_ms, max_ms] per 20-tick window, newest last (300 = ~5 min)
global_incident = null;
global_closed_at = 0;
global_baseline = null;
global_last_alert = {};
global_last_freeze = 0;
global_junk_logged = 0;
global_outbox = [];
global_mob = {};
global_wcache = {};
global_lines = 0;
global_cost = {};
global_last_full = {};

__on_start() -> (
    c = read_file('config', 'json');
    if (c, for (keys(c), global_cfg:_ = c:_));
    // mobs with AI (entity_types('living') also lists display entities, so build the set from the mob categories)
    for (['monster', 'creature', 'ambient', 'water_creature', 'water_ambient', 'underground_water_creature', 'axolotls'],
        for (entity_types(_), global_mob:_ = true));
    for (['villager', 'wandering_trader', 'iron_golem', 'snow_golem', 'copper_golem'], global_mob:_ = true);
    old = read_file('incidents', 'text');
    global_lines = if (old, length(old), 0);
    schedule(20, '_loop');
    schedule(1200, '_junk_loop');
    schedule(2400, '_baseline_loop');
);

// ───────────── the one-second sample ─────────────
_window() -> (
    s = 0; m = 0;
    for (slice(system_info('server_last_tick_times'), 0, 20), s += _; if (_ > m, m = _));
    [s / 20, m]
);

_mean(k) -> (
    h = global_hist; n = length(h); s = 0;
    for (range(n - k, n), s += h:_:0);
    s / k
);

_loop() -> (
    schedule(20, '_loop');
    w = _window();
    global_hist += w;
    if (length(global_hist) > 300, delete(global_hist, 0));
    if (w:1 > global_cfg:'freeze_ms', _freeze(w:1));
    n = length(global_hist);
    if (global_incident == null,
        if (n >= global_cfg:'lag_seconds' && _mean(global_cfg:'lag_seconds') > global_cfg:'lag_mspt', _open()),
        if (w:0 > global_incident:'peak', global_incident:'peak' = w:0);
        if (n >= global_cfg:'recover_seconds' && _mean(global_cfg:'recover_seconds') < global_cfg:'recover_mspt', _close())
    )
);

_open() -> (
    now = unix_time();
    if (now - global_closed_at < global_cfg:'min_gap_s' * 1000, return());
    mean = _mean(global_cfg:'lag_seconds');
    global_incident = {'start' -> now, 'peak' -> mean};
    c = _census(global_cfg:'census_top');
    inc = {'kind' -> 'lag', 'mspt' -> _r1(mean), 'culprit' -> c:'culprit', 'census' -> c,
        'tick_query' -> run('tick query'):1, 'players' -> _where()};
    removed = _sweep(c:'junk');
    if (removed, inc:'removed' = removed);
    _log(inc);
    _alert('lag', str('The server is lagging: %d ms per tick on average (healthy is under 50). Likely cause: %s. %s', round(mean), c:'culprit',
        if (removed, 'The junk pile was removed.', 'Nothing was changed, report only.')), global_cfg:'alert_minutes');
);

_close() -> (
    now = unix_time();
    _log({'kind' -> 'lag_end', 'seconds' -> round((now - global_incident:'start') / 1000), 'peak_mspt' -> _r1(global_incident:'peak')});
    global_incident = null;
    global_closed_at = now;
);

_freeze(m) -> (
    now = unix_time();
    if (now - global_last_freeze < 60000, return());
    global_last_freeze = now;
    _log({'kind' -> 'freeze', 'tick_ms' -> round(m), 'players' -> _where()});
);

// ───────────── census: what is loaded, where, and who owns it ─────────────
_wt(t) -> (
    w = global_wcache:t;
    if (w != null, return(w));
    w = if (t == 'player', 0,
        t == 'villager' || t == 'wandering_trader', 6,
        t == 'armor_stand', 0.3,
        t == 'mannequin', 0.5,
        global_mob:t, 2,
        (t ~ 'minecart') != null || (t ~ '_boat$') != null || (t ~ '_raft$') != null || t == 'falling_block' || t == 'tnt', 2,
        t == 'item' || t == 'experience_orb', 1,
        (t ~ '_display$') != null || t == 'marker' || t == 'interaction', 0.05,
        t == 'painting' || (t ~ 'item_frame$') != null || t == 'leash_knot', 0.1,
        0.5);
    global_wcache:t = w;
    w
);

_top(m, k) -> (
    l = sort_key(pairs(m), -_:1);
    if (l, slice(l, 0, min(k, length(l))), [])
);

// chunk key as ONE number (list keys made the census 3x slower): dimension index, chunk x, chunk z
_ck(di, cx, cz) -> di * 100000000000 + (cx + 50000) * 100000 + cz + 50000;
_unck(k) -> (di = floor(k / 100000000000); r = k - di * 100000000000; [di, floor(r / 100000) - 50000, r % 100000 - 50000]);

_census(top) -> (
    t0 = time();
    dims = system_info('world_dimensions');
    types = {}; tags = {}; cn = {}; cs = {}; ci = {}; co = {}; total = 0; score = 0;
    for (dims,
        di = _i;
        in_dimension(_, for (entity_list('*'),
            t = _~'type';
            if (t != 'player',
                w = _wt(t);
                total += 1; score += w;
                types:t = types:t + 1;
                k = _ck(di, floor(_~'x' / 16), floor(_~'z' / 16));
                cn:k = cn:k + 1;
                cs:k = cs:k + w;
                if (t == 'item', ci:k = ci:k + 1, t == 'experience_orb', co:k = co:k + 1);
                tg = _~'scoreboard_tags';
                if (tg, g = split('_', tg:0):0; tags:g = tags:g + 1)
            )
        ))
    );
    // second, small pass inside the hottest chunks (by server cost and by plain count): types, owners, stacked copies
    hot = _top(cs, top);
    dl = _top(cn, top);
    todo = {};
    for (hot, todo:(_:0) = true);
    for (slice(dl, 0, min(3, length(dl))), todo:(_:0) = true);
    detail = {}; stacks = {};
    for (keys(todo),
        k = _; u = _unck(k); dim = dims:(u:0); ty = {}; tg = {};
        in_dimension(dim, for (entity_area('*', [u:1 * 16 + 8, 128, u:2 * 16 + 8], [8, 200, 8]),
            t = _~'type';
            if (t != 'player',
                ty:t = ty:t + 1;
                s = _~'scoreboard_tags';
                if (s, g = split('_', s:0):0; tg:g = tg:g + 1);
                sk = str('%s;%s;%d;%d;%d;%s', t, if (s, join(',', sort(s)), ''), floor(_~'x'), floor(_~'y'), floor(_~'z'), dim);
                stacks:sk = stacks:sk + 1
            )));
        detail:k = [ty, tg]
    );
    chunks = map(hot, p = _; d = detail:(p:0); u = _unck(p:0);
        {'dim' -> dims:(u:0), 'cx' -> u:1, 'cz' -> u:2, 'x' -> u:1 * 16 + 8, 'z' -> u:2 * 16 + 8, 'n' -> cn:(p:0), 'score' -> _r1(p:1),
         'types' -> _top(d:0, 4), 'tags' -> _top(d:1, 3)});
    // most entities by plain count (display entities cost the server little but the players' FPS a lot)
    dense = map(dl, u = _unck(_:0); {'dim' -> dims:(u:0), 'x' -> u:1 * 16 + 8, 'z' -> u:2 * 16 + 8, 'n' -> _:1});
    // many copies of the same entity on the same block = something keeps re-creating it (a leak), not a design
    stacked = [];
    for (pairs(stacks), if (_:1 >= 10, f = split(';', _:0);
        stacked += {'type' -> f:0, 'tags' -> f:1, 'x' -> number(f:2), 'y' -> number(f:3), 'z' -> number(f:4), 'dim' -> f:5, 'n' -> _:1}));
    stacked = sort_key(stacked, -(_:'n'));
    if (length(stacked) > 5, stacked = slice(stacked, 0, 5));
    // identical copies = a leak; parts of one assembly (a wheel, a screen of pixels) share a spot but differ
    for (filter(stacked, _:'n' >= 50), x = _;
        es = in_dimension(x:'dim', filter(entity_area(x:'type', [x:'x' + 0.5, x:'y' + 0.5, x:'z' + 0.5], [0.6, 0.6, 0.6]),
            s = _~'scoreboard_tags'; if (s, join(',', sort(s)), '') == x:'tags'));
        sig = if (es, map(slice(es, 0, min(3, length(es))), n = _~'nbt'; str([n:'transformation', n:'text', n:'block_state', n:'item', n:'Rotation'])), []);
        x:'checked' = length(sig);
        x:'identical' = length(sig) >= 2 && length(filter(sig, _ != sig:0)) == 0
    );
    junk = [];
    for (pairs(ci), if (_:1 >= global_cfg:'junk_items', u = _unck(_:0);
        junk += {'dim' -> dims:(u:0), 'cx' -> u:1, 'cz' -> u:2, 'type' -> 'item', 'n' -> _:1}));
    for (pairs(co), if (_:1 >= global_cfg:'junk_xp', u = _unck(_:0);
        junk += {'dim' -> dims:(u:0), 'cx' -> u:1, 'cz' -> u:2, 'type' -> 'experience_orb', 'n' -> _:1}));
    delta = []; tdelta = [];
    if (global_baseline,
        bt = global_baseline:'types';
        for (pairs(types), b = bt:(_:0); if (b == null, b = 0); d = _:1 - b; if (d > 0, delta += [_:0, _:1, b, d * _wt(_:0)]));
        delta = sort_key(delta, -_:3);
        bg = global_baseline:'tags';
        for (pairs(tags), b = bg:(_:0); if (b == null, b = 0); d = _:1 - b; if (d > 0, tdelta += [_:0, _:1, b, d]));
        tdelta = sort_key(tdelta, -_:3)
    );
    global_last_full = {'types' -> types, 'tags' -> tags};
    c = {'entities' -> total, 'score' -> _r1(score), 'types' -> _top(types, 12), 'tags' -> _top(tags, 12),
         'chunks' -> chunks, 'dense' -> dense, 'stacked' -> stacked, 'junk' -> junk, 'delta' -> if (delta, slice(delta, 0, min(5, length(delta))), []), 'tag_delta' -> if (tdelta, slice(tdelta, 0, min(5, length(tdelta))), []),
         'baseline_age_min' -> if (global_baseline, round((unix_time() - global_baseline:'t') / 60000), null)};
    _name_culprit(c);
    c:'ms' = _r1(time() - t0);
    c
);

_name_culprit(c) -> (
    en = [];
    st = filter(c:'stacked', _:'identical');
    if (st && st:0:'n' >= 50,
        x = st:0;
        en += str('%d stacked copies of %s [%s] on one block at %d,%d,%d (%s): something keeps re-creating it', x:'n', x:'type', x:'tags', x:'x', x:'y', x:'z', x:'dim')
    );
    d = c:'delta';
    if (d && d:0:3 >= 30,
        x = d:0;
        en += str('sharp rise: %d %s now, %d %d min ago', x:1, x:0, x:2, c:'baseline_age_min')
    );
    td = c:'tag_delta';
    if (td && td:0:3 >= 100,
        x = td:0;
        en += str('entities tagged %s_* grew to %d (%d before)', x:0, x:1, x:2)
    );
    h = c:'chunks';
    if (h && h:0:'score' >= 60,
        x = h:0; ty = x:'types'; tg = x:'tags';
        main = if (ty, ty:0, ['?', 0]);
        own = if (tg, tg:0:0, null);
        en += str('hotspot: %d entities in chunk %d,%d near %d,%d (%s), mostly %d %s%s', x:'n', x:'cx', x:'cz', x:'x', x:'z', x:'dim',
            main:1, main:0, if (own, ' tagged ' + own + '_*', ''))
    );
    if (c:'junk',
        j = c:'junk':0;
        en += str('junk: %d %s in one chunk near %d,%d', j:'n', j:'type', j:'cx' * 16 + 8, j:'cz' * 16 + 8)
    );
    if (!en,
        en += 'no unusual entity load: likely chunk loading/generation, a heavy app, or memory/swap on the host'
    );
    c:'culprit' = join('; ', en);
);

// ───────────── junk: the only automatic fix ─────────────
_sweep(junk) -> (
    out = [];
    for (junk,
        j = _;
        if (global_cfg:'mitigate' == true,
            n = 0;
            in_dimension(j:'dim', for (entity_area(j:'type', [j:'cx' * 16 + 8, 128, j:'cz' * 16 + 8], [8, 200, 8]),
                if (_~'custom_name' == null && !_~'scoreboard_tags', modify(_, 'remove'); n += 1)));
            if (n > 0,
                out += {'dim' -> j:'dim', 'x' -> j:'cx' * 16 + 8, 'z' -> j:'cz' * 16 + 8, 'type' -> j:'type', 'removed' -> n};
                _alert('junk', str('Removed %d %s piled up in one chunk near %d,%d (%s). They were slowing the server.', n,
                    if (j:'type' == 'item', 'dropped items', 'xp orbs'), j:'cx' * 16 + 8, j:'cz' * 16 + 8, j:'dim'), global_cfg:'alert_minutes')
            )
        )
    );
    out
);

_junk_loop() -> (schedule(1200, '_junk_loop'); _junk_check());
_junk_check() -> (
    big = false;
    for (system_info('world_dimensions'), d = _;
        in_dimension(d, if (length(entity_list('item')) >= global_cfg:'junk_items' || length(entity_list('experience_orb')) >= global_cfg:'junk_xp', big = true)));
    if (big,
        c = _census(3);
        if (c:'junk',
            r = _sweep(c:'junk');
            // with mitigate off the same pile would be logged every minute: once per alert_minutes is enough
            if (r || unix_time() - global_junk_logged > global_cfg:'alert_minutes' * 60000,
                global_junk_logged = unix_time();
                _log({'kind' -> 'junk', 'junk' -> c:'junk', 'removed' -> r, 'mitigate' -> global_cfg:'mitigate'});
                if (!r, j = c:'junk':0; _alert('junk', str('A pile of %d %s in one chunk near %d,%d (%s). Not removed (mitigate is off), report only.',
                    j:'n', j:'type', j:'cx' * 16 + 8, j:'cz' * 16 + 8, j:'dim'), global_cfg:'alert_minutes'))
            )
        )
    )
);

_baseline_loop() -> (schedule(global_cfg:'baseline_minutes' * 1200, '_baseline_loop'); _baseline(false));
_baseline(force) -> (
    if (!force && !_humans(), return());   // nobody on: nothing to watch
    quiet = global_incident == null && length(global_hist) >= 30 && _mean(30) < global_cfg:'recover_mspt';
    c = _census(4);
    if (force || quiet, global_baseline = {'t' -> unix_time(), 'types' -> global_last_full:'types', 'tags' -> global_last_full:'tags'});
    _stack_alert(c);
);

// the most specific tag of 'arena,arena_screen' = arena_screen
_longest(t) -> (b = ''; for (split(',', t), if (length(_) > length(b), b = _)); if (b, b, 'untagged entity'));

// report-only: one message per set of stacks per stack_repeat_hours
_stack_alert(c) -> (
    big = filter(c:'stacked', _:'identical' && _:'n' >= global_cfg:'stack_alert');
    if (!big, return());
    big = slice(big, 0, min(3, length(big)));
    key = 'stacked:' + join(',', map(big, _:'tags'));
    names = join(', ', map(big, str('%d copies of %s near %d,%d', _:'n', _longest(_:'tags'), _:'x', _:'z')));
    if (_alert(key, str('Found entities copied over and over on one spot: %s. Probably an app re-creates them whenever their area was unloaded. They slow down the server and the game for every player. Nothing was changed, report only.', names),
            global_cfg:'stack_repeat_hours' * 60),
        _log({'kind' -> 'stacked', 'stacks' -> big})
    );
);

// ───────────── people, chat, log ─────────────
_humans() -> filter(player('all'), t = _~'player_type'; t != 'fake' && t != 'shadow');
_ops() -> filter(_humans(), _~'permission_level' >= 2);
_where() -> map(_humans(), p = pos(_); [_~'name', _~'dimension', round(p:0), round(p:1), round(p:2)]);

_send(players, msg) -> for (players, print(_, format('#e8a33d [Watchdog] ', 'w ' + msg)));

_alert(issue, msg, minutes) -> (
    mode = global_cfg:'alerts';
    if (mode == false, return(false));
    now = unix_time();
    last = global_last_alert:issue;
    if (last != null && now - last < minutes * 60000, return(false));
    ops = _ops();
    if (!ops, return(false));
    global_last_alert:issue = now;
    if (mode == 'dry',
        global_outbox += {'issue' -> issue, 'to' -> map(ops, _~'name'), 'msg' -> msg, 'time' -> _now()};
        if (length(global_outbox) > 20, delete(global_outbox, 0)),
        _send(ops, msg)
    );
    _log({'kind' -> 'alert', 'issue' -> issue, 'to' -> map(ops, _~'name'), 'dry' -> mode == 'dry'});
    true
);

_now() -> (d = convert_date(unix_time()); str('%04d-%02d-%02dT%02d:%02d:%02d', d:0, d:1, d:2, d:3, d:4, d:5));
_r1(v) -> round(v * 10) / 10;

_log(o) -> (
    o:'time' = _now();
    o:'t' = unix_time();
    o:'source' = 'watchdog.sc';
    if (global_lines > 4000,
        keep = read_file('incidents', 'text');
        delete_file('incidents_old', 'text');
        write_file('incidents_old', 'text', keep);
        delete_file('incidents', 'text');
        global_lines = 0
    );
    write_file('incidents', 'text', encode_json(o));
    global_lines += 1;
);

// ───────────── API (MCP / console) ─────────────
status() -> (
    h = global_hist; n = length(h);
    last = if (n, slice(h, max(0, n - 60), n), []);
    encode_json({'windows_ms' -> map(last, _r1(_:0)), 'max_ms' -> map(last, round(_:1)),
        'mean_15s' -> if (n >= 15, _r1(_mean(15)), null), 'mean_60s' -> if (n >= 60, _r1(_mean(60)), null),
        'incident' -> global_incident, 'baseline_age_min' -> if (global_baseline, round((unix_time() - global_baseline:'t') / 60000), null),
        'cfg' -> global_cfg, 'last_alert' -> global_last_alert, 'outbox' -> global_outbox, 'log_lines' -> global_lines, 'cost' -> global_cost})
);

census(top) -> encode_json(_census(top));

cost() -> (
    t = time(); loop(200, _window()); per = (time() - t) / 200;
    t = time(); c = _census(8); cm = time() - t;
    global_cost = {'sample_us' -> round(per * 1000), 'census_ms' -> _r1(cm), 'entities' -> c:'entities',
        'per_tick_us' -> round(per * 1000 / 20 + cm * 1000 / (global_cfg:'baseline_minutes' * 1200))};
    encode_json(global_cost)
);

config_set(k, v) -> (
    global_cfg:k = v;
    write_file('config', 'json', global_cfg);
    encode_json(global_cfg)
);

// for tests: the alert text would go to these players (fake players are fine to test the chat line)
say_test(name, msg) -> (_send([player(name)], msg); 'sent');
