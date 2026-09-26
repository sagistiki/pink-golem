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

// Every "N tools" in the docs must match the real number (the README once said 37 while client pages said 33).
import fs from "node:fs";
const docs = [path.join(root, "README.md"), ...fs.readdirSync(path.join(root, "docs"), { recursive: true })
  .filter((f) => f.endsWith(".md")).map((f) => path.join(root, "docs", f))];
const wrong = [];
for (const f of docs)
  fs.readFileSync(f, "utf8").split("\n").forEach((line, i) => {
    for (const m of line.matchAll(/\b(\d+)\*{0,2} (?:MCP )?tools\b/g))
      if (+m[1] !== t.TOOLS.length) wrong.push(`${path.relative(root, f)}:${i + 1} says ${m[1]} tools`);
  });
if (wrong.length) {
  console.error(`tool count: the server has ${t.TOOLS.length} tools, but\n  ${wrong.join("\n  ")}`);
  process.exit(1);
}
console.log(`tool count: every doc says ${t.TOOLS.length}`);
