# Pink Golem — instructions for Claude Code

This folder is a Pink Golem install: a Minecraft server (`server/`), the MCP server that gives you tools in it
(`mcp-server/`, tools named `minecraft_*`) and the building skill (`skill/pinkgolem/`).

- When `minecraft_*` tools are available, or the user talks about their Minecraft world, follow
  **`skill/pinkgolem/SKILL.md`** (loaded automatically as the `pinkgolem` skill after `python3 pinkgolem.py connect claude-code`).
- Server control: `python3 pinkgolem.py start | stop | status | doctor` (never start/stop the server without the user asking).
- Generators you write go in `jobs/` (e.g. `jobs/gen_bakery.py`) and are run with `minecraft_generate`.
- Runtime data (`data/`: world map, zones, undo stack, screenshots, LEARNINGS.md) is written by the tools — don't
  hand-edit it while an AI session is running.
- Improving the tools: edit `mcp-server/lib/*.js` or `mcp-server/tools/*.js` (they hot-reload on the next call),
  then `cd mcp-server && npm run check`.
