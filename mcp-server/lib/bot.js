/**
 * bot — the AI's body (a Carpet fake player): natural walking, A* pathfinding through doors and up stairs,
 * following a player, staying out of the build area, and walkability checks.
 */

export function install(K, ctx) {
  const st = ctx.state;
  const fmt = (p) => `${p[0].toFixed(2)} ${p[1].toFixed(2)} ${p[2].toFixed(2)}`;

  /**
   * Walk to a point the way a player would: face it, hold "forward", check progress every ~350 ms.
   * Stops when close enough, when stuck (against a wall) or on timeout. Returns the final position (null if the bot left).
   */
  K.walkTo = async (dest, { stopDistance = 2, timeoutMs = 20000, sprint = false } = {}) => {
    const P = `player ${K.BOT}`;
    let info;
    try { info = await K.playerInfo(K.BOT); } catch { throw new Error(`Bot "${K.BOT}" is not in the world — spawn it first (minecraft_bot action:"spawn").`); }
    await K.cmd(`${P} look at ${fmt(dest)}`).catch(() => {});
    if (sprint) await K.cmd(`${P} sprint`).catch(() => {});
    await K.cmd(`${P} move forward`).catch(() => {});
    let lastXZ = [info.position.x, info.position.z];
    let stuckTicks = 0;
    let finalPos = info.position;
    const start = Date.now();
    try {
      while (Date.now() - start < timeoutMs) {
        await K.sleep(350);
        try { info = await K.playerInfo(K.BOT); } catch { finalPos = null; break; }
        finalPos = info.position;
        const d3 = Math.hypot(finalPos.x - dest[0], finalPos.y - dest[1], finalPos.z - dest[2]);
        if (d3 <= stopDistance) break;
        const moved = Math.hypot(finalPos.x - lastXZ[0], finalPos.z - lastXZ[1]);
        if (moved < 0.06) { if (++stuckTicks >= 5) break; }
        else { stuckTicks = 0; await K.cmd(`${P} look at ${fmt(dest)}`).catch(() => {}); }
        lastXZ = [finalPos.x, finalPos.z];
      }
    } finally {
      // Carpet: "/player X stop" stops actions (attack/use/jump) but NOT walking; "/player X move" stops walking.
      await K.cmd(`${P} move`).catch(() => {});
      await K.cmd(`${P} stop`).catch(() => {});
      if (sprint) await K.cmd(`${P} unsprint`).catch(() => {});
    }
    return finalPos;
  };

  /** If the bot stands inside the box being built, step it out first so it doesn't get embedded in blocks. */
  K.keepBotOutOf = async (lo, hi) => {
    let b;
    try { b = (await K.playerInfo(K.BOT)).position; } catch { return null; }
    const inside = b.x >= lo[0] - 0.3 && b.x <= hi[0] + 1.3 && b.z >= lo[2] - 0.3 && b.z <= hi[2] + 1.3 && b.y >= lo[1] - 1 && b.y <= hi[1] + 1;
    if (!inside) return null;
    const spot = [(lo[0] + hi[0]) / 2 + 0.5, lo[1] + 1, lo[2] - 2 + 0.5];
    await K.cmd(`tp ${K.BOT} ${spot[0].toFixed(2)} ${spot[1]} ${spot[2].toFixed(2)}`).catch(() => {});
    return `bot was inside the build area — moved it to ${spot[0].toFixed(1)} ${spot[1]} ${spot[2].toFixed(1)}`;
  };

  const setDoor = async (c, open) => {
    const e = `b=block(${c.join(",")}); if(str(b)~'door'||str(b)~'gate', set(${c.join(",")}, b, 'open', '${open}'); ` +
      `if(str(block(${c[0]},${c[1] + 1},${c[2]}))==str(b), set(${c[0]},${c[1] + 1},${c[2]}, block(${c[0]},${c[1] + 1},${c[2]}), 'open', '${open}')); 1, 0)`;
    await K.scarpet(e).catch(() => {});
    await K.cmd(`playsound minecraft:block.wooden_door.${open ? "open" : "close"} block @a ${c.join(" ")} 0.8 1`).catch(() => {});
  };

  /** Walk with A*: around walls, through doors (opens and closes them), up stairs, drops ≤3. ±60 blocks. */
  K.smartWalk = async function smartWalk(dest, { sprint = false, timeoutMs = 45000 } = {}) {
    const bot = await K.playerInfo(K.BOT);
    const a = [bot.position.x, bot.position.y, bot.position.z];
    const lo = [Math.floor(Math.min(a[0], dest[0])) - 14, Math.floor(Math.min(a[1], dest[1])) - 4, Math.floor(Math.min(a[2], dest[2])) - 14];
    const hi = [Math.floor(Math.max(a[0], dest[0])) + 14, Math.floor(Math.max(a[1], dest[1])) + 5, Math.floor(Math.max(a[2], dest[2])) + 14];
    if (K.volOf([lo, hi]) > 118000) return { fallback: "too far for pathfinding (use tp, or walk in stages)" };
    const R = await K.dumpRegion(lo, hi);
    const P = K.PF.findPath(R, a, dest);
    if (P.error) return { fallback: P.error };
    const t0 = Date.now();
    const legs = [];
    const opened = [];
    for (const d of P.doors) { await setDoor(d, true); opened.push(d); }
    let prevY = P.start[1];
    try {
      for (const w of P.waypoints) {
        if (Date.now() - t0 > timeoutMs) { legs.push("timeout"); break; }
        const tgt = [w[0] + 0.5, w[1], w[2] + 0.5];
        if (w[1] > prevY) await K.cmd(`player ${K.BOT} jump continuous`).catch(() => {});
        const fp = await K.walkTo(tgt, { stopDistance: 0.7, timeoutMs: 12000, sprint });
        prevY = w[1];
        if (!fp) return { error: "bot disconnected" };
        const d = Math.hypot(fp.x - tgt[0], fp.z - tgt[2]);
        legs.push(`${d < 1.6 ? "✓" : "✗"} ${fp.x.toFixed(1)} ${fp.y.toFixed(1)} ${fp.z.toFixed(1)}`);
        if (d > 3) { // pushed off course — replan once from here
          const again = await smartWalk(dest, { sprint, timeoutMs: Math.max(5000, timeoutMs - (Date.now() - t0)) }).catch((e) => ({ error: e.message }));
          return { ...again, replanned: true, legs };
        }
      }
    } finally {
      await K.sleep(300);
      for (const d of opened) await setDoor(d, false);
    }
    const fin = (await K.playerInfo(K.BOT)).position;
    return { reached: P.reached && Math.hypot(fin.x - dest[0], fin.z - dest[2]) < 2.5, position: [fin.x, fin.y, fin.z].map((v) => +v.toFixed(1)), waypoints: P.waypoints.length, doors: P.doors.length, legs };
  };

  K.stopFollow = () => {
    if (st.followTimer) clearInterval(st.followTimer);
    st.followTimer = null;
    st.followTarget = null;
    K.cmd(`player ${K.BOT} move`).catch(() => {});
  };
  K.startFollow = (target) => {
    K.stopFollow();
    st.followTarget = target;
    const P2 = `player ${K.BOT}`;
    const DESIRED = 2.5, FAR = 10;
    let walking = false;
    const tick = async () => {
      try {
        const [botInfo, targetInfo] = await Promise.all([K.playerInfo(K.BOT).catch(() => null), K.playerInfo(target).catch(() => null)]);
        if (!botInfo || !targetInfo) return;
        const bp = botInfo.position, tp = targetInfo.position;
        const dist = Math.hypot(tp.x - bp.x, tp.z - bp.z);
        const look = () => K.cmd(`${P2} look at ${tp.x.toFixed(2)} ${tp.y.toFixed(2)} ${tp.z.toFixed(2)}`).catch(() => {});
        if (dist > FAR) {
          if (walking) { await K.cmd(`${P2} move`).catch(() => {}); walking = false; }
          await K.cmd(`execute as ${K.BOT} at ${target} run tp @s ^1.2 ^ ^-1.5`).catch(() => {});
          await look();
        } else if (dist > DESIRED) {
          await look();
          if (!walking) { await K.cmd(`${P2} move forward`).catch(() => {}); walking = true; }
        } else {
          if (walking) { await K.cmd(`${P2} move`).catch(() => {}); walking = false; }
          await look();
        }
      } catch {}
    };
    tick();
    st.followTimer = setInterval(tick, 600);
    st.followTimer.unref();
    return FAR;
  };

  /** Can a player walk from A to each target? (dry run of the pathfinder, nobody moves) */
  K.reach = async (fromP, targets, margin = 6) => {
    const all = [fromP, ...targets];
    const lo = [0, 1, 2].map((i) => Math.floor(Math.min(...all.map((p) => p[i]))) - (i === 1 ? 3 : margin));
    const hi = [0, 1, 2].map((i) => Math.floor(Math.max(...all.map((p) => p[i]))) + (i === 1 ? 5 : margin));
    lo[1] = Math.max(-64, lo[1]);
    if (K.volOf([lo, hi]) > 118000) throw new Error(`area ${K.volOf([lo, hi])} blocks is too big for one reach check (max ~118k) — check fewer / closer targets`);
    const R = await K.dumpRegion(lo, hi);
    return targets.map((t) => {
      const r = K.PF.findPath(R, fromP, t, { maxNodes: 120000 });
      if (r.error) return { to: t, reachable: false, why: r.error };
      return { to: t, reachable: r.reached, steps: r.cells, doors: r.doors.length, ...(r.reached ? {} : { closest: r.cells ? r.waypoints.slice(-1)[0] : null }) };
    });
  };
}
