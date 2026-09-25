/** Rail lines: minecraft_rails — trace a network, lay a path with correct shapes and boosters, ride a test cart. */
import fs from "node:fs";
import path from "node:path";

const vec = { type: "array", items: { type: "number" }, minItems: 3, maxItems: 3, description: "[x, y, z]" };
const DIRV = { north: [0, -1], south: [0, 1], east: [1, 0], west: [-1, 0] };
const r1 = (v) => Math.round(v * 10) / 10;

export const tools = [
  {
    name: "minecraft_rails",
    description: "Rail tools. action trace (pos = any rail): follow the whole connected line → rail count, closed loop?, open ends, one-way links (a rail pointing into the side of another), unpowered powered rails, stretches longer than `gap` (default 8) with no booster. action path (points = corners [[x,y,z],...], each leg straight along x or z; y may change along a leg → slopes): correct curve and slope shapes, a booster (powered rail on a redstone block) every boost_every (5) + curve_boost (2) right after each corner, a support block under every rail where there is air → a job file; build:true builds it (undo, zones, verify), dry_run:true = preflight only. action ride (pos = a rail, direction the cart starts rolling, speed 0.4, seconds ≤110, rider default true = an invisible armor-stand passenger, because an EMPTY cart loses speed fast): a real test cart → timeline, stops / stall position, distance, max speed, 'came back to the start' for loops; until_pos ends early. The cart is removed afterwards.",
    inputSchema: { type: "object", properties: {
      action: { type: "string", enum: ["trace", "path", "ride"] }, pos: vec, max: { type: "number" }, gap: { type: "number" },
      points: { type: "array", items: vec }, name: { type: "string" }, boost_every: { type: "number" }, curve_boost: { type: "number" }, support: { type: "string" },
      closed: { type: "boolean" }, build: { type: "boolean" }, dry_run: { type: "boolean" }, label: { type: "string" }, allow_protected: { type: "boolean" },
      direction: { type: "string", enum: ["north", "south", "east", "west"] }, speed: { type: "number" }, seconds: { type: "number" }, rider: { type: "boolean" },
      until_pos: vec, radius: { type: "number" }, keep: { type: "boolean" } }, required: ["action"] },
  },
];

