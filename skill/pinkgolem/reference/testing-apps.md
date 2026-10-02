# Testing and maintaining scarpet apps (and the server resource pack)

Read this before you change, reload or test a scarpet app on a server where people play, and before you ship a new
resource pack. Three tools do the work:

| Tool | What it's for |
|---|---|
| `minecraft_app` | `lint` (static checks) · `status` (is anyone using it?) · `reload` (only when idle) · `patch` (change one function live) · `errors` (from the log) |
| `minecraft_playtest` | a scripted test with fake players in ONE call → a timeline + PASS/FAIL, cleanup always included |
| `minecraft_pack` | `build` (merge + validate) · `deploy` (new url, server.properties, live push) · `status` |

The loop for any app change: **lint → patch (or reload when idle) → playtest → errors**.

## 1. Lint first — every time

`minecraft_app action:lint app:race` (or `all:true`, or `file:…`). It reads the source only; nothing runs. Each rule
is a trap that has broken real apps:

| Rule | The trap | Fix |
|---|---|---|
| `brackets` | an unclosed `(`: Carpet says only "Mismatched parentheses" and the app fails to load. Lint gives the opening line, the function, and the first later line that starts like a top-level function while brackets are still open — the ')' is missing just before it | close it where lint points |
| `semicolon` | two top-level statements without `;` between them: `'f2' is not allowed after …` | end every top-level definition with `;` |
| `put-accessor` | `put(m:k, 'field', v)` replaces the entry `m:k` with the **string** `'field'` | `m:k:'field' = v` |
| `reserved-var` | assigning `_`, `_i`, `_a`, `_x`, `_y`, `_z` (loop and `scan()` variables) fails at runtime: "0 is not a variable". `[x, _y, z] = pos(p)` is the classic. Other `_names` are fine | `[x, y, z] = pos(p)` |
| `builtin-name` | a function named like a built-in (`top`, `block`, `print` …) → "Internal error … Index 0 out of bounds" | rename it |
| `empty-slice` | `slice(list, …)` of an empty list throws "/ by zero" (`sort_key([])` is fine) | `if (list, slice(list, 0, n), [])` |
| `deferred-kill` | `run('kill …')` in a function a command can reach: inside a command, `run()` only happens after the command ends, so the next line still sees the entity | `modify(e, 'remove')` |
| `own-death-event` | the app deals damage with `run('damage …')` and relies on its own `__on_player_dies`: a death caused inside the app's own tick never reaches its own event handler | check health right after the damage **and** eliminate on a periodic check / on disconnect |
| `deprecated-tags` | `query(e, 'tags')` | `query(e, 'has_tag', 'x')` or `parse_nbt(query(e, 'nbt', 'Tags'))` |
| `unknown-function`, `event-name`, `duplicate`, `scope` | typos, `__on_player_dise`, a function defined twice, a missing `'scope' -> 'global'` | |

## 2. Is it in use? — `status`

`minecraft_app action:status app:race` answers "may I touch it now?". If the app's `status()` returns a boolean
`'busy'` (or `'idle'`), that decides — the app knows best; tags and area are then only reported. Otherwise:

- **state**: the app's `status()` (or `global_state`). Anything but idle/off/lobby/ready/waiting… = busy; a `status()`
  that names a real player online = busy.
- **tags**: real players carrying a tag the app sets (`modify(p, 'tag', 'x')`, `tag=x`, `has_tag`).
- **area**: real players inside a world-map entry or zone whose notes mention `<app>.sc` (+8 blocks).

Give every game app a `status()` that returns `{'state' -> …, 'busy' -> …, 'players' -> …}`: the tools, and you,
can then tell "idle" from "a round is running" in one call, whatever the app calls its idle state.

## 3. Changing a running app

**`patch` — one or more functions, live, state kept.** Use it for any fix while people play:

```
minecraft_app action:patch app:race code:"_finish(p, n, st) -> ( … );"
minecraft_app action:patch app:race function:_finish        # push the definition you already edited in race.sc
```

It lints the code, sends it to the running app, then writes it into the `.sc` file (replacing the old definition;
a backup goes to `data/app-backups/`). Globals, running games and scheduled calls are untouched. Code of any size
works: RCON takes ≤1400 bytes, so the tool uploads the text into a scratch global of the console's script host in
pieces and runs `schedule(0, _() -> run('script in <app> run ' + text))`. Two facts behind it:

