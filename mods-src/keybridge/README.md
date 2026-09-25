# Key Bridge — a tiny server-side Fabric mod for scarpet apps

Two things scarpet can't do on its own, in ~250 lines of Java. Players need **no** client mod.

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

## Build and install

Needs a JDK (javac) of the server's Java version and a server that has run once (so its jar and libraries exist).

```bash
python3 mods-src/keybridge/build.py --install   # builds build/keybridge-<version>.jar and copies it into server/mods
python3 clawdblock.py stop && python3 clawdblock.py start
```

It compiles with plain `javac` against the (unobfuscated) Minecraft 26.x server jar, the server's libraries and three
Fabric API modules taken from the fabric-api jar in `server/mods`. For another Minecraft version, change `minecraft`
in `fabric.mod.json` and rebuild; if Mojang renamed a class, javac tells you which line.

## Safety

Every part runs inside a try/catch: a failure is logged once (`[KeyBridge] … disabled`) and only that part switches
off — it never takes the server down. Commands need op level 2.
