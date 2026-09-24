/**
 * Memory of the world and its people: minecraft_map, minecraft_zones, minecraft_people, minecraft_notes,
 * minecraft_cleanup. Everything is stored under data/ (plain JSON / Markdown, safe to edit by hand when no AI runs).
 */
import fs from "node:fs";

const vec = { type: "array", items: { type: "number" }, minItems: 3, maxItems: 3, description: "[x, y, z]" };

export const tools = [
  {
    name: "minecraft_map",
    description: "The world map — an index of every build (bounds, entrances, warps, owner, builder, notes), merged with the protected zones. action: list | get (name: fuzzy, any language) | near (name or pos/player, radius) | at (pos or player: which build is here) | find_space (size:[w,d], near:<build> or pos/player, radius ≤120, margin: free buildable ground nobody uses, nearest first) | pov (player or pos+yaw+pitch: a far first-person picture of what they see + which builds are in view and under the crosshair — use it for 'build over there') | add / update (id or name + fields: name, aliases, from/to, entrances [[x,y,z,'note'],...], warps, owner, builder, kind, notes) | remove (id). Add every finished build.",
    inputSchema: { type: "object", properties: { action: { type: "string", enum: ["list", "get", "near", "at", "find_space", "pov", "add", "update", "remove"] }, name: { type: "string" }, id: { type: "string" },
      pos: vec, player: { type: "string" }, radius: { type: "number" }, near: { type: "string" }, size: { type: "array", items: { type: "number" }, description: "[width_x, depth_z]" }, margin: { type: "number" }, count: { type: "number" },
      yaw: { type: "number" }, pitch: { type: "number" }, fov: { type: "number" }, distance: { type: "number" }, width: { type: "number" }, height: { type: "number" },
      from: vec, to: vec, aliases: { type: "array", items: { type: "string" } }, entrances: { type: "array", items: { type: "array" } }, warps: { type: "array", items: { type: "string" } }, owner: { type: "string" }, builder: { type: "string" }, kind: { type: "string" }, notes: { type: "string" } }, required: ["action"] },
  },
  {
    name: "minecraft_zones",
    description: "Protected zones (other people's builds). Build tools refuse to change blocks inside them unless allow_protected:true. Your finished builds become zones automatically. action: list | add (name, owner, from, to, note, builder) | claim (name[, hours]) = 'I'm building this for its owner' — your phases pass for 6 h after your last build there | release | remove (name) | show (glowing outline in game for 20 s).",
    inputSchema: { type: "object", properties: { action: { type: "string", enum: ["list", "add", "claim", "release", "remove", "show"] }, name: { type: "string" }, owner: { type: "string" }, builder: { type: "string" }, hours: { type: "number" }, from: vec, to: vec, note: { type: "string" } }, required: ["action"] },
  },
  {
    name: "minecraft_people",
    description: "Memory of the people on the server: Minecraft name, roles (admin…), what they like to build, their style, pets, notes. Use it to greet people right and to suggest builds that fit them. action: list | get (name) | set (name + fields to merge: mc, aliases, roles, likes, style, uuid) | note (name, text) | pets (mobs tamed to them in loaded chunks) | suggest (their likes/style + what they own on the map).",
    inputSchema: { type: "object", properties: { action: { type: "string", enum: ["list", "get", "set", "note", "pets", "suggest"] }, name: { type: "string" }, mc: { type: "string" }, aliases: { type: "array", items: { type: "string" } },
      roles: { type: "array", items: { type: "string" } }, likes: { type: "array", items: { type: "string" } }, style: { type: "string" }, uuid: { type: "string" }, text: { type: "string" } }, required: ["action"] },
  },
  {
    name: "minecraft_notes",
    description: "Your learning journal (data/LEARNINGS.md, append-only, shared by every AI that uses this server). action:read at the start of a session (latest lines); action:add one line after every build (what + where + how to get in) and one line per lesson learned (section: build | lesson | bug). Never rewrite the file by hand.",
    inputSchema: { type: "object", properties: { action: { type: "string", enum: ["add", "read"] }, text: { type: "string" }, section: { type: "string" }, lines: { type: "number" } }, required: ["action"] },
  },
  {
    name: "minecraft_cleanup",
    description: "Count or remove clutter entities: dropped items, xp orbs, arrows, stray firework rockets, falling blocks. Optional area (from/to or pos+radius). dry_run:true only counts.",
    inputSchema: { type: "object", properties: { types: { type: "array", items: { type: "string" } }, from: vec, to: vec, pos: vec, radius: { type: "number" }, dry_run: { type: "boolean" } } },
  },
];

