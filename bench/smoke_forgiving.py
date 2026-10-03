#!/usr/bin/env python3
"""Live check of the small-model forgiveness in the MCP (needs the test server and the bench arena 7 free).

    python3 bench/smoke_forgiving.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mcpclient import MCP  # noqa: E402
from world import World  # noqa: E402

CX, CZ = 5000 + 256 * 7, 5000
BOX = ((CX - 48, CZ - 48), (CX + 48, CZ + 48))
ok = True


def check(name, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + name + (f"   [{detail[:300]}]" if not cond and detail else ""))


w = World()
w.forceload(BOX)
w.reset(BOX)
w.place_tester("Tester", CX, -60, CZ, yaw=180)
m = MCP(env={"MC_BOT_NAME": "Smoke"})
try:
    t, e, _ = m.call("minecraft_generate", {"script": "skill/pinkgolem/blueprints/cottage.py",
                                            "args": [f"--at {CX + 10},-61,{CZ - 4}", "--facing west"], "dry_run": True})
    check("generate: '--at X' in one string is split", not e and '"ok": true' in t and "args read as" in t, t)
    t, e, _ = m.call("minecraft_generate", {"script": "skill/pinkgolem/blueprints/cottage.py", "args": ["--bogus"]})
    check("generate: a failing generator is an error that says nothing was built", e and "NOTHING" in t, t)
    t2, e2, _ = m.call("minecraft_generate", {"script": "skill/pinkgolem/blueprints/cottage.py", "args": ["--bogus"]})
    check("same failing call twice: says so", e2 and "failed 2 times" in t2, t2)
    t, e, _ = m.call("minecraft_jobs", {"action": "wait"})
    check("jobs wait with no jobs: says nothing is being built", "nothing is being built" in t, t)
    t, e, _ = m.call("minecraft_bot", {"action": "spawn", "player": "Smoke"})
    check("spawn next to yourself → next to the real player", not e and "Tester" in t, t)
    t, e, _ = m.call("minecraft_build", {"relative_to_player": "y=0", "operations": [
        {"op": "fill", "from": [CX - 2, -61, CZ - 7], "to": [CX + 2, -61, CZ - 3], "block": "stone"}]})
    check("build: junk relative_to_player with absolute coords still builds", not e and "ignored" in t, t)
    t, e, _ = m.call("minecraft_vision", {"from": [CX - 1, -61, CZ - 1], "to": [CX + 1, -55, CZ + 1]})
    check("vision: a box without mode is a site check that names the player inside", '"free": false' in t and "Tester" in t and "bury" in t, t)
    t, e, _ = m.call("minecraft_get_players", {})
    p = json.loads(t)[0]
    check("get_players: facing.ground_3_ahead", p["facing"]["ground_3_ahead"] == [CX, -61, CZ - 3], json.dumps(p["facing"]))
    t, e, _ = m.call("minecraft_map", {"action": "add", "notes": "Smoke test stone floor near Tester"})
    check("map add without a name: named from its notes", not e and '"Smoke test stone floor"' in t, t)
    m.call("minecraft_map", {"action": "remove", "id": "smoke_test_stone_floor"})
    t, e, _ = m.call("minecraft_map", {"action": "add"})
    check("map add with nothing: shows a working example", e and '"name"' in t, t)
    t, e, _ = m.call("minecraft_build", {"relative_to_player": "Tester", "operations": [
        {"op": "setblock", "pos": [CX + 4, -60, CZ - 4], "block": "lantern"}]})
    check("build: a real player name + world coordinates builds at the world coordinates", not e and "world positions" in t, t)
    t, e, _ = m.call("minecraft_generate", {"script": "skill/pinkgolem/blueprints/tower.py", "args": ["--at", f"{CX},-61,{CZ}"], "build": True})
    check("generate: a phase refused (player in the way) is an error, not ok", e and "NOTHING was built" in t, t)
    t, e, _ = m.call("minecraft_generate", {"script": "skill/pinkgolem/blueprints/bakery.py", "args": []})
    check("generate: a missing blueprint lists the ones that exist", e and "cottage.py" in t, t)
    t, e, _ = m.call("minecraft_bot", {"action": "look_at", "player": "Steve"})
    check("unknown player: the error lists who is online", e and "Tester" in t, t)
finally:
    m.call("minecraft_undo", {"steps": 4})
    m.close()
    w.kill_bots(["Smoke"])
    w.reset(BOX)
    w.forceload(BOX, on=False)
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
