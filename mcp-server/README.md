# ClawdBlock MCP server

The Node MCP server behind ClawdBlock: 29 `minecraft_*` tools over stdio. It talks to the Minecraft server through
RCON (commands), `logs/latest.log` (chat) and Carpet's scarpet (fast world reads).

```
index.js          core: config, RCON client, log watcher, MCP wiring, hot reload
lib/core.js       locked RCON, JSON files, chat, players, geometry, scarpet helpers
lib/features.js   which mods are installed (hides tools that need a missing mod)
lib/world.js      region reads, natural-terrain rules, structure detection and text views
lib/safety.js     zones, overwrite guard, undo snapshots, auto-zones, verification
lib/crew.js       helper builders and speech bubbles
lib/bot.js        walking, A* pathfinding through doors, follow, reachability
lib/jobs.js       background jobs, after-build checks, Python generators
lib/sight.js      screenshots, previews, BlueMap photos, access check, free-space search
tools/*.js        tool groups: connection, chat, build, look, body, memory (schema + handler per tool)
render.js pathfind.js sim.js analyze.js worldmap.js   pure helpers (renderer, A*, command simulator, access analysis, map index)
test/load.mjs     loads every tool against a fake server — `npm run check`
test/run.mjs      drives the real MCP from a script: node test/run.mjs '[["minecraft_status",{}]]'
```

Everything in `lib/`, `tools/` and the helper modules hot-reloads: save a file and the next tool call uses it
(changes to `index.js` need a client restart). Configuration comes from `../clawdblock.json` and environment
variables (`MC_BOT_NAME`, `MC_CHAT_COLOR`, `MC_SERVER_DIR`, `MC_RCON_HOST`, `MC_RCON_PORT`, `MC_RCON_PASSWORD`,
`CLAWDBLOCK_CONFIG`). See [../docs/architecture.md](../docs/architecture.md) and [../docs/contributing.md](../docs/contributing.md).
