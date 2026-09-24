// Drive the ClawdBlock MCP from a script — for testing tools without an AI client.
//   node test/run.mjs '[["minecraft_status",{}], ["minecraft_bot",{"action":"spawn","pos":[0,-60,0]}]]'
//   node test/run.mjs calls.json            (a file with the same list)
// Every call runs in ONE MCP process (so background jobs and state survive between calls). Images are saved to
// data/screenshots by the tools themselves; this prints the text parts. Env: MC_BOT_NAME etc. work as usual.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const arg = process.argv[2] || "[]";
const calls = JSON.parse(fs.existsSync(arg) ? fs.readFileSync(arg, "utf8") : arg);
const transport = new StdioClientTransport({ command: process.execPath, args: [path.join(here, "..", "index.js")], env: { ...process.env }, stderr: "ignore" });
const client = new Client({ name: "clawdblock-test", version: "1.0.0" });
await client.connect(transport);
let failed = 0;
for (const [name, args] of calls) {
  const t0 = Date.now();
  const r = await client.callTool({ name, arguments: args || {} }, undefined, { timeout: 600000 });
  const texts = (r.content || []).filter((c) => c.type === "text").map((c) => c.text).join("\n");
  const imgs = (r.content || []).filter((c) => c.type === "image").length;
  if (r.isError) failed++;
  console.log(`\n=== ${name} ${JSON.stringify(args || {}).slice(0, 160)}  (${((Date.now() - t0) / 1000).toFixed(1)} s${imgs ? `, ${imgs} image(s)` : ""})${r.isError ? "  ERROR" : ""}`);
  console.log(texts.length > 4000 ? texts.slice(0, 4000) + `\n… (${texts.length} chars)` : texts);
}
await client.close();
process.exit(failed ? 1 : 0);
