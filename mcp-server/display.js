/**
 * display.js — display entities for the screenshot renderer (render.js), no dependencies.
 * item_display / block_display / text_display are drawn as what players see: textured quads built from the server
 * resource pack (+ the vanilla client jar when one is on this machine: vanilla item and block models, block states,
 * the font), placed with the game's display-renderer math, rasterised with a depth buffer against the voxel picture.
 * Without a pack or a jar it still works: missing textures become flat colours, text uses placeholder glyphs.
 *
 *   buildGroups(entities, { camYaw, camPitch, packs, jar, version, colorOf }) → { groups, rest, stats }
 *       groups = [{ c, r, quads }] per entity (world space); rest = entities not handled here (keep their old markers)
 *   rasterGroups(groups, target, cam)   depth-tested drawing into an RGB buffer (perspective or orthographic)
 *   decodePNG(buf) → { w, h, data: RGBA Uint8Array }
 *
 * The client jar (optional): MC_CLIENT_JAR=<path> or "off"; else pinkgolem.json "client_jar" (a path, or false = never);
 * else the newest <launcher dir>/versions/<v>/<v>.jar (the configured mc_version first) on macOS, Linux or Windows.
 * It is only read, on this machine.
 *
 * Conventions (MC 26.x DisplayRenderer): world = pos · O · T(translation) · L(left_rotation) · S(scale) · R(right_rotation)
 * with O = Ry(-yaw) · Rx(pitch) (billboard: camera angles instead); item_display then Ry(180°) · display-context
 * transform · (model/16 − 0.5); block_display the block model in 0..1 from the origin; text_display Ry(180°) ·
 * S(−0.025) with the text panel's bottom edge at the origin, readable from the entity's facing side (local +z).
 * Caches live on globalThis (this module is re-imported on every hot reload) and are dropped when idle.
 */
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import zlib from "node:zlib";

const Q = new URL(import.meta.url).search;   // the hot-reload query of render.js → share the tool layer's devkit instance
const { readZip } = await import("./lib/devkit.js" + Q);

// ───────────── caches (shared across hot reloads) ─────────────
const CACHE_V = 2;   // bump when cached structures / model resolution change (drops what older code cached)
let C = globalThis.__mcDisplayCache;
if (!C || C.v !== CACHE_V) {
  if (C) { if (C.timer) clearInterval(C.timer); C.zips?.clear(); C.tex?.clear(); C.quads?.clear(); C.src = []; }
  C = globalThis.__mcDisplayCache = { v: CACHE_V, zips: new Map(), key: "", src: [], tex: new Map(), texBytes: 0, models: new Map(), json: new Map(), quads: new Map(), font: undefined, lastUse: 0, timer: null };
}
const ZIP_IDLE_MS = 3 * 60e3, IDLE_MS = 10 * 60e3;   // the pack + jar buffers (~70 MB) go first; decoded textures later
function clearDerived() { C.tex.clear(); C.texBytes = 0; C.models.clear(); C.json.clear(); C.quads.clear(); C.font = undefined; }
function armExpiry() {
  if (C.timer) return;
  const cache = C;
  cache.timer = setInterval(() => {
    const now = Date.now();
    for (const [k, z] of cache.zips) if (z.used < now - ZIP_IDLE_MS) { cache.zips.delete(k); cache.src = []; }
    if (cache.lastUse < now - IDLE_MS) { cache.tex.clear(); cache.texBytes = 0; cache.models.clear(); cache.json.clear(); cache.quads.clear(); cache.font = undefined; }
    if (!cache.zips.size && !cache.tex.size) { clearInterval(cache.timer); cache.timer = null; }
  }, 60e3);
  cache.timer.unref?.();
}
function zipIndex(file) {
  if (!file) return null;
  let st;
  try { st = fs.statSync(file); } catch { return null; }
  let z = C.zips.get(file);
  if (!z || z.mtime !== st.mtimeMs || z.size !== st.size) {
    let entries;
    try { entries = readZip(fs.readFileSync(file)); } catch { return null; }
    z = { file, mtime: st.mtimeMs, size: st.size, map: new Map(entries.map((e) => [e.name, e])) };
    C.zips.set(file, z);
  }
  z.used = Date.now();
  armExpiry();
  return z;
}

// the vanilla client jar (models, block states, textures, font) — optional, see the header
const cmpVer = (a, b) => { const A = a.split(".").map(Number), B = b.split(".").map(Number); for (let i = 0; i < Math.max(A.length, B.length); i++) if ((A[i] || 0) !== (B[i] || 0)) return (A[i] || 0) - (B[i] || 0); return 0; };
const OFF = /^(off|none|no|0|false)$/i;
function launcherDirs() {
  const h = os.homedir();
  return [
    process.platform === "darwin" && path.join(h, "Library", "Application Support", "minecraft"),
    process.env.APPDATA && path.join(process.env.APPDATA, ".minecraft"),
    path.join(h, ".minecraft"),
  ].filter(Boolean);
}
function findJar(want, version) {
  const env = process.env.MC_CLIENT_JAR;
  const setting = env != null && env !== "" ? env : want;
  const key = `${setting}|${version}`;
  if (C.jarKey === key && C.jarChecked && Date.now() - C.jarChecked < 300e3) return C.jarPath;
  let found = null;
  if (setting === false || (typeof setting === "string" && OFF.test(setting))) found = null;
  else if (typeof setting === "string" && setting && !/^auto$/i.test(setting)) found = fs.existsSync(setting) ? setting : null;
  else {
    for (const h of launcherDirs()) {
      let vs;
      try { vs = fs.readdirSync(path.join(h, "versions")); } catch { continue; }
      const nums = vs.filter((v) => /^\d+(\.\d+)+$/.test(v)).sort(cmpVer).reverse();
      for (const v of version ? [String(version), ...nums] : nums) {
        const j = path.join(h, "versions", v, v + ".jar");
        if (fs.existsSync(j)) { found = j; break; }
      }
      if (found) break;
    }
  }
  C.jarPath = found; C.jarChecked = Date.now(); C.jarKey = key;
  return found;
}
/** packs: zip paths, first wins (the built server pack, or its parts); jar / version: see the header */
function setup(packs, jar, version) {
  const list = (Array.isArray(packs) ? packs : packs ? [packs] : []).map((f) => zipIndex(f)).filter(Boolean);
  const jarPath = findJar(jar, version);
  const j = jarPath ? zipIndex(jarPath) : null;
  const key = `${list.map((z) => z.file + "@" + z.mtime).join(",")}|${jarPath}|${j?.mtime}`;
  if (key !== C.key) { clearDerived(); C.key = key; }
  C.src = [...list, j].filter(Boolean);
  C.lastUse = Date.now();
  return { packs: list.length, jar: !!j };
}
function asset(name) {
  for (const z of C.src) { const e = z.map.get(name); if (e) { try { return e.data; } catch { return null; } } }
  return null;
}
function json(name) {
  if (C.json.has(name)) return C.json.get(name);
  let v = null;
  const b = asset(name);
  if (b) try { v = JSON.parse(b.toString("utf8").replace(/^﻿/, "")); } catch {}
  C.json.set(name, v);
  return v;
}

