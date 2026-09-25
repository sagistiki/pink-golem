/**
 * devkit — pure helpers for the developer tools (no server calls), used by tools/dev.js and tools/pack.js:
 *   scarpet   tokenize, stripComments, parseScarpet, lintSource (static checks for the traps that break apps)
 *   zip       readZip, writeZip (deterministic), mergePacks, validatePack (resource packs without dependencies)
 *   records   findRecords / removeAt / accessor: find what a test left behind in a JSON value or a scarpet global
 * install(K) puts them on K.devkit.
 */
import fs from "node:fs";
import path from "node:path";
import zlib from "node:zlib";
import crypto from "node:crypto";

// ═══════════════════════════ scarpet lint ═══════════════════════════
// Built-in function names (extracted from Carpet 26.2's function registrations) and event names.
export const BUILTINS = new Set(("_ abs acos acosh acot add_chunk_ticket air all and append asin asinh assign atan atan2 atanh biome bitwise_and " +
  "bitwise_arithmetic_shift_right bitwise_not bitwise_or bitwise_popcount bitwise_roll_left bitwise_roll_right bitwise_shift_left " +
  "bitwise_shift_right bitwise_xor blast_resistance block block_data block_light block_list block_properties block_sound block_state " +
  "block_tags block_tick blocks_movement bool bossbar break brightness c_for call ceil chunk_tickets close_screen continue convert_date " +
  "copy cos cosh cot coth crafting_remaining_item create_datapack create_explosion create_marker create_screen csc csch current_dimension " +
  "day_time decode_b64 decode_json decreasing define deg delete delete_file destroy diamond difference display_title double_to_long_bits " +
  "draw_shape drop_item effective_light element emitted_light enable_hidden_dimensions encode_b64 encode_json encode_nbt entity_area " +
  "entity_event entity_id entity_list entity_load_handler entity_selector entity_types equal escape_nbt exit exponent fact filter first " +
  "flammable floor for format game_tick generation_status get get_mob_counts handle_event hardness harvest has hash_code identity if " +
  "import in_dimension in_slime_chunk increasing inhabited_time inventory_find inventory_get inventory_has_items inventory_remove " +
  "inventory_set inventory_size is_chunk_generated item_category item_display_name item_list item_tags join keys l last_tick_times length " +
  "light liquid list_files ln ln1p load_app_data loaded loaded_ep loaded_status log log10 log1p logger long_to_double_bits loop lower m " +
  "mandelbrot map map_colour match material max min modify modulo nbt nbt_storage neighbours nondecreasing nonincreasing not number " +
  "opposite or outer pairs parse_nbt particle particle_box particle_line particle_rect perlin place_item player plop poi pos pos_offset " +
  "power print product profile_expr property put query quotient rad rand random_tick range read_file recipe_data rect reduce relight " +
  "reload_chunk relu remove_all_markers replace replace_first reset_chunk reset_seed return round run sample_noise save scan schedule " +
  "scoreboard scoreboard_add scoreboard_display scoreboard_property scoreboard_remove screen_property sec sech see_sky seed set set_biome " +
  "set_poi set_structure signal_event simplex sin sinh sky_light sleep slice solid sort sort_key sound spawn spawn_potential split sqrt " +
  "stack_limit statistic store_app_data str structure_eligibility structure_references structures suffocates sum swap synchronize " +
  "system_info system_variable_get system_variable_set tag_matches tan tanh task task_await task_completed task_count task_dock task_join " +
  "task_ready task_send task_thread task_value team_add team_leave team_list team_property team_remove then throw tick_time " +
  "ticks_randomly time title top transparent try type undef unique unix_time unpack update upper values var vars view_distance volume " +
  "weather while without_updates world_time write_file yield").split(" "));
const EVENTS = new Set(("chunk_generated chunk_loaded chunk_unloaded explosion explosion_outcome lightning player_attacks_entity " +
  "player_breaks_block player_changes_dimension player_chooses_recipe player_clicks_block player_collides_with_entity player_command " +
  "player_connects player_deals_damage player_deploys_elytra player_dies player_disconnects player_drops_item player_drops_stack " +
  "player_escapes_sleep player_finishes_using_item player_interacts_with_block player_interacts_with_entity player_jumps player_message " +
  "player_picks_up_item player_places_block player_placing_block player_releases_item player_respawns player_rides player_right_clicks_block " +
  "player_starts_sneaking player_starts_sprinting player_stops_sneaking player_stops_sprinting player_swaps_hands player_swings_hand " +
  "player_switches_slot player_takes_damage player_trades player_uses_item player_wakes_up server_shuts_down server_starts statistic " +
  "tick tick_ender tick_nether carpet_rule_changes").split(" ").map((e) => "__on_" + e).concat(["__on_start", "__on_close", "__config", "__command"]));
