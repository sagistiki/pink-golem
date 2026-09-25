#!/usr/bin/env python3
"""ClawdBlock — set up and run a Minecraft server that an AI can build in.

    python3 clawdblock.py setup            interactive install (server + mods + MCP + AI clients)
    python3 clawdblock.py start            start the server (console in this terminal; type "stop" to quit)
    python3 clawdblock.py start --background   start it in the background (logs in server/logs/)
    python3 clawdblock.py stop | status | doctor
    python3 clawdblock.py mods [list|add|remove|update] [names...]
    python3 clawdblock.py apps [list|add|remove] [names...]    scarpet game-logic apps in the world
    python3 clawdblock.py connect [claude-code|claude-desktop|gemini|codex|lmstudio|all|print]
    python3 clawdblock.py new-world
    python3 clawdblock.py backup [--keep 3] [--dry-run] [--include-ledger] [--dest DIR]

Only the Python standard library is used. Works on macOS, Linux and Windows.
"""
import argparse
import json
import os
import platform
import random
import re
import shutil
import socket
import ssl
import string
import struct
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "clawdblock.json"
MC_VERSION = "26.2"          # tested version. Newer ones usually work: setup --mc-version 26.3 (see docs/upgrading.md)
JAVA_MIN = 25                 # Minecraft 26.x needs Java 25
NODE_MIN = 20
UA = "clawdblock/1.0 (github.com/sagistiki/clawdblock)"
WIN = os.name == "nt"

# Mods: key → (modrinth slug, tier, what it gives the AI / the players)
MODS = {
    "fabric-api": ("fabric-api", "required", "Fabric's shared library; almost every mod needs it."),
    "carpet": ("carpet", "required", "The AI's body (fake players), scarpet scripting, undo snapshots, vision and checks."),
    "lithium": ("lithium", "recommended", "Server performance. Invisible, just makes big builds lag less."),
    "worldedit": ("worldedit", "recommended", "Big edits (//set, //replace, //copy, //paste) for you and the AI (minecraft_worldedit)."),
    "bluemap": ("bluemap", "recommended", "3D web map of your world at http://localhost:8100; the AI can take real-texture screenshots."),
    "essential-commands": ("essential-commands", "recommended", "/warp, /home, /spawn, /tpa for players; the AI sets warps to its builds."),
    "spark": ("spark", "recommended", "Lag profiler (/spark tps) when the server gets slow."),
    "chunky": ("chunky", "optional", "Pre-generate the world so exploring doesn't lag."),
    "polydecorations": ("polydecorations", "optional", "Server-side furniture blocks (benches, tables, baskets…) — no client mod needed."),
    "polymer": ("polymer", "optional", "Library for Polydecorations (added automatically)."),
    "ledger": ("ledger", "optional", "Block logging and rollback for multiplayer servers."),
    "carpet-extra": ("carpet-extra", "optional", "Extra Carpet rules."),
}
DEPS = {"polydecorations": ["polymer"], "carpet-extra": ["carpet"]}
CORE_APPS = ["cu", "helpers", "bubble"]   # scarpet apps the MCP needs (from skill/clawdblock/scripts)

# ───────────────────────────── small helpers ─────────────────────────────
if WIN:
    os.system("")  # constant empty command: the documented trick that turns on ANSI colours in Windows 10+ consoles
COL = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
def c(code, s): return f"\033[{code}m{s}\033[0m" if COL else s
def ok(s): print(c("32", "✓ ") + s)
def warn(s): print(c("33", "! ") + s)
def err(s): print(c("31", "✗ ") + s)
def info(s): print(c("36", "• ") + s)
def head(s): print("\n" + c("1;35", s))

ASSUME_YES = False
def ask(q, default=""):
    if ASSUME_YES:
        return default
    try:
        a = input(f"{q} {c('2', f'[{default}]') if default else ''}: ").strip()
    except EOFError:
        a = ""
    return a or default
def yes(q, default=True):
    if ASSUME_YES:
        return default
    a = ask(q + (" (Y/n)" if default else " (y/N)"), "y" if default else "n").lower()
    return a.startswith("y")

def load_cfg():
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
def save_cfg(cfg):
    CONFIG.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

def server_dir(cfg=None):
    cfg = cfg or load_cfg()
    p = Path(cfg.get("server_dir", "server"))
    return p if p.is_absolute() else ROOT / p

def read_props(sd):
    out = {}
    f = sd / "server.properties"
    if f.exists():
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out
def write_props(sd, updates):
    f = sd / "server.properties"
    lines = f.read_text(encoding="utf-8").splitlines() if f.exists() else ["#Minecraft server properties (ClawdBlock)"]
    seen = set()
    for i, line in enumerate(lines):
        if "=" in line and not line.startswith("#"):
            k = line.split("=", 1)[0].strip()
            if k in updates:
                lines[i] = f"{k}={updates[k]}"
                seen.add(k)
    lines += [f"{k}={v}" for k, v in updates.items() if k not in seen]
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")

def level_dir(sd):
    return sd / read_props(sd).get("level-name", "world")

# ── downloads: urllib first; if SSL/proxy breaks it (common with python.org builds on macOS), curl or PowerShell
def http_get(url, binary=True):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        ctx = None
        try:
            import certifi  # optional
            ctx = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            pass
        with urllib.request.urlopen(req, timeout=60, context=ctx) as r:
            data = r.read()
    except Exception as e:  # noqa: BLE001 — fall back to the system's own downloader
        data = None
        if shutil.which("curl"):
            p = subprocess.run(["curl", "-fsSL", "-A", UA, url], capture_output=True)
            if p.returncode == 0:
                data = p.stdout
        if data is None and WIN:   # Windows 10+ ships curl.exe; this is the last resort
            tmp = Path(os.environ.get("TEMP", ".")) / "clawdblock.download"
            ps = f"[Net.ServicePointManager]::SecurityProtocol='Tls12'; Invoke-WebRequest -UseBasicParsing -UserAgent '{UA}' -Uri '{url}' -OutFile '{tmp}'"
            p = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True)
            if p.returncode == 0 and tmp.exists():
                data = tmp.read_bytes()
                tmp.unlink()
        if data is None:
            raise RuntimeError(f"download failed: {url} ({e})") from e
    return data if binary else data.decode("utf-8")
