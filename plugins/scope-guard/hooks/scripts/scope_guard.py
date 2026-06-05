#!/usr/bin/env python3
"""
scope-guard :: PreToolUse gate
==============================
Refuses an Edit/Write/MultiEdit when the target file is OUTSIDE the declared
scope for this task. Keeps an agent in its lane: no drive-by edits, no
"while I'm here" refactors, no clobbering a file another agent owns.

Fires on every Edit/Write/MultiEdit/NotebookEdit. NO-OP unless a scope is
declared (so it never gets in the way until you opt in).

Scope is declared in priority order:
  1. SCOPE_GUARD_PATHS env var      ->  "src/**, !src/legacy/**"
  2. .scope-guard file in cwd       ->  one glob per line ('#' comments, '!' negates)
  3. Latest `SCOPE-GUARD: a, b, c`  ->  sentinel in the assistant transcript

Matching:
  * globs are POSIX-style, relative to cwd; '**' spans directories
  * a bare pattern with no '/' also matches the file's basename anywhere
  * a directory ('src' or 'src/') is treated as 'src/**'
  * '!pattern' is an exclusion (deny even if an allow matched)

Decision:
  * no scope declared            -> ALLOW (fail open)
  * path matches an exclusion    -> DENY
  * path matches an allow glob   -> ALLOW
  * scope declared, no match     -> DENY

Safety rails (fail-OPEN):
  * any exception                -> allow (exit 0)
  * kill switch env/file         -> allow
  * scope-guard's own files (.scope-guard, off-switch) are always allowed
"""
import sys, os, json, re, fnmatch

BLOCK_TAG = "[scope-guard]"
SENTINEL_RE = re.compile(r"(?im)^\s*SCOPE-GUARD:\s*(.+?)\s*$")
ALWAYS_ALLOW = (".scope-guard", ".scope-guard-off")


def _allow(msg=None):
    if msg:
        sys.stderr.write(msg + "\n")
    sys.exit(0)


def _deny(reason):
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    print(json.dumps(out))
    sys.exit(0)


def _kill_switch(cwd):
    if os.environ.get("SCOPE_GUARD_GATE", "").lower() in ("off", "0", "false", "no"):
        return True
    home = os.path.expanduser("~")
    if os.path.exists(os.path.join(home, ".claude", ".scope-guard-off")):
        return True
    if cwd and os.path.exists(os.path.join(cwd, ".scope-guard-off")):
        return True
    return False


def _split_patterns(blob):
    out = []
    for chunk in re.split(r"[,\n]", blob):
        p = chunk.strip()
        if not p or p.startswith("#"):
            continue
        out.append(p)
    return out


def _read_scope(cwd, transcript_path):
    # 1. env
    env = os.environ.get("SCOPE_GUARD_PATHS", "").strip()
    if env:
        return _split_patterns(env), "env"

    # 2. .scope-guard file
    sf = os.path.join(cwd, ".scope-guard") if cwd else ".scope-guard"
    if os.path.exists(sf):
        try:
            with open(sf, "r", encoding="utf-8", errors="ignore") as f:
                pats = _split_patterns(f.read())
            if pats:
                return pats, ".scope-guard"
        except Exception:
            pass

    # 3. latest SCOPE-GUARD: sentinel in the assistant transcript
    if transcript_path and os.path.exists(transcript_path):
        try:
            with open(transcript_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()[-1200:]
        except Exception:
            lines = []
        latest = None
        for ln in lines:
            ln = ln.strip()
            if not ln:
                continue
            try:
                e = json.loads(ln)
            except Exception:
                continue
            if e.get("type") != "assistant":
                continue
            msg = e.get("message", e)
            content = msg.get("content") if isinstance(msg, dict) else None
            texts = []
            if isinstance(content, str):
                texts.append(content)
            elif isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "text":
                        texts.append(b.get("text", ""))
            for t in texts:
                for m in SENTINEL_RE.finditer(t):
                    val = m.group(1)
                    # ignore doc/placeholder examples like "SCOPE-GUARD: <globs>"
                    if "<" in val or ">" in val:
                        continue
                    latest = val
        if latest:
            return _split_patterns(latest), "sentinel"

    return [], None


def _norm(path, cwd):
    if not path:
        return None
    p = path
    if os.path.isabs(p) and cwd:
        try:
            p = os.path.relpath(p, cwd)
        except Exception:
            pass
    p = p.replace(os.sep, "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def _glob_to_re(glob):
    # directory -> recursive
    g = glob.strip()
    if g.endswith("/"):
        g = g + "**"
    elif "*" not in g and "?" not in g and "." not in os.path.basename(g):
        # bare 'src' style dir token
        g = g + "/**"
    # translate, honoring '**'
    g = g.replace("/", "\x00")
    parts = []
    i = 0
    while i < len(g):
        c = g[i]
        if c == "*":
            if i + 1 < len(g) and g[i + 1] == "*":
                parts.append(".*")
                i += 2
                continue
            parts.append("[^\x00]*")
        elif c == "?":
            parts.append("[^\x00]")
        elif c == "\x00":
            parts.append("/")
        else:
            parts.append(re.escape(c))
        i += 1
    pat = "".join(parts).replace("\x00", "/")
    return re.compile("^" + pat + "$")


def _matches(path, glob):
    if _glob_to_re(glob).match(path):
        return True
    # bare pattern (no slash) also matches basename anywhere
    if "/" not in glob.strip().rstrip("/"):
        if fnmatch.fnmatch(os.path.basename(path), glob.strip()):
            return True
    return False


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        _allow()

    cwd = payload.get("cwd") or os.getcwd()
    if _kill_switch(cwd):
        _allow()

    tool_input = payload.get("tool_input") or {}
    target = tool_input.get("file_path") or tool_input.get("path") or tool_input.get("notebook_path")
    path = _norm(target, cwd)
    if not path:
        _allow()

    if os.path.basename(path) in ALWAYS_ALLOW:
        _allow()

    patterns, source = _read_scope(cwd, payload.get("transcript_path"))
    if not patterns:
        _allow()

    allows = [p for p in patterns if not p.startswith("!")]
    denies = [p[1:].strip() for p in patterns if p.startswith("!")]

    for d in denies:
        if _matches(path, d):
            _deny(
                f"{BLOCK_TAG} `{path}` is explicitly excluded from this task's scope "
                f"(!{d}, via {source}). If this edit is genuinely in scope, update the "
                f"scope declaration — don't widen it silently."
            )

    for a in allows:
        if _matches(path, a):
            _allow()

    shown = ", ".join(allows[:8]) + (" …" if len(allows) > 8 else "")
    _deny(
        f"{BLOCK_TAG} `{path}` is outside this task's declared scope ({source}: {shown}). "
        "This looks like a drive-by edit. If it's truly needed, STOP and either (a) re-declare "
        "scope with a new `SCOPE-GUARD: <globs>` line that includes it and say why, or "
        "(b) leave the file alone — on a shared tree it may belong to another agent. "
        "(False positive? `touch .scope-guard-off` in cwd, or unset the scope.)"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        sys.stderr.write("scope-guard skipped (%s)\n" % exc)
        sys.exit(0)
