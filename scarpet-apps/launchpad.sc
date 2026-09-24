// launchpad.sc — launch pads that fly players up a tower, and a free-fall drop back down into a pool.
// Pads are read from launchpad.data/pads.json (blueprints/drop_tower.py writes it), a list of:
//   {"name": "drop1", "pad": [x,y,z], "top": [x,y,z,yaw,pitch], "top_y": 70, "hole": [cx,cz,r], "pool": [cx,cz,r,y]}
// Step on the pad → levitation up the shaft (particles, sound) → teleported onto the roof facing the hole →
// jump in → free-fall height on the action bar → splash + "landed in 3.2 s" when you hit the pool.
// Reload after editing pads.json:  script in launchpad run reload()      Disable:  script unload launchpad

__config() -> {'stay_loaded' -> true, 'scope' -> 'global'};

global_pads = [];
global_up = {};     // player -> [pad, launch tick]
global_fall = {};   // player -> [pad, fall start tick, start y]
global_rbc = ['#FF5555', '#FFAA00', '#FFFF55', '#55FF55', '#5599FF', '#AA55FF'];

reload() -> (
    d = read_file('pads', 'json');
    global_pads = if (d, d, []);
    str('%d pad(s)', length(global_pads))
);
__on_start() -> reload();

_rb(s) -> (
    out = [];
    loop(length(s), out += str('{"text":"%s","color":"%s","bold":true}', slice(s, _, _ + 1), global_rbc:(_ % 6)));
    '[' + join(',', out) + ']'
);
_title(n, big, small, stay) -> (
    run(str('title %s times 5 %d 10', n, stay));
    run(str('title %s subtitle {"text":"%s","color":"white"}', n, small));
    run(str('title %s title %s', n, _rb(big)))
);

_launch(n, pad, x, y, z) -> (
    global_up:n = [pad, tick_time()];
    run(str('effect give %s minecraft:levitation 20 29 true', n));
    run(str('playsound minecraft:entity.firework_rocket.launch master @a %.1f %.1f %.1f 2 0.7', x, y, z));
    run(str('particle minecraft:firework %.1f %.1f %.1f 0.4 0.2 0.4 0.15 60 force', x, y + 0.3, z));
    _title(n, 'LIFT OFF!', 'up to the roof', 30)
);

_rise(n, x, y, z) -> (
    [pad, t0] = global_up:n;
    el = tick_time() - t0;
    if (el % 2 == 0, run(str('particle minecraft:end_rod %.1f %.1f %.1f 0.3 0.4 0.3 0.02 3 force', x, y, z)));
    // arrive: near the top, or the client ignores levitation (flying players), or it takes too long
    if (y > pad:'top_y' - 10 || el > 400 || (el > 40 && y < pad:'pad':1 + 4),
        delete(global_up, n);
        t = pad:'top';
        run(str('effect clear %s minecraft:levitation', n));
        run(str('tp %s %.1f %.1f %.1f %.0f %.0f', n, t:0, t:1, t:2, t:3, t:4));
        run(str('playsound minecraft:entity.player.levelup master @a %.1f %.1f %.1f 1.5 1.4', t:0, t:1, t:2));
        run(str('particle minecraft:firework %.1f %.1f %.1f 0.6 0.4 0.6 0.1 50 force', t:0, t:1 + 1, t:2));
        _title(n, str('%d m', pad:'top_y' - pad:'pool':3), 'jump into the hole!', 50)
    )
);

_falling(p, n, x, y, z) -> (
    [pad, t0, y0] = global_fall:n;
    el = tick_time() - t0;
    q = pad:'pool';
    if (el % 8 == 0 && y > q:3 + 4, run(str('title %s actionbar %s', n, _rb(str('free fall  %d m', floor(y - q:3))))));
    if (y < q:3 + 1.2 && (x - q:0 - 0.5) ^ 2 + (z - q:1 - 0.5) ^ 2 < (q:2 + 0.5) ^ 2,
        delete(global_fall, n);
        run(str('playsound minecraft:entity.generic.splash master @a %.1f %.1f %.1f 2 0.8', x, q:3 + 1, z));
        run(str('particle minecraft:splash %.1f %.1f %.1f 1 0.3 1 0.5 120 force', x, q:3 + 1.5, z));
        run(str('particle minecraft:firework %.1f %.1f %.1f 1 0.5 1 0.1 40 force', x, q:3 + 2, z));
        _title(n, 'SPLASH!', str('%d m in %.1f s', floor(y0 - y), el / 20), 50),
    el > 600 || y > y0 + 3,
        delete(global_fall, n)
    )
);

__on_tick() -> (
    if (!global_pads, return());
    for (player('all'),
        p = _; n = p~'name'; [x, y, z] = pos(p);
        if (p~'dimension' == 'overworld',
            if (has(global_up, n), _rise(n, x, y, z),
                has(global_fall, n), _falling(p, n, x, y, z),
                for (global_pads,
                    pad = _; c = pad:'pad'; h = pad:'hole';
                    if (floor(x) == c:0 && floor(z) == c:2 && abs(y - c:1) < 0.6,
                        _launch(n, pad, x, y, z),
                    y < pad:'top_y' && y > pad:'top_y' - 12 && (x - h:0 - 0.5) ^ 2 + (z - h:1 - 0.5) ^ 2 < (h:2 + 0.5) ^ 2 && p~'motion':1 < 0,
                        global_fall:n = [pad, tick_time(), y];
                        run(str('execute as %s at @s run playsound minecraft:entity.breeze.wind_burst master @s ~ ~ ~ 1 0.8', n))
                    )
                )
            )
        )
    )
);
