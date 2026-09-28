# Tower floors: a hotel, registration, an arcade, a club, a museum, a roof bar and build protection

Read this before building a **themed floor that people use**, not only look at: rooms that belong to one player, a
gate that decides who gets in, a game with a score, a place with music and light, a guide who explains things, or a
rule about who may change what. Seven scarpet apps in [`scarpet-apps/`](../../../scarpet-apps) do these jobs. Each
has an example data folder next to it (`<app>.data.example/`, copy it to `<app>.data/`), and all of them run with
no client mod. This page is written so a small or local model can follow it literally.

| App | What it does | Needs |
|---|---|---|
| `hotel.sc` | check-in dialog, suites that belong to one guest, iron doors that open only for their guest, plaques "free/taken", auto check-out on logout | nothing |
| `residents.sc` | registration without a password: an invisible barrier holds new players in the lobby until they register in a dialog; a role colour, a resident card, a skin studio, a fitting wall with real clothes, and a clerk who resets your look | `resourcepacks/studio` (mannequin skins), `resourcepacks/wardrobe` (clothes); SkinRestorer for players' skins (optional) |
| `arcade.sc` | 3-lane bowling with physics and real scoring, a claw machine, whack-a-mole, a dance-arrows game, tickets, a prize counter, high scores | `resourcepacks/arcade`; Key Bridge for the dance game |
| `warehouse.sc` | a techno club: a bouncer, a beat-synced music loop per player, strobes, lasers, an LED wall, LED bars, a crowd, a bar | `resourcepacks/club`, `resourcepacks/studio` |
| `protect.sc` | build protection: in a zone, only its owner (and players they trust) can break, place, pour or edit | nothing |
| `museum.sc` | a timeline of framed photos with plaques, spinning exhibits, a guide who tells each story and teleports you there | `resourcepacks/museum` (your own photos) |
| `skydeck.sc` | a roof deck: a bartender, telescopes with an 8-second locked camera view, lights that switch on at dusk, a fireworks button | nothing |

## The rules every one of these apps follows

Copy these into any new app of the same kind. Each one is a bug that happened at least once.

1. **One entity per tag, guarded.** Every entity the app owns has a unique tag (`hotel_e_npc`, `museum_e_ph_castle`).
   `_one(tag, type, pos, nbt)` returns the existing entity, removes extras, and spawns only when the chunk is loaded
   (`loaded_status(pos) >= 3`) and a 30-60 s cooldown has passed. An entity-load handler removes duplicates that
   come back from disk. Never write "summon if the selector found nothing" without the cooldown: an unloaded chunk
   finds nothing and you get a new copy every tick.
2. **Nobody is ever locked in.** A door that opens "only for the guest" must also open for anyone already inside.
   A gate that opens "only if the bouncer said yes" must always open from the inside.
3. **Doors: set both halves with `setblock` and the full state.** Toggling each half with scarpet `set()` let the
   game "fix" the door by moving it to another block. Keep each door's `facing` and `hinge` in the data file and
   write `setblock x y z iron_door[half=lower,facing=south,hinge=left,open=true]` for the lower half, then the same
   for the upper half.
4. **Excluded areas are part of every rule.** A barrier, a guard or a zone message must skip the lift shaft and any
   player who is riding something (`query(p, 'mount')`). Otherwise the rule fires on a player passing through in the lift.
5. **Mannequins as NPCs:** `immovable:1b, hide_description:1b, Invulnerable:1b, CustomNameVisible:0b`. Show the name with
   a small `text_display` instead: `view_range:0.2f` for a name read up close, about `0.7f` (≈ 45 blocks) for a plaque
   read across a room. A text display is hidden behind blocks; a floating nametag shows through walls. `Invulnerable` does not stop a creative-mode player: cancel the hit in `__on_player_attacks_entity`.
6. **Dialogs:** `type: minecraft:multi_action`, `after_action: 'none'`, `pause: false`, and an `exit_action` that runs
   the app's own `close` command, which runs `dialog clear <name>`. Each button runs a slash command of the app.
   Inputs (`minecraft:text`, `minecraft:boolean`) reach the command through a `dynamic/run_command` template.
7. **Buttons:** a plain vanilla button, polled every 2 ticks for the rising edge of its `powered` state. Hand the
   result to the nearest real player within 6 blocks, with a 3 s cooldown per player.
8. **Reloads reset state.** Before `/script load <app>` check `status()` (every app has one; `busy: true` means a
   game or a camera view is running). Stop any looping sound (`stopsound <player> record <event>`) first.

