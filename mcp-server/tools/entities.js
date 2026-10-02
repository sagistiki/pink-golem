/**
 * Entity health: minecraft_entities — a census of the loaded entities, piles of identical copies, and "ghosts" (old
 * incarnations of an app's object left behind), with a dry-run-first remover.
 *
 * Leaks it was made for: a respawn loop that piled thousands of identical text_displays on one spot; a board that
 * stacked a new label on every restart; an app whose uuid-only cleanup missed the old body of a vehicle when its chunk
 * dropped below full loading, so a second body appeared next to the live one. The scan is cu.sc census() →
 * cu.data/census_<id>.json; only LOADED chunks are seen (nobody near = not counted).
 *
 * Ghosts rely on a tagging convention (skill/pinkgolem/reference/entities.md): tag everything an app spawns with the
 * app tag and the object's own tag (bus, bus_5) AND an incarnation tag (bus_i<n>: a new n every time that object is
 * spawned again) or a generation tag (bus_g<n> / _gen<n> / _run<n>: one n per app run). One object carrying two
 * incarnations, or one app with two generations alive, means one of them is a leftover. Other numbered tags (object
 * ids like car_12) are never compared with each other.
 */
import fs from "node:fs";
import path from "node:path";

const vec = { type: "array", items: { type: "number" }, minItems: 3, maxItems: 3, description: "[x, y, z]" };
// any numbered tag (object ids too: flag_123, car_12) — not a "family" name
const NUMTAG = /^(.*?[_-]?)(\d{2,})$/;
// incarnation tags (one object spawned again) and generation tags (one app run) — the only tags compared for ghosts.
// Object ids (flag_8795, car_12) are separate things, never ghosts of each other.
const INCTAG = /^(.*?_i)(\d+)$/;
const GENTAG = /^(.*?(?:_g|_gen_?|_run_?))(\d+)$/;

export const tools = [
  {
    name: "minecraft_entities",
    description: "Entity health check for display / interaction / armor-stand / mannequin / marker entities (all:true = every non-player entity). action census (default): counts by type and by family (first non-numeric tag) with their x/z span, plus duplicates and ghosts | duplicates: piles of identical copies (same type + tags + position + what they show: item model, dye, text, block, transformation); fix:true keeps one of each pile and removes the rest | ghosts: one owner (its non-numeric tags) carrying 2+ incarnation/generation tags of one family (<app>_i<n>, <app>_g<n>, _gen<n>, _run<n> — e.g. bus_5 with bus_i43 AND bus_i76) = an old copy left behind, typically after a chunk unload; tag the groups your apps spawn this way so ghosts can be found | remove: tags:[...] (entities carrying ALL of them) or uuids:[...], a dry run unless confirm:true (max 5000). Area: every loaded chunk, or pos/player + radius (default 64, max 512). Only LOADED chunks are seen. Needs the cu app's census() (python3 pinkgolem.py apps add cu).",
    inputSchema: { type: "object", properties: {
      action: { type: "string", enum: ["census", "duplicates", "ghosts", "remove"] }, all: { type: "boolean" },
      pos: vec, player: { type: "string" }, radius: { type: "number" }, fix: { type: "boolean" },
      tags: { type: "array", items: { type: "string" } }, uuids: { type: "array", items: { type: "string" } }, confirm: { type: "boolean" } } },
  },
];

