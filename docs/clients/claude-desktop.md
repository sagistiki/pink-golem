# Claude Desktop

This page connects the **Claude Desktop** app to your Pink Golem server. Desktop is the friendliest way to play if
you'd rather not work in a terminal: you chat in a window and Claude builds in your world. Setting it up takes two
steps, the MCP entry and the skill upload.

| | |
|---|---|
| Connect | `python3 pinkgolem.py connect claude-desktop` |
| MCP config | `claude_desktop_config.json` (path per system below) |
| Skill | upload `dist/pinkgolem-skill.zip` in **Settings → Capabilities → Skills** |
| Bot name | the one in `pinkgolem.json` (default **Claude**) |
| After connecting | **quit and reopen** Claude Desktop |

---

## Connect

Setup offers this automatically when it finds Claude Desktop's settings folder. To do it later, or again:

```bash
python3 pinkgolem.py connect claude-desktop
```

## What it writes

**1. The MCP entry**, merged into Claude Desktop's config file. Other servers in it stay as they are, and a
`.bak` copy is saved first.

| System | Config file |
|---|---|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| Linux | `~/.config/Claude/claude_desktop_config.json` |

```json
{
  "mcpServers": {
    "pinkgolem": {
      "command": "/usr/local/bin/node",
      "args": ["/home/you/pinkgolem/mcp-server/index.js"]
    }
  }
}
```

The `command` is the **absolute path** of `node`. Desktop apps don't see your terminal's `PATH` (on macOS they
don't read your shell profile), so a bare `node` often fails there. Setup writes the full path for you.

**2. The skill as a zip**: `dist/pinkgolem-skill.zip`, which contains the `pinkgolem/` skill folder (`SKILL.md`,
`reference/`, `scripts/`, `blueprints/`).

## Load the skill

1. Quit Claude Desktop completely: menu bar (macOS) or system tray (Windows) → **Quit**. Closing the window is not
   enough; the app keeps running.
2. Open it again.
3. **Settings → Capabilities → Skills → Upload skill**, and choose `dist/pinkgolem-skill.zip` from your
   Pink Golem folder.
4. Make sure the `pinkgolem` skill is switched on.

If you don't see a Skills section, update Claude Desktop. Skills and the settings they need can depend on your plan
and on other options on the same Capabilities page.

**After every Pink Golem update**, run `connect claude-desktop` again (it rebuilds the zip) and upload the new zip.
The uploaded skill is a copy; it doesn't follow the files in your folder.

## Bot name

Claude Desktop uses the `bot_name` from `pinkgolem.json` (**Golem**, shown as **Pink Golem**, by default), the same as Claude Code. That is
fine as long as you use one of them at a time. To run both together, give Desktop its own body by adding an `env`
block to its entry:

```json
"pinkgolem": { "command": "…", "args": ["…"], "env": { "MC_BOT_NAME": "Claudia" } }
```

Separate names matter because the bot name is the AI's body, its chat name and the owner of its builds. Two AIs
with one name fight over one body and can undo each other's builds. With separate names, each one has its own
body, undo stack and protected builds.

## Manual setup

1. Find your node path: `which node` (macOS/Linux) or `where node` (Windows).
2. Open the config file from the table above (create it if it doesn't exist; Claude Desktop's
   **Settings → Developer → Edit Config** opens it too).
3. Add the `pinkgolem` entry inside `"mcpServers"`, with your two absolute paths. On Windows, write backslashes
   twice: `"C:\\Users\\you\\pinkgolem\\mcp-server\\index.js"`.
4. Make the zip yourself if needed: zip the folder `skill/pinkgolem` so that the zip contains `pinkgolem/SKILL.md`.
5. Quit and reopen Claude Desktop, then upload the skill.

---

## First-session checklist

1. The Minecraft server is running (`python3 pinkgolem.py status`), and you are in the game.
2. Claude Desktop was fully restarted after `connect`.
3. The tools menu in the chat box lists **pinkgolem** with its `minecraft_*` tools.
4. The `pinkgolem` skill is uploaded and enabled.
5. Ask: *"Check the Minecraft server and spawn in next to me."* Approve the tool calls when asked (you can allow
   them for the whole chat).
6. Then: *"Build me a cottage next to me."*

## Tips

- **What Desktop can do without file access.** Everything: it runs the ready blueprints (cottage, modern villa,
  tower, park, drop tower), builds with commands and ASCII layers, sees with screenshots and vision, undoes and
  remembers — and it writes its **own** generators too, by passing the Python source to `minecraft_generate` in
  `code` (saved as `jobs/<name>.py`, then run). No filesystem MCP server is needed.
- **Screenshots come back into the chat.** Ask *"show me a picture of what you built"*. Copies are saved in
  `data/screenshots/`.
- **Long builds.** Blueprints run as background jobs with a progress bar in game. Claude waits for them in steps
  of up to 50 seconds, so a big build shows as several "wait" tool calls. That's normal.
- **Keep one chat per project.** Start a new chat when a conversation gets long. The world map and the AI's journal
  carry over between chats.

## Common problems

| Symptom | Fix |
|---|---|
| No pinkgolem tools after restart | the app wasn't fully quit; or the JSON has a typo (check with a JSON validator); or `node` isn't an absolute path |
| "Server disconnected" | open the MCP log: **Settings → Developer**. Usually `npm install` did not run: `python3 pinkgolem.py doctor` |
| Tools answer `ECONNREFUSED` | the Minecraft server is off: `python3 pinkgolem.py start` |
| Claude ignores the build rules | the skill isn't uploaded or is switched off |

More in [troubleshooting.md](../troubleshooting.md).

## See also

[Claude Code](claude-code.md) · [Gemini CLI](gemini-cli.md) · [Codex](codex.md) · [Local models](local-models.md)
· [Getting started](../getting-started.md)
