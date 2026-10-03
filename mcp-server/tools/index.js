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

// PINKGOLEM_TOOLS=core (or "tools": "core" in pinkgolem.json): offer only the tools a build needs — for small local
// models, whose context fills up with the full list (~14k tokens of descriptions vs ~5k). Hidden tools still answer.
const CORE = ["minecraft_status", "minecraft_get_players", "minecraft_chat", "minecraft_get_chat", "minecraft_wait_for_chat",
  "minecraft_bot", "minecraft_blueprint", "minecraft_generate", "minecraft_jobs", "minecraft_build", "minecraft_build_layers",
  "minecraft_vision", "minecraft_survey", "minecraft_inspect", "minecraft_map", "minecraft_notes", "minecraft_undo"];

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
  const pick = String(process.env.PINKGOLEM_TOOLS || ctx.config.RAW?.tools || "all").trim();
  const only = pick === "all" ? null : new Set(pick === "core" ? CORE : pick.split(/[\s,]+/).map((n) => (n.startsWith("minecraft_") ? n : "minecraft_" + n)));
  for (const p of GROUPS) {
    const g = await load(p);
    const hs = g.handlers(K, ctx);
    for (const t of g.tools) {
      if (!hs[t.name]) throw new Error(`${p}: no handler for ${t.name}`);
      H[t.name] = hs[t.name];
      REQ[t.name] = t.requires || [];
      if (K.missing(t.requires).length) continue;   // hidden: its mod is not installed
      if (only && !only.has(t.name)) continue;      // hidden: not in the chosen tool set
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
    // the same failing call again (small models loop on it): say so on top of the error
    const fails = ctx.state.fails || (ctx.state.fails = new Map());
    const sig = name + JSON.stringify(args);
    const again = (msg) => {
      const n = (fails.get(sig) || 0) + 1;
      fails.delete(sig);
      fails.set(sig, n);
      if (fails.size > 40) fails.delete(fails.keys().next().value);
      return n > 1 ? `This exact call has now failed ${n} times with the same arguments: repeating it won't work. Change the arguments as the error below says, or use another tool.\n${msg}` : msg;
    };
    let r;
    try { r = await h(args); } catch (e) { e.message = again(e.message); throw e; }
    if (r?.isError && r.content?.[0]?.type === "text") r.content[0].text = again(r.content[0].text);
    return r;
  }
  K.handle = handle;
  return { TOOLS, handle };
}