const RESERVED_VARS = new Set(["_", "_i", "_a", "_x", "_y", "_z"]);   // loop / scan variables: assigning them fails ("0 is not a variable")
const OPEN = { "(": ")", "[": "]", "{": "}" };
const CLOSE = { ")": "(", "]": "[", "}": "{" };
const ASSIGN_OPS = new Set(["=", "+=", "-=", "*=", "/=", "%=", "<>"]);

/** Scarpet tokens: strings ('..' with \ escapes), // comments, identifiers, numbers, operators, brackets. */
export function tokenize(src) {
  const toks = [], problems = [];
  let i = 0, line = 1, col = 1;
  const n = src.length;
  const step = () => { if (src[i] === "\n") { line++; col = 1; } else col++; i++; };
  while (i < n) {
    const c = src[i];
    if (c === " " || c === "\t" || c === "\r" || c === "\n") { step(); continue; }
    if (c === "/" && src[i + 1] === "/") { while (i < n && src[i] !== "\n") step(); continue; }
    const L = line, C = col, P = i;
    if (c === "'") {
      step();
      let v = "", closed = false;
      while (i < n) {
        const d = src[i];
        if (d === "\\" && i + 1 < n) { v += src[i + 1]; step(); step(); continue; }
        if (d === "'") { step(); closed = true; break; }
        v += d; step();
      }
      if (!closed) problems.push({ level: "error", rule: "string", line: L, col: C, message: "this string is never closed (a ' is missing) — everything after it is swallowed" });
      toks.push({ t: "str", v, line: L, col: C, pos: P, end: i });
      continue;
    }
    if (/[A-Za-z_]/.test(c)) {
      let v = "";
      while (i < n && /[A-Za-z0-9_]/.test(src[i])) { v += src[i]; step(); }
      toks.push({ t: "id", v, line: L, col: C, pos: P, end: i });
      continue;
    }
    if (/[0-9]/.test(c) || (c === "." && /[0-9]/.test(src[i + 1] || ""))) {
      let v = "";
      while (i < n && /[0-9A-Za-z_.]/.test(src[i])) { v += src[i]; step(); }
      toks.push({ t: "num", v, line: L, col: C, pos: P, end: i });
      continue;
    }
    const two = src.slice(i, i + 2);
    if (["->", "==", "!=", "<=", ">=", "&&", "||", "+=", "-=", "*=", "/=", "%=", "<>"].includes(two)) {
      step(); step();
      toks.push({ t: "op", v: two, line: L, col: C, pos: P, end: i });
      continue;
    }
    step();
    toks.push({ t: OPEN[c] || CLOSE[c] ? c : "op", v: c, line: L, col: C, pos: P, end: i });
  }
  return { toks, problems };
}

/** Commands (script run / script in) do not know // comments — only app files do. Strings are kept intact. */
export function stripComments(src) {
  let out = "", i = 0;
  const n = src.length;
  while (i < n) {
    const c = src[i];
    if (c === "'") { let j = i + 1; while (j < n && src[j] !== "'") { if (src[j] === "\\") j++; j++; } out += src.slice(i, j + 1); i = j + 1; continue; }
    if (c === "/" && src[i + 1] === "/") { while (i < n && src[i] !== "\n") i++; continue; }
    out += c; i++;
  }
  return out.replace(/[ \t]+$/gm, "");
}

/** Brackets, depths, top-level statements and function definitions of a scarpet source. */
export function parseScarpet(src) {
  const { toks, problems } = tokenize(src);
  const N = toks.length;
  const match = new Int32Array(N).fill(-1), depth = new Int32Array(N), parent = new Int32Array(N).fill(-1);
  const st = [], unclosed = [], bracketErrors = [];
  for (let k = 0; k < N; k++) {
    const t = toks[k];
    depth[k] = st.length;
    parent[k] = st.length ? st[st.length - 1] : -1;
    if (OPEN[t.t]) { st.push(k); continue; }
    if (!CLOSE[t.t]) continue;
    if (!st.length) { bracketErrors.push({ k, message: `'${t.t}' closes nothing — one '${t.t}' too many (or a '${CLOSE[t.t]}' missing before it)` }); continue; }
    const top = st[st.length - 1];
    if (toks[top].t === CLOSE[t.t]) { st.pop(); match[top] = k; match[k] = top; depth[k] = st.length; continue; }
    const deeper = st.map((x) => toks[x].t).lastIndexOf(CLOSE[t.t]);
    bracketErrors.push({ k, message: `'${t.t}' does not match the '${toks[top].t}' opened at line ${toks[top].line}:${toks[top].col}` });
    if (deeper >= 0) {
      const lost = st.splice(deeper);
      match[lost[0]] = k; match[k] = lost[0]; depth[k] = st.length;
      unclosed.push(...lost.slice(1));
    }
  }
  unclosed.push(...st);
  const defs = [];
  for (let k = 0; k < N - 1; k++) {
    const t = toks[k];
    if (t.t !== "id" || toks[k + 1].t !== "(") continue;
    const m = match[k + 1];
    if (m < 0 || toks[m + 1]?.v !== "->") continue;
    defs.push({ name: t.v, k, line: t.line, col: t.col, top: depth[k] === 0, body: m + 2, paramsEnd: m });
  }
  const tops = defs.filter((d) => d.top);
  tops.forEach((d, i) => {
    let end = -1;
    const limit = i + 1 < tops.length ? tops[i + 1].k : N;
    for (let j = d.body; j < limit; j++) if (depth[j] === 0 && toks[j].v === ";") { end = j; break; }
    d.semicolon = end >= 0;
    d.end = end >= 0 ? end : limit - 1;
    d.pos = toks[d.k].pos;
    d.endPos = toks[Math.max(d.end, d.k)].end;
  });
  return { toks, problems, match, depth, parent, unclosed, bracketErrors, defs, tops };
}

