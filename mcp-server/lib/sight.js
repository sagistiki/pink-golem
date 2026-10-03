/**
 * sight — pictures and spatial checks: isometric / top / first-person renders of the real world, previews of planned
 * builds (nothing placed), BlueMap photos with real textures (optional), the access check, free-space search, the
 * world map index.
 */
import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";

const CHROMES = [
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
  "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium", "/usr/bin/chromium-browser", "/snap/bin/chromium",
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe", "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
];

export function install(K) {
  const { Render, Sim, AN, WM } = K;
  K.mapEntries = () => WM.mergeIndex(K.readJSON(K.P.INDEX, []), K.loadZones());

  /** What the renderer needs to draw display entities textured: the built server pack (minecraft_pack), else its
   *  parts; the optional client jar setting and the Minecraft version (display.js finds the jar). */
  K.shotOpts = () => {
    const C = K.ctx.config.RAW || {}, rp = C.resource_pack || {};
    const abs = (p) => path.resolve(K.P.ROOT, p);
    const exists = (f) => { try { return fs.statSync(f).isFile(); } catch { return false; } };
    let packs = [abs(rp.output || "data/server-pack.zip")].filter(exists);
    if (!packs.length) {
      let parts = (rp.parts || []).map((p) => (typeof p === "string" ? p : p.path));
      if (!rp.parts) try { parts = fs.readdirSync(abs("resourcepacks")).sort().map((n) => `resourcepacks/${n}/${n}.zip`); } catch {}
      packs = parts.map(abs).filter(exists);
    }
    return { packs, jar: C.client_jar, version: C.mc_version };
  };
  const entityNote = (n, out, top) => (n ? ` ${n} entities: display entities drawn textured like in game (${out.displays ?? 0} drawn)` +
    `${top ? "" : ", others as bright cubes (red = NPC, blue = player, purple = painting; markers and interaction boxes are invisible in game and not drawn)"}.` : "");

  // ── screenshots of the real world
  K.screenshot = async (args) => {
    if (args.fetch) return realShot(args);
    let lo, hi;
    if (args.from && args.to) [lo, hi] = K.sortBox(K.V(args.from), K.V(args.to));
    else {
      let c;
      if (args.pos) c = K.V(args.pos);
      else {
        const p = await K.playerInfo(args.player || (await K.firstRealPlayer()) || K.BOT);
        c = [p.position.x, p.position.y, p.position.z];
      }
      const r = Math.max(4, Math.min(args.radius ?? 16, 40));
      lo = [Math.floor(c[0]) - r, Math.max(-64, Math.floor(c[1]) - 6), Math.floor(c[2]) - r];
      hi = [Math.floor(c[0]) + r, Math.floor(c[1]) + (args.height ?? 24), Math.floor(c[2]) + r];
    }
    const mode = args.mode || "iso";
    if (mode === "real") return realShot(args, lo, hi);
    if (mode === "fpv") return fpvShot(args);
    if (mode === "pov") return K.povShot(args);
    if (args.cut_y != null) hi[1] = Math.min(hi[1], Math.floor(Number(args.cut_y)));   // cutaway: hide everything above
    while (K.volOf([lo, hi]) > 118000 && hi[1] - lo[1] > 8) hi[1]--;
    if (K.volOf([lo, hi]) > 118000) throw new Error(`area too big (${K.volOf([lo, hi])} blocks) — use a smaller box (max ~118k blocks)`);
    const R = await K.dumpRegion(lo, hi);
    const ents = args.entities === false ? [] : await K.entitiesIn(lo, hi).catch(() => []);
    const out = mode === "top" ? Render.renderTop(R, { scale: args.scale, entities: ents, ...K.shotOpts() }) : Render.renderIso(R, { view: args.view || "se", scale: args.scale, entities: ents, ...K.shotOpts() });
    const saved = K.saveShot(args.name || "shot", out.png);
    return { content: [K.img(out.png), { type: "text", text: `${mode === "top" ? "top-down map" : `isometric view from the ${(args.view || "se").toUpperCase()} (camera there, looking across)`} of ${lo.join(",")} → ${hi.join(",")}, ${out.width}x${out.height}px, ${out.scale}px/block.` +
      `${entityNote(ents.length, out, mode === "top")}${args.cut_y != null ? ` Cutaway above y=${hi[1]}.` : ""} Saved as ${saved}` }] };
  };

  const fpvShot = async (args) => {
    let eye, yaw = args.yaw, pitch = args.pitch;
    if (args.pos) eye = K.V(args.pos);
    else {
      const p = await K.playerInfo(args.player || K.BOT);
      eye = [p.position.x, p.position.y + 1.62, p.position.z];
      yaw = yaw ?? p.facing?.yaw ?? 0; pitch = pitch ?? p.facing?.pitch ?? 0;
    }
    const r = Math.max(8, Math.min(args.radius ?? 26, 26));
    const lo = [Math.floor(eye[0]) - r, Math.max(-64, Math.floor(eye[1]) - 18), Math.floor(eye[2]) - r];
    const hi = [Math.floor(eye[0]) + r, Math.floor(eye[1]) + 18, Math.floor(eye[2]) + r];
    while (K.volOf([lo, hi]) > 118000) { lo[0]++; hi[0]--; lo[2]++; hi[2]--; }
    const R = await K.dumpRegion(lo, hi);
    const ents = await K.entitiesIn(lo, hi).catch(() => []);
    const out = Render.renderFPV(R, { eye, yaw: yaw ?? 0, pitch: pitch ?? 0, fov: args.fov || 75, width: args.width || 480, height: args.height || 270, entities: ents, maxDist: r * 1.5, ...K.shotOpts() });
    const saved = K.saveShot(args.name || "fpv", out.png);
    return { content: [K.img(out.png), { type: "text", text: `first-person view from ${eye.map((v) => v.toFixed(1)).join(",")} yaw ${Number(yaw ?? 0).toFixed(0)} pitch ${Number(pitch ?? 0).toFixed(0)} (flat-colour blocks; display entities textured; other entities = bright boxes, red = NPC). Saved as ${saved}` }] };
  };

  /** Far first-person picture of exactly what a player sees + which builds are in view. */
  K.povShot = async (args) => {
    let eye, yaw = args.yaw, pitch = args.pitch, who = null;
    if (args.pos) eye = K.V(args.pos);
    else {
      who = args.player || (await K.firstRealPlayer()) || K.BOT;
      const p = await K.playerInfo(who);
      eye = [p.position.x, p.position.y + 1.62, p.position.z];
      yaw = yaw ?? p.facing?.yaw ?? 0; pitch = pitch ?? p.facing?.pitch ?? 0;
    }
    yaw = Number(yaw ?? 0); pitch = Number(pitch ?? 0);
    const fov = args.fov || 75;
    let dist = Math.max(16, Math.min(args.distance ?? 72, 110));
    let lo, hi;
    for (;;) {
      [lo, hi] = WM.coneBox(eye, yaw, fov, dist, { below: 10, above: Math.max(20, Math.round(-pitch > 20 ? 50 : 30)) });
      if (K.volOf([lo, hi]) <= K.MAX_MULTI || dist <= 16) break;
      dist = Math.floor(dist * 0.85);
    }
    const R = await K.multiRegion(lo, hi);
    const ents = args.entities === false ? [] : await K.entitiesIn(lo, hi).catch(() => []);
    const out = Render.renderFPV(R, { eye, yaw, pitch, fov, width: args.width || 960, height: args.height || 540, entities: ents, maxDist: dist * 1.05, ...K.shotOpts() });
    const f = [-Math.sin((yaw * Math.PI) / 180) * Math.cos((pitch * Math.PI) / 180), -Math.sin((pitch * Math.PI) / 180), Math.cos((yaw * Math.PI) / 180) * Math.cos((pitch * Math.PI) / 180)];
    let target = null;
    for (let t = 0.5; t < dist; t += 0.25) {
      const q = [eye[0] + f[0] * t, eye[1] + f[1] * t, eye[2] + f[2] * t].map(Math.floor);
      const n = R.at(...q);
      if (n && !/^(air|cave_air|light|void_air)$/.test(n) && !/grass$|fern$|vine|lichen/.test(n)) { target = { block: n, pos: q, distance: +t.toFixed(1) }; break; }
    }
    const E = K.mapEntries();
    if (target) { const inb = WM.at(E, target.pos)[0]; if (inb) target.build = inb.name; }
    const inView = WM.inView(E, eye, yaw, fov, Math.max(dist, args.list_distance ?? 150)).slice(0, 12);
    const saved = K.saveShot(`pov-${who || "pos"}`, out.png);
    const dir = WM.compass(f[0] * 100, f[2] * 100);
    return { content: [K.img(out.png), { type: "text", text: JSON.stringify({ view: `${who ? who + "'s" : "the"} eyes at ${eye.map((v) => v.toFixed(1)).join(" ")}, looking ${dir}, yaw ${yaw.toFixed(0)} pitch ${pitch.toFixed(0)}, drawn out to ${dist} blocks (flat-colour blocks, display entities textured)`,
      crosshair: target || "sky / beyond the drawn distance", builds_in_view: inView, saved }, null, 1) }] };
  };

  // ── real textures: BlueMap's web map photographed by headless Chrome/Edge (optional; needs the BlueMap mod)
  const CHROME = CHROMES.find((p) => { try { return fs.existsSync(p); } catch { return false; } });
  const bluemapPort = () => {
    try { const m = /port:\s*(\d+)/.exec(fs.readFileSync(path.join(K.P.SERVER, "config", "bluemap", "webserver.conf"), "utf8")); if (m) return +m[1]; } catch {}
    return 8100;
  };
  const realShot = async (args, lo, hi) => {
    fs.mkdirSync(K.P.SHOTS, { recursive: true });
    const reply = (outFile, url) => {
      const png = fs.readFileSync(outFile);
      return { content: [K.img(png), { type: "text", text: `BlueMap render (real textures) ${url ? url + " " : ""}saved as ${K.rel(outFile)}. BlueMap can lag ~1 min behind fresh builds.` }] };
    };
    if (args.fetch) {
      const f = path.join(K.P.SHOTS, path.basename(String(args.fetch)));
      for (let k = 0; k < 60 && !fs.existsSync(f); k++) await K.sleep(500);
      if (!fs.existsSync(f)) return K.text(`not ready yet: ${path.basename(f)} — try again in a few seconds`);
      return reply(f);
    }
    if (!K.features.bluemap) throw new Error("real screenshots need the BlueMap mod (python3 pinkgolem.py mods add bluemap) — use mode iso/top/pov instead");
    if (!CHROME) throw new Error("Google Chrome or Microsoft Edge was not found on this machine — real screenshots need one of them");
    const c = [(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2];
    const span = Math.max(hi[0] - lo[0], hi[2] - lo[2], 20);
    const dist = args.distance || Math.round(span * 1.05 + 10);
    const rot = { se: 0.785, sw: 2.356, nw: 3.927, ne: 5.498 }[args.view || "se"] ?? 0.785;
    const angle = args.angle ?? 0.9;
    if (args.update) {
      await K.cmd(`bluemap update world ${Math.round(c[0])} ${Math.round(c[2])} ${Math.ceil(span / 2) + 16}`).catch(() => {});
      await K.sleep(Math.min(20, Math.max(3, args.wait_seconds ?? 8)) * 1000);
    }
    const url = args.url || `http://localhost:${bluemapPort()}/#world:${c[0].toFixed(0)}:${c[1].toFixed(0)}:${c[2].toFixed(0)}:${dist}:${rot}:${angle}:0:0:perspective`;
    const png = await chromeShot(url, { W: args.width || 1280, H: args.height || 800, budget: Math.min(args.load_seconds ?? 30, 45), settle: args.settle_seconds ?? 4 });
    const outFile = path.join(K.P.ROOT, K.saveShot(args.name || "real", png.data));
    const res = reply(outFile, url);
    res.content[1].text += ` (${png.note})`;
    return res;
  };
  // Headless Chrome driven over the DevTools protocol: waits until BlueMap has finished loading, then captures.
  const chromeShot = async (url, { W = 1280, H = 800, budget = 30, settle = 4 } = {}) => {
    if (typeof WebSocket === "undefined") throw new Error("this Node has no WebSocket (needs Node 22+) — real screenshots unavailable");
    const prof = path.join(K.tmpdir, `pinkgolem-shot-${process.pid}-${Date.now() % 100000}`);
    const ch = spawn(CHROME, ["--headless=new", `--user-data-dir=${prof}`, "--remote-debugging-port=0", "--no-first-run", "--no-default-browser-check", "--hide-scrollbars", "--mute-audio",
      "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist", `--window-size=${W},${H}`, "about:blank"], { stdio: ["ignore", "ignore", "pipe"] });
    const kill = () => { try { ch.kill("SIGKILL"); } catch {} setTimeout(() => { try { fs.rmSync(prof, { recursive: true, force: true }); } catch {} }, 1500).unref?.(); };
    const hard = setTimeout(kill, (budget + 25) * 1000); hard.unref?.();
    try {
      let errTxt = "";
      const wsUrl = await new Promise((res, rej) => {
        const t = setTimeout(() => rej(new Error("browser did not start: " + errTxt.slice(-300))), 15000);
        ch.stderr.on("data", (d) => { errTxt += d; const m = /DevTools listening on (ws:\/\/\S+)/.exec(errTxt); if (m) { clearTimeout(t); res(m[1]); } });
        ch.on("exit", (c) => { clearTimeout(t); rej(new Error(`browser exited (${c}): ${errTxt.slice(-300)}`)); });
      });
      const ws = new WebSocket(wsUrl);
      await new Promise((res, rej) => { ws.onopen = res; ws.onerror = () => rej(new Error("DevTools websocket failed")); });
      let seq = 0; const pend = new Map();
      ws.onmessage = (ev) => { const m = JSON.parse(ev.data); if (m.id && pend.has(m.id)) { const p = pend.get(m.id); pend.delete(m.id); m.error ? p.rej(new Error(m.error.message)) : p.res(m.result); } };
      const send = (method, params = {}, sessionId) => new Promise((res, rej) => { const id = ++seq; pend.set(id, { res, rej }); ws.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) })); });
      const { targetId } = await send("Target.createTarget", { url: "about:blank" });
      const { sessionId } = await send("Target.attachToTarget", { targetId, flatten: true });
      await send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: 1, mobile: false }, sessionId);
      await send("Page.navigate", { url }, sessionId);
      const t0 = Date.now(); let loadedAt = 0, state = "";
      while (Date.now() - t0 < budget * 1000) {
        await K.sleep(1000);
        const r = await send("Runtime.evaluate", { expression: "document.body ? document.body.innerText.slice(0, 300) : ''", returnByValue: true }, sessionId).catch(() => null);
        state = String(r?.result?.value ?? "");
        if (!/Loading|No map loaded/i.test(state) && state) { if (!loadedAt) loadedAt = Date.now(); if (Date.now() - loadedAt >= settle * 1000) break; }
        else loadedAt = 0;
      }
      const shot = await send("Page.captureScreenshot", { format: "png" }, sessionId);
      try { ws.close(); } catch {}
      const note = loadedAt ? `map loaded after ${((loadedAt - t0) / 1000).toFixed(0)} s` : `map still loading after ${budget} s — page said: ${state.replace(/\s+/g, " ").slice(0, 80)}`;
      return { data: Buffer.from(shot.data, "base64"), note };
    } finally { clearTimeout(hard); kill(); }
  };

  // ── preview: build the commands in a virtual copy of the world and photograph it — nothing is placed
  const flatGround = (x, y, z) => (y < -64 ? null : y === -64 ? "bedrock" : y <= -62 ? "dirt" : y === -61 ? "grass_block" : "air");
  K.previewBuild = async (args) => {
    const list = K.readCommandArgs(args);
    if (!list.length) throw new Error("give commands, commands_file or commands_files");
    const targets = K.targetsFromCommands(list);
    let ground = flatGround, overlayNote = "on empty superflat (overlay:false)";
    if (args.overlay !== false && targets.length) {
      const [l0, h0] = K.unionBox(targets);
      const lo = [l0[0] - 3, Math.max(-64, l0[1] - 2), l0[2] - 3], hi = [h0[0] + 3, h0[1] + 2, h0[2] + 3];
      try {
        if (K.volOf([lo, hi]) > K.MAX_MULTI) throw new Error("too big to read the world under it");
        const W = await K.multiRegion(lo, hi);
        ground = (x, y, z) => W.at(x, y, z) ?? flatGround(x, y, z);
        overlayNote = "on top of the real world (what is there now)";
      } catch (e) { overlayNote = `on empty superflat (${/ECONNREFUSED|not connected|RCON/i.test(e.message) ? "server offline" : e.message})`; }
    }
    const sim = Sim.simulate(list, { ground });
    const R = Sim.regionOf(sim, { margin: args.margin ?? 2, cutY: args.cut_y });
    if (!R) return K.text({ note: "nothing to draw — no fill/setblock/place/summon with absolute coordinates", stats: sim.stats });
    const counts = {};
    for (const [, b] of sim.changed) counts[b] = (counts[b] || 0) + 1;
    const top = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 14).map(([n, c]) => `${n}×${c}`);
    const ents = args.entities === false ? [] : sim.entities;
    const modes = args.mode === "all" ? ["iso", "top"] : [args.mode || "iso"];
    const content = [];
    const names = [];
    for (const m of modes) {
      let out;
      if (m === "top") out = Render.renderTop(R, { scale: args.scale });
      else if (m === "fpv") {
        const eye = args.pos ? K.V(args.pos) : [R.lo[0] - 6, R.lo[1] + 3.6, (R.lo[2] + R.hi[2]) / 2];
        out = Render.renderFPV(R, { eye, yaw: args.yaw ?? -90, pitch: args.pitch ?? 8, fov: args.fov || 75, width: args.width || 640, height: args.height || 360, entities: ents, maxDist: 96 });
      } else out = Render.renderIso(R, { view: args.view || "se", scale: args.scale, entities: ents });
      names.push(K.saveShot(`preview-${args.name || m}`, out.png));
      content.push(K.img(out.png));
    }
    const res = { preview: `${modes.join(" + ")} of the planned build ${overlayNote}. NOTHING was placed.`, box: [R.lo, R.hi], stats: sim.stats, blocks: top, entities: sim.entities.length, saved: names };
    if (args.entrance) res.access = summarizeAccess(AN.accessReport(R, K.V(args.entrance), { minRoom: args.min_room }));
    content.push({ type: "text", text: JSON.stringify(res, null, 1) });
    return { content };
  };

  function summarizeAccess(rep) {
    if (rep.error) return rep;
    const lines = [];
    for (const r of rep.unreachable_rooms) lines.push(`room around ${r.center.join(" ")} (${r.cells} cells, floor y${r.floor_y}${r.contents.length ? ", " + r.contents.slice(0, 3).join(" ") : ""}) — ${r.why}`);
    for (const d of rep.blocked_doors) lines.push(`door ${d.door.join(" ")}: ${d.problems.join("; ")}`);
    for (const s of rep.bad_stairs) lines.push(`stair ${s.stair.join(" ")}: ${s.problem}`);
    for (const j of rep.jump_steps_at_doors) lines.push(`full-block step at a door: ${j.block} at ${j.onto.join(" ")} (a path/floor one block too high?)`);
    if (rep.dark?.spots) lines.push(`${rep.dark.spots} dark spots (mobs can spawn), e.g. ${(rep.dark.examples || []).slice(0, 4).map((p) => p.join(" ")).join(" | ")}`);
    return { ok: rep.ok && !rep.dark?.spots, reached: `${rep.reached_indoor_cells}/${rep.walkable_indoor_cells} indoor floor cells reachable from ${rep.entrance.join(" ")}`,
      problems: lines, closed_empty_spaces: rep.closed_empty_spaces?.length || 0, details: { unreachable_rooms: rep.unreachable_rooms, blocked_doors: rep.blocked_doors, bad_stairs: rep.bad_stairs, jump_steps_at_doors: rep.jump_steps_at_doors } };
  }

  /** Walk (virtually) from an entrance to every room, door and stair of a build. */
  K.checkAccess = async (args) => {
    let box = null, entrance = args.entrance ? K.V(args.entrance) : null, entry = null;
    if (args.build) {
      entry = WM.lookup(K.mapEntries(), args.build)[0];
      if (!entry) throw new Error(`no build called "${args.build}" in the world map (minecraft_map action:list)`);
      box = [entry.lo, entry.hi];
      if (!entrance && entry.entrances?.length) entrance = entry.entrances[0].pos;
    }
    if (args.from && args.to) box = K.sortBox(K.V(args.from), K.V(args.to));
    let list = null;
    if (args.commands || args.commands_file || args.commands_files) { list = K.readCommandArgs(args); const t = K.targetsFromCommands(list); if (!box && t.length) box = K.unionBox(t); }
    if (!entrance && args.player) { const p = await K.playerInfo(args.player); entrance = [p.position.x, p.position.y, p.position.z]; }
    if (!box) throw new Error("which build? give build:<name from the map>, from/to, or the commands file(s)");
    if (!entrance) throw new Error("give entrance:[x,y,z] (feet position just outside the main door) — or add entrances to the map entry");
    const lo = [Math.min(box[0][0], Math.floor(entrance[0])) - 2, Math.max(-64, Math.min(box[0][1], Math.floor(entrance[1]) - 1) - 1), Math.min(box[0][2], Math.floor(entrance[2])) - 2];
    const hi = [Math.max(box[1][0], Math.floor(entrance[0])) + 2, box[1][1] + 3, Math.max(box[1][2], Math.floor(entrance[2])) + 2];
    let R, source;
    if (list && args.simulate) {
      const sim = Sim.simulate(list, {});
      R = { lo, hi, at: (x, y, z) => sim.at(x, y, z) }; source = "simulated from the commands (nothing built)";
    } else { R = await K.multiRegion(lo, hi); source = "the real world"; }
    const rep = AN.accessReport(R, entrance, { box: [[box[0][0], Math.max(-64, box[0][1]), box[0][2]], box[1]], minRoom: args.min_room });
    if (!rep.error && args.dark !== false && !args.simulate) {
      const d = await K.inApp("cu", `dark(${box[0][0]},${Math.max(-63, box[0][1])},${box[0][2]},${box[1][0]},${box[1][1]},${box[1][2]})`).catch(() => "");
      const m = /spots'?\s*(?:->|:)\s*(\d+)/.exec(d);
      const ex = [...String(d).matchAll(/\[(-?\d+), (-?\d+), (-?\d+)\]/g)].map((q) => [+q[1], +q[2], +q[3]]);
      if (m) rep.dark = { spots: +m[1], examples: ex };
    }
    return { build: entry?.name, source, ...summarizeAccess(rep) };
  };

  /** Free rectangles of buildable ground near a place. Flat worlds: grass at the ground level with nothing above.
   *  Normal worlds: natural surface, nothing built on it; each spot reports its height range (level it first). */
  K.findSpace = async (args) => {
    const size = args.size || [args.size_x ?? 20, args.size_z ?? 20];
    const w = Math.max(1, Math.round(size[0])), d = Math.max(1, Math.round(size[1]));
    const E = K.mapEntries();
    let c;
    if (args.near) {
      // "near" a build; small models also pass a player's name or coordinates here — take those too
      const q = String(args.near).trim();
      const e = WM.lookup(E, q)[0];
      const nums = q.match(/-?\d+(\.\d+)?/g);
      const who = !e && (await K.onlinePlayers()).names.find((n) => n.toLowerCase() === q.toLowerCase());
      if (e) c = WM.center(e);
      else if (who) { const p = await K.playerInfo(who); c = [p.position.x, p.position.y, p.position.z]; }
      else if (nums && nums.length >= 3) c = nums.slice(0, 3).map(Number);
      else throw new Error(`no build called "${q}" on the map (builds: ${E.filter((x) => x.lo).map((x) => x.name).slice(0, 12).join(", ") || "none yet"}). Near a player: player:"<name>"; near a spot: pos:[x,y,z].`);
    }
    else if (args.pos) c = K.V(args.pos);
    else { const p = await K.playerInfo(args.player || (await K.firstRealPlayer()) || K.BOT); c = [p.position.x, p.position.y, p.position.z]; }
    const r = Math.max(Math.ceil(Math.max(w, d) / 2) + 8, Math.min(args.radius ?? 90, 120));
    const x0 = Math.floor(c[0]) - r, z0 = Math.floor(c[2]) - r, W = 2 * r + 1, D = 2 * r + 1;
    const natural = "grass_block|dirt|coarse_dirt|podzol|sand|red_sand|gravel|stone|snow_block|mud|moss_block";
    const plants = "short_grass|tall_grass|fern|large_fern|dandelion|poppy|bush|short_dry_grass|tall_dry_grass|pink_petals|wildflowers|leaf_litter|snow";
    // per column: '1' = blocked, else the surface height as base-36 offset (flat worlds: fixed ground level)
    const gy = K.isFlat ? K.flatGroundY : null;
    const expr = gy !== null
      ? `s=[];for(range(${z0},${z0 + D}),z=_;for(range(${x0},${x0 + W}),x=_;g=str(block(x,${gy},z));a=block(x,${gy + 1},z);b=block(x,${gy + 2},z);` +
        `t=g!='grass_block'||!(air(a)||str(a)~'^(${plants})$')||!air(b);s+=if(t,'#','0')));join('',s)`
      : `s=[];for(range(${z0},${z0 + D}),z=_;for(range(${x0},${x0 + W}),x=_;y=top('surface',x,0,z)-1;g=str(block(x,y,z));a=block(x,y+1,z);` +
        `t=!(g~'^(${natural})$')||!(air(a)||str(a)~'^(${plants})$');s+=if(t,'#',slice('0123456789abcdefghijklmnopqrstuvwxyz',(y+64)%36,(y+64)%36+1))));join('',s)`;
    const out = await K.scarpet(expr, { raw: true });
    const v = out.value.replace(/^'|'$/g, "");
    if (v.length !== W * D) throw new Error(`ground scan failed (${v.length} of ${W * D}): ${out.raw.slice(0, 200)}`);
    const grid = new Uint8Array(W * D);
    const hts = new Int16Array(W * D);
    for (let i = 0; i < v.length; i++) { grid[i] = v[i] === "#" ? 1 : 0; hts[i] = grid[i] ? 0 : parseInt(v[i], 36); }
    const margin = args.margin ?? 3;
    // nobody wants a house built on their head: the ground around every player (not the bot or crew) is taken
    for (const n of (await K.onlinePlayers()).names) {
      if (n === K.BOT || (K.isCrew && K.isCrew(n))) continue;
      try {
        const p = (await K.playerInfo(n)).position;
        for (let z = Math.floor(p.z) - 2; z <= Math.floor(p.z) + 2; z++) for (let x = Math.floor(p.x) - 2; x <= Math.floor(p.x) + 2; x++)
          if (x >= x0 && x < x0 + W && z >= z0 && z < z0 + D) grid[(z - z0) * W + (x - x0)] = 1;
      } catch {}
    }
    for (const e of E) if (e.lo) for (let z = Math.max(z0, e.lo[2] - margin); z <= Math.min(z0 + D - 1, e.hi[2] + margin); z++) for (let x = Math.max(x0, e.lo[0] - margin); x <= Math.min(x0 + W - 1, e.hi[0] + margin); x++) grid[(z - z0) * W + (x - x0)] = 1;
    const free = AN.findFreeRects(grid, W, D, x0, z0, w, d, 0, [c[0], c[2]], { count: args.count ?? 3 });
    const taken = grid.reduce((a, b) => a + b, 0);
    return { searched: `${W}x${D} around ${c.map(Math.round).join(" ")}`, want: `${w}x${d} + ${margin} margin`, occupied_fraction: +(taken / grid.length).toFixed(2),
      spots: free.map((f) => {
        const m = [(f.from[0] + f.to[0]) / 2, (f.from[1] + f.to[1]) / 2];
        let ground = gy;
        let range = null;
        if (gy === null) {
          let lo = 999, hi = -999;
          for (let z = f.from[1]; z <= f.to[1]; z++) for (let x = f.from[0]; x <= f.to[0]; x++) { const q = hts[(z - z0) * W + (x - x0)]; lo = Math.min(lo, q); hi = Math.max(hi, q); }
          range = [lo, hi]; ground = null;
        }
        const nb = WM.near(E, { lo: [f.from[0], -64, f.from[1]], hi: [f.to[0], 320, f.to[1]] }, 25).slice(0, 3);
        return { from: [f.from[0], ground, f.from[1]], to: [f.to[0], ground, f.to[1]], rotated: f.rotated, distance: Math.round(f.dist), direction: WM.compass(m[0] - c[0], m[1] - c[2]),
          ...(range ? { surface_varies: `${range[1] - range[0]} blocks (check heights with ytop and level the site first)` } : {}), neighbours: nb.map((n) => `${n.name} (${n.gap} ${n.direction})`) };
      }),
      note: free.length ? (gy !== null ? `floor at y ${gy} (replace the grass), walls from ${gy + 1}` : "normal terrain: read the surface with `script in cu run ytop(x,z)` and level the site before building") : "no free spot that size — try a bigger radius or a smaller size" };
  };
}