## hotel.sc: rooms that belong to someone

Data: `hotel.data/hotel.json`, from `hotel.data.example/`:
```json
{"name": "The Hideaway", "color": "#E8A33D",
 "reception": {"npc": {"pos": [-55.5, -15, -98.65], "yaw": 0, "name": "Reception", "skin": "studio:entity/skin/soft_boy"}},
 "rooms": [{"id": 1, "name": "Rose Suite", "door": [-68, -9, -111], "facing": "south",
            "box": {"min": [-70, -9, -119], "max": [-65, -7, -112]}, "spawn": [-67.5, -9, -115.5],
            "plaque": {"pos": [-66.5, -7.5, -109.97], "yaw": 0}}],
 "checkout_days": 7, "lobby_spawn": [-64, -15, -101]}
```
- `door` = the lower half of an iron door (no handle, so only the app opens it). `box` = the room's inside, inclusive.
- A door opens when its guest is within 2.5 blocks of it, or when **anyone inside the box** is within 2.5 blocks of it.
  It shuts when nobody is near.
- Leaving the server checks the guest out (`__on_player_disconnects`). When the app starts it checks out anyone who
  is offline.
- A respawn point inside a suite that is no longer yours moves to `lobby_spawn`. Otherwise the next guest finds a
  stranger respawning in their bed.

## residents.sc: registration without a password

Data: `residents.data/config.json` (`lobby` box, `return` point, `role`, `exempt_names`, `exempt_patterns`,
`rules`, `seed`), `studio.json` (skins, wardrobe outfits, the card clerk, the fitting wall) and `wardrobe.json` (the
clothes catalogue, written by `resourcepacks/wardrobe/gen_wardrobe_pack.py`).
1. **The barrier is a position check, not blocks.** Once a tick, any unregistered player outside the `lobby` box is
   put back inside, clamped to the nearest point. If they are at the wrong height, they go to `return`. This works
   however they got out: walking, a lift, an ender pearl or `/tp`.
2. **Registration is a dialog** with a nickname box and an "I agree to the rules" checkbox. It opens by itself when
   the barrier holds someone, and on `/residents menu`. Registering adds the scoreboard tag `resident`, so any other
   app can check `query(p, 'has_tag', 'resident')`.
3. **Registered players get one fixed look:** a team colour and adventure mode. Ops, Carpet fake players and names in
   `exempt_names` / `exempt_patterns` are never held.
4. **`seed`** registers existing players once, the first time the app starts, so your regulars are not held in the lobby.
5. **Skins:** mannequins wear `studio:entity/skin/<id>` from `resourcepacks/studio`. To put a skin on a *player*, give
   SkinRestorer a `textures.minecraft.net` address (`skin set web classic <url> <player>`). Two traps:
   - In `skin set`, the variant (`classic`) comes before the URL.
   - MineSkin cannot fetch some file hosts. Upload the PNG to MineSkin once and keep the address it returns.
6. **The fitting wall: real clothes, no client mod.** A mannequin wears the current pick; each clothes row (hats and
   wigs, wings, tops, trousers and skirts, shoes) has a ◀ and a ▶ vanilla button, and three more buttons wear the
   look, pick a random one, or take it off. Right-clicking the dummy also offers to wear the look.
   - `equippable={slot:"chest",asset_id:"ns:x"}` draws `assets/ns/equipment/x.json`, whose layers are `humanoid`
     (a 64x32 texture in the old armour layout: head, chest, feet), `humanoid_leggings` (legs) and `wings` (the elytra
     model). Transparent pixels are not drawn.
   - One chest asset can hold `humanoid` AND `wings` layers, so a top and wings share the chest slot. Without a
     `glider` component nobody glides.
   - A head item with `equippable` but no `asset_id` is drawn as its item model on the head: a 3D hat. The head spans
     model units 1.6 to 14.4 on every axis (1 head pixel = 1.6), the model's north is the face, and x is mirrored.
   - Mannequins render like players, so a mannequin previews everything. `item replace entity <uuid> armor.<slot>`
     dresses it, but `query(e, 'holds', slot)` is null on a mannequin: re-dress it in full every time.
   - Every piece carries `custom_data={studio_outfit:1b}`. The app only replaces or removes pieces with that tag, so
     a player's real armour stays on.
   - Text components in a list inherit the first element's style. Start a coloured list with `''`.