// ───────────── PNG decoder (8/16-bit, palette/grey 1-8 bit, tRNS, Adam7) ─────────────
const ADAM7 = [[0, 0, 8, 8], [4, 0, 8, 8], [0, 4, 4, 8], [2, 0, 4, 4], [0, 2, 2, 4], [1, 0, 2, 2], [0, 1, 1, 2]];
export function decodePNG(buf) {
  if (buf.readUInt32BE(0) !== 0x89504e47) throw new Error("not a PNG");
  let p = 8, w = 0, h = 0, depth = 8, ct = 6, il = 0, pal = null, trns = null;
  const idat = [];
  while (p + 8 <= buf.length) {
    const len = buf.readUInt32BE(p), type = buf.toString("latin1", p + 4, p + 8), d = buf.subarray(p + 8, p + 8 + len);
    if (type === "IHDR") { w = d.readUInt32BE(0); h = d.readUInt32BE(4); depth = d[8]; ct = d[9]; il = d[12]; }
    else if (type === "PLTE") pal = d;
    else if (type === "tRNS") trns = d;
    else if (type === "IDAT") idat.push(d);
    else if (type === "IEND") break;
    p += 12 + len;
  }
  const ch = { 0: 1, 2: 3, 3: 1, 4: 2, 6: 4 }[ct];
  if (!ch || !w || !h) throw new Error("unsupported PNG");
  const raw = zlib.inflateSync(Buffer.concat(idat));
  const out = new Uint8Array(w * h * 4);
  const bpp = Math.max(1, (ch * depth) >> 3);
  const maxv = (1 << Math.min(depth, 8)) - 1;
  const key = trns && ct === 0 ? trns.readUInt16BE(0) : null;
  const keyRGB = trns && ct === 2 && trns.length >= 6 ? [trns.readUInt16BE(0), trns.readUInt16BE(2), trns.readUInt16BE(4)] : null;
  let off = 0;
  for (const [x0, y0, dx, dy] of il ? ADAM7 : [[0, 0, 1, 1]]) {
    const pw = Math.ceil((w - x0) / dx), ph = Math.ceil((h - y0) / dy);
    if (pw <= 0 || ph <= 0) continue;
    const stride = Math.ceil((pw * ch * depth) / 8);
    let prev = new Uint8Array(stride), cur = new Uint8Array(stride);
    for (let y = 0; y < ph; y++) {
      const ft = raw[off++];
      cur.set(raw.subarray(off, off + stride)); off += stride;
      if (ft === 1) for (let i = bpp; i < stride; i++) cur[i] = (cur[i] + cur[i - bpp]) & 255;
      else if (ft === 2) for (let i = 0; i < stride; i++) cur[i] = (cur[i] + prev[i]) & 255;
      else if (ft === 3) for (let i = 0; i < stride; i++) cur[i] = (cur[i] + (((i >= bpp ? cur[i - bpp] : 0) + prev[i]) >> 1)) & 255;
      else if (ft === 4) for (let i = 0; i < stride; i++) {
        const a = i >= bpp ? cur[i - bpp] : 0, b = prev[i], c = i >= bpp ? prev[i - bpp] : 0;
        const pp = a + b - c, pa = Math.abs(pp - a), pb = Math.abs(pp - b), pc = Math.abs(pp - c);
        cur[i] = (cur[i] + (pa <= pb && pa <= pc ? a : pb <= pc ? b : c)) & 255;
      }
      const oy = y0 + y * dy;
      if (depth === 8 && !il && (ct === 6 || ct === 2) && !keyRGB) {   // fast paths
        let o = oy * w * 4;
        if (ct === 6) out.set(cur, o);
        else for (let i = 0; i < stride; i += 3, o += 4) { out[o] = cur[i]; out[o + 1] = cur[i + 1]; out[o + 2] = cur[i + 2]; out[o + 3] = 255; }
      } else {
        for (let x = 0; x < pw; x++) {
          const o = (oy * w + x0 + x * dx) * 4;
          const s = (c) => {   // sample c of pixel x at native depth
            if (depth === 8) return cur[x * ch + c];
            if (depth === 16) return (cur[(x * ch + c) * 2] << 8) | cur[(x * ch + c) * 2 + 1];
            const bit = (x * ch + c) * depth;
            return (cur[bit >> 3] >> (8 - depth - (bit & 7))) & maxv;
          };
          const to8 = (v) => (depth === 16 ? v >> 8 : depth === 8 ? v : Math.round((v * 255) / maxv));
          if (ct === 3) {
            const i = s(0);
            out[o] = pal ? pal[i * 3] : 0; out[o + 1] = pal ? pal[i * 3 + 1] : 0; out[o + 2] = pal ? pal[i * 3 + 2] : 0;
            out[o + 3] = trns && i < trns.length ? trns[i] : 255;
          } else if (ct === 0 || ct === 4) {
            const g = s(0), G = to8(g);
            out[o] = out[o + 1] = out[o + 2] = G;
            out[o + 3] = ct === 4 ? to8(s(1)) : key != null && g === key ? 0 : 255;
          } else {
            const r = s(0), g = s(1), b = s(2);
            out[o] = to8(r); out[o + 1] = to8(g); out[o + 2] = to8(b);
            out[o + 3] = ct === 6 ? to8(s(3)) : keyRGB && r === keyRGB[0] && g === keyRGB[1] && b === keyRGB[2] ? 0 : 255;
          }
        }
      }
      [prev, cur] = [cur, prev];
    }
  }
  return { w, h, data: out };
}

// ───────────── textures ─────────────
const nsOf = (id) => { const s = String(id); const i = s.indexOf(":"); return i < 0 ? ["minecraft", s] : [s.slice(0, i), s.slice(i + 1)]; };
function finishTex(t) {
  let tr = false;
  for (let i = 3; i < t.data.length; i += 4) { const a = t.data[i]; if (a >= 4 && a < 250) { tr = true; break; } }
  t.translucent = tr;
  t.mips = [t];
  return t;
}
function solidTex(rgb, a = 255) { return finishTex({ w: 1, h: 1, fh: 1, data: Uint8Array.from([rgb[0], rgb[1], rgb[2], a]), missing: true }); }
function texture(id, colorOf) {
  const [ns, p] = nsOf(id);
  const name = `assets/${ns}/textures/${p}.png`;
  let t = C.tex.get(name);
  if (t) return t;
  const b = asset(name);
  if (b) {
    try {
      const d = decodePNG(b);
      let fh = d.h;
      const mm = d.h > d.w ? json(name + ".mcmeta") : null;
      if (mm?.animation) fh = Math.min(d.h, mm.animation.height || mm.animation.width || d.w);
      t = finishTex({ w: d.w, h: d.h, fh, data: d.data });
    } catch {}
  }
  if (!t) t = solidTex(colorOf ? colorOf(p.split("/").pop()) : [200, 0, 200]);
  if (C.texBytes > 160e6) { C.tex.clear(); C.quads.clear(); C.texBytes = 0; }
  C.tex.set(name, t); C.texBytes += t.data.length;
  return t;
}
function mipOf(t, level) {
  while (t.mips.length <= level) {
    const s = t.mips[t.mips.length - 1];
    if (s.w <= 1 && s.fh <= 1) break;
    const w = Math.max(1, s.w >> 1), h = Math.max(1, s.fh >> 1), d = new Uint8Array(w * h * 4);
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      let r = 0, g = 0, b = 0, a = 0, n = 0;
      for (let k = 0; k < 4; k++) {
        const sx = Math.min(s.w - 1, x * 2 + (k & 1)), sy = Math.min(s.fh - 1, y * 2 + (k >> 1)), i = (sy * s.w + sx) * 4, al = s.data[i + 3];
        r += s.data[i] * al; g += s.data[i + 1] * al; b += s.data[i + 2] * al; a += al; n++;
      }
      const o = (y * w + x) * 4;
      if (a) { d[o] = r / a; d[o + 1] = g / a; d[o + 2] = b / a; }
      d[o + 3] = a / n;
    }
    t.mips.push({ w, h, fh: h, data: d });
    C.texBytes += d.length;
  }
  return t.mips[Math.min(level, t.mips.length - 1)];
}

