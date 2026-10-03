# Changelog

## 2026-10-03: Pink Golem Bench, Ollama, and a stack a small model can drive (1.2.0)

Measured, not guessed: **[Pink Golem Bench](bench/README.md)** runs six building tasks on a model and scores what was
really built by scanning the world afterwards. On Gemma 4 E4B (8B, 4-bit, through Ollama) the published 1.1.2 scored
**22/100**; this release scores **84/100** with the same model. Claude Opus 5.5 scored 100 on 1.1.2.
Charts and every change's effect: [bench/results.md](bench/results.md).

- **Ollama support:** `bench/agent.py` is an MCP client and agent loop for any Ollama model with tool calling
  (32k context by default, warns before Ollama silently drops the start of a conversation; nudges a model that
  stops early or repeats a failing call). See [local models](docs/clients/local-models.md).
- **`minecraft_blueprint`** (tool 39): a whole blueprint in one call. It finds free ground next to a player or a
  build on the map, turns the door toward the player, builds with the crew, waits, checks and adds it to the map.
- **`PINKGOLEM_TOOLS=core`**: offer only the 17 tools a build needs (~5k tokens of descriptions instead of ~12.5k).
- **Tools forgive small-model mistakes:** generator arguments written as one string (`"--at 1,2,3"`, `--at=…`,
  decimals, a lone `x,y,z` or direction), `relative_to_player` filled with junk or with a name next to world
  coordinates, `spawn` next to yourself, `find_space` near a player or a position, `minecraft_vision` with a box
  and no mode, `map add` without a name, vanilla commands sent to WorldEdit.
- **Failures say so on the first line:** a failed generator, a refused phase, a fill that didn't place and an empty
  job list now come back as errors ("FAILED — NOTHING was built", "PARTLY BUILT", "NOT BUILT") instead of a
  success-shaped reply with `"ok": false` inside. A repeated failing call is pointed out.
- **Safety:** builds refuse to put blocks where a player stands (no override) and say where "in front of them" is;
  a coordinate list that isn't exactly three numbers is refused; `minecraft_build` refuses a box too big to check
  for existing builds instead of skipping the check.
- **Helpers for geometry:** `minecraft_get_players` gives `facing.step_xz` and `facing.ground_3_ahead`;
  `fill` takes `size:[w,h,d]` instead of a far corner; `minecraft_build` replies with what it built
  ("stone: 5×1×5 = 25 blocks").
- `SYSTEM_PROMPT.md` rewritten from the failures the bench recorded; `SKILL.md` knows `minecraft_blueprint`;
  ten new lessons (66-75) in `reference/lessons.md`.

## 2026-10-03: Script and sound checks (1.1.2)

- **`scripts/sc_check.py`** checks scarpet apps before `script load` (a failed load unloads the running app): bracket
  depth per function, `list + list` (adds element-wise) and `l:N || default` (list indexes wrap around).
- **`scripts/siren_check.py`** flags siren-like sounds before they ship: pitch glides of 2+ semitones over 0.3 s (up
  or down) and long pure tones, in files, folders or a pack zip. For some players a wail is a trauma trigger.
- Three lessons from horror games (jump scares that made no sound, siren-like sounds, a monster stuck at the exit) and
  two new scarpet traps in `reference/scarpet.md`.

## 2026-10-02: Pack hosts are opt-in (1.1.1)

- `minecraft_pack deploy` no longer uploads to a public pack host unless you list it:
  `"resource_pack": {"upload": {"hosts": ["mcpacks", "catbox"]}}` in `pinkgolem.json`. 1.1.0 used mcpacks.dev and
  catbox.moe by default and ticked mcpacks.dev's consent box for you; a third-party upload is now your choice (listing
  mcpacks means you accept its terms). With nothing configured, deploy asks for a host, your own uploader,
  `publish_dir` + `public_url`, or `url:`. [PRIVACY.md](PRIVACY.md) is updated.

## 2026-10-02: Checked pack uploads, an entity census, display entities in screenshots (1.1.0)