const IDLE_WORDS = /^(idle|off|stopped|none|ready|waiting|lobby|free|open|closed|done|end(ed)?|)$/i;

/**
 * Static checks for the traps that broke apps on this kind of server. Returns findings
 * { level: error|warning|note, rule, line, col, message } sorted by line.
 */
export function lintSource(src, { name = "app", known = [] } = {}) {
  const P = parseScarpet(src);
  const { toks, match, depth, parent, defs, tops } = P;
  const F = [...P.problems];
  const lines = src.split("\n");
  const add = (level, rule, t, message) => F.push({ level, rule, line: t.line, col: t.col, message });
  const topOf = (k) => { let best = null; for (const d of tops) if (d.k <= k && (d.end >= k || d === tops[tops.length - 1])) best = d; return best; };
  const where = (k) => { const d = topOf(k); return d ? ` (in ${d.name}())` : ""; };

  // 1. brackets
  for (const e of P.bracketErrors) add("error", "brackets", toks[e.k], e.message + where(e.k));
  for (const u of P.unclosed.slice(0, 6)) add("error", "brackets", toks[u], `'${toks[u].t}' opened here${where(u)} is never closed`);
  let hints = 0;
  for (let k = 0; k < toks.length - 1 && hints < 3; k++) {
    const t = toks[k];
    if (t.col !== 1 || t.t !== "id" || depth[k] === 0 || toks[k + 1].t !== "(") continue;
    const m = match[k + 1];
    if (m < 0 || toks[m + 1]?.v !== "->") continue;
    const open = toks[parent[k]];
    add("error", "brackets", t, `${t.v}() starts at column 1 like a top-level function, but ${depth[k]} bracket(s) are still open (innermost '${open.t}' from line ${open.line}) — a closing bracket is probably missing before this line`);
    hints++;
  }
  // 2. top-level statements need ';' between them
  for (const d of tops) {
    const prev = toks[d.k - 1];
    if (prev && prev.v !== ";" && depth[d.k] === 0) add("error", "semicolon", toks[d.k], `missing ';' before ${d.name}() — the previous top-level statement ends at line ${prev.line} without one ("'${d.name}' is not allowed after …")`);
  }
  // 3. definitions: built-in names, duplicates, unknown events
  const defined = new Set([...defs.map((d) => d.name), ...known]);
  const seen = new Map();
  for (const d of tops) {
    if (BUILTINS.has(d.name) && d.name !== "_") add("error", "builtin-name", toks[d.k], `${d.name}() has the name of a scarpet built-in — defining it fails ("Internal error … Index 0 out of bounds") or shadows the built-in; rename it`);
    if (seen.has(d.name)) add("warning", "duplicate", toks[d.k], `${d.name}() is defined twice (first at line ${seen.get(d.name)}); the later one wins`);
    else seen.set(d.name, d.line);
    if (d.name.startsWith("__") && !EVENTS.has(d.name)) add("warning", "event-name", toks[d.k], `${d.name}() is not a scarpet event name — it will never be called (typo?)`);
  }
  // imports
  const imported = new Set();
  for (let k = 0; k < toks.length - 2; k++) if (toks[k].v === "import" && toks[k + 1].t === "(") {
    const end = match[k + 1];
    for (let j = k + 2; j < end; j++) if (toks[j].t === "str") imported.add(toks[j].v);
  }
  // helpers for call arguments
  const argsOf = (k) => {   // k = the '(' token; returns arrays of token indices per argument
    const out = [[]], end = match[k];
    if (end < 0) return out;
    for (let j = k + 1; j < end; j++) {
      if (toks[j].v === "," && depth[j] === depth[k] + 1) { out.push([]); continue; }
      out[out.length - 1].push(j);
    }
    return out;
  };
  const txt = (idx) => idx.map((j) => (toks[j].t === "str" ? `'${toks[j].v}'` : toks[j].v)).join("");
  // 4. per-token checks
  const calls = [];   // {name, k}
  for (let k = 0; k < toks.length; k++) {
    const t = toks[k], nx = toks[k + 1];
    if (t.t === "id" && nx?.t === "(") {
      const m = match[k + 1];
      const isDef = m >= 0 && toks[m + 1]?.v === "->";
      if (!isDef) calls.push({ name: t.v, k });
      // put(m:k, 'field', v) replaces the entry m:k with the STRING 'field'
      if (t.v === "put" && !isDef) {
        const a = argsOf(k + 1);
        if (a.length >= 3 && a[0].some((j) => toks[j].v === ":" && depth[j] === depth[k] + 1) && a[1].length === 1 && toks[a[1][0]].t === "str")
          add("error", "put-accessor", t, `put(${txt(a[0])}, '${toks[a[1][0]].v}', …) replaces ${txt(a[0])} with the string '${toks[a[1][0]].v}' — write ${txt(a[0])}:'${toks[a[1][0]].v}' = … instead`);
      }
      // query(e, 'tags') is deprecated
      if (t.v === "query" && !isDef) {
        const a = argsOf(k + 1);
        if (a[1]?.length === 1 && toks[a[1][0]].v === "tags" && toks[a[1][0]].t === "str")
          add("warning", "deprecated-tags", t, "query(e, 'tags') is deprecated — use query(e, 'has_tag', 'x') or parse_nbt(query(e, 'nbt', 'Tags'))");
      }
      // slice() of an empty list throws "/ by zero"
      if ((t.v === "slice" || t.v === "sort_key") && !isDef) {
        const a = argsOf(k + 1), a0 = txt(a[0] || []);
        if (a0 && !/^\[/.test(a0) && !/^(range|system_info)\(/.test(a0)) {
          const win = lines.slice(Math.max(0, t.line - 4), t.line).join(" ").replace(/\s+/g, "");
          const inner = /^\w+\(([\w:']+)[,)]/.exec(a0)?.[1];   // sort_key(best, …) → best
          const guarded = [a0, inner].filter(Boolean).some((v) => [`length(${v})`, `!${v}`, `if(${v}`, `${v}&&`, `${v}||`, `${v}==[]`, `${v}!=[]`, `${v}+=`].some((g) => win.includes(g)));
          if (!guarded) {
            if (t.v === "slice") add("warning", "empty-slice", t, `slice(${a0}, …) without an emptiness check nearby — slice() of an empty list throws "/ by zero"`);
            else if (toks[match[k + 1] + 1]?.v === ":") add("note", "empty-sort", t, `sort_key(${a0}, …):… — sort_key([]) is fine, but indexing its result gives null when the list is empty`);
          }
        }
      }
      // schedule(n, 'fn') of a function that does not exist
      if (t.v === "schedule" && !isDef) {
        const a = argsOf(k + 1);
        const f = a[1]?.length === 1 && toks[a[1][0]].t === "str" ? toks[a[1][0]].v : null;
        if (f && !defined.has(f) && !BUILTINS.has(f) && !imported.has(f)) add("warning", "unknown-function", t, `schedule(…, '${f}') — no function ${f}() in this app`);
      }
    }
    // assigning a loop / scan variable fails at runtime ("0 is not a variable")
    if (t.t === "id" && RESERVED_VARS.has(t.v) && nx?.t !== "(" && toks[k - 1]?.v !== ":") {
      if (nx && ASSIGN_OPS.has(nx.v) && nx.t === "op") add("error", "reserved-var", t, `${t.v} is a built-in loop/scan variable (_, _i, _a, _x, _y, _z) — assigning it fails with "0 is not a variable"; use another name`);
      const p = parent[k];
      if (p >= 0 && toks[p].t === "[" && match[p] >= 0 && toks[match[p] + 1]?.v === "=" && t.v !== "_")
        add("error", "reserved-var", t, `[… ${t.v} …] = … unpacks into ${t.v}, a built-in loop/scan variable — fails with "0 is not a variable"; use another name (e.g. [x, y, z] or [x, yy, z])`);
    }
    if (t.v === "~" && nx?.t === "str" && nx.v === "tags") add("warning", "deprecated-tags", t, "e ~ 'tags' is deprecated — use query(e, 'has_tag', 'x')");
  }
  // 5. calls to functions that exist nowhere
  const unknown = new Map();
  for (const c of calls) if (!defined.has(c.name) && !BUILTINS.has(c.name) && !imported.has(c.name) && !c.name.startsWith("global_")) {
    if (!unknown.has(c.name)) unknown.set(c.name, c.k);
  }
  for (const [n, k] of unknown) add("warning", "unknown-function", toks[k], `${n}() is not defined in this app and is not a built-in (typo, or defined in another app?)`);
  // 6. call graph → kill inside functions reachable from commands
  const byName = new Map(tops.map((d) => [d.name, d]));
  const edges = new Map();
  for (const d of tops) {
    const s = new Set();
    for (let j = d.body; j <= d.end; j++) {
      const t = toks[j];
      if ((t.t === "id" && toks[j + 1]?.t === "(") || t.t === "str") if (byName.has(t.v) && t.v !== d.name) s.add(t.v);
    }
    edges.set(d.name, s);
  }
  const cfg = byName.get("__config");
  let entries = [];
  const cfgHasCommands = cfg && toks.slice(cfg.body, cfg.end + 1).some((t) => t.t === "str" && t.v === "commands");
  if (cfgHasCommands) entries = [...(edges.get("__config") || [])].filter((n) => !n.startsWith("__"));
  entries.push(...tops.map((d) => d.name).filter((n) => !n.startsWith("_")));
  entries = [...new Set(entries)];
  const via = new Map();
  const queue = entries.map((e) => [e, e]);
  while (queue.length) {
    const [n, from] = queue.shift();
    if (via.has(n)) continue;
    via.set(n, from);
    for (const m of edges.get(n) || []) if (!m.startsWith("__")) queue.push([m, from]);
  }
  const runOf = (d, re) => {
    for (let j = d.body; j <= d.end; j++) if (toks[j].v === "run" && toks[j + 1]?.t === "(") {
      let q = j + 2;
      if (toks[q]?.v === "str" && toks[q + 1]?.t === "(") q += 2;
      if (toks[q]?.t === "str" && re.test(toks[q].v)) return toks[j];
    }
    return null;
  };
  for (const d of tops) {
    if (!via.has(d.name)) continue;
    const hit = runOf(d, /^\s*kill\b/);
    if (hit) add("warning", "deferred-kill", hit, `run('kill …') in ${d.name}(), which a command can reach (via ${via.get(d.name)}()) — inside a command it only happens after the command ends; use modify(e, 'remove') when the next lines expect the entity gone`);
  }
  // 7. damage dealt by the app + __on_player_dies
  if (byName.has("__on_player_dies")) {
    const dmg = tops.map((d) => runOf(d, /^\s*damage\b/)).find(Boolean);
    if (dmg) add("note", "own-death-event", dmg, "this app deals damage with run('damage …') and relies on __on_player_dies: a death caused inside the app's own tick/schedule never reaches its own __on_player_dies (from a command it is only deferred) — check health right after the damage too");
  }
  // 8. scope
  if (cfg && !toks.slice(cfg.body, cfg.end + 1).some((t) => t.t === "str" && t.v === "global") && /\bglobal_\w+/.test(src))
    add("note", "scope", toks[cfg.k], "__config has no 'scope' -> 'global': every player gets their own copy of the globals (and /script in <app> from the console patches only the server's copy)");
  const order = { error: 0, warning: 1, note: 2 };
  F.sort((a, b) => a.line - b.line || order[a.level] - order[b.level]);
  const count = (l) => F.filter((f) => f.level === l).length;
  return { name, errors: count("error"), warnings: count("warning"), notes: count("note"), findings: F, functions: tops.length };
}

// ═══════════════════════════ zip (pure, no dependencies) ═══════════════════════════
export function readZip(buf) {
  let e = -1;
  for (let i = buf.length - 22; i >= Math.max(0, buf.length - 65557); i--) if (buf.readUInt32LE(i) === 0x06054b50) { e = i; break; }
  if (e < 0) throw new Error("not a zip file (no end of central directory)");
  const n = buf.readUInt16LE(e + 10), cdOff = buf.readUInt32LE(e + 16);
  if (cdOff === 0xffffffff || n === 0xffff) throw new Error("zip64 archives are not supported");
  const out = [];
  let p = cdOff;
  for (let k = 0; k < n; k++) {
    if (buf.readUInt32LE(p) !== 0x02014b50) throw new Error("corrupt central directory");
    const method = buf.readUInt16LE(p + 10), csize = buf.readUInt32LE(p + 20), usize = buf.readUInt32LE(p + 24);
    const nl = buf.readUInt16LE(p + 28), xl = buf.readUInt16LE(p + 30), cl = buf.readUInt16LE(p + 32), lo = buf.readUInt32LE(p + 42);
    const name = buf.toString("utf8", p + 46, p + 46 + nl);
    p += 46 + nl + xl + cl;
    if (name.endsWith("/")) continue;
    const start = lo + 30 + buf.readUInt16LE(lo + 26) + buf.readUInt16LE(lo + 28);
    const raw = buf.subarray(start, start + csize);
    let data = null;
    out.push({ name, usize, get data() { return (data ??= method === 0 ? raw : method === 8 ? zlib.inflateRawSync(raw) : (() => { throw new Error(`${name}: compression method ${method} not supported`); })()); } });
  }
  return out;
}
/** Deterministic zip (fixed 1980-01-01 timestamps): the same inputs give the same sha1. */
export function writeZip(entries) {
  const parts = [], cd = [];
  let off = 0;
  for (const { name, data } of entries) {
    const nb = Buffer.from(name, "utf8"), crc = zlib.crc32(data) >>> 0;
    const def = zlib.deflateRawSync(data, { level: 9 });
    const stored = def.length >= data.length, body = stored ? data : def, method = stored ? 0 : 8;
    const lh = Buffer.alloc(30);
    lh.writeUInt32LE(0x04034b50, 0); lh.writeUInt16LE(20, 4); lh.writeUInt16LE(0x800, 6); lh.writeUInt16LE(method, 8);
    lh.writeUInt16LE(0, 10); lh.writeUInt16LE(0x21, 12); lh.writeUInt32LE(crc, 14); lh.writeUInt32LE(body.length, 18);
    lh.writeUInt32LE(data.length, 22); lh.writeUInt16LE(nb.length, 26); lh.writeUInt16LE(0, 28);
    parts.push(lh, nb, body);
    const ch = Buffer.alloc(46);
    ch.writeUInt32LE(0x02014b50, 0); ch.writeUInt16LE(20, 4); ch.writeUInt16LE(20, 6); ch.writeUInt16LE(0x800, 8); ch.writeUInt16LE(method, 10);
    ch.writeUInt16LE(0, 12); ch.writeUInt16LE(0x21, 14); ch.writeUInt32LE(crc, 16); ch.writeUInt32LE(body.length, 20); ch.writeUInt32LE(data.length, 24);
    ch.writeUInt16LE(nb.length, 28); ch.writeUInt32LE(off, 42);
    cd.push(ch, nb);
    off += 30 + nb.length + body.length;
  }
  const cdBuf = Buffer.concat(cd), eocd = Buffer.alloc(22);
  eocd.writeUInt32LE(0x06054b50, 0); eocd.writeUInt16LE(entries.length, 8); eocd.writeUInt16LE(entries.length, 10);
  eocd.writeUInt32LE(cdBuf.length, 12); eocd.writeUInt32LE(off, 16);
  return Buffer.concat([...parts, cdBuf, eocd]);
}
export const sha1 = (b) => crypto.createHash("sha1").update(b).digest("hex");

// JSON files that several packs may each bring: merged instead of "first wins"
const MERGEABLE = [
  { re: /^assets\/[^/]+\/font\/.+\.json$/, list: "providers" },
  { re: /^assets\/[^/]+\/atlases\/.+\.json$/, list: "sources" },
  { re: /^assets\/[^/]+\/lang\/.+\.json$/, object: true },
  { re: /^assets\/[^/]+\/sounds\.json$/, object: true },
];

/** Merge pack zips (first part wins on a clash; fonts/atlases/lang/sounds JSON are merged) and validate the result. */
export function mergePacks(parts, { mergeJson = true } = {}) {
  const files = new Map();   // path -> { data, from }
  const clashes = [], merged = [], identical = [];
  for (const part of parts) {
    for (const e of readZip(part.buf)) {
      const n = e.name;
      if (!files.has(n)) { files.set(n, { data: e.data, from: part.name }); continue; }
      if (n === "pack.mcmeta" || n === "pack.png") continue;
      const cur = files.get(n);
      if (cur.data.equals(e.data)) { identical.push(n); continue; }
      const rule = mergeJson && MERGEABLE.find((r) => r.re.test(n));
      if (rule) {
        try {
          const a = JSON.parse(cur.data.toString("utf8")), b = JSON.parse(e.data.toString("utf8"));
          let out;
          if (rule.list) out = { ...b, ...a, [rule.list]: [...(a[rule.list] || []), ...(b[rule.list] || [])] };
          else out = { ...b, ...a };
          files.set(n, { data: Buffer.from(JSON.stringify(out, null, 1)), from: `${cur.from}+${part.name}` });
          merged.push(`${n} (${cur.from} + ${part.name})`);
          continue;
        } catch {}
      }
      clashes.push({ path: n, kept: cur.from, dropped: part.name });
    }
  }
  return { files, clashes, merged, identical };
}

export function validatePack(files) {
  const problems = [], stats = { json: 0, models: 0, items: 0, fonts: 0, textures: 0, sounds: 0 };
  const has = (p) => files.has(p);
  const idOf = (s) => { const [ns, p] = String(s).includes(":") ? String(s).split(":") : ["minecraft", String(s)]; return { ns, p }; };
  const vanilla = (ns) => ns === "minecraft";
  const json = new Map();
  for (const [p, f] of files) {
    if (/\.(json|mcmeta)$/.test(p)) {
      stats.json++;
      try { json.set(p, JSON.parse(f.data.toString("utf8").replace(/^\uFEFF/, ""))); }
      catch (e) { problems.push({ level: "error", path: p, from: f.from, message: `invalid JSON: ${e.message}` }); }
    }
    if (p.endsWith(".png")) {
      stats.textures++;
      if (f.data.length < 8 || f.data.readUInt32BE(0) !== 0x89504e47) problems.push({ level: "error", path: p, from: f.from, message: "not a PNG file" });
    }
  }
  const meta = json.get("pack.mcmeta");
  let format = null;
  if (!files.has("pack.mcmeta")) problems.push({ level: "error", path: "pack.mcmeta", message: "missing — Minecraft rejects the pack" });
  else if (meta) {
    format = meta.pack?.pack_format ?? meta.pack?.min_format ?? null;
    if (format === null) problems.push({ level: "error", path: "pack.mcmeta", message: "no pack.pack_format / min_format" });
  }
  // sprites made by atlas sources (paletted_permutations: <texture>_<key>) exist without a .png of their own
  const generated = new Set();
  for (const [p, j] of json) if (/^assets\/[^/]+\/atlases\/.+\.json$/.test(p)) for (const src of j.sources || []) {
    if (String(src.type || "").replace(/^minecraft:/, "") !== "paletted_permutations") continue;
    for (const t of src.textures || []) for (const key of Object.keys(src.permutations || {})) {
      const r = idOf(t);
      generated.add(`assets/${r.ns}/textures/${r.p}${src.separator ?? "_"}${key}.png`);
    }
  }
  const need = (p, from, what, ref) => { if (!has(p) && !generated.has(p)) problems.push({ level: "error", path: from, from: files.get(from)?.from, message: `${what} ${ref} → ${p} is not in the pack` }); };
  for (const [p, j] of json) {
    let m;
    if ((m = /^assets\/([^/]+)\/models\/(.+)\.json$/.exec(p))) {
      stats.models++;
      if (j.parent && !/^builtin\//.test(j.parent)) { const r = idOf(j.parent); if (!vanilla(r.ns) && !/^builtin\//.test(r.p)) need(`assets/${r.ns}/models/${r.p}.json`, p, "parent", j.parent); }
      for (const v of Object.values(j.textures || {})) if (typeof v === "string" && !v.startsWith("#")) { const r = idOf(v); if (!vanilla(r.ns)) need(`assets/${r.ns}/textures/${r.p}.png`, p, "texture", v); }
    } else if ((m = /^assets\/([^/]+)\/items\/(.+)\.json$/.exec(p))) {
      stats.items++;
      const walk = (o) => {
        if (Array.isArray(o)) return o.forEach(walk);
        if (!o || typeof o !== "object") return;
        if (typeof o.model === "string" && /model$/.test(String(o.type || ""))) { const r = idOf(o.model); if (!vanilla(r.ns)) need(`assets/${r.ns}/models/${r.p}.json`, p, "model", o.model); }
        for (const v of Object.values(o)) if (v && typeof v === "object") walk(v);
      };
      walk(j.model);
      if (!j.model) problems.push({ level: "error", path: p, from: files.get(p)?.from, message: "item definition without a 'model'" });
    } else if ((m = /^assets\/([^/]+)\/font\/(.+)\.json$/.exec(p))) {
      stats.fonts++;
      for (const pr of j.providers || []) {
        const type = String(pr.type || "").replace(/^minecraft:/, "");
        if (type === "bitmap") {
          const r = idOf(pr.file);
          if (!vanilla(r.ns)) need(`assets/${r.ns}/textures/${r.p}`, p, "bitmap", pr.file);
          const w = (pr.chars || []).map((s) => Array.from(s).length);
          if (w.length && w.some((x) => x !== w[0])) problems.push({ level: "error", path: p, from: files.get(p)?.from, message: `bitmap ${pr.file}: chars rows have different lengths (${w.join(",")})` });
          if (pr.ascent !== undefined && pr.height !== undefined && pr.ascent > pr.height) problems.push({ level: "error", path: p, from: files.get(p)?.from, message: `bitmap ${pr.file}: ascent ${pr.ascent} > height ${pr.height}` });
        } else if (type === "ttf") { const r = idOf(pr.file); if (!vanilla(r.ns)) need(`assets/${r.ns}/font/${r.p}`, p, "ttf", pr.file); }
        else if (type === "reference") { const r = idOf(pr.id); if (!vanilla(r.ns)) need(`assets/${r.ns}/font/${r.p}.json`, p, "reference", pr.id); }
      }
    } else if ((m = /^assets\/([^/]+)\/sounds\.json$/.exec(p))) {
      for (const [ev, def] of Object.entries(j)) for (const s of def.sounds || []) {
        const nm = typeof s === "string" ? s : s.type === "event" ? null : s.name;
        if (!nm) continue;
        stats.sounds++;
        const r = idOf(nm);
        if (!vanilla(r.ns) || m[1] !== "minecraft") { if (!vanilla(r.ns)) need(`assets/${r.ns}/sounds/${r.p}.ogg`, p, `sound ${ev}`, nm); }
      }
    }
  }
  return { format, problems, stats };
}

// ── small helpers (pure)
function walk(dir, maxDepth = 4, d = 0) {
  const out = [];
  let ents = [];
  try { ents = fs.readdirSync(dir, { withFileTypes: true }); } catch { return out; }
  for (const e of ents) {
    const f = path.join(dir, e.name);
    if (e.isDirectory()) { if (d < maxDepth && e.name !== "region" && e.name !== "entities" && e.name !== "poi") out.push(...walk(f, maxDepth, d + 1)); }
    else out.push(f);
  }
  return out;
}
const segsOf = (p) => (Array.isArray(p) ? p : p === "" || p === undefined || p === null ? [] : String(p).split("."));
/** ['a', 0] → scarpet accessor global_x:'a':0 */
function accessor(global, p) {
  return global + segsOf(p).map((s) => (typeof s === "number" ? `:${s}` : `:'${String(s).replace(/\\/g, "\\\\").replace(/'/g, "\\'")}'`)).join("");
}
function getPath(o, p, create = false) {
  let cur = o;
  for (const s of segsOf(p)) { if (cur == null) return undefined; if (!(s in cur) && create) cur[s] = {}; cur = cur[s]; }
  return cur;
}
function setPath(o, p, v) {
  const segs = [...segsOf(p)], last = segs.pop();
  const parent = getPath(o, segs, true);
  if (parent && typeof parent === "object") parent[last] = v;
}
/** Paths of records that belong to the given names: map keys equal to a name, and list entries that are the name or
 *  directly contain it (['Pt_A', 1234], {'name' -> 'Pt_A', …}). Later list indices come first so deleting in order is safe. */
function findRecords(o, names, pre = []) {
  const out = [];
  const holds = (v) => (typeof v === "string" ? names.includes(v) : Array.isArray(v) ? v.some((x) => typeof x === "string" && names.includes(x))
    : v && typeof v === "object" ? Object.values(v).some((x) => typeof x === "string" && names.includes(x)) : false);
  if (Array.isArray(o)) o.forEach((v, i) => { if (holds(v)) out.push([...pre, i]); else out.push(...findRecords(v, names, [...pre, i])); });
  else if (o && typeof o === "object") for (const [k, v] of Object.entries(o)) { if (names.includes(k)) out.push([...pre, k]); else out.push(...findRecords(v, names, [...pre, k])); }
  return out.sort((a, b) => { for (let i = 0; i < Math.min(a.length, b.length); i++) if (a[i] !== b[i]) return typeof a[i] === "number" && typeof b[i] === "number" ? b[i] - a[i] : String(a[i]) < String(b[i]) ? -1 : 1; return b.length - a.length; });
}
function removeAt(o, p) {
  const parent = getPath(o, p.slice(0, -1)), last = p[p.length - 1];
  if (Array.isArray(parent)) parent.splice(last, 1); else if (parent) delete parent[last];
}
function checkValue(v, exp, subst) {
  if (typeof exp !== "object" || exp === null) exp = { equals: exp };
  if (exp.equals !== undefined) { const e = String(typeof exp.equals === "string" ? subst(exp.equals) : exp.equals); return [String(v) === e || (!isNaN(Number(e)) && Number(v) === Number(e)), `expected ${e}`]; }
  if (exp.contains !== undefined) return [String(v).includes(subst(exp.contains)), `expected to contain ${exp.contains}`];
  if (exp.matches !== undefined) return [new RegExp(exp.matches).test(String(v)), `expected /${exp.matches}/`];
  const f = v === null || /^(null|false|0|0\.0|''|\[\]|\{\}|)$/.test(String(v).trim());
  if (exp.falsy) return [f, "expected falsy"];
  return [!f, "expected truthy"];
}


export function install(K) {
  K.devkit = { BUILTINS, tokenize, stripComments, parseScarpet, lintSource, readZip, writeZip, mergePacks, validatePack, sha1,
    walk, segsOf, accessor, getPath, setPath, findRecords, removeAt, checkValue };
}
