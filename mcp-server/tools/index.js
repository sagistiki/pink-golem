/**
 * tools/index.js — assembles the shared helper object K from lib/*.js and the tool groups from tools/*.js.
 * index.js re-imports this file (with a new ?v=) whenever any file in lib/ or tools/ changes, and this file passes
 * the same version on to everything it imports, so the whole tool layer hot-reloads together.
 *
 * Adding a tool: put { name, description, inputSchema, requires? } in a group's `tools` array and a handler with the
 * same name in its `handlers(K)` object. `requires: ["worldedit"]` hides the tool when that mod is not installed.
 */
const v = new URL(import.meta.url).search;
const load = (p) => import(new URL(p + v, import.meta.url).href);

const LIBS = ["../lib/core.js", "../lib/features.js", "../lib/world.js", "../lib/safety.js", "../lib/crew.js", "../lib/bot.js", "../lib/jobs.js", "../lib/sight.js", "../lib/context.js", "../lib/trust.js", "../lib/devkit.js"];
const GROUPS = ["./connection.js", "./chat.js", "./build.js", "./look.js", "./survey.js", "./rails.js", "./body.js", "./memory.js", "./health.js", "./dev.js", "./pack.js", "./entities.js"];

// JSON-ish arguments some clients send as strings
const BOOLS = ["background", "keep_helpers", "undo", "allow_protected", "allow_overwrite", "pathfind", "bubble", "list", "stop_on_error", "all_matching", "force", "raw", "overlay", "entities", "dark", "simulate", "check_access", "build", "dry_run", "changes_only", "any_owner", "mention_only", "update", "verify", "skip_check", "top", "heights", "closed", "rider", "keep", "all", "fix", "confirm"];
const NUMS = ["helpers", "pace_ms", "swing_every", "steps", "count", "id", "radius", "scale", "height", "timeout_seconds", "hours", "cut_y", "yaw", "pitch", "fov", "distance", "width", "depth", "margin", "min_room", "size_x", "size_z", "limit", "since_id", "lines", "seconds", "every_ticks", "times", "slot", "stop_distance", "angle", "max", "gap", "boost_every", "curve_boost", "speed", "poll_ms", "job"];
const ARRAYS = ["commands_files", "commands", "from", "to", "pos", "path", "entrance", "box", "size", "likes", "aliases", "roles", "targets", "views", "types", "track", "blocks", "entities", "warps", "entrances", "files", "args", "points", "until_pos", "at", "tags", "uuids"];

export async function create(ctx) {
  const K = {
    Render: await load("../render.js"),
    PF: await load("../pathfind.js"),
    Sim: await load("../sim.js"),
    AN: await load("../analyze.js"),
    WM: await load("../worldmap.js"),
  };
  for (const p of LIBS) (await load(p)).install(K, ctx);

  const TOOLS = [];
  const H = {};
  const REQ = {};
  for (const p of GROUPS) {
    const g = await load(p);
    const hs = g.handlers(K, ctx);
    for (const t of g.tools) {
      if (!hs[t.name]) throw new Error(`${p}: no handler for ${t.name}`);
      H[t.name] = hs[t.name];
      REQ[t.name] = t.requires || [];
      if (K.missing(t.requires).length) continue;   // hidden: its mod is not installed
      const { requires, ...schema } = t;
      TOOLS.push(schema);
    }
  }

  async function handle(name, args) {
    args = { ...(args || {}) };
    for (const k of BOOLS) if (args[k] === "true" || args[k] === "false") args[k] = args[k] === "true";
    for (const k of NUMS) if (typeof args[k] === "string" && /^-?\d+(\.\d+)?$/.test(args[k])) args[k] = Number(args[k]);
    for (const k of ARRAYS) if (typeof args[k] === "string" && /^\s*\[/.test(args[k])) { try { args[k] = JSON.parse(args[k]); } catch {} }
    const h = H[name];
    if (!h) throw new Error(`Unknown tool: ${name}`);
    const miss = K.missing(REQ[name]);
    if (miss.length) throw new Error(`${name} needs the ${miss.join(", ")} mod — install it with: python3 pinkgolem.py mods add ${miss.join(" ")}`);
    K.checkTrust(name, args);   // lib/trust.js: owners, guests, !approve — enforced here, not in the prompt
    return await h(args);
  }
  K.handle = handle;
  return { TOOLS, handle };
}
