/**
 * Building: minecraft_run_command, minecraft_build, minecraft_build_layers, minecraft_worldedit, minecraft_generate,
 * minecraft_jobs, minecraft_undo, minecraft_verify.
 * Every tool that changes blocks goes through the same rails: zone guard → undo snapshot → run → verify → auto-zone.
 */

const vec = { type: "array", items: { type: "number" }, minItems: 3, maxItems: 3, description: "[x, y, z]" };

export const tools = [
  {
    name: "minecraft_run_command",
    description:
      "Run server commands as the console (op level 4) and get their output — any vanilla or mod command: fill, setblock, clone, summon, give, tp, gamemode, time, weather, effect, execute, data, scoreboard, Carpet's /player, scarpet /script. No leading slash. For generated builds pass commands_file / commands_files (JSON arrays written by a generator into jobs/) with background:true: the build runs as a job with a boss bar, optional helper builders, an undo snapshot, and an automatic check afterwards. Commands that place blocks inside someone's protected zone are refused unless allow_protected:true.",
    inputSchema: {
      type: "object",
      properties: {
        command: { type: "string", description: "A single command" },
        commands: { type: "array", items: { type: "string" }, description: "Several commands, run in order" },
        commands_file: { type: "string", description: "A file inside the ClawdBlock folder, e.g. 'jobs/cottage.json': a JSON array of commands, or one command per line (# = comment)." },
        commands_files: { type: "array", items: { type: "string" }, description: "Several command files run in order as ONE job (one progress bar)" },
        background: { type: "boolean", description: "Run as a background job with a boss bar; returns a job id at once (then minecraft_jobs action:wait). Use for anything over ~300 commands so you can keep talking." },
        label: { type: "string", description: "Name on the progress bar and in the undo list — make it descriptive ('cottage walls')" },
        helpers: { type: "number", description: "Background jobs: bring this many helper builders (0-4) who work around the site and stay between jobs" },
        keep_helpers: { type: "boolean", description: "Keep the helpers after the job (dismiss later with minecraft_helpers)" },
        pace_ms: { type: "number", description: "Pause between commands in ms (0-500) so a build appears gradually. Default 0." },
        swing_every: { type: "number", description: "Make your bot swing its arm every N commands while building. Default off." },
        entrance: { ...vec, description: "After the build, walk (virtually) from this feet position just outside the main door to every room, door and stair, and report problems + dark spots. Give it on the LAST phase of a building." },
        check_access: { type: "boolean", description: "Like entrance, using the entrance stored in the world map for this build" },
        stop_on_error: { type: "boolean", description: "Stop at the first failing command (default false)" },
        undo: { type: "boolean", description: "Default true: undo snapshot of the area first (minecraft_undo reverts it)" },
        verify: { type: "boolean", description: "Compare the world with what the commands should have placed afterwards (default: on for >25 commands)" },
        allow_protected: { type: "boolean", description: "Allow changes inside protected zones (only when the zone's owner asked)" },
        call_tool: { type: "string", description: "Instead of commands: run another minecraft_* tool by name, with its arguments in tool_args. Use when a newer tool isn't in your tool list yet." },
        tool_args: { type: "object", description: "Arguments for call_tool" },
      },
    },
  },
  {
    name: "minecraft_build",
    description:
      "Build a few shapes quickly (fill/setblock/clone; big fills are split automatically). Coordinates are absolute, or offsets from the GROUND block a player stands on with relative_to_player (y=0 = the ground layer, y=1 = first block above). Floors replace the ground block; walls start one above. Refuses to overwrite existing builds unless allow_overwrite. Ops: {op:'fill', from, to, block, mode?: replace|hollow|outline|keep|destroy}, {op:'setblock', pos, block}, {op:'clone', from, to, dest}, {op:'command', command}. Block states in brackets: 'oak_stairs[facing=east]'. For anything bigger than a few dozen shapes, write a generator (skill: scripts/mclib.py) and use minecraft_generate.",
    inputSchema: {
      type: "object",
      properties: {
        operations: { type: "array", items: { type: "object" } },
        relative_to_player: { type: "string" },
        dimension: { type: "string", description: "e.g. minecraft:the_nether (default: overworld or the player's dimension)" },
        label: { type: "string" },
        allow_overwrite: { type: "boolean", description: "Only when you deliberately edit an existing structure" },
        allow_protected: { type: "boolean" },
        undo: { type: "boolean", description: "Default true" },
        entrance: vec,
      },
      required: ["operations"],
    },
  },
  {
    name: "minecraft_build_layers",
    description:
      "Build from ASCII layers like a blueprint. layers[0] is the bottom Y layer; each layer is a list of row strings; row index = +Z (south), character index = +X (east). legend maps each character to a block ('.' or ' ' = leave untouched unless in the legend; map a character to 'air' to clear). Put layers[0] (the floor) at the ground Y so it replaces the ground; walls start one above. Legend letters must be unique ignoring case.",
    inputSchema: {
      type: "object",
      properties: {
        origin: { ...vec, description: "[x,y,z] of the bottom-north-west corner (absolute, or offset if relative_to_player)" },
        relative_to_player: { type: "string" },
        dimension: { type: "string" },
        layers: { type: "array", items: { type: "array", items: { type: "string" } } },
        legend: { type: "object", additionalProperties: { type: "string" } },
        label: { type: "string" },
        allow_overwrite: { type: "boolean" },
        allow_protected: { type: "boolean" },
        undo: { type: "boolean" },
      },
      required: ["origin", "layers", "legend"],
    },
  },
  {
    name: "minecraft_generate",
    description: "Run a Python build generator inside the ClawdBlock folder (e.g. skill/clawdblock/blueprints/cottage.py, or your own in jobs/). Generators use skill/clawdblock/scripts/mclib.py and write command files into jobs/. Returns stdout and the files written. With build:true the files are queued as background jobs (undo, zone guard, verification, auto-zone), helpers join the first one, and entrance/check_access runs on the last one. Pass generator arguments in args (blueprints take --at x,y,z and --facing).",
    inputSchema: { type: "object", properties: {
      script: { type: "string", description: "path relative to the ClawdBlock folder" }, args: { type: "array", items: { type: "string" } },
      build: { type: "boolean", description: "queue the generated files as build jobs (default false = generate only, then minecraft_preview them)" },
      files: { type: "array", items: { type: "string" }, description: "only build these of the generated files (names or globs like cottage-*)" },
      helpers: { type: "number" }, allow_protected: { type: "boolean" }, label: { type: "string" }, entrance: vec, check_access: { type: "boolean" } }, required: ["script"] },
  },
  {
    name: "minecraft_worldedit",
    requires: ["worldedit"],
    description: "Run WorldEdit commands as the bot, WITHOUT the leading slashes, e.g. [\"pos1 10,-61,5\", \"pos2 20,-50,15\", \"set stone\", \"replace dirt grass_block\", \"walls glass\", \"sphere glass 5\", \"hcyl stone 8 20\", \"copy\", \"paste\", \"rotate 90\", \"stack 3 up\", \"undo\"]. Selection, clipboard and history belong to the bot's WorldEdit session. copy/paste are relative to where the bot stands — tp it first. WorldEdit's replies go to the bot, not here: ALWAYS verify with minecraft_inspect or a screenshot. WorldEdit edits are not in minecraft_undo (use its own undo).",
    inputSchema: { type: "object", properties: { commands: { type: "array", items: { type: "string" } }, allow_protected: { type: "boolean" } }, required: ["commands"] },
  },
  {
    name: "minecraft_jobs",
    description: "Background build jobs. action: list | status (id) | wait (id, up to 50 s; returns done/errors/failures and the automatic verification, access check and zone) | cancel (id).",
    inputSchema: { type: "object", properties: { action: { type: "string", enum: ["list", "status", "wait", "cancel"] }, id: { type: "number" }, timeout_seconds: { type: "number" } } },
  },
  {
    name: "minecraft_undo",
    description: "Undo recent builds (Ctrl+Z). Every build tool snapshots the area first. steps:N undoes your newest N builds; match:'cottage roof' undoes the newest build whose label has those words (all_matching for every match) and refuses if a newer build overlaps it (force:true to override). Only your own builds unless any_owner:true. list:true shows the stack.",
    inputSchema: { type: "object", properties: { steps: { type: "number" }, match: { type: "string" }, all_matching: { type: "boolean" }, force: { type: "boolean" }, list: { type: "boolean" }, any_owner: { type: "boolean" } } },
  },
  {
    name: "minecraft_verify",
    description: "Check that a build really is in the world: recomputes what every block should be from the command file(s) and compares with the world (mismatches by type, e.g. 'glass>oak_leaves' = a tree grew into it) + stray water/lava. Runs automatically after builds; use it to re-check later.",
    inputSchema: { type: "object", properties: { commands_file: { type: "string" }, commands_files: { type: "array", items: { type: "string" } }, commands: { type: "array", items: { type: "string" } } } },
  },
];

