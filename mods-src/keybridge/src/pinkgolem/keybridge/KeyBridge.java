package pinkgolem.keybridge;

import java.lang.reflect.Field;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;

import com.mojang.brigadier.CommandDispatcher;
import com.mojang.brigadier.arguments.DoubleArgumentType;
import com.mojang.brigadier.arguments.FloatArgumentType;
import com.mojang.brigadier.arguments.StringArgumentType;
import com.mojang.brigadier.builder.RequiredArgumentBuilder;
import com.mojang.brigadier.context.CommandContext;

import net.fabricmc.api.ModInitializer;
import net.fabricmc.fabric.api.command.v2.CommandRegistrationCallback;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerLifecycleEvents;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.Commands;
import net.minecraft.commands.arguments.EntityArgument;
import net.minecraft.commands.arguments.UuidArgument;
import net.minecraft.network.chat.Component;
import net.minecraft.network.protocol.common.ClientboundResourcePackPopPacket;
import net.minecraft.network.protocol.common.ClientboundResourcePackPushPacket;
import net.minecraft.network.protocol.game.ClientboundAddEntityPacket;
import net.minecraft.network.protocol.game.ClientboundRemoveEntitiesPacket;
import net.minecraft.network.protocol.game.ClientboundRotateHeadPacket;
import net.minecraft.network.protocol.game.ClientboundSetCameraPacket;
import net.minecraft.network.protocol.game.ClientboundSetEntityDataPacket;
import net.minecraft.network.protocol.game.ClientboundTeleportEntityPacket;
import net.minecraft.network.protocol.game.ClientboundUpdateAttributesPacket;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.ServerScoreboard;
import net.minecraft.server.dedicated.DedicatedServer;
import net.minecraft.server.dedicated.DedicatedServerProperties;
import net.minecraft.server.dedicated.DedicatedServerSettings;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.util.Mth;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntityTypes;
import net.minecraft.world.entity.PositionMoveRotation;
import net.minecraft.world.entity.ai.attributes.AttributeInstance;
import net.minecraft.world.entity.ai.attributes.Attributes;
import net.minecraft.world.entity.monster.spider.Spider;
import net.minecraft.world.entity.player.Input;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.storage.LevelResource;
import net.minecraft.world.phys.Vec3;
import net.minecraft.world.scores.Objective;
import net.minecraft.world.scores.criteria.ObjectiveCriteria;

/**
 * Key Bridge — a tiny server-side mod.
 *
 * 1. Keys: every tick it copies each player's movement keys (the input the client sends,
 *    ServerPlayer.getLastClientInput) into the dummy scoreboard objective "keys", so scarpet apps can read them with
 *    scoreboard('keys', name). Bits: 1 forward (W) · 2 back (S) · 4 left (A) · 8 right (D) · 16 jump (Space) ·
 *    32 sneak (Shift) · 64 sprint (Ctrl). Written only when a player's keys change.
 *
 * 2. Live resource pack (op level 2+):
 *    /packpush <url> <sha1> [prompt]  sends the pack to everyone online at once (ClientboundResourcePackPushPacket with
 *                                     one fixed UUID, so a newer push replaces the older one) and drops the
 *                                     server.properties pack they got at join. Players who join later get it too.
 *    /packpush                        shows what is pushed.
 *    /packpop                         removes the pushed pack and gives players back their join pack.
 *    If server.properties already names the same url + sha1 when you push (deploy writes it first), the running
 *    server adopts it, so later joiners get the new pack during login (one download, no double reload).
 *    Polymer AutoHost mode (1.4.0, config/polymer/auto-host.json enabled): pushes reuse Polymer's pack UUID, so they
 *    replace the pack Polymer sent at login; logins are left to Polymer; /packpop is refused.
 *
 * 3. Flip camera (op level 2+) — an upside-down view for one player, e.g. in a roller-coaster loop:
 *    /flipcam start <player> <x> <y> <z> <yaw> <pitch> [eye_height]
 *    /flipcam move  <player> <x> <y> <z> <yaw> <pitch>        (call every tick)
 *    /flipcam stop  <player> [camera_entity_uuid]
 *    The player's client gets a fake, invisible, silent spider (packets only — it never exists on the server, so
 *    Peaceful doesn't matter) and its camera is set to it. The client applies the post effect "minecraft:spider" to a
 *    spider camera; a resource pack replaces that effect with a 180° image rotation = the world upside down.
 *    x y z is the CAMERA (eye) point; the spider stands eye_height lower. eye_height defaults to the eye height of the
 *    player's current camera entity (the client eases the camera height after a switch, so matching it avoids a
 *    slide); the spider is scaled to it (0.65 × scale, scale 0.0625..16). Moves are compensated for the client's
 *    3-step interpolation of mobs, so the view follows the given poses exactly with the usual one-tick latency.
 *    stop sets the camera to the given entity, or to the camera the server thinks the player has. Disconnect,
 *    death, respawn and a dimension change clean up by themselves; one fake per player.
 *
 * 4. Skin easel (op level 2+, called by the scarpet app skinpaint.sc):
 *    /skinbake <id>   reads world/scripts/skinpaint.data/bake/<id>.json (4096 ARGB pixels), writes png/<id>.png,
 *                     uploads it to MineSkin (SkinBake, off the server thread) and answers on the server thread with
 *                     `script in skinpaint run _baked('<id>','<url>','<value>','<signature>')` or `_bake_failed('<id>','<why>')`.
 *    On start it writes skinpaint.data/keybridge.json {"version","skinbake":true} so the app knows it can save.
 *    Optional MineSkin API key (higher limits): config/keybridge-mineskin.txt.
 *
 * 5. Hidden from one player (1.4.0): an entity tagged kbhide_<player name in lower case> is not drawn for that player;
 *    everyone else sees it (e.g. a rider's own body double, which only the other riders should see).
 *
 * No client install needed. Any failure is logged once and that part switches off; it never takes the server down.
 */