export function handlers(K) {
  const { WM } = K;
  const loadPeople = () => K.readJSON(K.P.PEOPLE, []);
  const findPerson = (ps, q) => {
    const n = String(q || "").toLowerCase().trim();
    return ps.find((p) => [p.name, p.mc, ...(p.aliases || [])].filter(Boolean).some((s) => String(s).toLowerCase() === n)) ||
      ps.find((p) => [p.name, p.mc, ...(p.aliases || [])].filter(Boolean).some((s) => String(s).toLowerCase().includes(n) && n.length > 1));
  };

  return {
    async minecraft_map(args) {
      const a = args.action || "list";
      const E = K.mapEntries();
      const short = (e) => ({ id: e.id, name: e.name, owner: e.owner, ...(e.builder ? { builder: e.builder } : {}), box: e.lo ? `${e.lo.join(",")} → ${e.hi.join(",")}` : null, ...(e.warps?.length ? { warps: e.warps } : {}), ...(e.entrances?.length ? { entrance: e.entrances[0].pos } : {}) });
      const refPos = async () => { if (args.pos) return K.V(args.pos); const p = await K.playerInfo(args.player || (await K.firstRealPlayer()) || K.BOT); return [p.position.x, p.position.y, p.position.z]; };
      if (a === "list") return K.text({ builds: E.map(short), count: E.length });
      if (a === "get") {
        const hits = WM.lookup(E, args.name || args.id);
        if (!hits.length) return K.text(`nothing called "${args.name || args.id}" — action:list shows all`);
        const e = hits[0];
        return K.text({ ...e, nearby: WM.near(E, e, 40, e.id).slice(0, 6).map((n) => `${n.name}: ${n.gap} blocks ${n.direction}`), other_matches: hits.slice(1, 4).map((h) => h.name) });
      }
      if (a === "near") {
        let ref, label;
        if (args.name) { ref = WM.lookup(E, args.name)[0]; if (!ref) throw new Error(`no build called "${args.name}"`); label = ref.name; }
        else { ref = (await refPos()).map(Math.floor); label = ref.join(" "); }
        return K.text({ around: label, within: args.radius ?? 60, builds: WM.near(E, ref, args.radius ?? 60, ref.id).map((n) => ({ name: n.name, gap: n.gap, direction: n.direction, owner: n.owner, center: n.center })) });
      }
      if (a === "at") {
        const p = await refPos();
        const here = WM.at(E, p);
        return K.text({ pos: p.map((v) => +v.toFixed(1)), inside: here.map(short), nearest: here.length ? undefined : WM.near(E, p.map(Math.floor), 60).slice(0, 4).map((n) => `${n.name}: ${n.gap} ${n.direction}`) });
      }
      if (a === "find_space") return K.text(await K.findSpace(args));
      if (a === "pov") return await K.povShot(args);
      if (a === "add" || a === "update") {
        const id = String(args.id || args.name || "").trim();
        if (!id) throw new Error("give id or name");
        let saved = null;
        await K.updateJSON(K.P.INDEX, [], (all) => {
          let e = all.find((q) => q.id === id) || (a === "update" ? WM.lookup(all, id)[0] : null);
          if (!e) {
            if (a === "update") return;
            e = { id: id.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, "_").slice(0, 40), name: args.name || id, aliases: [], kind: "build", owner: args.owner || "?", builder: args.builder || K.BOT, entrances: [], warps: [], notes: "", created: new Date().toISOString() };
            all.push(e);
          }
          if (args.name && a === "update") e.name = args.name;
          for (const k of ["owner", "builder", "kind", "notes"]) if (args[k] != null) e[k] = args[k];
          if (args.aliases) e.aliases = [...new Set([...(e.aliases || []), ...args.aliases])];
          if (args.warps) e.warps = [...new Set([...(e.warps || []), ...args.warps])];
          if (args.from && args.to) [e.lo, e.hi] = K.sortBox(K.V(args.from), K.V(args.to));
          if (args.entrances) e.entrances = args.entrances.map((x) => (Array.isArray(x) ? { pos: x.slice(0, 3).map(Number), note: String(x[3] ?? "") } : x));
          e.updated = new Date().toISOString();
          saved = e;
        });
        if (!saved) throw new Error(`no build "${id}" to update`);
        return K.text({ [a === "add" ? "added" : "updated"]: saved });
      }
      if (a === "remove") {
        let gone = null;
        await K.updateJSON(K.P.INDEX, [], (all) => { const i = all.findIndex((q) => q.id === args.id || q.name === args.name); if (i >= 0) gone = all.splice(i, 1)[0]; });
        return K.text(gone ? { removed: gone.name } : "not in the index (zones are removed with minecraft_zones)");
      }
      throw new Error("unknown action");
    },

    async minecraft_zones(args) {
      const zs = K.loadZones();
      if (args.action === "list") return K.text(zs.length ? zs : "No protected zones.");
      if (args.action === "add") {
        if (!args.name || !args.from || !args.to) throw new Error("add needs name, from, to (and owner)");
        const [lo, hi] = K.sortBox(K.V(args.from), K.V(args.to));
        const z = { name: args.name, owner: args.owner || "?", lo, hi, note: args.note || "", ...(args.builder ? { builder: args.builder, touched: new Date().toISOString() } : {}) };
        await K.updateJSON(K.P.ZONES, [], (all) => [...all.filter((q) => q.name !== z.name), z]);
        return K.text({ added: z });
      }
      if (args.action === "claim" || args.action === "release") {
        let found = null;
        await K.updateJSON(K.P.ZONES, [], (all) => {
          const best = WM.lookup(all.map((z) => ({ id: z.name, name: z.name })), args.name)[0];
          const q = all.find((z) => z.name === args.name) || (best && all.find((z) => z.name === best.name));
          if (!q) return;
          if (args.action === "claim") { q.builder = K.BOT; q.touched = new Date().toISOString(); if (args.hours) q.grace_hours = Number(args.hours); }
          else delete q.touched;
          found = { name: q.name, owner: q.owner, builder: q.builder, touched: q.touched || null, grace_hours: q.grace_hours ?? K.WORK_GRACE_H };
        });
        if (!found) throw new Error(`no zone named ${args.name}`);
        return K.text({ [args.action === "claim" ? "claimed" : "released"]: found, note: args.action === "claim" ? "your builds inside it pass the zone guard while you keep working (each build refreshes the timer)" : "the zone blocks you again" });
      }
      if (args.action === "remove") {
        await K.updateJSON(K.P.ZONES, [], (all) => all.filter((q) => q.name !== args.name));
        return K.text(`removed ${args.name}`);
      }
      if (args.action === "show") {
        for (const z of zs.filter((q) => !args.name || q.name === args.name))
          await K.inApp("cu", `show(${z.lo.join(",")}, ${z.hi.join(",")}, ${K.scStr(z.name + " (" + z.owner + ")")}, 20)`).catch(() => {});
        return K.text("shown for 20 s");
      }
      throw new Error("unknown action");
    },

    async minecraft_people(args) {
      const a = args.action || "list";
      const ps = loadPeople();
      if (a === "list") return K.text(ps.length ? ps.map((p) => ({ name: p.name, mc: p.mc, roles: p.roles, likes: (p.likes || []).slice(0, 4) })) : "Nobody recorded yet — add people with action:set as you meet them.");
      const p0 = findPerson(ps, args.name || args.mc);
      if (a === "get") return K.text(p0 || `I don't know "${args.name}" yet — minecraft_people action:set name:... mc:... to add them`);
      if (a === "set" || a === "note") {
        let saved = null;
        await K.updateJSON(K.P.PEOPLE, [], (all) => {
          let p = findPerson(all, args.name || args.mc);
          if (!p) { if (!args.name) return; p = { name: args.name, mc: args.mc || "", aliases: [], roles: [], likes: [], style: "", pets: [], notes: [] }; all.push(p); }
          if (a === "set") {
            for (const k of ["mc", "style", "uuid"]) if (args[k] != null) p[k] = args[k];
            for (const k of ["aliases", "roles", "likes"]) if (args[k]) p[k] = [...new Set([...(p[k] || []), ...args[k]])];
          } else if (args.text) (p.notes = p.notes || []).push(`${new Date().toISOString().slice(0, 10)}: ${String(args.text).slice(0, 300)}`);
          p.updated = new Date().toISOString();
          saved = p;
        });
        if (!saved) throw new Error("give name");
        return K.text({ saved });
      }
      if (!p0) throw new Error(`I don't know "${args.name}"`);
      if (a === "pets") {
        let uuid = p0.uuid;
        if (!uuid && p0.mc) {
          const r = await K.cmd(`data get entity ${p0.mc} UUID`).catch(() => "");
          const m = /\[I;\s*(-?\d+),\s*(-?\d+),\s*(-?\d+),\s*(-?\d+)\]/.exec(r);
          if (m) { uuid = `[I;${m[1]},${m[2]},${m[3]},${m[4]}]`; await K.updateJSON(K.P.PEOPLE, [], (all) => { const q = findPerson(all, p0.name); if (q) q.uuid = uuid; }); }
        }
        if (!uuid) return K.text(`no UUID for ${p0.name} — they need to be online once (or set uuid)`);
        const r = await K.scarpet(`l=[];for(entity_selector('@e[nbt={Owner:${uuid.replace(/\s/g, "")}}]'),p=pos(_);l+=str('%s|%s|%d %d %d',query(_,'type'),query(_,'name'),floor(p:0),floor(p:1),floor(p:2)));join(';',l)`, { raw: true });
        const v = r.value.replace(/^'|'$/g, "");
        const pets = v && !/Error|null/.test(v) ? v.split(";").filter(Boolean).map((q) => { const [type, name, pos] = q.split("|"); return { type, name, pos }; }) : [];
        return K.text({ owner: p0.name, uuid, pets, note: "only loaded chunks are searched (skill script nbt_scan.py reads the whole save)", remembered: p0.pets || [] });
      }
      if (a === "suggest") {
        const theirs = K.mapEntries().filter((e) => [p0.mc, p0.name].filter(Boolean).includes(e.owner) || (p0.mc && e.builder === p0.mc)).map((e) => e.name);
        return K.text({ name: p0.name, mc: p0.mc, roles: p0.roles, likes: p0.likes, style: p0.style, pets: p0.pets, owns_or_built: theirs, notes: (p0.notes || []).slice(-8),
          tip: "Base the idea on their likes/style, place it near what they already own (minecraft_map find_space near:<their build>), and name it in their language." });
      }
      throw new Error("unknown action");
    },

    async minecraft_notes(args) {
      const f = K.P.LEARNINGS;
      if (args.action === "add") {
        if (!args.text) throw new Error("text required");
        const line = await K.withLock(f + ".lock", async () => {
          let s = ""; try { s = fs.readFileSync(f, "utf8"); } catch {}
          const head = "# LEARNINGS — shared, append-only journal (written only through minecraft_notes)\n\n";
          const l = `- ${new Date().toISOString().slice(0, 16).replace("T", " ")} [${K.BOT}]${args.section ? ` (${args.section})` : ""} ${String(args.text).replace(/\n+/g, " ")}\n`;
          fs.appendFileSync(f, (s ? (s.endsWith("\n") ? "" : "\n") : head) + l);   // append only — never rewrites what is there
          return l.trim();
        });
        return K.text({ added: line });
      }
      let s = ""; try { s = fs.readFileSync(f, "utf8"); } catch {}
      const lines = s.split("\n").filter((l) => l.startsWith("- "));
      return K.text(lines.slice(-(args.lines || 30)).join("\n") || "(no notes yet — add one after your first build)");
    },

    async minecraft_cleanup(args) {
      const types = args.types?.length ? args.types : ["item", "experience_orb", "arrow", "spectral_arrow", "firework_rocket", "falling_block"];
      let area = "";
      if (args.from && args.to) { const [lo, hi] = K.sortBox(K.V(args.from), K.V(args.to)); area = `,x=${lo[0]},y=${lo[1]},z=${lo[2]},dx=${hi[0] - lo[0]},dy=${hi[1] - lo[1]},dz=${hi[2] - lo[2]}`; }
      else if (args.pos) { const p = K.V(args.pos); area = `,x=${p[0]},y=${p[1]},z=${p[2]},distance=..${args.radius || 32}`; }
      const out = {};
      for (const t of types) {
        const sel = `@e[type=minecraft:${t.replace(/^minecraft:/, "")}${area}]`;
        const r = args.dry_run ? await K.cmd(`execute if entity ${sel}`) : await K.cmd(`kill ${sel}`);
        const n = +((/(\d+)/.exec(/Test passed, count: (\d+)|Killed (\d+)|(\d+) entities/.exec(r)?.[0] || "") || [0, 0])[1]);
        out[t] = n || (/^Killed [^\d]/.test(r) ? 1 : 0);
      }
      return K.text({ [args.dry_run ? "found" : "removed"]: out, total: Object.values(out).reduce((a, b) => a + b, 0) });
    },
  };
}
