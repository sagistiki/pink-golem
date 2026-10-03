/** The AI's body and its crew: minecraft_bot, minecraft_helpers. Both need Carpet (fake players). */

const vec = { type: "array", items: { type: "number" }, minItems: 3, maxItems: 3, description: "[x, y, z]" };

export const tools = [
  {
    name: "minecraft_bot",
    requires: ["carpet"],
    description: "Control your visible body in the world (a Carpet fake player with your bot name). spawn (near a player or at pos), despawn, tp (instant — for long distances), walk_to (walks like a player; plans an A* path around walls, through doors and up stairs by default), look_at (player or pos), follow / stop_follow, swing (arm-swing animation), jump, sneak/unsneak, sprint/unsprint, use, attack, stop, hotbar, give (item in hand), gamemode, move (raw direction), raw (any '/player <bot> ...' args). The bot runs in ADVENTURE mode with permanent resistance — never put it in creative: there 'attack' breaks the block it looks at. Feel natural: walk to the site before building, swing while building, look at the player when done.",
    inputSchema: {
      type: "object",
      properties: {
        action: { type: "string", enum: ["spawn", "despawn", "tp", "walk_to", "swing", "look_at", "follow", "stop_follow", "move", "jump", "sneak", "unsneak", "sprint", "unsprint", "use", "attack", "stop", "hotbar", "give", "gamemode", "raw"] },
        player: { type: "string", description: "Target player for spawn/tp/walk_to/look_at/follow" },
        pos: vec,
        direction: { type: "string", enum: ["forward", "backward", "left", "right", "stop"] },
        mode: { type: "string", description: "once | continuous | interval N (jump/use/attack); sprint (walk_to); a game mode (gamemode)" },
        stop_distance: { type: "number", description: "walk_to: how close counts as arrived (default 2)" },
        pathfind: { type: "boolean", description: "walk_to: plan a real path (default true when no path is given)" },
        path: { type: "array", items: vec, description: "walk_to: explicit waypoints, walked straight in order (no stairs)" },
        times: { type: "number", description: "swing: 1-6 (default 1)" },
        timeout_seconds: { type: "number", description: "walk_to: give up after this long, 1-55 (default 20)" },
        slot: { type: "number" },
        item: { type: "string", description: "Item id for give, e.g. diamond_pickaxe" },
        raw: { type: "string", description: "Args after '/player <name> ' for action=raw" },
      },
      required: ["action"],
    },
  },
  {
    name: "minecraft_helpers",
    requires: ["carpet"],
    description: "Helper builders (up to 4 fake players in hard hats and hi-vis vests; names from pinkgolem.json). action: spawn (count, near pos or player) | dismiss | list | say (name, message → speech bubble) | work (pos: all face it and hammer) | dress. Background jobs bring them automatically with helpers:N; they stay on site between jobs and go home after 10 idle minutes.",
    inputSchema: { type: "object", properties: { action: { type: "string", enum: ["spawn", "dismiss", "list", "say", "work", "dress"] }, count: { type: "number" }, pos: vec, player: { type: "string" }, name: { type: "string" }, message: { type: "string" } }, required: ["action"] },
  },
];

