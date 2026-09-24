/**
 * sim.js — dry-run a list of build commands into a virtual world (pure, no I/O).
 * Used by minecraft_preview (see a build before it exists) and by tests of analyze.js.
 *
 * Understands: fill (replace | hollow | outline | keep | destroy, "replace <filter>"), setblock (replace | keep),
 * clone (inside the simulation), "execute if|unless block X Y Z <block> run <cmd>" (nested, using the simulated state),
 * "place feature <tree>" (a stylised tree), summon (kept as entity markers for the renderer).
 * Everything else (give, data, kill, effect...) is ignored. Relative (~) coordinates are skipped.
 */

const base = (b) => String(b).replace(/^minecraft:/, "").split(/[[{]/)[0];
const N = "(-?\\d+(?:\\.\\d+)?)";
const reFill = new RegExp(`^fill\\s+${N}\\s+${N}\\s+${N}\\s+${N}\\s+${N}\\s+${N}\\s+(\\S+(?:\\{.*\\})?)(?:\\s+(replace|hollow|outline|keep|destroy)(?:\\s+(\\S+))?)?\\s*$`);
const reSet = new RegExp(`^setblock\\s+${N}\\s+${N}\\s+${N}\\s+(\\S+?(?:\\{.*\\})?)(?:\\s+(replace|keep|destroy))?\\s*$`);
const reClone = new RegExp(`^clone\\s+${N}\\s+${N}\\s+${N}\\s+${N}\\s+${N}\\s+${N}\\s+${N}\\s+${N}\\s+${N}`);
const reExec = new RegExp(`^execute\\s+(if|unless)\\s+block\\s+${N}\\s+${N}\\s+${N}\\s+(\\S+)\\s+(.*)$`);
const reFeature = new RegExp(`^place\\s+feature\\s+(\\S+)\\s+${N}\\s+${N}\\s+${N}`);
const reSummon = new RegExp(`^summon\\s+(\\S+)\\s+${N}\\s+${N}\\s+${N}(.*)$`);

const TAGS = {
  "#minecraft:logs": /(_log|_wood|_stem|_hyphae)$/,
  "#minecraft:leaves": /leaves$/,
  "#minecraft:stairs": /_stairs$/,
  "#minecraft:slabs": /_slab$/,
  "#minecraft:flowers": /tulip|poppy|dandelion|allium|orchid|daisy|bluet|cornflower|lily_of|peony|lilac|rose_bush|sunflower|petals|torchflower/,
  "#minecraft:doors": /_door$/,
  "#minecraft:air": /^(air|cave_air|void_air)$/,
};
function matches(name, filter) {
  const f = String(filter);
  if (f.startsWith("#")) { const re = TAGS[f.replace(/\[.*$/, "")]; return re ? re.test(name) : false; }
  return name === base(f);
}

/**
 * simulate(list, { ground: fn(x,y,z)->name|null }) → { at, set, get, lo, hi, entities, stats }
 * ground() gives the world below the build (default: superflat — bedrock -64, dirt -63/-62, grass -61, air above).
 */
export function simulate(list, opts = {}) {
  const flat = (x, y, z) => (y < -64 ? null : y === -64 ? "bedrock" : y <= -62 ? "dirt" : y === -61 ? "grass_block" : "air");
  const ground = opts.ground || flat;
  const V = new Map();
  const key = (x, y, z) => `${x},${y},${z}`;
  const get = (x, y, z) => { const k = key(x, y, z); return V.has(k) ? V.get(k) : ground(x, y, z); };
  const lo = [Infinity, Infinity, Infinity], hi = [-Infinity, -Infinity, -Infinity];
  const touch = (x, y, z) => { if (x < lo[0]) lo[0] = x; if (y < lo[1]) lo[1] = y; if (z < lo[2]) lo[2] = z; if (x > hi[0]) hi[0] = x; if (y > hi[1]) hi[1] = y; if (z > hi[2]) hi[2] = z; };
  const set = (x, y, z, b) => { V.set(key(x, y, z), b); touch(x, y, z); };
  const entities = [];
  const stats = { commands: 0, simulated: 0, skipped: 0, trees: 0, entities: 0, conditional_skipped: 0 };
  const skippedKinds = {};

  const tree = (feature, x, y, z) => {
    const f = base(feature);
    const wood = /birch/.test(f) ? "birch" : /dark_oak/.test(f) ? "dark_oak" : /cherry/.test(f) ? "cherry" : /spruce|pine/.test(f) ? "spruce" : /jungle/.test(f) ? "jungle" : /acacia/.test(f) ? "acacia" : /azalea/.test(f) ? "oak" : "oak";
    const leaves = /azalea/.test(f) ? "azalea_leaves" : `${wood}_leaves`;
    const h = /super_birch|fancy|dark_oak|spruce/.test(f) ? 7 : /azalea/.test(f) ? 4 : 5;
    const r = /fancy|cherry|dark_oak/.test(f) ? 3 : 2;
    if (!/^(grass_block|dirt|podzol|moss_block|coarse_dirt|rooted_dirt|mud)$/.test(get(x, y - 1, z))) return false;
    for (let i = 0; i < h; i++) if (get(x, y + i, z) === "air") set(x, y + i, z, `${wood}_log`);
    if (/dark_oak/.test(f)) for (const [dx, dz] of [[1, 0], [0, 1], [1, 1]]) for (let i = 0; i < h; i++) if (get(x + dx, y + i, z + dz) === "air") set(x + dx, y + i, z + dz, "dark_oak_log");
    const cy = y + h - 1;
    for (let dx = -r; dx <= r; dx++) for (let dz = -r; dz <= r; dz++) for (let dy = -1; dy <= 2; dy++) {
      const rr = r - (dy > 0 ? dy - 0 : 0) * 0.7;
      if (dx * dx + dz * dz <= rr * rr + 0.5 && get(x + dx, cy + dy, z + dz) === "air") set(x + dx, cy + dy, z + dz, /spruce/.test(f) && dy > 0 && Math.abs(dx) + Math.abs(dz) > 1 ? "air" : leaves);
    }
    return true;
  };

  const one = (c0, depth = 0) => {
    const c = String(c0).trim().replace(/^\//, "");
    let m;
    if ((m = reExec.exec(c)) && depth < 4) {
      const cond = matches(get(+m[2] | 0, +m[3] | 0, +m[4] | 0), m[5]);
      const rest = m[6].replace(/^run\s+/, "");
      if ((m[1] === "if") === cond) return one(rest, depth + 1);
      stats.conditional_skipped++; return true;
    }
    if (/^execute\s/.test(c)) {   // other execute forms: run the inner command if it has absolute coordinates
      const i = c.indexOf(" run ");
      if (i > 0 && !/\b(at|positioned|as)\b[^]*~/.test(c.slice(0, i))) return one(c.slice(i + 5), depth + 1);
      return false;
    }
    if (/~|\^/.test(c) && /^(fill|setblock|clone|place|summon)\b/.test(c)) return false;
    if ((m = reFill.exec(c))) {
      const a = [+m[1], +m[2], +m[3]].map(Math.floor), b = [+m[4], +m[5], +m[6]].map(Math.floor);
      const l = a.map((v, i) => Math.min(v, b[i])), h = a.map((v, i) => Math.max(v, b[i]));
      if ((h[0] - l[0] + 1) * (h[1] - l[1] + 1) * (h[2] - l[2] + 1) > 2_000_000) return false;
      const blk = base(m[7]), mode = m[8] || "replace", filt = m[9];
      for (let x = l[0]; x <= h[0]; x++) for (let y = l[1]; y <= h[1]; y++) for (let z = l[2]; z <= h[2]; z++) {
        const edge = x === l[0] || x === h[0] || y === l[1] || y === h[1] || z === l[2] || z === h[2];
        const cur = get(x, y, z);
        if (mode === "keep" && cur !== "air") continue;
        if (mode === "outline" && !edge) continue;
        if (mode === "replace" && filt && !matches(cur, filt)) continue;
        set(x, y, z, mode === "hollow" && !edge ? "air" : blk);
      }
      return true;
    }
    if ((m = reSet.exec(c))) {
      const [x, y, z] = [+m[1], +m[2], +m[3]].map(Math.floor);
      if (m[5] === "keep" && get(x, y, z) !== "air") return true;
      set(x, y, z, base(m[4]));
      return true;
    }
    if ((m = reClone.exec(c))) {
      const f = [+m[1], +m[2], +m[3]], t = [+m[4], +m[5], +m[6]], d = [+m[7], +m[8], +m[9]];
      const l = f.map((v, i) => Math.min(v, t[i])), h = f.map((v, i) => Math.max(v, t[i]));
      const buf = [];
      for (let x = l[0]; x <= h[0]; x++) for (let y = l[1]; y <= h[1]; y++) for (let z = l[2]; z <= h[2]; z++) buf.push([x - l[0], y - l[1], z - l[2], get(x, y, z)]);
      for (const [dx, dy, dz, b] of buf) set(d[0] + dx, d[1] + dy, d[2] + dz, b);
      return true;
    }
    if ((m = reFeature.exec(c))) { if (tree(m[1], ...[+m[2], +m[3], +m[4]].map(Math.floor))) stats.trees++; return true; }
    if ((m = reSummon.exec(c))) {
      const type = base(m[1]);
      const pose = /pose:"(\w+)"/.exec(m[5] || "")?.[1] || "";
      const name = /CustomName:"([^"]*)"/.exec(m[5] || "")?.[1];
      entities.push({ type, pos: [+m[2], +m[3], +m[4]], pose, name });
      touch(Math.floor(+m[2]), Math.floor(+m[3]), Math.floor(+m[4]));
      stats.entities++;
      return true;
    }
    return false;
  };

  for (const c of list) {
    stats.commands++;
    let ok = false;
    try { ok = one(c); } catch { ok = false; }
    if (ok) stats.simulated++;
    else { stats.skipped++; const k = String(c).trim().split(/\s+/)[0]; skippedKinds[k] = (skippedKinds[k] || 0) + 1; }
  }
  stats.skipped_kinds = skippedKinds;
  stats.changed_blocks = V.size;
  const at = (x, y, z) => get(x, y, z);
  return { at, get, set, lo, hi, entities, stats, changed: V };
}

/** A region view for the renderer / pathfinder: a box around the simulated build (plus a margin of ground). */
export function regionOf(sim, { margin = 2, groundDepth = 1, cutY = null } = {}) {
  if (!isFinite(sim.lo[0])) return null;
  const lo = [sim.lo[0] - margin, Math.max(-64, Math.min(sim.lo[1], -61) - (groundDepth - 1)), sim.lo[2] - margin];
  const hi = [sim.hi[0] + margin, sim.hi[1], sim.hi[2] + margin];
  if (cutY != null) hi[1] = Math.min(hi[1], Math.floor(cutY));
  return { lo, hi, at: (x, y, z) => (x < lo[0] || x > hi[0] || y < lo[1] || y > hi[1] || z < lo[2] || z > hi[2] ? null : sim.at(x, y, z)) };
}
