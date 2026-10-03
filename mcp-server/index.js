#!/usr/bin/env node
/**
 * Pink Golem MCP server — core.
 *
 * Talks to a Minecraft server the version-proof way:
 *   - RCON          runs any server command as the console (op level 4) and returns its output
 *   - latest.log    live player chat / joins / leaves
 *   - Carpet        gives the AI a visible body (/player <name> spawn) and scarpet to read the world
 *
 * The tools live in lib/ and tools/ and hot-reload: edit any of those files and the next tool call uses the new code.
 * Changes to this file need a restart of the MCP client.
 * stdout is reserved for MCP JSON-RPC; all logging goes to stderr.
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { CallToolRequestSchema, ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";
import net from "node:net";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

// ───────────────────────────── config ─────────────────────────────
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");

function log(...a) {
  console.error("[pinkgolem]", ...a);
}

function loadConfig() {
  const legacy = path.join(ROOT, "clawdblock.json");           // the project was called ClawdBlock until 2026-09-27
  const plain = path.join(ROOT, "pinkgolem.json");
  const file = process.env.PINKGOLEM_CONFIG || process.env.CLAWDBLOCK_CONFIG || (!fs.existsSync(plain) && fs.existsSync(legacy) ? legacy : plain);
  let c = {};
  try {
    c = JSON.parse(fs.readFileSync(file, "utf8"));
  } catch (e) {
    if (e.code !== "ENOENT") log(`cannot read ${file}: ${e.message}`);
  }
  const abs = (p) => (p ? (path.isAbsolute(p) ? p : path.resolve(ROOT, p)) : null);
  // The default body is "Golem" with a team prefix "Pink " → "Pink Golem" over its head, in the player list and chat
  // (a player name can't hold a space). Another bot_name gets no prefix unless bot_prefix says so.
  const botName = process.env.MC_BOT_NAME || c.bot_name || "Golem";
  const botPrefix = c.bot_prefix ?? (botName === "Golem" ? "Pink " : "");
  return {
    ROOT,
    CONFIG_FILE: file,
    SERVER_DIR: abs(process.env.MC_SERVER_DIR || c.server_dir || "server"),
    BOT_NAME: botName,
    BOT_PREFIX: botPrefix,
    BOT_OUTFIT: c.bot_outfit ?? "pink",
    CHAT_COLOR: process.env.MC_CHAT_COLOR || c.chat_color || "light_purple",
    BOT_ALIASES: c.bot_aliases || [...new Set([botPrefix + botName, botName, "golem", "bot"])],
    CREW: c.crew || {},
    RCON_HOST: process.env.MC_RCON_HOST || c.rcon_host || "127.0.0.1",
    RCON_PORT: process.env.MC_RCON_PORT || c.rcon_port || null,
    RCON_PASSWORD: process.env.MC_RCON_PASSWORD ?? c.rcon_password ?? null,
    RAW: c,
  };
}

const CFG = loadConfig();
const PROPS_FILE = path.join(CFG.SERVER_DIR, "server.properties");
const LOG_FILE = path.join(CFG.SERVER_DIR, "logs", "latest.log");
const MAX_FILL_VOLUME = 32768; // vanilla limit per /fill
const MAX_RCON_BYTES = 1400; // vanilla RCON drops packets > 1460 bytes

function readProps() {
  const out = {};
  try {
    for (const line of fs.readFileSync(PROPS_FILE, "utf8").split(/\r?\n/)) {
      if (!line || line.startsWith("#")) continue;
      const i = line.indexOf("=");
      if (i < 0) continue;
      out[line.slice(0, i).trim()] = line.slice(i + 1).trim();
    }
  } catch (e) {
    log("cannot read server.properties:", e.message);
  }
  return out;
}

function rconConfig() {
  const p = readProps();
  return {
    host: CFG.RCON_HOST,
    port: parseInt(CFG.RCON_PORT || p["rcon.port"] || "25575", 10),
    password: CFG.RCON_PASSWORD ?? p["rcon.password"] ?? "",
    enabled: (p["enable-rcon"] || "false") === "true",
    props: p,
  };
}

// ───────────────────────────── RCON client ─────────────────────────────
// Source RCON protocol (as implemented by vanilla Minecraft).
const T_AUTH = 3, T_EXEC = 2, T_RESP = 0;

class Rcon {
  constructor() {
    this.sock = null;
    this.buf = Buffer.alloc(0);
    this.nextId = 10;
    this.pending = new Map(); // id -> handler(packet)
    this.queue = Promise.resolve();
    this.connecting = null;
  }

  get connected() {
    return !!this.sock && !this.sock.destroyed && this.authed;
  }

  encode(id, type, body) {
    const payload = Buffer.from(body, "utf8");
    const b = Buffer.alloc(14 + payload.length);
    b.writeInt32LE(10 + payload.length, 0);
    b.writeInt32LE(id, 4);
    b.writeInt32LE(type, 8);
    payload.copy(b, 12);
    b.writeInt16LE(0, 12 + payload.length);
    return b;
  }

  onData(chunk) {
    this.buf = Buffer.concat([this.buf, chunk]);
    while (this.buf.length >= 4) {
      const len = this.buf.readInt32LE(0);
      if (this.buf.length < 4 + len) break;
      const id = this.buf.readInt32LE(4);
      const type = this.buf.readInt32LE(8);
      const body = this.buf.slice(12, 4 + len - 2).toString("utf8");
      this.buf = this.buf.slice(4 + len);
      const h = this.pending.get(id) || (id === -1 ? this.pending.get("auth") : null);
      if (h) h({ id, type, body });
    }
  }

  failAll(err) {
    for (const h of this.pending.values()) h({ error: err });
    this.pending.clear();
  }

  connect() {
    if (this.connected) return Promise.resolve();
    if (this.connecting) return this.connecting;
    const cfg = rconConfig();
    this.connecting = new Promise((resolve, reject) => {
      if (!cfg.password) {
        this.connecting = null;
        return reject(
          new Error(
            `RCON password is empty (${PROPS_FILE}). Run "python3 pinkgolem.py setup" or set enable-rcon=true and rcon.password=<something> in server.properties, then restart the Minecraft server.`
          )
        );
      }
      const sock = net.createConnection({ host: cfg.host, port: cfg.port });
      this.sock = sock;
      this.authed = false;
      this.buf = Buffer.alloc(0);
      const timer = setTimeout(() => {
        sock.destroy();
        done(new Error(`RCON connection to ${cfg.host}:${cfg.port} timed out`));
      }, 5000);
      let finished = false;
      const done = (err) => {
        if (finished) return;
        finished = true;
        clearTimeout(timer);
        this.connecting = null;
        this.pending.delete("auth");
        err ? reject(err) : resolve();
      };
      sock.on("data", (c) => this.onData(c));
      sock.on("error", (e) => {
        const hint =
          e.code === "ECONNREFUSED"
            ? ` — nothing is listening on ${cfg.host}:${cfg.port}. Is the Minecraft server running (python3 pinkgolem.py start)${cfg.enabled ? "" : " and is enable-rcon=true in server.properties (it is false now)"}?`
            : "";
        done(new Error(`RCON error: ${e.message}${hint}`));
        this.failAll(new Error(`RCON connection lost: ${e.message}`));
      });
      sock.on("close", () => {
        this.authed = false;
        this.sock = null;
        this.failAll(new Error("RCON connection closed (server stopped or restarted?)"));
        done(new Error("RCON connection closed during login"));
      });
      sock.on("connect", () => {
        const id = this.nextId++;
        const h = (p) => {
          if (p.error) return done(p.error);
          if (p.type !== 2 && p.type !== T_RESP) return;
          if (p.id === -1) {
            sock.destroy();
            return done(new Error("RCON login failed: wrong rcon.password"));
          }
          this.authed = true;
          this.pending.delete(id);
          done();
        };
        this.pending.set(id, h);
        this.pending.set("auth", h);
        sock.write(this.encode(id, T_AUTH, cfg.password));
      });
    });
    return this.connecting;
  }

  /** Run one command (no leading slash needed). Serialized. */
  command(cmd, timeoutMs = 10000) {
    const run = async () => {
      cmd = String(cmd).trim().replace(/^\/+/, "");
      const bytes = Buffer.byteLength(cmd, "utf8");
      if (bytes > MAX_RCON_BYTES)
        throw new Error(`Command too long for RCON (${bytes} bytes, max ${MAX_RCON_BYTES}). Split it up.`);
      await this.connect();
      const id = this.nextId++;
      // Vanilla RCON reads one packet per socket read and closes the connection if two packets arrive
      // together, so we never pipeline. A response is split into 4096-byte chunks; a shorter chunk is the last.
      return await new Promise((resolve, reject) => {
        const parts = [];
        let idle = null;
        const timer = setTimeout(() => {
          cleanup();
          parts.length ? resolve(parts.join("")) : reject(new Error(`RCON timeout for: ${cmd}`));
        }, timeoutMs);
        const cleanup = () => {
          clearTimeout(timer);
          clearTimeout(idle);
          this.pending.delete(id);
        };
        this.pending.set(id, (p) => {
          if (p.error) {
            cleanup();
            return reject(p.error);
          }
          parts.push(p.body);
          clearTimeout(idle);
          if (Buffer.byteLength(p.body, "utf8") < 4000) {
            cleanup();
            resolve(parts.join(""));
          } else {
            idle = setTimeout(() => {
              cleanup();
              resolve(parts.join(""));
            }, 250);
          }
        });
        this.sock.write(this.encode(id, T_EXEC, cmd));
      });
    };
    const p = this.queue.then(run, run);
    this.queue = p.catch(() => {});
    return p;
  }

  close() {
    try {
      this.sock?.destroy();
    } catch {}
  }
}

