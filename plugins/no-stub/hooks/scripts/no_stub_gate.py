#!/usr/bin/env python3
"""
no-stub :: Stop gate
====================
Refuses to let a turn END when the turn edited code that still contains
placeholder / stub markers — TODO/FIXME, NotImplementedError, "your code
here", empty `...` function bodies, and friends.

Fires on every Stop. NO-OP unless the current segment edited source files
AND the added code contains a stub marker.

Decision logic (segment = since last real user prompt):
  - no code edit                      -> PASS
  - code edited, no stub markers      -> PASS
  - code edited, stub markers found   -> BLOCK
  - sentinel present                  -> PASS

Sentinel (override): an assistant line containing
  NO-STUB: INTENTIONAL — <reason>
bypasses the block (e.g. a deliberate interface stub / abstract method).

Safety rails (fail-OPEN):
  * any exception -> exit 0
  * loop cap >= 2 prior blocks -> pass
  * kill switch env/file -> pass
  * bare `...` only flagged when it is the SOLE statement of a body
"""
import sys, os, json, re

SENTINEL = "NO-STUB: INTENTIONAL"
BLOCK_TAG = "[no-stub gate]"

# Extensions we treat as "code changed" (not docs-only by default).
# Mirrors verify-before-done, minus markup-ish formats where stub phrases
# legitimately appear as prose.
CODE_EXT = (
    ".py", ".js", ".ts", ".tsx", ".jsx", ".vue", ".svelte", ".go", ".rs",
    ".java", ".kt", ".swift", ".rb", ".php", ".cs", ".cpp", ".c", ".h",
    ".sql", ".sh", ".bash", ".zsh", ".gradle", ".m", ".mm", ".dart",
    ".astro",
)

# Docs-only paths skip the gate.
DOC_ONLY = (".md", ".txt", ".rst", ".mdx", ".json", ".yaml", ".yml", ".toml")

# --- Stub markers -----------------------------------------------------------
# Comment-marker tags: TODO / FIXME / XXX / HACK as a word, near a comment
# lead-in or standalone. We keep this tight to dodge prose like "todoist".
MARKER_PATTERNS = [
    # comment markers (must look like a marker: followed by :, space+text, or EOL)
    (re.compile(r"(?<![A-Za-z0-9_])(TODO|FIXME|XXX|HACK)\b(?![A-Za-z0-9_])"),
     "TODO/FIXME/XXX/HACK marker"),
    # explicit not-implemented signals
    (re.compile(r"NotImplementedError"), "NotImplementedError"),
    (re.compile(r"(?i)\bnot[ _-]?implemented\b"), '"not implemented"'),
    (re.compile(r"(?i)\bunimplemented\b"), '"unimplemented"'),
    (re.compile(r"(?i)\btodo!\s*\("), "Rust todo!() macro"),
    (re.compile(r"(?i)\bunimplemented!\s*\("), "Rust unimplemented!() macro"),
    # throw new Error("not implemented") and variants (covered by not-implemented),
    # plus generic stub throw/raise phrasing
    (re.compile(r"(?i)(throw|raise)\b.{0,40}\b(not\s+implemented|stub|placeholder)"),
     "stub throw/raise"),
    # natural-language placeholder phrases
    (re.compile(r"(?i)your\s+code\s+here"), '"your code here"'),
    (re.compile(r"(?i)implementation\s+(goes|here)"), '"implementation goes here"'),
    (re.compile(r"(?i)(rest|remainder)\s+of\s+.{0,40}\s+(here|goes here|implementation)"),
     '"rest of ... here"'),
    (re.compile(r"(?i)fill\s+(this|in)\s+(in|out|later)?"), '"fill this in"'),
    # placeholder/stub ONLY in a comment or intent phrase — never the bare word,
    # so JSX `placeholder="Email"`, CSS `::placeholder`, and identifiers like
    # `StubServer` don't false-positive.
    (re.compile(r"(?i)(#|//|/\*)\s*placeholder\b|placeholder\s+(impl|implementation|for now|until)"),
     '"placeholder" comment'),
    (re.compile(r"(?i)(#|//|/\*)\s*stub\b|\bstub(bed)?\s+(out|this|the)\b|"
                r"\bstub\s+(impl|implementation|for now)"),
     '"stub" comment'),
]