- Commands don't know `//` comments (only app files do) — the tool strips them; newlines are fine.
- `script in <app> run …` **loads** the app if it isn't loaded. To check without loading, use
  `system_info('app_list')`.

**`reload` — the whole file, state lost.** `minecraft_app action:reload app:race` refuses while the app is busy
(`force:true` overrides) and refuses on lint errors, because **reloading a file that doesn't parse unloads the
running app** — it's gone until someone fixes and loads it. After loading it watches the log for the app's errors.

**Never use `/reload` to change an app.** Carpet hooks the `/reload` command and reloads **every** scarpet app: all
state of every game on the server is reset and each app's `__on_start` runs again. It also reloads all data packs,
resends recipes/tags/advancements to everyone and runs every `#minecraft:load` function.

## 4. Playtests — `minecraft_playtest`

One call spawns fake players (Carpet `/player`), drives them, runs code, checks results and cleans up — even when a
step fails. Use test names (`Test_A`) in a spot far from players; the tool refuses names of real players online and
refuses an app that is busy.

```json
{
  "name": "race: a finish writes a record",
  "app": "race",
  "globals": { "global_allow_fake": "true" },
  "players": [{ "name": "Test_A", "pos": [100, -60, 200], "gamemode": "adventure", "yaw": 0 }],
  "steps": [
    { "player": "Test_A", "do": "move forward", "ticks": 20, "label": "run through the start box" },
    { "wait_until": "global_run:'Test_A' != null", "timeout": 40, "label": "timer started" },
    { "tp": "Test_A", "pos": [100, -60, 260], "label": "reach the finish (a course without checkpoints)" },
    { "wait_until": "global_run:'Test_A' == null", "timeout": 40 },
    { "assert": "scarpet", "expr": "global_rec:'demo'", "contains": "Test_A", "label": "record kept in memory" },
    { "assert": "scarpet", "expr": "read_file('records', 'json'):'demo'", "contains": "Test_A", "label": "and on disk" }
  ],
  "cleanup": { "records": [{ "app": "race", "global": "global_rec", "file": "server/world/scripts/race.data/records.json" }] }
}
```

What the result looks like:

```
PASS  assertions 3/3  4.1 s
[+0.2s t+4]  ✓ spawn Test_A at 100 -60 200 (adventure)
[+1.3s t+26] ✓ run through the start box: Test_A move forward for 20 ticks, then stop
…
cleanup: killed Test_A · restored race:global_allow_fake = false · race:global_rec:demo:0 removed ·
         server/world/scripts/race.data/records.json: demo.0 removed · deleted …/players/data/<uuid>.dat …
```

Steps (one key each, all take an optional `label`):

