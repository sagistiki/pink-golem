/**
 * worldmap.js — the bot's index of what is built where (pure, no I/O).
 * An entry: { id, name, aliases[], kind, owner, builder, lo:[x,y,z], hi:[x,y,z], entrances:[{pos:[x,y,z], note}], warps[], notes, source }
 * The index file (data/world_index.json) is merged with data/zones.json so every protected zone is on the map too.
 */

const norm = (s) => String(s || "").toLowerCase().replace(/[֑-ׇ]/g, "").replace(/[^\p{L}\p{N}]+/gu, " ").trim();

/** Merge the hand-kept index with zones (zones that no index entry covers become "zone" entries). */
export function mergeIndex(index, zones = []) {
  const out = index.map((e) => ({ ...e, source: e.source || "index" }));
  for (const z of zones) {
    const covered = out.some((e) => e.zone === z.name || (e.lo && boxInside(z, e, 3)));
    if (covered) continue;
    out.push({ id: "zone:" + z.name, name: z.name, kind: z.auto ? "build (auto zone)" : "protected zone", owner: z.owner, builder: z.builder, lo: z.lo, hi: z.hi, notes: z.note || "", source: "zones" });
  }
  return out;
}
const boxInside = (a, b, pad = 0) => a.lo.every((v, i) => v >= b.lo[i] - pad) && a.hi.every((v, i) => v <= b.hi[i] + pad);

/** Find entries by name / alias / id (fuzzy, any language). Best first. */
export function lookup(entries, q) {
  const n = norm(q);
  if (!n) return [];
  const words = n.split(" ");
  const scored = entries.map((e) => {
    const names = [e.id, e.name, ...(e.aliases || [])].map(norm);
    let s = 0;
    for (const nm of names) {
      if (nm === n) s = Math.max(s, 100);
      else if (nm.includes(n)) s = Math.max(s, 60 + n.length);
      else { const hit = words.filter((w) => w.length > 1 && nm.includes(w)).length; if (hit) s = Math.max(s, 20 * hit / words.length + hit); }
    }
    return [s, e];
  }).filter(([s]) => s > 0).sort((a, b) => b[0] - a[0]);
  return scored.map(([, e]) => e);
}

export const center = (e) => [0, 1, 2].map((i) => (e.lo[i] + e.hi[i]) / 2);
/** Horizontal gap between two boxes (0 if they touch/overlap). */
export function gapXZ(a, b) {
  const dx = Math.max(0, a.lo[0] - b.hi[0], b.lo[0] - a.hi[0]);
  const dz = Math.max(0, a.lo[2] - b.hi[2], b.lo[2] - a.hi[2]);
  return Math.hypot(dx, dz);
}
/** Compass word for a direction on this map (north = -z, east = +x). */
export function compass(dx, dz) {
  if (Math.hypot(dx, dz) < 1) return "here";
  const a = (Math.atan2(dx, -dz) * 180) / Math.PI;   // 0 = north, 90 = east
  const k = ((Math.round(a / 45) % 8) + 8) % 8;
  return ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"][k];
}

/** What is near a box/point: sorted by gap, with direction from the reference. */
export function near(entries, ref, radius = 80, skipId) {
  const R = Array.isArray(ref) ? { lo: ref, hi: ref } : ref;
  const c0 = center(R);
  return entries.filter((e) => e.lo && e.id !== skipId && e !== ref)
    .map((e) => { const g = gapXZ(R, e), c = center(e); const dir = compass(c[0] - c0[0], c[2] - c0[2]); return { id: e.id, name: e.name, owner: e.owner, gap: +g.toFixed(0), direction: dir, center: c.map(Math.round), lo: e.lo, hi: e.hi }; })
    .filter((r) => r.gap <= radius).sort((a, b) => a.gap - b.gap);
}

/** Entries that contain a point (smallest first). */
export function at(entries, p) {
  return entries.filter((e) => e.lo && [0, 1, 2].every((i) => p[i] >= e.lo[i] - (i === 1 ? 4 : 0) && p[i] <= e.hi[i] + (i === 1 ? 4 : 0)))
    .sort((a, b) => vol(a) - vol(b));
}
const vol = (e) => (e.hi[0] - e.lo[0] + 1) * (e.hi[1] - e.lo[1] + 1) * (e.hi[2] - e.lo[2] + 1);

