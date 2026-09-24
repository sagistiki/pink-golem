/** Talking with players: minecraft_chat, minecraft_get_chat, minecraft_wait_for_chat, minecraft_get_players. */

export const tools = [
  {
    name: "minecraft_chat",
    description: "Say something in game chat as your bot (appears as <BotName> message). Any language works. Long text is split automatically. Public messages also float above your bot's head as a speech bubble. Optionally whisper to one player. Keep in-game lines short, no emoji (they render as boxes) — use ★ ✦ ♥ ✓ ✖ ⏱ ▶ ♪ ⚒ instead.",
    inputSchema: {
      type: "object",
      properties: {
        message: { type: "string" },
        to_player: { type: "string", description: "Only this player sees it (default: everyone)" },
        bubble: { type: "boolean", description: "Also show it as a speech bubble above the bot (default true for public messages)" },
      },
      required: ["message"],
    },
  },
  {
    name: "minecraft_get_chat",
    description: "Read recent chat + join/leave events from the server log. Every event has an id (#N). Pass since_id to get only newer events.",
    inputSchema: { type: "object", properties: { limit: { type: "number", description: "Max events (default 30)" }, since_id: { type: "number", description: "Only events with id greater than this" } } },
  },
  {
    name: "minecraft_wait_for_chat",
    description: "Block until players write something new in chat (or timeout), then return the new messages. Loop it to hold a live conversation: wait → read → reply with minecraft_chat → wait again. With a timeout and nobody talking it is also a clean N-second pause.",
    inputSchema: {
      type: "object",
      properties: {
        since_id: { type: "number", description: "Return events newer than this id (default: now)" },
        timeout_seconds: { type: "number", description: "Max wait, 1–110 (default 45)" },
        from_player: { type: "string", description: "Only wake for messages from this player" },
        mention_only: { type: "boolean", description: "Only wake when a message mentions the bot (its name or an alias from clawdblock.json)" },
      },
    },
  },
  {
    name: "minecraft_get_players",
    description: "List online players with position, dimension, facing direction, health, food and game mode. standingOn = the ground block under their feet (use its y for floors: a floor REPLACES that block, walls start one above).",
    inputSchema: { type: "object", properties: { player: { type: "string", description: "Only this player (optional)" } } },
  },
];

export function handlers(K, ctx) {
  const { events, waiters, fmtEvent, pollLog } = ctx;
  return {
    async minecraft_chat(args) {
      await K.sayAsBot(args.message, args.to_player || "@a");
      if (!args.to_player && args.bubble !== false) await K.bubble(K.BOT, args.message);
      return K.text(`Said in chat${args.to_player ? ` (to ${args.to_player})` : ""}: ${args.message}\nlast chat id: ${ctx.chat.seq}`);
    },

    async minecraft_get_chat(args) {
      pollLog();
      const list = events.filter((e) => e.id > (args.since_id ?? 0)).slice(-(args.limit || 30));
      return K.text(list.length ? list.map(fmtEvent).join("\n") + `\n\nlast id: ${ctx.chat.seq}` : `No new chat. last id: ${ctx.chat.seq}`);
    },

    async minecraft_wait_for_chat(args) {
      pollLog();
      const since = args.since_id ?? ctx.chat.seq;
      const timeout = Math.max(1, Math.min(args.timeout_seconds ?? 45, 110)) * 1000;
      const matches = (e) => {
        if (e.type === "bot") return false;
        if (args.from_player && e.player !== args.from_player) return false;
        if (args.mention_only) return e.type === "chat" && K.mentionRe.test(e.message);
        return e.type === "chat" || e.type === "say" || e.type === "join" || e.type === "leave";
      };
      if (!events.some((e) => e.id > since && matches(e))) {
        await new Promise((resolve) => {
          const w = (e) => { if (matches(e)) setTimeout(finish, 1200); };   // grace period so multi-line bursts arrive together
          const finish = () => { clearTimeout(t); waiters.delete(w); resolve(); };
          const t = setTimeout(finish, timeout);
          waiters.add(w);
        });
      }
      const list = events.filter((e) => e.id > since && e.type !== "bot");
      return K.text(list.length ? list.map(fmtEvent).join("\n") + `\n\nlast id: ${ctx.chat.seq}` : `Nothing new (timeout). last id: ${ctx.chat.seq}`);
    },

    async minecraft_get_players(args) {
      const names = args.player ? [args.player] : (await K.onlinePlayers()).names;
      if (!names.length) return K.text("No players online.");
      const out = [];
      for (const n of names) {
        try { out.push(await K.playerInfo(n)); } catch (e) { out.push({ name: n, error: e.message }); }
      }
      return K.text(out);
    },
  };
}
