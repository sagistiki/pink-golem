/** Knowing an area cheaply: minecraft_survey (everything in one call) and minecraft_section (text slices / top map). */

const vec = { type: "array", items: { type: "number" }, minItems: 3, maxItems: 3, description: "[x, y, z]" };
const area = {
  from: vec, to: vec, build: { type: "string", description: "a build on the world map (its box + margin)" }, margin: { type: "number" },
  pos: vec, player: { type: "string" }, radius: { type: "number", description: "around pos/player, max 60" }, height: { type: "number", description: "blocks above the centre" },
};
const ROADS = new Set(["black_terracotta"]);          // the surface city.py road() lays; add yours

export const tools = [
  {
    name: "minecraft_survey",
    description: "ONE call to know an area before building in it or connecting to it: box size, players inside, world-map builds and protected zones there and nearby, ground (natural surface %, surface levels and blocks, water/lava), built blocks by type, rails (straight runs, curves/slopes, boosters, unpowered powered rails), containers with item counts, entities (counts + named/tagged — only in LOADED chunks), and the NEAREST road surface and rail to the point. Area: from/to, build, or pos/player + radius (default 16, max 60) and height. Max 480k blocks.",
    inputSchema: { type: "object", properties: area },
  },
  {
    name: "minecraft_section",
    description: "A cheap text picture (no screenshot): top:true = top-down map of the highest block of every column (+ heights:true = a height map); or axis x|y|z + at (a coordinate, or up to 4) = a slice: y = floor plan, x/z = vertical cross-section — the best quick check for arches, barrels, stairs, floor levels, 'is the door really in the wall'. Letters by frequency with a legend; '.' air, ',' natural ground, '~' water. Area like minecraft_survey. Max 160 wide.",
    inputSchema: { type: "object", properties: { ...area, top: { type: "boolean" }, heights: { type: "boolean" }, axis: { type: "string", enum: ["x", "y", "z"] }, at: { description: "coordinate, or an array of up to 4" } } },
  },
];

