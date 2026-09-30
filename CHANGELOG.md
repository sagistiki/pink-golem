# Changelog

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