const rcon = new Rcon();
const stripColors = (s) => String(s ?? "").replace(/§./g, "");

const ERROR_PATTERNS = [
  /Unknown or incomplete command/i,
  /Incorrect argument/i,
  /Expected /,
  /Invalid /,
  /not loaded/i,
  /No (player|entity) was found/i,
  /Unknown (block|item|entity|function)/i,
  /Too many blocks/i,
  /cannot /i,
  /Could not/i,
  /Unexpected/i,
  /<--\[HERE\]/,
  /^Failed to /,
];
const looksLikeError = (out) => ERROR_PATTERNS.some((r) => r.test(out));

async function cmd(c) {
  return stripColors(await rcon.command(c));
}

// ───────────────────────────── chat / log watcher ─────────────────────────────
const events = []; // {id, time, type: chat|join|leave|say|bot|system, player, message}
let eventSeq = 0;
let logOffset = 0;
let logInode = null;
let partial = "";
const MAX_EVENTS = 500;
const waiters = new Set();

const RE_LINE = /^\[(\d\d:\d\d:\d\d)\] \[([^\]]+)\/INFO\]: (.*)$/;
const RE_CHAT = /^(?:\[Not Secure\] )?<([^>]+)> (.*)$/;
const RE_SAY = /^\[([^\]:]+)\] (.*)$/;
// Join/leave come from the fixed server lines, not the chat text (chat mods rewrite that text).
const RE_JOIN = /^(\w+)\[[^\]]*\] logged in with entity id/;
const RE_LEFT = /^(\w+) lost connection:/;

