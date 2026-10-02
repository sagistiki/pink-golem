# Entities: NPCs, villagers, animals and pets

Read this before you summon anything that lives or looks alive: a shopkeeper, a butler, villagers for a village, zoo
animals, a pet for someone. Entities are where builds go wrong quietly — a mob suffocates a second after it
appears, a villager loses its job, a pet freezes, a command meant for one NPC hits the world origin. The rules below
come from things that actually happened.

**G** = the ground block (flat world: y=-61); a mob standing on it has its feet at G+1.

## Rules for every summon

| Rule | Why |
|---|---|
| `Tags:["<project>"]` on every entity | find, list and remove them later |
| `CustomName:"Mia"` as a **plain string** | a JSON string shows raw JSON; `'"Mia"'` shows the quotes |
| `PersistenceRequired:1b` on mobs | otherwise they can despawn |
| `Invulnerable:1b` on NPCs and pets | players and accidents can't kill them |
| Summon at block centres (`x.5`) **on top of** a solid floor | a mob inside a solid block suffocates |
| Only in **loaded chunks** | `summon` far from any player fails; `minecraft_bot action:tp` the bot there first |
| List them again **~5 s later**, not right after | a check right after the summon listed every pet while two were already suffocating inside a solid decoration block |
| Never summon in a loop or from a repeating command block | entity spam from repeating command blocks has crashed a server (watchdog) |
| On Peaceful difficulty hostile mobs can't be summoned | use a `mannequin` dressed up instead |

## NPCs: the vanilla `mannequin`

A `mannequin` is a player-shaped entity with equipment and poses — the vanilla way to make shopkeepers, guards,
butlers and statues. Working summon:

```
summon minecraft:mannequin 100.5 -60 40.5 {Tags:["shop_npc"],Rotation:[180f,0f],pose:"standing",immovable:1b,hide_description:1b,Invulnerable:1b,Silent:1b,equipment:{chest:{id:"minecraft:leather_chestplate",components:{"minecraft:dyed_color":16711680}},mainhand:{id:"minecraft:cookie"}},CustomName:"Mo",CustomNameVisible:1b}
```

| Field | Use |
|---|---|
| `Rotation:[yaw,0f]` | where it looks: south 0, west 90, north 180, east -90 |
| `pose` | `"standing"`, `"crouching"`, `"sleeping"` (a sleeper in a bed) |
| `immovable:1b` | players can't push it off its spot |
| `hide_description:1b` | hides the extra line under the name |
| `equipment` | `head`, `chest`, `legs`, `feet`, `mainhand`, `offhand`; dyed leather via `"minecraft:dyed_color":<rgb int>` |
| `CustomName:"Dinnerbone"` | vanilla joke: it renders upside down |

**Seated NPC:** make the mannequin a passenger of an invisible marker armor stand whose height is the seat height —
a stair seat at the block's y + 0.5, a bar stool (fence + carpet) at y + 1.6:

```
summon armor_stand 100.5 -59.5 40.5 {Invisible:1b,Marker:1b,NoGravity:1b,Tags:["bar_npc"],Passengers:[{id:"minecraft:mannequin",pose:"standing",immovable:1b,Invulnerable:1b,CustomName:"Kai",CustomNameVisible:1b,Tags:["bar_npc"]}]}
```

### Making NPCs feel alive

| Effect | Command |
|---|---|
| Turn to face a player | `execute as @e[tag=shop_npc] at @s run tp @s ~ ~ ~ facing entity <player> eyes` |
| Turn to a fixed yaw | `execute as @e[tag=shop_npc] at @s run tp @s ~ ~ ~ 90 0` |
| Swing an arm | scarpet `for (entity_selector('@e[tag=shop_npc]'), modify(_, 'swing'))` |
| Crouch / stand on a beat | `execute as @e[tag=dancer] run data merge entity @s {pose:"crouching"}` |
| Say something | a temporary `text_display` about 2.45 blocks above its feet, killed after ~3 s (`displays.md`) |
| Greet visitors | a scarpet app that fires on the **rising edge** of "player entered the box", with a per-player cooldown |

`scarpet-apps/vendor.sc` shows the pattern: a button press makes the NPC tagged `npc_tag` turn to the nearest player
and swing while the player gets an item. Writing such apps: `game-logic.md`.

## Villagers

