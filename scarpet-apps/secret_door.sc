// secret_door.sc — a button (or lever, or pressure plate) that opens a hidden passage by swapping blocks: no redstone
// wiring to hide, works through any thickness of wall, can't get out of sync.
// Doors are read from secret_door.data/doors.json, a list of:
//   {"name": "library", "trigger": [x,y,z], "cells": [[x,y,z], ...], "closed": "bookshelf", "auto_close": 100}
// Each rising edge of the trigger's `powered` state toggles the cells between `closed` and air (with a sound and
// dust). auto_close = ticks until it closes again by itself (0 = stays open until triggered again).
// Reload:  script in secret_door run reload()      Force: script in secret_door run set_door('library', true|false)

__config() -> {'stay_loaded' -> true, 'scope' -> 'global'};

global_doors = [];
global_prev = {};
global_open = {};

reload() -> (
    d = read_file('doors', 'json');
    global_doors = if (d, d, []);
    str('%d door(s)', length(global_doors))
);
__on_start() -> reload();

set_door(name, open) -> (
    d = first(global_doors, _:'name' == name);
    if (!d, return('no door ' + name));
    for (d:'cells', set(_:0, _:1, _:2, if (open, 'air', d:'closed'));
        run(str('particle minecraft:dust{color:[0.5,0.4,0.3],scale:1.5} %.1f %.1f %.1f 0.3 0.3 0.3 0 6', _:0 + 0.5, _:1 + 0.5, _:2 + 0.5)));
    c = d:'cells':0;
    run(str('playsound minecraft:block.piston.%s block @a %d %d %d 1 0.7', if (open, 'extend', 'contract'), c:0, c:1, c:2));
    global_open:name = if (open, tick_time(), null);
    if (open, 'opened', 'closed')
);

__on_tick() -> (
    if (tick_time() % 2 != 0 || !global_doors, return());
    for (global_doors,
        d = _; t = d:'trigger'; k = d:'name';
        on = str(block_state(block(t:0, t:1, t:2), 'powered')) == 'true';
        if (on && !global_prev:k, set_door(k, !global_open:k));
        global_prev:k = on;
        if (global_open:k && d:'auto_close' && tick_time() - global_open:k > d:'auto_close', set_door(k, false))
    )
);
