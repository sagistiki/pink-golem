/**
 * safety — the guard rails that make careless builds recoverable:
 * protected zones, the overwrite guard, automatic undo snapshots, auto-zones for finished builds, and verification
 * (what the commands should have placed vs what the world has now).
 */
import fs from "node:fs";
import path from "node:path";

export function install(K) {
  const N = "(-?\\d+(?:\\.\\d+)?)";

  /** Boxes that commands would change: fill / setblock / clone destinations with absolute coordinates. */
  K.targetsFromCommands = (list) => {
    const reFill = new RegExp(`\\bfill\\s+${N}\\s+${N}\\s+${N}\\s+${N}\\s+${N}\\s+${N}\\s+(\\S+)`);
    const reSet = new RegExp(`\\bsetblock\\s+${N}\\s+${N}\\s+${N}\\s+(\\S+)`);
    const reClone = new RegExp(`\\bclone\\s+${N}\\s+${N}\\s+${N}\\s+${N}\\s+${N}\\s+${N}\\s+${N}\\s+${N}\\s+${N}`);
    const out = [];
    list.forEach((c, i) => {
      let m;
      if ((m = reFill.exec(c))) {
        const a = [+m[1], +m[2], +m[3]].map(Math.floor), b = [+m[4], +m[5], +m[6]].map(Math.floor);
        const [lo, hi] = K.sortBox(a, b);
        out.push({ i, lo, hi, block: m[7] });
      } else if ((m = reSet.exec(c))) {
        const a = [+m[1], +m[2], +m[3]].map(Math.floor);
        out.push({ i, lo: a, hi: a, block: m[4] });
      } else if ((m = reClone.exec(c))) {
        const f = [+m[1], +m[2], +m[3]], t = [+m[4], +m[5], +m[6]], d = [+m[7], +m[8], +m[9]].map(Math.floor);
        out.push({ i, lo: d, hi: d.map((v, k) => v + Math.abs(t[k] - f[k])), block: "clone" });
      }
    });
    return out;
  };
  /** Crew only: summon commands with absolute coordinates count as work spots, so NPC / decoration jobs still get
   *  builders on site. Never used for undo, zones or verification. */
  K.summonWorkTargets = (list) => {
    const re = new RegExp(`\\bsummon\\s+\\S+\\s+${N}\\s+${N}\\s+${N}`);
    const out = [];
    list.forEach((c, i) => {
      const m = re.exec(c);
      if (m) { const a = [+m[1], +m[2], +m[3]].map(Math.floor); out.push({ i, lo: a, hi: a, block: null }); }
    });
    return out;
  };
  /** commands / commands_file / commands_files → one list. Files: JSON array, or one command per line (# = comment). */
  K.readCommandArgs = (args) => {
    let list = (args.commands || (args.command ? [args.command] : [])).slice();
    for (const cf of [args.commands_file, ...(args.commands_files || [])].filter(Boolean)) {
      const raw = fs.readFileSync(K.safePath(cf), "utf8");
      list = list.concat(raw.trim().startsWith("[") ? JSON.parse(raw) : raw.split(/\r?\n/).map((l) => l.trim()).filter((l) => l && !l.startsWith("#")));
    }
    return list;
  };

  // ── protected zones
  const WORK_GRACE_H = 6;
  K.WORK_GRACE_H = WORK_GRACE_H;
  K.loadZones = () => K.readJSON(K.P.ZONES, []);
  K.zoneGuard = (targets, allow) => {
    if (allow || !targets.length) return null;
    // the bot's own auto-registered builds don't block it; a zone it is building FOR someone stays open while it works there
    const working = (z) => z.builder === K.BOT && z.touched && Date.now() - Date.parse(z.touched) < (z.grace_hours ?? WORK_GRACE_H) * 3600e3;
    const hit = K.loadZones().filter((z) => !(z.auto && z.owner === K.BOT) && !working(z)).filter((z) => targets.some((t) =>
      t.lo[0] <= z.hi[0] && t.hi[0] >= z.lo[0] && t.lo[1] <= z.hi[1] && t.hi[1] >= z.lo[1] && t.lo[2] <= z.hi[2] && t.hi[2] >= z.lo[2]));
    if (!hit.length) return null;
    return `PROTECTED — nothing was changed. This touches protected zone(s): ${hit.map((z) => `"${z.name}" (owner ${z.owner}${z.builder ? `, builder ${z.builder}` : ""}, ${z.lo.join(",")} → ${z.hi.join(",")})`).join("; ")}. Only edit it if its owner asked you to, then pass allow_protected:true — or, for a job you are doing for the owner over several phases, minecraft_zones action:"claim" name:<zone> once (then every phase goes through for ${WORK_GRACE_H} h).`;
  };

  /** Refuse to overwrite existing builds. targets: list of {lo,hi}. null if OK, else a message. */
  K.overwriteGuard = async (targets, allow) => {
    if (allow || !targets.length) return null;
    const [lo, hi] = K.unionBox(targets);
    if (K.volOf([lo, hi]) > 120000) return null; // too big to check cheaply — use minecraft_vision mode:check first
    const occ = await K.occupiedIn(lo, hi);
    const hits = occ.filter(([x, y, z]) => targets.some((t) => x >= t.lo[0] && x <= t.hi[0] && y >= t.lo[1] && y <= t.hi[1] && z >= t.lo[2] && z <= t.hi[2]));
    if (!hits.length) return null;
    const counts = {};
    for (const h of hits) counts[h[3]] = (counts[h[3]] || 0) + 1;
    return `STOPPED — nothing was built. ${hits.length} existing block(s) are in the way: ${Object.entries(counts).map(([n, c]) => `${n}×${c}`).join(", ")}. e.g. ${hits.slice(0, 8).map((h) => h.slice(0, 3).join(" ")).join(" | ")}. Look with minecraft_vision, move the build, or pass allow_overwrite:true if you really mean to change this structure.`;
  };

  // ── automatic undo (snapshots through the cu app). Big boxes are split into slabs of ≤250k blocks, up to 4M per build.
  const SNAP_PART = 250000, SNAP_MAX = 4000000;
  const slabs = (box) => {
    const [lo, hi] = box;
    const ax = [0, 1, 2].reduce((a, i) => (hi[i] - lo[i] > hi[a] - lo[a] ? i : a), 0);
    const area = K.volOf(box) / (hi[ax] - lo[ax] + 1);
    const step = Math.max(1, Math.floor(SNAP_PART / area));
    const out = [];
    for (let a = lo[ax]; a <= hi[ax]; a += step) { const l = lo.slice(), h = hi.slice(); l[ax] = a; h[ax] = Math.min(hi[ax], a + step - 1); out.push([l, h]); }
    return out;
  };
  K.snapshotFor = async (targets, label) => {
    if (!targets.length) return null;
    const box = K.unionBox(targets);
    const vol = K.volOf(box);
    if (vol > SNAP_MAX) return { skipped: `no undo snapshot (box is ${vol} blocks, max ${SNAP_MAX})` };
    const id = "u" + Date.now().toString(36);
    const parts = [];
    for (const [k, [l, h]] of slabs(box).entries()) {
      const pid = `${id}_${k}`;
      const r = await K.inApp("cu", `snap('${pid}', ${l.join(",")}, ${h.join(",")})`);
      if (!/saved/.test(r)) { for (const q of parts) await K.inApp("cu", `unsnap('${q}')`).catch(() => {}); return { skipped: `undo snapshot failed: ${r.slice(0, 160)}` }; }
      parts.push(pid);
    }
    const drop = [];
    await K.updateJSON(K.P.UNDO, [], (stack) => {
      stack.push({ id, parts, owner: K.BOT, label: String(label || "build").slice(0, 80), lo: box[0], hi: box[1], time: new Date().toISOString() });
      while (stack.length > 30) drop.push(stack.shift());
    });
    for (const old of drop) for (const q of old.parts || [old.id]) await K.inApp("cu", `unsnap('${q}')`).catch(() => {});
    return { id, blocks: vol, parts: parts.length };
  };

  // ── every finished build becomes a protected zone owned by the bot that built it
  K.autoZone = async (label, box, blocks) => {
    if (!box) return null;
    await K.updateJSON(K.P.ZONES, [], (zs) => {
      for (const z of zs) if (z.builder === K.BOT && box[0].every((v, i) => v <= z.hi[i]) && box[1].every((v, i) => v >= z.lo[i])) z.touched = new Date().toISOString();
    }).catch(() => {});
    if ((blocks ?? K.volOf(box)) < 300) return null;
    let result = null;
    await K.updateJSON(K.P.ZONES, [], (zs) => {
      const inside = zs.find((z) => box[0].every((v, i) => v >= z.lo[i]) && box[1].every((v, i) => v <= z.hi[i]));
      if (inside) { result = { inside: inside.name }; return; }
      const mine = zs.find((z) => z.auto && z.owner === K.BOT && z.lo.every((v, i) => v <= box[1][i] + 2) && z.hi.every((v, i) => v >= box[0][i] - 2));
      if (mine) {
        mine.lo = mine.lo.map((v, i) => Math.min(v, box[0][i])); mine.hi = mine.hi.map((v, i) => Math.max(v, box[1][i]));
        mine.updated = new Date().toISOString(); result = { grew: mine.name }; return;
      }
      const z = { name: `${K.BOT}: ${String(label || "build").slice(0, 40)}`, owner: K.BOT, builder: K.BOT, auto: true, lo: box[0], hi: box[1],
        note: `built by ${K.BOT} ${new Date().toISOString().slice(0, 16)}`, created: new Date().toISOString() };
      zs.push(z); result = { added: z.name };
    });
    return result;
  };

  // ── verification: expected blocks from the commands vs the world
  const baseName = (b) => String(b).replace(/^minecraft:/, "").split(/[[{]/)[0];
  const VERIFY_SKIP = /^(fire|soul_fire|piston_head|moving_piston)$/;
  K.expectedFromCommands = (list, cap = 300000) => {
    const exp = new Map();
    const I = "(-?\\d+)";
    const reFill = new RegExp(`^\\s*fill\\s+${I}\\s+${I}\\s+${I}\\s+${I}\\s+${I}\\s+${I}\\s+(\\S+)(?:\\s+(\\w+)(?:\\s+(\\S+))?)?\\s*$`);
    const reSet = new RegExp(`^\\s*setblock\\s+${I}\\s+${I}\\s+${I}\\s+(\\S+)(?:\\s+(\\w+))?`);
    let total = 0;
    for (const c of list) {
      let m;
      if ((m = reSet.exec(c))) {
        if (m[5] === "keep") continue;
        exp.set(`${m[1]},${m[2]},${m[3]}`, baseName(m[4])); total++;
      } else if ((m = reFill.exec(c))) {
        const mode = m[8] || "replace";
        if (mode === "keep" || (mode === "replace" && m[9])) continue;
        const a = [+m[1], +m[2], +m[3]], b = [+m[4], +m[5], +m[6]];
        const [lo, hi] = K.sortBox(a, b);
        const name = baseName(m[7]);
        for (let x = lo[0]; x <= hi[0]; x++) for (let y = lo[1]; y <= hi[1]; y++) for (let z = lo[2]; z <= hi[2]; z++) {
          const edge = x === lo[0] || x === hi[0] || y === lo[1] || y === hi[1] || z === lo[2] || z === hi[2];
          if (mode === "outline" && !edge) continue;
          exp.set(`${x},${y},${z}`, mode === "hollow" && !edge ? "air" : name); total++;
        }
      }
      if (total > cap * 4) break;
    }
    let pts = [...exp.entries()].filter(([, n]) => !VERIFY_SKIP.test(n));
    if (pts.length > cap) { const k = Math.ceil(pts.length / cap); pts = pts.filter((_, i) => i % k === 0); }
    return pts.map(([key, n]) => { const [x, y, z] = key.split(",").map(Number); return [x, y, z, n]; });
  };
  K.verifyBuild = async (list, box) => {
    const pts = K.expectedFromCommands(list);
    if (!pts.length) return { checked: 0 };
    const id = "v" + Date.now().toString(36) + Math.floor(Math.random() * 1e4);
    fs.mkdirSync(K.P.CU_DATA, { recursive: true });
    const CH = 25000;
    const agg = { checked: 0, mismatches: 0, by_type: {}, examples: [] };
    for (let k = 0; k * CH < pts.length; k++) {
      fs.writeFileSync(path.join(K.P.CU_DATA, `verify_${id}_${k}.json`), JSON.stringify({ pts: pts.slice(k * CH, (k + 1) * CH) }));
      const r = await K.inApp("cu", `verify('${id}', ${k})`);
      const m = /=\s*(\{[\s\S]*\})/.exec(r);
      if (!m) { agg.error = r.slice(0, 200); break; }
      const num = (key) => +((new RegExp(`${key}: (\\d+)`).exec(m[1]) || [0, 0])[1]);
      agg.checked += num("checked"); agg.mismatches += num("mismatches");
      const bt = /by_type: \{([^}]*)\}/.exec(m[1]);
      if (bt && bt[1].trim()) for (const part of bt[1].split(",")) { const [key, n] = part.split(":").map((q) => q.trim()); if (key) agg.by_type[key] = (agg.by_type[key] || 0) + Number(n); }
      const ex = /examples: \[([^\]]*)\]/.exec(m[1]);
      if (ex && ex[1].trim() && agg.examples.length < 25) agg.examples.push(...ex[1].split(",").map((q) => q.trim()).slice(0, 25 - agg.examples.length));
    }
    // stray water / lava inside the build box
    const wet = pts.filter((p) => p[3] === "water" || p[3] === "lava").map((p) => `${p[0]},${p[1]},${p[2]}`);
    if (box && K.volOf(box) <= 400000) {
      fs.writeFileSync(path.join(K.P.CU_DATA, `verify_${id}_wet.json`), JSON.stringify({ pts: wet }));
      const r = await K.inApp("cu", `vfluid('${id}', ${box[0].join(",")}, ${box[1].join(",")})`);
      const m = /stray_fluids: (\d+)/.exec(r);
      const fl = /flowing: (\d+)/.exec(r);
      if (m) { agg.stray_fluids = +m[1]; const ex = /examples: \[([^\]]*)\]/.exec(r); if (+m[1] && ex) agg.fluid_examples = ex[1]; }
      if (fl && +fl[1]) agg.flowing_water = `${fl[1]} flowing blocks (fine for fountains/waterfalls; a leak if they run outside the basin)`;
      try { fs.unlinkSync(path.join(K.P.CU_DATA, `verify_${id}_wet.json`)); } catch {}
    }
    agg.ok = agg.mismatches === 0 && !agg.stray_fluids;
    agg.by_type = Object.fromEntries(Object.entries(agg.by_type).sort((a, b) => b[1] - a[1]).slice(0, 15));
    if (agg.mismatches) agg.hint = "grass_block>dirt (grass under a placed block turns to dirt) and 'Could not set' on air are harmless.";
    return agg;
  };
}
