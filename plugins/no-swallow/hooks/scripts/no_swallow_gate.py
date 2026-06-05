#!/usr/bin/env python3
"""
no-swallow :: Stop gate
=======================
Refuses to let a turn END when the turn edited code that SILENTLY SWALLOWS an
error/exception — a catch/except that neither handles, logs, re-raises, nor
returns. The classic `except: pass`, the empty `catch (e) {}`, the
`.catch(() => {})` that turns a failure into silence.

Fires on every Stop. NO-OP unless the current segment edited source files
AND the added code contains a swallowed handler.

Decision logic (segment = since last real user prompt):
  - no code edit                          -> PASS
  - code edited, no swallowed handlers    -> PASS
  - code edited, swallowed handler found  -> BLOCK
  - sentinel present                      -> PASS

Sentinel (override): an assistant line containing
  NO-SWALLOW: INTENTIONAL — <reason>
bypasses the block (e.g. genuinely best-effort optional cleanup).

Safety rails (fail-OPEN — this gate is heuristic and harder than the others, so
when in doubt it PASSES):
  * any exception -> exit 0
  * loop cap >= 2 prior blocks -> pass
  * kill switch env/file -> pass
  * a handler that LOGS / RE-RAISES / RETURNS / assigns / calls anything
    meaningful is NOT swallowed and is never flagged
  * Swift `try?` (optional-try) is a language idiom, never flagged
  * empty-block detection is line-based and conservative; ambiguous bodies pass
"""
import sys, os, json, re

SENTINEL = "NO-SWALLOW: INTENTIONAL"
BLOCK_TAG = "[no-swallow gate]"

# Extensions we treat as "code changed" (not docs-only by default).
# Mirrors no-debug / no-stub / verify-before-done.
CODE_EXT = (
    ".py", ".js", ".ts", ".tsx", ".jsx", ".vue", ".svelte", ".go", ".rs",
    ".java", ".kt", ".swift", ".rb", ".php", ".cs", ".cpp", ".c", ".h",
    ".sql", ".sh", ".bash", ".zsh", ".gradle", ".m", ".mm", ".dart",
    ".astro",
)

# Docs-only paths skip the gate.
DOC_ONLY = (".md", ".txt", ".rst", ".mdx", ".json", ".yaml", ".yml", ".toml")

# --- "Handled" signals ------------------------------------------------------
# If a handler body contains any of these, the error is being dealt with —
# logged, re-raised, returned, surfaced, or otherwise acted on. NOT swallowed.
HANDLED = re.compile(
    r"(?i)"
    r"\b(log|logger|logging|console\s*\.\s*(error|warn|info|log)|print|println|"
    r"printf|fmt\s*\.\s*(print|error|fprintf)|panic|fatal|warn|trace|slog|"
    r"raise|throw|rethrow|reraise|abort|exit|os\.exit|sys\.exit|"
    r"return|yield|reject|resolve|callback|cb|next|emit|dispatch|notify|"
    r"set[A-Za-z]*\(|setState|toast|alert|report|capture|sentry|rollbar|"
    r"assert|retry|fallback|recover|handle|cleanup\(|"
    r"res\s*\.\s*(status|json|send)|response\s*\.\s*)"
    r"|=\s*[^=]"          # an assignment (sets a variable / error state)
    r"|err\s*!=\s*nil"    # nested Go check inside the body = doing work
)

# Trivial promise-handler bodies that swallow: () => {}, () => null,
# () => undefined, function(){}, () => void 0, e => {}.
PROMISE_SWALLOW = re.compile(
    r"\.catch\s*\(\s*"
    r"(?:async\s+)?"
    r"(?:function\s*\w*\s*\([^)]*\)|\([^)]*\)|[A-Za-z_$][\w$]*)\s*"
    r"=>?\s*"
    r"(?:\{\s*\}|null|undefined|void\s+0)\s*"
    r"\)"
)

# Python `except ...:` opener.
PY_EXCEPT = re.compile(r"^(\s*)except\b[^:]*:\s*(.*)$")
# Brace-language catch opener (JS/TS/Java/Kotlin/C#/Swift/C++).
CATCH_OPEN = re.compile(r"\bcatch\b\s*(\([^)]*\)\s*)?\{")
# Swift bare `catch {` (no paren).
SWIFT_CATCH = re.compile(r"\bcatch\b\s*\{")
# Go empty error check: `if err != nil {` then immediately `}`.
GO_ERR_OPEN = re.compile(r"\bif\s+\w*err\w*\s*!=\s*nil\s*\{")

# Body-only statements that DON'T count as handling (pure swallow).
PY_NOOP_BODY = re.compile(r"^\s*(pass|\.\.\.|continue|break)\s*(#.*)?$")
# A pure comment line (no real statement).
PY_COMMENT = re.compile(r"^\s*#")
BRACE_COMMENT = re.compile(r"^\s*(//|/\*|\*)")


def _passthrough(msg=None):
    if msg:
        sys.stderr.write(msg + "\n")
    sys.exit(0)