// ───────────── models ─────────────
const BUILTIN = {
  "minecraft:block/block": {},
  "minecraft:block/cube": { parent: "minecraft:block/block", elements: [{ from: [0, 0, 0], to: [16, 16, 16], faces: { down: { texture: "#down" }, up: { texture: "#up" }, north: { texture: "#north" }, south: { texture: "#south" }, west: { texture: "#west" }, east: { texture: "#east" } } }] },
  "minecraft:block/cube_all": { parent: "minecraft:block/cube", textures: { particle: "#all", down: "#all", up: "#all", north: "#all", south: "#all", west: "#all", east: "#all" } },
  "minecraft:block/cube_column": { parent: "minecraft:block/cube", textures: { particle: "#side", down: "#end", up: "#end", north: "#side", south: "#side", west: "#side", east: "#side" } },
  "minecraft:block/cube_bottom_top": { parent: "minecraft:block/cube", textures: { particle: "#side", down: "#bottom", up: "#top", north: "#side", south: "#side", west: "#side", east: "#side" } },
  "minecraft:item/generated": { parent: "builtin/generated" },
  "minecraft:item/handheld": { parent: "minecraft:item/generated" },
};
function modelJson(id) { const [ns, p] = nsOf(id); return json(`assets/${ns}/models/${p}.json`) || BUILTIN[`${ns}:${p}`] || null; }
function resolveModel(id) {
  const key = String(id);
  if (C.models.has(key)) return C.models.get(key);
  const chain = [];
  let cur = id, generated = false;
  for (let i = 0; i < 24 && cur; i++) {
    const c = String(cur).replace(/^minecraft:/, "");
    if (c === "builtin/generated") { generated = true; break; }
    if (c.startsWith("builtin/")) break;
    const j = modelJson(cur);
    if (!j) break;
    chain.push(j); cur = j.parent;
  }
  const textures = {}, display = {};
  for (let i = chain.length - 1; i >= 0; i--) { Object.assign(textures, chain[i].textures || {}); Object.assign(display, chain[i].display || {}); }
  let elements = null;
  for (const j of chain) if (Array.isArray(j.elements)) { elements = j.elements; break; }
  if (!elements && generated) {
    elements = [];
    for (let i = 0; i < 8 && textures["layer" + i]; i++)
      elements.push({ from: [0, 0, 7.5], to: [16, 16, 8.5], faces: { south: { uv: [0, 0, 16, 16], texture: "#layer" + i, tintindex: i }, north: { uv: [16, 0, 0, 16], texture: "#layer" + i, tintindex: i } } });
  }
  const m = chain.length || generated ? { textures, display, elements: elements || [] } : null;
  C.models.set(key, m);
  return m;
}
function texRef(textures, ref) {
  let r = ref;
  for (let i = 0; i < 12 && typeof r === "string" && r.startsWith("#"); i++) r = textures[r.slice(1)];
  if (r && typeof r === "object") r = r.sprite;
  return typeof r === "string" && !r.startsWith("#") ? r : null;
}
// item model definition (assets/<ns>/items/<name>.json) → drawable leaves [{ model, tints }]
function itemLeaves(node, ctx, out = [], d = 0) {
  if (!node || d > 8) return out;
  if (typeof node === "string") { out.push({ model: node, tints: [] }); return out; }
  const t = String(node.type || "minecraft:model").replace(/^minecraft:/, "");
  if (t === "model") out.push({ model: node.model, tints: node.tints || [] });
  else if (t === "composite") for (const m of node.models || []) itemLeaves(m, ctx, out, d + 1);
  else if (t === "condition") itemLeaves(node.on_false || node.on_true, ctx, out, d + 1);
  else if (t === "select") {   // display_context: the case for this item_display's context (e.g. trident: 'fixed' → flat icon)
    const hit = String(node.property || "").replace(/^minecraft:/, "") === "display_context" &&
      (node.cases || []).find((c) => [].concat(c.when).map(String).includes(ctx));
    itemLeaves(hit ? hit.model : node.fallback || node.cases?.[0]?.model, ctx, out, d + 1);
  }
  else if (t === "range_dispatch") itemLeaves(node.fallback || node.entries?.[0]?.model, ctx, out, d + 1);
  else if (t === "special" && node.base) out.push({ model: node.base, tints: [] });
  return out;
}
function rgbInt(c) {
  if (Array.isArray(c)) return (Math.round(c[0] * 255) << 16) | (Math.round(c[1] * 255) << 8) | Math.round(c[2] * 255);
  return Number(c) & 0xffffff;
}
function tintOf(t, dye) {
  if (!t) return null;
  const ty = String(t.type || "").replace(/^minecraft:/, "");
  const c = ty === "dye" ? (dye ?? t.default) : ty === "constant" ? t.value : t.default;
  if (c == null) return null;
  const v = rgbInt(c);
  return v === 0xffffff ? null : [(v >> 16) & 255, (v >> 8) & 255, v & 255];
}

// ───────────── matrices: 3x4 row-major affine [m00 m01 m02 m03, m10 .. m13, m20 .. m23] ─────────────
const I = () => [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0];
function mul(A, B) {
  const r = new Array(12);
  for (let i = 0; i < 3; i++) for (let j = 0; j < 4; j++)
    r[i * 4 + j] = A[i * 4] * B[j] + A[i * 4 + 1] * B[4 + j] + A[i * 4 + 2] * B[8 + j] + (j === 3 ? A[i * 4 + 3] : 0);
  return r;
}
const T3 = (x, y, z) => [1, 0, 0, x, 0, 1, 0, y, 0, 0, 1, z];
const S3 = (x, y, z) => [x, 0, 0, 0, 0, y, 0, 0, 0, 0, z, 0];
const RX = (a) => { const c = Math.cos(a), s = Math.sin(a); return [1, 0, 0, 0, 0, c, -s, 0, 0, s, c, 0]; };
const RY = (a) => { const c = Math.cos(a), s = Math.sin(a); return [c, 0, s, 0, 0, 1, 0, 0, -s, 0, c, 0]; };
const RZ = (a) => { const c = Math.cos(a), s = Math.sin(a); return [c, -s, 0, 0, s, c, 0, 0, 0, 0, 1, 0]; };
function quat(q) {   // [x,y,z,w] or {angle, axis} → rotation matrix
  if (q && !Array.isArray(q) && q.axis) {
    const a = +q.angle || 0, ax = q.axis.map(Number), L = Math.hypot(...ax) || 1, s = Math.sin(a / 2);
    q = [(ax[0] / L) * s, (ax[1] / L) * s, (ax[2] / L) * s, Math.cos(a / 2)];
  }
  if (!Array.isArray(q) || q.length < 4) return I();
  let [x, y, z, w] = q.map(Number);
  const n = Math.hypot(x, y, z, w) || 1; x /= n; y /= n; z /= n; w /= n;
  return [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w), 0,
    2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w), 0,
    2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y), 0];
}
const ap = (M, x, y, z) => [M[0] * x + M[1] * y + M[2] * z + M[3], M[4] * x + M[5] * y + M[6] * z + M[7], M[8] * x + M[9] * y + M[10] * z + M[11]];
const DEG = Math.PI / 180;
function tfMatrix(tf) {
  if (Array.isArray(tf) && tf.length >= 12) return tf.slice(0, 12).map(Number);   // a 4x4 row-major matrix
  if (!tf || typeof tf !== "object") return I();
  const t = (tf.translation || [0, 0, 0]).map(Number), s = (tf.scale || [1, 1, 1]).map(Number);
  return mul(mul(mul(T3(t[0], t[1], t[2]), quat(tf.left_rotation)), S3(s[0], s[1], s[2])), quat(tf.right_rotation));
}
function displayCtx(display, ctx) {   // ItemTransform.apply (+ the −0.5 centring that follows it)
  const t = display?.[ctx];
  let M = I();
  if (t) {
    const left = /lefthand/.test(ctx), cl = (v, a) => Math.max(-a, Math.min(a, Number(v) || 0));
    const tr = (t.translation || [0, 0, 0]).map((v) => cl(v, 80) / 16), r = (t.rotation || [0, 0, 0]).map(Number), sc = (t.scale || [1, 1, 1]).map((v) => cl(v, 4));
    if (left) { tr[0] = -tr[0]; r[1] = -r[1]; r[2] = -r[2]; }
    M = mul(mul(mul(T3(tr[0], tr[1], tr[2]), RX(r[0] * DEG)), mul(RY(r[1] * DEG), RZ(r[2] * DEG))), S3(sc[0], sc[1], sc[2]));
    if (t.right_rotation) { const q = t.right_rotation.map(Number); M = mul(M, mul(RX(q[0] * DEG), mul(RY(q[1] * DEG), RZ(q[2] * DEG)))); }
  }
  return mul(M, T3(-0.5, -0.5, -0.5));
}

