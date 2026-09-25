/**
 * context — things several tools share:
 *   chat context   every chat line remembers where the player stood, what they looked at and which build they were in
 *                  (so "here" / "this chest" is known later; history in data/chat-context.jsonl)
 *   big boxes      read up to 480k blocks (dumpRegion is ~120k), resolve an area from from/to | build | pos/player + radius
 *   preflight      check a command list WITHOUT running it: the server parses every distinct command form
 *                  (`execute if block <unloaded> run <cmd>` never executes <cmd>), plus zones, overwrites, players, limits
 */
import fs from "node:fs";
import path from "node:path";

const r1 = (v) => Math.round(v * 10) / 10;

export function install(K, ctx) {
  const { waiters } = ctx;

  // ═══════════════════ chat context ═══════════════════
  let online = { t: 0, names: [] };
  K.onlineNamesCached = async () => {
    if (Date.now() - online.t > 10000) online = { t: Date.now(), names: (await K.onlinePlayers()).names };
    return online.names;
  };
  /** The account name behind a chat display name (chat mods decorate names: "✦ Steve" → Steve). */
  const accountOf = async (display) => {
    const names = await K.onlineNamesCached().catch(() => []);
    const hit = names.filter((n) => display.includes(n)).sort((a, b) => b.length - a.length)[0];
    return hit || (display.match(/[A-Za-z0-9_]{2,16}$/) || [display])[0];
  };
  const buildAt = (p) => {
    const inside = K.WM.at(K.mapEntries(), p).filter((e) => e.lo);
    inside.sort((a, b) => K.volOf([a.lo, a.hi]) - K.volOf([b.lo, b.hi]));
    return inside[0]?.name || null;
  };
  /** Where a player is right now: position, yaw/pitch, the block under the crosshair, dimension, the build they are in. */
  K.whereIs = async (name) => {
    const r = await K.scarpet(`p=player('${name}'); if(!p, 'none', b=query(p,'trace',64,'blocks'); encode_json([pos(p), query(p,'yaw'), query(p,'pitch'), if(b, [str(b), pos(b)], null), str(query(p,'dimension'))]))`);
    if (!/^\s*\[/.test(r.value)) return null;
    const [pos, yaw, pitch, look, dim] = JSON.parse(r.value);
    return { pos: pos.map(r1), yaw: r1(yaw), pitch: r1(pitch), look: look ? { block: look[0], pos: look[1] } : null, dim, build: buildAt(pos) };
  };
  const CHAT_LOG = path.join(K.P.DATA, "chat-context.jsonl");
  const enrich = (e) => {
    if ((e.type !== "chat" && e.type !== "say") || e.at !== undefined || e._pending) return;
    const p = (async () => {
      const mc = await accountOf(e.player);
      Object.defineProperty(e, "mc", { value: mc, enumerable: false, writable: true });
      if (mc === K.BOT || (K.isCrew && K.isCrew(mc))) return;
      e.at = await K.whereIs(mc).catch(() => null);
      try {
        if (fs.existsSync(CHAT_LOG) && fs.statSync(CHAT_LOG).size > 2e6) fs.renameSync(CHAT_LOG, CHAT_LOG + ".old");
        fs.appendFileSync(CHAT_LOG, JSON.stringify({ date: new Date().toISOString(), player: mc, message: e.message, at: e.at }) + "\n");
      } catch {}
    })().catch(() => {});
    Object.defineProperty(e, "_pending", { value: p, enumerable: false, writable: true });
  };
  K.enrichChat = enrich;
  // one listener per process: the tool layer hot-reloads, so replace the previous version's listener
  for (const w of [...waiters]) if (w.__chatctx) waiters.delete(w);
  const listener = (e) => enrich(e);
  listener.__chatctx = true;
  waiters.add(listener);
  /** Wait (bounded) for lines that are still being looked up. Never looks up old lines: that would give the CURRENT position. */
  K.settleChat = async (list, ms = 2500) => {
    const ps = list.map((e) => e._pending).filter(Boolean);
    if (ps.length) await Promise.race([Promise.all(ps), K.sleep(ms)]);
  };
  K.fmtChat = (e) => {
    const base = ctx.fmtEvent(e);
    const a = e.at;
    if (!a) return base;
    const bits = [`${e.mc || ""} @ ${a.pos.map(Math.floor).join(",")}`];
    if (a.look) bits.push(`looks at ${a.look.block} ${a.look.pos.join(",")}`);
    if (a.build) bits.push(`in ${a.build}`);
    if (a.dim && a.dim !== "overworld") bits.push(a.dim);
    return `${base}   ⟨${bits.join(" · ")}⟩`;
  };
  K.chatFrom = (e, name) => !name || e.player === name || e.mc === name || String(e.player).toLowerCase().includes(String(name).toLowerCase());

  // ═══════════════════ big boxes ═══════════════════
  /** dumpRegion for up to 480k blocks (split along y). Returns at(x,y,z). */
  K.dumpBig = async (lo, hi) => {
    const area = (hi[0] - lo[0] + 1) * (hi[2] - lo[2] + 1);
    if (area > 118000) throw new Error(`the footprint is ${area} columns — max 118000`);
    if (area * (hi[1] - lo[1] + 1) > 480000) throw new Error(`box is ${area * (hi[1] - lo[1] + 1)} blocks — max 480000, use a smaller box`);
    const step = Math.max(1, Math.floor(118000 / area));
    const parts = [];
    for (let y = lo[1]; y <= hi[1]; y += step) parts.push(await K.dumpRegion([lo[0], y, lo[2]], [hi[0], Math.min(hi[1], y + step - 1), hi[2]]));
    return (x, y, z) => { const R = parts[Math.floor((y - lo[1]) / step)]; return R ? R.at(x, y, z) : null; };
  };
  /** An area from tool args: from/to, build (world map name + margin), or pos/player + radius (dflt r, down, up). */
  K.boxFromArgs = async (args, dflt = { r: 16, down: 4, up: 24 }) => {
    if (args.from && args.to) return K.sortBox(K.V(args.from), K.V(args.to));
    if (args.build) {
      const e = K.WM.lookup(K.mapEntries(), args.build)[0];
      if (!e?.lo) throw new Error(`no build called "${args.build}" with bounds on the world map`);
      const m = args.margin ?? 2;
      return [[e.lo[0] - m, e.lo[1], e.lo[2] - m], [e.hi[0] + m, e.hi[1], e.hi[2] + m]];
    }
    let c;
    if (args.pos) c = K.V(args.pos).map(Math.floor);
    else {
      const who = args.player || (await K.firstRealPlayer());
      if (!who) throw new Error("give from/to, build, pos or player");
      const p = await K.playerInfo(who);
      c = [p.block.x, p.block.y, p.block.z];
    }
    const r = Math.max(2, Math.min(args.radius ?? dflt.r, 60));
    return [[c[0] - r, Math.max(-64, c[1] - dflt.down), c[2] - r], [c[0] + r, Math.min(319, c[1] + (args.height ?? dflt.up)), c[2] + r]];
  };

  // ═══════════════════ preflight ═══════════════════
  const PROBE = "execute if block 30000000 0 30000000 air run ";   // never loaded → the inner command is parsed, never run
  const template = (c) => String(c).trim().replace(/^\/+/, "").replace(/(?<=\s)[~^]?-?\d+(?:\.\d+)?(?=\s|$)/g, "0");
  /** Let the server parse every distinct command form (coordinates folded) without running anything. */
  K.syntaxCheck = async (list, cap = 2500) => {
    const seen = new Map();
    for (const c of list) { const t = template(c); if (!seen.has(t)) seen.set(t, c); }
    const bad = [], tooLong = [];
    let checked = 0;
    for (const [, orig] of seen) {
      if (checked >= cap) break;
      if (Buffer.byteLength(orig, "utf8") > 1400) { tooLong.push(orig.slice(0, 120)); continue; }
      const probe = PROBE + String(orig).trim().replace(/^\/+/, "");
      if (Buffer.byteLength(probe, "utf8") > 1400) continue;          // too close to the RCON limit to wrap
      checked++;
      let out;
      try { out = await K.cmd(probe); } catch (e) { out = "ERROR: " + e.message; }
      if (out && (out.startsWith("ERROR:") || K.looksLikeError(out))) bad.push({ command: orig.slice(0, 200), error: out.replace(PROBE, "").slice(0, 240) });
    }
    return { unique_forms: seen.size, checked, errors: bad, too_long: tooLong };
  };
  const LINTS = [
    [/^\s*kill\s+@e(\s|$)|^\s*kill\s+@e\[(?![^\]]*(type|tag|name)=)/, "kill @e without type/tag/name kills everything (pets, NPCs, minecarts)"],
    [/^\s*fill\b.*\bdestroy\b/, "fill … destroy drops items everywhere"],
    [/\b(setblock|fill)\b.*\b(water|lava)\b/, "places water/lava — make sure it cannot spill"],
  ];
  /** Everything worth knowing before running a command list — nothing is changed. */
  K.preflight = async (list, args = {}) => {
    const targets = K.targetsFromCommands(list);
    const box = targets.length ? K.unionBox(targets) : null;
    const rep = { commands: list.length, box: box ? `${box[0].join(",")} → ${box[1].join(",")}` : "no fill/setblock with absolute coordinates", volume: box ? K.volOf(box) : 0 };
    const z = K.zoneGuard(targets, args.allow_protected);
    rep.zones = z ? "BLOCKED: " + z : "ok";
    const bigFills = targets.filter((t) => K.volOf([t.lo, t.hi]) > 32768).map((t) => list[t.i].slice(0, 100));
    if (bigFills.length) rep.fill_too_big = bigFills.slice(0, 10);
    rep.syntax = await K.syntaxCheck(list);
    const lint = [];
    for (const c of list) for (const [re, msg] of LINTS) if (re.test(c) && lint.length < 8) lint.push(`${msg}: ${c.slice(0, 100)}`);
    if (lint.length) rep.warnings = lint;
    if (box && K.volOf(box) <= 480000) {
      try {
        const at = await K.dumpBig(box[0], box[1]);
        const final = new Map();                                  // the block every voxel ends up as (later commands win)
        const bn = (b) => String(b).replace(/^minecraft:/, "").split(/[[{]/)[0];
        let cap = 0;
        for (const t of targets) {
          if (t.block === "clone") continue;
          for (let x = t.lo[0]; x <= t.hi[0]; x++) for (let y = t.lo[1]; y <= t.hi[1]; y++) for (let zz = t.lo[2]; zz <= t.hi[2]; zz++) { final.set(`${x},${y},${zz}`, bn(t.block)); cap++; }
          if (cap > 1500000) break;
        }
        const hit = {}; let n = 0;
        for (const [k, want] of final) {
          if (want === "air") continue;
          const [x, y, zz] = k.split(",").map(Number);
          const b = at(x, y, zz);
          if (K.isSolid(b, y) && b !== want) { hit[b] = (hit[b] || 0) + 1; n++; }
        }
        rep.overwrites = n ? { blocks: n, types: Object.fromEntries(Object.entries(hit).sort((a, b) => b[1] - a[1]).slice(0, 12)) } : "none (only air / natural ground / the same block)";
      } catch (e) { rep.overwrites = "not checked: " + e.message; }
    }
    if (box) {
      const ps = [];
      for (const n of await K.onlineNamesCached()) {
        if (n === K.BOT || (K.isCrew && K.isCrew(n))) continue;
        try { const p = (await K.playerInfo(n)).position; if (p.x >= box[0][0] - 1 && p.x <= box[1][0] + 2 && p.z >= box[0][2] - 1 && p.z <= box[1][2] + 2 && p.y >= box[0][1] - 2 && p.y <= box[1][1] + 3) ps.push(n); } catch {}
      }
      if (ps.length) rep.players_in_the_way = ps;
    }
    rep.ok = !z && !bigFills.length && !rep.syntax.errors.length && !rep.syntax.too_long.length;
    rep.estimate_seconds = +(list.length * 0.002 + 1).toFixed(1);
    return rep;
  };
}
