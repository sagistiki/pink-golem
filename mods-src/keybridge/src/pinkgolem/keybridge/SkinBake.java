package pinkgolem.keybridge;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.function.Consumer;
import java.util.zip.CRC32;
import java.util.zip.Deflater;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

/**
 * Skin baking for the in-game easel (skinpaint.sc) — no Minecraft classes here, so it can be tested on its own.
 *
 * Input: <dir>/bake/<id>.json = {"img": [4096 ARGB numbers, row-major 64x64, 0 = transparent], "variant": "classic",
 * "name": "..."} written by the scarpet app. Output: <dir>/png/<id>.png, then the PNG is uploaded to MineSkin
 * (api.mineskin.org/v2/generate, works without an API key: ~10/min, 6 s apart) which signs it with a Minecraft account
 * and returns the textures.minecraft.net URL plus the signed texture property. One worker thread, one bake at a time,
 * MineSkin's "next request" time is respected.
 */
public final class SkinBake {
    public record Result(String id, boolean ok, String url, String value, String signature, String error) {}

    private static final String API = "https://api.mineskin.org/v2/generate";
    private static final String AGENT = "PinkGolem-KeyBridge/1.3 (+skin easel)";
    private final ExecutorService worker = Executors.newSingleThreadExecutor(r -> {
        Thread t = new Thread(r, "KeyBridge-SkinBake");
        t.setDaemon(true);
        return t;
    });
    private final HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(15)).build();
    private final String apiKey;
    private volatile long nextAllowed = 0;

    public SkinBake(String apiKey) {
        this.apiKey = apiKey == null ? "" : apiKey.trim();
    }

    public static boolean validId(String id) {
        return id != null && id.matches("[A-Za-z0-9_-]{1,64}");
    }

    /** Queue a bake; done() is called on the worker thread (hand it to the server thread yourself). */
    public void bake(Path dir, String id, Consumer<Result> done) {
        worker.submit(() -> {
            Result r;
            try {
                r = run(dir, id);
            } catch (Throwable t) {
                r = new Result(id, false, null, null, null, String.valueOf(t.getMessage() == null ? t : t.getMessage()));
            }
            done.accept(r);
        });
    }

    private Result run(Path dir, String id) throws Exception {
        if (!validId(id)) return new Result(id, false, null, null, null, "bad id");
        Path in = dir.resolve("bake").resolve(id + ".json");
        if (!Files.exists(in)) return new Result(id, false, null, null, null, "no bake file");
        JsonObject o = JsonParser.parseString(Files.readString(in, StandardCharsets.UTF_8)).getAsJsonObject();
        JsonArray a = o.getAsJsonArray("img");
        if (a == null || a.size() != 4096) return new Result(id, false, null, null, null, "img must have 4096 pixels");
        int[] argb = new int[4096];
        for (int i = 0; i < 4096; i++) argb[i] = (int) a.get(i).getAsLong();
        byte[] png = png64(argb);
        Path out = dir.resolve("png");
        Files.createDirectories(out);
        Files.write(out.resolve(id + ".png"), png);
        String variant = o.has("variant") ? o.get("variant").getAsString() : "classic";
        if (!variant.equals("slim")) variant = "classic";
        String name = o.has("name") ? o.get("name").getAsString() : id;
        return upload(id, png, variant, name, 0);
    }

    private Result upload(String id, byte[] png, String variant, String name, int attempt) throws Exception {
        long wait = nextAllowed - System.currentTimeMillis();
        if (wait > 0) Thread.sleep(Math.min(wait, 60_000));
        String boundary = "----pinkgolem" + UUID.randomUUID().toString().replace("-", "");
        ByteArrayOutputStream body = new ByteArrayOutputStream();
        field(body, boundary, "variant", variant);
        field(body, boundary, "visibility", "unlisted");
        field(body, boundary, "name", name.replaceAll("[^A-Za-z0-9_ -]", "").trim().isEmpty() ? id : name.replaceAll("[^A-Za-z0-9_ -]", "").trim());
        body.write(("--" + boundary + "\r\nContent-Disposition: form-data; name=\"file\"; filename=\"" + id
                + ".png\"\r\nContent-Type: image/png\r\n\r\n").getBytes(StandardCharsets.UTF_8));
        body.write(png);
        body.write(("\r\n--" + boundary + "--\r\n").getBytes(StandardCharsets.UTF_8));
        HttpRequest.Builder rq = HttpRequest.newBuilder(URI.create(API)).timeout(Duration.ofSeconds(90))
                .header("User-Agent", AGENT).header("Accept", "application/json")
                .header("Content-Type", "multipart/form-data; boundary=" + boundary)
                .POST(HttpRequest.BodyPublishers.ofByteArray(body.toByteArray()));
        if (!apiKey.isEmpty()) rq.header("Authorization", "Bearer " + apiKey);
        HttpResponse<String> resp = http.send(rq.build(), HttpResponse.BodyHandlers.ofString());
        JsonObject j;
        try {
            j = JsonParser.parseString(resp.body()).getAsJsonObject();
        } catch (Exception e) {
            return new Result(id, false, null, null, null, "HTTP " + resp.statusCode());
        }
        try {   // remember when MineSkin lets us ask again
            long next = j.getAsJsonObject("rateLimit").getAsJsonObject("next").get("absolute").getAsLong();
            nextAllowed = Math.max(nextAllowed, next);
        } catch (Exception ignored) {
            nextAllowed = System.currentTimeMillis() + 6000;
        }
        if (resp.statusCode() == 429 && attempt < 2) {
            nextAllowed = Math.max(nextAllowed, System.currentTimeMillis() + 7000);
            return upload(id, png, variant, name, attempt + 1);
        }
        if (!j.has("success") || !j.get("success").getAsBoolean()) {
            String msg = "MineSkin " + resp.statusCode();
            try {
                msg = j.getAsJsonArray("errors").get(0).getAsJsonObject().get("message").getAsString();
            } catch (Exception ignored) {
            }
            return new Result(id, false, null, null, null, msg);
        }
        JsonObject tex = j.getAsJsonObject("skin").getAsJsonObject("texture");
        String url = tex.getAsJsonObject("url").get("skin").getAsString();
        JsonObject data = tex.getAsJsonObject("data");
        return new Result(id, true, url, data.get("value").getAsString(), data.get("signature").getAsString(), null);
    }

    private static void field(ByteArrayOutputStream b, String boundary, String name, String value) throws IOException {
        b.write(("--" + boundary + "\r\nContent-Disposition: form-data; name=\"" + name + "\"\r\n\r\n" + value + "\r\n")
                .getBytes(StandardCharsets.UTF_8));
    }

    /** A 64x64 RGBA PNG from ARGB ints (row-major). */
    public static byte[] png64(int[] argb) throws IOException {
        ByteArrayOutputStream raw = new ByteArrayOutputStream();
        for (int y = 0; y < 64; y++) {
            raw.write(0);                                   // filter: none
            for (int x = 0; x < 64; x++) {
                int c = argb[y * 64 + x];
                raw.write((c >> 16) & 255);
                raw.write((c >> 8) & 255);
                raw.write(c & 255);
                raw.write((c >>> 24) & 255);
            }
        }
        Deflater def = new Deflater(9);
        def.setInput(raw.toByteArray());
        def.finish();
        ByteArrayOutputStream z = new ByteArrayOutputStream();
        byte[] buf = new byte[8192];
        while (!def.finished()) z.write(buf, 0, def.deflate(buf));
        def.end();
        ByteArrayOutputStream png = new ByteArrayOutputStream();
        png.write(new byte[]{(byte) 0x89, 'P', 'N', 'G', '\r', '\n', 0x1a, '\n'});
        ByteArrayOutputStream ihdr = new ByteArrayOutputStream();
        int32(ihdr, 64); int32(ihdr, 64);
        ihdr.write(8); ihdr.write(6); ihdr.write(0); ihdr.write(0); ihdr.write(0);
        chunk(png, "IHDR", ihdr.toByteArray());
        chunk(png, "IDAT", z.toByteArray());
        chunk(png, "IEND", new byte[0]);
        return png.toByteArray();
    }

    private static void int32(ByteArrayOutputStream o, int v) {
        o.write(v >>> 24); o.write((v >>> 16) & 255); o.write((v >>> 8) & 255); o.write(v & 255);
    }

    private static void chunk(ByteArrayOutputStream o, String type, byte[] data) throws IOException {
        int32(o, data.length);
        byte[] t = type.getBytes(StandardCharsets.US_ASCII);
        o.write(t);
        o.write(data);
        CRC32 crc = new CRC32();
        crc.update(t);
        crc.update(data);
        int32(o, (int) crc.getValue());
    }

    /** Stand-alone test: java -cp <gson>:out pinkgolem.keybridge.SkinBake <dir> <id> */
    public static void main(String[] args) throws Exception {
        SkinBake b = new SkinBake(System.getenv("MINESKIN_KEY"));
        Result r = b.run(Path.of(args[0]), args[1]);
        System.out.println(r.ok() ? ("OK " + r.url() + " value=" + r.value().length() + " sig=" + r.signature().length()) : ("FAIL " + r.error()));
    }
}