public class KeyBridge implements ModInitializer {
    private static final String OBJECTIVE = "keys";
    /** Fixed id of the pushed pack ("keybridge-pack"): a new push with the same id replaces the old one. */
    public static final UUID PUSH_ID = UUID.fromString("6b657962-7269-4467-a500-7061636b0001");

    private record Pack(String url, String hash, boolean required, Optional<Component> prompt) {}

    private final Map<UUID, Integer> last = new HashMap<>();
    /** players seen online, with the server.properties pack they received when they joined (may be empty) */
    private final Map<UUID, Optional<MinecraftServer.ServerResourcePackInfo>> joinPack = new HashMap<>();
    /** players whose join pack we removed (so /packpop can give it back) */
    private final Set<UUID> popped = new HashSet<>();
    private Pack latest = null;

    /** One flip camera: the fake spider and what the client shows after its next tick (the model the moves correct). */
    private static final class Flip {
        ServerPlayer player;
        Level level;
        Spider spider;
        int id;
        float eye;
        double x, y, z;       // feet position the client has
        float yRot, xRot;     // body yaw / pitch the client has
        float head;           // head yaw the client has (= camera yaw)
    }
    private final Map<UUID, Flip> flips = new HashMap<>();
    private int nextFakeId = Integer.MAX_VALUE - 1000;   // far above real entity ids, counting down
    private boolean flipBroken = false;
    private boolean keysBroken = false;
    private boolean packBroken = false;
    private boolean hideBroken = false;
    private SkinBake baker = null;

    @Override
    public void onInitialize() {
        try {
            ServerTickEvents.START_SERVER_TICK.register(this::safeTick);
        } catch (Throwable t) {
            System.err.println("[KeyBridge] keys disabled: " + t);
        }
        try {
            ServerLifecycleEvents.SERVER_STARTED.register(this::skinMarker);
        } catch (Throwable t) {
            System.err.println("[KeyBridge] skin easel marker disabled: " + t);
        }
        try {
            CommandRegistrationCallback.EVENT.register((dispatcher, context, selection) -> register(dispatcher));
        } catch (Throwable t) {
            System.err.println("[KeyBridge] pack commands disabled: " + t);
        }
    }

