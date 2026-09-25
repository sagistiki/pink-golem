# Contributing

Thank you for helping. This page shows how to add each kind of thing to ClawdBlock: a tool, a lib helper, a
blueprint, a scarpet app, a reference page or a lesson. It also covers how to test your change and what a good
pull request looks like. [architecture.md](architecture.md) gives the background for the code sections.

**Ground rules**

- **Match the surrounding code.** Same indentation, quoting and naming, similar line length, a short header
  comment per file. Read two neighbouring files before you write.
- **No new dependencies.** The MCP server depends only on the MCP SDK; the Python side uses only the standard
  library; scarpet apps are single files. This keeps installation a one-command affair on every system.
- **Everything is in English**, and nothing private: no real server names, player names, home paths, passwords or
  screenshots with private chat.
- **Test on a real server.** Most bugs in this project only show up in a live world.

---

## Add a tool

Tools live in **groups** in `mcp-server/tools/`: `connection.js`, `chat.js`, `build.js`, `look.js`, `survey.js`,
`rails.js`, `body.js`, `memory.js`. Each group exports a `tools` array (the schemas) and a `handlers(K, ctx)` function that returns one
async handler per tool name. `K` is the shared helper object built from `lib/*.js`.

Add the schema to the group that fits:

```js
{
  name: "minecraft_biome",
  description: "Which biome is at a position (e.g. to pick a matching style). pos: [x, y, z].",
  inputSchema: { type: "object", properties: { pos: vec }, required: ["pos"] },
},
```

and the handler with **the same name**:

```js
async minecraft_biome(args) {
  const [x, y, z] = K.V(args.pos);
  const r = await K.scarpet(`biome(${x}, ${y}, ${z})`);
  return K.text({ pos: [x, y, z], biome: r.value });
},
```

Things to know:

| Topic | How |
|---|---|
| Replies | `K.text(stringOrObject)` for results, `K.fail("what went wrong + what to do")` for refusals. Thrown errors become `Error: …` replies |
| Needs a mod | add `requires: ["worldedit"]` to the schema (keys: `carpet`, `worldedit`, `bluemap`, `polydecorations`, `essential_commands`, `chunky`, `spark`, `lithium`, `ledger`). The tool is hidden when the mod is missing |
| Changes blocks | go through the rails like `tools/build.js` does: `K.targetsFromCommands` → `K.zoneGuard` → `K.snapshotFor` → run → `K.afterBuild` |
| Runs commands | `K.cmd(c)` (locked, one at a time across all AI clients), `K.runMany(list)`, `K.scarpet(expr)`, `K.inApp("cu", expr)` |
| Files from the model | always `K.safePath(p)`; it keeps paths inside the ClawdBlock folder |
| Arguments sent as strings | some clients send `"3"` or `"true"`. If your new argument is a number, boolean or array, add its name to `NUMS`, `BOOLS` or `ARRAYS` in `tools/index.js` |
| A new group file | add it to `GROUPS` in `tools/index.js` |

**Write the description for a model**, since every AI reads every description in every session. Say what the tool
does, when to use it, the key arguments and the main pitfall, in a few sentences. The whole tool list already costs
about 7,000 tokens, which matters for small local models.

## Add a lib helper

Helpers that several tools share go in `mcp-server/lib/*.js`. Each module exports `install(K, ctx)` and adds
functions to `K`:

```js
/** terrain — ground checks for a building site. */
export function install(K) {
  /** Ground height over an area: {min, max, avg} from the cu app. min === max means the site is level. */
  K.siteSurface = async (x1, z1, x2, z2) => {
    const out = await K.inApp("cu", `surface(${x1}, ${z1}, ${x2}, ${z2})`);
    const num = (k) => Number((new RegExp(`${k}: (-?[\\d.]+)`).exec(out) || [])[1]);
    return { min: num("min"), max: num("max"), avg: num("avg") };
  };
}
```

Add a new file to `LIBS` in `tools/index.js`. Order matters only for code that runs *during* `install`; functions
call each other through `K` at call time. Put pure logic (no RCON, no files) in its own module like `pathfind.js`
or `sim.js` so it can be tested without a server.

## Hot reload while you work

Edits to `lib/` and `tools/` take effect on the next tool call, even in a running AI session. Only
`mcp-server/index.js` needs a client restart. So you can ask the AI to try your tool the moment you save.

---

## Add a blueprint

A blueprint is a generator that anyone (and any model) can run with one tool call. The full walkthrough, with a
complete example, is in **[writing-blueprints.md](writing-blueprints.md)**. The checklist:

1. File in `skill/clawdblock/blueprints/<name>.py`, with a docstring header like the others: what it builds and
   why it is a good example, the command line, what `--at` means (front-left corner or centre), the size, and
   the job files it writes.
2. `sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))`, then `from mclib import …` and
   `import parts as P`.
3. `a = parse_args({"name": …, "style": …})`, and `f = Frame(a.x, a.y, a.z, a.facing)`. Local coordinates only,
   and `{front}`/`{back}`/`{left}`/`{right}`/`{axis_i}`/`{axis_k}` in block states, so it works facing any way.
4. Reuse `parts.py` instead of re-inventing a door, a roof or a lamp. If you need a new part, add it to
   `parts.py` and to `catalog.py`.
