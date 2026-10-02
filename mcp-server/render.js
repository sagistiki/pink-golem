/**
 * render.js — turn a block region into a PNG picture (isometric, top-down or first person), no dependencies.
 * Pure functions: R = { lo:[x,y,z], hi:[x,y,z], at(x,y,z) -> block name | null }. Blocks are flat colours; display
 * entities (item / block / text displays) are drawn textured by display.js, other entities as bright markers.
 */
import zlib from "node:zlib";

// display entities (item/block/text displays) as textured quads — optional: if display.js fails to load, the old
// bright-cube markers are drawn instead. Same hot-reload query as this module.
const DX = await import("./display.js" + new URL(import.meta.url).search).catch((e) => { console.error("display.js:", e.message); return null; });
/** display entities → { groups (textured quads, world space), rest (entities for the old markers) }.
 *  opts.packs (resource-pack zips, first wins), opts.jar / opts.version (the optional client jar, see display.js) */
function displayGroups(entities, cam, opts) {
  if (!DX || opts.textured === false) return { groups: [], rest: entities || [] };
  try { return DX.buildGroups(entities, { ...cam, packs: opts.packs, jar: opts.jar, version: opts.version, colorOf: blockColor }); }
  catch (e) { console.error("display quads:", e.message); return { groups: [], rest: entities || [] }; }
}

