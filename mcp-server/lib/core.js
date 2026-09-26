/**
 * core — shared helpers every tool uses: locked RCON, JSON files, chat, players, geometry, scarpet.
 * install(K, ctx) adds everything to the shared object K; other lib modules call each other through K.
 */
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFile } from "node:child_process";

export function install(K, ctx) {
  const C = ctx.config;
  K.ctx = ctx;
  K.log = ctx.log;
  K.looksLikeError = ctx.looksLikeError;
  K.BOT = C.BOT_NAME;
  K.BOT_PREFIX = C.BOT_PREFIX || "";
  K.BOT_DISPLAY = K.BOT_PREFIX + K.BOT;            // what people see: "Pink Golem"
  K.BOT_OUTFIT = C.BOT_OUTFIT ?? "pink";
  K.CHAT_COLOR = C.CHAT_COLOR;
  K.MAX_FILL_VOLUME = C.MAX_FILL_VOLUME;

  // ── paths (everything the MCP writes stays inside the repo: data/, jobs/, the world's scripts folder)
  const props = ctx.readProps();
  const level = props["level-name"] || "world";
  K.P = {
    ROOT: C.ROOT,
    SERVER: C.SERVER_DIR,
    LOG: C.LOG_FILE,
    WORLD: path.join(C.SERVER_DIR, level),
    SCRIPTS: path.join(C.SERVER_DIR, level, "scripts"),
    CU_DATA: path.join(C.SERVER_DIR, level, "scripts", "cu.data"),
    DATA: path.join(C.ROOT, "data"),
    JOBS: path.join(C.ROOT, "jobs"),
    SHOTS: path.join(C.ROOT, "data", "screenshots"),
    ZONES: path.join(C.ROOT, "data", "zones.json"),
    UNDO: path.join(C.ROOT, "data", "undo.json"),
    INDEX: path.join(C.ROOT, "data", "world_index.json"),
    PEOPLE: path.join(C.ROOT, "data", "people.json"),
    LEARNINGS: path.join(C.ROOT, "data", "LEARNINGS.md"),
    LOCK: path.join(C.ROOT, "data", ".rcon.lock"),
  };
  fs.mkdirSync(K.P.DATA, { recursive: true });
  /** A path given by the model: relative to the repo root; must stay inside the repo or the server folder. */
  K.safePath = (p) => {
    const f = path.isAbsolute(p) ? path.resolve(p) : path.resolve(C.ROOT, p);
    const inside = (d) => f === path.resolve(d) || f.startsWith(path.resolve(d) + path.sep);
    if (!inside(C.ROOT) && !inside(C.SERVER_DIR)) throw new Error(`${p}: files must be inside the Pink Golem folder (${C.ROOT})`);
    return f;
  };
  K.rel = (f) => path.relative(C.ROOT, f).split(path.sep).join("/");

  // ── ground: a flat world has one ground level for everything; a normal world is read per column
  K.flatGroundY = detectFlatGround(props);
  K.isFlat = K.flatGroundY !== null;

  // ── one RCON command at a time across ALL MCP processes (several AI clients can share one server).
  // Vanilla RCON shares one console-output buffer between connections, so two clients sending at the same
  // moment get each other's output. A cross-process lock (atomic mkdir) makes every command run alone.
  K.sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  K.withLock = async (dir, fn, { stale = 12000, wait = 15000 } = {}) => {
    const t0 = Date.now();
    let got = false;
    for (;;) {
      try { fs.mkdirSync(dir); got = true; break; }
      catch (e) {
        if (e.code !== "EEXIST") break;
        try { if (Date.now() - fs.statSync(dir).mtimeMs > stale) { fs.rmdirSync(dir); continue; } } catch {}
        if (Date.now() - t0 > wait) break;          // don't hang forever: run unlocked
        await K.sleep(2 + Math.random() * 6);
      }
    }
    try { return await fn(); } finally { if (got) try { fs.rmdirSync(dir); } catch {} }
  };
  K.cmd = (c) => K.withLock(K.P.LOCK, () => ctx.cmd(c));
  /** Outputs that look like errors but only mean "already like that" (setblock/fill of an identical block, kill with
   *  nothing to kill). They are counted as `unchanged`, not as errors. */
  K.harmless = (out) => /^(Could not set the block|No blocks were filled|No entity was found)/.test(String(out).trim());
  K.runMany = async (cmds, { stopOnError = false } = {}) => {
    const results = []; let errors = 0;
    for (const c of cmds) {
      let out;
      try { out = await K.cmd(c); } catch (e) { out = `ERROR: ${e.message}`; }
      const bad = out.startsWith("ERROR:") || (K.looksLikeError(out) && !K.harmless(out));
      if (bad) errors++;
      results.push({ command: c, output: out, error: bad, unchanged: K.harmless(out) });
      if (bad && stopOnError) break;
    }
    return { results, errors };
  };

  // ── JSON files shared by several MCP processes: read-modify-write under a lock
  K.readJSON = (f, d) => { try { return JSON.parse(fs.readFileSync(f, "utf8")); } catch { return d; } };
  K.updateJSON = async (f, dflt, fn) => K.withLock(f + ".lock", async () => {
    let v; try { v = JSON.parse(fs.readFileSync(f, "utf8")); } catch { v = dflt; }
    const r = await fn(v);
    const out = r === undefined ? v : r;
    fs.mkdirSync(path.dirname(f), { recursive: true });
    fs.writeFileSync(f + ".tmp", JSON.stringify(out, null, 2)); fs.renameSync(f + ".tmp", f);
    return out;
  }, { stale: 20000, wait: 20000 });

  // ── MCP reply helpers
  K.text = (t) => ({ content: [{ type: "text", text: typeof t === "string" ? t : JSON.stringify(t, null, 2) }] });
  K.img = (png) => ({ type: "image", data: png.toString("base64"), mimeType: "image/png" });
  K.fail = (t) => ({ isError: true, content: [{ type: "text", text: t }] });
  K.saveShot = (prefix, png) => {
    fs.mkdirSync(K.P.SHOTS, { recursive: true });
    const f = `${String(prefix).replace(/[^\w-]+/g, "_")}-${new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19)}.png`;
    fs.writeFileSync(path.join(K.P.SHOTS, f), png);
    return "data/screenshots/" + f;
  };

  // ── chat
  const chunkText = (text, max = 220) => {
    const out = [];
    let rest = String(text);
    while (rest.length > max) {
      let cut = rest.lastIndexOf(" ", max);
      if (cut < max * 0.5) cut = max;
      out.push(rest.slice(0, cut));
      rest = rest.slice(cut).trimStart();
    }
    if (rest) out.push(rest);
    return out;
  };
  K.sayAsBot = async (message, target = "@a") => {
    const lines = String(message).split(/\n/).flatMap((l) => chunkText(l));
    for (const line of lines) {
      const comp = ["", { text: "<", color: "white" }, { text: K.BOT_DISPLAY, color: K.CHAT_COLOR }, { text: "> ", color: "white" }, { text: line }];
      const out = await K.cmd(`tellraw ${target} ${JSON.stringify(comp)}`);
      if (K.looksLikeError(out)) throw new Error(`tellraw failed: ${out}`);
    }
    ctx.pushEvent({ time: new Date().toTimeString().slice(0, 8), type: "bot", player: K.BOT, message: String(message) });
  };
  const esc = (s) => String(s).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  K.mentionRe = new RegExp(`(${C.BOT_ALIASES.map(esc).join("|")})`, "i");
  K.stripBotPrefix = (t) => String(t).replace(new RegExp(`^\\s*(${C.BOT_ALIASES.map(esc).join("|")})\\s*:\\s*`, "i"), "").trim();

  // ── players
  K.onlinePlayers = async () => {
    // "list uuids" prints plain account names — plain "list" shows display names, which chat mods, nicknames,
    // team prefixes and [AFK] tags decorate ("✦ Steve") → "There are 2 of a max of 10 players online: a (uuid), b (uuid)"
    const out = await K.cmd("list uuids");
    const m = /online:\s*(.*)$/s.exec(out);
    const names = m && m[1].trim() ? [...m[1].matchAll(/([A-Za-z0-9_]{1,16}) \([0-9a-f-]{36}\)/g)].map((x) => x[1]) : [];
    return { raw: out, names };
  };
  /** The first real (non-bot, non-crew) player online, for tools that default to "the player". */
  K.firstRealPlayer = async () => (await K.onlinePlayers()).names.find((n) => n !== K.BOT && !(K.isCrew && K.isCrew(n)));
  const parseDataValue = (out) => { const i = out.indexOf("entity data:"); return i >= 0 ? out.slice(i + 12).trim() : null; };
  K.parseNums = (v) => (v?.match(/-?\d+(?:\.\d+)?(?:E-?\d+)?/gi) || []).map(Number);
  K.yawToDir = (yaw) => {
    const y = ((yaw % 360) + 360) % 360;
    if (y >= 315 || y < 45) return "south (+Z)";
    if (y < 135) return "west (-X)";
    if (y < 225) return "north (-Z)";
    return "east (+X)";
  };
  K.playerInfo = async (name) => {
    const get = async (p) => parseDataValue(await K.cmd(`data get entity ${name} ${p}`));
    const pos = K.parseNums(await get("Pos"));
    if (pos.length < 3) throw new Error(`Player "${name}" not found / not online.`);
    const rot = K.parseNums(await get("Rotation"));
    const dim = (await get("Dimension"))?.replace(/"/g, "");
    const health = K.parseNums(await get("Health"))[0];
    const food = K.parseNums(await get("foodLevel"))[0];
    const gm = K.parseNums(await get("playerGameType"))[0];
    const modes = ["survival", "creative", "adventure", "spectator"];
    return {
      name,
      position: { x: +pos[0].toFixed(2), y: +pos[1].toFixed(2), z: +pos[2].toFixed(2) },
      block: { x: Math.floor(pos[0]), y: Math.floor(pos[1]), z: Math.floor(pos[2]) },
      // the block the player stands ON (ground). A house floor belongs at this Y, not at feet Y.
      standingOn: { x: Math.floor(pos[0]), y: Math.ceil(pos[1] - 1e-6) - 1, z: Math.floor(pos[2]) },
      facing: rot.length >= 2 ? { yaw: +rot[0].toFixed(1), pitch: +rot[1].toFixed(1), direction: K.yawToDir(rot[0]) } : null,
      dimension: dim,
      health,
      food,
      gameMode: modes[gm] ?? gm,
    };
  };

  // ── geometry
  K.V = (v) => (Array.isArray(v) ? v.map(Number) : [Number(v.x), Number(v.y), Number(v.z)]);
  K.add = (o, p) => [o[0] + p[0], o[1] + p[1], o[2] + p[2]];
  K.volOf = ([lo, hi]) => (hi[0] - lo[0] + 1) * (hi[1] - lo[1] + 1) * (hi[2] - lo[2] + 1);
  K.boxOf = (points) => {
    const lo = [Infinity, Infinity, Infinity], hi = [-Infinity, -Infinity, -Infinity];
    for (const p of points) for (let i = 0; i < 3; i++) (lo[i] = Math.min(lo[i], p[i])), (hi[i] = Math.max(hi[i], p[i]));
    return [lo, hi];
  };
  K.sortBox = (a, b) => [[0, 1, 2].map((i) => Math.min(a[i], b[i])), [0, 1, 2].map((i) => Math.max(a[i], b[i]))];
  K.unionBox = (targets) => K.boxOf(targets.flatMap((t) => [t.lo, t.hi]));
  K.inDim = (dimension, c) => (dimension ? `execute in ${dimension} run ${c}` : c);
  /** Split a box into sub-boxes each ≤ MAX_FILL_VOLUME blocks. */
  K.splitBox = function splitBox(a, b) {
    const lo = [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.min(a[2], b[2])];
    const hi = [Math.max(a[0], b[0]), Math.max(a[1], b[1]), Math.max(a[2], b[2])];
    const size = hi.map((h, i) => h - lo[i] + 1);
    if (size[0] * size[1] * size[2] <= K.MAX_FILL_VOLUME) return [[lo, hi]];
    const axis = size.indexOf(Math.max(...size));
    const mid = lo[axis] + Math.floor(size[axis] / 2) - 1;
    const hiA = [...hi]; hiA[axis] = mid;
    const loB = [...lo]; loB[axis] = mid + 1;
    return [...splitBox(lo, hiA), ...splitBox(loB, hi)];
  };
  K.fillCommands = (from, to, block, mode, dimension) => {
    const boxes = K.splitBox(from, to);
    // "hollow"/"outline" on split boxes would create inner walls → fall back to faces
    if ((mode === "hollow" || mode === "outline") && boxes.length > 1) {
      const [lo, hi] = K.sortBox(from, to);
      const faces = [
        [[lo[0], lo[1], lo[2]], [hi[0], hi[1], lo[2]]], [[lo[0], lo[1], hi[2]], [hi[0], hi[1], hi[2]]],
        [[lo[0], lo[1], lo[2]], [lo[0], hi[1], hi[2]]], [[hi[0], lo[1], lo[2]], [hi[0], hi[1], hi[2]]],
        [[lo[0], lo[1], lo[2]], [hi[0], lo[1], hi[2]]], [[lo[0], hi[1], lo[2]], [hi[0], hi[1], hi[2]]],
      ];
      const cmds = [];
      if (mode === "hollow" && hi.every((h, i) => h - lo[i] >= 2))
        for (const [a, b] of K.splitBox([lo[0] + 1, lo[1] + 1, lo[2] + 1], [hi[0] - 1, hi[1] - 1, hi[2] - 1]))
          cmds.push(K.inDim(dimension, `fill ${a.join(" ")} ${b.join(" ")} air`));
      for (const [fa, fb] of faces)
        for (const [a, b] of K.splitBox(fa, fb)) cmds.push(K.inDim(dimension, `fill ${a.join(" ")} ${b.join(" ")} ${block}`));
      return cmds;
    }
    return boxes.map(([a, b]) => K.inDim(dimension, `fill ${a.join(" ")} ${b.join(" ")} ${block}${mode ? " " + mode : ""}`));
  };
  K.resolveOrigin = async (args) => {
    if (args.relative_to_player) {
      const p = await K.playerInfo(args.relative_to_player);
      const g = p.standingOn;
      return {
        origin: [g.x, g.y, g.z],
        dimension: args.dimension || p.dimension,
        note: `relative to the ground block ${p.name} stands on (${g.x} ${g.y} ${g.z}); y=0 is the ground layer, y=1 is on top of it`,
      };
    }
    return { origin: [0, 0, 0], dimension: args.dimension, note: "absolute coordinates" };
  };

  // ── scarpet
  K.scStr = (s) => "'" + String(s).replace(/\\/g, "/").replace(/'/g, "’").replace(/\n/g, " ") + "'";
  /** RCON takes ONE line — newlines, // comments and a leading "script run" would break the expression (→ "= null"). */
  K.cleanScarpet = (expr) => {
    let e = String(expr).replace(/^\s*\/?script\s+run\s+/i, "");
    if (/\n/.test(e)) e = e.split(/\r?\n/).map((l) => l.replace(/(^|[^:'"])\/\/.*$/, "$1")).join(" ");
    return e.replace(/\s+/g, " ").trim().replace(/;\s*$/, "");
  };
  K.scarpet = async (expr, { raw = false } = {}) => {
    const e = raw ? String(expr) : K.cleanScarpet(expr);
    const out = await K.cmd(`script run ${e}`);
    if (/Unknown or incomplete command/i.test(out))
      throw new Error("Scarpet (/script) is not available — the Carpet mod is required (python3 pinkgolem.py mods).");
    const m = /^\s*=\s*([\s\S]*?)\s*(?:\([^()]*\d[^()]*s\))?\s*$/.exec(out);
    return { raw: out, value: m ? m[1] : out, expr: e };
  };
  /** Run an expression inside a scarpet app, loading the app first if needed. */
  K.inApp = async (app, expr) => {
    let out = await K.cmd(`script in ${app} run ${expr}`);
    if (/unknown app|no such app|not loaded|Unknown or incomplete/i.test(out) || /^\s*$/.test(out)) {
      await K.cmd(`script load ${app}`).catch(() => {});
      out = await K.cmd(`script in ${app} run ${expr}`);
    }
    return out;
  };

  // ── external programs (python generators, chrome)
  K.run = (file, argv, opts = {}) => new Promise((res) => execFile(file, argv, { timeout: opts.timeout || 60000, maxBuffer: 20 * 1024 * 1024, cwd: opts.cwd, env: { ...process.env, ...(opts.env || {}) }, windowsHide: true },
    (err, stdout, stderr) => res({ err, stdout: String(stdout || ""), stderr: String(stderr || "") })));
  K.PYTHONS = process.platform === "win32" ? ["py", "python", "python3"] : ["python3", "python", "/usr/bin/python3", "/opt/homebrew/bin/python3", "/usr/local/bin/python3"];
  K.tmpdir = os.tmpdir();
}

/** Superflat worlds put the ground (grass) at one Y everywhere: -61 for the default layers. null for normal worlds. */
function detectFlatGround(props) {
  const t = String(props["level-type"] || "").toLowerCase();
  if (!t.includes("flat")) return null;
  let top = -61;
  try {
    const gs = props["generator-settings"] ? JSON.parse(props["generator-settings"].replace(/\\:/g, ":")) : null;
    if (gs?.layers?.length) top = -64 + gs.layers.reduce((a, l) => a + (Number(l.height) || 0), 0) - 1;
  } catch {}
  return top;
}