    // ───────────────────────────── keys ─────────────────────────────
    private void safeTick(MinecraftServer server) {
        if (!keysBroken) {
            try {
                keys(server);
            } catch (Throwable t) {
                keysBroken = true;
                System.err.println("[KeyBridge] keys disabled after an error: " + t);
            }
        }
        if (!packBroken) {
            try {
                joins(server);
            } catch (Throwable t) {
                packBroken = true;
                System.err.println("[KeyBridge] pack push on join disabled after an error: " + t);
            }
        }
        if (!hideBroken) {
            try {
                hideFromSelf(server);
            } catch (Throwable t) {
                hideBroken = true;
                System.err.println("[KeyBridge] per-player hiding disabled after an error: " + t);
            }
        }
        if (!flipBroken && !flips.isEmpty()) {
            try {
                flipWatch(server);
            } catch (Throwable t) {
                flipBroken = true;
                flips.clear();
                System.err.println("[KeyBridge] flip camera disabled after an error: " + t);
            }
        }
    }

    private void keys(MinecraftServer server) {
        ServerScoreboard board = server.getScoreboard();
        Objective obj = board.getObjective(OBJECTIVE);
        if (obj == null) {
            obj = board.addObjective(OBJECTIVE, ObjectiveCriteria.DUMMY, Component.literal("keys"),
                    ObjectiveCriteria.RenderType.INTEGER, false, null);
        }
        for (ServerPlayer p : server.getPlayerList().getPlayers()) {
            Input in = p.getLastClientInput();
            int bits = (in.forward() ? 1 : 0) | (in.backward() ? 2 : 0) | (in.left() ? 4 : 0) | (in.right() ? 8 : 0)
                    | (in.jump() ? 16 : 0) | (in.shift() ? 32 : 0) | (in.sprint() ? 64 : 0);
            Integer prev = last.get(p.getUUID());
            if (prev == null || prev != bits) {
                board.getOrCreatePlayerScore(p, obj).set(bits);
                last.put(p.getUUID(), bits);
            }
        }
        if (server.getTickCount() % 1200 == 0) {
            last.keySet().removeIf(u -> server.getPlayerList().getPlayer(u) == null);
        }
    }

    // ───────────────────────────── hidden from one player ─────────────────────────────
    /** An entity tagged kbhide_<player name, lower case> is drawn for everyone except that player: every tick the
     *  player is told the entity is gone (ClientboundRemoveEntitiesPacket; later updates for an unknown id are ignored
     *  by the client, and a fresh spawn packet is answered on the next tick). E.g. a body double that shows a rider to
     *  the other riders, which the rider must not see from inside. */
    private void hideFromSelf(MinecraftServer server) {
        Map<String, it.unimi.dsi.fastutil.ints.IntArrayList> hide = null;
        for (net.minecraft.server.level.ServerLevel level : server.getAllLevels()) {
            for (net.minecraft.world.entity.Entity e : level.getAllEntities()) {
                Set<String> tags = e.entityTags();
                if (tags.isEmpty()) continue;
                for (String t : tags) {
                    if (!t.startsWith("kbhide_")) continue;
                    if (hide == null) hide = new HashMap<>();
                    hide.computeIfAbsent(t.substring(7), k -> new it.unimi.dsi.fastutil.ints.IntArrayList()).add(e.getId());
                }
            }
        }
        if (hide == null) return;
        for (ServerPlayer p : server.getPlayerList().getPlayers()) {
            it.unimi.dsi.fastutil.ints.IntArrayList ids = hide.get(p.getGameProfile().name().toLowerCase(java.util.Locale.ROOT));
            if (ids != null && !ids.isEmpty())
                p.connection.send(new net.minecraft.network.protocol.game.ClientboundRemoveEntitiesPacket(ids));
        }
    }

    // ───────────────────────────── live resource pack ─────────────────────────────
    /** Polymer AutoHost mode: when config/polymer/auto-host.json says "enabled": true, Polymer serves the pack from the
     *  game port and sends it during login under its main UUID (config/polymer/resource-pack.json main_uuid). A live
     *  push then reuses that UUID, so the client REPLACES Polymer's pack in place instead of stacking a second pack on
     *  top, and joins are left to Polymer (it serves the regenerated pack after /polymer generate-pack).
     *  Read at every push and join: switching the mode needs no rebuild. Empty = classic mode (server.properties pack). */
    static Optional<UUID> polymerPackId() {
        try {
            Path dir = Path.of("config", "polymer");
            String host = java.nio.file.Files.readString(dir.resolve("auto-host.json")).replaceAll("\\s", "");
            if (!host.contains("\"enabled\":true")) return Optional.empty();
            java.util.regex.Matcher m = java.util.regex.Pattern.compile("\"main_uuid\"\\s*:\\s*\"([0-9a-fA-F-]{36})\"")
                    .matcher(java.nio.file.Files.readString(dir.resolve("resource-pack.json")));
            return m.find() ? Optional.of(UUID.fromString(m.group(1))) : Optional.empty();
        } catch (Throwable t) {
            return Optional.empty();
        }
    }

