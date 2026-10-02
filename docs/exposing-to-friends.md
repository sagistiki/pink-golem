# Playing with friends

This page shows how to let other people join your Pink Golem server: on the same Wi-Fi, over the internet
through your router, or through a tunnel service. It also covers the safety settings to check first. Read the
[security notes](#security-checklist) before you open anything to the internet.

**The one rule:** share the **game port** (25565 by default) and nothing else. **Never** expose the RCON port
(25575 by default). RCON is a full server console, and whoever reaches it can run any command.

---

## Before anyone joins

| Check | Why |
|---|---|
| Friends use **Minecraft Java Edition 26.2** | the client version must match the server |
| Friends own Minecraft Java | `online-mode=true` (set by setup) checks every account with Microsoft, so nobody can join under someone else's name |
| You made a backup: `python3 pinkgolem.py backup` | new people plus an AI that builds on request: have a way back |
| You decided who is an operator | ops can run every command, including `/stop` and WorldEdit |

New Pink Golem worlds start in **creative** mode on **peaceful** difficulty. To change that for everyone, edit
`gamemode` and `difficulty` in `server/server.properties` while the server is stopped. To change it for one
player, run `/gamemode survival <name>`.

---

## 1. Same network (LAN)

Friends on the same Wi-Fi or network connect to your computer's **local IP address**.

1. Find your local IP:
   - macOS: **System Settings → Wi-Fi → Details**, or run `ipconfig getifaddr en0`
   - Windows: run `ipconfig` and read *IPv4 Address*
   - Linux: `hostname -I`
2. Friends choose **Multiplayer → Add Server** and enter `192.168.1.23:25565` (your address, your port).
3. If they can't connect, it is almost always the **firewall**. The first time the server starts, Windows asks
   whether Java may use the network: allow it on **private networks**. On macOS, allow incoming connections for
   `java` when asked, or in **System Settings → Network → Firewall**.

If BlueMap is installed, friends on your network can usually open the 3D web map at `http://<your local IP>:8100`.

---

## 2. Over the internet: port forwarding

Port forwarding tells your router to pass game traffic from the internet to your computer.

1. **Give your computer a fixed local IP.** In your router's admin page (often `http://192.168.1.1` or
   `http://192.168.0.1`; the address and password are usually on a sticker on the router), find *DHCP
   reservation* or *static lease* and reserve your computer's current local IP. Otherwise the forward breaks when
   the IP changes.
2. **Forward the game port.** Find *Port forwarding* (sometimes under *NAT*, *Virtual server* or *Gaming*). Add a
   rule: external port **25565**, protocol **TCP**, to your computer's local IP, internal port **25565**. Use your
   own port if you changed it at setup.
3. **Do not forward 25575** (RCON), or 8100 (BlueMap) unless you really want the map public.
4. **Find your public IP**: search the web for "what is my IP". Friends connect to `<public IP>:25565`.
5. **Test from outside your network**, for example a friend, or your phone's mobile data with a port-check website.
   Testing from inside your own network often fails even when the forward works.

**When port forwarding doesn't work:**

| Situation | What it means | Do this |
|---|---|---|
| The router's "WAN" or "Internet" IP differs from the public IP you looked up | your provider uses **CGNAT**: several customers share one public address, and no forward can reach you | use a tunnel (next section), or ask your provider for a public IP |
| It works for a day, then friends can't connect | your public IP changed | use a dynamic DNS service (many routers have one built in) or a tunnel |
| You can't open the router's admin page (student housing, some rentals) | you don't control the router | use a tunnel |

---

## 3. Tunnel services (no router changes)

A tunnel service gives your server a public address without touching the router. A small program (the *agent*)
on your computer keeps an outgoing connection to the service. Players connect to the service's address, and it
passes their traffic through that connection to your server. This works behind CGNAT and on networks you don't
control.

