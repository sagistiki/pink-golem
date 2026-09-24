// Loads the whole tool layer against a fake server context and lists the tools — catches syntax and wiring errors
// without a Minecraft server. Run: npm run check
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..", "..");
const ctx = {
  cmd: async () => "", looksLikeError: () => false, rconConfig: () => ({ host: "127.0.0.1", port: 25575, password: "x", enabled: true }),
  readProps: () => ({ "level-name": "world", "level-type": "minecraft:flat" }), pushEvent() {}, pollLog() {}, events: [], waiters: new Set(),
  fmtEvent: (e) => String(e), log: (...a) => console.error(...a),
  config: { ROOT: root, SERVER_DIR: path.join(root, "server"), BOT_NAME: "Claude", CHAT_COLOR: "light_purple", BOT_ALIASES: ["Claude", "claude"], CREW: {}, MAX_FILL_VOLUME: 32768, LOG_FILE: "", PROPS_FILE: "" },
  state: {}, chat: { seq: 0 },
};
const mod = await import(pathToFileURL(path.join(here, "..", "tools", "index.js")).href + "?v=test");
const t = await mod.create(ctx);
console.log(`${t.TOOLS.length} tools: ${t.TOOLS.map((x) => x.name.replace("minecraft_", "")).join(", ")}`);
const r = await t.handle("minecraft_notes", { action: "read" });
console.log("notes:", r.content[0].text.slice(0, 80));
