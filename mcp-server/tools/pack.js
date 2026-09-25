/**
 * The server resource pack in one call: minecraft_pack build (merge + validate) · deploy (host under a NEW url,
 * server.properties, live push with the Key Bridge mod's /packpush) · status (deployed vs built).
 *
 * Configuration: "resource_pack" in clawdblock.json (all optional):
 *   {
 *     "parts": [{"path": "server/polymer/resource_pack.zip", "generated": true},   // merged in order, first wins;
 *               "resourcepacks/minimap/minimap.zip"],                          // generated = a mod makes it: problems don't block
 *     "output": "data/server-pack.zip",
 *     "extra_outputs": [{"path": "server/world/resources.zip", "exclude": ["server/polymer/resource_pack.zip"]}],
 *     "merge_json": true,                         // fonts/atlases/lang/sounds.json from several parts are merged
 *     "upload_command": ["my-upload", "{file}"],  // prints the public URL of the uploaded file, or:
 *     "publish_dir": "/var/www/packs", "public_url": "https://example.org/packs"   // copy there under a new name
 *   }
 * Without "parts": every resourcepacks/<name>/<name>.zip. Without an upload setting: deploy with url:'<where you put it>'.
 * Pure zip/validation helpers: lib/devkit.js. Guide: skill/clawdblock/reference/testing-apps.md
 */
import fs from "node:fs";
import path from "node:path";

export const tools = [
  {
    name: "minecraft_pack",
    description: "The server resource pack in one call (parts from clawdblock.json resource_pack.parts, default every resourcepacks/<name>/<name>.zip; missing parts are skipped with a warning; problems inside a part marked generated:true — one a mod makes, like Polymer's — are warnings, not blockers). action: build (merge parts — first wins on a clash, font/atlas/lang/sounds JSON merged — validate JSON, models (parents, textures, atlas-generated sprites), item definitions, fonts, sounds; report clashes, size, sha1; writes the output + extra outputs; check_only:true writes nothing; output:'path' builds elsewhere) | deploy (build → put it under a NEW url (upload_command, or publish_dir + public_url, or url:'…' you uploaded yourself) → download check → back up + update server.properties → live push with /packpush when the Key Bridge mod is installed, else 'restart needed'; dry_run:true shows the plan and changes nothing) | status (deployed vs built, stale parts, last deploy, /packpush available; check_url:true downloads the deployed url and checks its sha1). Never overwrite a file clients may be downloading: every deploy gets a new url.",
    inputSchema: { type: "object", properties: {
      action: { type: "string", enum: ["build", "deploy", "status"] }, dry_run: { type: "boolean" }, check_only: { type: "boolean" }, output: { type: "string" },
      url: { type: "string" }, force: { type: "boolean" }, skip_build: { type: "boolean" }, check_url: { type: "boolean" },
    }, required: ["action"] },
  },
];