// ───────────── model → local quads ─────────────
// face vertex order = MC FaceInfo (0 = from, 1 = to per axis); (v1−v0)×(v2−v0) is the outward normal
const FACE = {
  down: [[0, 0, 1], [0, 0, 0], [1, 0, 0], [1, 0, 1]], up: [[0, 1, 0], [0, 1, 1], [1, 1, 1], [1, 1, 0]],
  north: [[1, 1, 0], [1, 0, 0], [0, 0, 0], [0, 1, 0]], south: [[0, 1, 1], [0, 0, 1], [1, 0, 1], [1, 1, 1]],
  west: [[0, 1, 0], [0, 0, 0], [0, 0, 1], [0, 1, 1]], east: [[1, 1, 1], [1, 0, 1], [1, 0, 0], [1, 1, 0]],
};
function autoUV(face, f, t) {
  switch (face) {
    case "down": return [f[0], 16 - t[2], t[0], 16 - f[2]];
    case "up": return [f[0], f[2], t[0], t[2]];
    case "north": return [16 - t[0], 16 - t[1], 16 - f[0], 16 - f[1]];
    case "south": return [f[0], 16 - t[1], t[0], 16 - f[1]];
    case "west": return [f[2], 16 - t[1], t[2], 16 - f[1]];
    default: return [16 - t[2], 16 - t[1], 16 - f[2], 16 - f[1]];
  }
}
function elementRot(rot) {   // → fn(p) in model units (0..16)
  if (!rot) return null;
  const o = (rot.origin || [8, 8, 8]).map(Number);
  let R, sc = [1, 1, 1];
  if (rot.axis) {
    const a = (Number(rot.angle) || 0) * DEG;
    R = rot.axis === "x" ? RX(a) : rot.axis === "y" ? RY(a) : RZ(a);
    if (rot.rescale && Math.cos(a) > 1e-3) { const f = 1 / Math.cos(a); sc = [rot.axis === "x" ? 1 : f, rot.axis === "y" ? 1 : f, rot.axis === "z" ? 1 : f]; }
  } else if (rot.x != null || rot.y != null || rot.z != null) R = mul(RX((+rot.x || 0) * DEG), mul(RY((+rot.y || 0) * DEG), RZ((+rot.z || 0) * DEG)));
  else return null;
  return (p) => { const q = ap(R, p[0] - o[0], p[1] - o[1], p[2] - o[2]); return [q[0] * sc[0] + o[0], q[1] * sc[1] + o[1], q[2] * sc[2] + o[2]]; };
}
/** model id → quads in the local space given by M (applied to model/16): [{ v: [12], uv: [8] (0..1), tex, tint }] */
function modelQuads(modelId, M, tints, dye, colorOf) {
  const m = resolveModel(modelId);
  if (!m) return null;
  const out = [];
  for (const el of m.elements) {
    const f = (el.from || [0, 0, 0]).map(Number), t = (el.to || [16, 16, 16]).map(Number), rot = elementRot(el.rotation);
    for (const [face, fd] of Object.entries(el.faces || {})) {
      const sel = FACE[face];
      if (!sel || !fd) continue;
      const ref = texRef(m.textures, fd.texture);
      const tex = ref ? texture(ref, colorOf) : solidTex([200, 0, 200]);
      const uvs = (fd.uv || autoUV(face, f, t)).map(Number);
      const sh = (((Number(fd.rotation) || 0) / 90) | 0) & 3;
      const v = [], uv = [];
      for (let i = 0; i < 4; i++) {
        let p = [sel[i][0] ? t[0] : f[0], sel[i][1] ? t[1] : f[1], sel[i][2] ? t[2] : f[2]];
        if (rot) p = rot(p);
        v.push(...ap(M, p[0] / 16, p[1] / 16, p[2] / 16));
        const j = (i + sh) & 3;
        uv.push((j === 0 || j === 1 ? uvs[0] : uvs[2]) / 16, (j === 0 || j === 3 ? uvs[1] : uvs[3]) / 16);
      }
      const ti = fd.tintindex == null ? -1 : Number(fd.tintindex);
      out.push({ v, uv, tex, tint: ti >= 0 ? (typeof tints === "function" ? tints(ti) : tintOf(tints?.[ti], dye)) : null });
    }
  }
  return out;
}

// item_display: the item's model in item space (after Ry(180) · display ctx · −0.5)
function itemLocal(e, colorOf) {
  const d = e.display;
  const id = d.model || d.item;
  if (!id) return null;
  const ctx = String(d.item_display || "none");
  const key = `i|${id}|${ctx}|${d.dye ?? ""}`;
  if (C.quads.has(key)) return C.quads.get(key);
  const [ns, p] = nsOf(id);
  const def = json(`assets/${ns}/items/${p}.json`)?.model;
  if (`${ns}:${p}` === "minecraft:air" || /(^|:)empty$/.test(String(def?.type || ""))) { C.quads.set(key, []); return []; }   // shows nothing
  const leaves = itemLeaves(def, ctx);
  if (!leaves.length && d.model && resolveModel(id)) leaves.push({ model: id, tints: [] });   // bare model id
  let quads = null;
  for (const lf of leaves) {
    const m = resolveModel(lf.model);
    if (!m) continue;
    const M = mul(RY(Math.PI), displayCtx(m.display, ctx));
    const q = modelQuads(lf.model, M, lf.tints, d.dye == null ? null : Number(d.dye), colorOf);
    if (q) (quads ||= []).push(...q);
  }
  C.quads.set(key, quads && quads.length ? quads : null);
  return C.quads.get(key);
}