export function handlers(K) {
  const H = {
    async minecraft_run_command(args) {
      // escape hatch: run any tool by name (lets new tools work before the client refreshes its cached tool list)
      if (args.call_tool) {
        let ta = args.tool_args;
        if (typeof ta === "string") ta = JSON.parse(ta);
        if (!ta || !Object.keys(ta).length) { ta = { ...args }; delete ta.call_tool; delete ta.tool_args; }
        for (const k of Object.keys(ta)) {
          const v = ta[k];
          if (typeof v === "string" && /^\s*[\[{]/.test(v)) { try { ta[k] = JSON.parse(v); } catch {} }
          else if (typeof v === "string" && /^-?\d+(\.\d+)?$/.test(v)) ta[k] = Number(v);
          else if (v === "true" || v === "false") ta[k] = v === "true";
        }
        return await K.handle(args.call_tool, ta);
      }
      const list = K.readCommandArgs(args);
      if (!list.length) throw new Error("Give command, commands, commands_file or commands_files.");
      const targets = K.targetsFromCommands(list);
      const zblock = K.zoneGuard(targets, args.allow_protected);
      if (zblock) return K.fail(zblock);
      const firstFile = args.commands_file || args.commands_files?.[0];
      const label = String(args.label || (firstFile ? firstFile.replace(/^.*\//, "").replace(/\.json$/, "") : list[0].slice(0, 40)));
      const undoInfo = targets.length && args.undo !== false ? await K.snapshotFor(targets, label).catch((e) => ({ skipped: e.message })) : null;
      if (args.background) {
        const wt = targets.length ? [] : K.summonWorkTargets(list);
        const job = K.enqueueJob({ label: label.slice(0, 40), list, targets, wt,
          box: targets.length ? K.unionBox(targets) : (wt.length ? K.unionBox(wt) : null), pace: Math.max(0, Math.min(args.pace_ms ?? 0, 500)), swing_every: args.swing_every || 0,
          helpers: Math.max(0, Math.min(args.helpers ?? 0, 4)), keep_helpers: !!args.keep_helpers, verify: args.verify, entrance: args.entrance ?? args.check_access, access_box: args.access_box, status: "queued", done: 0, errors: 0, failures: [], undo: undoInfo, hIdx: 0 });
        return K.text({ job: job.id, label: job.label, commands: list.length, status: "started in the background — progress bar is visible in game. Wait with minecraft_jobs action:wait id:" + job.id, undo: undoInfo });
      }
      const pace = Math.max(0, Math.min(args.pace_ms ?? 0, 500));
      if (list.length > 1 && (pace || args.swing_every)) {
        if (args.swing_every) {
          // in creative, "attack" breaks the block the bot looks at — only swing in adventure
          const gm = await K.playerInfo(K.BOT).then((p) => p.gameMode).catch(() => null);
          if (gm === "creative" || gm === "survival") await K.cmd(`gamemode adventure ${K.BOT}`).catch(() => {});
        }
        const results = [];
        let errors = 0;
        const t0 = Date.now();
        for (let i = 0; i < list.length; i++) {
          let out;
          try { out = await K.cmd(list[i]); } catch (e) { out = `ERROR: ${e.message}`; }
          const bad = out.startsWith("ERROR:") || (K.looksLikeError(out) && !K.harmless(out));
          if (bad) errors++;
          results.push({ command: list[i], output: out, error: bad });
          if (bad && args.stop_on_error) break;
          if (args.swing_every && i % args.swing_every === 0) await K.swingNow(K.BOT);
          if (pace) await K.sleep(pace);
        }
        const post = {};
        if (targets.length) await K.afterBuild(list, targets, label, post, args.verify ?? list.length > 25, args.entrance ?? args.check_access).catch(() => {});
        return K.text({ ran: results.length, ...(undoInfo ? { undo: undoInfo } : {}), errors, seconds: +((Date.now() - t0) / 1000).toFixed(1), failures: results.filter((r) => r.error).slice(0, 20).map((x) => `${x.command} → ${x.output}`), ...post });
      }
      if (list.length === 1 && !targets.length) {
        const out = await K.cmd(list[0]);
        return K.text(out || "(no output — command ran)");
      }
      const r = await K.runMany(list, { stopOnError: args.stop_on_error });
      const post = {};
      if (targets.length) await K.afterBuild(list, targets, label, post, args.verify ?? list.length > 25, args.entrance ?? args.check_access).catch(() => {});
      if (list.length > 25) return K.text({ ran: r.results.length, errors: r.errors, failures: r.results.filter((x) => x.error).slice(0, 20).map((x) => `${x.command} → ${x.output}`), ...(undoInfo ? { undo: undoInfo } : {}), ...post });
      return K.text({ ran: r.results.length, errors: r.errors, ...post, results: r.results.map((x) => `${x.error ? "✗" : x.unchanged ? "=" : "✓"} ${x.command}\n   → ${x.output || "(ok)"}`) });
    },

    async minecraft_build(args) {
      const { origin, dimension, note } = await K.resolveOrigin(args);
      const cmds = [];
      const targets = [];
      const pts = [];
      for (const op of args.operations || []) {
        const kind = op.op || op.type;
        const P = (v) => K.add(origin, K.V(v));
        if (kind === "fill") {
          cmds.push(...K.fillCommands(P(op.from), P(op.to), op.block, op.mode, dimension));
          if (op.mode !== "keep") { const [lo, hi] = K.sortBox(P(op.from), P(op.to)); targets.push({ lo, hi }); }
        } else if (kind === "setblock") {
          cmds.push(K.inDim(dimension, `setblock ${P(op.pos).join(" ")} ${op.block}${op.mode ? " " + op.mode : ""}`));
          if (op.mode !== "keep") targets.push({ lo: P(op.pos), hi: P(op.pos) });
        } else if (kind === "clone") {
          cmds.push(K.inDim(dimension, `clone ${P(op.from).join(" ")} ${P(op.to).join(" ")} ${P(op.dest).join(" ")}${op.mode ? " " + op.mode : ""}`));
          const f = K.V(op.from), t = K.V(op.to), d = P(op.dest);
          targets.push({ lo: d, hi: [d[0] + Math.abs(t[0] - f[0]), d[1] + Math.abs(t[1] - f[1]), d[2] + Math.abs(t[2] - f[2])] });
        } else if (kind === "command") cmds.push(op.command);
        else throw new Error(`Unknown op: ${JSON.stringify(op)} — use fill, setblock, clone or command`);
        for (const k of ["from", "to", "pos", "dest"]) if (op[k]) pts.push(P(op[k]));
      }
      if (cmds.length > 20000) throw new Error(`Too many commands (${cmds.length}). Use bigger fills or a generator.`);
      const zb = K.zoneGuard(targets, args.allow_protected);
      if (zb) return K.fail(zb);
      const blocked = await K.overwriteGuard(targets, args.allow_overwrite);
      if (blocked) return K.fail(blocked);
      if (args.undo !== false) await K.snapshotFor(targets, args.label || "build").catch(() => {});
      const botNote = pts.length ? await K.keepBotOutOf(...K.boxOf(pts)) : null;
      const r = await K.runMany(cmds);
      const post = {};
      await K.afterBuild(cmds, targets, args.label || "build", post, args.verify, args.entrance ?? args.check_access).catch(() => {});
      return K.text({ ...post, coordinates: note, origin, ...(botNote ? { bot: botNote } : {}), commandsRun: cmds.length, failed: r.errors,
        failures: r.results.filter((x) => x.error).slice(0, 15).map((f) => `${f.command} → ${f.output}`), sample: r.results.slice(0, 5).map((x) => `${x.command} → ${x.output}`) });
    },

    async minecraft_build_layers(args) {
      const { origin: base, dimension, note } = await K.resolveOrigin(args);
      const o = K.add(base, K.V(args.origin));
      const cmds = [];
      const runs = [];
      args.layers.forEach((layer, dy) => {
        layer.forEach((row, dz) => {
          const chars = [...row];
          let i = 0;
          while (i < chars.length) {
            const ch = chars[i];
            const block = args.legend[ch];
            if (!block) { i++; continue; }
            let j = i;
            while (j + 1 < chars.length && chars[j + 1] === ch) j++;
            const a = [o[0] + i, o[1] + dy, o[2] + dz];
            const b = [o[0] + j, o[1] + dy, o[2] + dz];
            runs.push({ lo: a, hi: b });
            cmds.push(K.inDim(dimension, i === j ? `setblock ${a.join(" ")} ${block}` : `fill ${a.join(" ")} ${b.join(" ")} ${block}`));
            i = j + 1;
          }
        });
      });
      const sx = Math.max(...args.layers.flat().map((r) => [...r].length));
      const sz = Math.max(...args.layers.map((l) => l.length));
      const zb = K.zoneGuard(runs, args.allow_protected);
      if (zb) return K.fail(zb);
      const blocked = await K.overwriteGuard(runs, args.allow_overwrite);
      if (blocked) return K.fail(blocked);
      if (args.undo !== false) await K.snapshotFor(runs, args.label || "build_layers").catch(() => {});
      const botNote = await K.keepBotOutOf(o, [o[0] + sx - 1, o[1] + args.layers.length - 1, o[2] + sz - 1]);
      const r = await K.runMany(cmds);
      const post = {};
      await K.afterBuild(cmds, runs, args.label || "build_layers", post, true, null).catch(() => {});
      return K.text({ ...post, coordinates: note, origin: o, ...(botNote ? { bot: botNote } : {}), size: { x: sx, y: args.layers.length, z: sz },
        commandsRun: cmds.length, failed: r.errors, failures: r.results.filter((x) => x.error).slice(0, 15).map((f) => `${f.command} → ${f.output}`) });
    },

    async minecraft_generate(args) {
      const g = await K.runGenerator(args.script, args.args || []);
      if (!args.build || !g.ok) return K.text(g);
      let files = g.files;
      if (args.files?.length) {
        const pats = args.files.map((f) => new RegExp("^(.*/)?" + String(f).replace(/[.+^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*").replace(/\?/g, ".") + "(\\.json)?$"));
        files = files.filter((f) => pats.some((p) => p.test(f)));
      }
      const jobs = [];
      // the access check at the end covers everything the generator made, not just the last file
      const allTargets = K.targetsFromCommands(files.flatMap((f) => K.readCommandArgs({ commands_file: f })));
      const accessBox = allTargets.length ? K.unionBox(allTargets) : null;
      for (const f of files) {
        const last = f === files[files.length - 1];
        const r = await H.minecraft_run_command({ commands_file: f, background: true, label: (args.label ? args.label + " " : "") + f.replace(/^.*\//, "").replace(/\.json$/, ""),
          helpers: jobs.length ? 0 : args.helpers, allow_protected: args.allow_protected, ...(last && (args.entrance || args.check_access) ? { entrance: args.entrance ?? args.check_access, access_box: accessBox } : {}) });
        const t = r.content?.[0]?.text || "";
        try { jobs.push(JSON.parse(t)); } catch { jobs.push({ file: f, error: t.slice(0, 300) }); if (r.isError) break; }
      }
      return K.text({ ...g, jobs, next: jobs.length ? `minecraft_jobs action:wait id:${jobs[jobs.length - 1].job} (repeat until done)` : undefined });
    },

    async minecraft_worldedit(args) {
      const pz = {};
      for (const c of args.commands || []) { const m = /^\/*pos([12])\s+(-?\d+)[ ,]+(-?\d+)[ ,]+(-?\d+)/.exec(String(c).trim()); if (m) pz[m[1]] = [+m[2], +m[3], +m[4]]; }
      if (pz[1] && pz[2]) {
        const [lo, hi] = K.sortBox(pz[1], pz[2]);
        const zb = K.zoneGuard([{ lo, hi }], args.allow_protected);
        if (zb) return K.fail(zb);
      }
      const out = [];
      for (let c of args.commands || []) {
        c = String(c).trim().replace(/^\/+/, "");
        if (/['\\]/.test(c)) throw new Error(`Quotes/backslashes not supported in WorldEdit commands: ${c}`);
        // WorldEdit ignores commands wrapped in /execute, so the bot runs them through scarpet's run()
        const r = await K.cmd(`execute as ${K.BOT} at @s run script run run('//${c}')`);
        out.push(`//${c} → ${/Unknown|Error|error/.test(r) ? r : "sent"}`);
      }
      return K.text(out.join("\n") + "\n(Verify the result with minecraft_inspect or a screenshot — WorldEdit's replies aren't visible here.)");
    },

    async minecraft_jobs(args) {
      if (args.action === "list" || !args.action) return K.text(K.allJobs().map(K.jobView));
      const job = K.findJob(args.id);
      if (!job) return K.text("No jobs.");
      if (args.action === "cancel") { job.cancel = true; if (job.status === "queued") job.status = "cancelled"; return K.text(K.jobView(job)); }
      if (args.action === "wait") {
        const until = Date.now() + Math.max(1, Math.min(args.timeout_seconds ?? 45, 50)) * 1000;
        while (Date.now() < until && ["queued", "running", "checking"].includes(job.status)) await K.sleep(500);
      }
      return K.text(K.jobView(job));
    },

    async minecraft_undo(args) {
      const stack = K.readJSON(K.P.UNDO, []);
      if (args.list) return K.text(stack.slice().reverse().map((u, i) => `${i + 1}. [${u.owner || "?"}] ${u.label} — ${u.lo.join(",")} → ${u.hi.join(",")} (${u.time.slice(0, 19)})`).join("\n") || "Undo stack is empty.");
      const n = Math.max(1, args.steps ?? 1);
      const mine = (u) => args.any_owner || !u.owner || u.owner === K.BOT;
      const picked = [];
      if (args.match) {
        const words = String(args.match).toLowerCase().split(/\s+/).filter(Boolean);
        const hitU = (u) => { const l = String(u.label || "").toLowerCase(); return words.every((w) => l.includes(w)) || String(u.id) === args.match; };
        const ov = (a, b) => [0, 1, 2].every((i) => a.lo[i] <= b.hi[i] && a.hi[i] >= b.lo[i]);
        let blocked = null;
        await K.updateJSON(K.P.UNDO, [], (all) => {
          const idx = [];
          for (let i = all.length - 1; i >= 0; i--) if (mine(all[i]) && hitU(all[i])) { idx.push(i); if (!args.all_matching) break; }
          if (!idx.length) return;
          const chosen = new Set(idx);
          const later = [];
          for (const i of idx) for (let j = i + 1; j < all.length; j++) if (!chosen.has(j) && ov(all[i], all[j])) later.push(all[j]);
          if (later.length && !args.force) { blocked = { matches: idx.map((i) => all[i].label), newer_overlapping: [...new Set(later.map((u) => `${u.label} (${u.time.slice(0, 16)})`))] }; return; }
          for (const i of idx.sort((a, b) => b - a)) picked.push(all.splice(i, 1)[0]);
        });
        if (blocked) return K.text({ refused: "newer builds overlap this one — restoring the old snapshot would also wipe them. Undo those first, or pass force:true.", ...blocked });
        if (!picked.length) {
          const near = K.readJSON(K.P.UNDO, []).filter(mine).map((u) => [words.filter((w) => String(u.label || "").toLowerCase().includes(w)).length, u]).filter(([k]) => k > 0).sort((a, b) => b[0] - a[0] || String(b[1].time).localeCompare(String(a[1].time)));
          return K.text({ nothing_undone: `no build label has all of: ${words.join(" ")}`, closest: near.slice(0, 6).map(([, u]) => `${u.label} (${u.time.slice(0, 16)}, id ${u.id})`) });
        }
      } else {
        await K.updateJSON(K.P.UNDO, [], (all) => {
          for (let i = all.length - 1; i >= 0 && picked.length < n; i--) if (mine(all[i])) picked.push(all.splice(i, 1)[0]);
        });
      }
      if (!picked.length) return K.text("Nothing of yours to undo.");
      const done = [];
      for (const u of picked) {
        const rs = [];
        for (const q of u.parts || [u.id]) {
          const r = await K.inApp("cu", `restore('${q}')`);
          await K.inApp("cu", `unsnap('${q}')`).catch(() => {});
          rs.push(r.replace(/\s*\(\d.*$/, "").trim());
        }
        done.push(`${u.label}: ${rs.join(" | ")}`);
      }
      return K.text({ undone: done, remaining: K.readJSON(K.P.UNDO, []).length });
    },

    async minecraft_verify(args) {
      const list = K.readCommandArgs(args);
      const targets = K.targetsFromCommands(list);
      if (!targets.length) return K.text("no fill/setblock commands with absolute coordinates to check");
      return K.text(await K.verifyBuild(list, K.unionBox(targets)));
    },
  };
  return H;
}
