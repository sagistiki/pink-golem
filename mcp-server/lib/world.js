/**
 * world — read the world as a voxel grid (one scarpet call per ~120k blocks), tell natural terrain from builds,
 * find the structure around a block and describe it as text (top view + elevations), list entities for pictures.
 */
import fs from "node:fs";
import path from "node:path";

const AIR = new Set(["air", "cave_air", "void_air", "light"]);
// natural terrain never counts as "somebody's build" (you may build on it / replace it)
const TERRAIN = new Set(["grass_block", "dirt", "coarse_dirt", "podzol", "rooted_dirt", "mud", "mycelium", "sand", "red_sand", "gravel", "clay",
  "stone", "deepslate", "granite", "diorite", "andesite", "tuff", "calcite", "dripstone_block", "bedrock", "snow", "snow_block", "powder_snow", "ice", "packed_ice",
  "water", "lava", "sandstone", "red_sandstone", "terracotta", "netherrack", "end_stone", "moss_block", "moss_carpet", "pale_moss_block", "pale_moss_carpet"]);
const PLANTS = /^(short_grass|tall_grass|fern|large_fern|dead_bush|bush|short_dry_grass|tall_dry_grass|leaf_litter|wildflowers|pink_petals|firefly_bush|dandelion|poppy|blue_orchid|allium|azure_bluet|red_tulip|orange_tulip|white_tulip|pink_tulip|oxeye_daisy|cornflower|lily_of_the_valley|sunflower|lilac|rose_bush|peony|sweet_berry_bush|seagrass|tall_seagrass|kelp|kelp_plant|sugar_cane|vine|glow_lichen|brown_mushroom|red_mushroom|lily_pad)$/;
const TREE = /(_log|_leaves|_wood)$/;
const CS = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ!#$%&*+-/<=>?@^~";

