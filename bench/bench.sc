// bench.sc — the Pink Golem bench judge. Scans an arena on the flat world and writes every block that differs from
// untouched flat ground (air above, grass_block at y=-61, dirt below) to <world>/scripts/bench.data/<name>.json:
// {n, lo, hi, counts:{block: n}, cells:[[x, y, z, 'block'], …]}. Holes in the ground are counted as 'hole'.
// Cells are listed only up to `max_cells`, so big builds still return counts and the box.

__config() -> {'scope' -> 'global', 'stay_loaded' -> true};

judge(x1, z1, x2, z2, ylo, yhi, name, max_cells) -> (
  counts = {};
  cells = [];
  lo = null;
  hi = null;
  n = 0;
  volume(x1, ylo, z1, x2, yhi, z2,
    b = str(_);
    p = pos(_);
    y = p:1;
    changed = if(y > -61, b != 'air',
                 y == -61, b != 'grass_block' && b != 'dirt',
                 b != 'dirt' && b != 'bedrock');
    if (changed,
      k = if(b == 'air', 'hole', b);
      counts:k = if(has(counts, k), counts:k, 0) + 1;
      n += 1;
      if (n <= max_cells, cells += [p:0, p:1, p:2, k]);
      if (lo == null,
        lo = [p:0, p:1, p:2]; hi = [p:0, p:1, p:2],
        lo = [min(lo:0, p:0), min(lo:1, p:1), min(lo:2, p:2)];
        hi = [max(hi:0, p:0), max(hi:1, p:1), max(hi:2, p:2)]
      )
    )
  );
  write_file(name, 'json', {'n' -> n, 'lo' -> lo, 'hi' -> hi, 'counts' -> counts, 'cells' -> cells});
  n
);
