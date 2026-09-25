/**
 * Developer tools for scarpet apps:
 *   minecraft_app       lint (static checks for known traps) · status (is anyone using it?) · reload (only when idle, errors
 *                       collected) · patch (a live function definition of any size, no reload) · errors (from the log)
 *   minecraft_playtest  one call = a scripted test with Carpet fake players → timeline + PASS/FAIL, with a cleanup that
 *                       always runs (fake players and their files, records keyed by their names, app globals)
 * Pure helpers (lint, records) live in lib/devkit.js. Background: skill/clawdblock/reference/testing-apps.md
 */
import fs from "node:fs";
import path from "node:path";

const vec = { type: "array", items: { type: "number" }, minItems: 3, maxItems: 3, description: "[x, y, z]" };

export const tools = [
  {
    name: "minecraft_app",
    requires: ["carpet"],
    description: "Scarpet app manager. action: lint (app | file | all:true; level error|warning) = static checks for the traps that break apps: bracket balance with line numbers (and where a ')' is probably missing), missing ';' between top-level statements, put(m:k,'f',v) (replaces m:k with the string), assigning _ _i _a _x _y _z, deprecated query(e,'tags'), functions named like built-ins, slice() without an emptiness guard, run('kill …') reachable from commands, damage + the app's own __on_player_dies, unknown functions/events, scope | status (app → busy? a boolean 'busy' or 'idle' in status() decides; otherwise the state from status()/global_state, real players carrying its tags or standing in its area on the world map; no app → loaded apps) | reload (app; refuses on lint errors — a broken file UNLOADS the running app — or while busy; force:true; collects the app's errors from the log for watch_seconds) | patch (app + code or code_file = one or more function definitions of ANY size, applied live without a reload (state kept), then written into the .sc file (persist:false to skip; backup in data/app-backups); or app + function:'name' to push that definition from the edited .sc file) | errors (app or all: runtime errors from the log, grouped, with call stacks).",
    inputSchema: { type: "object", properties: {
      action: { type: "string", enum: ["lint", "status", "reload", "patch", "errors"] }, app: { type: "string" }, file: { type: "string" }, all: { type: "boolean" },
      level: { type: "string", enum: ["error", "warning", "note"] }, code: { type: "string" }, code_file: { type: "string" }, function: { type: "string" },
      persist: { type: "boolean" }, force: { type: "boolean" }, watch_seconds: { type: "number" }, ignore_tags: { type: "array", items: { type: "string" } }, limit: { type: "number" },
    }, required: ["action"] },
  },
  {
    name: "minecraft_playtest",
    requires: ["carpet"],
    description: "Run a scripted test of a scarpet app with Carpet fake players in ONE call → a tick-stamped timeline + PASS/FAIL. players:[{name:'Test_A', pos, gamemode, yaw, pitch}] spawn first; globals:{global_allow_fake:'true'} are set in `app` and restored after. steps (one key each, optional label): {wait:ticks} | {wait_until:'scarpet expr', timeout:ticks} | {player:'Test_A', do:'move forward'|'look at x y z'|'jump'|'sneak'|'use once'|'attack once'|'stop'|'hotbar 2'…, ticks:N (then stop)} | {tp:'Test_A', pos} | {spawn:{…}} | {kill:'Test_A'} | {command:'…', expect:'regex'} | {scarpet:'expr', app, in_tick:true (runs via schedule(0) inside the app's own tick — a death caused there never reaches the app's own __on_player_dies), save:'var', expect:{equals|contains|matches|truthy}} | {set:{global_x:'expr'}, restore:false} | {assert:'scarpet', expr, equals|contains|matches|truthy|falsy} | {assert:'position', player, pos, radius, horizontal} | {assert:'gamemode', player, equals} | {assert:'tag', player, tag, present} | {assert:'item', player, item, count, slot, absent, exact} | {assert:'online', player, present} | {assert:'log', matches, absent} | {note}. ${uuid:Test_A} and ${var} are substituted in expressions. Cleanup ALWAYS runs: cleanup.commands (e.g. stop the game), cleanup.wait_until, kill the fakes, restore globals, cleanup.records:[{app, global:'global_stats', file:'server/world/scripts/x.data/stats.json', restore:['games']}] (map keys named after the fakes and list entries holding their names are removed, listed paths set back), files the app saved for the fakes (name/uuid in the file name, or new files mentioning them) and their world player files. Refuses when the app is busy (status()/tags/area; force:true overrides). App errors logged during the test fail it (fail_on_app_errors:false to ignore).",
    inputSchema: { type: "object", properties: {
      name: { type: "string" }, app: { type: "string", description: "default app for scarpet steps, asserts, globals and the idle check" },
      players: { type: "array", items: { type: "object", properties: { name: { type: "string" }, pos: vec, gamemode: { type: "string" }, yaw: { type: "number" }, pitch: { type: "number" }, dimension: { type: "string" } }, required: ["name", "pos"] } },
      globals: { type: "object", description: "global_x: scarpet expression (string) or JSON value; restored after the test" },
      steps: { type: "array", items: { type: "object" } },
      cleanup: { type: "object", properties: { commands: { type: "array", items: { type: "string" } }, wait_until: { description: "expr, or {expr, app, timeout}" }, records: { type: "array", items: { type: "object" } }, data_files: { type: "boolean" }, player_files: { type: "boolean" } } },
      require_idle: { type: "boolean" }, force: { type: "boolean" }, ignore_tags: { type: "array", items: { type: "string" } }, stop_on_fail: { type: "boolean" }, fail_on_app_errors: { type: "boolean" },
      timeout_seconds: { type: "number", description: "default 120, max 600" },
    }, required: ["steps"] },
  },
];

const IDLE_WORDS = /^(idle|off|stopped|none|ready|waiting|lobby|free|open|closed|done|end(ed)?|)$/i;
const VAL_RE = /^\s*=\s*([\s\S]*?)\s*(?:\([^()]*\d[^()]*s\))?\s*$/;
const SC_ERR = /HERE>>|<--\[HERE\]|Unknown or incomplete command|Incorrect argument|Unknown app|is not a variable|at pos \d+|at line \d+, pos \d+|Your math is wrong|Internal error|Failed to add/i;
const PLAYER_ACTIONS = /^(move|look|turn|jump|sneak|unsneak|sprint|unsprint|use|attack|stop|hotbar|drop|dropStack|swapHands|mount|dismount)\b/;