    /** A player who is new in the player list has finished logging in (and got the server.properties pack then). */
    private void joins(MinecraftServer server) {
        Set<UUID> now = new HashSet<>();
        for (ServerPlayer p : server.getPlayerList().getPlayers()) {
            UUID u = p.getUUID();
            now.add(u);
            if (joinPack.containsKey(u)) continue;
            Optional<MinecraftServer.ServerResourcePackInfo> base = server.getServerResourcePack();
            joinPack.put(u, base);
            if (latest != null && polymerPackId().isEmpty()   // Polymer mode: Polymer sends the current pack at login
                    && !(base.isPresent() && base.get().hash().equalsIgnoreCase(latest.hash()))) send(p, base);
        }
        joinPack.keySet().retainAll(now);
        popped.retainAll(now);
    }

    private void send(ServerPlayer p, Optional<MinecraftServer.ServerResourcePackInfo> base) {
        Optional<UUID> poly = polymerPackId();
        if (poly.isEmpty() && base.isPresent() && !base.get().hash().equalsIgnoreCase(latest.hash())) {
            p.connection.send(new ClientboundResourcePackPopPacket(Optional.of(base.get().id())));
            popped.add(p.getUUID());
        }
        p.connection.send(new ClientboundResourcePackPushPacket(poly.orElse(PUSH_ID), latest.url(), latest.hash(), latest.required(), latest.prompt()));
    }

    // ───────────────────────────── skin easel ─────────────────────────────
    private static Path skinDir(MinecraftServer server) {
        return server.getWorldPath(LevelResource.ROOT).normalize().resolve("scripts").resolve("skinpaint.data");
    }

    private void skinMarker(MinecraftServer server) {
        try {
            Path dir = skinDir(server);
            java.nio.file.Files.createDirectories(dir);
            java.nio.file.Files.writeString(dir.resolve("keybridge.json"), "{\"version\":\"1.4.0\",\"skinbake\":true}");
        } catch (Throwable t) {
            System.err.println("[KeyBridge] could not write the skin easel marker: " + t);
        }
    }

    private static String scarpetSafe(String s) {
        return s == null ? "" : s.replaceAll("[^A-Za-z0-9+/=:._ -]", "");
    }

    private int skinBake(CommandSourceStack src, String id) {
        if (!SkinBake.validId(id)) {
            src.sendFailure(Component.literal("[KeyBridge] skinbake: bad id"));
            return 0;
        }
        MinecraftServer server = src.getServer();
        if (baker == null) {
            String key = "";
            try {
                Path kf = server.getServerDirectory().resolve("config").resolve("keybridge-mineskin.txt");
                if (java.nio.file.Files.exists(kf)) key = java.nio.file.Files.readString(kf).trim();
            } catch (Throwable ignored) {
            }
            baker = new SkinBake(key);
        }
        baker.bake(skinDir(server), id, r -> server.execute(() -> {
            String cmd = r.ok()
                    ? "script in skinpaint run _baked('" + id + "','" + scarpetSafe(r.url()) + "','" + scarpetSafe(r.value()) + "','" + scarpetSafe(r.signature()) + "')"
                    : "script in skinpaint run _bake_failed('" + id + "','" + scarpetSafe(r.error()) + "')";
            try {
                server.getCommands().performPrefixedCommand(server.createCommandSourceStack().withSuppressedOutput(), cmd);
            } catch (Throwable t) {
                System.err.println("[KeyBridge] skinbake callback failed: " + t);
            }
        }));
        src.sendSuccess(() -> Component.literal("[KeyBridge] baking " + id), false);
        return 1;
    }