// ───────────── PNG encoder ─────────────
const CRC = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();
function crc32(buf) {
  let c = 0xffffffff;
  for (let i = 0; i < buf.length; i++) c = CRC[(c ^ buf[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}
function chunk(type, data) {
  const len = Buffer.alloc(4); len.writeUInt32BE(data.length);
  const td = Buffer.concat([Buffer.from(type, "ascii"), data]);
  const crc = Buffer.alloc(4); crc.writeUInt32BE(crc32(td));
  return Buffer.concat([len, td, crc]);
}
export function encodePNG(w, h, rgb) {
  const raw = Buffer.alloc((w * 3 + 1) * h);
  for (let y = 0; y < h; y++) {
    raw[y * (w * 3 + 1)] = 0;
    rgb.copy ? rgb.copy(raw, y * (w * 3 + 1) + 1, y * w * 3, (y + 1) * w * 3)
             : raw.set(rgb.subarray(y * w * 3, (y + 1) * w * 3), y * (w * 3 + 1) + 1);
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4);
  ihdr[8] = 8; ihdr[9] = 2; ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0;
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk("IHDR", ihdr),
    chunk("IDAT", zlib.deflateSync(raw, { level: 9 })),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

// ───────────── block colours ─────────────
const hex = (h) => [(h >> 16) & 255, (h >> 8) & 255, h & 255];
const DYE = {
  white: 0xe9ecec, orange: 0xf07613, magenta: 0xbd44b3, light_blue: 0x3aafd9, yellow: 0xf8c627, lime: 0x70b919,
  pink: 0xed8dac, gray: 0x3e4447, light_gray: 0x8e8e86, cyan: 0x158991, purple: 0x792aac, blue: 0x35399d,
  brown: 0x724728, green: 0x546d1b, red: 0xa12722, black: 0x141519,
};
const WOOD = {
  oak: [0xa2834f, 0x6b5130], spruce: [0x735531, 0x3b2912], birch: [0xc8b77a, 0xd8d7d2], jungle: [0xa0734d, 0x554419],
  acacia: [0xa85a32, 0x676157], dark_oak: [0x4a2f17, 0x3c2e1a], mangrove: [0x773636, 0x544a2b], cherry: [0xe3b4ad, 0x3b1f2a],
  bamboo: [0xc9b75a, 0x8f8a2f], crimson: [0x6a344b, 0x5c1c1e], warped: [0x2b6963, 0x3a3a4d], pale_oak: [0xe0d7d2, 0x6f6865],
};
const TABLE = [
  // v5: plants (were grey before) — checked first so vines/lichen/moss read as greenery
  [/^spore_blossom$/, 0xe07ab8], [/^flowering_azalea/, 0x7fa04a], [/^(azalea|potted_azalea_bush)/, 0x5f8a33], [/cave_vines/, 0x5e8a2e], [/glow_lichen/, 0x7fa88a],
  [/weeping_vines/, 0x9a2a1e], [/twisting_vines/, 0x1f9a8a], [/^vine$/, 0x3f7d25], [/hanging_roots/, 0xa88a6a], [/pale_hanging_moss|pale_moss/, 0xb8bdb0],
  [/^(short_grass|tall_grass|fern|large_fern|bush|short_dry_grass|tall_dry_grass)$/, 0x5f9a3a], [/^(moss_block|moss_carpet)$/, 0x5a8f2f], [/big_dripleaf|small_dripleaf/, 0x6f9e33],
  [/kelp|seagrass/, 0x3b8c3a], [/bamboo$|bamboo_sapling/, 0x6aa231], [/sugar_cane/, 0x8fc062], [/sweet_berry/, 0x3f6e2a], [/lily_pad/, 0x2f7d2a], [/sapling|propagule/, 0x4f8a2a],
  [/_door$/, 0x8a6a42], [/flower_pot|^potted_/, 0x8a4b35],
  [/poppy|rose|red_tulip|red_mushroom/, 0xd03030], [/dandelion|sunflower/, 0xf5d020], [/cornflower|blue_orchid/, 0x4060e0], [/allium|lilac|peony|pink_tulip|pink_petals/, 0xd070c0], [/azure|oxeye|white_tulip|lily_of/, 0xf0f0f0], [/orange_tulip|torchflower/, 0xf08020],
  [/^(grass_block|moss_block|moss_carpet)$/, 0x5d9b3a], [/leaves/, 0x3b7a2a], [/^cherry_leaves$/, 0xe7a6c3],
  [/^(water|bubble_column)$/, 0x3f76e4], [/lava/, 0xd4570f], [/^(sand|suspicious_sand)$/, 0xdbcfa3], [/sandstone/, 0xd8cb9b],
  [/red_sand/, 0xbe6621], [/gravel/, 0x847f7d], [/^(dirt|coarse_dirt|rooted_dirt|farmland|dirt_path)$/, 0x866043], [/mud_brick/, 0x89684f], [/^mud$/, 0x3c3a3d],
  [/deepslate/, 0x4a4a4f], [/tuff/, 0x6c6d66], [/polished_blackstone|blackstone/, 0x2e2830], [/basalt/, 0x4b4b50],
  [/^(stone|smooth_stone|stone_bricks|stone_brick_.*|chiseled_stone_bricks|cracked_stone_bricks|stone_slab|stone_stairs)$/, 0x7f7f7f],
  [/cobblestone/, 0x7a7a7a], [/andesite/, 0x888888], [/diorite/, 0xbdbdbd], [/granite/, 0x95675a], [/calcite/, 0xdfe0dc],
  [/^bricks|^brick_/, 0x97503f], [/nether_brick/, 0x2c1519], [/netherrack/, 0x6f3535], [/end_stone/, 0xdbde9e],
  [/quartz/, 0xebe5de], [/purpur/, 0xa97ba9], [/prismarine/, 0x639c97], [/amethyst/, 0x8662bf], [/obsidian/, 0x1b1428],
  [/sea_lantern/, 0xc4dcd3], [/glowstone/, 0xf8d57f], [/shroomlight/, 0xf19a4b], [/froglight/, 0xf3e7b3], [/lantern/, 0xd9a64a],
  [/torch|campfire|fire/, 0xffb33b], [/end_rod/, 0xf0ece0], [/redstone_lamp/, 0xa06b3a], [/redstone/, 0xab1c09],
  [/iron_block|iron_bars|iron_door|iron_trapdoor|iron_chain|chain/, 0xd8d8d8], [/gold/, 0xf5da2a], [/diamond/, 0x62ede4], [/emerald/, 0x42d86b],
  [/lapis/, 0x1f4aa6], [/netherite/, 0x423d3f], [/copper/, 0xc06c50], [/snow/, 0xf9fefe], [/ice/, 0x92b9fe],
  [/bedrock/, 0x555555], [/dripstone/, 0x866b5c], [/note_block|jukebox/, 0x6b4632], [/bookshelf/, 0x8c6c3f],
  [/crafting_table|barrel|chest|composter/, 0x9c7542], [/hay/, 0xc6a51b], [/terracotta/, 0x985f45], [/clay/, 0xa1a6b3],
  [/piston/, 0x8f8a7a], [/observer|dispenser|dropper|furnace/, 0x6e6e6e], [/tnt/, 0xdb4d33], [/sponge/, 0xc3c14a],
  [/cactus/, 0x5b8a2d], [/pumpkin|jack_o/, 0xe38a1d], [/melon/, 0x7c9e2d], [/mushroom/, 0xa8423a], [/sculk/, 0x0d2530],
  [/beacon/, 0x7bddda], [/glass/, 0xc8dce6], [/rail/, 0x8a7a66], [/wool|carpet|concrete|bed|banner|candle|shulker/, 0xdddddd],
];
const cache = new Map();
export function blockColor(name) {
  if (cache.has(name)) return cache.get(name);
  let n = String(name).replace(/^minecraft:/, "").replace(/^polydecorations:/, "");
  let c = null;
  const dk = n.startsWith("light_blue_") ? "light_blue" : n.startsWith("light_gray_") ? "light_gray" : Object.keys(DYE).find((d) => n.startsWith(d + "_"));
  if (dk) c = DYE[dk];
  if (c != null && /terracotta/.test(n)) c = mix(c, 0x985f45, 0.45);
  if (c == null) {
    for (const [w, [plank, log]] of Object.entries(WOOD)) {
      if (n.startsWith(w + "_") || n.startsWith("stripped_" + w + "_")) {
        c = /(_log|_wood|_stem|_hyphae)$/.test(n) && !n.startsWith("stripped") ? log : plank;
        if (/leaves/.test(n)) c = w === "cherry" ? 0xe7a6c3 : 0x3b7a2a;
        break;
      }
    }
  }
  if (c == null) for (const [re, v] of TABLE) if (re.test(n)) { c = v; break; }
  if (c == null) {
    let h = 0;
    for (const ch of n) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
    c = mix(0x8a8378, h & 0xffffff, 0.25);
  }
  const rgb = hex(c);
  cache.set(name, rgb);
  return rgb;
}
function mix(a, b, t) {
  const A = hex(a), B = hex(b);
  return (Math.round(A[0] * (1 - t) + B[0] * t) << 16) | (Math.round(A[1] * (1 - t) + B[1] * t) << 8) | Math.round(A[2] * (1 - t) + B[2] * t);
}

// ───────────── block shapes ─────────────
const AIR = /^(air|cave_air|void_air|light|structure_void|barrier)$/;
const TRANSP = /glass|^water$|ice$|^ice|bubble_column|leaves|iron_bars|chain|scaffolding/;
const FLAT = /carpet|rail|redstone_wire|pressure_plate|lily_pad|snow$|^snow$|pink_petals|leaf_litter|tripwire/;
const SMALL = /torch|flower|sapling|^short_grass$|^tall_grass$|fern|dead_bush|button|lever|sign|banner|^(dandelion|poppy|blue_orchid|allium|azure_bluet|oxeye_daisy|cornflower|lily_of_the_valley|wither_rose|sunflower|lilac|rose_bush|peony)$|_tulip|mushroom$|sweet_berry|sugar_cane|kelp|seagrass|vine|lichen|pointed_dripstone|end_rod|lantern|campfire|brewing_stand|candle|flower_pot|skull|head$|cobweb/;
const DOORISH = /_door$|_fence_gate$|_trapdoor$/;
const THIN = /_fence$|_wall$|^chain$|^iron_chain$|glass_pane$|^iron_bars$/;
const PLANT = /vine|lichen|roots|spore_blossom|moss_carpet|grass$|fern$|bush$|flower|tulip|poppy|dandelion|orchid|allium|bluet|daisy|cornflower|lily_of|peony|lilac|rose_bush|sapling|petals|kelp|seagrass|dripleaf|sugar_cane|sweet_berry|mushroom$|azalea$|hanging_moss/;
// 0 air, 1 solid, 2 transparent (glass/water/leaves, and v5: doors/gates = see-through panels), 3 flat, 4 small (plants, torches, fences...)
const kindOf = (n) => (!n || AIR.test(n) ? 0 : FLAT.test(n) ? 3 : DOORISH.test(n) ? 2 : SMALL.test(n) || THIN.test(n) || PLANT.test(n) ? 4 : TRANSP.test(n) ? 2 : 1);
export const isPlant = (n) => PLANT.test(n || "");

// view rotation: u,v grow toward the camera
const VIEWS = {
  se: { u: [1, 0], v: [0, 1] }, // camera south-east, looking north-west (default)
  sw: { u: [0, 1], v: [-1, 0] },
  nw: { u: [-1, 0], v: [0, -1] },
  ne: { u: [0, -1], v: [1, 0] },
};

function spriteMask(s) {
  // pixel (px,py) relative to top vertex; returns face: 1 top, 2 left(+v), 3 right(+u), 0 none; bit 8 = edge
  const W = 2 * s + 1, H = 2 * s + 1;
  const m = new Uint8Array(W * H);
  const inPoly = (x, y, P) => {
    let ins = false;
    for (let i = 0, j = P.length - 1; i < P.length; j = i++) {
      const [xi, yi] = P[i], [xj, yj] = P[j];
      if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) ins = !ins;
    }
    return ins;
  };
  const top = [[0, 0], [s, s / 2], [0, s], [-s, s / 2]];
  const left = [[-s, s / 2], [0, s], [0, 2 * s], [-s, 1.5 * s]];
  const right = [[0, s], [s, s / 2], [s, 1.5 * s], [0, 2 * s]];
  for (let py = 0; py < H; py++) for (let px = -s; px <= s; px++) {
    const x = px + 0.5 - 0.0001, y = py + 0.5;
    let f = inPoly(x, y, top) ? 1 : inPoly(x, y, left) ? 2 : inPoly(x, y, right) ? 3 : 0;
    m[py * W + (px + s)] = f;
  }
  // edges: pixel whose face differs from a neighbour
  const e = new Uint8Array(m);
  for (let py = 0; py < H; py++) for (let px = 0; px < W; px++) {
    const f = m[py * W + px];
    if (!f) continue;
    const nb = [[1, 0], [-1, 0], [0, 1], [0, -1]].some(([dx, dy]) => {
      const X = px + dx, Y = py + dy;
      return X < 0 || Y < 0 || X >= W || Y >= H || m[Y * W + X] !== f;
    });
    if (nb) e[py * W + px] = f | 8;
  }
  return { m: e, W, H };
}

/**
 * Isometric render. opts: { view:'se'|'sw'|'nw'|'ne', scale (px, even), maxWidth }
 * Returns { png, width, height, blocks }.
 */
export function renderIso(R, opts = {}) {
  const view = VIEWS[opts.view] || VIEWS.se;
  const [x1, y1, z1] = R.lo, [x2, y2, z2] = R.hi;
  const W = x2 - x1 + 1, D = z2 - z1 + 1, Hh = y2 - y1 + 1;
  let s = opts.scale || Math.floor((opts.maxWidth || 1100) / (W + D));
  s = Math.max(2, Math.min(18, s - (s % 2)));
  // collect visible blocks in view coords
  const toUV = (x, z) => [view.u[0] * x + view.u[1] * z, view.v[0] * x + view.v[1] * z];
  const fromDir = (du, dv) => {
    // world offset for +u / +v
    const det = view.u[0] * view.v[1] - view.u[1] * view.v[0];
    return [(du * view.v[1] - dv * view.u[1]) / det, (dv * view.u[0] - du * view.v[0]) / det];
  };
  const U = fromDir(1, 0), Vd = fromDir(0, 1);
  const kindAt = (x, y, z) => kindOf(R.at(x, y, z));
  const items = [];
  for (let y = y1; y <= y2; y++) for (let z = z1; z <= z2; z++) for (let x = x1; x <= x2; x++) {
    const n = R.at(x, y, z);
    const k = kindOf(n);
    if (!k) continue;
    if (k === 1) {
      const up = kindAt(x, y + 1, z), pu = kindAt(x + U[0], y, z + U[1]), pv = kindAt(x + Vd[0], y, z + Vd[1]);
      if (up === 1 && pu === 1 && pv === 1) continue; // fully hidden
    }
    const [u, v] = toUV(x, z);
    items.push([u, v, y, n, k]);
  }
  // display entities → textured quads; continuous world → (U, V, Y) with the cell of block x spanning [u, u+1]
  const offU = view.u[0] < 0 || view.u[1] < 0 ? 1 : 0, offV = view.v[0] < 0 || view.v[1] < 0 ? 1 : 0;
  const toCam = [U[0] + Vd[0], 1, U[1] + Vd[1]];   // world direction toward the iso camera (+u, +v, up)
  const camLen = Math.hypot(...toCam);
  const inBox = (e) => !/_display$/.test(e.type) || (e.pos[0] >= x1 - 1 && e.pos[0] < x2 + 2 && e.pos[2] >= z1 - 1 && e.pos[2] < z2 + 2 && e.pos[1] >= y1 - 2 && e.pos[1] < y2 + 2);
  const { groups, rest } = displayGroups((opts.entities || []).filter(inBox), { camYaw: (Math.atan2(toCam[0], -toCam[2]) * 180) / Math.PI, camPitch: (Math.asin(toCam[1] / camLen) * 180) / Math.PI }, opts);
  // v4: entities (mannequins, players, armor stands, paintings, text displays, carts...) as small figures
  for (const e of rest) {
    if (INVISIBLE.test(e.type)) continue;   // never visible in game (click boxes, markers)
    const ex = Math.floor(e.pos[0]), ey = Math.floor(e.pos[1]), ez = Math.floor(e.pos[2]);
    if (ex < x1 || ex > x2 || ez < z1 || ez > z2 || ey < y1 - 1 || ey > y2 + 1) continue;
    const [u, v] = toUV(ex, ez);
    const c = ENTITY_COLORS[e.type] || [230, 60, 200];
    if (/mannequin|player|armor_stand|villager|zombie|skeleton/.test(e.type)) {
      const lying = e.pose === "sleeping" || e.pose === "swimming";
      if (lying) items.push([u, v, ey, "@" + e.type, 5, c]);
      else { items.push([u, v, ey, "@" + e.type, 5, e.body || c]); items.push([u, v, ey + 1, "@head", 5, [233, 190, 150]]); }
    } else items.push([u, v, ey, "@" + e.type, 5, c]);
  }
  items.sort((a, b) => a[0] + a[1] - (b[0] + b[1]) || a[2] - b[2] || a[0] - b[0]);
  if (!items.length) {
    const png = encodePNG(64, 64, Buffer.alloc(64 * 64 * 3, 230));
    return { png, width: 64, height: 64, blocks: 0 };
  }
  // screen bounds
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (const [u, v, y] of items) {
    const sx = (u - v) * s, sy = ((u + v) * s) / 2 - y * s;
    minX = Math.min(minX, sx - s); maxX = Math.max(maxX, sx + s);
    minY = Math.min(minY, sy); maxY = Math.max(maxY, sy + 2 * s);
  }
  const pad = 12;
  const w = Math.ceil(maxX - minX) + 1 + pad * 2, h = Math.ceil(maxY - minY) + 1 + pad * 2;
  const img = Buffer.alloc(w * h * 3);
  for (let yy = 0; yy < h; yy++) {
    const t = yy / h;
    const c = [Math.round(206 - 40 * t), Math.round(224 - 30 * t), Math.round(240 - 20 * t)];
    for (let xx = 0; xx < w; xx++) img.set(c, (yy * w + xx) * 3);
  }
  const big = spriteMask(s), small = spriteMask(Math.max(2, 2 * Math.round(s / 4)));
  const shade = [0, 1.0, 0.78, 0.62];
  const put = (px, py, rgb, alpha) => {
    if (px < 0 || py < 0 || px >= w || py >= h) return;
    const i = (py * w + px) * 3;
    if (alpha >= 1) { img[i] = rgb[0]; img[i + 1] = rgb[1]; img[i + 2] = rgb[2]; }
    else for (let k = 0; k < 3; k++) img[i + k] = Math.round(img[i + k] * (1 - alpha) + rgb[k] * alpha);
  };
  const tiny = spriteMask(Math.max(2, 2 * Math.round(s / 3)));
  // depth buffer for the display quads: nearness D = U + V + 2Y (exact plane of the face under each pixel), stored as −D
  const zbuf = groups.length ? new Float32Array(w * h).fill(Infinity) : null;
  const ox = minX - pad, oy = minY - pad;
  for (const [u, v, y, n, k, ec] of items) {
    const base = k === 5 ? ec : blockColor(n);
    let sx = Math.round((u - v) * s - minX + pad), sy = Math.round(((u + v) * s) / 2 - y * s - minY + pad);
    let sp = big, alpha = k === 2 ? (DOORISH.test(n) ? 0.6 : 0.45) : 1;
    let onlyTop = false;
    if (k === 3) { sy += s; onlyTop = true; }                        // flat: just a top face at the bottom of the cell
    if (k === 4) { sp = small; sx += 0; sy += s - (sp.W >> 1) + (s >> 2); }   // small thing: small cube
    if (k === 5) { sp = tiny; sy += s - (sp.W >> 1); }                          // entity: a bright figure cube
    const S = (sp.W - 1) >> 1;
    for (let py = 0; py < sp.H; py++) for (let px = 0; px < sp.W; px++) {
      const f = sp.m[py * sp.W + px];
      if (!f) continue;
      const face = f & 7;
      if (onlyTop && face !== 1) continue;
      let m = shade[face];
      if (f & 8) m *= 0.82;
      if (face === 1 && n === "grass_block") m *= 1;
      const rgb = [Math.min(255, base[0] * m), Math.min(255, base[1] * m), Math.min(255, base[2] * m)];
      // grass sides: dirt colour below the green top strip
      if (n === "grass_block" && face !== 1 && py > s * 0.9 + (px > S ? 0 : 0)) {
        const d = blockColor("dirt");
        rgb[0] = d[0] * m; rgb[1] = d[1] * m; rgb[2] = d[2] * m;
      }
      put(sx - S + px, sy + py, rgb, alpha);
      if (zbuf && alpha >= 1) {
        const ix = sx - S + px, iy = sy + py;
        if (ix < 0 || iy < 0 || ix >= w || iy >= h) continue;
        const a = (ix + 0.5 + ox) / s, b = (iy + 0.5 + oy) / s - 1;
        let D;
        if (k >= 4) D = u + v + 2 * y + 2;                                   // small things / markers: their centre
        else if (face === 1) D = 2 * b + 4 * (k === 3 ? y : y + 1);          // top face (flat things sit one block lower)
        else if (face === 2) D = 2 * (a + 2 * (v + 1)) - 2 * b;               // +v face
        else D = 4 * (u + 1) - 2 * a - 2 * b;                                 // +u face
        zbuf[iy * w + ix] = -D;
      }
    }
  }
  if (groups.length) {
    const project = (x, y, z) => {
      const Uc = view.u[0] * x + view.u[1] * z + offU, Vc = view.v[0] * x + view.v[1] * z + offV;
      return [(Uc - Vc) * s - ox, ((Uc + Vc) * s) / 2 - y * s + s - oy, -(Uc + Vc + 2 * y)];
    };
    try { DX.rasterGroups(groups, { W: w, H: h, rgb: img, z: zbuf }, { persp: false, project, toCam, scale: s }); }
    catch (e) { console.error("display raster:", e.message); }
  }
  return { png: encodePNG(w, h, img), width: w, height: h, blocks: items.length, scale: s, displays: groups.length };
}

const ENTITY_COLORS = {
  mannequin: [220, 40, 40], player: [40, 120, 255], armor_stand: [200, 170, 90], painting: [150, 60, 200],
  text_display: [255, 255, 255], item_display: [255, 220, 90], block_display: [255, 220, 90], minecart: [90, 90, 100],
  allay: [80, 220, 255], villager: [150, 100, 60], item_frame: [170, 120, 70], glow_item_frame: [200, 255, 120],
};
export { ENTITY_COLORS };
const INVISIBLE = /^(interaction|marker)$/;   // entities players never see — not drawn (they used to hide what is behind them)

// ───────────── first-person view (voxel ray casting) ─────────────
/**
 * renderFPV(R, {eye:[x,y,z], yaw, pitch, fov, width, height, entities})
 * yaw/pitch in Minecraft degrees (yaw 0 = south, 90 = west; pitch + = down).
 */
export function renderFPV(R, opts = {}) {
  const W = opts.width || 480, H = opts.height || 270, fov = ((opts.fov || 75) * Math.PI) / 180;
  const [ex, ey, ez] = opts.eye;
  const yaw = ((opts.yaw || 0) * Math.PI) / 180, pitch = ((opts.pitch || 0) * Math.PI) / 180;
  // forward vector in MC convention
  const fwd = [-Math.sin(yaw) * Math.cos(pitch), -Math.sin(pitch), Math.cos(yaw) * Math.cos(pitch)];
  const right = [-Math.cos(yaw), 0, -Math.sin(yaw)];
  const up = [right[1] * fwd[2] - right[2] * fwd[1], right[2] * fwd[0] - right[0] * fwd[2], right[0] * fwd[1] - right[1] * fwd[0]];
  const tanF = Math.tan(fov / 2), aspect = W / H;
  const maxD = opts.maxDist || 64;
  const img = Buffer.alloc(W * H * 3);
  // display entities → textured quads (drawn after the voxels, depth-tested); the rest keep their boxes
  const { groups, rest } = displayGroups(opts.entities, { camYaw: opts.yaw || 0, camPitch: opts.pitch || 0 }, opts);
  const zbuf = groups.length ? new Float32Array(W * H).fill(Infinity) : null;          // view depth of the voxel hit
  const tintZ = groups.length ? new Float32Array(W * H).fill(Infinity) : null, tintC = groups.length ? new Uint8Array(W * H * 4) : null;
  const ents = rest.filter((e) => !INVISIBLE.test(e.type)).map((e) => {
    const lying = e.pose === "sleeping" || e.pose === "swimming";
    const hw = /painting|text_display/.test(e.type) ? 0.5 : 0.3, hh = lying ? 0.35 : /mannequin|player|armor_stand|villager/.test(e.type) ? 1.8 : 0.7;
    return { lo: [e.pos[0] - hw, e.pos[1], e.pos[2] - hw], hi: [e.pos[0] + hw, e.pos[1] + hh, e.pos[2] + hw], c: ENTITY_COLORS[e.type] || [230, 60, 200] };
  }).filter((b) => !(ex > b.lo[0] && ex < b.hi[0] && ey > b.lo[1] && ey < b.hi[1] + 0.3 && ez > b.lo[2] && ez < b.hi[2]));   // not the viewer's own body
  const hitBox = (o, d, b) => {
    let t0 = 0, t1 = maxD, n = 1;
    for (let i = 0; i < 3; i++) {
      if (Math.abs(d[i]) < 1e-9) { if (o[i] < b.lo[i] || o[i] > b.hi[i]) return null; continue; }
      let a = (b.lo[i] - o[i]) / d[i], c = (b.hi[i] - o[i]) / d[i];
      if (a > c) [a, c] = [c, a];
      if (a > t0) { t0 = a; n = i; }
      t1 = Math.min(t1, c);
      if (t0 > t1) return null;
    }
    return { t: t0, n };
  };
  for (let py = 0; py < H; py++) for (let px = 0; px < W; px++) {
    const sx = ((px + 0.5) / W * 2 - 1) * tanF * aspect, sy = (1 - (py + 0.5) / H * 2) * tanF;
    const d = [fwd[0] + right[0] * sx + up[0] * sy, fwd[1] + right[1] * sx + up[1] * sy, fwd[2] + right[2] * sx + up[2] * sy];
    const L = Math.hypot(d[0], d[1], d[2]); d[0] /= L; d[1] /= L; d[2] /= L;
    // sky
    let col = [Math.round(150 + 60 * Math.max(0, d[1])), Math.round(190 + 40 * Math.max(0, d[1])), 245];
    let eHit = null;
    for (const b of ents) { const h = hitBox([ex, ey, ez], d, b); if (h && (!eHit || h.t < eHit.t)) eHit = { ...h, c: b.c }; }
    // DDA through the voxels
    let X = Math.floor(ex), Y = Math.floor(ey), Z = Math.floor(ez);
    const step = d.map((v) => (v > 0 ? 1 : -1));
    const tD = d.map((v) => (Math.abs(v) < 1e-9 ? 1e9 : Math.abs(1 / v)));
    const tM = [0, 1, 2].map((i) => { const p = [ex, ey, ez][i], c = [X, Y, Z][i]; return Math.abs(d[i]) < 1e-9 ? 1e9 : (d[i] > 0 ? c + 1 - p : p - c) * tD[i]; });
    let t = 0, face = 1, tint = null, tintA = 0, tintT = Infinity, hitT = Infinity;
    for (let it = 0; it < 400 && t < maxD; it++) {
      const n = R.at(X, Y, Z);
      if (n == null && (Y < R.lo[1] || Y > R.hi[1])) { if (Y < R.lo[1]) { col = [100, 80, 60]; hitT = t; } break; }
      const k = n ? kindOf(n) : 0;
      let hitSmall = false;
      if (k === 4) {   // sample the ray in the middle of this voxel: only the central post counts
        const tn = Math.min(tM[0], tM[1], tM[2]), tm = (t + tn) / 2;
        const fx = ex + d[0] * tm - X, fy = ey + d[1] * tm - Y, fz = ez + d[2] * tm - Z;
        const w = PLANT.test(n) ? 0.34 : THIN.test(n) ? 0.2 : 0.22;
        hitSmall = Math.abs(fx - 0.5) < w && Math.abs(fz - 0.5) < w && (fy < (PLANT.test(n) || THIN.test(n) ? 0.95 : 0.7));
        if (/vine|lichen/.test(n)) hitSmall = ((X * 7 + Y * 13 + Z * 5 + Math.floor(fx * 4) + Math.floor(fy * 4) * 3) & 3) !== 0;   // patchy wall cover
      }
      if (k === 2 && !tint) { tint = blockColor(n); tintA = /water/.test(n) ? 0.55 : DOORISH.test(n) ? 0.55 : 0.3; tintT = t; }
      else if (k === 1 || hitSmall || (k === 3 && face === 1)) {
        if (eHit && eHit.t < t) break;
        const base = blockColor(n);
        const sh = face === 1 ? (d[1] < 0 ? 1.0 : 0.55) : face === 0 ? 0.8 : 0.68;
        const fog = Math.min(1, t / maxD);
        col = base.map((c, i) => Math.round(c * sh * (1 - fog * 0.6) + [190, 210, 240][i] * fog * 0.6));
        eHit = null;
        hitT = t;
        break;
      }
      const a = tM[0] < tM[1] ? (tM[0] < tM[2] ? 0 : 2) : (tM[1] < tM[2] ? 1 : 2);
      t = tM[a]; tM[a] += tD[a];
      if (a === 0) X += step[0]; else if (a === 1) Y += step[1]; else Z += step[2];
      face = a === 1 ? 1 : a === 0 ? 0 : 2;
    }
    if (eHit) { col = eHit.c.map((c) => Math.round(c * (eHit.n === 1 ? 1 : 0.8))); hitT = eHit.t; }
    if (tint) col = col.map((c, i) => Math.round(c * (1 - tintA) + tint[i] * tintA));
    img[(py * W + px) * 3] = col[0]; img[(py * W + px) * 3 + 1] = col[1]; img[(py * W + px) * 3 + 2] = col[2];
    if (zbuf) {   // ray length t → view depth (d is unit, its forward component is 1/L)
      const q = py * W + px;
      zbuf[q] = hitT / L;
      if (tint && tintT < hitT) { tintZ[q] = tintT / L; tintC[q * 4] = tint[0]; tintC[q * 4 + 1] = tint[1]; tintC[q * 4 + 2] = tint[2]; tintC[q * 4 + 3] = Math.round(tintA * 255); }
    }
  }
  if (groups.length) {
    const sky = [190, 210, 240];
    const post = (q, px, py, z, c) => {   // the voxels' fog + glass/water tint in front of the quad
      const sx = ((px + 0.5) / W * 2 - 1) * tanF * aspect, sy = (1 - (py + 0.5) / H * 2) * tanF;
      const f = Math.min(1, (z * Math.sqrt(1 + sx * sx + sy * sy)) / maxD) * 0.6;
      for (let i = 0; i < 3; i++) c[i] = c[i] * (1 - f) + sky[i] * f;
      if (tintZ[q] < z) { const a = tintC[q * 4 + 3] / 255; for (let i = 0; i < 3; i++) c[i] = c[i] * (1 - a) + tintC[q * 4 + i] * a; }
    };
    try {
      DX.rasterGroups(groups, { W, H, rgb: img, z: zbuf, post }, { persp: true, eye: [ex, ey, ez], fwd, right, up, tanF, aspect, near: 0.05, maxD, W, H });
    } catch (e) { console.error("display raster:", e.message); }
  }
  // crosshair
  for (let k = -4; k <= 4; k++) {
    for (const [qx, qy] of [[W / 2 + k, H / 2], [W / 2, H / 2 + k]]) { const i = (Math.floor(qy) * W + Math.floor(qx)) * 3; img[i] = img[i + 1] = img[i + 2] = 255; }
  }
  return { png: encodePNG(W, H, img), width: W, height: H };
}

/** Top-down map with height shading. */
export function renderTop(R, opts = {}) {
  const [x1, y1, z1] = R.lo, [x2, y2, z2] = R.hi;
  const W = x2 - x1 + 1, D = z2 - z1 + 1;
  let k = opts.scale || Math.max(2, Math.min(16, Math.floor((opts.maxWidth || 900) / Math.max(W, D))));
  const w = W * k, h = D * k;
  const img = Buffer.alloc(w * h * 3, 0);
  const tops = [];
  for (let z = z1; z <= z2; z++) for (let x = x1; x <= x2; x++) {
    let yy = y2, n = null;
    for (; yy >= y1; yy--) { const b = R.at(x, yy, z); if (b && !AIR.test(b)) { n = b; break; } }
    tops.push([x, z, yy, n]);
  }
  const hAt = new Map(tops.map(([x, z, yy]) => [x + "," + z, yy]));
  for (const [x, z, yy, n] of tops) {
    const base = n ? blockColor(n) : [40, 40, 48];
    const west = hAt.get(x - 1 + "," + z) ?? yy, north = hAt.get(x + "," + (z - 1)) ?? yy;
    let m = 0.75 + (yy - y1) / Math.max(1, y2 - y1) * 0.35;
    if (yy > west || yy > north) m *= 1.12; else if (yy < west || yy < north) m *= 0.82;
    const rgb = base.map((c) => Math.min(255, c * m));
    for (let py = 0; py < k; py++) for (let px = 0; px < k; px++) {
      const edge = (px === 0 || py === 0) && k >= 6 ? 0.9 : 1;
      const i = (((z - z1) * k + py) * w + (x - x1) * k + px) * 3;
      img[i] = rgb[0] * edge; img[i + 1] = rgb[1] * edge; img[i + 2] = rgb[2] * edge;
    }
  }
  // display entities seen from above (depth = height), when the caller passes entities
  const { groups } = opts.entities ? displayGroups(opts.entities, { camYaw: 180, camPitch: 90 }, opts) : { groups: [] };
  if (groups.length) {
    const zbuf = new Float32Array(w * h);
    for (const [x, z, yy] of tops) for (let py = 0; py < k; py++) zbuf.fill(-(yy + 1), ((z - z1) * k + py) * w + (x - x1) * k, ((z - z1) * k + py) * w + (x - x1 + 1) * k);
    const project = (x, y, z) => [(x - x1) * k, (z - z1) * k, -y];
    try { DX.rasterGroups(groups, { W: w, H: h, rgb: img, z: zbuf }, { persp: false, project, toCam: [0, 1, 0], scale: k }); }
    catch (e) { console.error("display raster:", e.message); }
  }
  return { png: encodePNG(w, h, img), width: w, height: h, scale: k, displays: groups.length };
}
