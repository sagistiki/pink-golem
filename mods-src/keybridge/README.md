# Key Bridge — a tiny server-side Fabric mod for scarpet apps

Three things scarpet can't do on its own, in ~500 lines of Java. Players need **no** client mod.

## 1. Movement keys → scoreboard

Every tick the mod copies each player's movement keys (the input their client sends) into the dummy scoreboard
objective `keys`, only when they change. A scarpet app reads them with `scoreboard('keys', name)`:

| bit | key |
|---|---|
| 1 | forward (W) |
| 2 | back (S) |
| 4 | left (A) |
| 8 | right (D) |
| 16 | jump (Space) |
| 32 | sneak (Shift) |
| 64 | sprint (Ctrl) |

Useful for vehicles, custom controls and anything that must react to keys while a player rides or is frozen.

## 2. Live resource pack push

Vanilla sends the server resource pack (`server.properties` → `resource-pack`) only when a player joins, so a new
pack normally means a restart. Key Bridge adds (op level 2+):

| command | what it does |
|---|---|
| `/packpush <url> <sha1> [prompt]` | sends the pack to everyone online **now** (one fixed pack id, so a newer push replaces the older one) and drops the pack they got at login; players who join later get it too |
| `/packpush` | shows what is pushed and which pack new logins get |
| `/packpop` | removes the pushed pack and gives players their login pack back |

If `server.properties` already names the **same** url and sha1 when you push (write it first — `minecraft_pack
action:deploy` does), the running server adopts it: later logins get the new pack during login, with one download and
no second reload. Otherwise they get it right after login. Adopting rewrites `server.properties` in the server's own
format, as it does at every start.

`minecraft_pack action:deploy` uses `/packpush` automatically when the command exists.

## 3. Flip camera — the world upside down for one player

For a roller-coaster loop, a barrel roll, a "you're hanging from the ceiling" moment. A spectated camera's pitch is
clamped to ±90° and has no roll, so the mod uses a client trick instead: the client applies the post effect
`minecraft:spider` while its camera entity is a spider, and the resource pack part in [`flipcam/`](flipcam) replaces that
effect with a 180° rotation of the image (vanilla shaders only). The mod shows the player a **fake spider that exists
only on that player's client** (packets only; it is never on the server, so Peaceful doesn't matter; invisible, silent,
no gravity) and sets their camera to it.

| command (op level 2) | what it does |
|---|---|
| `/flipcam start <player> <x> <y> <z> <yaw> <pitch> [eye_height]` | creates the fake spider and makes it the player's camera. `x y z` is the **camera (eye) point**: the spider stands `eye_height` lower. `eye_height` defaults to the eye height of the player's current camera entity (the player: 1.62; a display entity: 0 → the smallest spider, 0.04), because the client eases the camera height after a camera switch (×0.5 per tick) — matching it avoids a vertical slide. The spider is scaled to it (0.65 × scale, scale 0.0625–16). A second start replaces the first: one fake per player |
| `/flipcam move <player> <x> <y> <z> <yaw> <pitch>` | call it every tick with the new camera pose; silent |
| `/flipcam stop <player> [camera_uuid]` | camera back to that entity, or to the camera the server thinks the player has (themselves, or what `/spectate` set), then the fake is removed |
| `/flipcam` | lists the active flip cameras |

Disconnect, death, respawn and a dimension change clean up by themselves.

**Smooth movement.** The client moves a mob one third of the way to the latest position each tick (its 3-step
interpolation restarts with every packet), which trails a moving target by ~2 ticks — about 2 blocks at 20 blocks/s.
The mod sends `have + 3 × (want − have)` instead, so after the client's next tick the camera is exactly at the pose
you gave (the same one-tick latency every entity has). If a packet arrives late, the error shrinks by 2/3 per tick.
Position and pitch go in a teleport packet (full precision); the yaw of a mob's camera is its **head** yaw, sent in a
head-rotation packet (1.4° steps).

**Upside down means the image is rotated by 180°** (a 180° roll): up/down and left/right swap. In a vertical loop,
once the rider is past vertical, give the flipped camera the direction the rider really faces: loop yaw + 180° and
that direction's pitch. At pitch ±90° (straight up or down) the normal and the flipped camera show the same picture,
which is the seamless place to switch.

Resource pack: add `mods-src/keybridge/flipcam/flipcam.zip` to `resource_pack.parts` in `pinkgolem.json` (it is not
included by default) and deploy with `minecraft_pack`. Side effect: anyone spectating a real spider in spectator mode
also sees the flipped view. While the camera is not the player's own, the client doesn't send its own movement
(vanilla behaviour for any camera entity) — fine for a rider.

## Build and install

Needs a JDK (javac) of the server's Java version and a server that has run once (so its jar and libraries exist).

```bash
python3 mods-src/keybridge/build.py --install   # builds build/keybridge-<version>.jar and copies it into server/mods
python3 pinkgolem.py stop && python3 pinkgolem.py start
```

It compiles with plain `javac` against the (unobfuscated) Minecraft 26.x server jar, the server's libraries and three
Fabric API modules taken from the fabric-api jar in `server/mods`. For another Minecraft version, change `minecraft`
in `fabric.mod.json` and rebuild; if Mojang renamed a class, javac tells you which line.

## Safety

Every part runs inside a try/catch: a failure is logged once (`[KeyBridge] … disabled`) and only that part switches
off — it never takes the server down. Commands need op level 2.
