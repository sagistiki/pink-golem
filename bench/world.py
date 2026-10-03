"""The bench's own hands on the test server: RCON (sharing the MCP's cross-process lock), arenas, the Tester player and
the judge scan (bench.sc). Standard library only."""
import json
import math
import os
import re
import shutil
import socket
import struct
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GROUND = -61          # the flat world's grass layer
FILL_MAX = 32768


def read_props(sd):
    p = {}
    for line in (sd / "server.properties").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            p[k.strip()] = v.strip()
    return p


class World:
    def __init__(self, server_dir=None):
        cfg = json.loads((ROOT / "pinkgolem.json").read_text()) if (ROOT / "pinkgolem.json").exists() else {}
        self.sd = Path(server_dir or ROOT / cfg.get("server_dir", "server"))
        props = read_props(self.sd)
        self.port = int(props.get("rcon.port", 25575))
        self.password = props.get("rcon.password", "")
        self.level = props.get("level-name", "world")
        self.lock = ROOT / "data" / ".rcon.lock"
        self.crew = (cfg.get("crew") or {}).get("names") or ["Alex_Builder", "Sam_Builder", "Riley_Builder", "Jordan_Builder"]
        self.s = None

    # ── RCON ──────────────────────────────────────────────────────────────
    def _connect(self):
        self.s = socket.create_connection(("127.0.0.1", self.port), timeout=60)
        self._send(3, self.password)
        if self._recv()[0] == -1:
            raise RuntimeError("RCON login failed")

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
        """One command, holding the same lock directory the MCP uses so outputs never mix."""
        t0 = time.time()
        got = False
        while True:
            try:
                os.mkdir(self.lock)
                got = True
                break
            except FileExistsError:
                try:
                    if time.time() - self.lock.stat().st_mtime > 12:
                        os.rmdir(self.lock)
                        continue
                except FileNotFoundError:
                    continue
                if time.time() - t0 > 15:
                    break
                time.sleep(0.01)
        try:
            for attempt in range(2):
                try:
                    if not self.s:
                        self._connect()
                    self._send(2, c)
                    return re.sub("§.", "", self._recv()[2])
                except (OSError, ConnectionError):
                    self.s = None
                    if attempt:
                        raise
        finally:
            if got:
                try:
                    os.rmdir(self.lock)
                except FileNotFoundError:
                    pass

    def up(self):
        try:
            self.cmd("list")
            return True
        except Exception:
            return False

    # ── players ───────────────────────────────────────────────────────────
    def online(self):
        out = self.cmd("list uuids")
        m = re.search(r"online:\s*(.*)$", out, re.S)
        return re.findall(r"([A-Za-z0-9_]{1,16}) \([0-9a-f-]{36}\)", m.group(1)) if m else []

    def pos(self, name):
        out = self.cmd(f"data get entity {name} Pos")
        nums = re.findall(r"-?\d+(?:\.\d+)?", out.split("data:", 1)[-1]) if "data:" in out else []
        return [float(v) for v in nums[:3]] if len(nums) >= 3 else None

    def place_tester(self, name, x, y, z, yaw=180):
        """The 'player' every scenario talks for: a Carpet fake player standing at x, y, z."""
        if name in self.online():
            self.cmd(f"tp {name} {x + .5} {y} {z + .5} {yaw} 0")
        else:
            self.cmd(f"player {name} spawn at {x + .5} {y} {z + .5} facing {yaw} 0 in minecraft:overworld in creative")
            for _ in range(40):
                time.sleep(0.25)
                if name in self.online():
                    break
            self.cmd(f"tp {name} {x + .5} {y} {z + .5} {yaw} 0")
        self.cmd(f"gamemode creative {name}")

    def find(self, name):
        """The online spelling of a name (Carpet copies the casing of a real account with that name: Opus → OPUS)."""
        return next((n for n in self.online() if n.lower() == name.lower()), None)

    def kill_bots(self, names):
        on = {n.lower(): n for n in self.online()}
        for n in names:
            if n.lower() in on:
                self.cmd(f"player {on[n.lower()]} kill")

    # ── arenas ────────────────────────────────────────────────────────────
    def forceload(self, box, on=True):
        (x1, z1), (x2, z2) = box
        self.cmd(f"forceload {'add' if on else 'remove'} {x1} {z1} {x2} {z2}")

    def reset(self, box, ytop=80, around=None):
        """Back to untouched flat ground: entities gone, air above, grass, dirt below. `around` limits the block
        reset to a smaller box (the judge's last scan) for speed; entities are cleared across the whole arena."""
        (x1, z1), (x2, z2) = box
        self.cmd(f"kill @e[type=!player,x={x1},y=-64,z={z1},dx={x2 - x1},dy={ytop + 70},dz={z2 - z1}]")
        if around:
            (x1, y1, z1), (x2, y2, z2) = around
            x1, z1, x2, z2 = x1 - 1, z1 - 1, x2 + 1, z2 + 1
            ytop = y2 + 1
        area = (x2 - x1 + 1) * (z2 - z1 + 1)
        step = max(1, FILL_MAX // area)
        if area > FILL_MAX:            # rows along z for a very wide box
            raise ValueError("arena too wide for single-layer fills")
        y = GROUND + 1
        while y <= ytop:
            y2 = min(ytop, y + step - 1)
            self.cmd(f"fill {x1} {y} {z1} {x2} {y2} {z2} air")
            y = y2 + 1
        self.cmd(f"fill {x1} {GROUND} {z1} {x2} {GROUND} {z2} grass_block")
        self.cmd(f"fill {x1} {GROUND - 2} {z1} {x2} {GROUND - 1} {z2} dirt")

    # ── the judge ─────────────────────────────────────────────────────────
    def load_judge(self):
        dst = self.sd / self.level / "scripts"
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / "bench" / "bench.sc", dst / "bench.sc")
        out = self.cmd("script load bench")
        if "error" in out.lower() or "exception" in out.lower():
            raise RuntimeError(f"bench.sc did not load: {out}")

    def scan(self, box, ylo=GROUND - 2, yhi=80, max_cells=4000, name="scan"):
        (x1, z1), (x2, z2) = box
        f = self.sd / self.level / "scripts" / "bench.data" / f"{name}.json"
        if f.exists():
            f.unlink()
        out = self.cmd(f"script in bench run judge({x1},{z1},{x2},{z2},{ylo},{yhi},'{name}',{max_cells})")
        for _ in range(200):
            if f.exists():
                break
            time.sleep(0.05)
        if not f.exists():
            raise RuntimeError(f"judge scan failed: {out}")
        d = json.loads(f.read_text())
        d.setdefault("lo", None)
        d.setdefault("hi", None)
        d["counts"] = d.get("counts") or {}
        d["cells"] = d.get("cells") or []
        return d


def dist_point_box(p, lo, hi):
    """Horizontal distance from a point to a box (0 inside)."""
    dx = max(lo[0] - p[0], 0, p[0] - hi[0])
    dz = max(lo[2] - p[2], 0, p[2] - hi[2])
    return math.hypot(dx, dz)


def box_gap(alo, ahi, blo, bhi):
    """Horizontal gap between two boxes (0 = touching or overlapping)."""
    dx = max(blo[0] - ahi[0], alo[0] - bhi[0], 0)
    dz = max(blo[2] - ahi[2], alo[2] - bhi[2], 0)
    return math.hypot(dx, dz)
