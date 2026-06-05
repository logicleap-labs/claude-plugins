#!/usr/bin/env python3
"""
verify-before-done :: Stop gate
================================
Refuses to let a turn END when the turn edited code but never ran verification.

Fires on every Stop. NO-OP unless the current segment edited source files.

Decision logic (segment = since last real user prompt):
  - no code edit                     -> PASS
  - code edit AND verified           -> PASS  (sentinel OR test/build/run command)
  - code edit AND NOT verified       -> BLOCK

Verified means either:
  * assistant text contains VERIFY-BEFORE-DONE: PASS (after edits), or
  * a Bash/shell command in the segment matches VERIFY_CMD_PATTERNS

Safety rails (fail-OPEN):
  * any exception -> exit 0
  * loop cap >= 2 prior blocks -> pass
  * kill switch env/file -> pass
"""
import sys, os, json, re

SENTINEL = "VERIFY-BEFORE-DONE: PASS"
BLOCK_TAG = "[verify-before-done gate]"

# Extensions we treat as "code changed" (not docs-only by default)
CODE_EXT = (
    ".py", ".js", ".ts", ".tsx", ".jsx", ".vue", ".svelte", ".go", ".rs",
    ".java", ".kt", ".swift", ".rb", ".php", ".cs", ".cpp", ".c", ".h",
    ".sql", ".sh", ".bash", ".zsh", ".yaml", ".yml", ".toml", ".json",
    ".gradle", ".m", ".mm", ".dart", ".astro", ".mdx",
)

# Docs-only paths skip the gate unless paired with code
DOC_ONLY = (".md", ".txt", ".rst")

VERIFY_CMD_PATTERNS = re.compile(
    r"(?i)"
    r"(npm\s+(run\s+)?(test|build|lint|typecheck|check)|"
    r"npx\s+(vitest|jest|tsc|eslint)|"
    r"(pnpm|yarn)\s+(test|build|lint|run)|"
    r"pytest|py\.test|"
    r"cargo\s+(test|check|build)|"
    r"go\s+test|"
    r"xcodebuild\s+test|swift\s+test|swift\s+build|"
    r"gradle\s+test|mvn\s+test|"
    r"make\s+(test|check|build)|"
    r"bundle\s+exec\s+rake\s+test|"
    r"phpunit|"
    r"dotnet\s+test|"
    r"playwright\s+test|"
    r"deno\s+test|"
    r"bun\s+test|"
    r"ruff\s+check|mypy|"
    r"tsc\s+--noEmit|"
    r"eslint|prettier\s+--check)"
)


def _passthrough(msg=None):
    if msg:
        sys.stderr.write(msg + "\n")
    sys.exit(0)


def _kill_switch(cwd):
    if os.environ.get("VERIFY_BEFORE_DONE_GATE", "").lower() in ("off", "0", "false", "no"):
        return True
    home = os.path.expanduser("~")
    if os.path.exists(os.path.join(home, ".claude", ".verify-before-done-off")):
        return True
    if cwd and os.path.exists(os.path.join(cwd, ".verify-before-done-off")):
        return True
    return False


def _iter_text(content):
    if isinstance(content, str):
        yield content
    elif isinstance(content, list):
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str):
                yield b["text"]


def _tool_uses(content):
    if isinstance(content, list):
        for b in content:
            if isinstance(b, dict) and b.get("type") == "tool_use":
                yield b.get("name", ""), (b.get("input") or {})


def _is_code_path(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in DOC_ONLY:
        return False
    if ext in CODE_EXT:
        return True
    # unknown ext: treat as code if not obviously docs
    base = os.path.basename(path).lower()
    if base in ("dockerfile", "makefile", "gemfile", "procfile"):
        return True
    return ext != ""


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        _passthrough()

    cwd = payload.get("cwd") or os.getcwd()
    if _kill_switch(cwd):
        _passthrough()

    transcript_path = payload.get("transcript_path")
    if not transcript_path or not os.path.exists(transcript_path):
        _passthrough()

    try:
        with open(transcript_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except Exception:
        _passthrough()
    lines = lines[-800:]

    entries = []
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            entries.append(json.loads(ln))
        except Exception:
            continue

    seg_start = 0
    for i in range(len(entries) - 1, -1, -1):
        e = entries[i]
        if e.get("type") == "user":
            msg = e.get("message", e)
            content = msg.get("content") if isinstance(msg, dict) else None
            is_tool_result = isinstance(content, list) and any(
                isinstance(b, dict) and b.get("type") == "tool_result" for b in content
            )
            has_text = any(t.strip() for t in _iter_text(content))
            if has_text and not is_tool_result:
                seg_start = i
                break
    segment = entries[seg_start:]

    code_edited = False
    verified = False
    blocks_so_far = 0

    for e in segment:
        etype = e.get("type")
        msg = e.get("message", e)
        content = msg.get("content") if isinstance(msg, dict) else None

        if etype == "assistant":
            for name, inp in _tool_uses(content):
                low = (name or "").lower()
                if low.endswith("edit") or low.endswith("write") or "multiedit" in low \
                   or low in ("edit", "write", "multiedit"):
                    fp = inp.get("file_path") or inp.get("path") or ""
                    if _is_code_path(fp):
                        code_edited = True
                if low.endswith("bash") or low == "bash":
                    cmd = inp.get("command") or ""
                    if VERIFY_CMD_PATTERNS.search(cmd):
                        verified = True
            for txt in _iter_text(content):
                if SENTINEL.lower() in txt.lower() and code_edited:
                    verified = True
                if BLOCK_TAG in txt:
                    blocks_so_far += 1

        if etype == "user" and isinstance(content, list):
            for b in content:
                if isinstance(b, dict):
                    tc = b.get("content")
                    txt = ""
                    if isinstance(tc, str):
                        txt = tc
                    elif isinstance(tc, list):
                        txt = " ".join(x.get("text", "") for x in tc if isinstance(x, dict))
                    if BLOCK_TAG in txt:
                        blocks_so_far += 1

    if not code_edited:
        _passthrough()

    if blocks_so_far >= 2:
        _passthrough()

    if verified:
        _passthrough()

    reason = (
        f"{BLOCK_TAG} You edited code this turn but have not verified the change. "
        "A clean compile or 'should work' is not proof. Invoke the `verify-before-done` skill: "
        "run the smallest test/build/lint/smoke command that exercises what you changed, "
        "read the output, fix failures, then end your message with "
        f"{SENTINEL} — <command> → <outcome>. "
        "(False positive? `touch .verify-before-done-off` in cwd.)"
    )
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        sys.stderr.write("verify-before-done gate skipped (%s)\n" % exc)
        sys.exit(0)