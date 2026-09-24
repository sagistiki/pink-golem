// welcome.sc — a calm welcome when a real player joins: a title with their name, a colour shimmer on the action bar,
// a ring of particles. The AI's bot and the helper builders (fake players) get no show.
// Edit the texts below. Disable:  script unload welcome

__config() -> {'stay_loaded' -> true, 'scope' -> 'global'};

global_title = 'Welcome back';
global_colors = ['#FFAACF', '#DDBBFF', '#99D5FF', '#A0FFA0', '#FFE082'];

_rainbow(text, offset) -> (
    parts = []; i = 0;
    for (split('', text), parts += str('{"text":"%s","color":"%s"}', _, global_colors:((i + offset) % length(global_colors))); i += 1);
    '[' + join(',', parts) + ']'
);

__on_player_connects(p) -> (
    if (query(p, 'player_type') == 'fake', return());
    schedule(40, '_hello', p~'name');                  // let the client finish loading first
);

_hello(n) -> (
    p = player(n);
    if (!p, return());
    run(str('title %s times 10 60 20', n));
    run(str('title %s subtitle {"text":"%s","color":"white"}', n, n));
    run(str('title %s title %s', n, _rainbow(global_title, 0)));
    for (range(12), schedule(_ * 3, '_shimmer', n, _));
    [x, y, z] = pos(p);
    for (range(24), a = _ * 15; run(str('particle minecraft:end_rod %.2f %.2f %.2f 0 0.05 0 0.01 1', x + 1.5 * cos(a), y + 0.2, z + 1.5 * sin(a))));
    run(str('execute as %s at @s run playsound minecraft:block.amethyst_block.chime master @s ~ ~ ~ 1 1.2', n))
);

_shimmer(n, i) -> if (player(n), run(str('title %s actionbar %s', n, _rainbow('★ ' + global_title + ', ' + n + ' ★', i))));
