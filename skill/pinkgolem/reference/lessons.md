# Lessons learned the hard way

Each lesson here cost a real mistake in a real server. They are the reason behind many rules in the other pages.
Read this once; come back when something feels familiar. New lessons you learn go into `minecraft_notes`
(`section:lesson`); the ones that matter to everyone can be proposed for this page.

## Building

1. **A path laid one block high became a step in front of a villa's door.** Paths, patios and sidewalks replace
   the ground block. The access check now flags "full-block step at a door".
2. **A new street ran straight through an old lamp post.** Before laying a path or road, list the non-air blocks
   one to five blocks above its whole footprint and clear or route around them.
3. **A furniture fill along the wall line replaced a door.** Interior = footprint minus the wall ring. Write the
   interior range down; after furnishing, inspect the door cells.
4. **Round towers at the back corners of a big hall sat on the top landing of both main staircases.** The stairs ended
   in a wall. When towers or walls overlap rooms, carve the room out of the tower, and walk up every staircase
   (`minecraft_reach` from the entrance to the upper floor, or a real bot walk) before saying done.
5. **A decorative base course ran over a tower's door and erased its lower half.** The access check found a door
   floating one block up and 0 rooms reachable. Decoration passes must skip door cells.
6. **A regenerated generator silently undid a separate "fix" job.** Put fixes inside the generator, never in a
   separate patch file, and re-run the access check after every regeneration.
7. **Recolouring a bed half by half popped it.** Placing the new head updated the old foot, which broke, which broke
   the new head. Clear both halves, then place foot and head.
8. **Flowers on quartz and planks popped off as items.** Plants need soil — pots indoors, a moss planter, or grass
   under a flower bed (`parts.flower_bed` lays it for you).
9. **A banner could not make a clean six-stripe flag** (banner patterns are fixed, uneven bands). Six thin
   `block_display` slivers can (`parts.stripe_display`). Same trick for any striped sign.
10. **Twelve thousand fill commands for one tall tower** — because a colour spiral changes every layer. The spiral
    repeats every 24 blocks, so one period built by fills + `clone … masked` copies up the tower took 2000 commands
    and 3 seconds. Scan the master period first: masked clone copies EVERY non-air block, including an entrance
    frame you didn't mean to repeat.
11. **Glass looked dark at night.** Emissive blocks (sea lantern, froglights, glowstone, shroomlight) right behind
    tinted-glass windows render full-bright through the glass: random "office floors" of lamps make a tower glow
    without changing its facade.

## Working safely

12. **An app reload deleted a player's race boat mid-race and dropped them on the track.** `script load <app>` re-runs
    its start-up. Check the app's state (who is racing, who is in the zone) before reloading; make start-up clean up
    politely (dismount riders and send them somewhere safe).
13. **A player stayed stuck in adventure mode after a reload** — the app kept "who did I switch" only in memory.
    Keep such state in a player tag or a file, never only in an app global.
14. **Two pets suffocated right after being summoned** — into a furniture block that turned out to be solid. The
    entity list right after the summon still showed them; five seconds later it didn't. Summon on top (y+1), make
    pets invulnerable, and re-check after a few seconds.
15. **A tamed pet froze in place whenever its owner was offline.** Vanilla pets sit when their owner is missing.
    To let pets wander a building, make an invisible marker `armor_stand` their owner while the real owner is away.
16. **Summons silently did nothing far from players.** Entities can only be summoned in loaded chunks — teleport
    your bot there first.
17. **Holding boats at a starting line by teleporting them every tick felt like crashing** ("moved wrongly"). Use
    barrier gates. And a boat is 1.375 wide: a blocking block must start more than 0.69 from its centre, or the boat
    already overlaps it and passes straight through.

## Tools and scripting

18. **Builders never actually animated** — Carpet's `/player X attack` does nothing in adventure mode when aimed at a
    block. `helpers.sc` swings every fake player tagged `building` with `modify(p,'swing')`.
19. **`data merge entity` and `rotate` accept one entity.** Use `execute as @e[…] run data merge entity @s {…}`.
20. **`block()` read in the same scarpet call right after `run('setblock …')` still returned the old block** (same for
    `weather()`). Verify in a separate call.
21. **`read_file` returned nothing in plain `script run`** — it only works inside an app (`script in cu run …`).
22. **The access check once called an open doorway a "closed room".** Confirm surprising results with a real bot
    walk before rebuilding anything.
23. **A button left `powered=true` by a test re-fired after every app reload.** When testing buttons with
    `setblock … powered=true`, set `powered=false` in the very next call.
24. **Python's `urllib` failed SSL on some machines** (a certificate chain problem). The installer falls back to
    `curl` / PowerShell; do the same in your own scripts.
25. **A crew member's name matched a real Minecraft account**, so Carpet gave it that account's skin and exact
    lowercase spelling — and a case-sensitive name check lost it. Compare player names case-insensitively.