def get_json(url):
    return json.loads(http_get(url, binary=False))
def download(url, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = http_get(url)
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.write_bytes(data)
    tmp.replace(dest)
    return len(data)

def modrinth_version(slug, mc):
    q = urllib.parse.urlencode({"game_versions": json.dumps([mc]), "loaders": json.dumps(["fabric"])})
    vs = get_json(f"https://api.modrinth.com/v2/project/{slug}/version?{q}")
    if not vs:
        return None
    rel = [v for v in vs if v.get("version_type") == "release"] or vs
    v = rel[0]
    f = next((x for x in v["files"] if x.get("primary")), v["files"][0])
    return {"version": v["version_number"], "url": f["url"], "filename": f["filename"]}

# ── tool checks
def run_out(cmd):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=20, shell=False)
        return (p.stdout + p.stderr).strip()
    except Exception:  # noqa: BLE001
        return ""
def java_bin():
    home = os.environ.get("JAVA_HOME")
    if home and (Path(home) / "bin" / ("java.exe" if WIN else "java")).exists():
        return str(Path(home) / "bin" / ("java.exe" if WIN else "java"))
    return shutil.which("java")
def java_version():
    j = java_bin()
    if not j:
        return None, None
    m = re.search(r'version "(\d+)', run_out([j, "-version"]))
    return j, (int(m.group(1)) if m else None)
def node_version():
    n = shutil.which("node")
    if not n:
        return None, None
    m = re.search(r"v(\d+)", run_out([n, "--version"]))
    return n, (int(m.group(1)) if m else None)
def python_cmd():
    return sys.executable or ("py" if WIN else "python3")

INSTALL_HINTS = {
    "java": {"Darwin": "brew install --cask temurin@25   (or download: https://adoptium.net/temurin/releases/?version=25)",
             "Windows": "winget install EclipseAdoptium.Temurin.25.JDK   (or https://adoptium.net/temurin/releases/?version=25)",
             "Linux": "sudo apt install openjdk-25-jre-headless   (or https://adoptium.net/temurin/releases/?version=25)"},
    "node": {"Darwin": "brew install node   (or https://nodejs.org — the LTS installer)",
             "Windows": "winget install OpenJS.NodeJS.LTS   (or https://nodejs.org)",
             "Linux": "sudo apt install nodejs npm   (Node 20+; or https://nodejs.org / nvm)"},
}
def hint(tool):
    return INSTALL_HINTS[tool].get(platform.system(), INSTALL_HINTS[tool]["Linux"])

def total_ram_mb():
    try:
        if WIN:
            import ctypes
            class MS(ctypes.Structure):
                _fields_ = [("l", ctypes.c_ulong), ("m", ctypes.c_ulong), ("t", ctypes.c_ulonglong), ("a", ctypes.c_ulonglong),
                            ("tp", ctypes.c_ulonglong), ("ap", ctypes.c_ulonglong), ("tv", ctypes.c_ulonglong), ("av", ctypes.c_ulonglong), ("e", ctypes.c_ulonglong)]
            s = MS(); s.l = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s))
            return s.t // 1048576
        if sys.platform == "darwin":
            return int(run_out(["sysctl", "-n", "hw.memsize"])) // 1048576
        for line in open("/proc/meminfo"):
            if line.startswith("MemTotal"):
                return int(line.split()[1]) // 1024
    except Exception:  # noqa: BLE001
        pass
    return 8192

def port_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0