**playit.gg** is a popular one made for game servers, with a free tier. Other services work the same way, and
virtual-LAN tools (such as Tailscale or ZeroTier) are an alternative for a small group of friends who are
willing to install the tool too.

General steps (the exact screens change over time; follow the service's own guide):

1. Create an account on the service's website.
2. Download and run its agent on the computer that runs the Minecraft server. Link it to your account when asked.
3. Create a tunnel of type **Minecraft Java** (TCP) that points to **127.0.0.1:25565**, or your game port.
4. The service shows a public address (a hostname, sometimes with a port). Give that to your friends.
5. Keep the agent running while you play. It can usually be installed as a background service.

Notes:

- **Free tiers** usually give you a random or shared address and fair-use limits; paid plans add things like
  custom addresses or dedicated ports. Check the current terms on the service's site.
- Tunnel **only the game port**. Never create a tunnel to the RCON port.
- A tunnel adds a little latency. For friends far away, a service with a relay near them helps.
- A **Minecraft Java** tunnel carries only the game protocol and resets anything else on that port. That matters if
  the resource pack is served from the game port too (Polymer's AutoHost does that): friends who join through the
  tunnel can't download it. Host the pack elsewhere (`minecraft_pack action:deploy` uploads it to a pack host by
  default), or use a plain TCP tunnel for the game port.

---

## 4. Whitelist: only invited players

With the whitelist on, only names on the list can join. In the server console (or ask your AI to run these):

```
whitelist on
whitelist add FriendName
whitelist list
whitelist remove FriendName
```

The list lives in `server/whitelist.json`. Keep `online-mode=true`: the whitelist then matches real Microsoft
accounts, not just names that anyone could type.

The AI's body and the helper builders are fake players spawned from the server console, so the whitelist does not
normally keep them out. If a bot can't spawn after you turn the whitelist on, add its name too
(`whitelist add Claude`). Fake players do count toward `max-players` (20 by default): the AI plus four helpers use
five slots.

---

## Security checklist

| Setting | Where | Recommended |
|---|---|---|
| Game port open to the internet | router or tunnel | only if you want internet play; TCP 25565 only |
| RCON port | router, tunnel, firewall | **never** reachable from outside. The MCP server only uses it on this computer (`127.0.0.1`) |
| `rcon.password` | `server/server.properties` | the random 20-character password setup made. Never post or screenshot this file; it is not committed to git |
| `broadcast-rcon-to-ops` | `server.properties` | `false` (setup's value): the AI's many console commands aren't echoed to ops in chat |
| `online-mode` | `server.properties` | `true` |
| `white-list` | `whitelist on` | on for internet play |
| Operators | `op` / `deop`, stored in `server/ops.json` | only people you trust |
| `spawn-protection` | `server.properties` | setup sets `0` so everyone can build at spawn. Raise it (e.g. `16`) if you don't want non-ops building there |

Why RCON matters so much: RCON runs every command as the server console (the highest permission level). The only
protection is the password, and the RCON protocol sends it unencrypted. The MCP server connects to it on the same
machine, so there is never a reason to expose it. If you suspect the password leaked, change `rcon.password` in
`server.properties` and restart the server. Running setup again keeps the current password, so change it by hand.

**About the AI and other players.** The AI listens to chat and takes requests from anyone on the server. The skill
tells it to respect other people's builds (protected zones, the overwrite guard) and to change someone's build
only when its owner asks. Every AI build can be undone, and the AI remembers people and their roles
(`minecraft_people`). Tell it who is in charge ("only build when I ask, or when my brother asks") and it will note that. It is still
a powerful helper, so invite people you trust, and keep backups.

**Mods that help on a public server:** `ledger` (block logging and rollback, `python3 pinkgolem.py mods add
ledger`) shows who changed what, and `spark` finds lag.

## See also

- [Getting started](getting-started.md): ports, `server.properties`, operators
- [Troubleshooting](troubleshooting.md): "connection refused", lag, backups
- [Architecture](architecture.md): why RCON stays local