7. **The clerk resets a look:** studio pieces off and `skin reset <player>` (SkinRestorer), behind a confirm dialog
   and a 10 s cooldown.

## runway.sc: a fashion show on the studio floor

`scarpet-apps/runway.sc` + `runway.data.example/` + the music in `resourcepacks/studio_music` (`lounge:runway.show`,
`lounge:runway.pose`). A host podium with two vanilla buttons: **sign up** and **start**.

1. **Sign up = a snapshot of the look you wear now:** the four armour slots (`inventory_get(p, 36..39)`, stored as NBT
   strings) and the skin you wear now, read from the shared file `skins_now` (`read_file('skins_now', 'shared_json')`;
   residents.sc and skinpaint.sc write it whenever they put a skin on someone: a signed MineSkin texture or a pack
   texture). Apps can't read each other's data folders; `shared_json` is the way to share.
2. **The show:** each look walks the runway on a model mannequin (`data modify entity <uuid> profile set value …`,
   `data modify entity <uuid> equipment.<slot> set value <nbt>`), moved with `modify(e, 'pos', …)` every tick from
   backstage to the audience, then a pose (a spin, a crouch, flashes, the cheer sound), then back. A finale lines up to
   five of them. Titles and music go only to real players inside the studio floor box; the line-up clears afterwards.
3. **Nobody signed up = a house show:** three random looks from the wardrobe catalogue on the studio skins, so the
   button always does something.
4. **An unrecorded skin:** a mannequin profile `{name:"<player>"}` is not resolved by an offline-mode server; the
   sign-up dialog tells players to put their skin on again (so it is recorded) before signing up.

## arcade.sc: games with physics and a score

Data: `arcade.data/layout.json`, which holds lanes (`x1`, `x2`, `center`, `foul_z`, pin rows, `approach`, `screen`,
`join`, `start`), `claw`, `whack`, `rhythm`, `counter` and `scoreboard`. The app writes `tickets.json` and
`scores.json` itself.
- **Hold to charge, release to throw.** The ball is an item with a `consumable` component
  (`consume_seconds:100000, animation:"bow"`). `__on_player_uses_item` marks when the charge starts and
  `__on_player_releases_item` throws. Holding right-click on a plain item repeats the use event every few ticks, and
  that threw the ball with no power chosen.
- **Lock a lane while pins reset** (`phase 'wait'`). Clamp scores with `max(0, ...)`. A throw during the reset once
  scored a negative roll.
- **The approach zone includes the foul line.** "Stand before the red line" must accept a player standing on it.
- **An idle game ends after a minute without a throw**, and a lane whose players all left is freed.
- **High scores keep each player's best per game**, not every game played.
- **Dance arrows:** glazed terracotta's printed arrow points *opposite* its `facing`. Build one test tile and look
  at it before building 30. The player sits on an invisible marker armor stand. Key Bridge's `keys` scoreboard gives
  W/A/S/D, and each key snaps the seat to a tile and back.

## warehouse.sc: music and light on one beat grid

- **Pick the tempo so a beat is a whole number of ticks.** At 150 BPM a beat is exactly 8 ticks, and a 32-bar loop
  is 51.2 s = 1024 ticks. `resourcepacks/club/gen_club_pack.py` synthesises such a loop with numpy: a mono Ogg, with
  `stream: true` and category `record`.
- **Play it per player:** `execute as <p> at @s run playsound club:techno_loop record @s ~ ~ ~ 3 1`. Start it on a
  beat (`tick % 8 == 0`), re-trigger it every 1024 ticks, and `stopsound` when the player leaves the club. Every
  light effect runs on the same `tick % 8` grid, so the kick and the strobes land together.
- **Strobes** are `light` blocks set to level 15 on a kick and back to 0. **Lasers** are thin `block_display` beams
  turned with an interpolated quaternion (`_aim(dx,dy,dz)` rotates +z onto a direction). **An LED wall** is one
  `text_display` whose text is rows of coloured `█`. **LED bars** are `text_display`s with `billboard:"vertical"` and a
  tall non-uniform scale.
- **The bouncer** lets in admins and anyone in black clothing. Anyone else gets in with a set chance. A refusal means
  a 60 s wait. The gate always opens from the inside.

## protect.sc: only the owner builds here