// block_display: the block's model(s) from its block state (vanilla jar), else a box in its map colour
function matchWhen(when, props) {
  if (!when) return true;
  if (when.OR) return when.OR.some((w) => matchWhen(w, props));
  if (when.AND) return when.AND.every((w) => matchWhen(w, props));
  return Object.entries(when).every(([k, v]) => String(v).split("|").includes(String(props[k] ?? "")));
}
function blockLocal(e, colorOf) {
  const bs = e.display.block;
  const name = typeof bs === "string" ? bs : bs?.Name;
  if (!name) return null;
  const props = (bs && typeof bs === "object" && bs.Properties) || {};
  const key = `b|${name}|${JSON.stringify(props)}`;
  if (C.quads.has(key)) return C.quads.get(key);
  const [ns, p] = nsOf(name);
  const st = json(`assets/${ns}/blockstates/${p}.json`);
  const parts = [];
  if (st?.variants) {
    let best = null;
    for (const [k, v] of Object.entries(st.variants)) {
      const ok = k === "" || k.split(",").every((kv) => { const [a, b] = kv.split("="); return String(props[a] ?? "") === b; });
      if (ok) { best = v; break; }
    }
    best ??= Object.values(st.variants)[0];
    if (best) parts.push(Array.isArray(best) ? best[0] : best);
  } else if (Array.isArray(st?.multipart)) {
    for (const mp of st.multipart) if (matchWhen(mp.when, props)) parts.push(Array.isArray(mp.apply) ? mp.apply[0] : mp.apply);
  }
  const lc = colorOf ? colorOf(p) : [180, 180, 180];
  const tints = () => (/water/.test(p) ? [63, 118, 228] : /leaves|vine|lily|fern|grass|bush|sugar_cane/.test(p) ? [92, 160, 64] : /stem/.test(p) ? lc : [120, 180, 80]);
  let quads = [];
  for (const v of parts) {
    if (!v?.model) continue;
    const R = mul(mul(T3(0.5, 0.5, 0.5), mul(RY(-(Number(v.y) || 0) * DEG), RX(-(Number(v.x) || 0) * DEG))), T3(-0.5, -0.5, -0.5));
    const q = modelQuads(v.model, R, tints, null, colorOf);
    if (q) quads.push(...q);
  }
  if (!quads.length) {   // no model (no jar / entity-rendered block): a box in the block's map colour
    const tex = solidTex(lc);
    for (const [face, sel] of Object.entries(FACE)) {
      const v = [];
      for (let i = 0; i < 4; i++) v.push(sel[i][0], sel[i][1], sel[i][2]);
      quads.push({ v, uv: [0, 0, 0, 1, 1, 1, 1, 0], tex, tint: null, face });
    }
  }
  C.quads.set(key, quads);
  return quads;
}

// ───────────── text_display ─────────────
const NAMED = { black: 0x000000, dark_blue: 0x0000aa, dark_green: 0x00aa00, dark_aqua: 0x00aaaa, dark_red: 0xaa0000, dark_purple: 0xaa00aa, gold: 0xffaa00, gray: 0xaaaaaa,
  dark_gray: 0x555555, blue: 0x5555ff, green: 0x55ff55, aqua: 0x55ffff, red: 0xff5555, light_purple: 0xff55ff, yellow: 0xffff55, white: 0xffffff };
function colorVal(c) {
  if (c == null) return null;
  if (typeof c === "number") return c & 0xffffff;
  const s = String(c);
  if (s.startsWith("#")) return parseInt(s.slice(1), 16) & 0xffffff;
  return NAMED[s] ?? null;
}
const truthy = (v) => v === true || v === 1 || v === "1" || v === "true";
/** text component (string / {text, extra, color, bold, translate} / list) → runs [{ s, color, bold }] */
function flatten(c, st = { color: 0xffffff, bold: false }, out = [], d = 0) {
  if (c == null || d > 20) return out;
  if (typeof c === "string" || typeof c === "number" || typeof c === "boolean") { out.push({ s: String(c), ...st }); return out; }
  if (Array.isArray(c)) { if (c.length) { const s2 = styleOf(c[0], st); flatten(c[0], st, out, d + 1); for (const x of c.slice(1)) flatten(x, s2, out, d + 1); } return out; }
  if (typeof c !== "object") return out;
  const s2 = styleOf(c, st);
  const txt = c.text ?? (c.translate != null ? (c.fallback ?? c.translate) : c.keybind ?? (c.score ? "0" : c.selector ?? c.nbt ?? ""));
  if (txt !== "") out.push({ s: String(txt), ...s2 });
  for (const x of c.extra || []) flatten(x, s2, out, d + 1);
  return out;
}
function styleOf(c, st) {
  if (!c || typeof c !== "object" || Array.isArray(c)) return st;
  return { color: colorVal(c.color) ?? st.color, bold: c.bold != null ? truthy(c.bold) : st.bold };
}

