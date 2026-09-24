/**
 * analyze.js — "is this build usable?" checks over a block region (pure, no I/O).
 * R = { lo, hi, at(x,y,z) -> block name }.
 *
 * accessReport(R, entrance) walks (breadth-first, with the same rules as the pathfinder: 1-block jumps,
 * half steps, drops ≤3, doors pass) from the entrance and reports:
 *   - indoor areas nobody can reach (grouped into rooms)
 *   - doors that are blocked on one side (or not reachable at all)
 *   - stairs that end in a wall / have no headroom
 *   - full-block "jump" steps right next to doors (a path laid one block too high)
 */
import { makeWalker, isDoor } from "./pathfind.js";

const key = (x, y, z) => `${x},${y},${z}`;

export function accessReport(R, entrance, opts = {}) {
  const W = makeWalker(R, { maxDrop: 3 });
  const box = opts.box || [R.lo, R.hi];
  const inBox = (x, y, z) => x >= box[0][0] && x <= box[1][0] && y >= box[0][1] && y <= box[1][1] && z >= box[0][2] && z <= box[1][2];
  const start = W.snap(entrance);
  if (!start) return { error: `the entrance ${entrance.map((v) => Math.floor(v)).join(" ")} is not a spot a player can stand on` };

  // 1. breadth-first walk from the entrance
  const seen = new Set([key(...start)]);
  const q = [start];
  const jumps = [];
  const limit = opts.maxCells || 400000;
  for (let i = 0; i < q.length && q.length < limit; i++) {
    const [x, y, z] = q[i];
    for (const [nx, ny, nz, kind] of W.neighbors(x, y, z)) {
      const k = key(nx, ny, nz);
      if (kind === "jump") jumps.push([x, y, z, nx, ny, nz]);
      if (seen.has(k)) continue;
      seen.add(k); q.push([nx, ny, nz]);
    }
  }
  const reach = (x, y, z) => seen.has(key(x, y, z));

  // 2. every standable indoor cell in the box: a ceiling within 2..8 blocks above the head
  const [x1, y1, z1] = box[0], [x2, y2, z2] = box[1];
  const indoor = (x, y, z) => { for (let d = 2; d <= 8; d++) { const n = W.name(x, y + d, z); if (n && !W.pass(x, y + d, z)) return true; } return false; };
  const standable = [];
  for (let y = y1; y <= y2; y++) for (let z = z1; z <= z2; z++) for (let x = x1; x <= x2; x++)
    if (W.ok(x, y, z) && indoor(x, y, z)) standable.push([x, y, z]);
  const unreached = new Set(standable.filter((c) => !reach(...c)).map((c) => key(...c)));
  // group unreached cells into rooms (connected with the same walk rules)
  const rooms = [];
  const done = new Set();
  for (const k0 of unreached) {
    if (done.has(k0)) continue;
    const c0 = k0.split(",").map(Number);
    const cells = [c0]; done.add(k0);
    for (let i = 0; i < cells.length; i++) {
      const [x, y, z] = cells[i];
      for (const [nx, ny, nz] of W.neighbors(x, y, z)) {
        const k = key(nx, ny, nz);
        if (!unreached.has(k) || done.has(k)) continue;
        done.add(k); cells.push([nx, ny, nz]);
      }
    }
    if (cells.length < (opts.minRoom || 6)) continue;
    const lo = [0, 1, 2].map((i) => Math.min(...cells.map((c) => c[i]))), hi = [0, 1, 2].map((i) => Math.max(...cells.map((c) => c[i])));
    const mid = cells.reduce((a, c) => [a[0] + c[0], a[1] + c[1], a[2] + c[2]], [0, 0, 0]).map((v) => Math.round(v / cells.length));
    // what's in it: furniture / light / plants at feet or head level → a real room; nothing → an attic or a void in the walls
    const stuff = {};
    for (const [x, y, z] of cells) for (const dy of [0, 1]) { const n = W.name(x, y + dy, z); if (n && !/^(air|cave_air|light)$/.test(n)) stuff[n] = (stuff[n] || 0) + 1; }
    const lit = cells.some(([x, y, z]) => [0, 1, 2, 3].some((dy) => /lantern|torch|glowstone|sea_lantern|froglight|end_rod|shroomlight/.test(W.name(x, y + dy, z) || "")));
    const why = whyUnreachable(W, cells, reach);
    const furnished = Object.keys(stuff).length > 0;
    rooms.push({ cells: cells.length, floor_y: lo[1] - 1, from: lo, to: hi, center: mid, why,
      kind: furnished || lit ? "room (has furniture/light — players are meant to get here)" : "empty closed space (attic / void — fine if intended)",
      contents: Object.entries(stuff).sort((a, b) => b[1] - a[1]).slice(0, 6).map(([n, c]) => `${n}×${c}`), _p: (furnished ? 2 : 0) + (lit ? 1 : 0) });
  }
  rooms.sort((a, b) => b._p - a._p || b.cells - a.cells);
  const realRooms = rooms.filter((r) => r._p > 0);
  for (const r of rooms) delete r._p;

  // 3. doors (lower halves)
  const doors = [];
  for (let y = y1; y <= y2; y++) for (let z = z1; z <= z2; z++) for (let x = x1; x <= x2; x++) {
    const n = W.name(x, y, z);
    if (!n || !/_door$/.test(n) || W.name(x, y - 1, z) === n) continue;
    // the two open sides are along the axis where the neighbours are not both wall
    const axes = [[[1, 0], [-1, 0]], [[0, 1], [0, -1]]];
    const side = (dx, dz) => ({ at: [x + dx, y, z + dz], ok: W.ok(x + dx, y, z + dz) || isDoor(W.name(x + dx, y, z + dz)), reached: reach(x + dx, y, z + dz), block: W.name(x + dx, y, z + dz), above: W.name(x + dx, y + 1, z + dz) });
    let best = null;
    for (const ax of axes) {
      const s = ax.map(([dx, dz]) => side(dx, dz));
      const score = s.filter((q) => q.ok).length;
      if (!best || score > best.score) best = { score, s };
    }
    const problems = [];
    for (const s of best.s) {
      if (!s.ok) {
        const up = W.name(s.at[0], y + 1, s.at[2]), below = W.name(s.at[0], y - 1, s.at[2]);
        problems.push(W.pass(...s.at) && W.pass(s.at[0], y + 1, s.at[2]) ? `no floor under ${s.at.join(" ")} (${below})`
          : `${s.at.join(" ")} is ${W.pass(...s.at) ? up : s.block}${!W.pass(...s.at) && W.ok(s.at[0], y + 1, s.at[2]) ? " — a raised step right at the door" : ""}`);
      }
    }
    if (!reach(x, y, z) && best.s.every((q) => !q.reached)) problems.push("not reachable from the entrance");
    if (problems.length) doors.push({ door: [x, y, z], type: n, problems });
  }

  // 4. stairs: the step you stand on needs 2 blocks of air above it; a flight must not end in a wall
  const stairs = [];
  for (let y = y1; y <= y2; y++) for (let z = z1; z <= z2; z++) for (let x = x1; x <= x2; x++) {
    const n = W.name(x, y, z);
    if (!n || !/_stairs$/.test(n)) continue;
    const flight = [[1, 0], [-1, 0], [0, 1], [0, -1]].some(([dx, dz]) => /_stairs$/.test(W.name(x + dx, y + 1, z + dz) || "") || /_stairs$/.test(W.name(x + dx, y - 1, z + dz) || ""));
    if (!flight) continue;   // a lone stair = furniture (chair, sofa, roof)
    const roofish = !W.standOn(x, y - 1, z) && !/_stairs$/.test(W.name(x, y - 1, z) || "") && y > -58 && !reach(x, y + 1, z);
    if (!W.pass(x, y + 1, z) && !/_stairs$/.test(W.name(x, y + 1, z) || "")) {
      if (!roofish) stairs.push({ stair: [x, y, z], problem: `blocked: ${W.name(x, y + 1, z)} sits on the step (${x} ${y + 1} ${z})` });
    } else if (W.pass(x, y + 1, z) && !W.pass(x, y + 2, z) && !/_stairs$/.test(W.name(x, y + 2, z) || "")) {
      if (!roofish) stairs.push({ stair: [x, y, z], problem: `no headroom: ${W.name(x, y + 2, z)} at ${x} ${y + 2} ${z}` });
    }
  }
  // roof stairs are everywhere on gable roofs — keep only stairs that are part of an indoor walking route
  const stairsNear = stairs.filter((s) => {
    const [x, y, z] = s.stair;
    return [[0, 1], [1, 0], [-1, 0], [0, -1]].some(([dx, dz]) => [0, 1, -1].some((dy) => {
      const c = [x + dx, y + dy, z + dz];
      return reach(...c);
    }));
  });

  // 5. full-block jumps within 2 blocks of a door = a path/floor at the wrong height
  const doorCells = [];
  for (let y = y1; y <= y2; y++) for (let z = z1; z <= z2; z++) for (let x = x1; x <= x2; x++) { const n = W.name(x, y, z); if (n && /_door$/.test(n) && W.name(x, y - 1, z) !== n) doorCells.push([x, y, z]); }
  const nearDoor = (x, y, z) => doorCells.some((d) => Math.abs(d[0] - x) <= 2 && Math.abs(d[2] - z) <= 2 && Math.abs(d[1] - y) <= 1);
  const steps = [];
  const sk = new Set();
  // furniture and decoration next to a door is fine to jump on — only floors/paths at the wrong height are bugs
  const DECOR = /^potted_|flower_pot|candle|lantern|campfire|_bed$|chest|barrel|smoker|furnace|cauldron|bookshelf|crafting_table|_fence$|_wall$|_stairs$|_slab$|_trapdoor$|anvil|lectern|composter|beehive|bell|^polydecorations:/;
  for (const [x, y, z, nx, ny, nz] of jumps) {
    if (!inBox(nx, ny, nz) || !(nearDoor(x, y, z) || nearDoor(nx, ny, nz))) continue;
    if (DECOR.test(W.name(nx, ny - 1, nz) || "") || /water/.test(W.name(x, y, z) || "")) continue;   // climbing out of a pool is fine
    const k = key(nx, ny - 1, nz); if (sk.has(k)) continue; sk.add(k);
    steps.push({ from: [x, y, z], onto: [nx, ny - 1, nz], block: W.name(nx, ny - 1, nz) });
  }

  const reachedIndoor = standable.length - unreached.size;
  return {
    entrance: start,
    walkable_indoor_cells: standable.length,
    reached_indoor_cells: reachedIndoor,
    unreachable_rooms: rooms.filter((r) => !/^empty/.test(r.kind)).slice(0, 20),
    closed_empty_spaces: rooms.filter((r) => /^empty/.test(r.kind)).slice(0, 10).map((r) => ({ cells: r.cells, center: r.center, floor_y: r.floor_y })),
    blocked_doors: doors.slice(0, 30),
    bad_stairs: stairsNear.slice(0, 30),
    jump_steps_at_doors: steps.slice(0, 20),
    ok: !realRooms.length && !doors.length && !stairsNear.length && !steps.length,
  };
}