export function handlers(K) {
  const num = (out) => String(out).replace(/^\s*=\s*/, "").replace(/\s*\(.*$/, "").trim();
  const P = (e) => `${Math.round(e.x)} ${Math.round(e.y)} ${Math.round(e.z)}`;
  const fam = (e) => e.tags.find((t) => !NUMTAG.test(t)) || e.tags[0] || "(no tag)";

  async function scan(args) {
    const id = `c${Date.now().toString(36)}`;
    let cx = 0, cz = 0, r = 0;
    if (args.pos) [cx, , cz] = K.V(args.pos);
    else if (args.player) { const p = await K.playerInfo(args.player); cx = p.position.x; cz = p.position.z; }
    if (args.pos || args.player) r = Math.min(Math.max(Number(args.radius ?? 64), 4), 512);
    fs.mkdirSync(K.P.CU_DATA, { recursive: true });
    const out = await K.inApp("cu", `census('${id}', '${args.all ? "all" : "deco"}', ${Math.round(cx)}, ${Math.round(cz)}, ${r})`);
    const f = path.join(K.P.CU_DATA, `census_${id}.json`);
    if (!fs.existsSync(f))
      throw new Error(`census failed: ${String(out).slice(0, 200)} — if census() is unknown, update the cu app: python3 pinkgolem.py apps add cu`);
    const rows = K.readJSON(f, []).map(([type, uuid, tags, x, y, z, sig]) => ({ type, uuid, tags: tags || [], x, y, z, sig: sig || "" }));
    try { fs.unlinkSync(f); } catch {}
    return { rows, area: r ? `within ${r} blocks of ${Math.round(cx)},${Math.round(cz)}` : "every loaded chunk" };
  }
  /** cu.sc census_rm(): removes the listed uuids (never players); returns how many it found */
  async function removeUuids(uuids) {
    const id = `r${Date.now().toString(36)}`;
    fs.writeFileSync(path.join(K.P.CU_DATA, `census_rm_${id}.json`), JSON.stringify(uuids));
    return num(await K.inApp("cu", `census_rm('${id}')`));
  }
  function dupGroups(rows) {
    const g = new Map();
    for (const e of rows) {
      const k = [e.type, [...e.tags].sort().join(","), e.x.toFixed(2), e.y.toFixed(2), e.z.toFixed(2), e.sig].join("|");
      if (!g.has(k)) g.set(k, []);
      g.get(k).push(e);
    }
    return [...g.values()].filter((l) => l.length > 1).sort((a, b) => b.length - a.length);
  }
  /** one owner carrying 2+ values of one incarnation / generation family. The owner of an incarnation is the object
   *  (every other tag, ids included); the owner of a generation is the app (the tags that don't end in a number). */
  function ghostGroups(rows) {
    const g = new Map();
    for (const e of rows) {
      const objectOwner = e.tags.filter((t) => !INCTAG.test(t) && !GENTAG.test(t)).sort().join(",");
      const appOwner = e.tags.filter((t) => !/\d$/.test(t)).sort().join(",");
      for (const t of e.tags) {
        const mi = t.match(INCTAG), mg = mi ? null : t.match(GENTAG), m = mi || mg;
        if (!m) continue;
        const owner = mi ? objectOwner : appOwner;
        const k = `${owner}|${m[1]}`;
        if (!g.has(k)) g.set(k, new Map());
        const v = g.get(k);
        if (!v.has(t)) v.set(t, []);
        v.get(t).push(e);
      }
    }
    const out = [];
    for (const [k, v] of g) {
      if (v.size < 2) continue;
      const [owner, prefix] = k.split("|");
      const inc = [...v.entries()].map(([tag, l]) => ({ tag, n: l.length, at: P(l[0]) }))
        .sort((a, b) => Number(b.tag.match(/\d+$/)[0]) - Number(a.tag.match(/\d+$/)[0]));
      out.push({ owner: owner || "(no other tags)", family: prefix + "*", incarnations: inc });
    }
    return out;
  }

  async function entities(args) {
    const action = args.action || "census";
    if (action === "remove") {
      const want = args.tags || [];
      if (!want.length && !args.uuids?.length) throw new Error("remove needs tags:[...] (entities carrying ALL of them) or uuids:[...]");
      const { rows, area } = await scan({ ...args, all: true });
      const hit = args.uuids?.length ? rows.filter((e) => args.uuids.includes(e.uuid)) : rows.filter((e) => want.every((t) => e.tags.includes(t)));
      if (!args.confirm) return `DRY RUN (${area}): would remove ${hit.length} loaded entities (${[...new Set(hit.map((e) => e.type))].join(", ") || "none"})` +
        `${hit.length ? `, e.g. ${hit.slice(0, 5).map((e) => `${e.type} [${e.tags.join(",")}] @ ${P(e)}`).join(" | ")}` : ""}. Pass confirm:true to remove them.`;
      if (hit.length > 5000) throw new Error(`${hit.length} entities — refusing more than 5000 in one go`);
      return `removed ${await removeUuids(hit.map((e) => e.uuid))} of ${hit.length} matching entities`;
    }
    const { rows, area } = await scan(args);
    const L = [`ENTITY CENSUS · ${area} · ${rows.length} ${args.all ? "entities" : "display/interaction/armor-stand/mannequin/marker entities"} (loaded chunks only: areas nobody is near are not seen)`];
    const dups = dupGroups(rows), ghosts = ghostGroups(rows);
    if (action === "census") {
      const byType = {};
      for (const e of rows) byType[e.type] = (byType[e.type] || 0) + 1;
      L.push("by type: " + (Object.entries(byType).sort((a, b) => b[1] - a[1]).map(([t, n]) => `${t} ${n}`).join(", ") || "none"));
      const byFam = new Map();
      for (const e of rows) { const f = fam(e); if (!byFam.has(f)) byFam.set(f, []); byFam.get(f).push(e); }
      L.push(`families (first non-numbered tag), biggest ${Math.min(25, byFam.size)} of ${byFam.size}:`);
      for (const [f, l] of [...byFam.entries()].sort((a, b) => b[1].length - a[1].length).slice(0, 25)) {
        const xs = l.map((e) => e.x), zs = l.map((e) => e.z);
        L.push(`  ${f}: ${l.length} (${[...new Set(l.map((e) => e.type))].join("/")}) x ${Math.round(Math.min(...xs))}..${Math.round(Math.max(...xs))} z ${Math.round(Math.min(...zs))}..${Math.round(Math.max(...zs))}`);
      }
    }
    if (action !== "ghosts") {
      const extra = dups.reduce((a, l) => a + l.length - 1, 0);
      L.push(dups.length ? `DUPLICATES: ${dups.length} piles, ${extra} extra copies (same type + tags + position + what they show):` : "duplicates: none");
      for (const l of dups.slice(0, 15)) L.push(`  ${l.length}× ${l[0].type} [${l[0].tags.join(",")}] @ ${P(l[0])}  ${l[0].sig.slice(0, 70)}`);
      if (dups.length && args.fix) {
        const n = await removeUuids(dups.flatMap((l) => l.slice(1).map((e) => e.uuid)));
        L.push(`  fix: removed ${n} extra copies (one of each pile kept). The app that spawns them still leaks — fix its spawn check.`);
      } else if (dups.length) L.push("  (fix:true keeps one of each pile and removes the rest; then fix the app's spawn check)");
    }
    if (action !== "duplicates") {
      L.push(ghosts.length ? `POSSIBLE GHOSTS: ${ghosts.length} owners carry 2+ incarnations of one tag family (newest first; the older ones are usually leftovers — ask the app which one is live before removing):`
        : "ghosts: none (no owner carries two incarnation tags)");
      for (const g of ghosts.slice(0, 15)) L.push(`  [${g.owner}] ${g.family}: ${g.incarnations.map((i) => `${i.tag} ×${i.n} @ ${i.at}`).join("  |  ")}`);
      if (ghosts.length) L.push("  remove one: action:'remove' tags:['<incarnation tag>'] (dry run first, then confirm:true)");
    }
    return L.join("\n");
  }

  return {
    async minecraft_entities(args) {
      return K.text(await entities(args));
    },
  };
}