    private void register(CommandDispatcher<CommandSourceStack> d) {
        d.register(Commands.literal("packpush").requires(Commands.hasPermission(Commands.LEVEL_GAMEMASTERS))
                .executes(c -> status(c.getSource()))
                .then(Commands.argument("args", StringArgumentType.greedyString())
                        .executes(c -> push(c.getSource(), StringArgumentType.getString(c, "args")))));
        d.register(Commands.literal("skinbake").requires(Commands.hasPermission(Commands.LEVEL_GAMEMASTERS))
                .then(Commands.argument("id", StringArgumentType.word()).executes(c -> skinBake(c.getSource(), StringArgumentType.getString(c, "id")))));
        d.register(Commands.literal("packpop").requires(Commands.hasPermission(Commands.LEVEL_GAMEMASTERS))
                .executes(c -> pop(c.getSource())));
        d.register(Commands.literal("flipcam").requires(Commands.hasPermission(Commands.LEVEL_GAMEMASTERS))
                .executes(c -> flipStatus(c.getSource()))
                .then(Commands.literal("start").then(Commands.argument("player", EntityArgument.player()).then(pose(
                        Commands.argument("eye_height", FloatArgumentType.floatArg(0.0f, 16.0f))
                                .executes(c -> guard(c, () -> flipStart(c, FloatArgumentType.getFloat(c, "eye_height")))),
                        c -> guard(c, () -> flipStart(c, -1f))))))
                .then(Commands.literal("move").then(Commands.argument("player", EntityArgument.player()).then(pose(
                        null, c -> guard(c, () -> flipMove(c))))))
                .then(Commands.literal("stop").then(Commands.argument("player", EntityArgument.player())
                        .executes(c -> guard(c, () -> flipStop(c, null)))
                        .then(Commands.argument("camera", UuidArgument.uuid())
                                .executes(c -> guard(c, () -> flipStop(c, UuidArgument.getUuid(c, "camera"))))))));
    }

    private interface Body { int run() throws Exception; }

    /** Never let a flip camera problem escape a command: report it instead. */
    private static int guard(CommandContext<CommandSourceStack> c, Body b) {
        try {
            return b.run();
        } catch (com.mojang.brigadier.exceptions.CommandSyntaxException e) {
            c.getSource().sendFailure(Component.literal(e.getMessage()));
            return 0;
        } catch (Throwable t) {
            c.getSource().sendFailure(Component.literal("[KeyBridge] flipcam failed: " + t));
            return 0;
        }
    }

    /** <x> <y> <z> <yaw> <pitch> [then] */
    private static RequiredArgumentBuilder<CommandSourceStack, Double> pose(
            RequiredArgumentBuilder<CommandSourceStack, Float> then, com.mojang.brigadier.Command<CommandSourceStack> run) {
        RequiredArgumentBuilder<CommandSourceStack, Float> pitch = Commands.argument("pitch", FloatArgumentType.floatArg()).executes(run);
        if (then != null) pitch = pitch.then(then);
        return Commands.argument("x", DoubleArgumentType.doubleArg()).then(Commands.argument("y", DoubleArgumentType.doubleArg())
                .then(Commands.argument("z", DoubleArgumentType.doubleArg()).then(Commands.argument("yaw", FloatArgumentType.floatArg())
                        .then(pitch))));
    }

    private int status(CommandSourceStack src) {
        Optional<MinecraftServer.ServerResourcePackInfo> base = src.getServer().getServerResourcePack();
        String b = base.map(i -> i.url() + " " + i.hash()).orElse("none");
        String l = latest == null ? "none" : latest.url() + " " + latest.hash();
        String mode = polymerPackId().map(u -> " | Polymer autohost: on (pushes replace pack " + u + ")").orElse("");
        src.sendSuccess(() -> Component.literal("[KeyBridge] pushed: " + l + " | server pack for new joins: " + b + mode
                + " | usage: /packpush <url> <sha1> [prompt], /packpop"), false);
        return latest == null ? 0 : 1;
    }