function whyUnreachable(W, cells, reach) {
  // look for the closest reached cell to explain the gap (a wall, a missing stair, a 2-block climb)
  for (const [x, y, z] of cells) {
    for (const [dx, dz] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
      for (const dy of [-2, -1, 0, 1, 2]) {
        if (reach(x + dx, y + dy, z + dz)) {
          if (dy >= 2) return `a ${dy}-block climb from ${x + dx} ${y + dy} ${z + dz} — no stairs/ladder`;
          if (dy <= -2) return `${-dy} blocks higher than ${x + dx} ${y + dy} ${z + dz} — needs stairs up`;
          const between = W.name(x, y + 1, z);
          return `next to reachable ${x + dx} ${y + dy} ${z + dz} but blocked (${between} / headroom)`;
        }
      }
    }
  }
  return "no reachable cell next to it (closed room, or stairs/door missing)";
}

/** Largest-first free rectangles of size w×d (+margin) in an occupancy grid (Uint8Array, 1 = taken), nearest to (cx, cz). */
export function findFreeRects(grid, W, D, x0, z0, w, d, margin, center, { count = 3, avoid = [] } = {}) {
  const S = new Int32Array((W + 1) * (D + 1));
  for (let z = 0; z < D; z++) for (let x = 0; x < W; x++) S[(z + 1) * (W + 1) + x + 1] = grid[z * W + x] + S[z * (W + 1) + x + 1] + S[(z + 1) * (W + 1) + x] - S[z * (W + 1) + x];
  const sum = (ax, az, bx, bz) => S[(bz + 1) * (W + 1) + bx + 1] - S[az * (W + 1) + bx + 1] - S[(bz + 1) * (W + 1) + ax] + S[az * (W + 1) + ax];
  const out = [];
  const cands = [];
  for (const [ww, dd] of w === d ? [[w, d]] : [[w, d], [d, w]]) {
    for (let az = 0; az + dd + 2 * margin <= D; az++) for (let ax = 0; ax + ww + 2 * margin <= W; ax++) {
      if (sum(ax, az, ax + ww + 2 * margin - 1, az + dd + 2 * margin - 1)) continue;
      const lx = x0 + ax + margin, lz = z0 + az + margin;
      const mx = lx + ww / 2, mz = lz + dd / 2;
      cands.push({ dist: Math.hypot(mx - center[0], mz - center[1]), from: [lx, lz], to: [lx + ww - 1, lz + dd - 1], rotated: ww !== w });
    }
  }
  cands.sort((a, b) => a.dist - b.dist);
  for (const c of cands) {
    if (out.some((o) => !(c.to[0] < o.from[0] - margin || c.from[0] > o.to[0] + margin || c.to[1] < o.from[1] - margin || c.from[1] > o.to[1] + margin))) continue;
    if (avoid.some((b) => !(c.to[0] < b.lo[0] || c.from[0] > b.hi[0] || c.to[1] < b.lo[2] || c.from[1] > b.hi[2]))) continue;
    out.push(c);
    if (out.length >= count) break;
  }
  return out;
}