export function handlers(K) {
  async function trace(args) {
    const p = K.V(args.pos).map(Math.floor);
    const id = "t" + Date.now().toString(36);
    const out = await K.inApp("cu", `rtrace('${id}', ${p.join(",")}, ${Math.min(args.max ?? 6000, 20000)})`);
    const f = path.join(K.P.CU_DATA, `rails_${id}.json`);
    if (!fs.existsSync(f)) return { error: String(out).replace(/^\s*=\s*/, "").slice(0, 200) };
    const d = K.readJSON(f, { rails: [] });
    try { fs.unlinkSync(f); } catch {}
    const key = (q) => q.join(",");
    const nodes = new Map(d.rails.map((r) => [key(r.slice(0, 3)), { p: r.slice(0, 3), shape: r[3], block: r[4], powered: String(r[5]) === "true", ns: r[6] }]));
    const problems = [], links = new Map();
    for (const [k, n] of nodes) {
      const ok = [];
      n.ns.forEach((q, i) => {
        if (!q) { problems.push(`open end: ${n.shape} ${k} leads to nothing (side ${i + 1})`); return; }
        const m = nodes.get(key(q));
        if (!m) return;
        if (!m.ns.some((b) => b && key(b) === k)) problems.push(`one-way: ${n.shape} ${k} points into ${m.shape} ${key(q)}, which does not connect back`);
        else ok.push(key(q));
      });
      links.set(k, ok);
    }
    const start = [...links].find(([, l]) => l.length < 2)?.[0] || [...links.keys()][0];
    const order = [], seen = new Set();
    for (let cur = start; cur && !seen.has(cur); cur = links.get(cur).find((q) => !seen.has(q))) { seen.add(cur); order.push(cur); }
    const loop = order.length === nodes.size && links.get(order[order.length - 1])?.includes(start) && nodes.size > 3;
    const gap = args.gap ?? 8;
    const boostIdx = order.map((k, i) => (nodes.get(k).block === "powered_rail" && nodes.get(k).powered ? i : -1)).filter((i) => i >= 0);
    const stretches = [];
    if (boostIdx.length) {
      const seq = loop ? [...boostIdx, boostIdx[0] + order.length] : boostIdx;
      for (let j = 0; j + 1 < seq.length; j++) {
        const len = seq[j + 1] - seq[j];
        if (len > gap) stretches.push({ from: order[seq[j] % order.length], to: order[seq[j + 1] % order.length], rails: len });
      }
    }
    const shapes = {};
    for (const n of nodes.values()) shapes[n.shape] = (shapes[n.shape] || 0) + 1;
    const all = [...nodes.values()].map((n) => n.p);
    const bb = [[0, 1, 2].map((i) => Math.min(...all.map((q) => q[i]))), [0, 1, 2].map((i) => Math.max(...all.map((q) => q[i])))];
    return {
      rails: nodes.size, closed_loop: !!loop, truncated: !!d.truncated, bounds: `${bb[0].join(",")} → ${bb[1].join(",")}`, shapes,
      boosters: boostIdx.length, unpowered_powered_rails: [...nodes.values()].filter((n) => n.block === "powered_rail" && !n.powered).map((n) => key(n.p)).slice(0, 20),
      problems: problems.length ? problems.slice(0, 25) : "none",
      [`stretches_longer_than_${gap}_without_booster`]: stretches.length ? stretches.sort((a, b) => b.rails - a.rails).slice(0, 15) : "none",
      note: boostIdx.length ? "an EMPTY cart stops ~8 rails after a booster; a ridden cart goes much further" : "no boosters on this line",
    };
  }

  async function lay(args) {
    const pts = (args.points || []).map(K.V);
    if (pts.length < 2) throw new Error("points: at least 2 [x,y,z] corners, each leg straight along x or z");
    const name = String(args.name || "rails-" + Date.now().toString(36)).replace(/[^\w.-]/g, "_");
    const spec = { points: pts, name, boost_every: args.boost_every ?? 5, curve_boost: args.curve_boost ?? 2, support: args.support ?? "smooth_stone", closed: !!args.closed };
    const script = path.join(K.P.ROOT, "skill", "clawdblock", "scripts", "city.py");
    const env = { CLAWDBLOCK_ROOT: K.P.ROOT, CLAWDBLOCK_JOBS: K.P.JOBS, PYTHONIOENCODING: "utf-8" };
    let r = null;
    for (const py of K.PYTHONS) {
      r = await K.run(py, [script, "rails", JSON.stringify(spec)], { cwd: path.dirname(script), timeout: 60000, env });
      if (!(r.err && r.err.code === "ENOENT")) break;
    }
    if (r.err) throw new Error(`city.py failed: ${(r.stderr || r.err.message).slice(-800)}`);
    let res;
    try { res = JSON.parse(r.stdout.trim().split("\n").pop()); } catch { throw new Error("city.py output: " + r.stdout.slice(-500)); }
    if (!args.build && !args.dry_run) return { ...res, next: "build it: minecraft_run_command commands_files:" + JSON.stringify(res.files) + " (or call again with build:true), then action:ride / trace" };
    let list = [];
    for (const f of res.files) list = list.concat(JSON.parse(fs.readFileSync(K.safePath(f), "utf8")));
    if (args.dry_run) return { ...res, preflight: await K.preflight(list, args) };
    const b = await K.handle("minecraft_run_command", { commands_files: res.files, label: args.label || name, allow_protected: args.allow_protected });
    let build;
    try { build = JSON.parse(b.content?.[0]?.text || "{}"); } catch { build = b.content?.[0]?.text; }
    return { ...res, build };
  }

  async function ride(args) {
    const p = K.V(args.pos);
    const dir = DIRV[args.direction];
    if (!dir) throw new Error("direction: north | south | east | west (the way the cart should start rolling)");
    const sp = Math.max(0.05, Math.min(args.speed ?? 0.4, 1.2));
    const tag = "ride_" + Date.now().toString(36);
    const secs = Math.max(2, Math.min(args.seconds ?? 20, 110));
    // Carts only move in chunks that tick = near a player (forceloaded chunks do not tick entities, and a server
    // with pause-when-empty-seconds stops altogether). With nobody within 96 blocks a spectator fake player stands
    // by the start for the ride. Its name is looked up at Mojang the first time (a short freeze) — always reuse it.
    const near = await K.scarpet(`length(filter(player('all'), _~'dimension'=='overworld' && abs(pos(_):0-(${p[0]}))<96 && abs(pos(_):2-(${p[2]}))<96))`);
    let tester = null;
    if (Number(near.value) === 0) {
      tester = "Rail_Tester";
      await K.cmd(`player ${tester} spawn at ${p[0]} ${p[1] + 4} ${p[2]} facing 0 90 in minecraft:overworld in spectator`).catch(() => {});
      await K.sleep(1500);
    }
    const rider = args.rider !== false ? `,Passengers:[{id:"minecraft:armor_stand",Invisible:1b,Small:1b,NoGravity:1b,Tags:["${tag}"]}]` : "";
    const out = await K.cmd(`summon minecart ${Math.floor(p[0]) + 0.5} ${Math.floor(p[1])} ${Math.floor(p[2]) + 0.5} {Tags:["${tag}"],Motion:[${dir[0] * sp}d,0d,${dir[1] * sp}d]${rider}}`);
    if (K.looksLikeError(out)) { if (tester) await K.cmd(`player ${tester} kill`).catch(() => {}); throw new Error("could not summon the cart: " + out); }
    const until = args.until_pos ? K.V(args.until_pos) : null;
    const t0 = Date.now(), samples = [], stops = [];
    let last = null, dist = 0, still = 0, frozen = 0, maxV = 0, stopAt = null, reason = "time up";
    try {
      while (Date.now() - t0 < secs * 1000) {
        await K.sleep(250);
        const r = await K.scarpet(`e=entity_selector('@e[type=minecart,tag=${tag},limit=1]'); if(e, encode_json([pos(e:0), query(e:0,'motion')]), 'gone')`);
        if (!/^\s*\[/.test(r.value)) { reason = "the cart disappeared (broken, or it left the loaded chunks)"; break; }
        const [q, m] = JSON.parse(r.value);
        const v = Math.hypot(m[0], m[2]);
        maxV = Math.max(maxV, v);
        if (last) dist += Math.hypot(q[0] - last[0], q[1] - last[1], q[2] - last[2]);
        const t = +((Date.now() - t0) / 1000).toFixed(1);
        const prev = samples[samples.length - 1];
        if (!prev || (t - prev.t >= 1 && prev.pos.join() !== q.map(r1).join())) samples.push({ t, pos: q.map(r1), speed: +v.toFixed(2) });
        if (v >= 0.02 && last && Math.hypot(q[0] - last[0], q[1] - last[1], q[2] - last[2]) < 0.001) {
          if (++frozen >= 12) { reason = "frozen: the cart has speed but does not move — its chunk is not ticking"; break; }
        } else frozen = 0;
        if (v < 0.02 && last && Math.hypot(q[0] - last[0], q[2] - last[2]) < 0.05) {
          still++;
          if (still === 4) { stopAt = q.map(r1); stops.push({ t, pos: stopAt }); }
          if (still >= 12) { reason = `stalled at ${stopAt.map(Math.floor).join(",")}`; break; }
        } else still = 0;
        last = q;
        if (until && Math.hypot(q[0] - until[0] - 0.5, q[2] - until[2] - 0.5) <= (args.radius ?? 2)) { reason = "reached until_pos"; break; }
        if (!until && dist > 20 && Math.hypot(q[0] - p[0] - 0.5, q[2] - p[2] - 0.5) < 2) { reason = "came back to the start (closed loop ✓)"; break; }
      }
    } finally {
      if (!args.keep) await K.cmd(`kill @e[tag=${tag}]`).catch(() => {});
      if (tester) await K.cmd(`player ${tester} kill`).catch(() => {});
    }
    return { result: reason, seconds: +((Date.now() - t0) / 1000).toFixed(1), distance: Math.round(dist), max_speed: +maxV.toFixed(2), final: last?.map(r1),
      stops: stops.length ? stops : "none", timeline: samples.slice(0, 60), rider: args.rider !== false ? "armor stand passenger (keeps speed like a player)" : "empty cart (loses speed fast)" };
  }

  return {
    async minecraft_rails(args) {
      if (args.action === "trace") return K.text(await trace(args));
      if (args.action === "path") return K.text(await lay(args));
      if (args.action === "ride") return K.text(await ride(args));
      throw new Error("action: trace | path | ride");
    },
  };
}