def _kill_switch(cwd):
    if os.environ.get("NO_SWALLOW_GATE", "").lower() in ("off", "0", "false", "no"):
        return True
    home = os.path.expanduser("~")
    if os.path.exists(os.path.join(home, ".claude", ".no-swallow-off")):
        return True
    if cwd and os.path.exists(os.path.join(cwd, ".no-swallow-off")):
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
    # unknown ext: be conservative — only known code extensions count.
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


def _python_swallows(lines):
    """Detect Python `except ...:` whose body is ONLY pass/.../continue/break.

    Inline form (`except X: pass`) and multi-line indented bodies. A body that
    contains anything else (a log, raise, return, assignment, real call) is
    handled and not flagged. Comments alone don't count as handling, but the
    sentinel covers deliberate cases.
    """
    found = set()
    for i, raw in enumerate(lines):
        m = PY_EXCEPT.match(raw)
        if not m:
            continue
        indent, inline = m.group(1), m.group(2).strip()
        bare = re.match(r"^(\s*)except\s*:", raw) is not None

        # Inline body on the same line: `except X: pass`
        if inline:
            # strip a trailing comment
            stmt = inline.split("#", 1)[0].strip()
            if stmt in ("pass", "...", "continue", "break"):
                found.add("bare `except:` swallows (pass)" if bare
                          else "`except ...:` body is only pass/.../continue")
            continue

        # Multi-line: scan the indented block below.
        base = len(indent)
        body_noop_only = True
        saw_body = False
        j = i + 1
        while j < len(lines):
            ln = lines[j]
            if not ln.strip():
                j += 1
                continue
            cur_indent = len(ln) - len(ln.lstrip())
            if cur_indent <= base:
                break  # block ended
            saw_body = True
            if PY_COMMENT.match(ln):
                j += 1
                continue  # a comment is not handling, but not real code either
            if PY_NOOP_BODY.match(ln):
                j += 1
                continue
            # real statement -> handled (or at least doing something)
            body_noop_only = False
            break
        if saw_body and body_noop_only:
            found.add("bare `except:` swallows (empty body)" if bare
                      else "`except ...:` body is only pass/.../continue")
    return found


def _brace_block_body(text, open_idx):
    """Return (body_string, end_idx) for a `{...}` starting at the `{` at
    open_idx, by matching braces. None on imbalance."""
    depth = 0
    i = open_idx
    n = len(text)
    while i < n:
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[open_idx + 1:i], i
        i += 1
    return None, None


def _body_is_swallow(body):
    """True if a brace-block body is effectively empty / only comments —
    i.e. nothing that handles the error."""
    for raw in body.splitlines():
        s = raw.strip()
        if not s:
            continue
        if BRACE_COMMENT.match(raw) or s == "*/" or s.startswith("*"):
            continue  # comment is not handling
        if HANDLED.search(s):
            return False
        # any other real statement -> doing something, not a swallow
        return False
    return True


def _brace_swallows(text):
    """Detect empty `catch (...) {}` / `catch {}` (JS/TS/Java/Kotlin/C#/Swift/
    C++) and empty Go `if err != nil {}`. Conservative: only clearly-empty
    (or comment-only) bodies."""
    found = set()

    # catch ( ... ) { ... }  and Swift  catch { ... }
    for m in re.finditer(r"\bcatch\b\s*(\([^)]*\)\s*)?\{", text):
        open_idx = text.index("{", m.start())
        body, _ = _brace_block_body(text, open_idx)
        if body is None:
            continue  # imbalance -> fail open
        if _body_is_swallow(body):
            found.add("empty `catch` block swallows the error")

    # Go: if err != nil { }  — only the clearly-empty case.
    for m in re.finditer(GO_ERR_OPEN, text):
        open_idx = text.index("{", m.start())
        body, _ = _brace_block_body(text, open_idx)
        if body is None:
            continue
        # Go: empty means truly nothing (a lone comment we still flag-lenient:
        # treat comment-only as swallow too, matching brace rule).
        if _body_is_swallow(body):
            found.add("empty `if err != nil {}` swallows the error (Go)")

    return found


def _scan_for_swallows(text):
    """Return a sorted list of distinct swallow reasons found in `text`."""
    found = set()

    # Promise-style swallow: .catch(() => {}) etc.
    if PROMISE_SWALLOW.search(text):
        found.add("`.catch(() => {})` swallows the rejection")

    lines = text.splitlines()
    found |= _python_swallows(lines)
    found |= _brace_swallows(text)

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
                            for r in _scan_for_swallows(added):
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
        f"{BLOCK_TAG} You edited code this turn that silently swallows an "
        f"error: {found}. A caught error that's neither handled, logged, "
        "re-raised, nor returned is a bug that hides itself. Invoke the "
        "`no-swallow` skill: handle the error (do the real recovery), log it "
        "(with the project's logger), re-raise/throw it, or return a real "
        "fallback — never an empty `pass`/`{}`. If the swallow is genuinely "
        "intentional (best-effort optional cleanup), say so explicitly with a "
        f"line: {SENTINEL} — <reason>. "
        "(False positive? `touch .no-swallow-off` in cwd.)"
    )
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        sys.stderr.write("no-swallow gate skipped (%s)\n" % exc)
        sys.exit(0)