    private int push(CommandSourceStack src, String args) {
        String[] a = args.trim().split("\\s+", 3);
        if (a.length < 2) {
            src.sendFailure(Component.literal("[KeyBridge] usage: /packpush <url> <sha1> [prompt]"));
            return 0;
        }
        String url = a[0].replaceAll("^\"|\"$", "");
        String hash = a[1].toLowerCase();
        if (!url.matches("https?://\\S+")) {
            src.sendFailure(Component.literal("[KeyBridge] the url must start with http:// or https://"));
            return 0;
        }
        if (!hash.matches("[0-9a-f]{40}")) {
            src.sendFailure(Component.literal("[KeyBridge] the sha1 must be 40 hex characters"));
            return 0;
        }
        MinecraftServer server = src.getServer();
        Optional<Component> prompt = a.length > 2 ? Optional.of(Component.literal(a[2])) : Optional.empty();
        latest = new Pack(url, hash, server.isResourcePackRequired(), prompt);
        boolean adopted = adopt(server, url, hash);
        int n = 0, same = 0;
        for (ServerPlayer p : server.getPlayerList().getPlayers()) {
            Optional<MinecraftServer.ServerResourcePackInfo> base = joinPack.getOrDefault(p.getUUID(), Optional.empty());
            joinPack.put(p.getUUID(), base);
            if (base.isPresent() && base.get().hash().equalsIgnoreCase(hash) && !popped.contains(p.getUUID())) {
                same++;   // logged in with this very pack already
                continue;
            }
            send(p, base);
            n++;
        }
        final int sent = n, had = same;
        src.sendSuccess(() -> Component.literal("[KeyBridge] pushed " + url + " (" + hash + ") to " + sent + " player(s)"
                + (had > 0 ? " (" + had + " already had it)" : "") + "; "
                + (adopted ? "new joins get it at login (server.properties adopted)"
                           : "new joins get it right after login (server.properties differs or could not be adopted)")), true);
        return Math.max(sent, 1);
    }

    private int pop(CommandSourceStack src) {
        if (polymerPackId().isPresent()) {
            src.sendFailure(Component.literal("[KeyBridge] Polymer autohost is on: the pushed pack replaced Polymer's in place, so there is nothing to pop (run /polymer generate-pack + /packpush to go back)"));
            return 0;
        }
        if (latest == null) {
            src.sendFailure(Component.literal("[KeyBridge] nothing is pushed"));
            return 0;
        }
        latest = null;
        int n = 0;
        for (ServerPlayer p : src.getServer().getPlayerList().getPlayers()) {
            p.connection.send(new ClientboundResourcePackPopPacket(Optional.of(PUSH_ID)));
            Optional<MinecraftServer.ServerResourcePackInfo> base = joinPack.getOrDefault(p.getUUID(), Optional.empty());
            if (popped.remove(p.getUUID()) && base.isPresent()) {
                MinecraftServer.ServerResourcePackInfo i = base.get();
                p.connection.send(new ClientboundResourcePackPushPacket(i.id(), i.url(), i.hash(), i.isRequired(), Optional.ofNullable(i.prompt())));
            }
            n++;
        }
        final int sent = n;
        src.sendSuccess(() -> Component.literal("[KeyBridge] removed the pushed pack for " + sent + " player(s)"), true);
        return Math.max(sent, 1);
    }

    // ───────────────────────────── flip camera ─────────────────────────────
    /** The spider's eye height at scale 1 (0.65); read when first needed, not while the mod loads. */
    private static float spiderEye() { return EntityTypes.SPIDER.getDimensions().eyeHeight(); }

