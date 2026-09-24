// fireworks.sc — a fireworks show around a point, from a command block, a button or the AI:
//   script in fireworks run show(x, y, z, seconds)      e.g. show(0, -60, 0, 20)
// Rockets rise from a ring around the point in waves (colour volleys, star bursts, a finale). Keep the launch
// point clear of roofs and 6+ blocks from people. Only one show runs at a time.

__config() -> {'stay_loaded' -> true, 'scope' -> 'global'};

global_running = false;
global_cols = [16711680, 16744448, 16776960, 8453888, 65535, 3355647, 10040319, 16711935, 16777215];
global_shapes = ['large_ball', 'small_ball', 'star', 'burst'];

_rocket(x, y, z, life, shape, n) -> (
    c1 = global_cols:(floor(rand(length(global_cols)))); c2 = global_cols:(floor(rand(length(global_cols))));
    run(str('summon firework_rocket %.2f %.2f %.2f {LifeTime:%d,FireworksItem:{id:"minecraft:firework_rocket",count:1,components:{"minecraft:fireworks":{flight_duration:1,explosions:[{shape:"%s",colors:[I;%d,%d],fade_colors:[I;16777215],has_trail:true,has_twinkle:%s}]}}}}',
        x, y, z, life, shape, c1, c2, if (n % 2, 'true', 'false')))
);

show(x, y, z, secs) -> (
    if (global_running, return('a show is already running'));
    global_running = true;
    waves = max(3, floor(secs / 2));
    for (range(waves),
        w = _;
        schedule(w * 40, '_wave', x, y, z, w, w == waves - 1)
    );
    schedule(waves * 40 + 60, '_done');
    str('show: %d waves', waves)
);

_wave(x, y, z, w, finale) -> (
    n = if (finale, 16, 5 + w % 4);
    for (range(n),
        a = rand(360); r = 3 + rand(5);
        _rocket(x + r * cos(a), y + 1, z + r * sin(a), 25 + floor(rand(15)), global_shapes:(floor(rand(4))), _)
    )
);

_done() -> global_running = false;
