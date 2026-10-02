# Privacy

**Pink Golem has no accounts, no telemetry, no analytics and no servers of its own.** It never sends your AI
conversations anywhere, and everything it records stays in files on your computer. This page lists every network
connection the code in this repository makes, so you can check that for yourself.

## What stays on your computer

- **`data/`**: the world map (`world_index.json`), protected zones, the undo stack, screenshots, the shared journal
  (`LEARNINGS.md`) and `people.json`: what the AI chose to remember about players (Minecraft name, roles, what they like
  to build, notes). Delete any of it whenever you like.
- **`pinkgolem.json`**: your settings, including the owners list (Minecraft names).
- **`server/`**: your Minecraft server, its world and its logs. The MCP server reads `server/logs/latest.log` to see chat.
- The MCP server talks to your AI client over stdio (a local process) and to the Minecraft server over RCON on
  `127.0.0.1`. It opens no port of its own.
- Screenshots read the server resource pack and, if this computer has the Minecraft launcher, its client jar (for
  vanilla models and the font). Both are only read, on this computer (`"client_jar": false` turns the jar off).

## What your AI provider sees

Tool results go to your AI client, and your client sends them to the model you chose. They include chat lines with
player names and messages, block and entity data, and screenshots. That part is covered by your AI provider's own
privacy policy (Anthropic, Google, OpenAI, …). With a local model, nothing leaves your computer.
**Tell the players on your server that an AI reads the chat.**

## Every network connection

| When | To | What is sent | Off switch |
|---|---|---|---|
| Setup and `pinkgolem.py mods` | `api.modrinth.com`, `cdn.modrinth.com` | the mod name and your Minecraft version; the mod files come back | needed for setup |
| Setup | `meta.fabricmc.net` | your Minecraft version; the Fabric server launcher comes back | needed for setup |
| Setup | the npm registry | `npm install` of the MCP SDK in `mcp-server/` | needed for setup |
| Setup, if you say yes | Mojang's download servers, by BlueMap | BlueMap downloads Minecraft's textures to draw the map | answer no at setup, or `"bluemap_textures": false` |
| Every tool call | `127.0.0.1` (RCON) | server commands | local only |
| `minecraft_screenshot` with real textures | `localhost:8100` (BlueMap), through your own Chrome or Edge, started headless with a fresh temporary profile and driven over a local DevTools port for a few seconds | a map URL | local only (the browser may still make its own background calls, as on any start) |
| `minecraft_pack deploy` (when you or the AI deploy a pack), by default | `mcpacks.dev`, a free resource-pack host | the resource pack zip and its file name, through the site's upload form (the tool ticks its consent box for you, so [mcpacks.dev's terms](https://mcpacks.dev) apply); the pack gets a link anyone who has it can download, which is how players' games fetch it. The tool then downloads it once to check it | `"resource_pack": {"upload": {"hosts": []}}` in `pinkgolem.json`, your own upload setting (below), or deploy with `url:` |
| The same, only if `mcpacks.dev` fails or serves a broken copy | `catbox.moe`, a free file host | the same zip, as an anonymous upload; checked the same way | the same; or `"upload": {"hosts": ["mcpacks"]}` |
| `minecraft_pack deploy` with your own upload setting | whatever you configured: `upload.command` (or the older `upload_command`) or `publish_dir` | the resource pack zip; afterwards the tool downloads that URL once to check it | remove the setting |
| Saving a skin on the in-game skin easel (the optional Key Bridge mod) | `api.mineskin.org` | the 64×64 skin image and its name, uploaded as *unlisted*; [MineSkin's terms](https://mineskin.org) apply | don't install Key Bridge, or don't use the easel |

Pink Golem makes no other connections: no update checks, no crash reports, no usage statistics.

## What this page doesn't cover

- **Minecraft and the mods themselves.** The Minecraft server contacts Mojang when players log in (in online mode) and
  for player profiles. Your players' games download the server's resource pack from its URL. Each mod
  ([Fabric](https://fabricmc.net), [Carpet](https://github.com/gnembon/fabric-carpet),
  [BlueMap](https://bluemap.bluecolored.de), [WorldEdit](https://enginehub.org/worldedit), …) follows its own policy.
- **Anything you open to the internet.** [Exposing to friends](docs/exposing-to-friends.md) covers what to share and
  what never to share (RCON).

## Contact

Questions or a connection this page missed: [open an issue](https://github.com/sagistiki/pink-golem/issues).
Security problems: [SECURITY.md](SECURITY.md).

*Last updated: 2026-10-02.*
