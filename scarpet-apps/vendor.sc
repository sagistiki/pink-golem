// vendor.sc — button stands that serve things: a drink bar, an ice-cream cart, a gift shop.
// Stands are read from vendor.data/stands.json, a list of:
//   {"name": "beach bar", "button": [x,y,z], "npc_tag": "bartender", "menu": [
//       {"name": "Mojito", "color": "green", "item": "potion", "potion_color": 5635925, "effect": "speed", "seconds": 60},
//       {"name": "Ice cream", "color": "white", "item": "cookie"} ]}
// Pressing the button gives the nearest player (within 4.5 blocks) a random named item from the menu (+ its effect),
// the NPC with npc_tag (a mannequin/villager, optional) turns to them and swings, a sound and a few particles play.
// Why polling: button presses are read from the block's `powered` state every 2 ticks — reliable for every client.
// Reload after editing stands.json:  script in vendor run reload()      Test with the bot: set global_allow_fake = true.

__config() -> {'stay_loaded' -> true, 'scope' -> 'global'};

_or(v, d) -> if (v == null, d, v);

global_allow_fake = false;
global_stands = [];
global_prev = {};
global_cool = {};

reload() -> (
    d = read_file('stands', 'json');
    global_stands = if (d, d, []);
    str('%d stand(s)', length(global_stands))
);
__on_start() -> reload();

_nearest(c, r) -> (
    best = null; bd = r;
    for (player('all'),
        if (global_allow_fake || query(_, 'player_type') != 'fake',
            p = pos(_); d = sqrt((p:0 - c:0 - 0.5) ^ 2 + (p:2 - c:2 - 0.5) ^ 2);
            if (d < bd && abs(p:1 - c:1) < 3, bd = d; best = _)
        )
    );
    best
);

_serve(s) -> (
    c = s:'button';
    p = _nearest(c, 4.5);
    if (!p, return());
    n = p~'name';
    if (tick_time() < (_or(global_cool:n, 0)), return());
    global_cool:n = tick_time() + 30;
    m = s:'menu':(floor(rand(length(s:'menu'))));
    comps = str('custom_name={"text":"%s","color":"%s","italic":false}', m:'name', _or(m:'color', 'white'));
    if (m:'item' == 'potion',
        eff = if (m:'effect', str(',custom_effects:[{id:"minecraft:%s",duration:%d}]', m:'effect', (_or(m:'seconds', 60)) * 20), '');
        comps += str(',potion_contents={custom_color:%d%s}', _or(m:'potion_color', 16777215), eff)
    );
    run(str('give %s %s[%s] 1', n, m:'item', comps));
    run(str('playsound minecraft:block.brewing_stand.brew master @a %d %d %d 1 1.4', c:0, c:1, c:2));
    run(str('particle minecraft:happy_villager %.1f %.1f %.1f 0.3 0.3 0.3 0 8', c:0 + 0.5, c:1 + 1, c:2 + 0.5));
    run(str('title %s actionbar {"text":"%s","color":"%s"}', n, m:'name', _or(m:'color', 'white')));
    if (s:'npc_tag',
        run(str('execute as @e[tag=%s] at @s run tp @s ~ ~ ~ facing entity %s eyes', s:'npc_tag', n));
        for (entity_selector(str('@e[tag=%s]', s:'npc_tag')), modify(_, 'swing'))
    )
);

__on_tick() -> (
    if (tick_time() % 2 != 0 || !global_stands, return());
    for (global_stands,
        s = _; c = s:'button'; k = str(c);
        on = str(block_state(block(c:0, c:1, c:2), 'powered')) == 'true';
        if (on && !global_prev:k, _serve(s));
        global_prev:k = on
    )
);