# Bodies that are ONLY an ellipsis / pass-with-todo. Matched line-by-line.
# `pass  # ...`  /  `// ...`  /  `# ...`  as a body-only placeholder.
PASS_TODO = re.compile(r"^\s*(pass|return)\b.*#\s*(TODO|FIXME|\.\.\.|stub|placeholder)",
                       re.IGNORECASE)
COMMENT_ELLIPSIS = re.compile(r"^\s*(#|//)\s*\.\.\.\s*$")
BARE_ELLIPSIS = re.compile(r"^\s*\.\.\.\s*$")

# Lines that look like a JS/Python spread / type-hint ellipsis we must NOT flag:
#   foo(...args)   [...arr]   {...obj}   Tuple[int, ...]   def f(x: ...)
# These never match BARE_ELLIPSIS (which requires `...` to be the whole line),
# so they're already safe; BARE handling below adds the body-context guard.

DEF_OPENER = re.compile(r"^\s*(def |async def |function |fn |func |sub |"
                        r"(public|private|protected|static|override|final|"
                        r"async|export|const|let|var)\b.*[({]).*", re.IGNORECASE)


def _passthrough(msg=None):
    if msg:
        sys.stderr.write(msg + "\n")
    sys.exit(0)


def _kill_switch(cwd):
    if os.environ.get("NO_STUB_GATE", "").lower() in ("off", "0", "false", "no"):
        return True
    home = os.path.expanduser("~")
    if os.path.exists(os.path.join(home, ".claude", ".no-stub-off")):
        return True
    if cwd and os.path.exists(os.path.join(cwd, ".no-stub-off")):
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
    # unknown ext: be conservative — only known code extensions count,
    # so we don't false-positive on data/config files with "todo" strings.
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


def _bare_ellipsis_is_body(lines, idx):
    """True if a bare `...` line is the SOLE statement of a function body.

    Heuristic: the non-blank line immediately preceding the `...` opens a
    definition (ends with `:` for Python, or `{` for brace languages), and the
    next non-blank line is NOT another statement at the same/deeper indent.
    Avoids flagging spreads/type-hints (those never reach here — they aren't
    whole-line `...`).
    """
    # find previous non-blank line
    j = idx - 1
    while j >= 0 and not lines[j].strip():
        j -= 1
    if j < 0:
        return False
    prev = lines[j].rstrip()
    opens_block = prev.endswith(":") or prev.endswith("{") or DEF_OPENER.match(prev or "")
    if not opens_block:
        return False
    # find next non-blank line
    k = idx + 1
    while k < len(lines) and not lines[k].strip():
        k += 1
    if k < len(lines):
        nxt = lines[k].strip()
        # if the body continues with real code, the `...` wasn't the sole stmt
        if nxt and nxt not in ("}", ")", "});") and not nxt.startswith(("#", "//")):
            # a closing brace right after is fine (sole stmt); real code is not
            if not nxt.startswith(("}", ")")):
                return False
    return True


def _scan_for_stubs(text):
    """Return a sorted list of distinct stub reasons found in `text`."""
    found = set()
    for pat, label in MARKER_PATTERNS:
        if pat.search(text):
            found.add(label)

    lines = text.splitlines()
    for i, raw in enumerate(lines):
        if PASS_TODO.match(raw):
            found.add("placeholder pass/return body")
        if COMMENT_ELLIPSIS.match(raw):
            found.add("comment ellipsis placeholder")
        if BARE_ELLIPSIS.match(raw) and _bare_ellipsis_is_body(lines, i):
            found.add("empty `...` function body")
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
                            for r in _scan_for_stubs(added):
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
        f"{BLOCK_TAG} You edited code this turn that still contains stub/placeholder "
        f"markers: {found}. Half-written code is not done. Invoke the `no-stub` skill: "
        "replace each placeholder with a real, working implementation (or delete it), "
        "then end the turn. If a stub is genuinely intentional (an interface, abstract "
        "method, or deliberate not-yet-built path), say so explicitly with a line: "
        f"{SENTINEL} — <reason>. "
        "(False positive? `touch .no-stub-off` in cwd.)"
    )
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        sys.stderr.write("no-stub gate skipped (%s)\n" % exc)
        sys.exit(0)