export function handlers(K, ctx) {
  const D = K.devkit;
  const bool = (v, d) => (v === undefined ? d : v === true || v === "true");
  const STATE = path.join(K.P.DATA, "pack-state.json");
  const PROPS = path.join(K.P.SERVER, "server.properties");

  function config() {
    const c = { ...((ctx.config.RAW || {}).resource_pack || {}) };
    if (!c.parts) {
      const dir = path.join(K.P.ROOT, "resourcepacks");
      let names = [];
      try { names = fs.readdirSync(dir).filter((n) => fs.existsSync(path.join(dir, n, `${n}.zip`))).sort(); } catch {}
      c.parts = names.map((n) => `resourcepacks/${n}/${n}.zip`);
    }
    c.parts = c.parts.map((p) => (typeof p === "string" ? { path: p } : p));
    c.output ||= "data/server-pack.zip";
    c.extra_outputs ||= [];
    return c;
  }
  const state = () => K.readJSON(STATE, {});
  const saveState = (fn) => { const s = state(); fn(s); fs.mkdirSync(path.dirname(STATE), { recursive: true }); fs.writeFileSync(STATE, JSON.stringify(s, null, 2)); };
  const writeAtomic = (f, b) => { fs.mkdirSync(path.dirname(f), { recursive: true }); fs.writeFileSync(f + ".tmp", b); fs.renameSync(f + ".tmp", f); };
  const props = () => {
    const o = {};
    try { for (const l of fs.readFileSync(PROPS, "utf8").split(/\r?\n/)) { const i = l.indexOf("="); if (i > 0 && !l.startsWith("#")) o[l.slice(0, i).trim()] = l.slice(i + 1).trim().replace(/\\(.)/g, "$1"); } } catch {}
    return o;
  };

  function build(args) {
    const cfg = config();
    const warnings = [], used = [], parts = [];
    for (const p of cfg.parts) {
      const f = K.safePath(p.path);
      if (!fs.existsSync(f)) { warnings.push(`missing part skipped: ${p.path}${p.note ? " (" + p.note + ")" : ""}`); continue; }
      const buf = fs.readFileSync(f);
      parts.push({ name: p.path, buf });
      used.push({ path: p.path, size: buf.length, sha1: D.sha1(buf) });
    }
    if (!parts.length) throw new Error("no pack parts found — set resource_pack.parts in clawdblock.json, or put packs in resourcepacks/<name>/<name>.zip");
    const m = D.mergePacks(parts, { mergeJson: cfg.merge_json !== false });
    const v = D.validatePack(m.files);
    // a part a mod generates (e.g. Polymer's own pack) works in game even when a check here fails: report, don't block
    const gen = new Set(cfg.parts.filter((p) => p.generated).map((p) => p.path));
    for (const pr of v.problems) if (pr.level === "error" && pr.from && pr.from.split("+").every((f) => gen.has(f))) { pr.level = "warning"; pr.message += " (generated part — not blocking)"; }
    const errors = v.problems.filter((p) => p.level === "error");
    const zip = D.writeZip([...m.files].map(([name, f]) => ({ name, data: f.data })));
    const out = K.safePath(args.output || cfg.output);
    const res = {
      output: K.rel(out), size: zip.length, size_mb: +(zip.length / 1048576).toFixed(2), sha1: D.sha1(zip), files: m.files.size, pack_format: v.format,
      parts: used.map((p) => `${p.path} (${(p.size / 1024).toFixed(0)} KB)`), warnings, stats: v.stats,
      clashes: m.clashes.slice(0, 40), ...(m.clashes.length > 40 ? { clashes_more: m.clashes.length - 40 } : {}), merged_json: m.merged, identical_duplicates: m.identical.length,
      problems: v.problems.slice(0, 60).map((p) => `${p.level.toUpperCase()} ${p.path}${p.from ? " [" + p.from + "]" : ""}: ${p.message}`), ...(v.problems.length > 60 ? { problems_more: v.problems.length - 60 } : {}),
    };
    if (errors.length && !args.force) return { ...res, written: false, refused: `${errors.length} error(s) in the merged pack — nothing written (force:true writes anyway)` };
    if (args.check_only) return { ...res, written: false };
    writeAtomic(out, zip);
    res.written = true;
    res.extra_outputs = [];
    for (const x of args.output ? [] : cfg.extra_outputs) {
      const sub = parts.filter((p) => !(x.exclude || []).includes(p.name));
      if (!sub.length) continue;
      const mx = D.mergePacks(sub, { mergeJson: cfg.merge_json !== false });
      const zx = D.writeZip([...mx.files].map(([name, f]) => ({ name, data: f.data })));
      writeAtomic(K.safePath(x.path), zx);
      res.extra_outputs.push(`${x.path} (${(zx.length / 1024).toFixed(0)} KB, from ${sub.map((p) => p.name).join(" + ")})`);
    }
    if (!args.output) saveState((s) => { s.build = { time: new Date().toISOString(), output: res.output, sha1: res.sha1, size: res.size, parts: used }; });
    return res;
  }

  const deployed = () => { const p = props(); return { url: p["resource-pack"] || "", sha1: (p["resource-pack-sha1"] || "").toLowerCase(), required: p["require-resource-pack"] === "true", prompt: p["resource-pack-prompt"] || "" }; };
  async function keybridge() {
    const out = await K.cmd("packpush").catch((e) => e.message);
    return { available: !/Unknown or incomplete command|Unknown command/i.test(out), output: out.trim().slice(0, 300) };
  }
  async function download(url) {
    const r = await fetch(url, { signal: AbortSignal.timeout(60000), redirect: "follow" });
    if (!r.ok) throw new Error(`GET ${url}: HTTP ${r.status}`);
    return Buffer.from(await r.arrayBuffer());
  }
  /** A NEW public url for the file: the configured upload command, or a copy in publish_dir under a new name. */
  async function host(file, sha, cfg) {
    if (cfg.upload_command) {
      const argv = cfg.upload_command.map((s) => s.replace("{file}", file));
      const r = await K.run(argv[0], argv.slice(1), { timeout: 180000 });
      const url = (r.stdout.match(/https?:\/\/\S+/g) || []).pop();
      if (!url) throw new Error(`upload_command printed no URL: ${(r.stderr || r.stdout).slice(0, 300)}`);
      return url;
    }
    if (cfg.publish_dir && cfg.public_url) {
      const name = `pack-${sha.slice(0, 12)}-${Date.now().toString(36)}.zip`;
      fs.mkdirSync(cfg.publish_dir, { recursive: true });
      fs.copyFileSync(file, path.join(cfg.publish_dir, name));
      return cfg.public_url.replace(/\/+$/, "") + "/" + name;
    }
    throw new Error("no way to publish the pack: set resource_pack.upload_command or publish_dir + public_url in clawdblock.json, or upload it yourself and call deploy with url:'…'");
  }
  function setProps(kv) {
    const lines = fs.readFileSync(PROPS, "utf8").split(/\r?\n/);
    const esc = (v) => String(v).replace(/\\/g, "\\\\").replace(/:/g, "\\:").replace(/=/g, "\\=");
    for (const [k, v] of Object.entries(kv)) {
      const i = lines.findIndex((l) => l.startsWith(k + "="));
      if (i >= 0) lines[i] = `${k}=${esc(v)}`; else lines.splice(lines.length - (lines[lines.length - 1] === "" ? 1 : 0), 0, `${k}=${esc(v)}`);
    }
    return lines.join("\n");
  }

  async function deploy(args) {
    const cfg = config();
    const dry = bool(args.dry_run, false);
    const b = args.skip_build ? null : build({ ...args, check_only: dry });
    if (b?.refused) return { refused: b.refused, build: b };
    const out = K.safePath(cfg.output);
    if (!dry && !fs.existsSync(out)) throw new Error(`${cfg.output} does not exist — build first`);
    const sha = b?.sha1 || D.sha1(fs.readFileSync(out));
    const cur = deployed();
    const res = { dry_run: dry, build: b ? { sha1: b.sha1, size_mb: b.size_mb, files: b.files, warnings: b.warnings, problems: b.problems.length, clashes: b.clashes.length } : "skipped", deployed_before: cur };
    if (cur.sha1 === sha && !args.force) return { ...res, note: "this exact pack is already deployed (same sha1) — nothing to do (force:true redeploys)" };
    const kb = await keybridge();
    const d = new Date(), z = (n) => String(n).padStart(2, "0");
    const backup = `server.properties.bak-pack-${d.getFullYear()}${z(d.getMonth() + 1)}${z(d.getDate())}-${z(d.getHours())}${z(d.getMinutes())}${z(d.getSeconds())}`;
    const how = args.url ? "the url you gave" : cfg.upload_command ? "upload_command" : cfg.publish_dir ? `a copy in ${cfg.publish_dir}` : "NOTHING CONFIGURED — pass url:'…'";
    if (dry) return { ...res, keybridge: kb, plan: [
      `host ${cfg.output} (${b?.size_mb ?? "?"} MB) under a NEW url via ${how}; download it back and compare the sha1`,
      `back up server.properties → ${backup}`, `server.properties: resource-pack=<NEW-URL>  resource-pack-sha1=${sha}`,
      kb.available ? `live: /packpush <NEW-URL> ${sha} → everyone online gets it now; later joins get it at login` : "no /packpush (the Key Bridge mod is not installed) → players get the pack after the next restart",
      `record the deploy in ${K.rel(STATE)}`] };
    const url = args.url || (await host(out, sha, cfg));
    let verified = false;
    for (let k = 0; k < 3 && !verified; k++) { try { verified = D.sha1(await download(url)) === sha; } catch {} if (!verified) await K.sleep(2000); }
    if (!verified && !args.force) return { ...res, url, refused: "the url does not serve a file with this sha1 (yet) — server.properties NOT changed (retry with url:<that url>, or force:true)" };
    fs.copyFileSync(PROPS, path.join(K.P.SERVER, backup));
    writeAtomic(PROPS, setProps({ "resource-pack": url, "resource-pack-sha1": sha }));
    let live = "restart needed: server.properties points to the new pack; players get it when they join after the restart";
    if (kb.available) live = (await K.cmd(`packpush ${url} ${sha}${cur.prompt && !/^\s*[{\[]/.test(cur.prompt) ? " " + cur.prompt : ""}`)).trim();
    saveState((s) => { (s.deploys ||= []).unshift({ time: new Date().toISOString(), url, sha1: sha, previous: cur.url, backup, live }); s.deploys = s.deploys.slice(0, 20); });
    return { ...res, url, verified_download: verified, backup, server_properties: { "resource-pack": url, "resource-pack-sha1": sha }, live };
  }

  async function status(args) {
    const cfg = config(), st = state(), cur = deployed();
    const out = K.safePath(cfg.output);
    let built = null;
    if (fs.existsSync(out)) { const buf = fs.readFileSync(out); built = { path: cfg.output, sha1: D.sha1(buf), size_mb: +(buf.length / 1048576).toFixed(2), time: new Date(fs.statSync(out).mtimeMs).toISOString() }; }
    const parts = cfg.parts.map((p) => {
      const f = K.safePath(p.path);
      if (!fs.existsSync(f)) return { path: p.path, exists: false };
      const buf = fs.readFileSync(f), rec = st.build?.parts?.find((x) => x.path === p.path);
      const changed = rec ? rec.sha1 !== D.sha1(buf) : built ? fs.statSync(f).mtimeMs > fs.statSync(out).mtimeMs : true;
      return { path: p.path, exists: true, size_kb: Math.round(buf.length / 1024), changed_since_build: changed };
    });
    const res = { deployed: cur, built, built_is_deployed: !!built && built.sha1 === cur.sha1, build_is_stale: parts.some((p) => p.exists && p.changed_since_build), parts, last_deploy: st.deploys?.[0] || null, keybridge: await keybridge() };
    if (args.check_url && cur.url) { try { const b = await download(cur.url); res.deployed_url_check = D.sha1(b) === cur.sha1 ? "ok: the url serves the configured sha1" : `MISMATCH: the url serves ${D.sha1(b)}`; } catch (e) { res.deployed_url_check = `download failed: ${e.message}`; } }
    return res;
  }

  return {
    minecraft_pack: async (args) => {
      args = { ...args };
      for (const k of ["check_only", "skip_build", "check_url", "dry_run", "force"]) if (args[k] === "true" || args[k] === "false") args[k] = args[k] === "true";
      if (args.action === "build") return K.text(build(args));
      if (args.action === "deploy") return K.text(await deploy(args));
      if (args.action === "status") return K.text(await status(args));
      throw new Error("action: build | deploy | status");
    },
  };
}
