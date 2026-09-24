/**
 * features — which mods the server has, read from the server's mods/ folder (when the MCP runs next to the server).
 * Tools that need a missing mod are hidden from the tool list; minecraft_status says what to install.
 */
import fs from "node:fs";
import path from "node:path";

const MODS = {
  carpet: /^fabric-carpet/i,   // not carpet-extra
  worldedit: /^worldedit/i,
  bluemap: /^bluemap/i,
  polydecorations: /^polydecorations/i,
  essential_commands: /^essential[_-]commands/i,
  chunky: /^chunky/i,
  spark: /^spark/i,
  lithium: /^lithium/i,
  ledger: /^ledger/i,
};

export function install(K) {
  const dir = path.join(K.P.SERVER, "mods");
  let jars = null;
  try { jars = fs.readdirSync(dir).filter((f) => f.endsWith(".jar")); } catch {}
  const f = { known: jars !== null, jars: jars || [] };
  for (const [k, re] of Object.entries(MODS)) f[k] = jars === null ? true : jars.some((j) => re.test(j));
  K.features = f;
  /** Mods a tool needs that are missing (empty when the mods folder can't be read: then everything is offered). */
  K.missing = (requires = []) => (f.known ? requires.filter((r) => !f[r]) : []);
}
