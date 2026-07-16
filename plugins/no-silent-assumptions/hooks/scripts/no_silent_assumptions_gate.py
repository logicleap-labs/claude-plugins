#!/usr/bin/env python3
"""
no-silent-assumptions :: Stop gate
==================================
Refuses to let a turn END when the turn made material guesses — about the
environment, a data shape, an API's behavior, an edge case — and never
surfaced them. A buried guess is a bug report the human files next week.

Fires on every Stop. NO-OP unless the current segment edited code AND the
added code carries assumption-laden language, with no "Assumptions:" block
(and no sentinel) anywhere in the assistant's own text this segment.

Decision logic (segment = since last real user prompt):
  - no code edit                                   -> PASS
  - code edited, no assumption markers in adds     -> PASS
  - markers found, "Assumptions:" block declared   -> PASS
  - markers found, nothing surfaced                -> BLOCK
  - sentinel present                               -> PASS

Sentinel (override): an assistant line containing
  NO-SILENT-ASSUMPTIONS: INTENTIONAL — <reason>
bypasses the block (e.g. the "assumption" is a documented invariant, not
a guess made this turn).

Safety rails (fail-OPEN):
  * any exception -> exit 0
  * loop cap >= 2 prior blocks -> pass
  * kill switch env/file -> pass
  * conservative on purpose: only HIGH-precision phrases flag ("assuming
    the API returns", "guessing this is", "not sure if") — a bare "assume"
    in an assert message or a variable named `assumed_role` never fires
  * docs-only edits skip the gate
"""
import sys, os, json, re

SENTINEL = "NO-SILENT-ASSUMPTIONS: INTENTIONAL"
BLOCK_TAG = "[no-silent-assumptions gate]"

# Extensions we treat as "code changed". Mirrors no-debug / no-stub.
CODE_EXT = (
    ".py", ".js", ".ts", ".tsx", ".jsx", ".vue", ".svelte", ".go", ".rs",
    ".java", ".kt", ".swift", ".rb", ".php", ".cs", ".cpp", ".c", ".h",
    ".sql", ".sh", ".bash", ".zsh", ".gradle", ".m", ".mm", ".dart",
    ".astro",
)

DOC_ONLY = (".md", ".txt", ".rst", ".mdx", ".json", ".yaml", ".yml", ".toml")

# HIGH-PRECISION assumption phrases. Each is a multi-word guess-shaped phrase
# the model writes into comments/strings while papering over unknowns. A bare
# "assume" / "expect" / "should" never fires — only the guessy compounds.
ASSUMPTION_MARKERS = [
    (re.compile(r"(?i)\bassum(?:e|es|ing)\s+(?:the|this|that|it|a)\b"), "an 'assuming the/that…' guess"),
    (re.compile(r"(?i)\bguess(?:ing)?\s+(?:the|this|that|it)\b"), "a 'guessing the/that…' guess"),
    (re.compile(r"(?i)\bnot\s+sure\s+(?:if|whether|what|how)\b"), "a 'not sure if…' uncertainty"),
    (re.compile(r"(?i)\bprobably\s+(?:works|fine|correct|safe|ok(?:ay)?|returns|the\s+same)\b"), "a 'probably works/fine' hedge"),
    (re.compile(r"(?i)\bshould\s+(?:probably|hopefully)\b"), "a 'should probably/hopefully' hedge"),
    (re.compile(r"(?i)\bhopefully\s+(?:this|the|it)\b"), "a 'hopefully this…' hedge"),
    (re.compile(r"(?i)\bmight\s+(?:not\s+)?(?:work|exist|be\s+(?:correct|right|wrong|present|set|null|none|empty))\b"), "a 'might (not) work/be…' hedge"),
    (re.compile(r"(?i)\bif\s+(?:the\s+)?API\s+(?:actually|really)\b"), "an 'if the API actually…' doubt"),
    (re.compile(r"(?i)\bTODO[:\s].{0,30}\b(verify|confirm|check\s+(?:if|whether|with))\b"), "a 'TODO: verify/confirm' deferral"),
    (re.compile(r"(?i)\buntested\s+(?:assumption|path|edge\s+case)\b"), "an explicit untested assumption"),
    (re.compile(r"(?i)\bno\s+idea\s+(?:if|whether|what)\b"), "a 'no idea if…' uncertainty"),
]

# An "Assumptions:" block in the assistant's own text counts as surfaced.
DECLARED_RE = re.compile(r"(?im)^\s*(?:\*\*)?Assumptions?(?:\*\*)?\s*(?:made)?\s*:")


def _passthrough(msg=None):
    if msg:
        sys.stderr.write(msg + "\n")
    sys.exit(0)


def _kill_switch(cwd):
    if os.environ.get("NO_SILENT_ASSUMPTIONS_GATE", "").lower() in ("off", "0", "false", "no"):
        return True
    home = os.path.expanduser("~")
    if os.path.exists(os.path.join(home, ".claude", ".no-silent-assumptions-off")):
        return True
    if cwd and os.path.exists(os.path.join(cwd, ".no-silent-assumptions-off")):
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
    return ext in CODE_EXT


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


def _scan_for_assumptions(text):
    """Return distinct assumption reasons found in added code."""
    found = set()
    for line in text.splitlines():
        for pat, label in ASSUMPTION_MARKERS:
            if pat.search(line):
                found.add(label)
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
    declared = False
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
                            for r in _scan_for_assumptions(added):
                                reasons.add(r)
            for txt in _iter_text(content):
                if SENTINEL.lower() in txt.lower():
                    sentinel = True
                if DECLARED_RE.search(txt):
                    declared = True
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

    if sentinel or declared:
        _passthrough()

    if blocks_so_far >= 2:
        _passthrough()

    found = "; ".join(sorted(reasons))
    reason = (
        f"{BLOCK_TAG} You edited code this turn that carries unsurfaced guesses: {found}. "
        "A guess buried in a comment is invisible to the human who has to live with it. "
        "Invoke the `no-silent-assumptions` skill: list every material assumption you made "
        "(environment, data shape, API behavior, edge cases) in a short block starting with "
        "a line `Assumptions:` — one per line, with what would break if it's wrong — before "
        "claiming done. If the flagged phrase is a documented invariant rather than a guess, "
        f"say so explicitly with a line: {SENTINEL} — <reason>. "
        "(False positive? `touch .no-silent-assumptions-off` in cwd.)"
    )
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        sys.stderr.write("no-silent-assumptions gate skipped (%s)\n" % exc)
        sys.exit(0)