function pushEvent(e) {
  e.id = ++eventSeq;
  events.push(e);
  if (events.length > MAX_EVENTS) events.shift();
  for (const w of waiters) w(e);
}

function parseLine(line) {
  const m = RE_LINE.exec(line);
  if (!m) return;
  const [, time, thread, msg] = m;
  if (!thread.startsWith("Server thread") && !thread.startsWith("Async Chat")) return;
  let x;
  if ((x = RE_CHAT.exec(msg))) {
    if (x[1] === CFG.BOT_NAME) return;
    return pushEvent({ time, type: "chat", player: x[1], message: x[2] });
  }
  if ((x = RE_JOIN.exec(msg))) return pushEvent({ time, type: "join", player: x[1], message: "joined the game" });
  if ((x = RE_LEFT.exec(msg))) return pushEvent({ time, type: "leave", player: x[1], message: "left the game" });
  if ((x = RE_SAY.exec(msg))) {
    // /say from a player → "[name] msg". Skip command feedback like "[Player: Set ...]" and mod noise.
    if (/^(Rcon|Server|Essential Commands|BlueMap)$/.test(x[1]) || x[1].includes(" ")) return;
    return pushEvent({ time, type: "say", player: x[1], message: x[2] });
  }
}

function pollLog() {
  let st;
  try {
    st = fs.statSync(LOG_FILE);
  } catch {
    return;
  }
  if (logInode !== null && (st.ino !== logInode || st.size < logOffset)) {
    logOffset = 0;
    partial = "";
    pushEvent({ time: new Date().toTimeString().slice(0, 8), type: "system", player: "", message: "server log rotated (server restarted)" });
  }
  logInode = st.ino;
  if (st.size <= logOffset) return;
  const fd = fs.openSync(LOG_FILE, "r");
  try {
    const len = Math.min(st.size - logOffset, 4 * 1024 * 1024);
    const b = Buffer.alloc(len);
    fs.readSync(fd, b, 0, len, logOffset);
    logOffset += len;
    const text = partial + b.toString("utf8");
    const lines = text.split(/\r?\n/);
    partial = lines.pop();
    for (const l of lines) parseLine(l);
  } finally {
    fs.closeSync(fd);
  }
}