export function install(K) {
  K.AIR = AIR;
  /** true for blocks that belong to a build (not air, not natural ground, not wild plants). Trees count as natural in normal worlds. */
  K.isSolid = (n, y) => {
    if (!n || AIR.has(n) || PLANTS.test(n)) return false;
    if (K.isFlat) return !(TERRAIN.has(n) && y <= K.flatGroundY);
    return !TERRAIN.has(n) && !TREE.test(n);
  };

  /** Read every block in a box (≤ ~120k blocks) in one scarpet call. */
  K.dumpRegion = async (lo, hi) => {
    const [x1, y1, z1] = lo, [x2, y2, z2] = hi;
    const vol = (x2 - x1 + 1) * (y2 - y1 + 1) * (z2 - z1 + 1);
    if (vol > 120000) throw new Error(`Region too big to scan (${vol} blocks, max 120000)`);
    const expr =
      `cs='${CS}';pal={};pl=[];s=[];` +
      `for(range(${y1},${y2 + 1}),y=_;for(range(${z1},${z2 + 1}),z=_;for(range(${x1},${x2 + 1}),` +
      `b=str(block(_,y,z));if(!has(pal,b),pal:b=min(length(pl),77);if(length(pl)<78,pl+=b));s+=slice(cs,pal:b,pal:b+1))));` +
      `join(',',pl)+'|'+join('',s)`;
    const r = await K.scarpet(expr);
    const v = r.value.replace(/^'|'$/g, "");
    const bar = v.indexOf("|");
    if (bar < 0) throw new Error(`scan failed: ${r.raw.slice(0, 300)}`);
    const pal = v.slice(0, bar).split(",");
    const data = v.slice(bar + 1);
    const W = x2 - x1 + 1, D = z2 - z1 + 1;
    if (data.length !== vol) throw new Error(`scan returned ${data.length} of ${vol} blocks (output truncated?) — scan a smaller area`);
    const at = (x, y, z) => {
      if (x < x1 || x > x2 || y < y1 || y > y2 || z < z1 || z > z2) return null;
      return pal[CS.indexOf(data[(y - y1) * W * D + (z - z1) * W + (x - x1)])];
    };
    return { lo, hi, pal, at };
  };

  const MAX_MULTI = 700000;
  K.MAX_MULTI = MAX_MULTI;
  /** Read a box bigger than one scan: slabs of ≤110k blocks, composed into one region. */
  K.multiRegion = async (lo, hi) => {
    if (K.volOf([lo, hi]) > MAX_MULTI) throw new Error(`area ${K.volOf([lo, hi])} blocks is too big (max ${MAX_MULTI})`);
    const parts = [];
    for (const [l, h] of K.WM.splitBox(lo, hi, 110000)) parts.push(await K.dumpRegion(l, h));
    return K.WM.composeRegions(parts, lo, hi);
  };

  /** Build blocks (see isSolid) inside a box → [[x,y,z,name]...] */
  K.occupiedIn = async (lo, hi) => {
    const R = await K.dumpRegion(lo, hi);
    const out = [];
    for (let y = lo[1]; y <= hi[1]; y++) for (let z = lo[2]; z <= hi[2]; z++) for (let x = lo[0]; x <= hi[0]; x++) {
      const n = R.at(x, y, z);
      if (K.isSolid(n, y)) out.push([x, y, z, n]);
    }
    return out;
  };

  /** Y of the first free cell above the surface at x,z (where a player would stand). */
  K.groundAt = async (x, z, fallback) => {
    if (K.isFlat) return K.flatGroundY + 1;
    const r = await K.inApp("cu", `ytop(${Math.floor(x)},${Math.floor(z)})`).catch(() => "");
    const m = /=\s*(-?\d+)/.exec(r);
    return m ? +m[1] + 1 : fallback;
  };

  /** Entities for pictures (no items/xp/fireworks), with what display entities SHOW (transformation, item model, dye,
   *  block state, text, background, billboard…; one NBT read each) so render.js can draw them textured. The cu app
   *  writes the list to cu.data/shot_<id>.json (a big frame overflows an RCON reply); without cu → positions only. */
  const nul = (v) => (v === "null" || v === undefined ? null : v);
  const dyeOf = (v) => { v = nul(v); if (v == null) return null; if (typeof v === "number") return v; const m = /rgb:\s*(-?\d+)/.exec(String(v)); return m ? +m[1] : null; };
  K.entitiesIn = async (lo, hi) => {
    const c = [0, 1, 2].map((i) => (lo[i] + hi[i] + 1) / 2), h = [0, 1, 2].map((i) => (hi[i] - lo[i] + 1) / 2);
    const id = `shot_${process.pid}_${Date.now().toString(36)}`, f = path.join(K.P.CU_DATA, id + ".json");
    try {
      const out = await K.inApp("cu", `l=[];for(entity_area('*',[${c.join(",")}],[${h.join(",")}]),t=query(_,'type');if(t!='item'&&t!='experience_orb'&&t!='firework_rocket',p=pos(_);` +
        `r=[t,p:0,p:1,p:2,query(_,'yaw'),query(_,'pitch')];if(t=='mannequin',r+=query(_,'nbt','pose'),t~'_display',n=query(_,'nbt');r+=[parse_nbt(n:'transformation'),` +
        `n:'item.components."minecraft:item_model"',n:'item.components."minecraft:dyed_color"',n:'item.id',n:'item_display',parse_nbt(n:'block_state'),parse_nbt(n:'text'),` +
        `n:'background',n:'billboard',n:'line_width',n:'alignment',n:'text_opacity',n:'default_background',n:'shadow']);l+=r));write_file('${id}','json',l);length(l)`);
      if (/^\s*=\s*\d+/.test(out) && fs.existsSync(f)) {
        return JSON.parse(fs.readFileSync(f, "utf8")).map(([type, x, y, z, yaw, pitch, ex]) => {
          const e = { type, pos: [x, y, z], yaw, pitch, pose: typeof ex === "string" ? ex.replace(/"/g, "") : "" };
          if (Array.isArray(ex) && /_display$/.test(type)) {
            const [tf, model, dye, item, ctx, block, txt, bg, billboard, lw, align, op, dbg, shadow] = ex;
            e.display = { transformation: nul(tf), model: nul(model), dye: dyeOf(dye), item: nul(item), item_display: nul(ctx), block: nul(block), text: nul(txt),
              background: nul(bg), billboard: nul(billboard), line_width: nul(lw), alignment: nul(align), text_opacity: nul(op), default_background: nul(dbg), shadow: nul(shadow) };
          }
          return e;
        });
      }
    } catch (e) { K.log("entitiesIn (cu):", e.message); }
    finally { try { fs.unlinkSync(f); } catch {} }
    const r = await K.scarpet(`l=[];for(entity_area('*',[${c.join(",")}],[${h.join(",")}]),t=query(_,'type');if(t!='item'&&t!='experience_orb'&&t!='firework_rocket',` +
      `p=pos(_);l+=str('%s,%.1f,%.1f,%.1f,%s',t,p:0,p:1,p:2,if(t=='mannequin',query(_,'nbt','pose'),''))));join(';',slice(l,0,min(length(l),400)))`);
    const v = r.value.replace(/^'|'$/g, "");
    if (!v || /Error/.test(r.raw)) return [];
    return v.split(";").filter(Boolean).map((q) => { const [type, x, y, z, pose] = q.split(","); return { type, pos: [+x, +y, +z], pose: (pose || "").replace(/"/g, "") }; });
  };

  /** Flood-fill the structure connected (26-neighbourhood) to a seed block. */
  K.floodStructure = (R, seed, limit = 60000) => {
    const key = (x, y, z) => `${x},${y},${z}`;
    const seen = new Set([key(...seed)]);
    const cells = [];
    const q = [seed];
    let touches = false;
    for (let i = 0; i < q.length && cells.length < limit; i++) {
      const [x, y, z] = q[i];
      cells.push([x, y, z]);
      for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) for (let dz = -1; dz <= 1; dz++) {
        if (!dx && !dy && !dz) continue;
        const nx = x + dx, ny = y + dy, nz = z + dz;
        const k = key(nx, ny, nz);
        if (seen.has(k)) continue;
        seen.add(k);
        const n = R.at(nx, ny, nz);
        if (n === null) { touches = true; continue; }
        if (K.isSolid(n, ny)) q.push([nx, ny, nz]);
      }
    }
    return { cells, touches, truncated: cells.length >= limit };
  };

  const FEATURES = [
    ["doors", /_door$/], ["trapdoors", /_trapdoor$/], ["windows (glass)", /glass/], ["lights", /lantern|torch|lamp|glowstone|sea_lantern|end_rod|campfire|froglight|shroomlight|candle|beacon|brazier/],
    ["beds", /_bed$/], ["stairs", /_stairs$/], ["slabs", /_slab$/], ["fences/walls", /_fence$|_wall$|_fence_gate$|iron_bars/],
    ["interactive", /button|lever|pressure_plate|chest|barrel|crafting_table|furnace|jukebox|note_block|shulker/],
    ["plants", /flower|tulip|poppy|dandelion|allium|orchid|daisy|bluet|lily|azalea|leaves|sapling|fern|bush|vine/],
    ["water/lava", /^water$|^lava$/],
  ];

  /** Text picture of a structure: size, features, legend, top view, elevations, optional layers. */
  K.renderStructure = (R, cells, opts) => {
    const lo = [Infinity, Infinity, Infinity], hi = [-Infinity, -Infinity, -Infinity];
    const set = new Map();
    for (const [x, y, z] of cells) {
      set.set(`${x},${y},${z}`, R.at(x, y, z));
      for (let i = 0; i < 3; i++) { lo[i] = Math.min(lo[i], [x, y, z][i]); hi[i] = Math.max(hi[i], [x, y, z][i]); }
    }
    const counts = {};
    for (const n of set.values()) counts[n] = (counts[n] || 0) + 1;
    const ranked = Object.entries(counts).sort((a, b) => b[1] - a[1]);
    const LET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
    const ch = {};
    ranked.forEach(([n], i) => (ch[n] = LET[i] || "?"));
    const g = (x, y, z) => set.get(`${x},${y},${z}`);
    const W = hi[0] - lo[0] + 1, H = hi[1] - lo[1] + 1, D = hi[2] - lo[2] + 1;
    const out = [];
    out.push(`STRUCTURE ${W}(x) × ${H}(y) × ${D}(z) = ${cells.length} blocks · box [${lo.join(" ")}] → [${hi.join(" ")}]`);
    out.push(`Orientation: north = −Z, east = +X. Map rows run north→south, columns west→east.`);
    const feats = FEATURES.map(([label, re]) => {
      const hits = ranked.filter(([n]) => re.test(n));
      const total = hits.reduce((a, [, c]) => a + c, 0);
      return total ? `${label}: ${total} (${hits.slice(0, 4).map(([n, c]) => `${n}×${c}`).join(", ")})` : null;
    }).filter(Boolean);
    if (feats.length) out.push("Features: " + feats.join(" | "));
    out.push("Legend: " + ranked.slice(0, 40).map(([n, c]) => `${ch[n]}=${n}(${c})`).join("  ") + (ranked.length > 40 ? `  … +${ranked.length - 40} more (shown as ?)` : ""));
    const views = opts.views || ["top", "south", "east"];
    const colHdr = (from, len) => "     " + Array.from({ length: len }, (_, i) => String(Math.abs(from + i) % 10)).join("");
    if (views.includes("top")) {
      out.push(`\nTOP VIEW (highest block per column; x ${lo[0]}..${hi[0]}, z ${lo[2]}..${hi[2]})`);
      out.push(colHdr(lo[0], W));
      for (let z = lo[2]; z <= hi[2]; z++) {
        let row = "";
        for (let x = lo[0]; x <= hi[0]; x++) {
          let c = ".";
          for (let y = hi[1]; y >= lo[1]; y--) { const n = g(x, y, z); if (n) { c = ch[n]; break; } }
          row += c;
        }
        out.push(String(z).padStart(4) + " " + row);
      }
    }
    const elev = (label, cols, pick) => {
      out.push(`\n${label}`);
      for (let y = hi[1]; y >= lo[1]; y--) {
        let row = "";
        for (const c of cols) row += pick(c, y);
        out.push(String(y).padStart(4) + " " + row);
      }
    };
    const xs = Array.from({ length: W }, (_, i) => lo[0] + i), zs = Array.from({ length: D }, (_, i) => lo[2] + i);
    const firstAlong = (x, y, zOrder) => { for (const z of zOrder) { const n = g(x, y, z); if (n) return ch[n]; } return "."; };
    const firstAlongX = (z, y, xOrder) => { for (const x of xOrder) { const n = g(x, y, z); if (n) return ch[n]; } return "."; };
    if (views.includes("south")) elev(`FROM THE SOUTH (looking north; columns = x ${lo[0]}→${hi[0]}, west on the left)`, xs, (x, y) => firstAlong(x, y, [...zs].reverse()));
    if (views.includes("north")) elev(`FROM THE NORTH (looking south; columns = x ${hi[0]}→${lo[0]}, east on the left)`, [...xs].reverse(), (x, y) => firstAlong(x, y, zs));
    if (views.includes("east")) elev(`FROM THE EAST (looking west; columns = z ${hi[2]}→${lo[2]}, south on the left)`, [...zs].reverse(), (z, y) => firstAlongX(z, y, [...xs].reverse()));
    if (views.includes("west")) elev(`FROM THE WEST (looking east; columns = z ${lo[2]}→${hi[2]}, north on the left)`, zs, (z, y) => firstAlongX(z, y, xs));
    if (views.includes("layers")) {
      const yFrom = opts.layer_from ?? lo[1], yTo = opts.layer_to ?? hi[1];
      for (let y = Math.max(lo[1], yFrom); y <= Math.min(hi[1], yTo); y++) {
        out.push(`\nLAYER y=${y}  ('.' = air/empty, '+' = other blocks not part of this structure)`);
        out.push(colHdr(lo[0], W));
        for (let z = lo[2]; z <= hi[2]; z++) {
          let row = "";
          for (let x = lo[0]; x <= hi[0]; x++) {
            const n = g(x, y, z);
            if (n) row += ch[n];
            else { const o = R.at(x, y, z); row += K.isSolid(o, y) ? "+" : "."; }
          }
          out.push(String(z).padStart(4) + " " + row);
        }
      }
    }
    return { text: out.join("\n"), lo, hi };
  };
}
