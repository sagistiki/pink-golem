/** Connection and server health: minecraft_status, minecraft_server_log. */
import fs from "node:fs";

export const tools = [
  {
    name: "minecraft_status",
    description: "Call this first in every session. Checks the RCON connection, who is online, whether your bot body is in the world, which mods are installed (and which tools are unavailable without them), the world type (flat ground level or normal terrain), and the chat cursor.",
    inputSchema: { type: "object", properties: {} },
  },
  {
    name: "minecraft_server_log",
    description: "Read the last lines of the server log (logs/latest.log), optionally filtered by a regex. Good for debugging errors, crashed scarpet apps and mod messages.",
    inputSchema: { type: "object", properties: { lines: { type: "number", description: "default 40, max 400" }, filter: { type: "string" } } },
  },
];

export function handlers(K, ctx) {
  return {
    async minecraft_status() {
      const cfg = ctx.rconConfig();
      const f = K.features;
      const recommended = ["worldedit", "bluemap", "essential_commands", "lithium", "spark"].filter((m) => f.known && !f[m]);
      const st = {
        serverDir: K.P.SERVER,
        rcon: { host: cfg.host, port: cfg.port, enabledInProperties: cfg.enabled, passwordSet: !!cfg.password },
        botName: K.BOT,
        world: K.isFlat ? { type: "flat", ground_y: K.flatGroundY, feet_y: K.flatGroundY + 1, note: `floors and paths replace the grass at y=${K.flatGroundY}; walls start at y=${K.flatGroundY + 1}` }
          : { type: "normal terrain", note: "read the ground height where you build: minecraft_get_players → standingOn.y, or script in cu run ytop(x,z)" },
        mods: f.known ? { installed: f.jars.length, carpet: f.carpet, worldedit: f.worldedit, bluemap: f.bluemap, polydecorations: f.polydecorations, essential_commands: f.essential_commands } : "unknown (the server's mods folder is not on this machine)",
        ...(f.known && !f.carpet ? { PROBLEM: "Carpet is not installed — the bot body, scarpet, undo, vision and most checks need it. Run: python3 clawdblock.py mods add carpet" } : {}),
        ...(recommended.length ? { could_add: recommended.map((m) => `${m} (python3 clawdblock.py mods add ${m})`) } : {}),
        lastChatId: ctx.chat.seq,
        learnings: fs.existsSync(K.P.LEARNINGS) ? "data/LEARNINGS.md has notes from earlier sessions — read them with minecraft_notes action:read" : "no notes yet",
      };
      try {
        const pl = await K.onlinePlayers();
        st.connected = true;
        st.online = pl.raw;
        st.players = pl.names;
        st.botInWorld = pl.names.includes(K.BOT);
        st.following = ctx.state.followTarget;
        if (!st.botInWorld) st.next = `minecraft_bot action:spawn player:<a player's name> — gives you a body in the world`;
      } catch (e) {
        st.connected = false;
        st.error = e.message;
        st.next = "The Minecraft server is not reachable. Start it with `python3 clawdblock.py start` (in the ClawdBlock folder), wait for 'Done', then call minecraft_status again. Meanwhile you can plan, write generators and preview them (minecraft_preview works offline).";
      }
      return K.text(st);
    },

    async minecraft_server_log(args) {
      const n = Math.min(args.lines || 40, 400);
      let lines = fs.readFileSync(K.P.LOG, "utf8").split(/\r?\n/);
      if (args.filter) {
        const re = new RegExp(args.filter, "i");
        lines = lines.filter((l) => re.test(l));
      }
      return K.text(lines.slice(-n).map((l) => l.slice(0, 400)).join("\n"));
    },
  };
}
