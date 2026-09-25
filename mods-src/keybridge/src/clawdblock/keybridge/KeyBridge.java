package clawdblock.keybridge;

import java.lang.reflect.Field;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;

import com.mojang.brigadier.CommandDispatcher;
import com.mojang.brigadier.arguments.StringArgumentType;

import net.fabricmc.api.ModInitializer;
import net.fabricmc.fabric.api.command.v2.CommandRegistrationCallback;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.Commands;
import net.minecraft.network.chat.Component;
import net.minecraft.network.protocol.common.ClientboundResourcePackPopPacket;
import net.minecraft.network.protocol.common.ClientboundResourcePackPushPacket;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.ServerScoreboard;
import net.minecraft.server.dedicated.DedicatedServer;
import net.minecraft.server.dedicated.DedicatedServerProperties;
import net.minecraft.server.dedicated.DedicatedServerSettings;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.entity.player.Input;
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
    private boolean keysBroken = false;
    private boolean packBroken = false;

    @Override
    public void onInitialize() {
        try {
            ServerTickEvents.START_SERVER_TICK.register(this::safeTick);
        } catch (Throwable t) {
            System.err.println("[KeyBridge] keys disabled: " + t);
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

    // ───────────────────────────── live resource pack ─────────────────────────────
    /** A player who is new in the player list has finished logging in (and got the server.properties pack then). */
    private void joins(MinecraftServer server) {
        Set<UUID> now = new HashSet<>();
        for (ServerPlayer p : server.getPlayerList().getPlayers()) {
            UUID u = p.getUUID();
            now.add(u);
            if (joinPack.containsKey(u)) continue;
            Optional<MinecraftServer.ServerResourcePackInfo> base = server.getServerResourcePack();
            joinPack.put(u, base);
            if (latest != null && !(base.isPresent() && base.get().hash().equalsIgnoreCase(latest.hash()))) send(p, base);
        }
        joinPack.keySet().retainAll(now);
        popped.retainAll(now);
    }

    private void send(ServerPlayer p, Optional<MinecraftServer.ServerResourcePackInfo> base) {
        if (base.isPresent() && !base.get().hash().equalsIgnoreCase(latest.hash())) {
            p.connection.send(new ClientboundResourcePackPopPacket(Optional.of(base.get().id())));
            popped.add(p.getUUID());
        }
        p.connection.send(new ClientboundResourcePackPushPacket(PUSH_ID, latest.url(), latest.hash(), latest.required(), latest.prompt()));
    }

    private void register(CommandDispatcher<CommandSourceStack> d) {
        d.register(Commands.literal("packpush").requires(Commands.hasPermission(Commands.LEVEL_GAMEMASTERS))
                .executes(c -> status(c.getSource()))
                .then(Commands.argument("args", StringArgumentType.greedyString())
                        .executes(c -> push(c.getSource(), StringArgumentType.getString(c, "args")))));
        d.register(Commands.literal("packpop").requires(Commands.hasPermission(Commands.LEVEL_GAMEMASTERS))
                .executes(c -> pop(c.getSource())));
    }

    private int status(CommandSourceStack src) {
        Optional<MinecraftServer.ServerResourcePackInfo> base = src.getServer().getServerResourcePack();
        String b = base.map(i -> i.url() + " " + i.hash()).orElse("none");
        String l = latest == null ? "none" : latest.url() + " " + latest.hash();
        src.sendSuccess(() -> Component.literal("[KeyBridge] pushed: " + l + " | server pack for new joins: " + b
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
