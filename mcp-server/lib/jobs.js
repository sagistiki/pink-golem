/**
 * jobs — background build jobs with a boss bar everyone sees, the helper crew on site, and the automatic
 * after-build checks (verification, access check, auto-zone). Also runs Python generators.
 */
import fs from "node:fs";
import path from "node:path";

export function install(K, ctx) {
  const st = ctx.state;
  st.jobs = st.jobs || [];
  st.jobSeq = st.jobSeq || 0;

  K.enqueueJob = (job) => {
    job.id = ++st.jobSeq;
    st.jobs.push(job);
    if (st.jobs.length > 20) st.jobs.splice(0, st.jobs.length - 20);
    if (!st.jobRunner) st.jobRunner = runQueue().finally(() => { st.jobRunner = null; });
    return job;
  };
  const runQueue = async () => {
    for (;;) {
      const job = st.jobs.find((j) => j.status === "queued");
      if (!job) return;
      await runJob(job).catch((e) => { job.status = "failed"; job.error = e.message; });
    }
  };
  K.findJob = (id) => st.jobs.find((j) => j.id === Number(id)) || st.jobs[st.jobs.length - 1];
  K.allJobs = () => st.jobs;

  const runJob = async (job) => {
    job.status = "running";
    job.started = Date.now();
    const bar = `pinkgolem:job${job.id}`;
    const name = (pct) => JSON.stringify({ text: `⚒ ${job.label}  ${pct}%`, color: "yellow" });
    await K.cmd(`bossbar remove ${bar}`).catch(() => {});
    await K.cmd(`bossbar add ${bar} ${name(0)}`).catch(() => {});
    for (const c of [`bossbar set ${bar} max ${job.list.length}`, `bossbar set ${bar} color yellow`, `bossbar set ${bar} style notched_10`, `bossbar set ${bar} players @a`, `bossbar set ${bar} value 0`])
      await K.cmd(c).catch(() => {});
    const tIdx = new Map((job.targets.length ? job.targets : job.wt || []).map((t) => [t.i, t]));
    if (job.helpers > 0 && job.box) {
      clearTimeout(st.helperDismissTimer);
      const cx = (job.box[0][0] + job.box[1][0]) / 2, cz = job.box[0][2] - 3;
      const cy = await K.groundAt(cx, cz, job.box[0][1] + 1);
      const r = await K.spawnCrew(job.helpers, [cx, cy, cz]);
      job.helperNames = await K.onlineCrew();
      // builders already on site from an earlier job walk (teleport) to this one instead of leaving and re-spawning
      for (const [i, h] of job.helperNames.entries()) {
        if (r.spawned.includes(h)) continue;
        await K.cmd(`tp ${h} ${(cx + (i - 1) * 2).toFixed(2)} ${cy} ${cz.toFixed(2)}`).catch(() => {});
        await K.cmd(`player ${h} stop`).catch(() => {});
      }
      await K.startWorking(job.helperNames);
      if (r.spawned.length) K.bubble(r.spawned[0], K.crewStartLine(), 3);
    }
    if (job.swing_every) {
      const gm = await K.playerInfo(K.BOT).then((p) => p.gameMode).catch(() => null);
      if (gm === "creative" || gm === "survival") await K.cmd(`gamemode adventure ${K.BOT}`).catch(() => {});
    }
    let lastBar = 0, lastHelper = 0, lastT = null;
    for (let i = 0; i < job.list.length; i++) {
      if (job.cancel) { job.status = "cancelled"; break; }
      let out;
      try { out = await K.cmd(job.list[i]); } catch (e) { out = `ERROR: ${e.message}`; }
      if (K.harmless(out)) job.unchanged = (job.unchanged || 0) + 1;
      else if (out.startsWith("ERROR:") || K.looksLikeError(out)) { job.errors++; if (job.failures.length < 20) job.failures.push(`${job.list[i]} → ${out}`); }
      job.done = i + 1;
      if (tIdx.has(i)) lastT = tIdx.get(i);
      if (job.swing_every && i % job.swing_every === 0) await K.swingNow(K.BOT);
      const now = Date.now();
      if (now - lastBar > 500) {
        lastBar = now;
        await K.cmd(`bossbar set ${bar} value ${job.done}`).catch(() => {});
        await K.cmd(`bossbar set ${bar} name ${name(Math.floor((job.done / job.list.length) * 100))}`).catch(() => {});
      }
      if (lastT && job.helperNames?.length && now - lastHelper > 1300) { lastHelper = now; await K.crewStep(job, lastT).catch(() => {}); }
      if (job.pace) await K.sleep(job.pace);
    }
    if (job.status === "running") {
      job.status = "checking";
      await K.afterBuild(job.list, job.targets, job.label, job, job.verify, job.entrance, job.access_box).catch((e) => { job.verify_error = e.message; });
      job.status = "done";
    }
    job.finished = Date.now();
    const ok = job.status === "done";
    await K.cmd(`bossbar set ${bar} value ${job.done}`).catch(() => {});
    await K.cmd(`bossbar set ${bar} color ${ok ? "green" : "red"}`).catch(() => {});
    await K.cmd(`bossbar set ${bar} name ${JSON.stringify({ text: `${ok ? "✓" : "✖"} ${job.label}`, color: ok ? "green" : "red" })}`).catch(() => {});
    await K.stopWorking(job.helperNames || []);
    setTimeout(() => K.cmd(`bossbar remove ${bar}`).catch(() => {}), 5000).unref?.();
    if (job.helperNames?.length) K.crewIdleTimer(job.keep_helpers);
  };

  /** After every build: check the world matches, optional access check, register it as a protected zone. */
  K.afterBuild = async (list, targets, label, into, doVerify = true, entrance = null, accessBox = null) => {
    if (!targets?.length) return;
    const box = K.unionBox(targets);
    if (entrance) {
      // the whole build = the world-map entry around this job (a last phase alone is often just plants/furniture)
      const e = K.WM.at(K.mapEntries(), K.WM.center({ lo: box[0], hi: box[1] })).find((q) => q.source === "index") || null;
      const ent = entrance === true ? e?.entrances?.[0]?.pos || null : K.V(entrance);
      const base = accessBox || box;
      const bx = e ? [e.lo.map((v, i) => Math.min(v, base[0][i])), e.hi.map((v, i) => Math.max(v, base[1][i]))] : base;
      const a = ent ? await K.checkAccess({ entrance: ent, from: bx[0], to: bx[1] }).catch((q) => ({ error: q.message })) : { error: "no entrance stored in the world map for this area — pass entrance:[x,y,z]" };
      into.access = a.error ? a : { ok: a.ok, reached: a.reached, problems: a.problems.slice(0, 15) };
    }
    if (doVerify !== false) {
      await K.sleep(300);
      const v = await K.verifyBuild(list, box).catch((e) => ({ error: e.message }));
      if (v.checked || v.error) into.verify = v;
    }
    const blocks = targets.reduce((n, t) => n + K.volOf([t.lo, t.hi]), 0);
    const z = await K.autoZone(label, box, blocks).catch(() => null);
    if (z) into.zone = z;
  };

  K.jobView = (j) => ({ id: j.id, label: j.label, status: j.status, done: j.done, total: j.list.length, errors: j.errors, ...(j.unchanged ? { unchanged: `${j.unchanged} (already like that — harmless)` } : {}), failures: j.failures.slice(0, 10),
    seconds: j.started ? +(((j.finished || Date.now()) - j.started) / 1000).toFixed(1) : 0, helpers: j.helperNames || [], undo: j.undo,
    ...(j.verify ? { verify: j.verify } : {}), ...(j.zone ? { zone: j.zone } : {}), ...(j.access ? { access: j.access } : {}), ...(j.verify_error ? { verify_error: j.verify_error } : {}), ...(j.error ? { error: j.error } : {}) });

  /** Run a Python generator (inside the repo). It writes job JSON files into jobs/. */
  K.runGenerator = async (script, argv = []) => {
    const abs = K.safePath(script);
    if (!fs.existsSync(abs)) {
      const bp = path.join(K.P.ROOT, "skill", "pinkgolem", "blueprints");
      const have = fs.existsSync(bp) ? fs.readdirSync(bp).filter((f) => f.endsWith(".py")) : [];
      throw new Error(`no such script: ${script}.` + (have.length ? ` Ready blueprints (skill/pinkgolem/blueprints/): ${have.join(", ")}.` : "")
        + " For anything else write your own generator: pass its Python source in `code` with a script name under jobs/.");
    }
    fs.mkdirSync(K.P.JOBS, { recursive: true });
    const t0 = Date.now() - 1500;
    let r = null;
    const env = { PINKGOLEM_ROOT: K.P.ROOT, PINKGOLEM_JOBS: K.P.JOBS, PINKGOLEM_CU_DATA: K.P.CU_DATA, PYTHONIOENCODING: "utf-8" };
    for (const [k, v] of Object.entries(env)) if (k.startsWith("PINKGOLEM_")) env[k.replace("PINKGOLEM_", "CLAWDBLOCK_")] = v;   // old generators
    for (const py of K.PYTHONS) {
      r = await K.run(py, [abs, ...argv.map(String)], { cwd: path.dirname(abs), timeout: 240000, env });
      if (!(r.err && r.err.code === "ENOENT")) break;
    }
    const files = fs.readdirSync(K.P.JOBS).filter((f) => f.endsWith(".json"))
      .map((f) => ({ f, t: fs.statSync(path.join(K.P.JOBS, f)).mtimeMs })).filter((q) => q.t >= t0)
      .sort((a, b) => a.f.localeCompare(b.f, undefined, { numeric: true })).map((q) => "jobs/" + q.f);
    // build in the order the generator PRINTED its files (site before interior …), not alphabetically
    const said = r.stdout || "";
    const seenAt = (f) => { const i = said.indexOf(f.replace(/^jobs\//, "")); return i < 0 ? Infinity : i; };
    files.sort((a, b) => seenAt(a) - seenAt(b));
    return { ok: !r.err, exit: r.err ? r.err.code ?? r.err.message : 0, stdout: r.stdout.slice(-1500), stderr: r.stderr.slice(-1500), files };
  };
}