# ── minimal RCON client (for stop / status / first-start setup)
class Rcon:
    def __init__(self, host, port, password):
        self.s = socket.create_connection((host, port), timeout=5)
        self._send(3, password)
        rid, _, _ = self._recv()
        if rid == -1:
            raise RuntimeError("RCON login failed (wrong rcon.password)")
    def _send(self, typ, body):
        b = body.encode("utf-8")
        self.s.sendall(struct.pack("<iii", len(b) + 10, 7, typ) + b + b"\0\0")
    def _recv(self):
        n = struct.unpack("<i", self._read(4))[0]
        d = self._read(n)
        rid, typ = struct.unpack("<ii", d[:8])
        return rid, typ, d[8:-2].decode("utf-8", errors="replace")
    def _read(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.s.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("RCON connection closed")
            buf += chunk
        return buf
    def cmd(self, c):
        self._send(2, c)
        return re.sub("§.", "", self._recv()[2])
    def close(self):
        self.s.close()
def rcon(sd=None):
    cfg = load_cfg()
    sd = sd or server_dir(cfg)
    p = read_props(sd)
    return Rcon("127.0.0.1", int(p.get("rcon.port", 25575)), p.get("rcon.password", ""))
def server_up(sd=None):
    try:
        r = rcon(sd); r.close()
        return True
    except Exception:  # noqa: BLE001
        return False

# ───────────────────────────── setup ─────────────────────────────
def cmd_setup(a):
    global ASSUME_YES
    ASSUME_YES = a.yes
    cfg = load_cfg()
    print(c("1;35", "\n  ClawdBlock setup") + c("2", f"   Minecraft {a.mc_version or cfg.get('mc_version', MC_VERSION)} · Fabric · Carpet · MCP\n"))

    head("1/7  Checking your computer")
    j, jv = java_version()
    if jv and jv >= JAVA_MIN:
        ok(f"Java {jv} ({j})")
    else:
        err(f"Java {JAVA_MIN}+ is needed (found: {jv or 'none'}). Install it:\n    {hint('java')}")
        if not yes("Continue anyway (you can install Java later)?", False):
            return 1
    n, nv = node_version()
    if nv and nv >= NODE_MIN:
        ok(f"Node {nv} (for the MCP server)")
    else:
        warn(f"Node {NODE_MIN}+ is needed for the AI connection (found: {nv or 'none'}). Install it:\n    {hint('node')}")
    ok(f"Python {platform.python_version()}")
    ok(f"{total_ram_mb() // 1024} GB RAM")

    head("2/7  Server settings")
    sd = Path(ask("Server folder", cfg.get("server_dir", "server")))
    cfg["server_dir"] = str(sd)
    sd = sd if sd.is_absolute() else ROOT / sd
    mc = a.mc_version or cfg.get("mc_version", MC_VERSION)
    cfg["mc_version"] = mc
    existing = (sd / "server.properties").exists()
    props = read_props(sd)
    world_kind = "flat" if "flat" in props.get("level-type", "flat").lower() else "normal"
    if not existing:
        if a.world:
            world_kind = a.world
        else:
            print("  World type:\n    1) flat creative building world (recommended: clean ground, easy for the AI)\n    2) normal terrain (hills, trees, caves)")
            world_kind = "normal" if ask("Choose", "1") == "2" else "flat"
    port = int(a.port or props.get("server-port") or ask("Game port (players connect to this)", "25565"))
    if not existing and not port_free(port):
        warn(f"port {port} is in use (another server?) — pick another one with --port")
    rport = int(a.rcon_port or props.get("rcon.port", 25575))
    if not existing and not port_free(rport):
        rport = next(p for p in range(rport, rport + 100) if port_free(p))
    if a.memory:
        cfg["memory_mb"] = a.memory
    cfg["bot_name"] = a.bot_name or ask("Your AI's name in the game", cfg.get("bot_name", "Claude"))
    cfg.setdefault("chat_color", "light_purple")
    cfg.setdefault("bot_aliases", [cfg["bot_name"], "claude", "bot"])
    cfg.setdefault("crew", {"names": ["Alex_Builder", "Sam_Builder", "Riley_Builder", "Jordan_Builder"]})

    head("3/7  Minecraft server (Fabric)")
    loader = get_json("https://meta.fabricmc.net/v2/versions/loader/" + mc)
    if not loader:
        err(f"Fabric has no loader for Minecraft {mc}")
        return 1
    lv = loader[0]["loader"]["version"]
    iv = get_json("https://meta.fabricmc.net/v2/versions/installer")[0]["version"]
    jar = sd / "fabric-server-launch.jar"
    if jar.exists() and cfg.get("fabric") == [mc, lv, iv]:
        ok(f"Fabric server launcher already here (loader {lv})")
    else:
        size = download(f"https://meta.fabricmc.net/v2/versions/loader/{mc}/{lv}/{iv}/server/jar", jar)
        cfg["fabric"] = [mc, lv, iv]
        ok(f"Fabric server launcher {mc} / loader {lv} ({size // 1024} KB)")
    eula = sd / "eula.txt"
    if "eula=true" not in (eula.read_text() if eula.exists() else ""):
        print("  Minecraft's EULA: https://aka.ms/MinecraftEULA")
        # never accepted silently: --yes alone still needs --accept-eula (or an interactive yes)
        if a.accept_eula or (not ASSUME_YES and yes("Do you accept the Minecraft EULA?", False)):
            eula.write_text("eula=true\n")
            ok("EULA accepted")
        else:
            warn("Without accepting the EULA the server will not start. Edit server/eula.txt later.")
    pw = props.get("rcon.password") or "".join(random.choice(string.ascii_letters + string.digits) for _ in range(20))
    updates = {"enable-rcon": "true", "rcon.port": str(rport), "rcon.password": pw, "server-port": str(port),
               "broadcast-rcon-to-ops": "false", "enable-command-block": "true", "spawn-protection": "0"}
    if not existing:
        updates.update({"motd": "A ClawdBlock server — an AI builds here", "gamemode": "creative", "difficulty": "peaceful",
                        "allow-flight": "true", "max-players": "20", "view-distance": "12", "simulation-distance": "8",
                        "level-type": "minecraft:flat" if world_kind == "flat" else "minecraft:normal", "online-mode": "true"})
    write_props(sd, updates)
    ok(f"server.properties: RCON on port {rport} with a random password" + ("" if existing else f", {world_kind} creative world, peaceful"))

    head("4/7  Mods")
    have = installed_mods(sd)
    wanted = [k for k, (_, tier, _) in MODS.items() if tier == "required"]
    for k, (_, tier, why) in MODS.items():
        if tier == "recommended":
            if k in have or yes(f"  {c('1', k)}: {why} Install?", True):
                wanted.append(k)
    if not ASSUME_YES:
        for k, (_, tier, why) in MODS.items():
            if tier == "optional" and k != "polymer" and (k in have or yes(f"  {c('1', k)} (optional): {why} Install?", False)):
                wanted.append(k)
    install_mods(sd, mc, wanted, cfg)
    if "bluemap" in wanted and "bluemap_textures" not in cfg:
        cfg["bluemap_textures"] = yes("  BlueMap draws the map with Minecraft's own textures, downloaded from Mojang (covered by the\n"
                                      "  Minecraft EULA). Allow that download?", True)

    head("5/7  Game-logic apps (scarpet)")
    install_apps(sd, CORE_APPS)

    head("6/7  MCP server (the AI's hands and eyes)")
    npm = shutil.which("npm")
    if npm:
        p = subprocess.run([npm, "install", "--no-audit", "--no-fund", "--silent"], cwd=ROOT / "mcp-server", shell=WIN)
        (ok if p.returncode == 0 else err)("npm install in mcp-server/" + ("" if p.returncode == 0 else " failed — run it by hand"))
    else:
        warn("npm not found — install Node, then run: cd mcp-server && npm install")
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "jobs").mkdir(exist_ok=True)
    save_cfg(cfg)
    ok("clawdblock.json saved")

    head("7/7  Connect your AI")
    clients = [] if a.no_connect else detect_clients()
    if clients:
        info("Found: " + ", ".join(clients))
    for cl in clients:
        if yes(f"  Connect {cl}?", True):
            connect(cl, cfg)
    if not clients:
        info("No AI client found. Later: python3 clawdblock.py connect print   (shows the config to paste)")

    print(c("1;32", "\n  Done!") + " Next:\n"
          f"    1. Start the server:   {c('1', 'python3 clawdblock.py start')}   (first start builds the world, ~1 min)\n"
          f"    2. Join in Minecraft {mc}: Multiplayer → Add Server → localhost" + ("" if port == 25565 else f":{port}") + "\n"
          f"    3. Make yourself op in the server console:  op <your name>\n"
          f"    4. Open your AI in this folder and say: \"Spawn in and build me a cottage next to me\"\n"
          f"  Problems? {c('1', 'python3 clawdblock.py doctor')}")
    return 0

