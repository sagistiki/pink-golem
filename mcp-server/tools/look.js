/**
 * Looking at the world: minecraft_inspect, minecraft_vision, minecraft_scarpet, minecraft_screenshot,
 * minecraft_preview, minecraft_check_access, minecraft_reach, minecraft_monitor.
 */
import fs from "node:fs";
import path from "node:path";

const vec = { type: "array", items: { type: "number" }, minItems: 3, maxItems: 3, description: "[x, y, z]" };

export const tools = [
  {
    name: "minecraft_inspect",
    description: "Read blocks: one block at pos (full state), or a box from/to (max 8000 blocks) listing every non-air block (mode list) or block counts (mode counts). Coordinates absolute or relative_to_player. Use it to check door cells, stair facings and exact states — pictures can't show those.",
    inputSchema: { type: "object", properties: { pos: vec, from: vec, to: vec, relative_to_player: { type: "string" }, mode: { type: "string", enum: ["list", "counts"], description: "For boxes (default list)" } } },
  },
  {
    name: "minecraft_vision",
    description: "SEE a structure as text: finds the whole build connected to a seed block and returns its size, block counts, features (doors, windows, lights, stairs, plants…), a TOP view and elevations, optionally every LAYER. Use it for 'look at my house', 'what do you think', 'improve this', and before building near anything. target: looking_at (the block under a player's crosshair) | near_player | pos | box (exact from/to). mode 'check' = is this box free to build in? (lists every non-natural block and players inside).",
    inputSchema: {
      type: "object",
      properties: {
        target: { type: "string", enum: ["looking_at", "near_player", "pos", "box"], description: "Default near_player" },
        player: { type: "string", description: "Whose view / position to use (default: the first real player online)" },
        pos: vec, from: vec, to: vec,
        radius: { type: "number", description: "Search radius around the seed/player (default 20, max 40)" },
        views: { type: "array", items: { type: "string", enum: ["top", "south", "north", "east", "west", "layers"] }, description: "Default top, south, east" },
        layer_from: { type: "number" }, layer_to: { type: "number" },
        mode: { type: "string", enum: ["see", "check"] },
      },
    },
  },
  {
    name: "minecraft_scarpet",
    description: "Run a Carpet scarpet expression (/script run ...) and get the result. Good for reading the world: block(x,y,z), block_state(...), biome(x,y,z), top('surface',x,0,z), entity_selector('@e[type=cat]'), player('all'). Multi-line code and // comments are cleaned up. End with the value you want (`...; l`). Use app:'cu' for the helper functions (occupied, count, ytop, dark, show, snap...).",
    inputSchema: { type: "object", properties: { expression: { type: "string" }, app: { type: "string", description: "run inside a scarpet app (e.g. cu) when you need its functions" }, raw: { type: "boolean", description: "send exactly as written" } }, required: ["expression"] },
  },
  {
    name: "minecraft_screenshot",
    description: "Take a picture of part of the world and SEE it. mode iso (default: isometric 3D, view from se|sw|nw|ne) | top (map) | fpv (first person from a player's eyes, near) | pov (first person, far, + which builds are in view) | real (BlueMap render with real textures; needs the BlueMap mod + Chrome/Edge). Area = from/to box, or pos/player + radius (default: around the first real player). cut_y = cutaway to see inside rooms. Flat colours, no textures. Max ~118k blocks per iso/top shot.",
    inputSchema: { type: "object", properties: {
      from: vec, to: vec, pos: vec, player: { type: "string" }, radius: { type: "number" }, height: { type: "number", description: "blocks above the centre (default 24)" },
      view: { type: "string", enum: ["se", "sw", "nw", "ne"] }, mode: { type: "string", enum: ["iso", "top", "fpv", "pov", "real"] },
      cut_y: { type: "number" }, entities: { type: "boolean", description: "draw NPCs/players/text as bright markers (default true)" },
      yaw: { type: "number" }, pitch: { type: "number" }, fov: { type: "number" }, width: { type: "number" },
      distance: { type: "number" }, update: { type: "boolean", description: "real mode: re-render the area in BlueMap first (+8 s)" }, fetch: { type: "string" }, angle: { type: "number" },
      scale: { type: "number", description: "px per block (auto)" }, name: { type: "string" } } },
  },
  {
    name: "minecraft_preview",
    description: "SEE a build BEFORE building it: runs the commands (commands / commands_file / commands_files — fill, setblock, clone, place feature, summon…) in a virtual copy of the world and returns pictures. NOTHING is placed. overlay (default true) draws it on top of what is really there (offline: on empty flat ground). mode iso | top | fpv | all. cut_y = cutaway. entrance:[x,y,z] also runs the access check on the plan (unreachable rooms, blocked doors, bad stairs) so you fix bugs before they exist.",
    inputSchema: { type: "object", properties: {
      commands: { type: "array", items: { type: "string" } }, commands_file: { type: "string" }, commands_files: { type: "array", items: { type: "string" } },
      mode: { type: "string", enum: ["iso", "top", "fpv", "all"] }, view: { type: "string", enum: ["se", "sw", "nw", "ne"] }, cut_y: { type: "number" }, overlay: { type: "boolean" },
      entrance: vec, pos: vec, yaw: { type: "number" }, pitch: { type: "number" }, fov: { type: "number" }, scale: { type: "number" }, margin: { type: "number" }, entities: { type: "boolean" }, name: { type: "string" } } },
  },
  {
    name: "minecraft_check_access",
    description: "Accessibility check of a build (nobody moves): walks virtually from the entrance (feet position just outside the main door) with real player rules (1-block jumps, stairs/slabs, drops ≤3, doors) and reports rooms nobody can reach (and why), doors blocked on one side, stairs that end in a wall or lack headroom, full-block steps at doors (a path one block too high) and dark spots where mobs spawn. Which build: build:<name in the world map>, or from/to, or the command file(s) with simulate:true (checks a plan before building). Build tools run this automatically when you pass entrance on the last phase. It must say ok before you call a building done.",
    inputSchema: { type: "object", properties: { build: { type: "string" }, entrance: vec, player: { type: "string", description: "use this player's position as the entrance" }, from: vec, to: vec,
      commands: { type: "array", items: { type: "string" } }, commands_file: { type: "string" }, commands_files: { type: "array", items: { type: "string" } }, simulate: { type: "boolean" }, dark: { type: "boolean" }, min_room: { type: "number", description: "ignore unreachable pockets smaller than this many floor cells (default 6)" } } },
  },
  {
    name: "minecraft_reach",
    description: "Walkability check (nobody moves): can a player walk from `from` (or a player's position) to each target, using doors and stairs? Returns reachable yes/no, steps and doors used.",
    inputSchema: { type: "object", properties: { from: vec, player: { type: "string" }, targets: { type: "array", items: vec }, margin: { type: "number" } }, required: ["targets"] },
  },
  {
    name: "minecraft_monitor",
    description: "Record a timeline for up to 50 s: positions/vehicles of players, block states at chosen spots (a lamp, a door, a rail) and entity counts/positions (selectors). Debugs redstone, rides and game logic: 'did the door open when the cart passed?'.",
    inputSchema: { type: "object", properties: {
      seconds: { type: "number", description: "duration, max 50 (default 10)" }, every_ticks: { type: "number", description: "sample interval in ticks (default 10)" },
      track: { type: "array", items: { type: "string" }, description: "player names (default: the bot)" },
      blocks: { type: "array", items: { type: "array" }, description: "[[x,y,z,'label'], ...]" },
      entities: { type: "array", items: { type: "array" }, description: "[['@e[type=minecart,distance=..20,x=0,y=-60,z=0]','carts'], ...]" },
      changes_only: { type: "boolean", description: "only list samples where something changed (default true)" } } },
  },
];