// font: bitmap providers of the vanilla jar (ascii, accented, nonlatin_european) + GNU Unifont (launcher assets)
function loadFont() {
  if (C.font !== undefined) return C.font;
  const font = { map: new Map(), space: { " ": 4 }, hex: null };
  C.font = font;
  const sp = json("assets/minecraft/font/include/space.json");
  for (const pr of sp?.providers || []) if (pr.type === "space") Object.assign(font.space, pr.advances || {});
  const df = json("assets/minecraft/font/include/default.json");
  for (const pr of df?.providers || []) {
    if (pr.type !== "bitmap" || !pr.file) continue;
    const [ns, p] = nsOf(pr.file);
    const b = asset(`assets/${ns}/textures/${p}`);
    if (!b) continue;
    let img;
    try { img = decodePNG(b); } catch { continue; }
    const rows = pr.chars || [], cols = Math.max(...rows.map((r) => [...r].length));
    if (!rows.length || !cols) continue;
    const cw = Math.floor(img.w / cols), chh = Math.floor(img.h / rows.length), height = pr.height ?? 8, ascent = pr.ascent ?? 7, sc = height / chh;
    bitmapGlyphs(font, img, rows, cw, chh, sc, ascent);
  }
  // GNU Unifont (unihex, from the launcher's assets next to the jar) for everything else: Hebrew, Arabic, Cyrillic…
  try {
    const jar = C.jarPath;
    if (jar) {
      const home = path.resolve(path.dirname(jar), "..", "..");
      const ver = JSON.parse(fs.readFileSync(jar.replace(/\.jar$/, ".json"), "utf8"));
      const idx = JSON.parse(fs.readFileSync(path.join(home, "assets", "indexes", ver.assetIndex.id + ".json"), "utf8")).objects;
      const o = idx["minecraft/font/unifont.zip"];
      if (o) {
        const z = readZip(fs.readFileSync(path.join(home, "assets", "objects", o.hash.slice(0, 2), o.hash)));
        const hx = z.find((e) => e.name.endsWith(".hex"));
        if (hx) {
          font.hex = new Map();
          for (const line of hx.data.toString("latin1").split("\n")) {
            const i = line.indexOf(":");
            if (i < 0) continue;
            const cp = parseInt(line.slice(0, i), 16);
            if (cp < 0x3000 || (cp >= 0xfb00 && cp <= 0xffff)) font.hex.set(cp, line.slice(i + 1).trim());
          }
        }
      }
    }
  } catch {}
  return font;
}
function bitmapGlyphs(font, img, rows, cw, chh, sc, ascent) {
  rows.forEach((row, ry) => [...row].forEach((ch, cx) => {
    if (ch === "\u0000" || ch === " " || font.map.has(ch)) return;
    let wid = 0;
    for (let x = cw - 1; x >= 0 && !wid; x--) for (let y = 0; y < chh; y++) if (img.data[((ry * chh + y) * img.w + cx * cw + x) * 4 + 3] > 0) { wid = x + 1; break; }
    const px = [];   // [x, y, w, h] in half text pixels relative to (pen x, line top)
    const top = (7 - ascent) * 2;
    for (let y = 0; y < chh; y++) for (let x = 0; x < wid; x++)
      if (img.data[((ry * chh + y) * img.w + cx * cw + x) * 4 + 3] > 0) px.push([Math.round(x * sc * 2), top + Math.round(y * sc * 2), Math.max(1, Math.round(sc * 2)), Math.max(1, Math.round(sc * 2))]);
    font.map.set(ch, { adv: Math.floor(0.5 + wid * sc) + 1, px, half: 1 });
  }));
}
function glyph(font, ch) {
  let g = font.map.get(ch);
  if (g) return g;
  if (font.space[ch] != null) return { adv: font.space[ch], px: [] };
  const cp = ch.codePointAt(0), hx = font.hex?.get(cp);
  if (hx) {
    const wide = hx.length >= 64, bw = wide ? 16 : 8, px = [];
    let l = bw, r = -1;
    for (let y = 0; y < 16; y++) {
      const bits = parseInt(hx.slice((y * bw) / 4, ((y + 1) * bw) / 4), 16);
      for (let x = 0; x < bw; x++) if (bits & (1 << (bw - 1 - x))) { l = Math.min(l, x); r = Math.max(r, x); }
    }
    if (r >= l) for (let y = 0; y < 16; y++) {
      const bits = parseInt(hx.slice((y * bw) / 4, ((y + 1) * bw) / 4), 16);
      for (let x = l; x <= r; x++) if (bits & (1 << (bw - 1 - x))) px.push([x - l, y, 1, 1]);
    }
    g = { adv: r >= l ? Math.floor((r - l + 1) / 2) + 1 : 4, px, half: 0.5 };
  } else g = { adv: 6, px: [[0, 2, 10, 12]], half: 1 };   // unknown: a block
  font.map.set(ch, g);
  return g;
}
// bidi (simplified Unicode bidi algorithm: strong R/L, European numbers + their separators, neutrals, mirrored
// brackets); paragraph direction = first strong character
const isR = (cp) => (cp >= 0x0590 && cp <= 0x08ff) || (cp >= 0xfb1d && cp <= 0xfdff) || (cp >= 0xfe70 && cp <= 0xfeff);
const MIRROR = { "(": ")", ")": "(", "[": "]", "]": "[", "{": "}", "}": "{", "<": ">", ">": "<", "«": "»", "»": "«" };
function visual(line) {   // line = [{ ch, st }]
  const ty = line.map(({ ch }) => (isR(ch.codePointAt(0)) ? "R" : /\p{Nd}/u.test(ch) ? "EN" : /\p{L}/u.test(ch) ? "L" : /^[,.:/]$/.test(ch) ? "CS" : /^[+\-]$/.test(ch) ? "ES" : /^[#$%°€₪¢£¥+]$/.test(ch) ? "ET" : "N"));
  const first = ty.find((t) => t === "R" || t === "L") || "L";
  const base = first === "R" ? 1 : 0;
  for (let i = 1; i + 1 < ty.length; i++) if ((ty[i] === "CS" || ty[i] === "ES") && ty[i - 1] === "EN" && ty[i + 1] === "EN") ty[i] = "EN";   // W4
  for (let i = 0; i < ty.length; i++) if (ty[i] === "ET") {   // W5: currency/percent next to a number
    let j = i;
    while (j < ty.length && ty[j] === "ET") j++;
    if ((i > 0 && ty[i - 1] === "EN") || ty[j] === "EN") for (let k = i; k < j; k++) ty[k] = "EN";
    i = j - 1;
  }
  let strong = base ? "R" : "L";   // W7: a number after L text is L
  for (let i = 0; i < ty.length; i++) { if (ty[i] === "R" || ty[i] === "L") strong = ty[i]; else if (ty[i] === "EN" && strong === "L") ty[i] = "L"; }
  const dir = (t) => (t === "L" ? "L" : t === "R" || t === "EN" ? "R" : null);
  for (let i = 0; i < ty.length; ) {   // N1/N2: neutrals take the surrounding direction, else the paragraph's
    if (dir(ty[i])) { i++; continue; }
    let j = i;
    while (j < ty.length && !dir(ty[j])) j++;
    const a = i > 0 ? dir(ty[i - 1]) : base ? "R" : "L", b = j < ty.length ? dir(ty[j]) : base ? "R" : "L";
    const t = a === b ? a : base ? "R" : "L";
    for (let k = i; k < j; k++) ty[k] = t === "R" ? "r" : "l";
    i = j;
  }
  const lv = ty.map((t) => (base ? (t === "R" || t === "r" ? 1 : 2) : t === "EN" ? 2 : t === "R" || t === "r" ? 1 : 0));
  const idx = line.map((_, i) => i);
  for (let level = Math.max(0, ...lv); level >= 1; level--) {
    for (let i = 0; i < idx.length; ) {
      if (lv[idx[i]] < level) { i++; continue; }
      let j = i;
      while (j < idx.length && lv[idx[j]] >= level) j++;
      const seg = idx.slice(i, j).reverse();
      for (let k = i; k < j; k++) idx[k] = seg[k - i];
      i = j;
    }
  }
  return idx.map((i) => (lv[i] & 1 && MIRROR[line[i].ch] ? { ...line[i], ch: MIRROR[line[i].ch] } : line[i]));
}
function textCanvas(d) {
  const font = loadFont();
  const runs = flatten(d.text);
  const chars = [];
  for (const r of runs) for (const ch of r.s.replace(/\r/g, "")) chars.push({ ch, st: r });
  const adv = (c) => (c.ch === "\n" ? 0 : glyph(font, c.ch).adv + (c.st.bold ? 1 : 0));
  const maxW = Number(d.line_width) > 0 ? Number(d.line_width) : 200;
  // split: explicit newlines, then word-wrap at line_width (logical order, like StringSplitter)
  const lines = [];
  let cur = [], w = 0, lastSpace = -1;
  for (const c of chars) {
    if (c.ch === "\n") { lines.push(cur); cur = []; w = 0; lastSpace = -1; continue; }
    const a = adv(c);
    if (w + a > maxW && cur.length) {
      if (lastSpace > 0) { const rest = cur.slice(lastSpace + 1); lines.push(cur.slice(0, lastSpace)); cur = rest; }
      else { lines.push(cur); cur = []; }
      w = cur.reduce((s, x) => s + adv(x), 0); lastSpace = -1;
      cur.forEach((x, i) => { if (x.ch === " ") lastSpace = i; });
    }
    if (c.ch === " ") lastSpace = cur.length;
    cur.push(c); w += a;
  }
  lines.push(cur);
  const widths = lines.map((l) => l.reduce((s, x) => s + adv(x), 0));
  const k = Math.max(0, ...widths), L = lines.length * 10;
  // canvas in half text pixels: text x −1..k, y −1..L
  const W = (k + 1) * 2, H = (L + 1) * 2, data = new Uint8Array(W * H * 4);
  let bg = d.default_background && truthy(d.default_background) ? 0x40000000 : d.background == null ? 0x40000000 : Number(d.background);
  bg >>>= 0;
  const ba = bg >>> 24;
  for (let i = 0; i < W * H; i++) { data[i * 4] = (bg >> 16) & 255; data[i * 4 + 1] = (bg >> 8) & 255; data[i * 4 + 2] = bg & 255; data[i * 4 + 3] = ba; }
  let op = d.text_opacity == null ? 255 : Number(d.text_opacity) & 255;
  if (op < 26) op = 255;   // MC treats tiny opacities as opaque-ish; keep text visible
  const shadow = d.shadow != null && truthy(d.shadow);
  const align = String(d.alignment || "center");
  const plot = (x, y, w, h, rgb, a) => {
    for (let yy = Math.max(0, y); yy < Math.min(H, y + h); yy++) for (let xx = Math.max(0, x); xx < Math.min(W, x + w); xx++) {
      const o = (yy * W + xx) * 4, A = a / 255, B = data[o + 3] / 255, oa = A + B * (1 - A);
      if (oa <= 0) continue;
      for (let c = 0; c < 3; c++) data[o + c] = Math.round((rgb[c] * A + data[o + c] * B * (1 - A)) / oa);
      data[o + 3] = Math.round(oa * 255);
    }
  };
  lines.forEach((ln, li) => {
    const lw = widths[li];
    let x = align === "left" ? 0 : align === "right" ? k - lw : k / 2 - lw / 2;
    const y = li * 10;
    for (const c of visual(ln)) {
      const g = glyph(font, c.ch), col = c.st.color ?? 0xffffff, rgb = [(col >> 16) & 255, (col >> 8) & 255, col & 255];
      const ox = Math.round((x + 1) * 2), oy = (y + 1) * 2, so = Math.round((g.half ?? 1) * 2);
      const passes = [];
      if (shadow) passes.push([so, so, rgb.map((v) => Math.floor(v / 4))]);
      passes.push([0, 0, rgb]);
      for (const [dx, dy, cc] of passes) for (const [gx, gy, gw, gh] of g.px) {
        plot(ox + dx + gx, oy + dy + gy, gw, gh, cc, op);
        if (c.st.bold) plot(ox + dx + gx + so, oy + dy + gy, gw, gh, cc, op);
      }
      x += adv(c);
    }
  });
  return { tex: finishTex({ w: W, h: H, fh: H, data }), k, L };
}
function textLocal(e) {
  const d = e.display;
  const key = "t|" + JSON.stringify([d.text, d.line_width, d.background, d.default_background, d.text_opacity, d.shadow, d.alignment]);
  if (C.quads.has(key)) return C.quads.get(key);
  const { tex, k, L } = textCanvas(d);
  const s = 0.025, x0 = (-k / 2) * s, x1 = (k / 2 + 1) * s, y0 = 0, y1 = (L + 1) * s;
  // text pixel (tx, ty) → local ((tx + 1 − k/2)·0.025, (L − ty)·0.025, 0); readable from +z
  const q = [{ v: [x0, y1, 0, x0, y0, 0, x1, y0, 0, x1, y1, 0], uv: [0, 0, 0, 1, 1, 1, 1, 0], tex, tint: null, flat: true }];
  if (C.quads.size > 4000) C.quads.clear();
  C.quads.set(key, q);
  return q;
}

// ───────────── entities → world-space quad groups ─────────────
const L0 = (() => { const v = [0.2, 1, -0.7], n = Math.hypot(...v); return v.map((x) => x / n); })();
const L1 = (() => { const v = [-0.2, 1, 0.7], n = Math.hypot(...v); return v.map((x) => x / n); })();
const lightOf = (n) => Math.min(1, 0.4 + 0.6 * (Math.max(0, n[0] * L0[0] + n[1] * L0[1] + n[2] * L0[2]) + Math.max(0, n[0] * L1[0] + n[1] * L1[1] + n[2] * L1[2])));
function orientation(e, cam) {
  const d = e.display, bb = String(d.billboard || "fixed");
  const yaw = Number(e.yaw) || 0, pitch = Number(e.pitch) || 0, cy = cam.camYaw ?? 0, cp = cam.camPitch ?? 0;
  const Y = bb === "vertical" || bb === "center" ? cy - 180 : yaw, X = bb === "horizontal" || bb === "center" ? -cp : pitch;
  return mul(RY(-Y * DEG), RX(X * DEG));
}
/**
 * entities (from lib/world.js entitiesIn: { type, pos, yaw, pitch, display: {...} }) → { groups, rest, stats }.
 * opts: { camYaw, camPitch (billboards face this camera), packs (zip paths, first wins), jar, version (client jar,
 * see the header), colorOf(name) → [r,g,b] }
 */
export function buildGroups(entities, opts = {}) {
  const groups = [], rest = [];
  const disp = (entities || []).filter((e) => e && e.display && /_display$/.test(e.type));
  if (!disp.length) return { groups, rest: entities || [], stats: { display: 0 } };
  const have = setup(opts.packs, opts.jar, opts.version);
  let handled = 0;
  for (const e of entities) {
    if (!e || !e.display || !/_display$/.test(e.type)) { rest.push(e); continue; }
    let local = null, kind = e.type;
    try {
      local = kind === "item_display" ? itemLocal(e, opts.colorOf) : kind === "block_display" ? blockLocal(e, opts.colorOf) : textLocal(e);
    } catch { local = null; }
    if (!local) { if (kind !== "item_display" || (e.display.model || e.display.item)) rest.push(e); continue; }   // empty item_display = invisible
    const M = mul(mul(T3(e.pos[0], e.pos[1], e.pos[2]), orientation(e, opts)), tfMatrix(e.display.transformation));
    const quads = [];
    let cx = 0, cy = 0, cz = 0;
    for (const q of local) {
      const v = new Float64Array(12);
      for (let i = 0; i < 4; i++) { const p = ap(M, q.v[i * 3], q.v[i * 3 + 1], q.v[i * 3 + 2]); v[i * 3] = p[0]; v[i * 3 + 1] = p[1]; v[i * 3 + 2] = p[2]; }
      const ax = v[3] - v[0], ay = v[4] - v[1], az = v[5] - v[2], bx = v[6] - v[0], by = v[7] - v[1], bz = v[8] - v[2];
      let n = [ay * bz - az * by, az * bx - ax * bz, ax * by - ay * bx];
      let nl = Math.hypot(n[0], n[1], n[2]);
      if (nl < 1e-12) {   // degenerate first triangle: try the other one
        const cx2 = v[9] - v[0], cy2 = v[10] - v[1], cz2 = v[11] - v[2];
        n = [by * cz2 - bz * cy2, bz * cx2 - bx * cz2, bx * cy2 - by * cx2]; nl = Math.hypot(n[0], n[1], n[2]);
        if (nl < 1e-12) continue;
      }
      n = n.map((x) => x / nl);
      const shade = q.flat ? 1 : lightOf(n);
      quads.push({ v, uv: q.uv, tex: q.tex, tint: q.tint, n, shade });
      cx += v[0] + v[3] + v[6] + v[9]; cy += v[1] + v[4] + v[7] + v[10]; cz += v[2] + v[5] + v[8] + v[11];
    }
    if (!quads.length) continue;
    const c = [cx / (quads.length * 4), cy / (quads.length * 4), cz / (quads.length * 4)];
    let r = 0;
    for (const q of quads) for (let i = 0; i < 4; i++) r = Math.max(r, Math.hypot(q.v[i * 3] - c[0], q.v[i * 3 + 1] - c[1], q.v[i * 3 + 2] - c[2]));
    groups.push({ c, r, quads, type: kind });
    handled++;
  }
  return { groups, rest, stats: { display: disp.length, drawn: handled, packs: have.packs, jar: have.jar } };
}

// ───────────── rasteriser ─────────────
/**
 * target: { W, H, rgb (Buffer, 3 B/px), z (Float32Array, smaller = nearer), post?(i, px, py, z, c) → c (fog / glass tint) }
 * cam (perspective): { persp: true, eye, fwd, right, up, tanF, aspect, near, maxD }
 * cam (orthographic): { persp: false, project(x, y, z) → [sx, sy, depth], toCam: [x, y, z] (world direction to the camera), scale (px per block) }
 */
export function rasterGroups(groups, T, cam) {
  const deferred = [];
  let drawn = 0;
  for (const g of groups) {
    if (!sphereVisible(g, T, cam)) continue;
    for (const q of g.quads) if (drawQuad(q, T, cam, 0, deferred)) drawn++;
  }
  deferred.sort((a, b) => b.d - a.d);
  for (const t of deferred) drawQuad(t.q, T, cam, 1, null, t.P);
  return drawn;
}
function sphereVisible(g, T, cam) {
  if (cam.persp) {
    const dx = g.c[0] - cam.eye[0], dy = g.c[1] - cam.eye[1], dz = g.c[2] - cam.eye[2];
    const z = dx * cam.fwd[0] + dy * cam.fwd[1] + dz * cam.fwd[2];
    if (z < -g.r || z - g.r > cam.maxD) return false;
    const x = dx * cam.right[0] + dy * cam.right[1] + dz * cam.right[2], y = dx * cam.up[0] + dy * cam.up[1] + dz * cam.up[2];
    const tx = cam.tanF * cam.aspect, ty = cam.tanF;
    if (Math.abs(x) - g.r * Math.hypot(1, tx) > z * tx) return false;
    if (Math.abs(y) - g.r * Math.hypot(1, ty) > z * ty) return false;
    return true;
  }
  const p = cam.project(g.c[0], g.c[1], g.c[2]), m = g.r * (cam.scale || 1) * 2 + 2;
  return p[0] > -m && p[1] > -m && p[0] < T.W + m && p[1] < T.H + m;
}
function drawQuad(q, T, cam, pass, deferred, Pin) {
  let P = Pin;
  if (!P) {
    const v = q.v, n = q.n;
    if (cam.persp) {
      if ((cam.eye[0] - v[0]) * n[0] + (cam.eye[1] - v[1]) * n[1] + (cam.eye[2] - v[2]) * n[2] <= 0) return false;   // back face
      let poly = [];
      for (let i = 0; i < 4; i++) {
        const dx = v[i * 3] - cam.eye[0], dy = v[i * 3 + 1] - cam.eye[1], dz = v[i * 3 + 2] - cam.eye[2];
        poly.push([dx * cam.right[0] + dy * cam.right[1] + dz * cam.right[2], dx * cam.up[0] + dy * cam.up[1] + dz * cam.up[2], dx * cam.fwd[0] + dy * cam.fwd[1] + dz * cam.fwd[2], q.uv[i * 2], q.uv[i * 2 + 1]]);
      }
      const near = cam.near || 0.05;
      if (poly.every((p) => p[2] < near)) return false;
      if (poly.every((p) => p[2] > cam.maxD)) return false;
      if (poly.some((p) => p[2] < near)) poly = clipNear(poly, near);
      if (poly.length < 3) return false;
      const sx = cam.W / 2 / (cam.tanF * cam.aspect), sy = cam.H / 2 / cam.tanF;
      P = poly.map(([x, y, z, u, w]) => [cam.W / 2 + (x / z) * sx, cam.H / 2 - (y / z) * sy, z, 1 / z, u, w]);
    } else {
      if (n[0] * cam.toCam[0] + n[1] * cam.toCam[1] + n[2] * cam.toCam[2] <= 0) return false;
      P = [];
      for (let i = 0; i < 4; i++) { const p = cam.project(v[i * 3], v[i * 3 + 1], v[i * 3 + 2]); P.push([p[0], p[1], p[2], 1, q.uv[i * 2], q.uv[i * 2 + 1]]); }
    }
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    for (const p of P) { x0 = Math.min(x0, p[0]); x1 = Math.max(x1, p[0]); y0 = Math.min(y0, p[1]); y1 = Math.max(y1, p[1]); }
    if (x1 < 0 || y1 < 0 || x0 >= T.W || y0 >= T.H) return false;
    // mip level from texels per screen pixel
    let sa = 0, ta = 0;
    for (let i = 0; i < P.length; i++) { const a = P[i], b = P[(i + 1) % P.length]; sa += a[0] * b[1] - b[0] * a[1]; ta += a[4] * b[5] - b[4] * a[5]; }
    const tex = q.tex, ratio = Math.sqrt((Math.abs(ta) / 2 * tex.w * tex.fh) / Math.max(1e-6, Math.abs(sa) / 2));
    P.level = ratio > 1.4 ? Math.min(12, Math.floor(Math.log2(ratio))) : 0;
    if (tex.translucent && deferred) { let d = 0; for (const p of P) d += p[2]; deferred.push({ q, P, d: d / P.length }); }
  }
  const tx = P.level ? mipOf(q.tex, P.level) : q.tex;
  for (let i = 1; i + 1 < P.length; i++) tri(P[0], P[i], P[i + 1], q, tx, T, cam.persp, pass);
  return true;
}
function clipNear(poly, near) {
  const out = [];
  for (let i = 0; i < poly.length; i++) {
    const a = poly[i], b = poly[(i + 1) % poly.length], ain = a[2] >= near, bin = b[2] >= near;
    if (ain) out.push(a);
    if (ain !== bin) { const t = (near - a[2]) / (b[2] - a[2]); out.push(a.map((v, k) => v + (b[k] - v) * t)); }
  }
  return out;
}
function tri(A, B, Cc, q, tx, T, persp, pass) {
  const W = T.W, H = T.H;
  const minX = Math.max(0, Math.floor(Math.min(A[0], B[0], Cc[0]))), maxX = Math.min(W - 1, Math.ceil(Math.max(A[0], B[0], Cc[0])));
  const minY = Math.max(0, Math.floor(Math.min(A[1], B[1], Cc[1]))), maxY = Math.min(H - 1, Math.ceil(Math.max(A[1], B[1], Cc[1])));
  if (minX > maxX || minY > maxY) return;
  const area = (B[0] - A[0]) * (Cc[1] - A[1]) - (B[1] - A[1]) * (Cc[0] - A[0]);
  if (Math.abs(area) < 1e-9) return;
  const ia = 1 / area;
  // attributes interpolated linearly in screen space: w (= 1/z or 1), u·w, v·w, and depth (ortho)
  const aw = A[3], bw = B[3], cw = Cc[3];
  const au = A[4] * aw, bu = B[4] * bw, cu = Cc[4] * cw, av = A[5] * aw, bv = B[5] * bw, cv = Cc[5] * cw;
  const tw = tx.w, th = tx.fh, data = tx.data, tint = q.tint, sh = q.shade;
  const tr = tint ? (tint[0] / 255) * sh : sh, tg = tint ? (tint[1] / 255) * sh : sh, tb = tint ? (tint[2] / 255) * sh : sh;
  const zb = T.z, rgb = T.rgb, post = T.post, col = [0, 0, 0];
  for (let py = minY; py <= maxY; py++) {
    const y = py + 0.5;
    for (let px = minX; px <= maxX; px++) {
      const x = px + 0.5;
      const w0 = ((B[0] - x) * (Cc[1] - y) - (B[1] - y) * (Cc[0] - x)) * ia;
      const w1 = ((Cc[0] - x) * (A[1] - y) - (Cc[1] - y) * (A[0] - x)) * ia;
      const w2 = 1 - w0 - w1;
      if (w0 < -1e-7 || w1 < -1e-7 || w2 < -1e-7) continue;
      const iw = w0 * aw + w1 * bw + w2 * cw;
      const z = persp ? 1 / iw : w0 * A[2] + w1 * B[2] + w2 * Cc[2];
      const idx = py * W + px;
      if (!(z < zb[idx])) continue;
      const u = (w0 * au + w1 * bu + w2 * cu) / iw, v = (w0 * av + w1 * bv + w2 * cv) / iw;
      let ix = Math.floor(u * tw), iy = Math.floor(v * th);
      if (ix < 0) ix = 0; else if (ix >= tw) ix = tw - 1;
      if (iy < 0) iy = 0; else if (iy >= th) iy = th - 1;
      const k = (iy * tw + ix) * 4, a = data[k + 3];
      if (a < 4) continue;
      const opaque = a >= 250;
      if (pass === 0 ? !opaque : opaque) continue;
      col[0] = data[k] * tr; col[1] = data[k + 1] * tg; col[2] = data[k + 2] * tb;
      if (post) post(idx, px, py, z, col);
      const o = idx * 3;
      if (opaque) { rgb[o] = col[0]; rgb[o + 1] = col[1]; rgb[o + 2] = col[2]; zb[idx] = z; }
      else { const al = a / 255; rgb[o] = rgb[o] * (1 - al) + col[0] * al; rgb[o + 1] = rgb[o + 1] * (1 - al) + col[1] * al; rgb[o + 2] = rgb[o + 2] * (1 - al) + col[2] * al; }
    }
  }
}

/** cache / source info (for tool replies) */
export function info() {
  return { jar: C.jarPath || null, zips: [...C.zips.keys()], textures: C.tex.size, mb: Math.round(C.texBytes / 1e6) };
}