26. **A two-block-deep pool stopped a 187-block free fall** with no damage. Levitation amplifier 29 lifts a player
    about 1.5 blocks per tick — a fun elevator.

## Working with people

27. **The best-received format for "upgrade X":** a survey with numbers (what's there, what's empty), then ~10
    numbered options with where and size, a recommendation, the player picks several — then plan properly and
    build without more questions.
28. **Players test builds live, often before you say done.** Treat every step as if someone is already inside.
29. **Players love the helper builders and the site outline before building.** They make a command-line build feel
    like watching a crew at work.

## From running a busy server

30. **A "keep one cart on the track" app piled up 190 minecarts.** It summoned a new cart whenever `entity_selector`
    found none — but carts in unloaded chunks are invisible to it. The pile lagged everyone near it. Never respawn
    without a loaded/near check and a dedupe (`rails.md`).
31. **An interactive build was announced after testing only the code path, not a real click — and players said it
    didn't work.** Test with a real player before announcing (`minecraft_wait reply_from:<player> ask:"…"`), and prefer
    games that join by STANDING somewhere: a fake player can then test the whole round end to end (`minigames.md`).
32. **A generator's files were built alphabetically** (interior before the site — the site then paved over the
    floors). `minecraft_generate` now builds in the order the script prints its files: print them in build order.
33. **Let the server check your commands.** `execute if block <unloaded> run <cmd>` parses `<cmd>` completely and never
    runs it; `dry_run:true` does that for every distinct command in a job and catches bad block states, missing
    effect amplifiers (`effect give @a glowing 30 true` → the amplifier is required before hideParticles) and
    pre-1.20.5 item NBT (`sword{Damage:3}` → components `sword[damage=3]`) before anything is placed.
34. **A fake player with a never-seen name froze the server ~5 s** when it joined (a Mojang profile lookup on the main
    thread). Reuse one test name.
35. **"Here", "this chest", "the floating thing"** — players point with words. Every chat line now carries where the
    player stood and looked when they wrote it: read that before asking where they mean.

## From building a cinema and a gallery

36. **A seat's stair block used the direction it LOOKS as its `facing` state.** A stair's `facing` is the side its
    backrest faces, not the way a seated player looks — the backrest ended up in front of the sitter instead of
    behind them. A seat that looks north needs `facing=south`.
37. **A poster and a wall plaque were positioned at the wall block's own coordinate.** A block at integer z=Z spans
    z..z+1, so a display centred on z is inside solid stone and renders nothing. Put it on the FACE the room's
    interior actually sees — one block further in the direction of that face (or the equivalent fractional offset
    for an entity) — never the block's own coordinate (`displays.md` has the same rule for any display, not just
    posters).
38. **A resource-pack part was deployed without anyone looking at a preview, and one map came out completely
    blank** (a texture path typo that never threw an error). A contact sheet or a rendered preview catches a
    clipped card, a wrong palette or a dead frame in one glance, before it reaches a live player. Never ship a
    resource-pack part nobody has visually checked.
39. **One custom item-model button was reused for every trigger in a build**, from a lift call to a cinema
    entrance to a gallery exhibit. Every button ended up looking and behaving exactly the same, and none of them
    read as special anymore. Reserve a custom model for one signature feature; a plain vanilla button (polled for
    its `powered` rising edge) is simpler, needs no pack at all, and is the right default for everything else.

## From building a tower of floors (hotel, registration, arcade, club, museum, roof)

40. **Hotel doors moved to another block after a few toggles.** Each door half was toggled with scarpet `set()`, and
    the game "repaired" the half-door by placing it elsewhere. Set both halves with `setblock` and the full state
    (`half`, `facing`, `hinge`, `open`), and keep `facing`/`hinge` in the data file.
41. **A throw fired before the player chose a power.** Holding right-click on a plain item repeats the use event.
    Give the item a `consumable` component with a long `consume_seconds`: the use event marks the start, and
    `__on_player_releases_item` fires once on release.
42. **An "invulnerable" mannequin was killed by a creative-mode player.** `Invulnerable:1b` does not stop creative
    hits. Cancel the hit in `__on_player_attacks_entity` by returning `'cancel'`.
43. **A zone message and an admin-floor guard fired on players riding the lift past the floor.** Every area rule must
    exclude the lift shaft column and anyone mounted.
44. **A nametag showed through three floors.** Hide it (`CustomNameVisible:0b`) and use a small `text_display` with
    `view_range:0.2f` next to the head.
45. **Music and lights drifted apart.** Choose a tempo whose beat is a whole number of ticks (150 BPM = 8 ticks), make
    the loop a whole number of bars (51.2 s = 1024 ticks), and trigger both sound and lights from the same `tick % 8`.
46. **Build protection:** `player_placing_block` fires *before* a block goes in and can be cancelled.
    `player_places_block` fires after and cannot. Buckets need `player_uses_item`, because they aim by raycast.
    WorldEdit, `/fill` and TNT go around all of it, so keep a block logger.