    private int flipStart(CommandContext<CommandSourceStack> c, float eyeOverride) throws Exception {
        ServerPlayer p = EntityArgument.getPlayer(c, "player");
        double x = DoubleArgumentType.getDouble(c, "x"), y = DoubleArgumentType.getDouble(c, "y"), z = DoubleArgumentType.getDouble(c, "z");
        float yaw = FloatArgumentType.getFloat(c, "yaw"), pitch = Mth.clamp(FloatArgumentType.getFloat(c, "pitch"), -90f, 90f);
        Flip old = flips.remove(p.getUUID());
        float want = eyeOverride >= 0 ? eyeOverride : p.getCamera().getEyeHeight();
        float scale = Mth.clamp(want / spiderEye(), 0.0625f, 16f);
        Flip f = new Flip();
        f.player = p;
        f.level = p.level();
        f.id = nextFakeId--;
        f.eye = spiderEye() * scale;
        f.spider = new Spider(EntityTypes.SPIDER, p.level());   // never added to the level: only its data is used
        f.spider.setId(f.id);
        f.spider.setUUID(UUID.randomUUID());
        f.spider.setInvisible(true);
        f.spider.setSilent(true);
        f.spider.setNoGravity(true);
        AttributeInstance sc = f.spider.getAttribute(Attributes.SCALE);
        if (sc != null) sc.setBaseValue(scale);
        f.x = x; f.y = y - f.eye; f.z = z;
        f.spider.snapTo(f.x, f.y, f.z, yaw, pitch);
        f.spider.setYHeadRot(yaw);
        p.connection.send(new ClientboundAddEntityPacket(f.id, f.spider.getUUID(), f.x, f.y, f.z, pitch, yaw, EntityTypes.SPIDER, 0, Vec3.ZERO, yaw));
        p.connection.send(new ClientboundSetEntityDataPacket(f.id, f.spider.getEntityData().getNonDefaultValues()));
        if (sc != null) p.connection.send(new ClientboundUpdateAttributesPacket(f.id, java.util.List.of(sc)));
        p.connection.send(new ClientboundSetCameraPacket(f.spider));
        // the add packet carries rotations as bytes: the client starts from those, the next move corrects it
        f.xRot = Mth.unpackDegrees(Mth.packDegrees(pitch));
        f.yRot = Mth.unpackDegrees(Mth.packDegrees(yaw));
        f.head = f.yRot;
        sendMove(f, x, y, z, yaw, pitch);
        if (old != null && old.player == p) p.connection.send(new ClientboundRemoveEntitiesPacket(old.id));
        flips.put(p.getUUID(), f);
        final float eye = f.eye, sc2 = scale;
        c.getSource().sendSuccess(() -> Component.literal(String.format(java.util.Locale.ROOT,
                "[KeyBridge] flip camera on for %s (fake spider #%d, eye height %.3f = scale %.3f)%s",
                p.getScoreboardName(), f.id, eye, sc2, old != null ? ", replaced the previous one" : "")), false);
        return 1;
    }

    private int flipMove(CommandContext<CommandSourceStack> c) throws Exception {
        ServerPlayer p = EntityArgument.getPlayer(c, "player");
        Flip f = flips.get(p.getUUID());
        if (f == null) {
            c.getSource().sendFailure(Component.literal("[KeyBridge] no flip camera for " + p.getScoreboardName() + " — /flipcam start first"));
            return 0;
        }
        sendMove(f, DoubleArgumentType.getDouble(c, "x"), DoubleArgumentType.getDouble(c, "y"), DoubleArgumentType.getDouble(c, "z"),
                FloatArgumentType.getFloat(c, "yaw"), Mth.clamp(FloatArgumentType.getFloat(c, "pitch"), -90f, 90f));
        return 1;   // silent: this runs every tick
    }

    /**
     * The client moves a mob 1/3 of the way to the latest target each tick (3-step interpolation, restarted by every
     * packet), which trails ~2 ticks behind a moving target. Sending target = have + 3 × (want − have) makes the client
     * land exactly on "want" after its next tick; if a packet comes late, the error shrinks by 2/3 per tick.
     */
    private void sendMove(Flip f, double x, double eyeY, double z, float yaw, float pitch) {
        double y = eyeY - f.eye;
        double dx = x - f.x, dy = y - f.y, dz = z - f.z;
        double dist = Math.sqrt(dx * dx + dy * dy + dz * dz);
        Vec3 target;
        if (dist * 3 > 60) {            // a jump: the client snaps beyond 64 blocks, so send the point itself
            target = new Vec3(x, y, z);
            if (dist > 64) { f.x = x; f.y = y; f.z = z; } else { f.x += dx / 3; f.y += dy / 3; f.z += dz / 3; }
        } else {
            target = new Vec3(f.x + 3 * dx, f.y + 3 * dy, f.z + 3 * dz);
            f.x = x; f.y = y; f.z = z;
        }
        float tPitch = f.xRot + 3 * (pitch - f.xRot);
        float tYaw = f.yRot + 3 * Mth.wrapDegrees(yaw - f.yRot);
        f.xRot = pitch;
        f.yRot = yaw;
        byte tHead = Mth.packDegrees(f.head + 3 * Mth.wrapDegrees(yaw - f.head));
        f.head = f.head + Mth.wrapDegrees(Mth.unpackDegrees(tHead) - f.head) / 3;   // head packets are bytes: model what the client gets
        f.player.connection.send(ClientboundTeleportEntityPacket.teleport(f.id, new PositionMoveRotation(target, Vec3.ZERO, tYaw, tPitch), java.util.Set.of(), false));
        f.player.connection.send(new ClientboundRotateHeadPacket(f.spider, tHead));
    }