export function handlers(K) {
  return {
    async minecraft_inspect(args) {
      const { origin } = await K.resolveOrigin(args);
      if (args.pos) {
        const p = K.add(origin, K.V(args.pos));
        const r = await K.inApp("cu", `bstr(block(${p.join(",")}))`);
        const m = /=\s*(.*?)\s*(\(\d.*)?$/.exec(r);
        return K.text({ pos: p, block: m ? m[1].replace(/^'|'$/g, "") : r });
      }
      if (!args.from || !args.to) throw new Error("Give pos, or from + to.");
      const a = K.add(origin, K.V(args.from)), b = K.add(origin, K.V(args.to));
      const vol = K.volOf(K.sortBox(a, b));
      if (vol > 8000) throw new Error(`Box is ${vol} blocks; max 8000 per inspect. Split it, or use cu count() for totals.`);
      const r = await K.scarpet(`l=[];volume(${a.join(",")},${b.join(",")},if(!air(_),p=pos(_);l+=str('%d %d %d %s',p:0,p:1,p:2,str(_))));join('|',l)`);
      const val = r.value.replace(/^'|'$/g, "");
      if (/error|exception/i.test(r.raw) && !val.includes("|") && !/^-?\d/.test(val)) return K.text({ scarpetError: r.raw });
      const items = val ? val.split("|").filter(Boolean) : [];
      if (args.mode === "counts") {
        const counts = {};
        for (const it of items) { const n = it.split(" ").slice(3).join(" "); counts[n] = (counts[n] || 0) + 1; }
        return K.text({ from: a, to: b, nonAirBlocks: items.length, counts });
      }
      return K.text({ from: a, to: b, nonAirBlocks: items.length, blocks: items.slice(0, 1500), truncated: items.length > 1500 });
    },

    async minecraft_vision(args) {
      if (args.mode === "check") {
        if (!args.from || !args.to) throw new Error("check needs from + to");
        const [lo, hi] = K.sortBox(K.V(args.from), K.V(args.to));
        const occ = await K.occupiedIn(lo, hi);
        const counts = {};
        for (const o of occ) counts[o[3]] = (counts[o[3]] || 0) + 1;
        const inside = [];
        for (const n of (await K.onlinePlayers()).names) {
          try {
            const p = (await K.playerInfo(n)).position;
            if (p.x >= lo[0] && p.x < hi[0] + 1 && p.y >= lo[1] - 1 && p.y <= hi[1] + 1 && p.z >= lo[2] && p.z < hi[2] + 1) inside.push(n);
          } catch {}
        }
        return K.text({ box: [lo, hi], free: occ.length === 0 && inside.filter((n) => n !== K.BOT).length === 0, occupiedBlocks: occ.length, counts,
          sample: occ.slice(0, 20).map((o) => `${o[0]} ${o[1]} ${o[2]} ${o[3]}`), playersInside: inside,
          note: occ.length ? "Something is already here — build elsewhere, or ask its owner before changing it." : "Area is free (only air / natural ground)." });
      }
      let playerName = args.player;
      if (!playerName && args.target !== "box" && args.target !== "pos") {
        playerName = await K.firstRealPlayer();
        if (!playerName) throw new Error("No real player online to look from — give pos or from/to.");
      }
      const target = args.target || "near_player";
      const r = Math.max(4, Math.min(args.radius ?? 20, 40));
      if (target === "box") {
        if (!args.from || !args.to) throw new Error("box needs from + to");
        const [lo, hi] = K.sortBox(K.V(args.from), K.V(args.to));
        const R = await K.dumpRegion(lo, hi);
        const cells = [];
        for (let y = lo[1]; y <= hi[1]; y++) for (let z = lo[2]; z <= hi[2]; z++) for (let x = lo[0]; x <= hi[0]; x++) if (K.isSolid(R.at(x, y, z), y)) cells.push([x, y, z]);
        if (!cells.length) return K.text(`Nothing built in [${lo.join(" ")}] → [${hi.join(" ")}] (only air / natural ground).`);
        return K.text(K.renderStructure(R, cells, args).text);
      }
      let seed, center, note = "";
      if (target === "looking_at") {
        const t = await K.scarpet(`b=query(player('${playerName}'),'trace',96,'blocks');if(b,pos(b),'none')`);
        const nums = K.parseNums(t.value);
        if (nums.length < 3) throw new Error(`${playerName} isn't looking at any block within 96 blocks (${t.raw.trim()})`);
        seed = nums.slice(0, 3).map(Math.round);
        center = seed;
        note = `${playerName} is looking at ${seed.join(" ")}`;
      } else if (target === "pos") {
        seed = K.V(args.pos);
        center = seed;
      } else {
        const p = await K.playerInfo(playerName);
        center = [p.block.x, p.block.y, p.block.z];
        note = `${playerName} stands at ${center.join(" ")}`;
      }
      const lo = [center[0] - r, Math.max(-64, center[1] - 6), center[2] - r];
      const hi = [center[0] + r, center[1] + Math.min(40, 2 * r), center[2] + r];
      while (K.volOf([lo, hi]) > 120000) { lo[0]++; hi[0]--; lo[2]++; hi[2]--; }
      const R = await K.dumpRegion(lo, hi);
      if (target === "near_player") {
        let best = null, bd = Infinity;
        for (let y = lo[1]; y <= hi[1]; y++) for (let z = lo[2]; z <= hi[2]; z++) for (let x = lo[0]; x <= hi[0]; x++) {
          if (!K.isSolid(R.at(x, y, z), y)) continue;
          const d = (x - center[0]) ** 2 + (y - center[1]) ** 2 * 2 + (z - center[2]) ** 2;
          if (d < bd) { bd = d; best = [x, y, z]; }
        }
        if (!best) return K.text(`${note}. Nothing built within ${r} blocks.`);
        seed = best;
        note += `; closest built block: ${best.join(" ")} (${R.at(...best)})`;
      }
      const seedName = R.at(...seed);
      if (!K.isSolid(seedName, seed[1])) throw new Error(`Seed ${seed.join(" ")} is ${seedName} (not part of a build).`);
      const fl = K.floodStructure(R, seed);
      const view = K.renderStructure(R, fl.cells, args);
      const warn = fl.touches ? `\n⚠ The structure reaches the edge of the scanned area (radius ${r}) — it may be bigger; rescan with a larger radius or target:box.` : "";
      return K.text(`${note}\n${view.text}${warn}`);
    },

    async minecraft_scarpet(args) {
      if (args.app) return K.text(await K.inApp(args.app, K.cleanScarpet(args.expression)));
      const r = await K.scarpet(args.expression, { raw: args.raw === true });
      if (/^\s*=\s*null\b/.test(r.raw) && !args.raw) {
        // "= null" usually means the LAST statement returned nothing, or the code needs an app's functions
        const sideEffects = /\b(set|run|spawn|modify|inventory_set|place_item|delete_file|write_file|schedule|create_explosion|harvest|destroy|summon|without_updates)\s*\(/.test(r.expr);
        const again = sideEffects ? "null (not re-run: the code changes the world)" : await K.inApp("cu", r.expr).catch((e) => "ERROR " + e.message);
        const hint = "Result was null. Usual causes: the last statement returns nothing (end with the value, e.g. `...; l`), a for()/print() at the end, or a function that only exists in an app (use app:'cu').";
        return K.text(`${r.raw}\n${/null/.test(again) ? "" : `in app cu: ${again}\n`}${hint}`);
      }
      return K.text(r.raw);
    },

    minecraft_screenshot: (args) => K.screenshot(args),
    minecraft_preview: (args) => K.previewBuild(args),
    minecraft_check_access: async (args) => K.text(await K.checkAccess(args)),

    async minecraft_reach(args) {
      let from = args.from ? K.V(args.from) : null;
      if (!from) { const p = await K.playerInfo(args.player || K.BOT); from = [p.position.x, p.position.y, p.position.z]; }
      const res = await K.reach(from, (args.targets || []).map(K.V), args.margin ?? 6);
      return K.text({ from, all_reachable: res.every((r) => r.reachable), results: res });
    },

    async minecraft_monitor(args) {
      const secs = Math.max(1, Math.min(args.seconds ?? 10, 50));
      const every = Math.max(1, Math.min(args.every_ticks ?? 10, 200));
      const id = "m" + Date.now().toString(36);
      const spec = { every, count: Math.max(1, Math.floor((secs * 20) / every)), track: args.track || [K.BOT],
        blocks: (args.blocks || []).map((b) => [Math.floor(+b[0]), Math.floor(+b[1]), Math.floor(+b[2]), String(b[3] ?? b.slice(0, 3).join(","))]),
        entities: (args.entities || []).map((e) => [String(e[0]), String(e[1] ?? e[0])]) };
      fs.mkdirSync(K.P.CU_DATA, { recursive: true });
      const outF = path.join(K.P.CU_DATA, `mon_${id}_out.json`);
      fs.writeFileSync(path.join(K.P.CU_DATA, `mon_${id}.json`), JSON.stringify(spec));
      const r = await K.inApp("cu", `mon_start('${id}')`);
      if (!/started/.test(r)) throw new Error(`monitor did not start: ${r.slice(0, 300)}`);
      const until = Date.now() + secs * 1000 + 8000;
      while (Date.now() < until && !fs.existsSync(outF)) await K.sleep(500);
      if (!fs.existsSync(outF)) return K.text("monitor did not finish in time (server lagging?)");
      await K.sleep(200);
      const samples = K.readJSON(outF, { samples: [] }).samples || [];
      try { fs.unlinkSync(outF); } catch {}
      const r1 = (v) => (Array.isArray(v) ? v.map((q) => (typeof q === "number" ? +q.toFixed(1) : q)) : v);
      const norm = samples.map((s) => ({ t: s.t, p: Object.fromEntries(Object.entries(s.p || {}).map(([k, v]) => [k, r1(v)])), b: s.b || {},
        e: Object.fromEntries(Object.entries(s.e || {}).map(([k, v]) => [k, Array.isArray(v) ? [v[0], r1(v[1])] : v])) }));
      let tl = norm;
      if (args.changes_only !== false) {
        let prev = null;
        tl = norm.filter((s) => {
          const key = JSON.stringify({ b: s.b, e: Object.fromEntries(Object.entries(s.e).map(([k, v]) => [k, v[0]])), m: Object.values(s.p).map((v) => v?.[3]) });
          const keep = key !== prev || s === norm[norm.length - 1]; prev = key; return keep || s === norm[0];
        });
      }
      return K.text({ samples: norm.length, every_ticks: every, timeline: tl.slice(0, 120) });
    },
  };
}
