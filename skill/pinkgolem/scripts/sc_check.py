"""sc_check.py — catch scarpet mistakes BEFORE `script load` (a failed load UNLOADS the running app).

    python3 sc_check.py scarpet-apps/myapp.sc [more.sc ...]

Checks every top-level function (a line starting with `name(args) ->`) for balanced ( [ { outside strings and //
comments, and reports the first function where the running depth is not back to 0. Exit code 1 on a problem.
Known scarpet traps it also flags: `[...] + list` (lists ADD element-wise — use l += x or a helper) and
`l:N || default` / `l:N != null` (indexes WRAP AROUND: a missing optional element reads as l:(N % length) — a
display's scale once read its own x coordinate and filled the sky). `continue()` outside a loop is not detected.
"""
import re
import sys


def strip(line):
    out, i, q = "", 0, None
    while i < len(line):
        c = line[i]
        if q:
            if c == "\\":
                i += 2
                continue
            if c == q:
                q = None
            i += 1
            continue
        if c in "'\"":
            q = c
            i += 1
            continue
        if line[i:i + 2] == "//":
            break
        out += c
        i += 1
    return out


def check(path):
    src = open(path, encoding="utf-8").read().split("\n")
    depth, fn, bad = 0, None, []
    for n, line in enumerate(src, 1):
        if re.match(r"^[A-Za-z_]\w*\(.*\)\s*->", line):
            if depth != 0 and fn:
                bad.append(f"{path}:{fn[0]} {fn[1]!r} leaves depth {depth:+d}")
                depth = 0
            fn = (n, line[:60])
        s = strip(line)
        if re.search(r"\]\s*\+\s*[A-Za-z_\[]", s) and "range" not in s:
            bad.append(f"{path}:{n} list + … adds element-wise in scarpet: {line.strip()[:80]}")
        if re.search(r"\w:\d+\s*\|\|", s) or re.search(r"\w:\d+\s*!=\s*null", s):
            bad.append(f"{path}:{n} `list:N || default` — scarpet list indexes WRAP AROUND (l:3 of a 3-list is l:0), "
                       f"so a missing optional element is never null; check length(l) > N: {line.strip()[:80]}")
        for ch in s:
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth -= 1
    if depth != 0:
        bad.append(f"{path}: end of file depth {depth:+d} (last function {fn})")
    return bad


if __name__ == "__main__":
    problems = []
    for p in sys.argv[1:]:
        problems += check(p)
    for b in problems:
        print("✗", b)
    if not problems:
        print("✓ brackets balanced in", ", ".join(sys.argv[1:]))
    sys.exit(1 if problems else 0)
