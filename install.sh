#!/usr/bin/env bash
# ClawdBlock installer for macOS and Linux.
#   ./install.sh            interactive
#   ./install.sh --yes --accept-eula    recommended answers, no questions (--accept-eula = you accept https://aka.ms/MinecraftEULA)
set -e
cd "$(dirname "$0")"
say() { printf '\033[1;35m%s\033[0m\n' "$*"; }
need() { printf '\033[33m! %s\033[0m\n    %s\n' "$1" "$2"; }

say "ClawdBlock — checking what your computer has"
PY=""
for p in python3 python; do command -v "$p" >/dev/null 2>&1 && "$p" -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null && PY="$p" && break; done
if [ -z "$PY" ]; then
  need "Python 3.9+ is needed to run the installer." "macOS: brew install python   ·   Ubuntu/Debian: sudo apt install python3   ·   https://www.python.org/downloads/"
  exit 1
fi
OS="$(uname -s)"
if ! command -v java >/dev/null 2>&1; then
  if [ "$OS" = "Darwin" ]; then need "Java 25 is needed for Minecraft 26.x." "brew install --cask temurin@25   (or https://adoptium.net/temurin/releases/?version=25)"
  else need "Java 25 is needed for Minecraft 26.x." "sudo apt install openjdk-25-jre-headless   (or https://adoptium.net/temurin/releases/?version=25)"; fi
fi
if ! command -v node >/dev/null 2>&1; then
  if [ "$OS" = "Darwin" ]; then need "Node.js 20+ is needed for the AI connection (MCP)." "brew install node   (or https://nodejs.org)"
  else need "Node.js 20+ is needed for the AI connection (MCP)." "sudo apt install nodejs npm   (or https://nodejs.org / nvm)"; fi
fi
exec "$PY" clawdblock.py setup "$@"
