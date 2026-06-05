#!/usr/bin/env python3
"""
no-debug :: Stop gate
=====================
Refuses to let a turn END when the turn edited code that still contains
leftover DEBUG statements — console.log / debugger, pdb.set_trace /
breakpoint(), binding.pry / byebug, dd() / var_dump(), dbg!(), and the
debug-ish prints that never belong in shipped code.

Fires on every Stop. NO-OP unless the current segment edited source files
AND the added code contains a high-signal debug marker.

Decision logic (segment = since last real user prompt):
  - no code edit                       -> PASS
  - code edited, no debug markers      -> PASS
  - code edited, debug markers found   -> BLOCK
  - sentinel present                   -> PASS

Sentinel (override): an assistant line containing
  NO-DEBUG: INTENTIONAL — <reason>
bypasses the block (e.g. a CLI tool that prints to stdout by design).

Safety rails (fail-OPEN):
  * any exception -> exit 0
  * loop cap >= 2 prior blocks -> pass
  * kill switch env/file -> pass
  * console.error / console.warn and real loggers are NEVER flagged
  * ambiguous prints (print/Println/System.out.println) only flag with
    debug-ish content; a bare CLI print is left alone
  * commented-out lines (// or #) are never flagged
"""
import sys, os, json, re

SENTINEL = "NO-DEBUG: INTENTIONAL"
BLOCK_TAG = "[no-debug gate]"

# Extensions we treat as "code changed" (not docs-only by default).
# Mirrors no-stub / verify-before-done, minus markup-ish formats where the
# string "console.log" legitimately appears as prose.
CODE_EXT = (
    ".py", ".js", ".ts", ".tsx", ".jsx", ".vue", ".svelte", ".go", ".rs",
    ".java", ".kt", ".swift", ".rb", ".php", ".cs", ".cpp", ".c", ".h",
    ".sql", ".sh", ".bash", ".zsh", ".gradle", ".m", ".mm", ".dart",
    ".astro",
)

# Docs-only paths skip the gate.
DOC_ONLY = (".md", ".txt", ".rst", ".mdx", ".json", ".yaml", ".yml", ".toml")

# --- Debug markers ----------------------------------------------------------
# HIGH-SIGNAL: near-universally debug-only, flagged on sight. Each is matched
# against a single (non-comment) line of added code.
HIGH_SIGNAL = [
    # JS / TS
    (re.compile(r"\bconsole\s*\.\s*(log|debug|trace|dir)\s*\("), "console.log/debug/trace/dir"),
    (re.compile(r"\bdebugger\b\s*;?"), "debugger statement"),
    # Python
    (re.compile(r"\bpdb\s*\.\s*set_trace\s*\("), "pdb.set_trace()"),
    (re.compile(r"\bipdb\s*\.\s*set_trace\s*\("), "ipdb.set_trace()"),
    (re.compile(r"\bbreakpoint\s*\("), "breakpoint()"),
    (re.compile(r"^\s*import\s+i?pdb\b"), "import pdb/ipdb"),
    # Ruby
    (re.compile(r"\bbinding\s*\.\s*(pry|irb)\b"), "binding.pry/irb"),
    (re.compile(r"\bbyebug\b"), "byebug"),
    # PHP / Laravel
    (re.compile(r"\bvar_dump\s*\("), "var_dump()"),
    (re.compile(r"\bprint_r\s*\("), "print_r()"),
    (re.compile(r"(?<![A-Za-z0-9_])dd\s*\("), "dd()"),
    (re.compile(r"(?<![A-Za-z0-9_>])dump\s*\("), "dump()"),
    (re.compile(r"\berror_log\s*\("), "error_log()"),
    # Rust
    (re.compile(r"\bdbg!\s*\("), "dbg!() macro"),
]

# AMBIGUOUS: legit in CLIs/scripts, so only flag when the line ALSO carries
# debug-ish content (a DEBUG/TODO marker, "here", arrows, bangs, equals
# rules, or an emoji). Conservative on purpose.
AMBIGUOUS = [
    (re.compile(r"\bprint\s*\("), "print()"),                          # Python / others
    (re.compile(r"\bfmt\s*\.\s*Print(ln|f)?\s*\("), "fmt.Println/Printf"),  # Go
    (re.compile(r"\bSystem\s*\.\s*out\s*\.\s*print(ln)?\s*\("), "System.out.println"),  # Java/Kotlin
    (re.compile(r"\beprintln!\s*\("), "eprintln!()"),                  # Rust
]

