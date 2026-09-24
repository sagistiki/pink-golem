// race.sc — timed courses with checkpoints and a record board: foot races, parkour, boat or horse tracks.
// Courses are read from race.data/courses.json, a list of:
//   {"name": "sky parkour", "start": [x1,y1,z1,x2,y2,z2], "checkpoints": [[x1,y1,z1,x2,y2,z2], ...],
//    "finish": [x1,y1,z1,x2,y2,z2], "board": [x,y,z], "fall_y": -58}
// Walk through the start box → the timer runs on your action bar → pass every checkpoint in order → reach the finish
// box: your time, a sound, and (if it's a top-5 time) the board updates. Falling below fall_y sends you back to your
// last checkpoint. Records survive restarts (race.data/records.json).
// Reload after editing courses.json:  script in race run reload()

__config() -> {'stay_loaded' -> true, 'scope' -> 'global'};

_or(v, d) -> if (v == null, d, v);

global_allow_fake = false;
global_courses = [];
global_run = {};        // player -> [course index, start tick, next checkpoint, last safe pos]
global_rec = {};        // course name -> [[player, ticks], ...] best first

reload() -> (
    d = read_file('courses', 'json');
    global_courses = if (d, d, []);
    r = read_file('records', 'json');
    global_rec = if (r, r, {});
    for (range(length(global_courses)), _board(_));
    str('%d course(s)', length(global_courses))
);
__on_start() -> reload();

_in(b, p) -> p:0 >= b:0 && p:0 < b:3 + 1 && p:1 >= b:1 && p:1 < b:4 + 1 && p:2 >= b:2 && p:2 < b:5 + 1;
_fmt(t) -> (s = t / 20; if (s >= 60, str('%d:%05.2f', floor(s / 60), s - 60 * floor(s / 60)), str('%.2f s', s)));
_bar(n, text, color) -> run(str('title %s actionbar {"text":"%s","color":"%s"}', n, text, color));
_snd(n, s, pitch) -> run(str('execute as %s at @s run playsound %s master @s ~ ~ ~ 1 %s', n, s, pitch));

_board(ci) -> (
    c = global_courses:ci;
    if (!c:'board', return());
    b = c:'board';
    lines = [str('{"text":"%s\\n","color":"gold","bold":true}', upper(c:'name'))];
    l = _or(global_rec:(c:'name'), []);
    if (!l, lines += '{"text":"no times yet — be the first!","color":"gray"}');
    for (l, lines += str('{"text":"%d. %s  %s\\n","color":"%s"}', _i + 1, _:0, _fmt(_:1), if (_i == 0, 'yellow', 'white')));
    txt = '[' + join(',', lines) + ']';
    tag = 'race_board_' + ci;
    if (entity_selector(str('@e[type=text_display,tag=%s]', tag)),
        run(str('execute as @e[type=text_display,tag=%s] run data merge entity @s {text:%s}', tag, txt)),
        run(str('summon text_display %.1f %.1f %.1f {billboard:"center",Tags:["%s"],background:1073741824,text:%s}', b:0 + 0.5, b:1, b:2 + 0.5, tag, txt))
    )
);

_finish(p, n, st) -> (
    c = global_courses:(st:0);
    t = tick_time() - st:1;
    delete(global_run, n);
    _snd(n, 'minecraft:ui.toast.challenge_complete', 1);
    run(str('title %s title {"text":"%s","color":"gold","bold":true}', n, _fmt(t)));
    l = _or(global_rec:(c:'name'), []);
    l = filter(l, _:0 != n || _:1 < t);
    if (!first(l, _:0 == n), l += [n, t]);
    l = slice(sort_key(l, _:1), 0, min(5, length(l)));
    global_rec:(c:'name') = l;
    write_file('records', 'json', global_rec);
    _board(st:0)
);

__on_tick() -> (
    if (!global_courses, return());
    for (player('all'),
        p = _; n = p~'name';
        if (global_allow_fake || p~'player_type' != 'fake',
            q = pos(p); st = global_run:n;
            if (st,
                c = global_courses:(st:0); cps = _or(c:'checkpoints', []);
                el = tick_time() - st:1;
                if (el % 4 == 0, _bar(n, str('⏱ %s   checkpoint %d/%d', _fmt(el), st:2, length(cps)), 'yellow'));
                if (st:2 < length(cps) && _in(cps:(st:2), q),
                    st:2 = st:2 + 1; st:3 = q; _snd(n, 'minecraft:block.note_block.bell', 1.5),
                st:2 >= length(cps) && _in(c:'finish', q),
                    _finish(p, n, st)
                );
                if (c:'fall_y' && q:1 < c:'fall_y' && global_run:n,
                    run(str('tp %s %.2f %.2f %.2f', n, st:3:0, st:3:1, st:3:2)); _snd(n, 'minecraft:entity.enderman.teleport', 1)),
                // not racing: a start box starts the timer
                for (range(length(global_courses)),
                    ci = _;
                    if (_in(global_courses:ci:'start', q),
                        global_run:n = [ci, tick_time(), 0, q];
                        _snd(n, 'minecraft:block.note_block.pling', 2);
                        run(str('title %s title {"text":"GO!","color":"green","bold":true}', n)))
                )
            )
        )
    )
);

__on_player_disconnects(p, reason) -> delete(global_run, p~'name');
