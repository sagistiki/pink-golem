/**
 * pathfind.js — A* walking paths over a scanned block region (pure, no I/O).
 * R = { lo, hi, at(x,y,z) -> block name }. Cells are feet positions [x,y,z] (integers).
 */
export const PASS = /^(air|cave_air|void_air|light|structure_void|short_grass|tall_grass|fern|large_fern|dead_bush|snow|water|bubble_column|redstone_wire|tripwire|string|cobweb|vine|glow_lichen|seagrass|tall_seagrass|kelp|kelp_plant|sugar_cane|sweet_berry_bush|nether_sprouts|lever|ladder|pink_petals|leaf_litter|lily_pad|cave_vines|cave_vines_plant|weeping_vines|weeping_vines_plant|twisting_vines|twisting_vines_plant|hanging_roots|spore_blossom|pale_hanging_moss|firefly_bush|bush|short_dry_grass|tall_dry_grass|wildflowers|nether_portal|end_rod|scaffolding)$|_carpet$|torch|_button$|rail$|_pressure_plate$|_sign$|_banner$|sapling|_tulip$|^(dandelion|poppy|blue_orchid|allium|azure_bluet|oxeye_daisy|cornflower|lily_of_the_valley|wither_rose|sunflower|lilac|rose_bush|peony|torchflower)$|mushroom$|_roots$|_door$|_fence_gate$/;
export const BLOCKS_ALL = /fence|_wall$|^iron_bars$|glass_pane$|^chain$|iron_chain|cactus|magma_block|campfire|lava/;  // can't walk through or stand on
export const HALF = /slab|stairs|bed$|^snow$|chest$|campfire|enchanting_table|lectern|stonecutter|daylight_detector|_carpet$|composter|cake|farmland|dirt_path|soul_sand|mud$/;
export const isDoor = (n) => /_door$|_fence_gate$/.test(n || "");

export function findPath(R, start, goal, { maxNodes = 80000, maxDrop = 3 } = {}) {
  const [x1, y1, z1] = R.lo, [x2, y2, z2] = R.hi;
  const name = (x, y, z) => (x < x1 || x > x2 || y < y1 || y > y2 || z < z1 || z > z2 ? null : R.at(x, y, z));
  const pass = (x, y, z) => { const n = name(x, y, z); return n != null && PASS.test(n) && !BLOCKS_ALL.test(n); };
  const standOn = (x, y, z) => { const n = name(x, y, z); return n != null && !PASS.test(n) && !BLOCKS_ALL.test(n); };
  const wet = (x, y, z) => name(x, y, z) === "water";
  const ok = (x, y, z) => pass(x, y, z) && pass(x, y + 1, z) && (standOn(x, y - 1, z) || wet(x, y, z));
  const snap = (p) => {
    const [x, y, z] = p.map(Math.floor);
    for (const dy of [0, 1, -1, 2, -2, 3]) if (ok(x, y + dy, z)) return [x, y + dy, z];
    for (let r = 1; r <= 3; r++) for (let dx = -r; dx <= r; dx++) for (let dz = -r; dz <= r; dz++) for (const dy of [0, 1, -1])
      if (ok(x + dx, y + dy, z + dz)) return [x + dx, y + dy, z + dz];
    return null;
  };
  const s = snap(start), g = snap(goal);
  if (!s) return { error: "start position is not walkable" };
  if (!g) return { error: "no walkable spot near the destination" };
  const key = (x, y, z) => `${x},${y},${z}`;
  const h = (x, y, z) => Math.hypot(x - g[0], z - g[2]) + Math.abs(y - g[1]) * 0.5;
  const open = [[h(...s), 0, s]];  // binary heap of [f, g, cell]
  const push = (it) => { open.push(it); let i = open.length - 1; while (i) { const p = (i - 1) >> 1; if (open[p][0] <= open[i][0]) break; [open[p], open[i]] = [open[i], open[p]]; i = p; } };
  const pop = () => { const top = open[0], last = open.pop(); if (open.length) { open[0] = last; let i = 0; for (;;) { const l = 2 * i + 1, r = l + 1; let m = i; if (l < open.length && open[l][0] < open[m][0]) m = l; if (r < open.length && open[r][0] < open[m][0]) m = r; if (m === i) break; [open[m], open[i]] = [open[i], open[m]]; i = m; } } return top; };
  const gBest = new Map([[key(...s), 0]]), came = new Map();
  let nodes = 0, best = s, bestH = h(...s);
  const DIRS = [[1, 0], [-1, 0], [0, 1], [0, -1], [1, 1], [1, -1], [-1, 1], [-1, -1]];
  while (open.length && nodes++ < maxNodes) {
    const [, gc, c] = pop();
    const [x, y, z] = c;
    if (x === g[0] && y === g[1] && z === g[2]) { best = c; break; }
    if (gc > (gBest.get(key(x, y, z)) ?? Infinity)) continue;
    const hc = h(x, y, z); if (hc < bestH) { bestH = hc; best = c; }
    for (const [dx, dz] of DIRS) {
      const nx = x + dx, nz = z + dz;
      if (dx && dz && !(ok(x + dx, y, z) && ok(x, y, z + dz))) continue;    // no corner cutting
      const cands = [];
      if (ok(nx, y, nz)) cands.push([y, 0]);
      else if (ok(nx, y + 1, nz) && pass(x, y + 2, z)) cands.push([y + 1, HALF.test(name(nx, y, nz) || "") ? 0.2 : 0.8]); // step / jump up
      else for (let d = 1; d <= maxDrop; d++) { if (!pass(nx, y - d + 1, nz)) break; if (ok(nx, y - d, nz)) { cands.push([y - d, 0.3 * d]); break; } }
      for (const [ny, extra] of cands) {
        const cost = gc + (dx && dz ? 1.414 : 1) + extra + (wet(nx, ny, nz) ? 3 : 0) + (isDoor(name(nx, ny, nz)) ? 0.5 : 0);
        const k = key(nx, ny, nz);
        if (cost < (gBest.get(k) ?? Infinity)) { gBest.set(k, cost); came.set(k, c); push([cost + h(nx, ny, nz), cost, [nx, ny, nz]]); }
      }
    }
  }
  const reached = best[0] === g[0] && best[1] === g[1] && best[2] === g[2];
  const cells = [];
  for (let c = best; c; c = came.get(key(...c))) cells.push(c);
  cells.reverse();
  // simplify: keep turning points / height changes / doors, then straight-line shortcuts on flat ground
  const los = (a, b) => {
    if (a[1] !== b[1]) return false;
    const n = Math.ceil(Math.hypot(b[0] - a[0], b[2] - a[2]) * 3);
    for (let i = 1; i < n; i++) {
      const t = i / n, fx = a[0] + 0.5 + (b[0] - a[0]) * t, fz = a[2] + 0.5 + (b[2] - a[2]) * t;
      for (const [ox, oz] of [[0.3, 0.3], [-0.3, 0.3], [0.3, -0.3], [-0.3, -0.3]]) {
        const cx = Math.floor(fx + ox), cz = Math.floor(fz + oz);
        if (!ok(cx, a[1], cz) || isDoor(name(cx, a[1], cz))) return false;
      }
    }
    return true;
  };
  const way = [cells[0]];
  let i = 0;
  while (i < cells.length - 1) {
    let j = cells.length - 1;
    while (j > i + 1 && !los(cells[i], cells[j])) j--;
    way.push(cells[j]);
    i = j;
  }
  const doors = cells.filter((c) => isDoor(name(...c)));
  return { reached, cells: cells.length, nodes, waypoints: way.slice(1), doors, start: s, goal: g, climbs: way.slice(1).map((w, k) => w[1] > way[k][1]) };
}