Data: `protect.data/zones.json` = `{"zones": [{name, owner, label, msg, trusted: [], min, max}]}`. Use the whole
height (`y -64..320`) and leave room around the build so the owner can grow it.
Carpet lets a handler cancel the action by returning `'cancel'` for these events:
`player_breaks_block`, `player_placing_block` (fired *before* the block goes in; `player_places_block` fires after
and cannot cancel), `player_right_clicks_block`, `player_uses_item` (buckets aim by raycast, not at a block),
`player_interacts_with_entity`, `player_attacks_entity`.
Visitors may still use doors, gates, trapdoors, buttons and levers. Commands: `/protect`, `/protect list`,
`/protect trust <player>` and `untrust` (owner), `/protect show`, `/protect bypass` and `reload` (ops).
**Not covered:** WorldEdit, Axiom, `/fill`, TNT, fire and pistons. Keep a block logger (Ledger) to roll those back.
To find who built something, query the logger's database. Copy it first, because the live file is locked.

## museum.sc: a history told by photos

1. Photograph each landmark with `minecraft_screenshot` (an iso render), named `mus_<id>`. Centre it on the build's
   real footprint, from your world index `lo`/`hi`. A ride made of display entities (a coaster track) does not show up
   in a block render: photograph its station building instead.
2. `python3 resourcepacks/museum/gen_museum_pack.py <id> <id> ...` crops each render to its content, sets it in a mat
   with a frame, and packs `museum:<id>` quads.
3. List the stations in `museum.data/museum.json` in build order: photo centre 0.05 in front of the wall, `face`, a
   date, a title, one line of text, and `tp` (the entrance). Hang them clockwise from the lift door.
4. The guide mannequin opens a dialog with one button per station. Each station has its story and a **Take me
   there** button. The teleport searches upward from `tp` for a solid floor with two free blocks, so it never lands
   inside a wall.

## skydeck.sc: telescopes, bar, lights, fireworks

- **A locked camera view without a client mod:** save the player's game mode, set spectator, `tp` to the camera
  point, spawn an invisible marker armor stand there facing the target, then `spectate <marker> <player>`. After 8 s
  run `execute as <player> run spectate`, tp back and restore the game mode. Write the saved state to a file, and
  restore it in `__on_player_connects` for someone who logged out mid-view. Retry the marker spawn until the camera
  chunk is loaded.
- **Lights at dusk:** `waxed_copper_bulb[lit=true]` stays lit with no redstone, and `lit=false` stays dark. Check
  `day_time() % 24000` every 5 s and fix any bulb that is wrong. A redstone lamp set to lit with `setblock` turns
  itself off.
- **Fireworks only on a button**, with a 60 s cooldown. Summon `firework_rocket` with a `LifeTime` and explosions in
  its `FireworksItem`. Never set off fireworks automatically: players find surprise shows annoying.

## Build order for a new floor (any of the above)

1. **Write the contract first:** a short SPEC with the box, the fixed things (lift shaft, door, stairs), and a table of
   coordinates.
2. **Write a generator** that uses `put`/`pbox` helpers with guards: never touch the shaft, the door apron or the
   corner pillars. Assert those guards over every voxel before saving. The generator also writes the app's data
   file, so the coordinates live in one place.
3. `minecraft_run_command dry_run:true`: read the overwrites, and protect players' builds with `fill ... replace <block>`.
4. Build, verify (0 mismatches), take a cutaway screenshot (`cut_y`).
5. Lint the app, load it, call `status()`, and look at it live. A block render does not show display entities.
6. Deploy the resource pack only after looking at a preview sheet of every new texture.

## Common mistakes

| Mistake | Fix |
|---|---|
| A door vanished or doubled after a few toggles | both halves with `setblock` and the full state (rule 3) |
| A bowling throw fired before choosing power | hold-to-charge with a `consumable` item and the release event |
| A nametag seen through three floors | `CustomNameVisible:0b` + a close-range `text_display` label |
| A zone message fired inside the passing lift | exclude the shaft column and mounted players |
| An "invulnerable" NPC killed by a creative player | cancel in `__on_player_attacks_entity` |
| The music drifted off the light show | a whole number of ticks per beat; start sound and lights on the same tick grid |
| A flag or display at the wall block's coordinate is invisible | put it on the face, 0.05 into the room |
| The museum photo of a coaster is an empty field | display-entity rides don't render in block renders: photograph the station |
| A lit redstone lamp went dark | use `waxed_copper_bulb[lit=true]` |

See also: `cinema-and-gallery.md` (quads, the yaw convention), `displays.md`, `game-logic.md`, `lessons.md`,
the case study [`docs/case-study-tower.md`](../../../docs/case-study-tower.md).
