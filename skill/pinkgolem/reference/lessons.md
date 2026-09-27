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

See also: `verification.md`, `game-logic.md`, `behaving-naturally.md`, `cinema-and-gallery.md`.