export function handlers(K, ctx) {
  const D = K.devkit;
  const bool = (v, d) => (v === undefined ? d : v === true || v === "true");
  const appName = (a) => { const n = String(a || "").replace(/\.sc$/, ""); if (!/^[A-Za-z0-9_]+$/.test(n)) throw new Error(`bad app name: ${a}`); return n; };
  const appFile = (a) => path.join(K.P.SCRIPTS, appName(a) + ".sc");
  const falsy = (v) => v === null || /^(null|false|0|0\.0|''|\[\]|\{\}|)$/.test(String(v).trim());
  const scEsc = (s) => String(s).replace(/\\/g, "\\\\").replace(/'/g, "\\'").replace(/\r/g, "").replace(/\n/g, "\\n");
  const fmtFinding = (f) => `${f.level.toUpperCase()} ${f.line}:${f.col} [${f.rule}] ${f.message}`;
  const fmtPos = (p) => p.map((v) => +Number(v).toFixed(2)).join(" ");

  // ── scarpet over RCON (never auto-loads an app: `script in <app>` would load an unloaded one)
  async function sc(expr, app) {
    const c = app ? `script in ${appName(app)} run ${expr}` : `script run ${expr}`;
    if (Buffer.byteLength(c) > 1400) throw new Error(`expression too long for RCON (${Buffer.byteLength(c)} bytes) — use minecraft_app action:patch for big definitions`);
    const out = await K.cmd(c);
    const m = VAL_RE.exec(out);
    if (SC_ERR.test(out) || !m) return { ok: false, out: out.trim(), value: null };
    return { ok: true, out: out.trim(), value: m[1] };
  }
  const tick = async () => Number((await sc("tick_time()")).value);
  const loadedApps = async () => { const r = await sc("system_info('app_list')"); return r.ok ? r.value.replace(/^\[|\]$/g, "").split(",").map((s) => s.trim()).filter(Boolean) : []; };

  /** Run code of ANY length inside an app at the start of the next tick. RCON takes ≤1400 bytes, so the text goes into a
   *  scratch global of the console's script host in pieces, then schedule(0) → run('script in <app> run ' + text).
   *  Commands know no // comments (strip them first); newlines are fine. */
  async function longRun(app, code, { timeoutMs = 5000 } = {}) {
    const g = `global_mcp_buf_${Math.random().toString(36).slice(2, 8)}`;
    const target = app ? `script in ${appName(app)} run ` : "script run ";
    try {
      const r0 = await sc(`${g} = ''; ${g}_r = null; 'ok'`);
      if (!r0.ok) throw new Error(`scratch global: ${r0.out}`);
      let piece = "", pieces = 0;
      const flush = async () => {
        if (!piece) return;
        const r = await sc(`${g} = ${g} + '${piece}'; length(${g})`);
        if (!r.ok) throw new Error(`upload failed: ${r.out.slice(0, 300)}`);
        piece = ""; pieces++;
      };
      for (const ch of String(code)) { const e = scEsc(ch); if (Buffer.byteLength(piece + e) > 1250) await flush(); piece += e; }
      await flush();
      const len = Number((await sc(`length(${g})`)).value);
      if (len !== String(code).length) throw new Error(`uploaded ${len} of ${String(code).length} characters`);
      const q = await sc(`schedule(0, _() -> ${g}_r = run('${scEsc(target)}' + ${g})); 'queued'`);
      if (!q.ok) throw new Error(`schedule failed: ${q.out}`);
      const t0 = Date.now();
      while (Date.now() - t0 < timeoutMs) {
        await K.sleep(100);
        const raw = await K.cmd(`script run if(${g}_r == null, 'wait', encode_json(${g}_r))`);
        const v = VAL_RE.exec(raw)?.[1] ?? raw;
        if (v === "wait") continue;
        let res; try { res = JSON.parse(v); } catch { res = [null, [v], null]; }
        const msgs = (res[1] || []).map(String).join("\n");
        return { ok: !res[2] && !SC_ERR.test(msgs), out: [msgs, res[2]].filter(Boolean).join("\n"), pieces };
      }
      throw new Error("no result within the timeout (server lagging?)");
    } finally {
      await sc(`undef('${g}'); undef('${g}_r'); 'ok'`).catch(() => {});
    }
  }

  // ── the log
  const logSize = () => { try { return fs.statSync(K.P.LOG).size; } catch { return 0; } };
  function logText(from = null, maxBytes = 3e6) {
    try {
      const size = fs.statSync(K.P.LOG).size;
      const start = from === null || from > size ? Math.max(0, size - maxBytes) : from;
      const fd = fs.openSync(K.P.LOG, "r");
      try { const b = Buffer.alloc(size - start); fs.readSync(fd, b, 0, b.length, start); return b.toString("utf8"); } finally { fs.closeSync(fd); }
    } catch { return ""; }
  }
  /** Scarpet runtime errors of one app (or all) in the log, grouped with their call stack. (Load errors of `script load`
   *  go to the command output, not the log; errors inside scheduled calls are dropped by Carpet without a message.) */
  function logErrors(app, textBlock) {
    const entries = [];
    for (const l of textBlock.split(/\r?\n/)) {
      const m = /^\[(\d\d:\d\d:\d\d)\] \[([^\]]+)\/(\w+)\]: ?(.*)$/.exec(l);
      if (m) entries.push({ time: m[1], level: m[3], text: m[4] });
      else if (entries.length && l.trim()) entries[entries.length - 1].text += "\n" + l;
    }
    const out = [];
    let frames = [];
    const mine = (s) => !app || new RegExp(`\\[${app}\\]|\\bin ${app}\\b|\\b${app}\\.sc\\b`).test(s);
    for (const e of entries) {
      const f = /^\s*\.\.\. in (\S+)\[(\w+)\]\/(\d+):(\d+)/.exec(e.text);
      if (f) { frames.push({ fn: f[1], app: f[2], line: +f[3], col: +f[4] }); continue; }
      const isErr = /Callback failed|HERE>>|Error while evaluating|at line \d+, pos \d+|Unexpected exception while running Scarpet/i.test(e.text) || (e.level === "ERROR" && /scarpet|carpet\.script/i.test(e.text));
      if (isErr && (mine(e.text) || frames.some((x) => x.app === app))) {
        const ls = e.text.split("\n").filter((s) => s.trim());
        const java = ls.some((s) => /^\s+at /.test(s));
        const last = java ? `${ls[0].trim()} — ${(ls.find((s) => /^[\w.$]+(Exception|Error)\b/.test(s.trim())) || "").trim()}` : ls.pop() || e.text;
        const at = /in (\w+) at line (\d+), pos (\d+)/.exec(e.text);
        out.push({ time: e.time, app: at?.[1] || frames[0]?.app || app || null, message: last.trim().slice(0, 300), line: at ? +at[2] : frames[0]?.line, stack: frames.map((x) => `${x.fn}[${x.app}]/${x.line}:${x.col}`), code: (e.text.match(/.*HERE>>.*/) || [""])[0].trim().slice(0, 240) });
      }
      frames = [];
    }
    const grouped = new Map();
    for (const e of out) { const k = e.message + "|" + e.stack.join(","); const g = grouped.get(k); if (g) { g.count++; g.last = e.time; } else grouped.set(k, { ...e, count: 1, first: e.time, last: e.time }); }
    return [...grouped.values()].map(({ time, ...r }) => r);
  }

  // ── is anyone using the app?
  async function realPlayers() {
    const r = await sc("encode_json(map(filter(player('all'), _~'player_type' != 'fake'), (t = query(_, 'nbt', 'Tags'); [_~'name', pos(_), _~'dimension', if(t, parse_nbt(t), [])])))");
    try { return JSON.parse(r.value).map(([name, pos, dim, tags]) => ({ name, pos, dim, tags: Array.isArray(tags) ? tags : [] })).filter((p) => p.name !== K.BOT && !(K.isCrew && K.isCrew(p.name))); } catch { return []; }
  }
  function appTags(src) {
    const s = new Set();
    for (const re of [/modify\(\s*[^,()]+,\s*'tag'\s*,\s*'([\w.+-]+)'/g, /tag=!?([\w.+-]+)/g, /has_tag'\s*,\s*'([\w.+-]+)'/g]) for (const m of src.matchAll(re)) s.add(m[1]);
    return [...s];
  }
  /** World-map entries and zones whose notes mention <app>.sc are the app's area. */
  const appAreas = (app) => { const re = new RegExp(`\\b${app}\\.sc\\b`); return K.mapEntries().filter((e) => e && e.lo && e.hi && re.test(JSON.stringify(e))).map((e) => ({ name: e.name || e.id, lo: e.lo, hi: e.hi })); };
  async function busyCheck(app, { ignoreTags = [], margin = 8 } = {}) {
    const file = appFile(app);
    const src = fs.existsSync(file) ? fs.readFileSync(file, "utf8") : "";
    const res = { app, loaded: (await loadedApps()).includes(app), busy: false, reasons: [] };
    const reals = await realPlayers();
    res.real_players_online = reals.map((p) => p.name);
    if (res.loaded) {
      let st = null;
      if (/^status\s*\(\s*\)\s*->/m.test(src)) { const r = await sc("encode_json(status())", app); try { st = JSON.parse(r.value); } catch { st = r.ok ? r.value : null; } }
      else if (/\bglobal_state\b/.test(src)) st = { state: (await sc("global_state", app)).value };
      res.status = st;
      if (st && typeof st === "object" && (typeof st.busy === "boolean" || typeof st.idle === "boolean")) {
        res.explicit = true;   // the app says it itself ('busy' -> false / 'idle' -> true): trust it over every guess below
        res.busy = typeof st.busy === "boolean" ? st.busy : !st.idle;
        if (res.busy) res.reasons.push("status() says busy");
      } else if (st && typeof st === "object") {
        const state = st.state ?? st.phase ?? st.stage;
        if (typeof state === "string" && !IDLE_WORDS.test(state)) { res.busy = true; res.reasons.push(`state is '${state}'`); }
        for (const k of ["running", "active", "playing", "started", "in_game"]) if (st[k] === true) { res.busy = true; res.reasons.push(`${k} is true`); }
        const blob = JSON.stringify(st);
        const named = reals.filter((p) => new RegExp(`(^|[^A-Za-z0-9_])${p.name}([^A-Za-z0-9_]|$)`).test(blob)).map((p) => p.name);
        if (named.length) { res.busy = true; res.reasons.push(`status() names real players: ${named.join(", ")}`); }
      }
    }
    const tags = appTags(src).filter((t) => !ignoreTags.includes(t));
    res.tags = tags;
    const tagged = reals.filter((p) => p.tags.some((t) => tags.includes(t))).map((p) => `${p.name} (${p.tags.filter((t) => tags.includes(t)).join(",")})`);
    const observe = (msg) => { if (res.explicit) (res.observations ||= []).push(msg); else { res.busy = true; res.reasons.push(msg); } };
    if (tagged.length) observe(`real players carry the app's tags: ${tagged.join("; ")}`);
    const areas = appAreas(app);
    res.areas = areas.map((a) => a.name);
    const inArea = [];
    for (const p of reals) for (const a of areas) {
      if (!/overworld/.test(p.dim || "overworld")) continue;
      if ([0, 1, 2].every((i) => p.pos[i] >= Math.min(a.lo[i], a.hi[i]) - margin && p.pos[i] <= Math.max(a.lo[i], a.hi[i]) + margin + 1)) inArea.push(`${p.name} in ${a.name}`);
    }
    if (inArea.length) observe(`real players inside the app's area: ${[...new Set(inArea)].join("; ")}`);
    return res;
  }

  // ═════════════ minecraft_app ═════════════
  const lintFile = (file) => D.lintSource(fs.readFileSync(file, "utf8"), { name: path.basename(file, ".sc") });

  async function reload(app, args) {
    const file = appFile(app);
    if (!fs.existsSync(file)) throw new Error(`${K.rel(file)} does not exist`);
    const lint = lintFile(file);
    if (lint.errors && !args.force)
      return { refused: `lint found ${lint.errors} error(s) — a broken file UNLOADS the running app on reload (its state is lost and it stays down). Fix them first, or force:true.`, findings: lint.findings.filter((f) => f.level === "error").map(fmtFinding) };
    const busy = await busyCheck(app, { ignoreTags: args.ignore_tags || [] });
    if (busy.busy && !args.force) return { refused: "the app is in use — reloading resets its state (globals, running games)", reasons: busy.reasons, status: busy.status, hint: "wait until it is idle, or pass force:true" };
    const mark = logSize();
    const out = await K.cmd(`script load ${app}`);
    const failed = /Failed to add|HERE>>|Error while/i.test(out);
    await K.sleep(Math.max(0, Math.min(Number(args.watch_seconds ?? 4), 30)) * 1000);
    const loaded = (await loadedApps()).includes(app);
    return { app, reloaded: !failed && loaded, output: out.trim().slice(0, 1500), loaded, errors_after_load: logErrors(app, logText(mark)), lint: { errors: lint.errors, warnings: lint.warnings }, was_busy: busy.busy ? busy.reasons : undefined };
  }

  async function patch(app, args) {
    const file = appFile(app);
    if (!fs.existsSync(file)) throw new Error(`${K.rel(file)} does not exist`);
    let src = fs.readFileSync(file, "utf8");
    let code = args.code ?? (args.code_file ? fs.readFileSync(K.safePath(args.code_file), "utf8") : null);
    const fromFile = !code && args.function;
    if (fromFile) {
      const d = D.parseScarpet(src).tops.find((x) => x.name === args.function);
      if (!d) throw new Error(`${args.function}() is not defined at the top level of ${K.rel(file)}`);
      code = src.slice(d.pos, d.endPos);
    }
    if (!code) throw new Error("give code (or code_file) with one or more function definitions, or function (a name: pushes that definition from the .sc file)");
    code = String(code).trim();
    const P = D.parseScarpet(code);
    if (!P.tops.length) throw new Error("code must contain function definitions: name(args) -> (body); …");
    const stray = P.toks.filter((t, k) => P.depth[k] === 0 && t.v !== ";" && !P.tops.some((d) => k >= d.k && k <= d.end));
    if (stray.length) throw new Error(`code has statements outside function definitions (line ${stray[0].line}: '${stray[0].v}') — only definitions can be patched`);
    // names resolve against the whole app (its functions and imports) plus the patch
    const known = [...D.parseScarpet(src).tops.map((d) => d.name), ...[...src.matchAll(/import\(\s*'[^']*'((?:\s*,\s*'[^']*')*)\s*\)/g)].flatMap((m) => [...m[1].matchAll(/'([^']*)'/g)].map((x) => x[1]))];
    const lint = D.lintSource(code, { name: app, known });
    const errs = lint.findings.filter((f) => f.level === "error");
    if (errs.length && !args.force) return { refused: "the code has errors — nothing was sent", findings: errs.map(fmtFinding) };
    if (!(await loadedApps()).includes(app)) return { refused: `${app} is not loaded — load it with action:reload (patch changes a running app)` };
    const mark = logSize();
    const liveCode = D.stripComments(code).trim();
    const oneLine = `script in ${app} run ${liveCode}`;
    let live;
    if (!/\n/.test(liveCode) && Buffer.byteLength(oneLine) <= 1400) {
      const out = await K.cmd(oneLine);
      live = { ok: !SC_ERR.test(out), out: out.trim(), route: "direct" };
    } else {
      const r = await longRun(app, liveCode);
      live = { ok: r.ok, out: r.out.trim(), route: `chunked (${r.pieces} RCON pieces → schedule(0) → run('script in ${app} run …'))` };
    }
    const res = { app, functions: P.tops.map((d) => d.name), bytes: Buffer.byteLength(code), live: live.ok ? "applied" : "FAILED", route: live.route, output: live.out.slice(0, 800) };
    if (!live.ok) return res;
    await K.sleep(Math.max(0, Math.min(Number(args.watch_seconds ?? 2), 30)) * 1000);
    res.errors_after = logErrors(app, logText(mark));
    const warn = lint.findings.filter((f) => f.level !== "note");
    if (warn.length) res.lint = warn.map(fmtFinding).slice(0, 12);
    if (fromFile) { res.persisted = "already in the file (pushed from it)"; return res; }
    if (!bool(args.persist, true)) { res.persisted = false; return res; }
    const bak = path.join(K.P.DATA, "app-backups", `${app}.sc.bak`);
    fs.mkdirSync(path.dirname(bak), { recursive: true });
    fs.writeFileSync(bak, src);
    const changes = [];
    for (const d of P.tops) {
      const piece = code.slice(d.pos, d.endPos).replace(/;?\s*$/, ";");
      const cur = D.parseScarpet(src).tops.find((x) => x.name === d.name);
      if (cur) { src = src.slice(0, cur.pos) + piece + src.slice(cur.endPos); changes.push(`replaced ${d.name}() at line ${cur.line}`); }
      else { src = src.replace(/\s*$/, "\n") + "\n" + piece + "\n"; changes.push(`appended ${d.name}()`); }
    }
    const brk = D.lintSource(src, { name: app }).findings.filter((f) => f.level === "error" && ["brackets", "string", "semicolon"].includes(f.rule));
    if (brk.length) { res.persisted = false; res.persist_error = `the patched file would not load — left unchanged: ${brk.map(fmtFinding).slice(0, 3).join(" | ")}`; return res; }
    fs.writeFileSync(file + ".tmp", src);
    fs.renameSync(file + ".tmp", file);
    res.persisted = changes;
    res.backup = K.rel(bak);
    return res;
  }

  async function app(args) {
    const act = args.action;
    if (act === "lint") {
      let files;
      if (args.all) files = fs.readdirSync(K.P.SCRIPTS).filter((f) => f.endsWith(".sc")).sort().map((f) => path.join(K.P.SCRIPTS, f));
      else if (args.file) files = [K.safePath(args.file)];
      else if (args.app) files = [appFile(args.app)];
      else throw new Error("give app, file or all:true");
      const levels = args.level === "error" ? ["error"] : args.level === "warning" ? ["error", "warning"] : ["error", "warning", "note"];
      const out = files.map((f) => {
        const r = lintFile(f);
        const shown = r.findings.filter((x) => levels.includes(x.level));
        return { file: K.rel(f), errors: r.errors, warnings: r.warnings, notes: r.notes, findings: shown.slice(0, files.length > 1 ? 15 : 200).map(fmtFinding), ...(shown.length > 15 && files.length > 1 ? { more: shown.length - 15 } : {}) };
      });
      if (files.length === 1) return out[0];
      return { files: out.length, errors: out.reduce((a, r) => a + r.errors, 0), warnings: out.reduce((a, r) => a + r.warnings, 0), notes: out.reduce((a, r) => a + r.notes, 0), apps: out.filter((r) => r.findings.length) };
    }
    if (act === "status") return args.app ? await busyCheck(appName(args.app), { ignoreTags: args.ignore_tags || [] }) : { loaded: await loadedApps() };
    if (act === "reload") return await reload(appName(args.app), args);
    if (act === "patch") return await patch(appName(args.app), args);
    if (act === "errors") {
      const a = args.app ? appName(args.app) : null;
      const errs = logErrors(a, logText());
      return { app: a || "all", errors: errs.slice(-(Number(args.limit) || 20)), total: errs.length };
    }
    throw new Error("action: lint | status | reload | patch | errors");
  }

  // ═════════════ minecraft_playtest ═════════════
  async function playtest(args) {
    const t0 = Date.now();
    const deadline = t0 + Math.min(Math.max(Number(args.timeout_seconds) || 120, 5), 600) * 1000;
    const app = args.app ? appName(args.app) : null;
    const stopOnFail = bool(args.stop_on_fail, true);
    const timeline = [], vars = {}, uuids = {}, spawned = [], restores = [], touchedApps = new Set(app ? [app] : []);
    const preexisting = new Set();   // world files of a name the server knew before the test are kept
    let failed = null, passed = 0, failedCount = 0;
    const mark = logSize();
    const tick0 = await tick();
    const note = async (ok, what, out) => {
      const s = +((Date.now() - t0) / 1000).toFixed(1), t = (await tick().catch(() => tick0)) - tick0;
      timeline.push(`[+${s}s t+${t}] ${ok === null ? "·" : ok ? "✓" : "✗"} ${what}${out !== undefined && out !== "" ? " → " + String(out).slice(0, 300) : ""}`);
    };
    const subst = (s) => String(s).replace(/\$\{uuid:(\w+)\}/g, (_, n) => uuids[n] || `<no uuid for ${n}>`).replace(/\$\{(\w+)\}/g, (m, n) => (n in vars ? vars[n] : m));
    const ensureTime = () => { if (Date.now() > deadline) throw new Error("test timeout"); };
    const mine = (n) => { if (!spawned.includes(n)) throw new Error(`${n} is not one of this test's fake players`); };

    // safety first
    const names = (args.players || []).map((p) => p.name);
    for (const n of names) {
      if (!/^[A-Za-z0-9_]{3,16}$/.test(n)) throw new Error(`bad fake player name: ${n}`);
      if (n === K.BOT || (K.isCrew && K.isCrew(n))) throw new Error(`${n} is the bot/crew — use test names like Test_A`);
    }
    const clash = (await realPlayers()).filter((p) => names.includes(p.name));
    if (clash.length) throw new Error(`${clash.map((p) => p.name).join(", ")} is a real player online — pick other test names`);
    if (app && bool(args.require_idle, true)) {
      if (!(await loadedApps()).includes(app)) throw new Error(`${app} is not loaded`);
      const b = await busyCheck(app, { ignoreTags: args.ignore_tags || [] });
      if (b.busy && !args.force) return { refused: `${app} is in use — a test would disturb real players`, reasons: b.reasons, status: b.status, hint: "wait until it is idle (or force:true)" };
      await note(null, `${app} idle check`, JSON.stringify(b.status ?? "no status()").slice(0, 200));
    }
    const records = (args.cleanup?.records || []).map((r) => ({ ...r }));
    for (const r of records) {
      if (r.file) { r.fileAbs = K.safePath(r.file); const j = K.readJSON(r.fileAbs, null); r.fileBefore = {}; for (const p of r.restore || []) r.fileBefore[p] = j ? D.getPath(j, p) : undefined; }
      if (r.app && r.global) {
        r.memBefore = {};
        touchedApps.add(appName(r.app));
        for (const p of r.restore || []) { const x = await sc(`encode_json(${D.accessor(r.global, p)})`, r.app); r.memBefore[p] = x.ok ? x.value : "null"; }
      }
    }
    const dataDirs = () => [...touchedApps].map((a) => path.join(K.P.SCRIPTS, `${a}.data`)).filter((d) => fs.existsSync(d));
    const before = new Set();
    for (const d of dataDirs()) for (const f of D.walk(d)) before.add(f);

    async function setGlobal(a, name, value, restore) {
      if (!/^global_\w+$/.test(name)) throw new Error(`${name}: only global_ variables can be set`);
      touchedApps.add(appName(a));
      if (restore) { const o = await sc(`encode_json(${name})`, a); if (o.ok) restores.unshift({ app: a, name, json: o.value }); }
      const v = typeof value === "string" ? subst(value) : JSON.stringify(value);
      const r = await sc(`${name} = ${v}`, a);
      if (!r.ok) throw new Error(`${name} = ${v}: ${r.out}`);
      return r.value;
    }
    async function spawn(p) {
      const known = K.readJSON(path.join(K.P.SERVER, "usercache.json"), []).filter((e) => e.name === p.name).map((e) => e.uuid);
      for (const id of known) for (const f of D.walk(K.P.WORLD, 3)) if (path.basename(f).startsWith(id)) preexisting.add(f);
      const pos = p.pos || p.at;
      if (!Array.isArray(pos) || pos.length !== 3) throw new Error(`${p.name}: pos [x,y,z] is required`);
      if ((await sc(`p = player('${p.name}'); if(p, p~'player_type', 'none')`)).value === "fake") { await K.cmd(`player ${p.name} kill`); await K.sleep(300); }
      const gm = p.gamemode || "creative", dim = p.dimension || "minecraft:overworld";
      const out = await K.cmd(`player ${p.name} spawn at ${fmtPos(pos)} facing ${Number(p.yaw ?? 0)} ${Number(p.pitch ?? 0)} in ${dim} in ${gm}`);
      if (/Unknown|Incorrect|Invalid|already|Could not|can't|isn't/i.test(out)) throw new Error(`spawn ${p.name}: ${out.trim()}`);
      spawned.push(p.name);
      for (let k = 0; k < 40 && !uuids[p.name]; k++) {
        await K.sleep(150);
        const r = await sc(`p = player('${p.name}'); if(p, p~'uuid', null)`);
        if (r.ok && r.value !== "null") uuids[p.name] = r.value.trim();
      }
      if (!uuids[p.name]) throw new Error(`${p.name} did not appear within 6 s`);
      await K.cmd(`gamemode ${gm} ${p.name}`);
      return `${p.name} at ${fmtPos(pos)} (${gm})`;
    }
    async function check(a) {
      const kind = a.assert, P = a.player;
      if (P && kind !== "online") mine(P);
      if (kind === "scarpet") {
        const r = await sc(subst(a.expr), a.app ?? app);
        if (!r.ok) return [false, `error: ${r.out.slice(0, 200)}`];
        const [ok, why] = D.checkValue(r.value, a, subst);
        return [ok, `${a.expr} = ${r.value}${ok ? "" : " (" + why + ")"}`];
      }
      if (kind === "position") {
        const r = await sc(`p = player('${P}'); if(p, pos(p), null)`);
        if (!r.ok || r.value === "null") return [false, `${P} is not online`];
        const p = r.value.replace(/^\[|\]$/g, "").split(",").map(Number), q = a.pos.map(Number);
        const d = Math.hypot(p[0] - q[0], a.horizontal ? 0 : p[1] - q[1], p[2] - q[2]), rad = Number(a.radius ?? 1.5);
        return [d <= rad, `${P} at ${fmtPos(p)}, ${d.toFixed(2)} from ${fmtPos(q)} (radius ${rad})`];
      }
      if (kind === "gamemode") { const r = await sc(`p = player('${P}'); if(p, p~'gamemode', null)`); return [r.value === String(a.equals), `${P} gamemode ${r.value}${r.value === String(a.equals) ? "" : " (expected " + a.equals + ")"}`]; }
      if (kind === "tag") {
        const r = await sc(`p = player('${P}'); if(p, query(p, 'has_tag', '${a.tag}'), 'offline')`);
        return [r.value === String(a.present !== false), `${P} tag ${a.tag}: ${r.value === "true" ? "present" : r.value === "offline" ? "player offline" : "absent"}`];
      }
      if (kind === "item") {
        const item = String(a.item).replace(/^minecraft:/, "");
        const r = a.slot !== undefined
          ? await sc(`p = player('${P}'); s = inventory_get(p, ${Number(a.slot)}); if(s && s:0 == '${item}', s:1, 0)`)
          : await sc(`p = player('${P}'); c = 0; for(range(inventory_size(p)), s = inventory_get(p, _); if(s && s:0 == '${item}', c += s:1)); c`);
        const n = Number(r.value) || 0;
        if (a.absent) return [n === 0, `${P} has ${n} ${item}`];
        const min = Number(a.count ?? 1);
        return [a.exact ? n === min : n >= min, `${P} has ${n} ${item}${a.slot !== undefined ? " in slot " + a.slot : ""} (want ${a.exact ? "" : "≥"}${min})`];
      }
      if (kind === "online") { const r = await sc(`player('${P}') != null`); return [r.value === String(a.present !== false), `${P} ${r.value === "true" ? "online" : "offline"}`]; }
      if (kind === "log") {
        const hit = logText(mark).split(/\r?\n/).find((l) => new RegExp(a.matches).test(l));
        return [a.absent ? !hit : !!hit, hit ? `log: ${hit.slice(0, 200)}` : `no log line matches /${a.matches}/`];
      }
      throw new Error(`unknown assert '${kind}' (scarpet | position | gamemode | tag | item | online | log)`);
    }
    async function waitTicks(n) {
      const s = await tick();
      for (;;) { ensureTime(); const t = await tick(); if (t - s >= n) return t - s; await K.sleep(Math.max(20, Math.min(250, (n - (t - s)) * 50 - 20))); }
    }
    async function waitUntil(expr, a, timeoutTicks, pollMs) {
      const s = await tick();
      for (;;) {
        ensureTime();
        const r = await sc(subst(expr), a);
        if (r.ok && !falsy(r.value)) return [true, `${expr} = ${r.value}`];
        if ((await tick()) - s > timeoutTicks) return [false, `timeout after ${timeoutTicks} ticks, last: ${String(r.ok ? r.value : r.out).slice(0, 200)}`];
        await K.sleep(pollMs);
      }
    }
    /** schedule(0) inside the app: the code runs in the app's own tick (events of the app are not delivered to itself there). */
    async function inTick(expr, a) {
      const g = "global_mcp_pt";
      if (a) touchedApps.add(appName(a));
      const q = await sc(`${g} = null; schedule(0, _() -> (${g} = ['start']; ${g} = ['done', str((${subst(expr)}))])); 'queued'`, a);
      if (!q.ok) return { ok: false, out: q.out };
      for (let k = 0; k < 60; k++) {
        await K.sleep(60);
        const r = await sc(g, a);
        if (r.ok && /^\[done, /.test(r.value)) { await sc(`undef('${g}'); 'ok'`, a); return { ok: true, value: r.value.replace(/^\[done, /, "").replace(/\]$/, "") }; }
        if (r.ok && r.value === "[start]" && k > 3) break;
      }
      const r = await sc(g, a);
      await sc(`undef('${g}'); 'ok'`, a);
      return { ok: false, out: r.value === "[start]" ? "the code threw inside the tick — Carpet drops errors of scheduled calls without a message; run the same expression without in_tick to see it" : "the tick never ran it (server lagging?)" };
    }

    async function cleanupTest() {
      const c = args.cleanup || {}, done = [];
      try {
        for (const x of c.commands || []) { const out = await K.cmd(subst(x)); done.push(`/${x} → ${out.trim().slice(0, 120)}`); }
        if (c.wait_until) {
          const w = typeof c.wait_until === "string" ? { expr: c.wait_until } : c.wait_until;
          const [ok, msg] = await waitUntil(w.expr, w.app ?? app, Number(w.timeout ?? 400), 200).catch((e) => [false, e.message]);
          done.push(`wait_until ${ok ? "ok" : "FAILED"}: ${msg}`);
        }
      } catch (e) { done.push(`cleanup commands: ${e.message}`); }
      for (const n of spawned) if ((await sc(`p = player('${n}'); if(p, p~'player_type', 'gone')`)).value === "fake") await K.cmd(`player ${n} kill`);
      for (let k = 0; k < 30 && spawned.length; k++) { if ((await sc(`length(filter([${spawned.map((n) => `'${n}'`).join(",")}], player(_)))`)).value === "0") break; await K.sleep(200); }
      if (spawned.length) done.push(`killed ${spawned.join(", ")}`);
      for (const r of restores) { const x = await sc(`${r.name} = decode_json('${scEsc(r.json)}')`, r.app); done.push(`restored ${r.app}:${r.name} = ${x.ok ? x.value : "FAILED " + x.out.slice(0, 100)}`); }
      const fakes = spawned;
      for (const r of records) {
        if (r.app && r.global) {
          let j = null; try { j = JSON.parse((await sc(`encode_json(${r.global})`, r.app)).value); } catch {}
          if (j) for (const h of D.findRecords(j, fakes)) {
            const last = h[h.length - 1], key = typeof last === "number" ? last : `'${scEsc(last)}'`;
            const x = await sc(`delete(${D.accessor(r.global, h.slice(0, -1))}, ${key}); 'ok'`, r.app);
            done.push(`${r.app}:${r.global}:${h.join(":")} removed${x.ok ? "" : " FAILED " + x.out.slice(0, 80)}`);
          }
          for (const [p, v] of Object.entries(r.memBefore || {})) { const x = await sc(`${D.accessor(r.global, p)} = decode_json('${scEsc(v)}')`, r.app); done.push(`${r.app}:${r.global}:${p} restored to ${v}${x.ok ? "" : " FAILED"}`); }
        }
        if (r.fileAbs && fs.existsSync(r.fileAbs)) {
          const j = K.readJSON(r.fileAbs, null);
          if (j) {
            const hits = D.findRecords(j, fakes);
            for (const h of hits) { D.removeAt(j, h); done.push(`${K.rel(r.fileAbs)}: ${h.join(".")} removed`); }
            for (const [p, v] of Object.entries(r.fileBefore || {})) if (v !== undefined && JSON.stringify(D.getPath(j, p)) !== JSON.stringify(v)) { D.setPath(j, p, v); done.push(`${K.rel(r.fileAbs)}: ${p} restored to ${JSON.stringify(v)}`); }
            if (hits.length || Object.keys(r.fileBefore || {}).length) fs.writeFileSync(r.fileAbs, JSON.stringify(j, null, 2));
          }
        }
      }
      if (c.data_files !== false && fakes.length) {
        const keys = [...fakes, ...fakes.map((n) => uuids[n]).filter(Boolean)];
        for (const d of dataDirs()) for (const f of D.walk(d)) {
          const base = path.basename(f);
          const byName = keys.some((k) => new RegExp(`(^|[^A-Za-z0-9])${k}([^A-Za-z0-9]|$)`).test(base));
          let newWithName = false;
          if (!byName && !before.has(f)) { try { const t = fs.statSync(f).size < 2e6 ? fs.readFileSync(f, "utf8") : ""; newWithName = keys.some((k) => t.includes(k)); } catch {} }
          if (byName || newWithName) { fs.rmSync(f, { force: true }); done.push(`deleted ${K.rel(f)}`); }
          else { try { if (fs.statSync(f).mtimeMs >= t0 && keys.some((k) => fs.readFileSync(f, "utf8").includes(k))) done.push(`NOTE ${K.rel(f)} still mentions a fake player — add it to cleanup.records`); } catch {} }
        }
      }
      if (c.player_files !== false) {
        await K.sleep(500);
        const online = (await sc(`encode_json(map(player('all'), _~'uuid'))`)).value || "";
        for (const id of fakes.map((n) => uuids[n]).filter(Boolean)) {
          if (online.includes(id)) { done.push(`${id} still online — its files were kept`); continue; }
          for (const f of D.walk(K.P.WORLD, 3)) if (path.basename(f).startsWith(id)) {
            if (preexisting.has(f)) { done.push(`kept ${K.rel(f)} (it existed before the test)`); continue; }
            fs.rmSync(f, { force: true }); done.push(`deleted ${K.rel(f)}`);
          }
        }
      }
      for (const a of touchedApps) await sc("undef('global_mcp_pt'); 'ok'", a).catch(() => {});
      return done;
    }

    let cleanup;
    try {
      for (const [n, v] of Object.entries(args.globals || {})) {
        if (!app) throw new Error("globals need app");
        await note(true, `set ${n} = ${await setGlobal(app, n, v, true)} (restored at the end)`);
      }
      for (const p of args.players || []) await note(true, `spawn ${await spawn(p)}`);
      const steps = args.steps || [];
      for (let i = 0; i < steps.length; i++) {
        ensureTime();
        const s = steps[i], label = s.label ? `${s.label}: ` : "";
        const fail = (msg) => { failedCount++; failed ??= `step ${i + 1}: ${label}${msg}`; };
        try {
          if (s.wait !== undefined) await note(true, `${label}wait ${await waitTicks(Number(s.wait))} ticks`);
          else if (s.wait_until !== undefined) {
            const [ok, msg] = await waitUntil(s.wait_until, s.app ?? app, Number(s.timeout ?? s.timeout_ticks ?? 200), Number(s.poll_ms ?? 150));
            await note(ok, `${label}wait_until ${msg}`);
            if (ok) passed++; else { fail("wait_until timed out"); if (stopOnFail) break; }
          } else if (s.player !== undefined && s.do !== undefined) {
            mine(s.player);
            const act = subst(s.do);
            if (!PLAYER_ACTIONS.test(act)) throw new Error(`player action '${act}' not allowed (move/look/turn/jump/sneak/unsneak/sprint/unsprint/use/attack/stop/hotbar/drop/dropStack/swapHands/mount/dismount)`);
            const out = await K.cmd(`player ${s.player} ${act}`);
            if (/Unknown|Incorrect|Invalid/i.test(out)) throw new Error(out.trim());
            if (s.ticks) { await waitTicks(Number(s.ticks)); await K.cmd(`player ${s.player} stop`); }
            await note(true, `${label}${s.player} ${act}${s.ticks ? ` for ${s.ticks} ticks, then stop` : ""}`);
          } else if (s.spawn) await note(true, `${label}spawn ${await spawn(s.spawn)}`);
          else if (s.kill !== undefined) { mine(s.kill); await K.cmd(`player ${s.kill} kill`); await note(true, `${label}kill ${s.kill}`); }
          else if (s.tp !== undefined) {
            mine(s.tp);
            const out = await K.cmd(`tp ${s.tp} ${fmtPos(s.pos)}${s.yaw !== undefined ? ` ${s.yaw} ${s.pitch ?? 0}` : ""}`);
            await note(!/Unknown|Incorrect|No entity/i.test(out), `${label}tp ${s.tp} ${fmtPos(s.pos)}`, out.trim());
          } else if (s.command !== undefined || s.commands !== undefined) {
            let stop = false;
            for (const c of s.commands || [s.command]) {
              const out = (await K.cmd(subst(c))).trim();
              const ok = s.expect ? new RegExp(s.expect).test(out) : !/Unknown or incomplete|Incorrect argument|HERE>>/.test(out);
              await note(ok, `${label}/${subst(c)}`, out);
              if (!ok) { fail(`/${c}`); if (stopOnFail) { stop = true; break; } } else if (s.expect) passed++;
            }
            if (stop) break;
          } else if (s.scarpet !== undefined) {
            const a = s.app ?? app;
            const r = s.in_tick ? await inTick(s.scarpet, a) : await sc(subst(s.scarpet), a);
            if (s.save && r.ok) vars[s.save] = r.value;
            let ok = r.ok, why = r.ok ? r.value : r.out;
            if (r.ok && s.expect) { const [o, w] = D.checkValue(r.value, s.expect, subst); ok = o; if (!o) why += ` (${w})`; }
            await note(ok, `${label}${s.in_tick ? "[in tick] " : ""}${a ? a + ": " : ""}${s.scarpet}`, why);
            if (!ok) { fail("scarpet"); if (stopOnFail) break; } else if (s.expect) passed++;
          } else if (s.set !== undefined) {
            for (const [n, v] of Object.entries(s.set)) await note(true, `${label}set ${n} = ${await setGlobal(s.app ?? app, n, v, !!s.restore)}${s.restore ? " (restored at the end)" : ""}`);
          } else if (s.assert !== undefined) {
            const [ok, msg] = await check(s);
            await note(ok, `${label}assert ${s.assert}: ${msg}`);
            if (ok) passed++; else { fail(`assert ${s.assert}: ${msg}`); if (stopOnFail) break; }
          } else if (s.note !== undefined) await note(null, s.note);
          else throw new Error(`unknown step ${JSON.stringify(s).slice(0, 120)}`);
        } catch (e) {
          fail(e.message);
          await note(false, `${label}${e.message}`);
          if (stopOnFail || e.message === "test timeout") break;
        }
      }
    } catch (e) {
      failed ??= e.message;
      await note(false, e.message);
    } finally {
      cleanup = await cleanupTest();
    }
    const appErrors = logErrors(null, logText(mark)).filter((e) => !app || e.app === app || touchedApps.has(e.app));
    if (appErrors.length && bool(args.fail_on_app_errors, true)) failed ??= `app errors in the log: ${appErrors[0].message}`;
    let after;
    if (app) { const b = await busyCheck(app, { ignoreTags: args.ignore_tags || [] }).catch(() => null); if (b) after = { busy: b.busy, status: b.status, reasons: b.reasons }; }
    return {
      name: args.name || "playtest", result: failed ? "FAIL" : "PASS", ...(failed ? { failed } : {}),
      assertions: { passed, failed: failedCount }, seconds: +((Date.now() - t0) / 1000).toFixed(1),
      timeline, ...(Object.keys(vars).length ? { saved: vars } : {}), app_errors: appErrors, cleanup, app_after: after,
    };
  }

  // clients that send everything as text
  const norm = (a) => {
    a = { ...a };
    for (const k of ["globals", "cleanup", "players", "steps", "ignore_tags"]) if (typeof a[k] === "string" && /^\s*[\[{]/.test(a[k])) { try { a[k] = JSON.parse(a[k]); } catch {} }
    for (const k of ["all", "persist", "require_idle", "stop_on_fail", "fail_on_app_errors"]) if (a[k] === "true" || a[k] === "false") a[k] = a[k] === "true";
    for (const k of ["watch_seconds", "timeout_seconds"]) if (typeof a[k] === "string" && /^\d+(\.\d+)?$/.test(a[k])) a[k] = Number(a[k]);
    return a;
  };
  return {
    minecraft_app: async (args) => K.text(await app(norm(args))),
    minecraft_playtest: async (args) => K.text(await playtest(norm(args))),
  };
}
