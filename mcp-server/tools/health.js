/**
 * Server health: minecraft_watchdog — what makes the server slow, an incident log, disk + memory, backups.
 *
 * The in-server half is scarpet-apps/watchdog.sc (copied into the world and loaded on first use). It reads the tick
 * times once a second (a few microseconds), opens an incident when ticks stay slow, names the culprit with an entity
 * census (by type, chunk and tag), tells the ops online once and removes only obvious junk (1000+ dropped items in
 * one chunk). It works with no AI connected.
 * This half adds what the game can't see: free disk, swap, the JVM's busiest threads, one incident log
 * (data/watchdog/incidents.jsonl), `clawdblock.py backup`, and a background check every 60 s (one MCP process at a
 * time) that tells the ops in chat when the disk runs low — once per level, never more than once per 10 minutes.
 * Settings: "watchdog" in clawdblock.json, e.g. {"disk_warn_gb": 5, "disk_crit_gb": 2, "loop": false}. MC_WATCHDOG=0
 * turns the background check off.
 */
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const GB = 1073741824, MB = 1048576;
const fmt = (n) => (n == null ? "?" : n >= 10 * GB ? (n / GB).toFixed(1) + " GB" : n >= GB ? (n / GB).toFixed(2) + " GB" : Math.round(n / MB) + " MB");
const localIso = (d = new Date()) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 19);
const bool = (v) => v === true || v === "true";

export const tools = [
  {
    name: "minecraft_watchdog",
    description: "Server health and lag hunting. action status (default): tick time now (avg/P95/P99) and over the last minute, paused?, heap, swap, disk, any open lag incident. heavy: WHAT IS HEAVY RIGHT NOW — entity census by type, by chunk (a server-cost score plus the builds there), by scoreboard tag (and which app or generator uses that tag), stacks of identical copies on one block (a leak), sharp rises since the last quiet census, force-loaded chunks, apps that run every tick; threads:true adds the busiest JVM threads (3 s sample). incidents (limit, kind, full): the log of lag / freeze / stacked / junk / disk / memory / backup / alert events. disk (refresh): disk + memory breakdown and what could be freed, with sizes — deletes nothing. backup (dry_run, keep=3, include_ledger, dest): zip the world with rotation; refuses when free space is under 3x the world. check (dry_run): run the background disk check now. See reference/watchdog.md.",
    inputSchema: { type: "object", properties: {
      action: { type: "string", enum: ["status", "heavy", "incidents", "disk", "backup", "check"] },
      top: { type: "number", description: "heavy: how many chunks to detail (default 8)" },
      threads: { type: "boolean", description: "heavy: add a 3 s CPU sample of the JVM threads (needs jcmd from a JDK)" },
      limit: { type: "number" }, kind: { type: "string", description: "incidents: lag | lag_end | freeze | stacked | junk | alert | disk_low | disk_ok | memory | backup" },
      full: { type: "boolean", description: "incidents: keep the whole census in each lag incident" },
      refresh: { type: "boolean", description: "disk: measure the folders again now" },
      dry_run: { type: "boolean" }, keep: { type: "number", description: "backup: how many zips to keep (default 3)" },
      include_ledger: { type: "boolean", description: "backup: also the Ledger database (left out by default: it is big)" },
      dest: { type: "string", description: "backup: another folder or disk for the zips" },
      simulate_free_mb: { type: "number", description: "backup, TESTS ONLY: pretend this much space is free (to test the refusal)" } } },
  },
];