    private int flipStop(CommandContext<CommandSourceStack> c, UUID camera) throws Exception {
        ServerPlayer p = EntityArgument.getPlayer(c, "player");
        Flip f = flips.remove(p.getUUID());
        Entity target = camera != null ? p.level().getEntity(camera) : null;
        String note = camera != null && target == null ? " (entity " + camera + " not found — used the player's own camera)" : "";
        if (target == null) target = p.getCamera();
        p.connection.send(new ClientboundSetCameraPacket(target));
        if (f != null) p.connection.send(new ClientboundRemoveEntitiesPacket(f.id));
        final String who = target == p ? "the player" : target.getType().toShortString() + " " + target.getUUID();
        c.getSource().sendSuccess(() -> Component.literal("[KeyBridge] flip camera " + (f != null ? "off" : "was not on") + " for "
                + p.getScoreboardName() + "; camera → " + who + note), false);
        return f != null ? 1 : 0;
    }

    private int flipStatus(CommandSourceStack src) {
        StringBuilder b = new StringBuilder("[KeyBridge] flip cameras: " + flips.size());
        for (Flip f : flips.values()) b.append(String.format(java.util.Locale.ROOT, " | %s #%d at %.2f %.2f %.2f yaw %.1f pitch %.1f",
                f.player.getScoreboardName(), f.id, f.x, f.y + f.eye, f.z, f.yRot, f.xRot));
        b.append(" | usage: /flipcam start|move <player> <x> <y> <z> <yaw> <pitch> [eye_height], /flipcam stop <player> [camera_uuid]");
        src.sendSuccess(() -> Component.literal(b.toString()), false);
        return flips.size();
    }

    /** Disconnect, death, respawn (a new player object) or another dimension: the fake is gone or wrong — clean up. */
    private void flipWatch(MinecraftServer server) {
        var it = flips.entrySet().iterator();
        while (it.hasNext()) {
            Flip f = it.next().getValue();
            ServerPlayer now = server.getPlayerList().getPlayer(f.player.getUUID());
            if (now == null) { it.remove(); continue; }
            if (now != f.player || now.level() != f.level || !now.isAlive()) {
                now.connection.send(new ClientboundSetCameraPacket(now.getCamera()));
                now.connection.send(new ClientboundRemoveEntitiesPacket(f.id));
                it.remove();
            }
        }
    }

    /**
     * When server.properties on disk already names this url + sha1, make the running server use it for new logins
     * (DedicatedServerSettings.update re-reads nothing else and writes the same file back). Returns false otherwise.
     */
    private boolean adopt(MinecraftServer server, String url, String hash) {
        if (!(server instanceof DedicatedServer ds)) return false;
        try {
            DedicatedServerProperties fresh = DedicatedServerProperties.fromFile(Path.of("server.properties"));
            Optional<MinecraftServer.ServerResourcePackInfo> info = fresh.serverResourcePackInfo;
            if (info.isEmpty() || !info.get().url().equals(url) || !info.get().hash().equalsIgnoreCase(hash)) return false;
            Field f = DedicatedServer.class.getDeclaredField("settings");
            f.setAccessible(true);
            DedicatedServerSettings settings = (DedicatedServerSettings) f.get(ds);
            settings.update(old -> fresh);
            return server.getServerResourcePack().map(i -> i.hash().equalsIgnoreCase(hash)).orElse(false);
        } catch (Throwable t) {
            System.err.println("[KeyBridge] could not adopt server.properties: " + t);
            return false;
        }
    }
}