5. One `Build()` per phase (structure / interior / outside), each saved as `f"{a.name}-1"`, `-2`, `-3`.
6. Print the box and the entrance at the end: the AI uses them for the access check and the world map.
7. Run it by hand in all four directions (`--facing north|south|east|west`) and check that it doesn't crash.
8. Build it on a real server (below) and look at it from two sides and inside.
9. Add a row to the blueprint table in `skill/clawdblock/SKILL.md` (Part 4), and to the list in `SYSTEM_PROMPT.md`
   if small models should use it.

## Add a scarpet app

Game-logic apps go in `scarpet-apps/<name>.sc`. Follow the header format of the existing apps, because
`python3 clawdblock.py apps list` shows the first comment line:

```
// vendor.sc — button stands that serve things: a drink bar, an ice-cream cart, a gift shop.
// Stands are read from vendor.data/stands.json, a list of:
//   {"name": "beach bar", "button": [x,y,z], ...}
// What happens when a player uses it, in one or two lines.
// Reload after editing stands.json:  script in vendor run reload()
```

| Rule | Why |
|---|---|
| `__config() -> {'stay_loaded' -> true, 'scope' -> 'global'};` | stays loaded across restarts, one shared state |
| Settings in `<app>.data/*.json`, read with `read_file('stands', 'json')` | the AI (or a blueprint) can configure it without editing code. The folder is `server/world/scripts/<app>.data/` |
| A `reload()` function, and `__on_start() -> reload();` | configuration changes apply without reloading the app |
| Skip fake players where it matters: `query(p, 'player_type') == 'fake'` | the AI's bot and the helpers shouldn't trigger shows or win races |
| Start-up cleans up politely | `script load` re-runs start-up. Never strand a player who is mid-ride or mid-race |

Install it on your server with `python3 clawdblock.py apps add <name>`, then test it with real players.

## Add a reference page

Reference pages in `skill/clawdblock/reference/` are read **by AI models**, from small local models to Claude, and
by curious humans. Style:

- Start with 2-4 lines: what the page is for and when to read it.
- Prefer tables, numbered checklists and short code blocks with exact block strings and tool calls.
- Give every rule its reason in a few words ("paths go IN the ground: a path one block too high is a step at the door").
- Add a clearly marked **Common mistakes** section, and end with **See also** links (relative, e.g. `roofs.md`).
- 120-300 lines, no padding. Use tool names exactly as in `mcp-server/tools/*.js` and library functions exactly as
  in `mclib.py` / `parts.py`.
- Always write "the ground block (flat world: y = -61)" and say how to read the ground elsewhere.

Then add the page to the table in Part 8 of `SKILL.md`.

## Add a lesson

Lessons live in `skill/clawdblock/reference/lessons.md`, numbered, in sections. Each is one bold sentence telling
what went wrong, then the general rule and how to avoid it:

```markdown
13. **A lantern on top of a fence post popped off when the fence was replaced.** Place supports before what they
    carry, in the same job, and verify both.
```

Turn stories into generic lessons. Mention no real builds, servers or people. A good lesson has cost a real mistake
and prevents the next one.

---

## Testing

| What | Command | Needs a server? |
|---|---|---|
| The tool layer loads (syntax, wiring, every tool has a handler) | `cd mcp-server && npm run check` | no |
| Everything is installed and talking | `python3 clawdblock.py doctor` (it also runs the load check) | partly |
| A generator runs | `python3 skill/clawdblock/blueprints/<name>.py --at 0,-61,0 --facing east` | no |
| Tools against a live world | `node test/run.mjs '<list of calls>'` | yes |

`test/run.mjs` drives the MCP server like an AI client would. Every call runs in **one** process, so background
jobs survive between calls:

```bash
cd mcp-server
node test/run.mjs '[["minecraft_status",{}],
  ["minecraft_generate",{"script":"skill/clawdblock/blueprints/cottage.py","args":["--at","200,-61,0","--facing","south"],"build":true}],
  ["minecraft_jobs",{"action":"wait"}], ["minecraft_jobs",{"action":"wait"}], ["minecraft_jobs",{"action":"wait"}],
  ["minecraft_screenshot",{"from":[192,-61,-8],"to":[215,-45,12]}]]'
```

You can also put the list in a file: `node test/run.mjs calls.json`. It prints the text of each result. Pictures
are saved in `data/screenshots/`. The exit code is 1 if any call failed. Use a test world (`new-world`), or a spot
far from real builds.

## Pull request checklist

- [ ] `npm run check` passes, and `python3 clawdblock.py doctor` shows no new problems.
- [ ] Tested on a real server; **screenshots** in the PR for anything visible (iso from two sides, and a `cut_y`
      cutaway for interiors). Say which Minecraft version you tested on.
- [ ] New blueprints run in all four facings; builds finish with `errors: 0`, `verify.mismatches: 0` (except
      `grass_block>dirt`) and an access check `ok: true`.
- [ ] Docs updated: the tool table in `SKILL.md`, a reference page, `SYSTEM_PROMPT.md`, or these docs, if your
      change affects them.
- [ ] English only, no private data (names, servers, paths, passwords, private chat in screenshots).
- [ ] No new dependencies; the code matches its neighbours.
- [ ] One topic per pull request, with a short description of why.

## See also

[Architecture](architecture.md) · [Writing blueprints](writing-blueprints.md) · [Upgrading](upgrading.md)
· [Troubleshooting](troubleshooting.md)
