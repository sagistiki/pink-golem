/**
 * The server resource pack in one call: minecraft_pack build (merge + validate) · deploy (host under a NEW url,
 * server.properties, live push with the Key Bridge mod's /packpush) · status (deployed vs built).
 *
 * Configuration: "resource_pack" in pinkgolem.json (all optional):
 *   {
 *     "parts": [{"path": "server/polymer/resource_pack.zip", "generated": true},   // merged in order, first wins;
 *               "resourcepacks/minimap/minimap.zip"],                          // generated = a mod makes it: problems don't block
 *     "output": "data/server-pack.zip",
 *     "extra_outputs": [{"path": "server/world/resources.zip", "exclude": ["server/polymer/resource_pack.zip"]}],
 *     "merge_json": true,                         // fonts/atlases/lang/sounds.json from several parts are merged
 *     "upload": {"hosts": ["mcpacks", "catbox"]},  // the default: free public pack hosts, tried in order, ONE try each
 *     "upload": {"command": ["my-upload", "{file}"]},   // or your own uploader (prints the public URL), or:
 *     "publish_dir": "/var/www/packs", "public_url": "https://example.org/packs"   // copy there under a new name
 *   }
 * Without "parts": every resourcepacks/<name>/<name>.zip. "upload": {"hosts": []} turns the public hosts off (then
 * deploy needs url:'<where you put it>'). The old "upload_command" still works (= upload.command).
 * Pure zip/validation helpers: lib/devkit.js. Guide: skill/pinkgolem/reference/testing-apps.md
 */
import fs from "node:fs";
import path from "node:path";