def installed_mods(sd):
    d = sd / "mods"
    if not d.exists():
        return {}
    have = {}
    for f in d.glob("*.jar"):
        low = f.name.lower()
        for k, (slug, _, _) in MODS.items():
            pat = {"fabric-api": "fabric-api", "carpet": "fabric-carpet", "essential-commands": "essential_commands", "polymer": "polymer-bundled"}.get(k, slug)
            if low.startswith(pat) and not (k == "carpet" and "extra" in low):
                have[k] = f.name
    return have

def install_mods(sd, mc, keys, cfg):
    keys = list(dict.fromkeys(keys + [d for k in keys for d in DEPS.get(k, [])]))
    have = installed_mods(sd)
    lock = cfg.setdefault("mods", {})
    for k in keys:
        slug = MODS[k][0]
        try:
            v = modrinth_version(slug, mc)
        except Exception as e:  # noqa: BLE001
            err(f"{k}: {e}")
            continue
        if not v:
            warn(f"{k}: no build for Minecraft {mc} on Modrinth yet — skipped")
            if k in have:   # an old jar for another Minecraft version can stop the server from starting
                (sd / "mods" / "disabled").mkdir(exist_ok=True)
                shutil.move(str(sd / "mods" / have[k]), sd / "mods" / "disabled" / have[k])
                warn(f"{k}: moved the old {have[k]} to server/mods/disabled/")
            continue
        if have.get(k) == v["filename"]:
            ok(f"{k} {v['version']} (already installed)")
        else:
            if k in have:
                (sd / "mods" / have[k]).unlink(missing_ok=True)
            download(v["url"], sd / "mods" / v["filename"])
            ok(f"{k} {v['version']}")
        lock[k] = v["filename"]

def app_sources():
    src = {}
    for d in (ROOT / "skill" / "clawdblock" / "scripts", ROOT / "scarpet-apps"):
        for f in d.glob("*.sc"):
            src[f.stem] = f
    return src

def app_libraries(app_file):
    """the .scl files in scarpet-apps/ that an app imports with import('<name>', ...)"""
    names = set(re.findall(r"import\(\s*'([a-z0-9_]+)'", app_file.read_text(encoding="utf-8", errors="replace")))
    return [ROOT / "scarpet-apps" / f"{n}.scl" for n in sorted(names) if (ROOT / "scarpet-apps" / f"{n}.scl").exists()]

def install_apps(sd, names):
    dst = level_dir(sd) / "scripts"
    dst.mkdir(parents=True, exist_ok=True)
    src = app_sources()
    for n in names:
        if n not in src:
            err(f"no app called {n} (have: {', '.join(sorted(src))})")
            continue
        shutil.copy2(src[n], dst / f"{n}.sc")
        ok(f"{n}.sc → {dst.relative_to(ROOT) if dst.is_relative_to(ROOT) else dst}")
        for lib in app_libraries(src[n]):                     # scarpet libraries it imports (gamekit.scl, hud.scl)
            shutil.copy2(lib, dst / lib.name)
            ok(f"  + library {lib.name}")
    if server_up(sd):
        r = rcon(sd)
        for n in names:
            info(f"script load {n}: {r.cmd(f'script load {n}')[:80]}")
        r.close()

# ───────────────────────────── AI clients ─────────────────────────────
def mcp_entry(cfg, bot=None):
    node = shutil.which("node") or "node"
    env = {"MC_BOT_NAME": bot} if bot else {}
    return {"command": node, "args": [str(ROOT / "mcp-server" / "index.js")], **({"env": env} if env else {})}

def desktop_config_path():
    s = platform.system()
    if s == "Darwin":
        return Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"
    if s == "Windows":
        return Path(os.environ.get("APPDATA", Path.home())) / "Claude/claude_desktop_config.json"
    return Path.home() / ".config/Claude/claude_desktop_config.json"

def detect_clients():
    found = []
    if shutil.which("claude"):
        found.append("claude-code")
    if desktop_config_path().parent.exists():
        found.append("claude-desktop")
    if shutil.which("gemini") or (Path.home() / ".gemini").exists():
        found.append("gemini")
    if shutil.which("codex") or (Path.home() / ".codex").exists():
        found.append("codex")
    if (Path.home() / ".lmstudio").exists():
        found.append("lmstudio")
    return found

def merge_json(path, fn):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8") or "{}")
            shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
        except json.JSONDecodeError:
            warn(f"{path} is not valid JSON — leaving it alone")
            return False
    fn(data)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return True

def link_skill(dest):
    src = ROOT / "skill" / "clawdblock"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_symlink() or dest.exists():
        if dest.is_symlink() or dest.is_file():
            dest.unlink()
        else:
            shutil.rmtree(dest)
    try:
        dest.symlink_to(src, target_is_directory=True)
        return "linked"
    except OSError:   # Windows without developer mode: copy (re-run connect after updating the repo)
        shutil.copytree(src, dest)
        return "copied"

def skill_zip():
    out = ROOT / "dist" / "clawdblock-skill.zip"
    out.parent.mkdir(exist_ok=True)
    src = ROOT / "skill" / "clawdblock"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in src.rglob("*"):
            if f.is_file() and "__pycache__" not in f.parts:
                z.write(f, Path("clawdblock") / f.relative_to(src))
    return out