/** Walk rules shared with analyze.js (same as findPath): ok(x,y,z) = a player can stand with feet at y. */
export function makeWalker(R, { maxDrop = 3 } = {}) {
  const [x1, y1, z1] = R.lo, [x2, y2, z2] = R.hi;
  const name = (x, y, z) => (x < x1 || x > x2 || y < y1 || y > y2 || z < z1 || z > z2 ? null : R.at(x, y, z));
  const pass = (x, y, z) => { const n = name(x, y, z); return n != null && PASS.test(n) && !BLOCKS_ALL.test(n); };
  const standOn = (x, y, z) => { const n = name(x, y, z); return n != null && !PASS.test(n) && !BLOCKS_ALL.test(n); };
  const wet = (x, y, z) => name(x, y, z) === "water";
  const ok = (x, y, z) => pass(x, y, z) && pass(x, y + 1, z) && (standOn(x, y - 1, z) || wet(x, y, z));
  const DIRS = [[1, 0], [-1, 0], [0, 1], [0, -1], [1, 1], [1, -1], [-1, 1], [-1, -1]];
  /** neighbours of a feet cell: [[x,y,z, kind]] kind = flat | step (half block up) | jump (full block up) | drop */
  const neighbors = (x, y, z) => {
    const out = [];
    for (const [dx, dz] of DIRS) {
      const nx = x + dx, nz = z + dz;
      if (dx && dz && !(ok(x + dx, y, z) && ok(x, y, z + dz))) continue;
      if (ok(nx, y, nz)) out.push([nx, y, nz, "flat"]);
      else if (ok(nx, y + 1, nz) && pass(x, y + 2, z)) out.push([nx, y + 1, nz, HALF.test(name(nx, y, nz) || "") ? "step" : "jump"]);
      else for (let d = 1; d <= maxDrop; d++) { if (!pass(nx, y - d + 1, nz)) break; if (ok(nx, y - d, nz)) { out.push([nx, y - d, nz, "drop"]); break; } }
    }
    return out;
  };
  const snap = (p) => {
    const [x, y, z] = p.map(Math.floor);
    for (const dy of [0, 1, -1, 2, -2, 3]) if (ok(x, y + dy, z)) return [x, y + dy, z];
    for (let r = 1; r <= 3; r++) for (let dx = -r; dx <= r; dx++) for (let dz = -r; dz <= r; dz++) for (const dy of [0, 1, -1])
      if (ok(x + dx, y + dy, z + dz)) return [x + dx, y + dy, z + dz];
    return null;
  };
  return { name, pass, standOn, wet, ok, neighbors, snap };
}
