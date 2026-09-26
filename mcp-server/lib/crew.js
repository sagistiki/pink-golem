/**
 * crew — the helper builders: Carpet fake players in hard hats and hi-vis vests that work around a build site,
 * swing for real (helpers.sc) and chat now and then. Names and lines come from pinkgolem.json "crew".
 * Also: speech bubbles above anyone's head (bubble.sc).
 */

const DEFAULT_NAMES = ["Alex_Builder", "Sam_Builder", "Riley_Builder", "Jordan_Builder"];
const DEFAULT_LINES = ["One more block!", "Who ordered the concrete?", "This is looking great!", "Coffee break in five", "Almost there, team!",
  "Careful, working up here!", "Where did I put my level?", "Is this straight?", "Last layer and we're done", "Measure twice, place once"];
const DEFAULT_ARRIVE = ["We're here! What are we building?", "Crew reporting for duty!"];
const DEFAULT_START = ["Alright team, let's go!", "Hard hats on!"];
const DEFAULT_LEAVE = ["Heading home!", "Done here, bye!", "Good job everyone!"];
const TOOLS = ["iron_shovel", "iron_pickaxe", "brick", "iron_axe", "stone_bricks"];
const pick = (a) => a[Math.floor(Math.random() * a.length)];

export function install(K, ctx) {
  const cfg = ctx.config.CREW || {};
  const NAMES = (cfg.names?.length ? cfg.names : DEFAULT_NAMES).slice(0, 4);
  const LINES = cfg.lines?.length ? cfg.lines : DEFAULT_LINES;
  K.CREW_NAMES = NAMES;
  const st = ctx.state;

  // ── speech bubbles (bubble.sc)
  K.bubble = async (name, message, secs) => {
    const t = K.stripBotPrefix(message);
    if (!t) return;
    const s = secs ?? Math.max(3, Math.min(10, 2 + t.length / 12));
    await K.inApp("bubble", `say('${name}', ${K.scStr(t.slice(0, 180))}, ${s.toFixed(1)})`).catch(() => {});
  };

  const dress = async (n) => {
    const items = [
      ["armor.head", "leather_helmet[dyed_color=16766720]"],                                               // yellow hard hat
      ["armor.chest", "leather_chestplate[dyed_color=14679808,trim={material:\"iron\",pattern:\"ward\"}]"],  // hi-vis vest
      ["armor.legs", "leather_leggings[dyed_color=3890066]"],                                               // work jeans
      ["armor.feet", "leather_boots[dyed_color=5913118]"],                                                  // brown boots
      ["weapon.mainhand", pick(TOOLS)],
    ];
    for (const [slot, it] of items) {
      const out = await K.cmd(`item replace entity ${n} ${slot} with ${it}`).catch((e) => "ERR " + e.message);
      if (K.looksLikeError(out) && /trim/.test(it)) await K.cmd(`item replace entity ${n} ${slot} with leather_chestplate[dyed_color=14679808]`).catch(() => {});
    }
  };
  K.dressCrew = dress;

  // The bot's own look, so players can tell it apart: a team gives the name its colour and prefix ("Pink " + "Golem"
  // = "Pink Golem" over its head, in the player list and in chat); outfit "pink" = pink leather with gold trim and a
  // shimmer, a pink block in hand and a pink tulip in the other (bot_outfit: "none" to skip).
  const PINK = 16738740;                                       // #FF69B4
  K.dressBot = async () => {
    const n = K.BOT;
    await K.cmd("team add bot_look").catch(() => {});
    await K.cmd(`team modify bot_look color ${K.CHAT_COLOR}`).catch(() => {});
    await K.cmd(`team modify bot_look prefix ${JSON.stringify({ text: K.BOT_PREFIX, color: K.CHAT_COLOR })}`).catch(() => {});
    await K.cmd(`team join bot_look ${n}`).catch(() => {});
    if (K.BOT_OUTFIT !== "pink") return;
    const piece = (id) => `${id}[dyed_color=${PINK},trim={material:"gold",pattern:"silence"},enchantment_glint_override=true,unbreakable={}]`;
    const items = [
      ["armor.head", piece("leather_helmet")], ["armor.chest", piece("leather_chestplate")],
      ["armor.legs", piece("leather_leggings")], ["armor.feet", piece("leather_boots")],
      ["weapon.mainhand", "pink_concrete[enchantment_glint_override=true]"], ["weapon.offhand", "pink_tulip"],
    ];
    for (const [slot, it] of items) {
      const out = await K.cmd(`item replace entity ${n} ${slot} with ${it}`).catch((e) => "ERR " + e.message);
      if (K.looksLikeError(out)) await K.cmd(`item replace entity ${n} ${slot} with ${it.replace(/,trim=\{[^}]*\}/, "")}`).catch(() => {});
    }
  };
  // Carpet takes the name's real Mojang profile when one exists (skin + exact casing, e.g. "alex_builder"), so match
  // crew names case-insensitively and use the names as they are online.
  const isCrew = (n) => NAMES.some((m) => m.toLowerCase() === String(n).toLowerCase());
  K.isCrew = isCrew;
  K.onlineCrew = async () => (await K.onlinePlayers()).names.filter(isCrew);
  K.spawnCrew = async (count, near) => {
    const pl = await K.onlinePlayers();
    const max = Number(/max of (\d+)/.exec(pl.raw)?.[1] || 20);
    const room = max - pl.names.length;
    const online = pl.names.map((n) => n.toLowerCase());
    const want = NAMES.slice(0, Math.max(0, Math.min(count, NAMES.length))).filter((n) => !online.includes(n.toLowerCase())).slice(0, Math.max(0, room));
    const spawned = [];
    for (const [i, n] of want.entries()) {
      const ang = (i / Math.max(1, want.length)) * Math.PI * 2;
      const x = near[0] + Math.cos(ang) * 2.5, z = near[2] + Math.sin(ang) * 2.5;
      const out = await K.cmd(`player ${n} spawn at ${x.toFixed(2)} ${near[1]} ${z.toFixed(2)} facing 0 0 in minecraft:overworld`);
      if (K.looksLikeError(out)) continue;
      spawned.push(n);
    }
    if (spawned.length) await K.sleep(900);
    for (const n of spawned) {
      await K.cmd(`gamemode adventure ${n}`).catch(() => {});
      await K.cmd(`effect give ${n} resistance infinite 4 true`).catch(() => {});
      await K.cmd(`effect give ${n} saturation infinite 0 true`).catch(() => {});
      await dress(n);
    }
    return { spawned, skipped: want.length < count ? `server has room for ${room} more players` : undefined };
  };
  K.dismissCrew = async (names) => {
    for (const n of names) await K.bubble(n, pick(cfg.leave_lines || DEFAULT_LEAVE), 2.5);
    if (names.length) await K.sleep(1800);
    for (const n of names) await K.cmd(`player ${n} kill`).catch(() => {});
  };
  K.crewArriveLine = () => pick(cfg.arrive_lines || DEFAULT_ARRIVE);
  K.crewStartLine = () => pick(cfg.start_lines || DEFAULT_START);

  const itemFor = (b) => {
    if (!b) return null;
    const n = b.replace(/\[.*$/, "").replace(/^minecraft:/, "");
    if (/^(air|cave_air|void_air)$/.test(n)) return "iron_shovel";
    const map = { redstone_wire: "redstone", water: "water_bucket", lava: "lava_bucket", wall_torch: "torch", soul_wall_torch: "soul_torch", piston_head: null, fire: "flint_and_steel", clone: "iron_pickaxe" };
    return n in map ? map[n] : n;
  };

  // Real arm swing: Carpet's `attack` does nothing in adventure mode when aimed at a block, so helpers.sc swings every
  // fake player tagged "building" every 7 ticks; swingNow() swings one player on demand. Both fall back to `attack`.
  let swingAppOk = null;
  const ensureSwingApp = async () => {
    const bad = (o) => /unknown|not found|error|exception/i.test(String(o));
    let out = await K.cmd("script in helpers run swings('x')").catch((e) => "ERROR " + e.message);
    if (bad(out)) {
      await K.cmd("script load helpers").catch(() => {});
      out = await K.cmd("script in helpers run swings('x')").catch((e) => "ERROR " + e.message);
    }
    swingAppOk = !bad(out);
    return swingAppOk;
  };
  K.swingNow = async (name) => {
    if (swingAppOk === null) await ensureSwingApp();
    if (swingAppOk) {
      const out = await K.cmd(`script in helpers run modify(player('${name}'),'swing')`).catch((e) => "ERROR " + e.message);
      if (!/error|exception|unknown/i.test(String(out))) return;
      swingAppOk = false;
    }
    await K.cmd(`player ${name} attack once`).catch(() => {});
  };
  K.startWorking = async (names) => {
    const ok = await ensureSwingApp();
    for (const h of names) {
      await K.cmd(`tag ${h} add building`).catch(() => {});
      if (!ok) await K.cmd(`player ${h} attack interval 7`).catch(() => {});
    }
    return ok;
  };
  K.stopWorking = async (names) => {
    for (const h of names) {
      await K.cmd(`tag ${h} remove building`).catch(() => {});
      await K.cmd(`player ${h} stop`).catch(() => {});
    }
  };
  /** Move one helper next to the part of the build that was just placed, facing it, holding the right block. */
  K.crewStep = async (job, t) => {
    const hs = job.helperNames;
    if (!hs?.length) return;
    const h = hs[job.hIdx++ % hs.length];
    const c = [(t.lo[0] + t.hi[0]) / 2, t.hi[1], (t.lo[2] + t.hi[2]) / 2];
    const look = async () => {
      await K.cmd(`player ${h} look at ${(c[0] + 0.5).toFixed(1)} ${c[1] + 0.5} ${(c[2] + 0.5).toFixed(1)}`).catch(() => {});
      const it = itemFor(t.block);
      if (it) await K.cmd(`item replace entity ${h} weapon.mainhand with ${it}`).catch(() => {});
      if (Math.random() < 0.1) K.bubble(h, pick(LINES), 4);
    };
    // preferred: a real standing spot next to the work (also inside rooms), from helpers.sc stand()
    const sr = await K.inApp("helpers", `stand(${c[0].toFixed(1)},${t.lo[1]},${c[2].toFixed(1)})`).catch(() => "");
    const sm = /=\s*\[\s*(-?[\d.]+),\s*(-?[\d.]+),\s*(-?[\d.]+)\s*\]/.exec(String(sr));
    if (sm) {
      await K.cmd(`tp ${h} ${sm[1]} ${sm[2]} ${sm[3]}`).catch(() => {});
      return look();
    }
    const [lo, hi] = job.box;
    let x = Math.min(Math.max(c[0], lo[0]), hi[0]), z = Math.min(Math.max(c[2], lo[2]), hi[2]);
    const d = [x - lo[0], hi[0] - x, z - lo[2], hi[2] - z];
    const k = d.indexOf(Math.min(...d));
    if (k === 0) x = lo[0] - 2; else if (k === 1) x = hi[0] + 3; else if (k === 2) z = lo[2] - 2; else z = hi[2] + 3;
    x += (Math.random() - 0.5) * 3; z += (Math.random() - 0.5) * 3;
    const y = await K.groundAt(x, z, t.lo[1]);
    await K.cmd(`tp ${h} ${x.toFixed(2)} ${y} ${z.toFixed(2)}`).catch(() => {});
    return look();
  };
  K.crewIdleTimer = (jobKeep) => {
    // Builders stay on site between the jobs of one build session: they go home after 10 minutes with no new job
    // (never with keep_helpers; right away with minecraft_helpers dismiss). A new job with helpers cancels this.
    clearTimeout(st.helperDismissTimer);
    if (jobKeep) return;
    st.helperDismissTimer = setTimeout(() => { K.onlineCrew().then((n) => K.dismissCrew(n)).catch(() => {}); }, 600000);
    st.helperDismissTimer.unref?.();
  };
}