- **`minecraft_pack deploy` can upload to free pack hosts**, opt-in: list them in `resource_pack.upload.hosts` in
  `pinkgolem.json`, e.g. `["mcpacks", "catbox"]` ([mcpacks.dev](https://mcpacks.dev), then [catbox.moe](https://catbox.moe)).
  Nothing goes to a third party unless you list a host (listing mcpacks.dev means accepting its terms).
  - Each host gets **one** upload. The first copy that downloads back with the right SHA-1 goes into
    `server.properties`, and the reply names the `host` and every `hosts_tried`.
  - Why the check: a host started storing empty files while still returning a URL. Why one try each: retry loops look
    like bot spam to a free host.
  - Your own `upload.command` (the older `upload_command` still works), `publish_dir` + `public_url` and `url:` work
    as before. [PRIVACY.md](PRIVACY.md) lists both hosts.
- **New tool `minecraft_entities`** (38 tools now): a census of the loaded display, interaction, armor-stand,
  mannequin and marker entities by app, with their x/z span.
  - **Duplicates**: piles of identical copies on one spot (same type, tags, position and what they show). `fix:true`
    keeps one of each.
  - **Ghosts**: one object carrying two incarnation tags (`<app>_i<n>`), or one app with two generations alive
    (`<app>_g<n>`, `_gen<n>`, `_run<n>`): an old copy left behind after a chunk unload.
  - **Remove** by tags or uuids, a dry run unless `confirm:true`.
  - The `cu` app has the scan (`census()`, `census_rm()`): update it with `python3 pinkgolem.py apps add cu`.
  - [`entities.md`](skill/pinkgolem/reference/entities.md) explains the tagging convention it relies on.
- **Screenshots draw display entities the way players see them**, in iso, top, fpv and pov ([`display.js`](mcp-server/display.js)):
  - item displays with their models from the server pack, block displays with real block models, text displays with
    their text, including right-to-left scripts and billboards, depth-tested against the blocks;
  - vanilla items, blocks and the font come from the client jar of a local Minecraft launcher when there is one
    (`client_jar` in `pinkgolem.json`: a path, or `false`; `MC_CLIENT_JAR=off`); without it, everything still works
    with flat colours and markers;
  - markers and interaction boxes are no longer drawn: players never see them.
- **Key Bridge 1.4** ([`mods-src/keybridge`](mods-src/keybridge/README.md)):
  - works with Polymer's AutoHost: `/packpush` reuses Polymer's pack id, so it replaces the pack Polymer sent at login
    instead of stacking a second one; logins are left to Polymer;
  - an entity tagged `kbhide_<player name>` is not drawn for that one player (a rider's own body double).
- Lessons 57-62: integer x/z in `summon`/`tp` are centred (write `-72.0`), entities that vanish from `entity_id()` when
  a chunk drops below full loading, boards that grew one copy per restart, virtual model mobs, AutoHost behind a
  "Minecraft Java" tunnel, checking every uploaded pack.

## 2026-09-30: Rides that move smoothly

- **Fix: riders jumped on moving seats.** Carpet's `modify(e, 'pos'|'location', …)` sends its own position packet, but the
  vanilla tracker still sends a delta from the spot it last sent (every 3 ticks for an armor stand, 2 for a mannequin),
  and the client adds that delta on top. So anything moved every tick that was not a display ran ahead and snapped back.
  - The seats in `cars.sc`, the Ferris wheel cabins (`ferris.sc`) and the arcade dance pad are now invisible
    `item_display`s, which sync every tick and interpolate like the body they sit in. Seat heights are unchanged; the
    Ferris wheel seat moved up 1.975 because a full-size armor stand carried its passengers that much higher.
  - Walking runway models and one-off moves use vanilla `tp` instead: pins, moles, prizes, the dance seat and the
    skin-easel markers. A one-off `modify` left the entity drawn one move too far until a full resync, 20-60 s later.
- The scarpet reference lists both traps with the fix ([`skill/pinkgolem/reference/scarpet.md`](skill/pinkgolem/reference/scarpet.md)).

## 2026-09-30: The skin easel's cursor

- **Fix:** `scarpet-apps/skinpaint.sc` set the cursor's `text_opacity` to `150b`, which is not a valid NBT byte (a byte
  ends at 127), so creating the cursor failed with "Incorrect NBT tag" whenever it had to be made again (after a
  restart or a cleanup). It is now `-106b`, the same 150 as an unsigned byte.

## 2026-09-29: An automatic check on GitHub, a privacy page, a town GIF

- **GitHub checks every push and pull request** ([`.github/workflows/check.yml`](.github/workflows/check.yml)), with no
  Minecraft server: the tool layer loads, the trust rules hold, all Python compiles on 3.9, every blueprint generates,
  and the Claude Code plugin manifest is valid. A badge at the top of the README shows the result.
- `npm run check` now also fails when a doc or the plugin manifest gives the wrong number of **reference pages** (it
  already checked the tool count), and it reads the README's badge too.
- **[PRIVACY.md](PRIVACY.md)**: every network connection Pink Golem makes, what it stores and where, and what your AI
  provider sees. No telemetry, no accounts, no servers of its own.
- The contributing guide lists all the tool groups, the real tool-list cost (~12,000 tokens), the automatic checks and
  the release steps; a pull request template.
- A second demo GIF: five blueprints build one town, then a slice down through it shows every interior.

## 2026-09-28: Install as a Claude Code plugin, a demo GIF, a clearer README

- Pink Golem is now a **Claude Code plugin and marketplace**: `/plugin marketplace add sagistiki/pink-golem`, then
  `/plugin install pink-golem@pink-golem`. The plugin carries the skill and starts the MCP server from your Pink Golem
  folder, which it asks for once (`.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`).
- A demo GIF at the top of the README (the cottage blueprint, phase by phase, from Pink Golem's own renderer) and a
  "What makes it different" section.
- `glama.json` names the maintainer for MCP directories; issue templates for bugs and ideas.

## 2026-09-28: A character studio: real clothes, a fitting wall, and an in-game skin easel

- **Clothes from the pack, not dyed leather.** [`resourcepacks/wardrobe`](resourcepacks/wardrobe) draws 15 tops, 11
  bottoms, 8 shoes, 4 wigs, 15 3D hats and 5 wings in code as 26.x equipment assets (a top and wings share one chest
  item) and head item models.
- **Fitting wall** in `residents.sc`: a turning mannequin, a row of vanilla ◀ ▶ buttons per slot, and wear /
  surprise / take off buttons. The clerk can also reset your look.
- **Skin easel**, a new app [`scarpet-apps/skinpaint.sc`](scarpet-apps/skinpaint.sc) with
  [`resourcepacks/skinpaint`](resourcepacks/skinpaint):
  - you paint a real 64x64 skin (5 views, 2 layers) on a wall of `text_display` pixels;
  - the tools are on the wall: a colour strip, a paint toolbar, a stage at eye height;
  - saving gives you the skin for everyone;
  - a gallery shows saved skins, with creators' hide / show / delete.
- **Key Bridge 1.3**: `/skinbake` makes the PNG, uploads it to MineSkin off the server thread, and answers the app.
- **Easel precision**: an automatic layer (paint what you see), a cursor on the aimed pixel, a 3x magnifier.
- **Fashion show** [`scarpet-apps/runway.sc`](scarpet-apps/runway.sc): sign up with your look and skin, models walk the
  runway, a finale, a house show when nobody signed up.
- **Original music** [`resourcepacks/studio_music`](resourcepacks/studio_music): a lofi for lifts (segments +
  `minVolume`) and a runway track.
- New case study: [`docs/case-study-character-studio.md`](docs/case-study-character-studio.md). Lessons 49-56.

## 2026-09-28: A tower of floors: hotel, registration, arcade, club, museum, roof bar, build protection

Seven new scarpet apps, each with an example data folder (`scarpet-apps/<app>.data.example/`) and no client mod:

- `hotel.sc`: a check-in dialog, suites that belong to one guest, iron doors that open only for their guest (and
  always for anyone inside), "free/taken" plaques, check-out on logout, respawn points that follow the booking.
- `residents.sc`: registration without a password. An invisible barrier (a position check) holds new players in
  the lobby until they register in a dialog. Also a role colour, a resident card, a skin studio and a wardrobe.
- `arcade.sc`: 3-lane bowling with physics and real scoring, hold-to-charge throwing, a claw machine,
  whack-a-mole, a dance-arrows game, tickets, a prize counter, per-player high scores.
- `warehouse.sc`: a techno club with a bouncer, a per-player music loop on an 8-tick beat grid, strobes,
  quaternion lasers, an LED wall and LED bars made of `text_display`s, a posed crowd, a bar.
- `protect.sc`: build protection. In a zone only the owner and trusted players can break, place, pour or edit,
  using Carpet's cancellable events.
- `museum.sc`: a timeline of framed photos, spinning exhibits, and a guide who tells each story and teleports you there.
- `skydeck.sc`: a roof bar, telescopes with an 8-second locked camera view, copper-bulb lights at dusk, a fireworks button.

New resource-pack generators: [`resourcepacks/studio`](resourcepacks/studio) (7 original skins + a resident card),
[`resourcepacks/arcade`](resourcepacks/arcade) (pins, ball, moles, claw, plushies),
[`resourcepacks/club`](resourcepacks/club) (an original 150 BPM hard-techno loop, synthesised with numpy),
[`resourcepacks/museum`](resourcepacks/museum) (frames your own landmark renders).

- New reference page: [`skill/pinkgolem/reference/tower-floors.md`](skill/pinkgolem/reference/tower-floors.md).
- New case study: [`docs/case-study-tower.md`](docs/case-study-tower.md).
- Nine new lessons in `lessons.md` (#40-48).

## 2026-09-28: A cinema and an art gallery, with no client mods

New scarpet apps `cinema.sc` and `gallery.sc`: a screening room (seats, a vanilla button, a subtitle strip, house
lights that dim) and a picture gallery (paintings, a spinning exhibit, sculptures, quiet zones), both drawn with
`item_display` quads swapped between pre-rendered item models — no client mod, no map art, no shaders. Ships with a
working example: a complete 14 s demo film ("The Lighthouse") and four demo paintings, both fully generated by the
Python toolkits in [`resourcepacks/cinema/`](resourcepacks/cinema) and [`resourcepacks/gallery/`](resourcepacks/gallery).

- New reference page: [`skill/pinkgolem/reference/cinema-and-gallery.md`](skill/pinkgolem/reference/cinema-and-gallery.md)
  — a step-by-step guide (exact file names, copy-pasteable JSON, the frame-swap snippet, a comparison of screen
  techniques with real numbers, a checklist and a common-mistakes table) plus the design lessons: wall-clock frame
  scheduling, mono positional sound, RTL-safe intertitle text, the shared yaw convention, seat/stair offsets, and
  when a plain vanilla button beats a custom model.
- New case study: [`docs/case-study-cinema.md`](docs/case-study-cinema.md).
- Four new lessons in `lessons.md` (#36-39): stair-backrest `facing`, a display positioned inside its wall block
  instead of on its face, shipping a resource-pack part nobody previewed, and reusing one custom button model for
  everything.
- `resourcepacks/cinema/cinemalib.py`'s RTL text helper (`visual()`) now detects whether a line actually contains
  an RTL character and passes a pure-LTR line through unchanged — reversing an all-English intertitle used to
  scramble its clause order.

## 2026-09-27: ClawdBlock is now Pink Golem

The project was renamed to keep its name clearly apart from Anthropic's trademarks. The code, the tools and your world
are the same.

### Upgrading from ClawdBlock

1. Clone the new repository (`git clone https://github.com/sagistiki/pink-golem.git`), or point your existing clone
   at it: `git remote set-url origin https://github.com/sagistiki/pink-golem.git && git pull`.
2. Run `python3 pinkgolem.py connect <your client>` again. It registers the MCP server as `pinkgolem`, links the
   skill as `pinkgolem`, and removes the old `clawdblock` skill link.
3. That's it:
   - `clawdblock.json` is renamed to `pinkgolem.json` automatically.
   - Generators that read `CLAWDBLOCK_ROOT` / `CLAWDBLOCK_JOBS` / `CLAWDBLOCK_CU_DATA` keep working (both names are
     set).
   - `clawdblock.py` is now `pinkgolem.py`, and the skill folder is `skill/pinkgolem/`.

### Security (see [SECURITY.md](SECURITY.md))

- **Owners and guests:** `security.owners` in `pinkgolem.json`, asked for during setup. Chat lines reach the AI tagged
  `[owner]` or `[guest]`.
- **Guest lock, enforced in code:** after a guest talks to the AI, generators, admin commands (`op`, `whitelist`,
  `ban`, …), app patches and pack deploys are refused for 10 minutes, unless an owner types `!approve` (one action).
- `stop` is always refused. `minecraft_generate`'s `code` parameter is **off by default** (`security.allow_code`).
- `doctor` warns about missing owners, `allow_code` and `online-mode=false`.

**Existing installs:** add your Minecraft name to `pinkgolem.json`:

```json
"security": { "owners": ["YourMinecraftName"] }
```

Without it, every player counts as a guest and nobody can approve.

### Also new

- The default body is **Pink Golem**: the player `Golem` with the team prefix `Pink `, pink leather armor with a
  gold trim, and a pink block in hand, so players can tell it from a person. `bot_name`, `bot_prefix` and
  `bot_outfit: "none"` change it. A `bot_name` from an older config is kept.
- `npm run check` also fails when a doc gives a different tool count than the server really has (37).
- New banner.