export function handlers(K, ctx) {
  const WD_DIR = path.join(K.P.DATA, "watchdog");
  const STATE = path.join(WD_DIR, "state.json");
  const LOG = path.join(WD_DIR, "incidents.jsonl");
  const APP_SRC = path.join(K.P.ROOT, "scarpet-apps", "watchdog.sc");
  const APP_LOG = path.join(K.P.SCRIPTS, "watchdog.data", "incidents.txt");
  const CFG = { disk_warn_gb: 2, disk_crit_gb: 1, disk_ok_gb: 2.5, repeat_hours: 6, min_gap_min: 10, loop_s: 60, lease_s: 180, loop: true,
    ...((ctx.config.RAW && ctx.config.RAW.watchdog) || {}) };

  // ───────────── shared state: several MCP processes (AI clients) may watch one server ─────────────
  const loadState = () => K.readJSON(STATE, {});
  function saveState(s) { fs.mkdirSync(WD_DIR, { recursive: true }); fs.writeFileSync(STATE + ".tmp", JSON.stringify(s, null, 1)); fs.renameSync(STATE + ".tmp", STATE); }
  const withState = (fn) => { fs.mkdirSync(WD_DIR, { recursive: true }); return K.withLock(STATE + ".lock", async () => { const s = loadState(); const r = await fn(s); saveState(s); return r; }, { stale: 30000, wait: 10000 }); };

  function logIncident(o) {
    fs.mkdirSync(WD_DIR, { recursive: true });
    try { if (fs.statSync(LOG).size > 4 * MB) fs.renameSync(LOG, LOG + ".old"); } catch {}
    fs.appendFileSync(LOG, JSON.stringify({ time: localIso(), t: Date.now(), source: "mcp", ...o }) + "\n");
  }
  // the app appends JSON lines to its own file (so it works with no AI connected); copy new lines into the one log
  function mirrorApp(s) {
    let st;
    try { st = fs.statSync(APP_LOG); } catch { return 0; }
    const m = s.app_log || { ino: 0, off: 0 };
    if (st.ino !== m.ino || st.size < m.off) { m.ino = st.ino; m.off = 0; }
    s.app_log = m;
    if (st.size <= m.off) return 0;
    const len = Math.min(st.size - m.off, 4 * MB), b = Buffer.alloc(len);
    const fd = fs.openSync(APP_LOG, "r");
    try { fs.readSync(fd, b, 0, len, m.off); } finally { fs.closeSync(fd); }
    const end = b.lastIndexOf(10);
    if (end < 0) return 0;
    const lines = b.subarray(0, end).toString("utf8").split("\n").map((l) => l.trim()).filter((l) => l.startsWith("{"));
    m.off += end + 1;
    if (lines.length) { fs.mkdirSync(WD_DIR, { recursive: true }); fs.appendFileSync(LOG, lines.join("\n") + "\n"); }
    return lines.length;
  }
  function tail(n) {
    let t = "";
    try { const st = fs.statSync(LOG), len = Math.min(st.size, 3 * MB), b = Buffer.alloc(len), fd = fs.openSync(LOG, "r"); fs.readSync(fd, b, 0, len, st.size - len); fs.closeSync(fd); t = b.toString("utf8"); } catch { return []; }
    return t.split("\n").slice(-n - 1).map((l) => { try { return JSON.parse(l); } catch { return null; } }).filter(Boolean);
  }

  // ───────────── measurements (macOS, Linux, Windows) ─────────────
  function diskFree(p = K.P.SERVER) { const s = fs.statfsSync(fs.existsSync(p) ? p : K.P.ROOT); return { free: s.bavail * s.bsize, total: s.blocks * s.bsize }; }
  async function size(p) {
    let total = 0;
    const stack = [p];
    if (!fs.existsSync(p)) return null;
    while (stack.length) {
      const d = stack.pop();
      let ents;
      try { ents = await fs.promises.readdir(d, { withFileTypes: true }); } catch { try { total += (await fs.promises.stat(d)).size; } catch {} continue; }
      for (const e of ents) {
        const f = path.join(d, e.name);
        if (e.isDirectory()) stack.push(f);
        else if (e.isFile()) { try { total += (await fs.promises.stat(f)).size; } catch {} }
      }
    }
    return total;
  }
  async function memory() {
    const m = { ram: `${fmt(os.totalmem() - os.freemem())} of ${fmt(os.totalmem())} used` };
    if (process.platform === "darwin") {
      const r = await K.run("sysctl", ["-n", "vm.swapusage"], { timeout: 5000 });
      const g = (k) => { const x = new RegExp(k + "\\s*=\\s*([\\d.]+)M").exec(r.stdout); return x ? +x[1] * MB : null; };
      m.swap_total = g("total"); m.swap_used = g("used");
    } else if (process.platform === "linux") {
      try {
        const t = fs.readFileSync("/proc/meminfo", "utf8");
        const g = (k) => { const x = new RegExp(k + ":\\s+(\\d+) kB").exec(t); return x ? +x[1] * 1024 : null; };
        m.swap_total = g("SwapTotal"); m.swap_used = m.swap_total != null ? m.swap_total - g("SwapFree") : null;
      } catch {}
    }
    if (m.swap_total) m.swap = `${fmt(m.swap_used)} of ${fmt(m.swap_total)} used`;
    return m;
  }
  async function serverProc() {
    let pid = null;
    try { pid = +fs.readFileSync(path.join(K.P.SERVER, "server.pid"), "utf8").trim(); process.kill(pid, 0); } catch { pid = null; }
    if (!pid && process.platform !== "win32") {
      const r = await K.run("pgrep", ["-f", "fabric-server-launch"], { timeout: 5000 });
      pid = +(r.stdout.split(/\s+/).filter(Boolean)[0] || 0) || null;
    }
    if (!pid) return null;
    let rss = null;
    if (process.platform !== "win32") { const r = await K.run("ps", ["-o", "rss=", "-p", String(pid)], { timeout: 5000 }); rss = parseInt(r.stdout, 10) * 1024 || null; }
    return { pid, rss };
  }
  const scJSON = (out) => {
    const m = /=\s*([[{][\s\S]*[\]}])\s*(?:\([^()]*\))?\s*$/.exec(out);
    if (!m) throw new Error("scarpet: " + String(out).slice(0, 300));
    return JSON.parse(m[1]);
  };
  // call the watchdog app; install + load it only when the reply is not a value
  let installed = false;
  async function app(expr) {
    let out = await K.cmd(`script in watchdog run ${expr}`);
    if (!/^\s*=/.test(out) && !/Error while evaluating/.test(out)) {
      const dst = path.join(K.P.SCRIPTS, "watchdog.sc");
      if (!fs.existsSync(dst) && fs.existsSync(APP_SRC)) { fs.mkdirSync(K.P.SCRIPTS, { recursive: true }); fs.copyFileSync(APP_SRC, dst); installed = true; }
      await K.cmd("script load watchdog").catch(() => {});
      out = await K.cmd(`script in watchdog run ${expr}`);
    }
    return out;
  }
  async function tickQuery() {
    const out = await K.cmd("tick query");
    const n = (re) => { const m = re.exec(out); return m ? +m[1] : null; };
    return { avg_ms: n(/Average time per tick: ([\d.]+)ms/), p50_ms: n(/P50: ([\d.]+)ms/), p95_ms: n(/P95: ([\d.]+)ms/), p99_ms: n(/P99: ([\d.]+)ms/),
      state: /running normally/.test(out) ? "running" : /frozen/i.test(out) ? "frozen (/tick freeze)" : /sprint/i.test(out) ? "sprinting" : out.slice(0, 80) };
  }
  function paused() {
    // pause-when-empty-seconds: "Server empty for 60 seconds, pausing" after the last login = not ticking
    try {
      const st = fs.statSync(K.P.LOG), len = Math.min(st.size, 512 * 1024), b = Buffer.alloc(len);
      const fd = fs.openSync(K.P.LOG, "r"); fs.readSync(fd, b, 0, len, st.size - len); fs.closeSync(fd);
      const t = b.toString("utf8");
      return t.lastIndexOf("Server empty for") > t.lastIndexOf("logged in with entity id");
    } catch { return null; }
  }
  async function heap() {
    const out = await K.cmd("script run [system_info('java_used_memory'), system_info('java_max_memory')]");
    const m = /\[(\d+),\s*(\d+)\]/.exec(out);
    return m ? `${fmt(+m[1])} of ${fmt(+m[2])}` : null;
  }
  const humanOps = async () => scJSON(await K.cmd("script run encode_json(map(filter(player('all'), t = _~'player_type'; t != 'fake' && t != 'shadow' && _~'permission_level' >= 2), _~'name'))"));
  async function tellOps(names, lines) {
    for (const n of names) for (const line of lines)
      await K.cmd(`tellraw ${n} ${JSON.stringify(["", { text: "[Watchdog] ", color: "gold" }, { text: line, color: "white" }])}`);
  }
  async function sizes(refresh = false) {
    const s = loadState();
    if (!refresh && s.sizes && Date.now() - s.sizes.t < 10 * 60000) return s.sizes;
    const z = { t: Date.now(), world: await size(K.P.WORLD), ledger: (() => { try { return fs.statSync(path.join(K.P.WORLD, "ledger.sqlite")).size; } catch { return null; } })() };
    await withState(async (st) => { st.sizes = z; });
    return z;
  }
  // what could be freed inside this install (report only)
  const CANDIDATES = [
    [path.join(K.P.ROOT, "backups"), "world backups (clawdblock.py backup keeps the newest 3)"],
    [path.join(K.P.WORLD, "ledger.sqlite"), "Ledger block history: trim old rows in game with /ledger purge (the owner decides)"],
    [path.join(K.P.SCRIPTS, "cu.data"), "undo snapshots (minecraft_undo needs the recent ones)"],
    [path.join(K.P.SERVER, "bluemap"), "BlueMap render cache (it re-renders by itself, which costs CPU)"],
    [path.join(K.P.SERVER, "logs"), "old server logs (*.log.gz)"],
    [path.join(K.P.SERVER, "crash-reports"), "old crash reports"],
    [K.P.SHOTS, "screenshots the AI took"],
  ];
  async function freeable(refresh = false) {
    const s = loadState();
    if (!refresh && s.freeable && Date.now() - s.freeable.t < 6 * 3600000) return s.freeable;
    const items = [];
    for (const [p, what] of CANDIDATES) { const b = await size(p).catch(() => null); if (b && b > 20 * MB) items.push({ path: K.rel(p), bytes: b, size: fmt(b), what }); }
    items.sort((a, b) => b.bytes - a.bytes);
    const f = { t: Date.now(), time: localIso(), items };
    await withState(async (st) => { st.freeable = f; });
    return f;
  }

  // ───────────── background check (one MCP process holds the lease) ─────────────
  function diskMessage(level, free, items) {
    const head = level === "critical"
      ? `Urgent: only ${fmt(free)} left on the server's disk. If it fills up, saving the world can fail and damage parts of it.`
      : `The server's disk is running low: ${fmt(free)} free. If it fills up, saving the world can fail and damage parts of it.`;
    const top = items.slice(0, 4).map((i) => `${i.path} ${i.size}`).join(", ");
    return [head, `${top ? "Could be freed: " + top + ". " : ""}Nothing was deleted; that is your call.`];
  }
  async function check({ force = false, dry = false } = {}) {
    const out = { time: localIso() };
    const mine = await withState(async (s) => {
      const L = s.lease;
      let alive = false;
      if (L && L.pid !== process.pid) { try { process.kill(L.pid, 0); alive = true; } catch {} }
      if (!force && alive && Date.now() - L.t < CFG.lease_s * 1000) return false;
      s.lease = { pid: process.pid, t: Date.now() };
      out.mirrored = mirrorApp(s);
      return true;
    });
    if (!mine) return { skipped: "another MCP process runs the checks" };
    const d = diskFree();
    const level = d.free < CFG.disk_crit_gb * GB ? "critical" : d.free < CFG.disk_warn_gb * GB ? "warn" : "ok";
    out.disk = { free: fmt(d.free), level };
    const mem = await memory().catch(() => ({}));
    if (mem.swap) out.swap = mem.swap;
    const items = level === "ok" ? [] : (await freeable()).items;
    await withState(async (s) => {
      s.alerts = s.alerts || {};
      s.last = { t: Date.now(), time: out.time, free: d.free, level };
      if (mem.swap_total && (mem.swap_total - mem.swap_used) / mem.swap_total < 0.1 && Date.now() - (s.alerts.swap_logged || 0) > CFG.repeat_hours * 3600000) {
        s.alerts.swap_logged = Date.now();
        logIncident({ kind: "memory", swap: mem.swap, note: "swap nearly full: the computer is short of RAM; on macOS every new swap file also takes disk space" });
      }
      const a = s.alerts.disk;
      if (level === "ok") {
        if (a && d.free > CFG.disk_ok_gb * GB) { logIncident({ kind: "disk_ok", free: fmt(d.free) }); delete s.alerts.disk; out.alert = "recovered"; }
        return;
      }
      if (!a || a.level !== level) logIncident({ kind: "disk_low", level, free: fmt(d.free), freeable: items.slice(0, 6).map((i) => `${i.path} ${i.size}`) });
      const rank = { warn: 1, critical: 2 };
      const since = a?.sent ? Date.now() - a.sent : Infinity;
      const due = since >= CFG.repeat_hours * 3600000 || (rank[level] > rank[a.level] && since >= CFG.min_gap_min * 60000);
      s.alerts.disk = { ...(a || {}), level };
      if (!due) { out.alert = `already told ${a.to?.join(", ") || "the ops"} ${Math.round(since / 60000)} min ago`; return; }
      const ops = await humanOps().catch(() => []);
      const msg = diskMessage(level, d.free, items);
      if (!ops.length) { out.alert = "due, but no op is online: sent when one is"; out.message = msg; return; }
      if (dry) { out.would_send = { to: ops, message: msg }; return; }
      await tellOps(ops, msg);
      s.alerts.disk = { level, sent: Date.now(), to: ops };
      logIncident({ kind: "alert", issue: "disk", level, to: ops, free: fmt(d.free), message: msg.join(" ") });
      out.alert = `sent to ${ops.join(", ")}`;
      out.message = msg;
    });
    return out;
  }
  const G = (ctx.state.watchdog ||= { busy: false });
  clearInterval(G.timer); clearTimeout(G.first);
  if (CFG.loop !== false && process.env.MC_WATCHDOG !== "0") {
    const beat = () => {
      if (G.busy) return;
      G.busy = true;
      check().catch((e) => K.log("watchdog check:", e.message)).finally(() => { G.busy = false; });
    };
    G.first = setTimeout(beat, 20000); G.first.unref?.();
    G.timer = setInterval(beat, CFG.loop_s * 1000); G.timer.unref?.();
  }

  // ───────────── heavy: name the culprit ─────────────
  function appsForTags(groups) {
    const srcs = [];
    const add = (dir, ext) => { try { for (const f of fs.readdirSync(dir)) if (f.endsWith(ext) && f !== "watchdog.sc") srcs.push([f, fs.readFileSync(path.join(dir, f), "utf8")]); } catch {} };
    add(K.P.SCRIPTS, ".sc");
    add(K.P.JOBS, ".py");
    add(path.join(K.P.ROOT, "skill", "clawdblock", "blueprints"), ".py");
    const out = {};
    for (const g of groups) {
      const esc = g.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const re = new RegExp(`(^|[^A-Za-z0-9_])${esc}(_[A-Za-z0-9]|['"\\],])`);
      out[g] = srcs.filter(([, t]) => re.test(t)).map(([f]) => f).slice(0, 4);
    }
    return out;
  }
  async function hotThreads(ms = 3000) {
    const proc = await serverProc();
    if (!proc) return { error: "server process not found (start it with clawdblock.py start --background, or run on Linux/macOS)" };
    const jcmds = ["jcmd", process.env.JAVA_HOME && path.join(process.env.JAVA_HOME, "bin", "jcmd")].filter(Boolean);
    const snap = async () => {
      for (const j of jcmds) {
        const r = await K.run(j, [String(proc.pid), "Thread.print"], { timeout: 30000 });
        if (r.err && r.err.code === "ENOENT") continue;
        const m = new Map();
        for (const x of r.stdout.matchAll(/^"([^"]+)"[^\n]*?cpu=([\d.]+)ms/gm)) m.set(x[1], (m.get(x[1]) || 0) + +x[2]);
        return m;
      }
      return null;
    };
    const a = await snap();
    if (!a) return { error: "jcmd not found: it comes with a JDK (set JAVA_HOME or put jcmd on the PATH)" };
    const t0 = Date.now();
    await K.sleep(ms);
    const b = await snap(), dt = Date.now() - t0;
    const top = [...b].map(([n, c]) => ({ thread: n, cpu_pct: +(((c - (a.get(n) || 0)) / dt) * 100).toFixed(1) }))
      .filter((r) => r.cpu_pct >= 1).sort((x, y) => y.cpu_pct - x.cpu_pct).slice(0, 10);
    return { window_ms: dt, note: "% of one CPU core per JVM thread. 'Server thread' = the game tick; GC, C2 compiler, BlueMap, Chunky, Worker-Main, IO = background work.", top };
  }
  async function heavy(args) {
    const top = Math.max(3, Math.min(Number(args.top) || 8, 20));
    const tq = await tickQuery().catch((e) => ({ error: e.message }));
    const c = scJSON(await app(`census(${top})`));
    let entries = [];
    try { entries = K.mapEntries(); } catch {}
    const builds = (x, z) => K.WM.near(entries, { lo: [x - 8, -64, z - 8], hi: [x + 7, 320, z + 7] }, 12).slice(0, 2).map((b) => (b.gap ? `${b.name} (${b.gap} blocks ${b.direction})` : b.name));
    for (const ch of [...(c.chunks || []), ...(c.dense || [])]) ch.builds = builds(ch.x, ch.z);
    const apps = appsForTags((c.tags || []).map((t) => t[0]));
    const who = await K.cmd("script run encode_json(map(player('all'), p = pos(_); [_~'name', _~'player_type', _~'dimension', round(p:0), round(p:1), round(p:2)]))").then(scJSON).catch(() => []);
    const fl = [];
    for (const dim of ["overworld", "the_nether", "the_end"]) {
      const r = await K.cmd(`execute in minecraft:${dim} run forceload query`).catch(() => "");
      const m = /There (?:is|are) (\d+) force loaded chunks?/.exec(r);
      if (m && +m[1] > 0) fl.push({ dim, chunks: +m[1], list: r.split(": ").slice(1).join(": ").slice(0, 300) });
    }
    let tickApps = [];
    try { tickApps = fs.readdirSync(K.P.SCRIPTS).filter((f) => f.endsWith(".sc") && /__on_tick\s*\(/.test(fs.readFileSync(path.join(K.P.SCRIPTS, f), "utf8"))).map((f) => f.replace(/\.sc$/, "")); } catch {}
    const avg = tq.avg_ms;
    const res = {
      mspt: tq, paused: paused(),
      verdict: avg == null ? "unknown" : avg < 30 ? "healthy" : avg < 50 ? "busy (still 20 TPS)" : `lagging: ${(1000 / avg).toFixed(1)} TPS`,
      culprit: c.culprit, census_ms: c.ms, entities: c.entities, server_cost_score: c.score,
      note: "score = rough tick cost per entity (villager 6, other mobs 2, minecarts/boats 2, items 1, displays/markers 0.05). Display entities cost the server little but the players' frame rate a lot: see dense.",
      hottest_chunks: c.chunks, dense: c.dense, stacked: c.stacked, types: c.types,
      tags: (c.tags || []).map(([g, n]) => ({ tag: g + "_*", n, used_by: apps[g] || [] })),
      rises_since_quiet_census: { age_min: c.baseline_age_min, types: c.delta, tags: c.tag_delta },
      junk: c.junk, force_loaded: fl, apps_running_every_tick: tickApps, players: who,
      ...(installed ? { installed: "the watchdog app was copied into the world and loaded" } : {}),
    };
    if (bool(args.threads)) res.threads = await hotThreads(3000).catch((e) => ({ error: e.message }));
    return res;
  }

  // ───────────── status / incidents / disk / backup ─────────────
  async function status() {
    const [tq, st, hp, mem, proc, sz] = await Promise.all([
      tickQuery().catch((e) => ({ error: e.message })), app("status()").then(scJSON).catch((e) => ({ error: e.message })),
      heap().catch(() => null), memory().catch(() => ({})), serverProc().catch(() => null), sizes().catch(() => ({})),
    ]);
    const d = diskFree();
    const s = loadState();
    const w = st.windows_ms || [];
    const counts = {};
    for (const e of tail(300).filter((e) => e.t > Date.now() - 86400000)) counts[e.kind] = (counts[e.kind] || 0) + 1;
    return {
      tick: { ...tq, paused: paused() },
      last_minute: w.length ? { min_ms: Math.min(...w), mean_ms: +(w.reduce((a, b) => a + b, 0) / w.length).toFixed(1), max_window_ms: Math.max(...w), worst_single_tick_ms: Math.max(...(st.max_ms || [0])) } : st.error || "no samples (paused?)",
      open_incident: st.incident || null,
      app: st.cfg ? { alerts: st.cfg.alerts, mitigate: st.cfg.mitigate, lag_mspt: st.cfg.lag_mspt, lag_seconds: st.cfg.lag_seconds, log_lines: st.log_lines, cost: st.cost } : st,
      memory: { heap: hp, server_rss: proc?.rss ? fmt(proc.rss) : null, ram: mem.ram, swap: mem.swap || null },
      disk: { free: fmt(d.free), of: fmt(d.total), level: d.free < CFG.disk_crit_gb * GB ? "critical" : d.free < CFG.disk_warn_gb * GB ? "warn" : "ok", world: fmt(sz.world), ledger: fmt(sz.ledger) },
      incidents_24h: counts,
      background: { holder_pid: s.lease?.pid, this_pid: process.pid, last_check: s.last?.time, disk_alert: s.alerts?.disk || null },
      ...(installed ? { installed: "the watchdog app was copied into the world and loaded" } : {}),
    };
  }
  async function incidents(args) {
    await withState(async (s) => { mirrorApp(s); });
    let list = tail(1000);
    if (args.kind) list = list.filter((e) => e.kind === args.kind);
    list = list.slice(-(Number(args.limit) || 20));
    if (!bool(args.full)) list = list.map((e) => (e.census ? { ...e, census: { entities: e.census.entities, top_chunks: (e.census.chunks || []).slice(0, 3).map((c) => `${c.n} @ ${c.x},${c.z} ${c.dim} (${(c.types || []).slice(0, 2).map((t) => t.join(" ")).join(", ")})`), top_types: (e.census.types || []).slice(0, 5), rises: e.census.delta, stacked: e.census.stacked } } : e));
    return { log: K.rel(LOG), count: list.length, incidents: list };
  }
  async function disk(args) {
    const d = diskFree();
    const [mem, proc, hp, sz, fr] = await Promise.all([memory().catch(() => ({})), serverProc().catch(() => null), heap().catch(() => null), sizes(bool(args.refresh)), freeable(bool(args.refresh))]);
    const part = {};
    for (const [k, p] of [["regions, entities, poi", "dimensions"], ["region (older layout)", "region"], ["scripts (app data)", "scripts"], ["player data", "players"]]) {
      const b = await size(path.join(K.P.WORLD, p)).catch(() => null);
      if (b) part[k] = fmt(b);
    }
    return {
      disk: { free: fmt(d.free), total: fmt(d.total), warn_below: CFG.disk_warn_gb + " GB", critical_below: CFG.disk_crit_gb + " GB" },
      world: { total: fmt(sz.world), ledger_sqlite: fmt(sz.ledger), ...part },
      memory: { heap: hp, server_rss: proc?.rss ? fmt(proc.rss) : null, ram: mem.ram, swap: mem.swap || null },
      could_free: { measured: fr.time, items: fr.items },
      note: "Nothing was deleted. Deleting is the owner's call. Outside this folder, the usual big ones are package-manager and app caches.",
    };
  }
  async function backup(args) {
    const argv = [path.join(K.P.ROOT, "clawdblock.py"), "backup", "--json", "--keep", String(Math.max(1, Math.min(Number(args.keep) || 3, 30)))];
    if (bool(args.dry_run)) argv.push("--dry-run");
    if (bool(args.include_ledger)) argv.push("--include-ledger");
    if (args.dest) argv.push("--dest", String(args.dest));
    if (args.simulate_free_mb != null) argv.push("--simulate-free-mb", String(Number(args.simulate_free_mb)));
    let r = null;
    for (const py of K.PYTHONS) {
      r = await K.run(py, argv, { cwd: K.P.ROOT, timeout: 30 * 60000, env: { PYTHONIOENCODING: "utf-8" } });
      if (!(r.err && r.err.code === "ENOENT")) break;
    }
    let j;
    try { j = JSON.parse(r.stdout); } catch { j = { ok: false, error: "clawdblock.py backup did not answer in JSON", stdout: r.stdout.slice(-1500), stderr: r.stderr.slice(-1500) }; }
    logIncident({ kind: "backup", ok: j.ok, dry_run: bool(args.dry_run), refused: !!j.refused, zip: j.zip, size: j.zip_size, rotated: j.rotated, reason: j.reason || j.error, simulated_free: j.simulated_free || undefined });
    return j;
  }

  return {
    async minecraft_watchdog(args) {
      const a = args.action || "status";
      if (a === "status") return K.text(await status());
      if (a === "heavy") return K.text(await heavy(args));
      if (a === "incidents") return K.text(await incidents(args));
      if (a === "disk") return K.text(await disk(args));
      if (a === "backup") return K.text(await backup(args));
      if (a === "check") return K.text(await check({ force: true, dry: bool(args.dry_run) }));
      throw new Error("action: status | heavy | incidents | disk | backup | check");
    },
  };
}