```
summon villager 100.5 -60 40.5 {VillagerData:{profession:"minecraft:farmer",level:2,type:"minecraft:plains"},Xp:10,CustomName:"Rosa",PersistenceRequired:1b,Invulnerable:1b,Tags:["village"]}
```

- **`level:2` + `Xp`** keeps the profession even before the villager finds a job site block. `nitwit` and `none`
  stay at level 1.
- `type`: `plains`, `desert`, `jungle`, `savanna`, `snow`, `swamp`, `taiga` (the outfit). Match it to the house style.
- Give every villager a bed and every professional its job site block nearby; a `bell` marks the meeting point.
- **Loaded chunks only:** tp the bot to each site first, then summon that site's villagers.
- About 5 s later, check they settled: `minecraft_scarpet expression:"l=[]; for(entity_selector('@e[type=villager,tag=village]'), b=str(query(_,'nbt','Brain')); l+=str('%s home:%s job:%s', _~'name', b~'home'!=null, b~'job_site'!=null)); l"`.

| Profession | Job site block | Profession | Job site block |
|---|---|---|---|
| farmer | `composter` | librarian | `lectern` |
| cleric | `brewing_stand` | butcher | `smoker` |
| fisherman | `barrel` | toolsmith | `smithing_table` |
| cartographer | `cartography_table` | shepherd | `loom` |
| fletcher | `fletching_table` | armorer | `blast_furnace` |
| weaponsmith | `grindstone` | leatherworker | `cauldron` |
| mason | `stonecutter` | | |

In a test, 40 loaded villagers kept the server at about 13 ms per tick — a village is fine; a crowd of hundreds is not.

## Animals

Summon on the enclosure floor at G+1 (`.5` centres), flyers one block higher, fish and axolotls in the middle of
their tank. Always `CustomName`, `PersistenceRequired:1b` and a tag. Variant NBT that works:

| Animal | NBT |
|---|---|
| Parrot | `Variant:0` … `4` (red, blue, green, yellow-blue, grey) |
| Axolotl | `Variant:0` … `4` |
| Fox | `Type:"snow"` for a white fox |
| Panda | `MainGene:"playful"` / `"lazy"` / `"normal"`, `HiddenGene:` the same values |
| Cat | `CollarColor:6b` = pink collar (for tamed cats) |
| Rideable horse | `{Tame:1b,Age:0,Temper:100,equipment:{saddle:{id:"minecraft:saddle",count:1}}}` (tested on 26.2; the old `SaddleItem` tag no longer saddles the horse) |

Enclosure rules (curb + 2 glass, roofs for flyers and jumpers, hole scan before summoning, water last) are in
`landscaping.md`. After summoning, list every animal with its position and check each is inside its box:

```
minecraft_scarpet expression:"l=[]; for(entity_selector('@e[tag=zoo]'), p=pos(_); l+=str('%s %s %d %d %d', _~'type', _~'name', p:0, p:1, p:2)); l"
```

## Pets and taming

1. Get the player's UUID: `data get entity <player> UUID` → `[I; a, b, c, d]` (or `minecraft_people action:get`).
2. Tame by setting the owner on the mob (target it by its UUID or a precise selector):
   `data merge entity <mob uuid> {Owner:[I;a,b,c,d],Invulnerable:1b}` — cats also `CollarColor:6b`.
3. `minecraft_people action:pets name:"<player>"` lists the mobs tamed to them (loaded chunks only).

- **A tamed mob has exactly one owner.** "Tame it for both of us" is impossible — say so and offer choices (one pet
  each, or one owner and the other plays with it).
- **A pet whose owner is offline freezes in place** (vanilla sits-when-owner-missing behaviour). To let pets roam a
  building while the owner is away, make an invisible marker armor stand the owner:
  `summon armor_stand x y z {Invisible:1b,Marker:1b,NoGravity:1b,Tags:["pet_keeper"]}`, read its UUID in scarpet
  with `str(query(e,'nbt','UUID'))`, and let an app switch `Owner` to the keeper while the player is offline and
  back to the player when they arrive. Pets then wander around the keeper.
- **Never summon a pet inside a solid block.** A decorative box or bed that is a full block suffocates it; summon on
  top (y + 1) and check again ~5 s later.
- A pet you can't find with a selector is in an unloaded chunk (or gone). Selectors and `people pets` only see
  loaded chunks.

## Counting and cleaning up