def connect(client, cfg=None):
    cfg = cfg or load_cfg()
    bot = cfg.get("bot_name", "Claude")
    if client == "claude-code":
        # project scope: open Claude Code in this folder and everything is there (.mcp.json + .claude/skills)
        merge_json(ROOT / ".mcp.json", lambda d: d.setdefault("mcpServers", {}).__setitem__("clawdblock", mcp_entry(cfg)))
        how = link_skill(ROOT / ".claude" / "skills" / "clawdblock")
        ok(f"Claude Code: .mcp.json + skill {how} into .claude/skills — run `claude` in {ROOT}")
        if yes("  Also make it available in every folder (user scope)?", False):
            link_skill(Path.home() / ".claude" / "skills" / "clawdblock")
            e = mcp_entry(cfg)
            subprocess.run(["claude", "mcp", "add", "clawdblock", "--scope", "user", "--", e["command"], *e["args"]], shell=WIN)
            ok("Claude Code (user scope) registered")
    elif client == "claude-desktop":
        p = desktop_config_path()
        merge_json(p, lambda d: d.setdefault("mcpServers", {}).__setitem__("clawdblock", mcp_entry(cfg)))
        z = skill_zip()
        ok(f"Claude Desktop: MCP added to {p}. Restart Claude Desktop.")
        info(f"Skill: Settings → Capabilities → Skills → Upload skill → {z}")
    elif client == "gemini":
        p = Path.home() / ".gemini" / "settings.json"
        merge_json(p, lambda d: d.setdefault("mcpServers", {}).__setitem__("clawdblock", {**mcp_entry(cfg, "Gemini"), "cwd": str(ROOT)}))
        ok(f"Gemini CLI: MCP added to {p} (bot name Gemini). Run `gemini` in {ROOT} — GEMINI.md loads the skill.")
    elif client == "codex":
        p = Path.home() / ".codex" / "config.toml"
        p.parent.mkdir(parents=True, exist_ok=True)
        e = mcp_entry(cfg, "Codex")
        block = (f'[mcp_servers.clawdblock]\ncommand = {json.dumps(e["command"])}\nargs = {json.dumps(e["args"])}\n'
                 f'env = {{ MC_BOT_NAME = "Codex" }}\nstartup_timeout_sec = 20\ntool_timeout_sec = 120\n')
        s = p.read_text(encoding="utf-8") if p.exists() else ""
        s = re.sub(r"\[mcp_servers\.clawdblock\][^\[]*", "", s).rstrip()
        p.write_text((s + "\n\n" if s else "") + block, encoding="utf-8")
        ok(f"Codex: MCP added to {p} (bot name Codex). Run `codex` in {ROOT} — AGENTS.md loads the skill.")
    elif client == "lmstudio":
        p = Path.home() / ".lmstudio" / "mcp.json"
        merge_json(p, lambda d: d.setdefault("mcpServers", {}).__setitem__("clawdblock", mcp_entry(cfg, "Buddy")))
        ok(f"LM Studio: MCP added to {p} (bot name Buddy). Paste skill/clawdblock/SYSTEM_PROMPT.md into the system prompt.")
    elif client == "print":
        print(json.dumps({"mcpServers": {"clawdblock": mcp_entry(cfg)}}, indent=2))
        info("Paste this into your MCP client's config. Skill: skill/clawdblock/SKILL.md (or SYSTEM_PROMPT.md for small models).")
    else:
        err(f"unknown client {client} (claude-code, claude-desktop, gemini, codex, lmstudio, print)")
        return 1
    return 0

def cmd_connect(a):
    global ASSUME_YES
    ASSUME_YES = a.yes
    targets = a.clients or detect_clients() or ["print"]
    if "all" in targets:
        targets = detect_clients()
    for t in targets:
        connect(t)
    return 0