export function handlers(K) {
  const natural = (n, y) => !!n && !K.AIR.has(n) && !K.isSolid(n, y);

  function summarizeRails(rails) {
    if (!rails.length) return "none";
    const key = new Map(rails.map((r) => [`${r[0]},${r[1]},${r[2]}`, r]));
    const used = new Set(), runs = [], special = [];
    for (const r of rails) {
      const k = `${r[0]},${r[1]},${r[2]}`;
      if (used.has(k)) continue;
      const ax = r[4] === "east_west" ? 0 : r[4] === "north_south" ? 2 : -1;
      if (ax < 0) { special.push(`${r[4]}${r[3] !== "rail" ? " (" + r[3] + (String(r[5]) === "false" ? ", OFF" : "") + ")" : ""} ${k}`); used.add(k); continue; }
      const at = (v) => { const p = [r[0], r[1], r[2]]; p[ax] = v; return key.get(p.join(",")); };
      let a = r[ax], b = r[ax];
      while (at(a - 1)?.[4] === r[4]) a--;
      while (at(b + 1)?.[4] === r[4]) b++;
      let boost = 0, off = 0;
      for (let v = a; v <= b; v++) { const q = at(v); used.add(`${q[0]},${q[1]},${q[2]}`); if (q[3] === "powered_rail") String(q[5]) === "true" ? boost++ : off++; }
      const tail = `(${b - a + 1}${boost ? `, ${boost} boosters` : ""}${off ? `, ${off} unpowered` : ""})`;
      runs.push(ax === 0 ? `east_west z ${r[2]} y ${r[1]}: x ${a}..${b} ${tail}` : `north_south x ${r[0]} y ${r[1]}: z ${a}..${b} ${tail}`);
    }
    return { count: rails.length, straight_runs: runs.slice(0, 30), curves_slopes: special.slice(0, 30), ...(runs.length > 30 || special.length > 30 ? { note: "truncated — survey a smaller box or use minecraft_rails trace" } : {}) };
  }

  const LET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789@#$%&*+=?!";
  const legendFor = (cells) => {
    const c = {};
    for (const [n, y] of cells) if (n && !K.AIR.has(n) && !natural(n, y) && n !== "water") c[n] = (c[n] || 0) + 1;
    const ranked = Object.entries(c).sort((a, b) => b[1] - a[1]);
    const ch = {};
    ranked.forEach(([n], i) => (ch[n] = LET[i] || "?"));
    return { ch, legend: ranked.map(([n, k]) => `${ch[n]}=${n}(${k})`).join(" ") };
  };
  const glyph = (n, y, ch) => (!n || K.AIR.has(n) ? "." : n === "water" ? "~" : natural(n, y) ? "," : ch[n]);
  const ruler = (start, n) => {
    let s = "";
    for (let i = 0; i < n; i++) { const v = start + i; s += v % 10 === 0 ? "|" : v % 5 === 0 ? "+" : "-"; }
    return `      ${s}   (| = multiple of 10, starts at ${start})`;
  };

  return {
    async minecraft_survey(args) {
      const [lo, hi] = await K.boxFromArgs(args);
      const at = await K.dumpBig(lo, hi);
      const counts = {}, surf = {}, tops = {};
      let fluids = 0, naturalCols = 0, cols = 0;
      const roadCells = [];
      for (let x = lo[0]; x <= hi[0]; x++) for (let z = lo[2]; z <= hi[2]; z++) {
        cols++;
        let top = null, topY = null, builtAbove = false;
        for (let y = hi[1]; y >= lo[1]; y--) {
          const n = at(x, y, z);
          if (!n || K.AIR.has(n)) continue;
          if (K.isSolid(n, y)) { counts[n] = (counts[n] || 0) + 1; builtAbove = true; }
          if (n === "water" || n === "lava") fluids++;
          if (top === null && !/^(short_grass|tall_grass|fern|large_fern)$/.test(n)) { top = n; topY = y; }
        }
        if (top) { surf[top] = (surf[top] || 0) + 1; tops[topY] = (tops[topY] || 0) + 1; }
        if (top && natural(top, topY) && !builtAbove) naturalCols++;
        if (ROADS.has(top)) roadCells.push([x, topY, z]);
      }
      const sorted = (o, n) => Object.entries(o).sort((a, b) => b[1] - a[1]).slice(0, n);
      const sc = await K.scarpet(`r=[]; c=[]; volume(${lo.join(",")},${hi.join(",")}, b=str(_); if(b~'rail$', r+=[pos(_):0,pos(_):1,pos(_):2,b,str(block_state(_,'shape')),block_state(_,'powered')], b~'chest|barrel|shulker_box|hopper|dispenser|dropper', p=pos(_); c+=[p:0,p:1,p:2,b,reduce(inventory_get(p), _a+if(_,_:1,0), 0)])); encode_json([r,c])`);
      let rails = [], containers = [];
      try { [rails, containers] = JSON.parse(sc.value); } catch {}
      const cen = lo.map((v, i) => (v + hi[i] + 1) / 2), half = lo.map((v, i) => (hi[i] - v + 1) / 2);
      const en = await K.scarpet(`encode_json(map(entity_area('*', [${cen.join(",")}], [${half.join(",")}]), [str(_~'type'), if(_~'type'=='player', _~'name', query(_,'custom_name')), query(_,'tags'), map(pos(_), floor(_))]))`);
      let ents = [];
      try { ents = JSON.parse(en.value); } catch {}
      const eCounts = {};
      for (const [t] of ents) eCounts[t] = (eCounts[t] || 0) + 1;
      const B = { lo, hi };
      const E = K.mapEntries();
      const overlaps = (e) => e.lo.every((v, i) => v <= hi[i]) && e.hi.every((v, i) => v >= lo[i]);
      const ref = args.pos ? K.V(args.pos) : cen;
      const nearest = (cells) => { let b = null, bd = Infinity; for (const c of cells) { const d = Math.hypot(c[0] - ref[0], c[2] - ref[2]); if (d < bd) { bd = d; b = c; } } return b ? { pos: b.slice(0, 3), ...(b[4] ? { shape: b[4] } : {}), distance: Math.round(bd) } : null; };
      const z = K.zoneGuard([{ lo, hi }], false);
      return K.text({
        box: `${lo.join(",")} → ${hi.join(",")}`, size: hi.map((v, i) => v - lo[i] + 1).join("×"),
        players_inside: ents.filter((e) => e[0] === "player").map((e) => `${e[1]} ${e[3].join(",")}`),
        map_builds: E.filter((e) => e.lo && overlaps(e)).map((e) => `${e.name} (${e.owner || "?"}) ${e.lo.join(",")} → ${e.hi.join(",")}`),
        nearby_builds: K.WM.near(E, B, 30).filter((n) => n.gap > 0).slice(0, 6).map((n) => `${n.name}: ${n.gap} blocks ${n.direction}`),
        protected: z ? "yes — " + z.slice(0, 400) : "no protected zone here",
        ground: { natural_surface_columns: `${naturalCols}/${cols} (${Math.round((100 * naturalCols) / cols)}%)`, surface_levels: sorted(tops, 4).map(([y, n]) => `y ${y}: ${n}`), surface_blocks: Object.fromEntries(sorted(surf, 8)), fluids },
        built_blocks: { total: Object.values(counts).reduce((a, b) => a + b, 0), top: Object.fromEntries(sorted(counts, 20)) },
        rails: summarizeRails(rails),
        containers: containers.slice(0, 30).map((c) => `${c[3]} ${c.slice(0, 3).join(",")}: ${c[4]} items`),
        entities: ents.length ? { counts: Object.fromEntries(sorted(eCounts, 15)), named_or_tagged: ents.filter((e) => e[0] !== "player" && (e[2]?.length || e[1])).slice(0, 25).map((e) => `${e[0]}${e[1] ? ` "${e[1]}"` : ""}${e[2]?.length ? " [" + e[2].join(",") + "]" : ""} ${e[3].join(",")}`) }
          : "none seen — entities exist only in LOADED chunks (nobody near = nothing listed)",
        nearest: { road: nearest(roadCells), rail: nearest(rails) },
      });
    },

    async minecraft_section(args) {
      const [lo, hi] = await K.boxFromArgs(args, { r: 12, down: 2, up: 20 });
      const W = hi[0] - lo[0] + 1, D = hi[2] - lo[2] + 1, H = hi[1] - lo[1] + 1;
      const out = [];
      if (args.top || !args.axis) {
        if (W > 160 || D > 120) throw new Error(`top map is ${W}×${D} — max 160×120`);
        const at = await K.dumpBig(lo, hi);
        const grid = [], hs = [];
        for (let z = lo[2]; z <= hi[2]; z++) {
          const row = [], hrow = [];
          for (let x = lo[0]; x <= hi[0]; x++) {
            let n = null, yy = lo[1];
            for (let y = hi[1]; y >= lo[1]; y--) { const b = at(x, y, z); if (b && !K.AIR.has(b) && !/^(short_grass|tall_grass)$/.test(b)) { n = b; yy = y; break; } }
            row.push([n, yy]); hrow.push(yy);
          }
          grid.push(row); hs.push(hrow);
        }
        const { ch, legend } = legendFor(grid.flat());
        out.push(`TOP MAP x ${lo[0]}..${hi[0]} (→ east) · z ${lo[2]}..${hi[2]} (↓ south) · highest block of each column`, ruler(lo[0], W));
        grid.forEach((row, i) => out.push(`${String(lo[2] + i).padStart(5)} ${row.map(([n, y]) => glyph(n, y, ch)).join("")}`));
        out.push("legend: " + legend);
        if (args.heights) {
          const base = Math.min(...hs.flat());
          out.push(`HEIGHTS (y − ${base}, base36: 0-9 then a=10 …)`);
          hs.forEach((row, i) => out.push(`${String(lo[2] + i).padStart(5)} ${row.map((y) => Math.min(35, y - base).toString(36)).join("")}`));
        }
        return K.text(out.join("\n"));
      }
      const ats = [].concat(args.at ?? []).map(Number).slice(0, 4);
      if (!ats.length) throw new Error("axis needs at: a coordinate (or up to 4)");
      for (const a of ats) {
        let R, rows = [];
        if (args.axis === "y") {
          if (W > 160 || D > 120) throw new Error(`slice is ${W}×${D} — max 160×120`);
          R = await K.dumpRegion([lo[0], a, lo[2]], [hi[0], a, hi[2]]);
          for (let z = lo[2]; z <= hi[2]; z++) rows.push({ label: z, cells: Array.from({ length: W }, (_, i) => [R.at(lo[0] + i, a, z), a]) });
          out.push(`FLOOR PLAN at y ${a} · x ${lo[0]}..${hi[0]} (→ east) · z (↓ south)`, ruler(lo[0], W));
        } else if (args.axis === "x") {
          if (D > 160 || H > 120) throw new Error(`slice is ${D}×${H} — max 160×120`);
          R = await K.dumpRegion([a, lo[1], lo[2]], [a, hi[1], hi[2]]);
          for (let y = hi[1]; y >= lo[1]; y--) rows.push({ label: y, cells: Array.from({ length: D }, (_, i) => [R.at(a, y, lo[2] + i), y]) });
          out.push(`SECTION at x ${a}, seen from the east · z ${lo[2]}..${hi[2]} (→ south) · y (↓ down)`, ruler(lo[2], D));
        } else if (args.axis === "z") {
          if (W > 160 || H > 120) throw new Error(`slice is ${W}×${H} — max 160×120`);
          R = await K.dumpRegion([lo[0], lo[1], a], [hi[0], hi[1], a]);
          for (let y = hi[1]; y >= lo[1]; y--) rows.push({ label: y, cells: Array.from({ length: W }, (_, i) => [R.at(lo[0] + i, y, a), y]) });
          out.push(`SECTION at z ${a}, seen from the south · x ${lo[0]}..${hi[0]} (→ east) · y (↓ down)`, ruler(lo[0], W));
        } else throw new Error("axis: x | y | z (or top:true)");
        if (args.axis !== "y") while (rows.length > 1 && rows[0].cells.every(([n]) => !n || K.AIR.has(n))) rows.shift();
        const { ch, legend } = legendFor(rows.flatMap((r) => r.cells));
        for (const r of rows) out.push(`${String(r.label).padStart(5)} ${r.cells.map(([n, y]) => glyph(n, y, ch)).join("")}`);
        out.push("legend: " + legend, "");
      }
      return K.text(out.join("\n"));
    },
  };
}