function startLogWatcher() {
  pollLog();
  setInterval(pollLog, 400).unref();
}

function fmtEvent(e) {
  if (e.type === "chat") return `#${e.id} [${e.time}] <${e.player}> ${e.message}`;
  if (e.type === "bot") return `#${e.id} [${e.time}] <${CFG.BOT_NAME}> ${e.message}   (you)`;
  if (e.type === "say") return `#${e.id} [${e.time}] [${e.player}] ${e.message}`;
  if (e.type === "system") return `#${e.id} [${e.time}] * ${e.message}`;
  return `#${e.id} [${e.time}] * ${e.player} ${e.message}`;
}

// ───────────────────────────── hot-reloadable tools ─────────────────────────────
// Every .js file in lib/ and tools/ plus the helper modules next to this file is watched; any change reloads all of them.
const WATCH = [path.join(__dirname, "lib"), path.join(__dirname, "tools"), __dirname];
function codeVersion() {
  let m = 0;
  for (const d of WATCH) {
    let names = [];
    try { names = fs.readdirSync(d); } catch { continue; }
    for (const n of names) {
      if (!n.endsWith(".js") || (d === __dirname && n === "index.js")) continue;
      try { m = Math.max(m, fs.statSync(path.join(d, n)).mtimeMs); } catch {}
    }
  }
  return m;
}

const ctx = {
  cmd, looksLikeError, rconConfig, readProps, pushEvent, pollLog, events, waiters, fmtEvent, log,
  config: { ...CFG, MAX_FILL_VOLUME, LOG_FILE, PROPS_FILE },
  state: { followTimer: null, followTarget: null },
  chat: { get seq() { return eventSeq; } },
};
let toolsMod = null;
let toolsVer = 0;
let serverReady = false;
async function tools() {
  const v = codeVersion();
  if (!toolsMod || v !== toolsVer) {
    const mod = await import(pathToFileURL(path.join(__dirname, "tools", "index.js")).href + "?v=" + v);
    toolsMod = await mod.create(ctx);
    const first = !toolsVer;
    toolsVer = v;
    log(first ? `tools loaded (${toolsMod.TOOLS.length})` : "tool code changed — reloaded");
    if (!first && serverReady) server.sendToolListChanged().catch(() => {});
  }
  return toolsMod;
}

// ───────────────────────────── MCP wiring ─────────────────────────────
const server = new Server({ name: "pinkgolem", version: "1.2.0" }, { capabilities: { tools: { listChanged: true } } });

server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools: (await tools()).TOOLS }));

server.setRequestHandler(CallToolRequestSchema, async (req) => {
  const { name, arguments: args = {} } = req.params;
  log("tool", name, JSON.stringify(args).slice(0, 300));
  try {
    return await (await tools()).handle(name, args);
  } catch (e) {
    log("error", name, e.message);
    return { isError: true, content: [{ type: "text", text: `Error: ${e.message}` }] };
  }
});

async function main() {
  startLogWatcher();
  await tools(); // fail fast if the tool code is broken
  await server.connect(new StdioServerTransport());
  serverReady = true;
  log(`running. server dir: ${CFG.SERVER_DIR}, bot name: ${CFG.BOT_NAME}`);
  rcon.connect().then(
    () => log("RCON connected"),
    (e) => log("RCON not ready yet:", e.message)
  );
}

process.on("uncaughtException", (e) => log("uncaught:", e?.stack || e));
process.on("unhandledRejection", (e) => log("unhandled:", e?.stack || e));

main().catch((e) => {
  log("fatal:", e);
  process.exit(1);
});