# ───────────────────────────── run the server ─────────────────────────────
def java_cmd(sd, cfg):
    j, _ = java_version()
    ram = total_ram_mb()
    mem = cfg.get("memory_mb") or max(2048, min(8192, ram // 2))
    return [j or "java", f"-Xms{mem}M", f"-Xmx{mem}M", "-XX:+UseG1GC", "-XX:+ParallelRefProcEnabled", "-XX:MaxGCPauseMillis=200",
            "-XX:+UnlockExperimentalVMOptions", "-XX:+DisableExplicitGC", "-XX:G1NewSizePercent=30", "-XX:G1MaxNewSizePercent=40",
            "-XX:G1HeapRegionSize=8M", "-XX:G1ReservePercent=20", "-XX:InitiatingHeapOccupancyPercent=15",
            "-jar", "fabric-server-launch.jar", "nogui"], mem

def fix_bluemap(sd, cfg):
    """BlueMap stays blank until accept-download is true; its config only exists after the first start."""
    conf = sd / "config" / "bluemap" / "core.conf"
    if not cfg.get("bluemap_textures") or not conf.exists():
        return False
    t = conf.read_text(encoding="utf-8")
    if "accept-download: false" not in t:
        return False
    conf.write_text(t.replace("accept-download: false", "accept-download: true"), encoding="utf-8")
    return True

def cmd_start(a):
    cfg = load_cfg()
    sd = server_dir(cfg)
    fix_bluemap(sd, cfg)
    if not (sd / "fabric-server-launch.jar").exists():
        err("No server yet — run: python3 clawdblock.py setup")
        return 1
    if "eula=true" not in ((sd / "eula.txt").read_text() if (sd / "eula.txt").exists() else ""):
        err("The Minecraft EULA is not accepted: set eula=true in server/eula.txt (https://aka.ms/MinecraftEULA)")
        return 1
    if server_up(sd):
        ok("The server is already running.")
        return 0
    cmd, mem = java_cmd(sd, cfg)
    info(f"Starting Minecraft {cfg.get('mc_version', MC_VERSION)} with {mem} MB RAM in {sd}")
    if a.background:
        (sd / "logs").mkdir(exist_ok=True)
        out = open(sd / "logs" / "console.log", "a", encoding="utf-8")
        kw = {"creationflags": 0x00000008 | 0x00000200} if WIN else {"start_new_session": True}
        p = subprocess.Popen(cmd, cwd=sd, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT, **kw)
        (sd / "server.pid").write_text(str(p.pid))
        t0 = time.time()
        log = sd / "logs" / "latest.log"
        while time.time() - t0 < a.wait:
            time.sleep(2)
            if p.poll() is not None:
                err(f"The server stopped (exit {p.returncode}). Last lines of server/logs/console.log:")
                print("".join(open(sd / "logs" / "console.log", encoding="utf-8", errors="replace").readlines()[-15:]))
                return 1
            if log.exists() and re.search(r"Done \(\d", log.read_text(encoding="utf-8", errors="replace")[-20000:]) and server_up(sd):
                ok(f"Server is up ({time.time() - t0:.0f} s). Stop it with: python3 clawdblock.py stop")
                return 0
        warn(f"Still starting after {a.wait} s — watch server/logs/latest.log")
        return 0
    print(c("2", "  Console: type server commands here (list, op <name>, say hi). Type  stop  to shut down cleanly.\n"))
    if sys.platform == "darwin" and shutil.which("caffeinate"):
        cmd = ["caffeinate", "-i"] + cmd   # keep the Mac awake while the server runs
    try:
        return subprocess.call(cmd, cwd=sd)
    except KeyboardInterrupt:
        return 0

def cmd_stop(a):
    sd = server_dir()
    try:
        r = rcon(sd)
        r.cmd("stop")
        r.close()
        ok("Stopping the server (it saves the world first).")
    except Exception as e:  # noqa: BLE001
        warn(f"Could not reach the server over RCON ({e}) — it is probably not running.")
    return 0

def cmd_status(a):
    cfg = load_cfg()
    sd = server_dir(cfg)
    print(c("1", "ClawdBlock") + f"  server: {sd}")
    try:
        r = rcon(sd)
        ok("running — " + r.cmd("list"))
        tps = r.cmd("script run system_info('server_last_tick_times')") if "carpet" in installed_mods(sd) else ""
        r.close()
        if tps:
            info("tick times (ms): " + tps[:80])
    except Exception as e:  # noqa: BLE001
        warn(f"not running ({e})")
    mods = installed_mods(sd)
    info("mods: " + (", ".join(sorted(mods)) or "none"))
    return 0

def cmd_doctor(a):
    cfg = load_cfg()
    sd = server_dir(cfg)
    bad = 0
    def check(cond, good, fix):
        nonlocal bad
        if cond:
            ok(good)
        else:
            bad += 1
            err(fix)
    head("ClawdBlock doctor")
    _, jv = java_version()
    check(jv and jv >= JAVA_MIN, f"Java {jv}", f"Java {JAVA_MIN}+ missing (found {jv}). {hint('java')}")
    _, nv = node_version()
    check(nv and nv >= NODE_MIN, f"Node {nv}", f"Node {NODE_MIN}+ missing (found {nv}). {hint('node')}")
    check(CONFIG.exists(), "clawdblock.json", "No clawdblock.json — run: python3 clawdblock.py setup")
    check((sd / "fabric-server-launch.jar").exists(), f"server jar in {sd}", "No server — run: python3 clawdblock.py setup")
    check("eula=true" in ((sd / "eula.txt").read_text() if (sd / "eula.txt").exists() else ""), "EULA accepted", "EULA not accepted: eula=true in server/eula.txt")
    p = read_props(sd)
    check(p.get("enable-rcon") == "true" and p.get("rcon.password"), f"RCON enabled (port {p.get('rcon.port')})", "RCON off — run setup again (it keeps your world)")
    mods = installed_mods(sd)
    for k in ("fabric-api", "carpet"):
        check(k in mods, f"mod {k}", f"mod {k} missing — python3 clawdblock.py mods add {k}")
    apps = level_dir(sd) / "scripts"
    for n in CORE_APPS:
        check((apps / f"{n}.sc").exists(), f"scarpet app {n}", f"scarpet app {n} missing — python3 clawdblock.py apps add {n}")
    check((ROOT / "mcp-server" / "node_modules" / "@modelcontextprotocol").exists(), "MCP dependencies installed", "run: cd mcp-server && npm install")
    if fix_bluemap(sd, cfg):
        info("BlueMap: texture download enabled (restart the server, or run 'bluemap reload' in its console)")
    up = server_up(sd)
    (ok if up else warn)("server is running" if up else "server is not running (python3 clawdblock.py start)")
    if up:
        r = rcon(sd)
        out = r.cmd("script run 1+1")
        check("2" in out, "Carpet scarpet answers", f"scarpet does not answer: {out[:100]}")
        out = r.cmd("script in cu run ytop(0,0)")
        check("=" in out and "rror" not in out, "cu app loaded", f"cu app not loaded ({out[:80]}) — in the server console: script load cu")
        r.close()
    nd = shutil.which("node")
    if nd and (ROOT / "mcp-server" / "node_modules").exists():
        pr = subprocess.run([nd, str(ROOT / "mcp-server" / "test" / "load.mjs")], capture_output=True, text=True, cwd=ROOT / "mcp-server")
        check(pr.returncode == 0, "MCP tools load (" + (pr.stdout.split(" tools")[0] if pr.returncode == 0 else "") + " tools)", "MCP tools fail to load:\n" + pr.stderr[-800:])
    cl = detect_clients()
    info("AI clients found: " + (", ".join(cl) or "none") + ("" if (ROOT / ".mcp.json").exists() or not cl else "  → python3 clawdblock.py connect"))
    print(c("1;32", "\nAll good.") if not bad else c("1;31", f"\n{bad} problem(s) above."))
    return 1 if bad else 0

def cmd_mods(a):
    global ASSUME_YES
    ASSUME_YES = a.yes
    cfg = load_cfg()
    sd = server_dir(cfg)
    mc = cfg.get("mc_version", MC_VERSION)
    have = installed_mods(sd)
    if a.action == "list":
        for k, (slug, tier, why) in MODS.items():
            mark = c("32", "✓") if k in have else " "
            print(f" {mark} {k:<19} {c('2', tier):<22} {why}")
        others = sorted(set(p.name for p in (sd / "mods").glob("*.jar")) - set(have.values())) if (sd / "mods").exists() else []
        if others:
            info("other mods in server/mods: " + ", ".join(others))
        return 0
    if a.action == "add":
        unknown = [n for n in a.names if n not in MODS]
        if unknown:
            err(f"unknown: {', '.join(unknown)}. Any other Fabric mod: drop its .jar into {sd / 'mods'}")
        install_mods(sd, mc, [n for n in a.names if n in MODS], cfg)
    elif a.action == "remove":
        for n in a.names:
            if n in have:
                (sd / "mods" / have[n]).unlink()
                cfg.get("mods", {}).pop(n, None)
                ok(f"removed {n}")
    elif a.action == "update":
        install_mods(sd, mc, list(have), cfg)
    save_cfg(cfg)
    if server_up(sd):
        warn("Restart the server for mod changes to take effect.")
    return 0

def cmd_apps(a):
    sd = server_dir()
    src = app_sources()
    dst = level_dir(sd) / "scripts"
    if a.action == "list":
        for n, f in sorted(src.items()):
            doc = next((l.strip("/ ").strip() for l in f.read_text(encoding="utf-8").splitlines()[:3] if l.startswith("//")), "")
            mark = c("32", "✓") if (dst / f"{n}.sc").exists() else " "
            print(f" {mark} {n:<14} {doc[:90]}")
        return 0
    if a.action == "add":
        install_apps(sd, a.names)
    elif a.action == "remove":
        for n in a.names:
            if (dst / f"{n}.sc").exists():
                if server_up(sd):
                    r = rcon(sd); r.cmd(f"script unload {n}"); r.close()
                (dst / f"{n}.sc").unlink()
                ok(f"removed {n}")
    return 0

def cmd_new_world(a):
    sd = server_dir()
    if server_up(sd):
        err("Stop the server first: python3 clawdblock.py stop")
        return 1
    lv = level_dir(sd)
    apps = list(CORE_APPS)
    if lv.exists():
        dst = ROOT / "backups" / f"{lv.name}-{time.strftime('%Y%m%d-%H%M%S')}"
        dst.parent.mkdir(exist_ok=True)
        shutil.move(str(lv), dst)
        apps = sorted(set(apps) | {p.stem for p in (dst / "scripts").glob("*.sc") if p.stem in app_sources()})
        ok(f"old world moved to {dst.relative_to(ROOT)} (not deleted)")
    for f in ("zones.json", "undo.json", "world_index.json"):
        (ROOT / "data" / f).unlink(missing_ok=True)   # they describe the old world
    install_apps(sd, apps)
    ok("The next start creates a fresh world.")
    return 0

LEDGER_FILES = ("ledger.sqlite", "ledger.sqlite-wal", "ledger.sqlite-shm", "ledger.sqlite-journal")
STORED_EXT = (".mca", ".zip", ".png", ".jpg", ".gz")   # already compressed: deflating them again only burns CPU

def _tree_size(p, skip=()):
    total = 0
    for dp, _, files in os.walk(p):
        for f in files:
            if f not in skip:
                try:
                    total += os.lstat(os.path.join(dp, f)).st_size
                except OSError:
                    pass
    return total

def _free(p):
    p = Path(p)
    while not p.exists():
        p = p.parent
    return shutil.disk_usage(p).free

def _mb(n):
    return f"{n / 1048576:.2f} MB" if n < 10 * 1048576 else f"{n / 1048576:.0f} MB" if n < 10 * 1073741824 else f"{n / 1073741824:.1f} GB"

def _world_in_use(lv):
    """True when a running server holds <world>/session.lock; None when we can't tell (Windows)."""
    f = lv / "session.lock"
    if not f.exists():
        return False
    try:
        import fcntl
    except ImportError:
        return None
    try:
        with open(f, "r+b") as fh:
            fcntl.lockf(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.lockf(fh, fcntl.LOCK_UN)
        return False
    except OSError:
        return True

def cmd_backup(a):
    """save-off -> save-all flush -> copy -> save-on (always) -> zip -> verify -> rotate. Refuses without room."""
    import signal
    import sqlite3
    def _interrupt(*_):
        raise KeyboardInterrupt   # so the finally blocks run (save-on!) when a terminal or the MCP stops us
    for sig in ("SIGTERM", "SIGHUP"):
        if hasattr(signal, sig):
            signal.signal(getattr(signal, sig), _interrupt)
    sd = server_dir()
    lv = level_dir(sd)
    dest = Path(a.dest).resolve() if a.dest else ROOT / "backups"
    res = {"ok": False, "dry_run": a.dry_run, "world": str(lv), "dest": str(dest), "keep": a.keep, "include_ledger": a.include_ledger}

    def done(code, **kw):
        res.update(kw)
        if a.json:
            print(json.dumps(res, indent=1))
        elif res.get("ok"):
            ok(res.get("would") or f"backup: {res.get('zip')} ({res.get('zip_size')})" + (f", removed old: {', '.join(res['rotated'])}" if res.get("rotated") else ""))
            if a.dry_run and res.get("would_rotate"):
                info("rotation would remove: " + ", ".join(res["would_rotate"]))
        else:
            err(res.get("reason") or res.get("error") or "backup failed")
        return code

    if not lv.exists():
        return done(1, error="no world yet")
    if a.keep < 1:
        return done(1, error="--keep must be at least 1")
    skip = ("session.lock",) + (() if a.include_ledger else LEDGER_FILES)
    world_bytes = _tree_size(lv)
    free = int(a.simulate_free_mb * 1048576) if a.simulate_free_mb is not None else _free(dest)
    need = int(world_bytes * 3)
    name_re = re.compile(rf"^{re.escape(lv.name)}-\d{{8}}-\d{{6}}\.zip$")
    old = sorted(p for p in dest.glob(f"{lv.name}-*.zip") if name_re.match(p.name)) if dest.is_dir() else []
    space = f"free {_mb(free)}, need 3 x world {_mb(world_bytes)} = {_mb(need)}"
    res.update(world_bytes=world_bytes, copy_bytes=_tree_size(lv, skip), excluded=[s for s in skip if (lv / s).exists()],
               free_bytes=free, need_bytes=need, space=space, simulated_free=a.simulate_free_mb is not None, existing_backups=[p.name for p in old])
    if free < need:   # the live server must always have room to save
        return done(2, refused=True, reason=f"not enough free space ({space}). Nothing was written. Free some space or use --dest <another disk>.")
    doomed = old[:max(0, len(old) - (a.keep - 1))]
    if a.dry_run:
        return done(0, ok=True, would=f"copy {_mb(res['copy_bytes'])} while saving is paused, zip it into {dest}, keep {a.keep}", would_rotate=[p.name for p in doomed])

    dest.mkdir(parents=True, exist_ok=True)
    lock = dest / ".backup.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
    except FileExistsError:
        if time.time() - lock.stat().st_mtime < 7200:
            return done(2, refused=True, reason=f"another backup is running ({lock})")
        lock.unlink(missing_ok=True)
        return done(1, error="removed a stale backup lock; run again")
    try:
        if hasattr(os, "nice"):
            os.nice(10)   # the server comes first
        stamp = time.strftime("%Y%m%d-%H%M%S")
        stage, final, part = dest / f".staging-{stamp}", dest / f"{lv.name}-{stamp}.zip", dest / f".{lv.name}-{stamp}.zip.part"
        r = None
        try:
            r = rcon(sd)
        except Exception as e:  # noqa: BLE001
            if _world_in_use(lv) is not False:
                return done(1, error=f"the server has the world open but RCON does not answer ({e}); cannot flush saves safely")
        t0 = time.time()
        try:
            if r:
                r.cmd("save-off")
                res["flush"] = r.cmd("save-all flush").strip()[:120]
            shutil.copytree(lv, stage, ignore=lambda d, names: [n for n in names if n in skip])
            if a.include_ledger and (lv / "ledger.sqlite").exists():   # a consistent snapshot while Ledger writes
                src, dst = sqlite3.connect(f"file:{lv / 'ledger.sqlite'}?mode=ro", uri=True), sqlite3.connect(stage / "ledger.sqlite")
                with dst:
                    src.backup(dst)
                src.close(); dst.close()
        finally:
            if r:
                try:
                    r.cmd("save-on")
                finally:
                    r.close()
        res["save_off_seconds"] = round(time.time() - t0, 1) if r else 0
        try:
            if _free(dest) < _tree_size(stage) + 512 * 1048576:
                return done(1, error="free space ran low after the copy; nothing zipped, the copy was removed")
            with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
                for dp, _, files in os.walk(stage):
                    for f in files:
                        p = Path(dp) / f
                        z.write(p, Path(lv.name) / p.relative_to(stage), zipfile.ZIP_STORED if f.endswith(STORED_EXT) else zipfile.ZIP_DEFLATED)
            with zipfile.ZipFile(part) as z:
                bad = z.testzip()
            if bad:
                return done(1, error=f"the new zip failed its check at {bad}; nothing rotated")
            part.rename(final)
        finally:
            shutil.rmtree(stage, ignore_errors=True)
            part.unlink(missing_ok=True)
        rotated = []
        for p in doomed:
            p.unlink(missing_ok=True)
            rotated.append(p.name)
        return done(0, ok=True, zip=str(final), zip_bytes=final.stat().st_size, zip_size=_mb(final.stat().st_size),
                    seconds=round(time.time() - t0, 1), rotated=rotated)
    except KeyboardInterrupt:
        return done(1, error="interrupted (saving was switched back on)")
    finally:
        lock.unlink(missing_ok=True)

def main():
    ap = argparse.ArgumentParser(prog="clawdblock", description="Set up and run a Minecraft server an AI can build in.")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("setup", help="install or repair everything (keeps your world)")
    s.add_argument("--yes", "-y", action="store_true", help="accept the recommended answers")
    s.add_argument("--accept-eula", action="store_true", help="accept the Minecraft EULA (https://aka.ms/MinecraftEULA)")
    s.add_argument("--mc-version", help=f"Minecraft version (default {MC_VERSION}, the tested one)")
    s.add_argument("--port", type=int, help="game port (default 25565)")
    s.add_argument("--rcon-port", type=int, help="RCON port (default 25575, or the next free one)")
    s.add_argument("--memory", type=int, help="server RAM in MB (default: half the computer's RAM, 2-8 GB)")
    s.add_argument("--world", choices=["flat", "normal"], help="world type for a new server")
    s.add_argument("--bot-name", help="the AI's name in the game (default Claude)")
    s.add_argument("--no-connect", action="store_true", help="don't register with AI clients now (later: connect)")
    s = sub.add_parser("start", help="start the server")
    s.add_argument("--background", "-b", action="store_true")
    s.add_argument("--wait", type=int, default=180, help="background: seconds to wait for 'Done'")
    sub.add_parser("stop", help="stop the server (saves first)")
    sub.add_parser("status", help="is it running, who is online, which mods")
    sub.add_parser("doctor", help="find and explain problems")
    s = sub.add_parser("mods", help="list / add / remove / update mods")
    s.add_argument("action", nargs="?", default="list", choices=["list", "add", "remove", "update"])
    s.add_argument("names", nargs="*")
    s.add_argument("--yes", "-y", action="store_true")
    s = sub.add_parser("apps", help="scarpet game-logic apps in the world")
    s.add_argument("action", nargs="?", default="list", choices=["list", "add", "remove"])
    s.add_argument("names", nargs="*")
    s = sub.add_parser("connect", help="register the MCP + skill with AI clients")
    s.add_argument("clients", nargs="*", help="claude-code claude-desktop gemini codex lmstudio all print")
    s.add_argument("--yes", "-y", action="store_true")
    sub.add_parser("new-world", help="archive the world; the next start makes a fresh one")
    s = sub.add_parser("backup", help="zip the world into backups/ (keeps the newest 3; refuses without 3x the world free)")
    s.add_argument("--keep", type=int, default=3, help="how many backups to keep (default 3)")
    s.add_argument("--include-ledger", action="store_true", help="also back up the Ledger database (big; left out by default)")
    s.add_argument("--dest", help="another folder or disk for the zips (default: backups/)")
    s.add_argument("--dry-run", action="store_true", help="only report sizes, free space and what rotation would remove")
    s.add_argument("--simulate-free-mb", type=float, help=argparse.SUPPRESS)   # tests: pretend this much is free
    s.add_argument("--json", action="store_true", help="print one JSON object (used by minecraft_watchdog)")
    a = ap.parse_args()
    fn = {"setup": cmd_setup, "start": cmd_start, "stop": cmd_stop, "status": cmd_status, "doctor": cmd_doctor, "mods": cmd_mods,
          "apps": cmd_apps, "connect": cmd_connect, "new-world": cmd_new_world, "backup": cmd_backup}.get(a.cmd)
    if not fn:
        ap.print_help()
        return 0
    try:
        return fn(a) or 0
    except KeyboardInterrupt:
        print()
        return 130
    except RuntimeError as e:
        err(str(e))
        return 1

if __name__ == "__main__":
    sys.exit(main())
