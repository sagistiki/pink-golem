// helpers.sc — makes the helper builders (Carpet fake players) really swing their arm while they work.
// Anyone (fake player) carrying the tag "building" swings every 7 ticks. Tag: /tag <name> add building
// swings('name') returns how many swings the server has seen for that player (proof the animation runs).

__config() -> {'stay_loaded' -> true, 'scope' -> 'global'};

global_swings = {};

__on_player_swings_hand(p, hand) -> (
    n = p ~ 'name';
    c = global_swings:n;
    if (c == null, c = 0);
    global_swings:n = c + 1;
);

swings(n) -> (c = global_swings:n; if (c == null, 0, c));

swing(n) -> modify(player(n), 'swing');

// A standing spot (feet position) near a work target: free feet + head cells and a solid floor within 8 blocks below.
// Works inside rooms too, so builders stand on the floor next to the work instead of on the roof.
stand(tx, ty, tz) -> (
    best = null;
    for (range(30),
        a = rand(360);
        r = 1.6 + rand(2.4);
        x = floor(tx + cos(a) * r);
        z = floor(tz + sin(a) * r);
        y = floor(ty);
        while (air(x, y - 1, z) && y > floor(ty) - 8, 100, y += -1);
        if (!air(x, y - 1, z) && air(x, y, z) && air(x, y + 1, z),
            if (best == null || y < best:1, best = [x + 0.5, y, z + 0.5]));
    );
    best
);

__on_tick() -> (
    if (tick_time() % 7 == 0,
        for (player('all'),
            if (query(_, 'player_type') == 'fake' && query(_, 'has_tag', 'building'), modify(_, 'swing'))
        )
    );
);
