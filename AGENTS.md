# Pink Golem — instructions for AI agents (Codex, Gemini CLI, and others)

This repository runs a Minecraft Java server that you can build in through the Pink Golem MCP server (tools named
`minecraft_*`).

**Before doing anything in the Minecraft world, read `skill/pinkgolem/SKILL.md` and follow it.** It has the golden
rules, a step-by-step recipe for any build request, a table of every tool, and links to the reference pages in
`skill/pinkgolem/reference/` — read the page that matches your task before you start it.

If your context is small, `skill/pinkgolem/SYSTEM_PROMPT.md` is the condensed version.

Repository layout:
- `pinkgolem.py` — setup / start / stop / status / doctor / mods / apps / connect (Python, stdlib only)
- `mcp-server/` — the MCP server (Node): `index.js` core, `lib/` shared helpers, `tools/` tool groups
- `skill/pinkgolem/` — SKILL.md, `reference/`, `scripts/` (mclib.py, parts.py, city.py, scarpet helper apps), `blueprints/`
- `scarpet-apps/` — example game-logic apps (launch pads, races, TNT Run, vendor stands, secret doors…)
- `jobs/` — generated build files (yours go here too); `data/` — the world map, zones, undo, notes, screenshots

Never start, stop or reset the Minecraft server unless the user asks.
