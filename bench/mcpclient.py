"""A tiny MCP client over stdio (standard library only).

Starts the Pink Golem MCP server as a child process and talks JSON-RPC to it, one JSON message per line:
initialize → tools/list → tools/call. Enough for an agent loop; not a general MCP implementation.
"""
import json
import os
import queue
import shutil
import subprocess
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class MCPError(Exception):
    pass


class MCP:
    def __init__(self, env=None, log_stderr=None):
        node = shutil.which("node") or "node"
        e = dict(os.environ)
        e.update(env or {})
        self.p = subprocess.Popen([node, str(ROOT / "mcp-server" / "index.js")], cwd=str(ROOT), env=e,
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True, encoding="utf-8", bufsize=1)
        self._id = 0
        self._q = {}
        self._lock = threading.Lock()
        self._stderr = log_stderr
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=self._read_err, daemon=True).start()
        self.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                    "clientInfo": {"name": "pinkgolem-bench", "version": "1"}})
        self.notify("notifications/initialized")

    def _read(self):
        for line in self.p.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            q = self._q.get(msg.get("id"))
            if q:
                q.put(msg)

    def _read_err(self):
        for line in self.p.stderr:
            if self._stderr:
                self._stderr.write(line)
                self._stderr.flush()

    def notify(self, method, params=None):
        self._send({"jsonrpc": "2.0", "method": method, **({"params": params} if params else {})})

    def _send(self, msg):
        with self._lock:
            self.p.stdin.write(json.dumps(msg) + "\n")
            self.p.stdin.flush()

    def request(self, method, params=None, timeout=900):
        self._id += 1
        rid = self._id
        q = self._q[rid] = queue.Queue()
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})
        try:
            msg = q.get(timeout=timeout)
        except queue.Empty:
            raise MCPError(f"{method}: no answer in {timeout} s")
        finally:
            self._q.pop(rid, None)
        if "error" in msg:
            raise MCPError(msg["error"].get("message", str(msg["error"])))
        return msg.get("result", {})

    def tools(self):
        return self.request("tools/list").get("tools", [])

    def call(self, name, args=None, timeout=900):
        """Returns (text, is_error, images). images = list of (mime, base64)."""
        t0 = time.time()
        try:
            r = self.request("tools/call", {"name": name, "arguments": args or {}}, timeout=timeout)
        except MCPError as e:
            return f"Error: {e}", True, []
        texts, images = [], []
        for c in r.get("content", []):
            if c.get("type") == "text":
                texts.append(c.get("text", ""))
            elif c.get("type") == "image":
                images.append((c.get("mimeType", "image/png"), c.get("data", "")))
        return "\n".join(texts), bool(r.get("isError")), images

    def close(self):
        try:
            self.p.stdin.close()
            self.p.wait(timeout=5)
        except Exception:
            self.p.kill()