# What makes an ambiguous print look like debug noise rather than real output.
DEBUG_ISH = re.compile(
    r"(?i)\b(debug|todo|xxx|fixme|here)\b"
    r"|<<<|>>>|!!!|==="
    r"|[\U0001F300-\U0001FAFF☀-➿]"   # emoji / dingbats
)

# A proper logger -> never debug noise. If one of these is on the line, skip it.
LOGGER_HINT = re.compile(
    r"(?i)\b(logger|logging\.getLogger|winston|pino|slog|log4j|zerolog|"
    r"console\s*\.\s*(error|warn|info)"
    r"|log\s*\.\s*(info|warn|error|debug|trace|fatal|panic)"
    r"|self\.log|this\.logger|Log\s*\.\s*(d|i|w|e|v))\b"
)

# Comment line -> never flagged.
COMMENT_LINE = re.compile(r"^\s*(//|#|/\*|\*)")


def _passthrough(msg=None):
    if msg:
        sys.stderr.write(msg + "\n")
    sys.exit(0)


def _kill_switch(cwd):
    if os.environ.get("NO_DEBUG_GATE", "").lower() in ("off", "0", "false", "no"):
        return True
    home = os.path.expanduser("~")
    if os.path.exists(os.path.join(home, ".claude", ".no-debug-off")):
        return True
    if cwd and os.path.exists(os.path.join(cwd, ".no-debug-off")):
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
    # unknown ext: be conservative — only known code extensions count, so we
    # don't false-positive on data/config files that mention "console.log".
    return False


def _added_text(name, inp):
    """Return the chunk of NEW code an Edit/Write/MultiEdit introduces."""
    low = (name or "").lower()
    parts = []
    if low.endswith("write") or low == "write":
        c = inp.get("content")
        if isinstance(c, str):
            parts.append(c)
    elif "multiedit" in low:
        for ed in (inp.get("edits") or []):
            if isinstance(ed, dict) and isinstance(ed.get("new_string"), str):
                parts.append(ed["new_string"])
    elif low.endswith("edit") or low == "edit":
        ns = inp.get("new_string")
        if isinstance(ns, str):
            parts.append(ns)
    return "\n".join(parts)


def _scan_for_debug(text):
    """Return a sorted list of distinct debug reasons found in `text`.

    Scans line-by-line so we can skip comments and apply the logger guard
    and the ambiguous-print content rule per line.
    """
    found = set()
    for raw in text.splitlines():
        line = raw
        # Never flag commented-out debug lines.
        if COMMENT_LINE.match(line):
            continue
        # Never flag a line that is a real logger call.
        if LOGGER_HINT.search(line):
            continue

        for pat, label in HIGH_SIGNAL:
            if pat.search(line):
                found.add(label)

        for pat, label in AMBIGUOUS:
            if pat.search(line) and DEBUG_ISH.search(line):
                found.add(label + " (debug content)")

    return sorted(found)


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
    sentinel = False
    blocks_so_far = 0
    reasons = set()

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
                        added = _added_text(name, inp)
                        if added:
                            for r in _scan_for_debug(added):
                                reasons.add(r)
            for txt in _iter_text(content):
                if SENTINEL.lower() in txt.lower():
                    sentinel = True
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

    if not code_edited or not reasons:
        _passthrough()

    if sentinel:
        _passthrough()

    if blocks_so_far >= 2:
        _passthrough()

    found = ", ".join(sorted(reasons))
    reason = (
        f"{BLOCK_TAG} You edited code this turn that still contains leftover debug "
        f"statements: {found}. Debug noise is not production output. Invoke the "
        "`no-debug` skill: strip each debug print/breakpoint (or, if you need "
        "persistent logging, replace it with a real logger — console.error/warn or "
        "logger.info, not console.log). If a print is intentional (a CLI tool that "
        "writes to stdout by design), say so explicitly with a line: "
        f"{SENTINEL} — <reason>. "
        "(False positive? `touch .no-debug-off` in cwd.)"
    )
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        sys.stderr.write("no-debug gate skipped (%s)\n" % exc)
        sys.exit(0)