| Step | Does |
|---|---|
| `{wait: 20}` | wait N server ticks (measured on the server, so lag doesn't break it) |
| `{wait_until: "expr", timeout: 200}` | poll a scarpet expression in `app` until truthy |
| `{player: "Test_A", do: "move forward", ticks: 20}` | a Carpet action: move / look / turn / jump / sneak / unsneak / sprint / use / attack / stop / hotbar / drop / swapHands / mount / dismount; `ticks` = do it that long, then `stop` (which also ends sneaking) |
| `{tp: "Test_A", pos: [x,y,z]}`, `{spawn: {…}}`, `{kill: "Test_A"}` | move, add or remove a fake player |
| `{command: "…", expect: "regex"}` | any command |
| `{scarpet: "expr", app, in_tick: true, save: "v", expect: {…}}` | run code; `save` it as `${v}` for later steps |
| `{set: {global_x: "expr"}}` | change a global (add `restore: true` to put it back at the end) |
| `{assert: "scarpet" \| "position" \| "gamemode" \| "tag" \| "item" \| "online" \| "log", …}` | checks; see the tool description |

`${uuid:Test_A}` is replaced by that fake player's UUID — handy for files an app keys by UUID.

**`in_tick: true`** runs the code through `schedule(0)` inside the app, i.e. in the app's own tick, the way the app's
own game logic runs. Use it when the behaviour depends on where the code runs — the classic: a player killed by the
app's `run('damage …')` inside its tick never reaches that app's `__on_player_dies`; from a command it is only deferred.
Carpet drops errors of scheduled code without a message, so a failing `in_tick` step says "the code threw inside the
tick" — run the same expression without `in_tick` to see the error.

**Fake players are not real players.** Most game apps ignore them (`p ~ 'player_type' == 'fake'`); give such apps a
`global_allow_fake` switch and set it through `globals` (restored after the test). A fake player that dies is disconnected
by Carpet right away, so an app's own `health <= 0` check right after its damage can miss it — the game must also
notice a player who is gone (`__on_player_disconnects`, or a periodic check).

**Cleanup** runs in this order: `cleanup.commands` (e.g. `script in race run stop()`), `cleanup.wait_until`, the fake
players are killed, globals restored, then `cleanup.records` — map keys named after a fake player and list entries
holding its name (`['Test_A', 1234]`, `{'name' -> 'Test_A'}`) are removed from the app's global **and** its JSON file,
and `restore: ['games']` puts counters back to their value before the test. Files in `<app>.data/` with a fake player's
name or UUID in the file name (or new files that mention them) are deleted, and so are the fake players' own world
files (player data, stats, advancements, mod data) — unless they existed before the test. Errors the apps logged
during the test make it FAIL (`fail_on_app_errors:false` to ignore).

## 5. Reading errors

`minecraft_app action:errors app:myapp` groups the app's runtime errors from `logs/latest.log` with their call stack:

```
{ "message": "0 is not a variable in myapp at line 49, pos 20", "stack": ["_land[myapp]/44:26"],
  "code": "[x, _y, z]  HERE>> = pos(p);", "count": 3, "first": "21:04:18", "last": "21:04:56" }
```

Load errors (`script load`) are not in the log — they come back in the command output, which `reload` shows.

## 6. The server resource pack — `minecraft_pack`

Vanilla sends one resource pack (`server.properties` → `resource-pack` + `resource-pack-sha1`). If several things need
pack assets (the minimap, a HUD, vehicles, a furniture mod), they must be merged into one zip.

- **build** merges the parts listed in `pinkgolem.json` → `resource_pack.parts` (default: every
  `resourcepacks/<name>/<name>.zip`). The first part wins on a clash; fonts, atlases, lang files and `sounds.json` are
  merged instead. Mark a part a mod generates (e.g. Polymer's own pack) `{"path": …, "generated": true}`: problems
  inside it are reported as warnings and don't block the build. It validates every JSON file, model parents and textures (including sprites generated by atlas
  `paletted_permutations`), item definitions, fonts and sounds, and reports clashes, size and SHA-1. The zip is
  deterministic: the same parts give the same SHA-1.
  A clash is a real problem when two packs replace the same file — e.g. two packs that both override
  `assets/minecraft/shaders/core/text.vsh` can't both work; merge the shader code by hand.
- **deploy** builds, puts the zip under a **new** URL, downloads it back to check the SHA-1, backs up
  `server.properties`, writes the new url + sha1, and pushes it live with `/packpush` when the Key Bridge mod is
  installed ([mods-src/keybridge](../../../mods-src/keybridge/README.md)); otherwise players get it after the next
  restart. `dry_run:true` shows the plan and changes nothing. Never overwrite a file at a URL players already use: a
  client that downloads while you replace it gets a broken pack, and clients cache by URL. Where the zip goes:
  - free public pack hosts, **only if the owner lists them** (opt-in, off by default):
    `"resource_pack": {"upload": {"hosts": ["mcpacks", "catbox"]}}` in `pinkgolem.json` — **mcpacks.dev**, then
    **catbox.moe**. Listing mcpacks.dev means accepting its terms (the tool ticks its consent box); ask the owner before
    adding a host for them. Each host gets **one** upload; the first copy that downloads
    with the right SHA-1 wins, and the reply names the `host` and every `hosts_tried`. A host can return a URL and
    still store a broken (even empty) file, which is why every copy is checked. Never retry uploads in a loop: free
    hosts treat that as bot spam.
  - your own uploader: `"upload": {"command": ["my-upload", "{file}"]}` (it prints the public URL; the older
    `upload_command` still works);
  - your own web server: `publish_dir` + `public_url` (a copy under a new name);
  - `url:` for a file you uploaded yourself. `"upload": {"hosts": []}` turns the public hosts off.
- **status**: what `server.properties` points at vs. what was built, parts changed since the build, the last deploy,
  whether `/packpush` exists; `check_url:true` downloads the live URL and checks its SHA-1.
