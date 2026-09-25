#!/usr/bin/env python3
"""Build the Key Bridge server mod (a tiny Fabric mod) with plain javac — no Gradle, no Loom.

Minecraft 26.x server jars are not obfuscated, so the mod compiles directly against the server jar that the
ClawdBlock server already has, plus its libraries and three Fabric API modules (taken from the fabric-api jar in
server/mods). Needs a JDK (javac + jar) of the same major version as the server's Java.

    python3 mods-src/keybridge/build.py              # → mods-src/keybridge/build/keybridge-<version>.jar
    python3 mods-src/keybridge/build.py --install    # also copy it into server/mods (restart the server to load it)
    python3 mods-src/keybridge/build.py --server /path/to/server
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
FABRIC_MODULES = ("fabric-api-base", "fabric-lifecycle-events-v1", "fabric-command-api-v2")


def tool(name):
    home = os.environ.get("JAVA_HOME")
    exe = name + (".exe" if os.name == "nt" else "")
    if home and (Path(home) / "bin" / exe).exists():
        return str(Path(home) / "bin" / exe)
    found = shutil.which(name)
    if not found:
        sys.exit(f"{name} not found — install a JDK (not just a JRE) or set JAVA_HOME")
    return found


def server_jar(sd):
    cands = sorted(sd.glob("versions/*/server-*.jar")) + sorted(sd.glob(".fabric/server/*-server.jar"))
    if not cands:
        sys.exit(f"no Minecraft server jar under {sd} (versions/ or .fabric/server/) — start the server once first")
    return cands[0]


def fabric_modules(sd, tmp):
    """The Fabric API modules the mod uses, extracted from the fabric-api jar in mods/ (nested jars)."""
    api = sorted(sd.glob("mods/fabric-api-*.jar"))
    if not api:
        sys.exit(f"no fabric-api jar in {sd / 'mods'} — install it first (python3 clawdblock.py mods)")
    out = []
    with zipfile.ZipFile(api[-1]) as z:
        for n in z.namelist():
            base = Path(n).name
            if n.startswith("META-INF/jars/") and base.endswith(".jar") and any(base.startswith(m + "-") for m in FABRIC_MODULES):
                p = Path(tmp) / base
                p.write_bytes(z.read(n))
                out.append(p)
    missing = [m for m in FABRIC_MODULES if not any(p.name.startswith(m + "-") for p in out)]
    if missing:
        sys.exit(f"{api[-1].name} has no {', '.join(missing)}")
    return out


def main():
    ap = argparse.ArgumentParser(description="Build the Key Bridge mod")
    ap.add_argument("--server", default=str(ROOT / "server"), help="the server folder (default: ./server)")
    ap.add_argument("--install", action="store_true", help="copy the jar into <server>/mods")
    a = ap.parse_args()
    sd = Path(a.server).resolve()
    meta = json.loads((HERE / "fabric.mod.json").read_text(encoding="utf-8"))
    build = HERE / "build"
    classes = build / "classes"
    shutil.rmtree(classes, ignore_errors=True)
    classes.mkdir(parents=True)
    with tempfile.TemporaryDirectory() as tmp:
        cp = [server_jar(sd)] + sorted(sd.glob("libraries/**/*.jar")) + fabric_modules(sd, tmp)
        srcs = [str(p) for p in (HERE / "src").rglob("*.java")]
        r = subprocess.run([tool("javac"), "-nowarn", "-d", str(classes), "-cp", os.pathsep.join(map(str, cp)), *srcs])
        if r.returncode:
            sys.exit("javac failed")
    shutil.copy(HERE / "fabric.mod.json", classes / "fabric.mod.json")
    jar = build / f"{meta['id']}-{meta['version']}.jar"
    if jar.exists():
        jar.unlink()
    r = subprocess.run([tool("jar"), "--create", "--file", str(jar), "-C", str(classes), "."])
    if r.returncode:
        sys.exit("jar failed")
    print(f"built {jar.relative_to(ROOT) if jar.is_relative_to(ROOT) else jar} ({jar.stat().st_size} bytes)")
    if a.install:
        mods = sd / "mods"
        for old in mods.glob(f"{meta['id']}-*.jar"):
            old.unlink()
            print(f"removed old {old.name}")
        shutil.copy(jar, mods / jar.name)
        print(f"installed {mods / jar.name} — restart the server to load it")


if __name__ == "__main__":
    main()