- Keep counts modest: about 25 animals for a zoo, a few NPCs per building. Every entity costs server time.
- Your own entities: `kill @e[tag=<project>]` (check the tag first — it removes every entity carrying it; count with
  `execute if entity @e[tag=<project>]`).
- Clutter: `minecraft_cleanup` removes dropped items, xp orbs, arrows, stray firework rockets and falling blocks,
  optionally in an area (`from`/`to` or `pos` + `radius`); `dry_run:true` only counts; `types:[...]` for others.
- Flowers washed away by water or popped off stone show up as dropped items — clean them after fixing the cause.

## Leaks: census, duplicates and ghosts — `minecraft_entities`

Apps that spawn entities leak in two typical ways: a **pile** (the same display summoned again and again on one spot,
e.g. on every restart) and a **ghost** (an old copy of a moving object left behind when its chunk unloaded, while the
app made a new one). Both cost server time and look broken.

| Call | What you get |
|---|---|
| `minecraft_entities` (census) | display / interaction / armor-stand / mannequin / marker entities by type and by family (first tag that isn't numbered) with their x/z span, plus piles and ghosts. `all:true` = every non-player entity |
| `action:duplicates` | piles: same type + tags + position + what they show (item model, dye, text, block, transformation). `fix:true` keeps one of each pile and removes the rest |
| `action:ghosts` | objects carrying two incarnations, apps with two generations alive (see the convention below), newest first |
| `action:remove tags:[…]` or `uuids:[…]` | a dry run listing what would go; `confirm:true` removes (max 5000, never players) |

Area: every loaded chunk, or `pos`/`player` + `radius` (default 64). **Only loaded chunks are seen**: a leak where
nobody is standing doesn't show up until someone goes there. After a fix, the app still leaks until its spawn code is
fixed (lessons 58-59). Mobs whose model comes from a Polymer-based model library show up as their base mob only: the
model parts are packets, not entities (lesson 60). Needs the `cu` app's `census()`: after an update,
`python3 pinkgolem.py apps add cu`.

### The tagging convention ghosts rely on

Give everything an app spawns three kinds of tags:

| Tag | Example | Meaning |
|---|---|---|
| the app | `bus` | find and remove everything of the app |
| the object | `bus_5` | one bus = several entities (body, seats, hitboxes) |
| an incarnation **or** a generation | `bus_i43` / `bus_g7` (also `_gen<n>`, `_run<n>`) | `_i<n>`: a new n every time this object is spawned again. `_g<n>`: one n per app run, bumped when the app starts |

Then an app can sweep by tag (`entity_selector('@e[tag=bus]')`, remove what doesn't carry the live incarnation or
generation) instead of trusting stored uuids, and the census can say "`bus_5` carries `bus_i43` **and** `bus_i76`":
one of them is a leftover (ask the app which is live, then `action:remove tags:['bus_i43']`). Only `_i`, `_g`, `_gen`
and `_run` tags are compared; other numbered tags (`car_12`, `flag_8795`) are object ids and never count as ghosts of
each other. Keep tags to `[a-z0-9_]`.

Spawn such groups only while a player is near, check for an existing one first, and never in `__on_start` (the chunk
may not be loaded: lessons 58-59).

## `execute as … at @s` — the one-entity rule

| Wrong | Right | Why |
|---|---|---|
| `execute as @e[tag=npc] run tp @s ~ ~ ~ 90 0` | `execute as @e[tag=npc] at @s run tp @s ~ ~ ~ 90 0` | without `at @s`, `~` is where the command runs — from the console that is the world origin, so the NPC jumps to 0 0 0 |
| `data merge entity @e[tag=npc] {...}` | `execute as @e[tag=npc] run data merge entity @s {...}` | `data merge entity` and `rotate` accept one entity |
| Selecting by a non-ASCII name | select by tag, box or UUID | name selectors can miss over RCON |

## Common mistakes

- Summoning far from the bot → nothing appears (unloaded chunk).
- A mob summoned into a full-block decoration → suffocates a second later.
- A villager at level 1 without a job site nearby → loses its profession.
- Pets tamed to an offline player "stuck" in place → use the keeper trick.
- A JSON-wrapped `CustomName` → the raw JSON shows above the head.
- Forgetting tags → you can't clean up without hitting players' own animals.

## See also

`displays.md` · `landscaping.md` · `game-logic.md` · `scarpet.md` · `behaving-naturally.md` · `troubleshooting.md` ·
`mods.md`