export const tools = [
  {
    name: "minecraft_pack",
    description: "The server resource pack in one call (parts from pinkgolem.json resource_pack.parts, default every resourcepacks/<name>/<name>.zip; missing parts are skipped with a warning; problems inside a part marked generated:true — one a mod makes, like Polymer's — are warnings, not blockers). action: build (merge parts — first wins on a clash, font/atlas/lang/sounds JSON merged — validate JSON, models (parents, textures, atlas-generated sprites), item definitions, fonts, sounds; report clashes, size, sha1; writes the output + extra outputs; check_only:true writes nothing; output:'path' builds elsewhere) | deploy (build → put it under a NEW url: the pack hosts in resource_pack.upload.hosts, in order, ONE try each (default mcpacks.dev, then catbox.moe), the first copy that downloads with the right sha1 wins — or your upload.command, or publish_dir + public_url, or url:'…' you uploaded yourself → back up + update server.properties → live push with /packpush when the Key Bridge mod is installed, else 'restart needed'; the reply names the host and hosts_tried; dry_run:true shows the plan and changes nothing) | status (deployed vs built, stale parts, last deploy, /packpush available; check_url:true downloads the deployed url and checks its sha1). Never overwrite a file clients may be downloading: every deploy gets a new url.",
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
    if (!parts.length) throw new Error("no pack parts found — set resource_pack.parts in pinkgolem.json, or put packs in resourcepacks/<name>/<name>.zip");
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
  /** Public pack hosts, tried in order (resource_pack.upload.hosts). Each upload gets a NEW url; the copy must download
   *  with the right sha1 or the next host is tried. ONE attempt per host per deploy: never loop uploads — retry loops
   *  look like bot spam to a free host (and one host started storing 0-byte files, which only the sha1 check catches). */
  const PACK_HOSTS = {
    // mcpacks.dev: a free Minecraft resource-pack host, no account, packs kept while people download them. A
    // Laravel/Inertia form: GET / for the XSRF + session cookies, POST /upload (resource_pack, consent) → 302
    // /pack/<uuid>; the pack is at /pack/<uuid>/download (302 to https object storage, which the game client follows).
    async mcpacks(buf, name) {
      const home = await fetch("https://mcpacks.dev/", { signal: AbortSignal.timeout(30000) });
      const html = await home.text();
      const cookies = (home.headers.getSetCookie?.() || []).map((c) => c.split(";")[0]);
      const xs = cookies.find((c) => c.startsWith("XSRF-TOKEN="));
      if (!xs) throw new Error("mcpacks: no XSRF cookie");
      const ver = (html.match(/version&quot;:&quot;([a-f0-9]+)/) || [])[1] || "";   // the page's data-page JSON
      const fd = new FormData();
      fd.append("resource_pack", new Blob([buf], { type: "application/zip" }), name);
      fd.append("consent", "1");
      const r = await fetch("https://mcpacks.dev/upload", { method: "POST", body: fd, redirect: "manual", signal: AbortSignal.timeout(600000),
        headers: { Cookie: cookies.join("; "), "X-XSRF-TOKEN": decodeURIComponent(xs.slice("XSRF-TOKEN=".length)),
          "X-Requested-With": "XMLHttpRequest", "X-Inertia": "true", "X-Inertia-Version": ver, Accept: "text/html, application/xhtml+xml" } });
      const loc = r.headers.get("location") || "";
      const m = loc.match(/^https:\/\/mcpacks\.dev\/pack\/([0-9a-f-]{36})$/);
      if (!m) throw new Error(`mcpacks: upload gave HTTP ${r.status} location "${loc.slice(0, 120)}"`);
      return `https://mcpacks.dev/pack/${m[1]}/download`;
    },
    // catbox.moe: a free file host (anonymous uploads)
    async catbox(buf, name) {
      const fd = new FormData();
      fd.append("reqtype", "fileupload");
      fd.append("fileToUpload", new Blob([buf], { type: "application/zip" }), name);
      const r = await fetch("https://catbox.moe/user/api.php", { method: "POST", body: fd, signal: AbortSignal.timeout(180000) });
      const t = (await r.text()).trim();
      if (!r.ok || !/^https:\/\/files\.catbox\.moe\/[\w.-]+$/.test(t)) throw new Error(`catbox: upload failed (HTTP ${r.status}): ${t.slice(0, 200)}`);
      return t;
    },
  };
  const uploadOf = (cfg) => {
    const up = { ...(cfg.upload || {}) };
    if (!up.command && cfg.upload_command) up.command = cfg.upload_command;    // the older top-level setting
    if (!up.hosts) up.hosts = up.service ? [up.service] : cfg.publish_dir && cfg.public_url ? [] : ["mcpacks", "catbox"];
    return up;
  };
  const howHosted = (cfg) => {
    const up = uploadOf(cfg);
    if (up.command) return "your upload command";
    if (cfg.publish_dir && cfg.public_url) return `a copy in ${cfg.publish_dir}`;
    return up.hosts.length ? `${up.hosts.join(" → then ")} (one try each)` : null;
  };
  /** A NEW public url for the file → { url, host, verified, tried }: your upload command, a copy in publish_dir, or the
   *  first pack host whose copy downloads with the right sha1. */
  async function host(file, sha, cfg) {
    const up = uploadOf(cfg);
    if (up.command) {
      const argv = up.command.map((s) => s.replace("{file}", file));
      const r = await K.run(argv[0], argv.slice(1), { timeout: 180000 });
      const url = (r.stdout.match(/https?:\/\/\S+/g) || []).pop();
      if (!url) throw new Error(`the upload command printed no URL: ${(r.stderr || r.stdout).slice(0, 300)}`);
      return { url, host: "command", verified: false, tried: [] };
    }
    if (cfg.publish_dir && cfg.public_url) {
      const name = `pack-${sha.slice(0, 12)}-${Date.now().toString(36)}.zip`;
      fs.mkdirSync(cfg.publish_dir, { recursive: true });
      fs.copyFileSync(file, path.join(cfg.publish_dir, name));
      return { url: cfg.public_url.replace(/\/+$/, "") + "/" + name, host: "publish_dir", verified: false, tried: [] };
    }
    if (!up.hosts.length) throw new Error("no way to publish the pack: resource_pack.upload.hosts is empty — set upload.hosts, upload.command or publish_dir + public_url in pinkgolem.json, or upload it yourself and call deploy with url:'…'");
    const buf = fs.readFileSync(file);
    const name = `pack-${sha.slice(0, 10)}.zip`;
    const tried = [];
    for (const h of up.hosts) {
      if (!PACK_HOSTS[h]) { tried.push(`${h}: unknown host (known: ${Object.keys(PACK_HOSTS).join(", ")})`); continue; }
      try {
        const url = await PACK_HOSTS[h](buf, name);
        let ok = false, why = "";
        for (let k = 0; k < 3 && !ok; k++) {                     // download again (never upload again): a CDN can lag a few seconds
          try { const b = await download(url); ok = D.sha1(b) === sha; if (!ok) why = `downloads ${b.length} bytes with another sha1`; } catch (e) { why = e.message; }
          if (!ok && k < 2) await K.sleep(4000);
        }
        tried.push(`${h}: ${ok ? "ok" : "bad copy (" + why + ")"} ${url}`);
        if (ok) return { url, host: h, verified: true, tried };
      } catch (e) { tried.push(`${h}: ${e.message}`); }
    }
    throw new Error(`no pack host gave a good copy — ${tried.join(" | ")}`);
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
    const how = args.url ? "the url you gave" : howHosted(cfg) || "NOTHING: upload.hosts is empty — pass url:'…'";
    if (dry) return { ...res, keybridge: kb, plan: [
      `put ${cfg.output} (${b?.size_mb ?? "?"} MB) under a NEW url via ${how}; download it back and compare the sha1 (a bad copy → the next host)`,
      `back up server.properties → ${backup}`, `server.properties: resource-pack=<NEW-URL>  resource-pack-sha1=${sha}`,
      kb.available ? `live: /packpush <NEW-URL> ${sha} → everyone online gets it now; later joins get it at login` : "no /packpush (the Key Bridge mod is not installed) → players get the pack after the next restart",
      `record the deploy in ${K.rel(STATE)}`] };
    const up = args.url ? null : await host(out, sha, cfg);
    const url = args.url || up.url;
    let verified = !!up?.verified;
    for (let k = 0; k < 3 && !verified; k++) { try { verified = D.sha1(await download(url)) === sha; } catch {} if (!verified) await K.sleep(2000); }
    if (!verified && !args.force) return { ...res, url, ...(up ? { host: up.host } : {}), refused: "the url does not serve a file with this sha1 (yet) — server.properties NOT changed (retry with url:<that url>, or force:true)" };
    fs.copyFileSync(PROPS, path.join(K.P.SERVER, backup));
    writeAtomic(PROPS, setProps({ "resource-pack": url, "resource-pack-sha1": sha }));
    let live = "restart needed: server.properties points to the new pack; players get it when they join after the restart";
    if (kb.available) live = (await K.cmd(`packpush ${url} ${sha}${cur.prompt && !/^\s*[{\[]/.test(cur.prompt) ? " " + cur.prompt : ""}`)).trim();
    saveState((s) => { (s.deploys ||= []).unshift({ time: new Date().toISOString(), url, sha1: sha, ...(up ? { host: up.host } : {}), previous: cur.url, backup, live }); s.deploys = s.deploys.slice(0, 20); });
    return { ...res, url, ...(up ? { host: up.host, hosts_tried: up.tried } : {}), verified_download: verified, backup, server_properties: { "resource-pack": url, "resource-pack-sha1": sha }, live };
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
