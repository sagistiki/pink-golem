/**
 * Building: minecraft_run_command, minecraft_build, minecraft_build_layers, minecraft_worldedit, minecraft_generate,
 * minecraft_jobs, minecraft_undo, minecraft_verify.
 * Every tool that changes blocks goes through the same rails: zone guard → undo snapshot → run → verify → auto-zone.
 */

import fs from "node:fs";
import path from "node:path";

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
        commands_file: { type: "string", description: "A file inside the Pink Golem folder, e.g. 'jobs/cottage.json': a JSON array of commands, or one command per line (# = comment)." },
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
        dry_run: { type: "boolean", description: "PREFLIGHT, nothing runs: the server parses every distinct command form (bad block names/states, wrong arguments, old item NBT…), plus protected zones, which existing blocks would be overwritten, players in the way, fill/RCON limits and a time estimate" },
        skip_check: { type: "boolean", description: "Background jobs are syntax-checked first and refused on errors; true skips that" },
        call_tool: { type: "string", description: "Instead of commands: run another minecraft_* tool by name, with its arguments in tool_args. Use when a newer tool isn't in your tool list yet." },
        tool_args: { type: "object", description: "Arguments for call_tool" },
      },
    },
  },
  {
    name: "minecraft_build",
    description:
      "Build a few shapes quickly (fill/setblock/clone; big fills are split automatically). Coordinates are absolute. Or set relative_to_player to a player's NAME: then coordinates are offsets from the ground block that player stands on ([0,0,0] = that ground block, y=1 = the first block above it). Floors replace the ground block; walls start one above. Refuses to overwrite existing builds unless allow_overwrite. Ops: {op:'fill', from, to (or size:[w,h,d] instead of to), block, mode?: replace|hollow|outline|keep|destroy}, {op:'setblock', pos, block}, {op:'clone', from, to, dest}, {op:'command', command}. Block states in brackets: 'oak_stairs[facing=east]'. For anything bigger than a few dozen shapes, write a generator (skill: scripts/mclib.py) and use minecraft_generate.",
    inputSchema: {
      type: "object",
      properties: {
        operations: { type: "array", items: { type: "object" } },
        relative_to_player: { type: "string", description: "a player's NAME (e.g. \"Steve\"); then the coordinates are offsets from the block they stand on. Leave out for absolute coordinates." },
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
        relative_to_player: { type: "string", description: "a player's NAME (e.g. \"Steve\"); then the coordinates are offsets from the block they stand on. Leave out for absolute coordinates." },
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
    description: "Run a Python build generator inside the Pink Golem folder (e.g. skill/pinkgolem/blueprints/cottage.py, or your own in jobs/). Generators use skill/pinkgolem/scripts/mclib.py and write command files into jobs/. Returns stdout and the files written. With build:true the files are queued as background jobs (undo, zone guard, verification, auto-zone), helpers join the first one, and entrance/check_access runs on the last one. Pass generator arguments in args (blueprints take --at x,y,z and --facing). No file access in your client? Pass the Python source in `code` and a file name in `script` (saved under jobs/, then run).",
    inputSchema: { type: "object", properties: {
      script: { type: "string", description: "path relative to the Pink Golem folder (with code: a file name like jobs/gen_bakery.py)" }, args: { type: "array", items: { type: "string" } },
      code: { type: "string", description: "optional Python source to save as `script` (must be under jobs/) before running it. Off unless security.allow_code is true in pinkgolem.json (it runs on the host computer)" },
      build: { type: "boolean", description: "queue the generated files as build jobs (default false = generate only, then minecraft_preview them)" },
      files: { type: "array", items: { type: "string" }, description: "only build these of the generated files (names or globs like cottage-*)" },
      helpers: { type: "number" }, allow_protected: { type: "boolean" }, label: { type: "string" }, entrance: vec, check_access: { type: "boolean" },
      dry_run: { type: "boolean", description: "generate, then PREFLIGHT all written files (syntax parsed by the server, zones, overwrites, players) — nothing is built" } }, required: ["script"] },
  },
  {
    name: "minecraft_blueprint",
    description:
      "Build a ready-made blueprint in ONE call — the easy way to 'build me a house / cottage / villa / tower / park (next to me / near X)'. It finds free flat ground next to a player or a build on the map, turns the door toward the player, builds with the helper crew, waits until it's done, checks it and adds it to the map. Then tell the player what it says in `say`. name: cottage | modern_villa | tower | park | drop_tower.",
    inputSchema: {
      type: "object",
      properties: {
        name: { type: "string", enum: ["cottage", "modern_villa", "tower", "park", "drop_tower"] },
        near: { type: "string", description: "a player's name or a build on the map (default: the player online)" },
        at: { ...vec, description: "optional exact spot: the blueprint's --at (ground level). Leave out to let the tool pick free ground" },
        facing: { type: "string", enum: ["north", "south", "east", "west"], description: "default: the door faces the player" },
        style: { type: "string", description: "optional: cottage oak|birch|dark, villa white|dark|wood, tower stone|sandstone|brick" },
        label: { type: "string", description: "name on the map (default: the blueprint's name)" },
        helpers: { type: "number", description: "helper builders 0-4 (default 3)" },
      },
      required: ["name"],
    },
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
      if (args.dry_run) return K.text(await K.preflight(list, args));
      if (args.background && !args.skip_check) {
        const sx = await K.syntaxCheck(list);
        if (sx.errors.length || sx.too_long.length)
          return K.fail(JSON.stringify({ refused: "syntax errors — nothing was built (the server parsed every command form without running it). Fix them, or pass skip_check:true.", ...sx }, null, 2));
      }
      const targets = K.targetsFromCommands(list);
      const zblock = K.zoneGuard(targets, args.allow_protected);
      if (zblock) return K.fail(zblock);
      const pblock = await K.playerGuard(targets);
      if (pblock) return K.fail(pblock);
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
      const summary = [];
      for (let op of args.operations || []) {
        const kind = op.op || op.type;
        // "a 5x5 floor" is easier as a size than as a far corner: size [w, h, d] → to = from + size - 1
        if (kind === "fill" && op.size !== undefined && op.to === undefined) {
          const sz = op.size;
          if (!(Array.isArray(sz) && sz.length === 3 && sz.every((v) => Number.isInteger(Number(v)) && Number(v) >= 1)))
            throw new Error(`fill size must be three whole numbers ≥ 1 [width_x, height_y, depth_z]; got ${JSON.stringify(sz)}. Nothing was built.`);
          op = { ...op, to: K.V(op.from).map((v, i) => v + Number(sz[i]) - 1) };
        }
        // [x, y, z] means exactly three numbers: a fourth one ("to":[5512,4,-60,5001]) once became a 5 km stone wall
        for (const k of ["from", "to", "pos", "dest"])
          if (op[k] !== undefined && !(Array.isArray(op[k]) && op[k].length === 3 && op[k].every((v) => Number.isFinite(Number(v)))))
            throw new Error(`${kind} ${k} must be exactly three numbers [x, y, z]; got ${JSON.stringify(op[k])}. Nothing was built.`);
        const P = (v) => K.add(origin, K.V(v));
        if (kind === "fill") {
          const [slo, shi] = K.sortBox(P(op.from), P(op.to));
          const d = [0, 1, 2].map((i) => shi[i] - slo[i] + 1);
          summary.push(`${op.block}: ${d[0]}×${d[1]}×${d[2]} = ${d[0] * d[1] * d[2]} blocks, ${slo.join(",")} → ${shi.join(",")}${op.mode ? ` (${op.mode})` : ""}`);
          cmds.push(...K.fillCommands(P(op.from), P(op.to), op.block, op.mode, dimension));
          if (op.mode !== "keep") { const [lo, hi] = K.sortBox(P(op.from), P(op.to)); targets.push({ lo, hi, block: op.block }); }
        } else if (kind === "setblock") {
          summary.push(`${op.block} at ${P(op.pos).join(",")}`);
          cmds.push(K.inDim(dimension, `setblock ${P(op.pos).join(" ")} ${op.block}${op.mode ? " " + op.mode : ""}`));
          if (op.mode !== "keep") targets.push({ lo: P(op.pos), hi: P(op.pos), block: op.block });
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
      const pb = await K.playerGuard(targets);
      if (pb) return K.fail(pb);
      const blocked = await K.overwriteGuard(targets, args.allow_overwrite);
      if (blocked) return K.fail(blocked);
      if (args.undo !== false) await K.snapshotFor(targets, args.label || "build").catch(() => {});
      const botNote = pts.length ? await K.keepBotOutOf(...K.boxOf(pts)) : null;
      const r = await K.runMany(cmds);
      const post = {};
      await K.afterBuild(cmds, targets, args.label || "build", post, args.verify, args.entrance ?? args.check_access).catch(() => {});
      const listed = summary.length > 12 ? [...summary.slice(0, 12), `… ${summary.length - 12} more`] : summary;
      const placed = !r.errors && !(post.verify && post.verify.checked && post.verify.mismatches === post.verify.checked);
      if (!placed) {   // say it first: a reply that starts with "built" reads as success to a small model
        const why = (r.results || []).find((x) => x.error)?.output || (post.verify ? `${post.verify.mismatches} of ${post.verify.checked} blocks are not as planned` : "");
        const some = r.errors < cmds.length && !(post.verify && post.verify.mismatches === post.verify.checked);
        return K.fail(`${some ? "PARTLY BUILT" : "NOT BUILT"} — ${r.errors} of ${cmds.length} commands failed${why ? `: ${String(why).slice(0, 200)}` : ""}. `
          + `Requested: ${listed.join("; ")}. Fix the cause and build again${some ? " (minecraft_undo steps:1 first if the half-built part is in the way)" : ""}.`);
      }
      return K.text({ built: listed, ...post, coordinates: note, origin, ...(botNote ? { bot: botNote } : {}), commandsRun: cmds.length, failed: r.errors,
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
            runs.push({ lo: a, hi: b, block });
            cmds.push(K.inDim(dimension, i === j ? `setblock ${a.join(" ")} ${block}` : `fill ${a.join(" ")} ${b.join(" ")} ${block}`));
            i = j + 1;
          }
        });
      });
      const sx = Math.max(...args.layers.flat().map((r) => [...r].length));
      const sz = Math.max(...args.layers.map((l) => l.length));
      const zb = K.zoneGuard(runs, args.allow_protected);
      if (zb) return K.fail(zb);
      const pb = await K.playerGuard(runs);
      if (pb) return K.fail(pb);
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
      if (args.code) {   // clients without file access can still write their own generators
        const f = K.safePath(args.script);
        if (!f.startsWith(K.P.JOBS + path.sep) || !f.endsWith(".py")) throw new Error("with code, script must be a .py file under jobs/ (e.g. jobs/gen_bakery.py)");
        fs.writeFileSync(f, String(args.code));
      }
      const blueprint = /(^|\/)blueprints\//.test(String(args.script));
      const argv = K.fixGeneratorArgs(args.args || [], blueprint);
      const fixed = JSON.stringify(argv) !== JSON.stringify((args.args || []).map(String)) ? `(args read as ${JSON.stringify(argv)})` : "";
      const g = await K.runGenerator(args.script, argv);
      if (fixed) g.args_fixed = fixed;
      if (!g.ok) {
        const err = (g.stderr || g.stdout || "").trim().split(/\r?\n/).slice(-8).join("\n");
        return K.fail(`FAILED — ${args.script} stopped with an error, so NOTHING was generated or built.\n${err}`
          + (blueprint ? `\nBlueprint arguments are separate strings: "args": ["--at", "X,Y,Z", "--facing", "south"]` : "")
          + (fixed ? `\n${fixed}` : "") + "\nFix the arguments and call minecraft_generate again. Don't tell the player it's built.");
      }
      if (args.build && !g.files.length) return K.fail(`FAILED — ${args.script} ran but wrote no job files, so nothing was built.\n${(g.stdout || "").slice(-600)}`);
      if (args.dry_run && g.ok) {
        let all = [];
        for (const f of g.files) { const raw = fs.readFileSync(K.safePath(f), "utf8"); all = all.concat(raw.trim().startsWith("[") ? JSON.parse(raw) : raw.split(/\r?\n/).map((l) => l.trim()).filter((l) => l && !l.startsWith("#"))); }
        return K.text({ ...g, preflight: await K.preflight(all, args) });
      }
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
      // a phase refused by a guard (protected zone, a player in the way, existing blocks) must not hide under "ok": true
      const refused = jobs.filter((j) => j.job == null);
      if (refused.length) {
        const started = jobs.filter((j) => j.job != null);
        return K.fail(`${started.length ? `PARTLY BUILT — ${started.length} phase(s) started, ${refused.length} refused` : "FAILED — NOTHING was built"}: `
          + `${String(refused[0].error || "").slice(0, 500)}\nMove the build (another spot or facing) and run minecraft_generate again. Don't tell the player it's built.`
          + (started.length ? `\nStarted jobs: ${started.map((j) => j.job).join(", ")} — undo them with minecraft_undo if the build moves.` : ""));
      }
      return K.text({ ...g, jobs, next: jobs.length ? `minecraft_jobs action:wait id:${jobs[jobs.length - 1].job} (repeat until done)` : undefined });
    },

    async minecraft_blueprint(args) {
      const BP = { cottage: "cottage.py", house: "cottage.py", modern_villa: "modern_villa.py", villa: "modern_villa.py", tower: "tower.py",
        lookout_tower: "tower.py", park: "park.py", drop_tower: "drop_tower.py" };
      const key = String(args.name || "").toLowerCase().trim().replace(/\.py$/, "").replace(/[\s-]+/g, "_");
      const file = BP[key];
      if (!file) throw new Error(`no blueprint "${args.name}". Choose one of: cottage, modern_villa, tower, park, drop_tower`);
      const kind = file.replace(/\.py$/, "");
      const script = `skill/pinkgolem/blueprints/${file}`;
      const extra = args.style ? ["--style", String(args.style)] : [];
      const probe = async (facing, at) => {
        const g = await K.runGenerator(script, ["--at", at.join(","), "--facing", facing, ...extra]);
        const m = /box \[(-?\d+), (-?\d+), (-?\d+)\] -> \[(-?\d+), (-?\d+), (-?\d+)\]/.exec(g.stdout || "");
        if (!g.ok || !m) throw new Error(`blueprint ${file} failed: ${(g.stderr || g.stdout || "").slice(-400)}`);
        const e = /entrance[^[]*\[(-?[\d.]+), (-?[\d.]+), (-?[\d.]+)\]/.exec(g.stdout);
        return { lo: [+m[1], +m[2], +m[3]], hi: [+m[4], +m[5], +m[6]], entrance: e ? [+e[1], +e[2], +e[3]] : null };
      };
      // who it is for and where: a player (default: the one online) or a build on the map
      const players = (await K.onlinePlayers()).names.filter((n) => n !== K.BOT && !(K.isCrew && K.isCrew(n)));
      const q = args.near ? String(args.near).trim() : "";
      let forWhom = (q && players.find((n) => n.toLowerCase() === q.toLowerCase())) || null;
      let nearBuild = null;
      if (q && !forWhom) {
        nearBuild = K.WM.lookup(K.mapEntries(), q)[0] || null;
        if (!nearBuild) throw new Error(`"${q}" is neither a player online (${players.join(", ") || "nobody"}) nor a build on the map (minecraft_map action:list)`);
      }
      if (!forWhom) forWhom = players[0] || null;
      const who = forWhom ? (await K.playerInfo(forWhom)).position : null;
      const toward = (from) => {                     // the door looks at the player
        if (!who) return "south";
        const dx = who.x - from[0], dz = who.z - from[1];
        return Math.abs(dx) > Math.abs(dz) ? (dx > 0 ? "east" : "west") : (dz > 0 ? "south" : "north");
      };
      let facing = args.facing ? String(args.facing).toLowerCase() : null;
      let at;
      if (args.at) {
        at = K.V(args.at).map(Math.round);
        facing = facing || toward([at[0], at[2]]);
      } else {
        const c = nearBuild ? K.WM.center(nearBuild) : who ? [who.x, who.y, who.z] : null;
        if (!c) throw new Error("nobody is online: pass near (a build on the map) or at [x,y,z]");
        const b0 = await probe("south", [0, K.isFlat ? K.flatGroundY : 0, 0]);
        const side = Math.max(b0.hi[0] - b0.lo[0], b0.hi[2] - b0.lo[2]) + 3;       // any facing fits, +1 block around
        const found = await K.findSpace({ size: [side, side], ...(nearBuild ? { near: nearBuild.name } : { pos: c }), radius: 60, margin: 2, count: 1 });
        const spot = found.spots?.[0];
        if (!spot) throw new Error(`no free ${side}x${side} ground near ${nearBuild ? nearBuild.name : forWhom}: ${found.note}`);
        const m = [(spot.from[0] + spot.to[0]) / 2, (spot.from[2] + spot.to[2]) / 2];
        let gy = K.isFlat ? K.flatGroundY : null;
        if (gy === null) gy = parseInt(String(await K.inApp("cu", `ytop(${Math.round(m[0])},${Math.round(m[1])})`)).match(/-?\d+/)?.[0] ?? "0", 10);
        facing = facing || toward(m);
        const b = await probe(facing, [0, gy, 0]);
        at = [Math.round(m[0] - (b.lo[0] + b.hi[0]) / 2), gy, Math.round(m[1] - (b.lo[2] + b.hi[2]) / 2)];
      }
      const box = await probe(facing, at);
      const r = await H.minecraft_generate({ script, args: ["--at", at.join(","), "--facing", facing, ...extra], build: true,
        helpers: args.helpers ?? 3, label: kind, ...(box.entrance ? { entrance: box.entrance } : {}) });
      if (r.isError) return r;
      let res;
      try { res = JSON.parse(r.content[0].text); } catch { return r; }
      const ids = (res.jobs || []).map((j) => j.job).filter((x) => x != null);
      if (!ids.length) return K.fail(`the build did not start: ${JSON.stringify(res.jobs || res).slice(0, 600)}`);
      const views = () => ids.map((id) => K.findJob(id)).filter(Boolean);
      const until = Date.now() + 50000;
      while (Date.now() < until && views().some((j) => ["queued", "running", "checking"].includes(j.status))) await K.sleep(500);
      const js = views().map(K.jobView);
      const done = js.every((j) => j.status === "done");
      const errors = js.reduce((a, j) => a + (j.errors || 0), 0);
      const base = args.label || kind.replace(/_/g, " ").replace(/^./, (ch) => ch.toUpperCase());
      const taken = new Set(K.mapEntries().map((e) => String(e.name).toLowerCase()));
      let name = base;
      for (let i = 2; taken.has(name.toLowerCase()); i++) name = `${base} ${i}`;
      await K.handle("minecraft_map", { action: "add", name, from: box.lo, to: box.hi, builder: K.BOT, owner: forWhom || "?", kind,
        ...(box.entrance ? { entrances: [[...box.entrance, "front door"]] } : {}), notes: `${kind} blueprint, facing ${facing}` }).catch(() => {});
      let where = "";
      if (who && box.entrance) {
        const dx = box.entrance[0] - who.x, dz = box.entrance[2] - who.z;
        where = `${Math.round(Math.hypot(dx, dz))} blocks ${K.WM.compass(dx, dz)} of you`;
      }
      return K.text({ built: name, status: done ? (errors ? "done with errors" : "done") : "still building", at, facing, box: [box.lo, box.hi],
        entrance: box.entrance, errors,
        jobs: js.map((j) => ({ id: j.id, status: j.status, done: `${j.done}/${j.total}`, errors: j.errors, verify_ok: j.verify?.ok, access_ok: j.access?.ok })),
        ...(done ? {} : { next: `still building — call minecraft_jobs {"action":"wait","id":${ids[ids.length - 1]}} until it says done` }),
        ...(done && !errors ? { say: `Your ${name.toLowerCase()} is ready${where ? ", " + where : ""}${forWhom && box.entrance ? " — the door faces you" : ""}.` } : {}) });
    },

    async minecraft_worldedit(args) {
      const pz = {};
      for (const c of args.commands || []) { const m = /^\/*pos([12])\s+(-?\d+)[ ,]+(-?\d+)[ ,]+(-?\d+)/.exec(String(c).trim()); if (m) pz[m[1]] = [+m[2], +m[3], +m[4]]; }
      if (pz[1] && pz[2]) {
        const [lo, hi] = K.sortBox(pz[1], pz[2]);
        const zb = K.zoneGuard([{ lo, hi }], args.allow_protected);
        if (zb) return K.fail(zb);
      }
      // vanilla commands sent here go out as "//fill …", which WorldEdit ignores — and the reply would still say "sent"
      const vanilla = (args.commands || []).map((c) => String(c).trim().replace(/^\/+/, "").split(/\s+/)[0].toLowerCase())
        .filter((w) => ["fill", "setblock", "clone", "summon", "give", "tp", "teleport", "execute", "kill", "data", "place"].includes(w));
      if (vanilla.length) throw new Error(`"${vanilla[0]}" is a vanilla command, not a WorldEdit one — nothing was sent. Use minecraft_build `
        + `(fill / setblock / clone with absolute coordinates) or minecraft_run_command. WorldEdit commands look like set, replace, walls, copy, paste, stack.`);
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
      if (!job) return K.text(args.id ? `No job ${args.id}. Jobs: ${JSON.stringify(K.allJobs().map((j) => ({ id: j.id, label: j.label, status: j.status })))}`
        : "No build jobs: nothing is being built and nothing was built by a job in this session. If minecraft_generate failed, fix it and run it again with build:true.");
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