47. **A museum photo of a roller coaster showed an empty field.** The track was display entities, which a block
    renderer does not draw. Photograph the station building, or take a real in-game screenshot. (`minecraft_screenshot`
    now draws display entities textured; BlueMap still doesn't.)
48. **A lit redstone lamp set with `setblock` turned itself off.** For lights an app switches on and off, use
    `waxed_copper_bulb[lit=true|false]`: a copper bulb keeps its state without redstone.
49. **Players painted with red error spam.** `query(p, 'active_item')` does not exist in Carpet for 26.2. Track a
    held right-click with `__on_player_uses_item` / `__on_player_releases_item` and check
    `query(p, 'holds', 'mainhand')` each tick.
50. **"Saving needs a restart" after the restart.** Scarpet apps load before Fabric's `SERVER_STARTED`, so a file a
    mod writes at start is not there yet in `__on_start`. Read such markers lazily, when they are needed.
51. **A toolbar and every mannequin after it never spawned.** An entity tag with `:` (`tool:brush`) breaks
    `@e[tag=..]`, and the error stopped the whole spawn pass. Keep tags to `[a-z0-9_]`.
52. **A live one-function patch broke the function.** Patches are joined into one line, so a `//` comment in the
    middle of an expression swallowed the rest. Put comments on their own line above.
53. **The easel vanished from across the room.** `view_range` scales the entity render distance: 0.3 is about 19
    blocks. UI that must read across a room needs 1.0. A `text_display` is hidden behind blocks, unlike a nametag
    (lesson 44), so a longer range does not leak through floors.
54. **Pixels any colour, cheaply:** a 10x10 white glyph with ascent 7 fills one text-display line exactly (lines are
    10 font px apart at 0.025 block/px), a -1 space glyph cancels the automatic +1 advance, and the component colour
    tints it. One `text_display` per band of the picture, `shadow` off.
55. **Music for someone moving far (a 150-block lift ride) faded away.** A played sound stays where it started. Pass
    `minVolume` (`playsound <s> record @s ~ ~ ~ 0.55 1 0.55`): beyond its range the listener keeps hearing it at that
    level. For short rides, slice a track into equal segments and play each rider the next one.
56. **"Some colours don't work" on a pixel canvas** was painting under a template's second layer. Paint what the
    player sees by default, and show a cursor on the aimed pixel; add a magnifier when pixels are small.

## From keeping vehicles, boards and posters alive on a busy server

57. **Two wall posters sat half a block off, one half behind a pillar.** `summon` and `tp` centre an **integer** x or z
    (`-72` becomes `-71.5`); only a number with a decimal point is exact. Write `-72.0` for a display that must sit
    exactly on a block edge (scarpet `spawn()` is exact too). Y is never shifted.
58. **A vehicle left a frozen copy of itself behind.** When a chunk drops below full loading (its last player
    teleports away) its entities stay in memory but `entity_id(uuid)` returns null, so a cleanup by stored uuids
    removes nothing. When the chunk is full again they come back **without** an `entity_load_handler` event (that
    only fires for a load from disk). Tag every group an app spawns with an incarnation id (`bus_i<n>`, a new n each
    time) and sweep by tag (`entity_selector('@e[tag=bus]')`, remove those whose incarnation is not the live one).
    Never trust uuid-only removal or the load handler alone. `minecraft_entities action:ghosts` finds the leftovers.
59. **A score board grew one copy per server restart** (31 stacked). The app killed and summoned it in `__on_start`,
    when nobody was near: the kill missed the old one in the unloaded chunk, the summon still went in. Create such
    things lazily (on a tick, only while a player is within range), check for an existing one first, and give them a
    generation tag. `minecraft_entities action:duplicates fix:true` removes the extra copies.
60. **Mobs with custom models were invisible to every entity query.** Server-side model libraries built on Polymer
    (for example Blockbench Import Library) keep only the base mob on the server; the model parts are packets sent to
    each player. A census, a selector or a screenshot sees the base mob, not the model. Check those in game.
61. **The resource pack stopped downloading for friends who joined through a tunnel.** Polymer's AutoHost serves the
    pack over HTTP on the game port, and a tunnel of type "Minecraft Java" only carries the game protocol and resets
    anything else. Use a raw TCP tunnel for the game port, or host the pack on a web host.
62. **A pack host started storing empty files.** The upload "worked" and returned a URL, and the server would have
    pointed every player at a 0-byte pack. Download every uploaded copy and compare its SHA-1 before it goes into
    `server.properties`; when it fails, try the next host once. Never loop uploads: retry loops look like bot spam,
    and free hosts close uploads over it. `minecraft_pack action:deploy` does both.

See also: `verification.md`, `game-logic.md`, `behaving-naturally.md`, `cinema-and-gallery.md`, `tower-floors.md`.