/**
 * Builds in a player's field of view. yaw/pitch in Minecraft degrees (yaw 0 = south, 90 = west).
 * Returns [{ name, distance, side: 'ahead'|'left'|'right', angle, visible_fraction }] nearest first.
 */
export function inView(entries, eye, yaw, fov = 75, maxDist = 120) {
  const y = (yaw * Math.PI) / 180;
  const f = [-Math.sin(y), Math.cos(y)];          // forward in x/z
  const r = [-Math.cos(y), -Math.sin(y)];         // player's right
  const out = [];
  for (const e of entries) {
    if (!e.lo) continue;
    // sample the box footprint (corners + centre + edge midpoints) and keep samples inside the cone
    const xs = [e.lo[0], (e.lo[0] + e.hi[0]) / 2, e.hi[0] + 1], zs = [e.lo[2], (e.lo[2] + e.hi[2]) / 2, e.hi[2] + 1];
    let best = null, seen = 0, all = 0;
    for (const x of xs) for (const z of zs) {
      all++;
      const dx = x - eye[0], dz = z - eye[2], d = Math.hypot(dx, dz);
      const ang = (Math.atan2(dx * r[0] + dz * r[1], dx * f[0] + dz * f[1]) * 180) / Math.PI;   // + = right
      if (Math.abs(ang) <= fov / 2 && d <= maxDist) { seen++; if (!best || d < best.d) best = { d, ang }; }
    }
    const inside = eye[0] >= e.lo[0] && eye[0] <= e.hi[0] + 1 && eye[2] >= e.lo[2] && eye[2] <= e.hi[2] + 1;
    if (inside) { out.push({ id: e.id, name: e.name, owner: e.owner, distance: 0, side: "you are inside", angle: 0, visible_fraction: 1 }); continue; }
    if (!best) continue;
    out.push({ id: e.id, name: e.name, owner: e.owner, distance: Math.round(best.d), angle: Math.round(best.ang),
      side: Math.abs(best.ang) < 12 ? "ahead" : best.ang > 0 ? "right" : "left", visible_fraction: +(seen / all).toFixed(2) });
  }
  return out.sort((a, b) => a.distance - b.distance);
}

/** A box (lo, hi) that holds the view cone out to `dist`, from ground to above the eye. */
export function coneBox(eye, yaw, fov, dist, { below = 8, above = 30 } = {}) {
  const y = (yaw * Math.PI) / 180, h = ((fov / 2 + 4) * Math.PI) / 180;
  const pts = [[eye[0], eye[2]]];
  for (const a of [-h, -h / 2, 0, h / 2, h]) pts.push([eye[0] - Math.sin(y + a) * dist, eye[2] + Math.cos(y + a) * dist]);
  const lo = [Math.floor(Math.min(...pts.map((p) => p[0]))) - 1, Math.max(-64, Math.floor(eye[1]) - below), Math.floor(Math.min(...pts.map((p) => p[1]))) - 1];
  const hi = [Math.ceil(Math.max(...pts.map((p) => p[0]))) + 1, Math.floor(eye[1]) + above, Math.ceil(Math.max(...pts.map((p) => p[1]))) + 1];
  return [lo, hi];
}

/** Split a box into slabs of at most maxVol blocks along its longest horizontal axis. */
export function splitBox(lo, hi, maxVol = 110000) {
  const V = (hi[0] - lo[0] + 1) * (hi[1] - lo[1] + 1) * (hi[2] - lo[2] + 1);
  if (V <= maxVol) return [[lo, hi]];
  const ax = hi[0] - lo[0] >= hi[2] - lo[2] ? 0 : 2;
  const area = V / (hi[ax] - lo[ax] + 1);
  const step = Math.max(1, Math.floor(maxVol / area));
  const out = [];
  for (let a = lo[ax]; a <= hi[ax]; a += step) { const l = lo.slice(), h = hi.slice(); l[ax] = a; h[ax] = Math.min(hi[ax], a + step - 1); out.push([l, h]); }
  return out;
}
/** Compose several region reads (from splitBox) into one R. */
export function composeRegions(parts, lo, hi) {
  return {
    lo, hi,
    at: (x, y, z) => {
      for (const p of parts) if (x >= p.lo[0] && x <= p.hi[0] && y >= p.lo[1] && y <= p.hi[1] && z >= p.lo[2] && z <= p.hi[2]) return p.at(x, y, z);
      return null;
    },
  };
}