export function handlers(K, ctx) {
  const st = ctx.state;
  return {
    async minecraft_bot(args) {
      const B = K.BOT;
      const P = `player ${B}`;
      const act = args.action;
      const target = args.player;
      const run = async (c) => {
        const out = await K.cmd(c);
        if (K.looksLikeError(out)) throw new Error(`${c} → ${out}`);
        return out;
      };
      switch (act) {
        case "spawn": {
          let where = "", note = "";
          let near = target;
          if (near) {
            // "spawn next to <me>" or a name that isn't online: spawn next to the one real player instead of failing
            const on = (await K.onlinePlayers()).names;
            const real = on.filter((n) => n !== B && !(K.isCrew && K.isCrew(n)));
            const hit = on.find((n) => n.toLowerCase() === String(near).toLowerCase());
            if ((!hit || hit === B) && real.length) {
              note = ` — "${near}" is ${hit === B ? "you" : "not online"}, so you spawned next to ${real[0]}${real.length > 1 ? ` (online: ${real.join(", ")})` : ""}`;
              near = real[0];
            } else if (hit) near = hit;
          }
          if (near) {
            const p = await K.playerInfo(near);
            where = ` at ${(p.position.x + 1.5).toFixed(2)} ${p.position.y} ${(p.position.z + 1.5).toFixed(2)} facing ${p.facing ? ((p.facing.yaw + 180) % 360).toFixed(1) : 0} 0 in ${p.dimension}`;
          } else if (args.pos) where = ` at ${K.V(args.pos).join(" ")}`;
          const out = await run(`${P} spawn${where}`);
          // adventure: attack/use are pure animations (can't break or place). Carpet needs a moment to log the fake
          // player in, or the game mode is lost.
          await K.sleep(700);
          await K.cmd(`gamemode ${args.mode || "adventure"} ${B}`).catch(() => {});
          await K.cmd(`effect give ${B} resistance infinite 4 true`).catch(() => {});
          await K.cmd(`effect give ${B} saturation infinite 0 true`).catch(() => {});
          await K.dressBot();
          if (near) await K.cmd(`execute as ${B} at @s facing entity ${near} eyes run tp @s ~ ~ ~ ~ ~`).catch(() => {});
          return K.text(`${out || "spawned"}${where ? " (" + where.trim() + ")" : ""}${note}`);
        }
        case "despawn":
          K.stopFollow();
          return K.text((await run(`${P} kill`)) || "despawned");
        case "tp":
          if (target) return K.text(await run(`tp ${B} ${target}`));
          if (args.pos) return K.text(await run(`tp ${B} ${K.V(args.pos).join(" ")}`));
          throw new Error("tp needs player or pos");
        case "walk_to": {
          if (Array.isArray(args.path) && args.path.length) {
            const legs = [];
            for (const wp of args.path) {
              const fp = await K.walkTo(K.V(wp), { stopDistance: args.stop_distance ?? 0.8, timeoutMs: 15000, sprint: args.mode === "sprint" });
              if (!fp) return K.text("Bot disconnected while walking.");
              const d = Math.hypot(fp.x - wp[0], fp.z - wp[2]);
              legs.push(`${d <= (args.stop_distance ?? 0.8) + 0.3 ? "✓" : "✗ stuck"} → ${fp.x.toFixed(1)} ${fp.y.toFixed(1)} ${fp.z.toFixed(1)}`);
              if (d > (args.stop_distance ?? 0.8) + 1.5) break;
            }
            return K.text(`Walked path:\n${legs.join("\n")}`);
          }
          let dest;
          if (target) { const p = await K.playerInfo(target); dest = [p.position.x, p.position.y, p.position.z]; }
          else if (args.pos) dest = K.V(args.pos);
          else throw new Error("walk_to needs player or pos");
          const stopDistance = args.stop_distance ?? 2;
          const timeoutMs = Math.max(1, Math.min(args.timeout_seconds ?? 20, 55)) * 1000;
          if (args.pathfind !== false) {
            const r = await K.smartWalk(dest, { sprint: args.mode === "sprint", timeoutMs: Math.max(timeoutMs, 30000) }).catch((e) => ({ fallback: e.message }));
            if (!r.fallback) return K.text({ pathfinding: true, ...r });
            const fp = await K.walkTo(dest, { stopDistance, timeoutMs, sprint: args.mode === "sprint" });
            if (!fp) return K.text("Bot disconnected while walking.");
            return K.text(`No path (${r.fallback}) — walked straight instead; now at ${fp.x.toFixed(1)} ${fp.y.toFixed(1)} ${fp.z.toFixed(1)}`);
          }
          const fp = await K.walkTo(dest, { stopDistance, timeoutMs, sprint: args.mode === "sprint" });
          if (!fp) return K.text("Bot disconnected while walking.");
          const d = Math.hypot(fp.x - dest[0], fp.y - dest[1], fp.z - dest[2]);
          return K.text(`${d <= stopDistance ? "Arrived" : "Stopped (stuck or timed out) at"} — bot position: ${fp.x.toFixed(1)} ${fp.y.toFixed(1)} ${fp.z.toFixed(1)} (${d.toFixed(1)} blocks from target)`);
        }
        case "look_at":
          if (target) await K.playerInfo(target);     // "facing entity <nobody>" fails silently — name who is online instead
          if (target) return K.text((await run(`execute as ${B} at @s facing entity ${target} eyes run tp @s ~ ~ ~ ~ ~`)) || `looking at ${target}`);
          if (args.pos) return K.text((await run(`${P} look at ${K.V(args.pos).join(" ")}`)) || "looking");
          throw new Error("look_at needs player or pos");
        case "follow": {
          if (!target) throw new Error("follow needs player");
          await K.playerInfo(target);
          const far = K.startFollow(target);
          return K.text(`Following ${target} — walks normally, only teleports to catch up if left more than ${far} blocks behind. Use stop_follow to stop.`);
        }
        case "stop_follow":
          K.stopFollow();
          return K.text("Stopped following.");
        case "move":
          return K.text((await run(`${P} move${args.direction && args.direction !== "stop" ? " " + args.direction : ""}`)) || "ok");
        case "swing": {
          const gm = (await K.playerInfo(B)).gameMode;
          let note = "";
          if (gm === "creative" || gm === "survival") {
            await K.cmd(`gamemode adventure ${B}`);
            note = ` (switched the bot from ${gm} to adventure so swinging can't break blocks)`;
          }
          const n = Math.max(1, Math.min(args.times ?? 1, 6));
          for (let i = 0; i < n; i++) { await K.swingNow(B); if (i < n - 1) await K.sleep(250); }
          return K.text(`swung ${n}x${note}`);
        }
        case "jump": case "use": case "attack":
          return K.text((await run(`${P} ${act} ${args.mode || "once"}`)) || "ok");
        case "sneak": case "unsneak": case "sprint": case "unsprint": case "stop":
          if (act === "stop") { K.stopFollow(); await K.cmd(`${P} move`).catch(() => {}); }
          return K.text((await run(`${P} ${act}`)) || "ok");
        case "hotbar":
          return K.text((await run(`${P} hotbar ${args.slot || 1}`)) || "ok");
        case "give": {
          if (!args.item) throw new Error("give needs item");
          return K.text((await run(`item replace entity ${B} weapon.mainhand with ${args.item}`)) || `holding ${args.item}`);
        }
        case "gamemode":
          return K.text(await run(`gamemode ${args.mode || "adventure"} ${B}`));
        case "raw":
          return K.text((await K.cmd(`${P} ${args.raw || ""}`)) || "ok");
        default:
          throw new Error(`Unknown bot action ${act}`);
      }
    },

    async minecraft_helpers(args) {
      const act = args.action;
      if (act === "list") return K.text({ online: await K.onlineCrew(), all: K.CREW_NAMES });
      if (act === "spawn") {
        let near;
        if (args.pos) near = K.V(args.pos);
        else { const p = await K.playerInfo(args.player || K.BOT); near = [p.position.x, p.position.y, p.position.z]; }
        const r = await K.spawnCrew(Math.max(1, Math.min(args.count ?? 3, 4)), near);
        const on = await K.onlineCrew();
        if (on.length) await K.bubble(on[0], K.crewArriveLine(), 3);
        return K.text({ ...r, online: on });
      }
      if (act === "dismiss") { clearTimeout(st.helperDismissTimer); const on = await K.onlineCrew(); await K.dismissCrew(on); return K.text({ dismissed: on }); }
      if (act === "dress") { const on = await K.onlineCrew(); for (const n of on) await K.dressCrew(n); return K.text({ dressed: on }); }
      if (act === "say") { await K.bubble(args.name || K.CREW_NAMES[0], args.message || "!"); return K.text("said"); }
      if (act === "work") {
        const on = await K.onlineCrew();
        const p = K.V(args.pos);
        for (const n of on) await K.cmd(`player ${n} look at ${p[0] + 0.5} ${p[1] + 0.5} ${p[2] + 0.5}`).catch(() => {});
        await K.startWorking(on);
        return K.text({ working: on, stop: "dismiss them, or they stop at the end of the next job" });
      }
      throw new Error("unknown action");
    },
  };
}
