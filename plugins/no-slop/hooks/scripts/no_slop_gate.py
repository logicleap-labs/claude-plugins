#!/usr/bin/env python3
"""
no-slop :: Stop gate
====================
Refuses to let a turn END when PROSE the model wrote this turn is full of
AI-tell "slop" phrasing — "delve into", "it's worth noting that", "rich
tapestry", "navigate the complexities", "a testament to", em-dash pile-ups,
and friends.

The PROSE complement to no-stub (which gates code). This gate scans ONLY the
added text of Write/Edit/MultiEdit to prose files — .md/.mdx/.txt/.rst — and
ignores code entirely.

Fires on every Stop. NO-OP unless the current segment edited a prose file AND
the added prose carries >= 2 DISTINCT AI tells.

Decision logic (segment = since last real user prompt):
  - no prose edit                       -> PASS
  - prose edited, < 2 distinct tells    -> PASS
  - prose edited, >= 2 distinct tells   -> BLOCK
  - sentinel present                    -> PASS

Sentinel (override): an assistant line containing
  NO-SLOP: INTENTIONAL — <reason>
bypasses the block (e.g. quoting slop as an example of what NOT to write).

Safety rails (fail-OPEN):
  * any exception -> exit 0
  * loop cap >= 2 prior blocks -> pass
  * kill switch env/file -> pass
  * one stray cliché never blocks (threshold is 2 DISTINCT tells)
  * em-dash signal is lenient: only true em-dashes, only in short paragraphs
"""
import sys, os, json, re

SENTINEL = "NO-SLOP: INTENTIONAL"
BLOCK_TAG = "[no-slop gate]"

# Prose extensions we scan. The INVERSE of no-stub's code set: we only care
# about human-readable writing, never code.
PROSE_EXT = (".md", ".mdx", ".txt", ".rst")

# --- AI tells ---------------------------------------------------------------
# HIGH-PRECISION ONLY. Each entry is near-universally slop. We deliberately
# avoid common-but-fine single words (leverage, robust, utilize, delve as a
# bare word) — only the multi-word clichés below. Keeping the list tight is
# what keeps false positives near zero.
TELL_PATTERNS = [
    (re.compile(r"(?i)\bdelv(e|ing)\s+into\b"), '"delve into"'),
    (re.compile(r"(?i)\bit('?s| is)\s+worth\s+noting\s+that\b"),
     '"it\'s worth noting that"'),
    (re.compile(r"(?i)\bin\s+today'?s\s+fast[- ]paced\b"),
     '"in today\'s fast-paced"'),
    (re.compile(r"(?i)\bin\s+today'?s\s+digital\s+age\b"),
     '"in today\'s digital age"'),
    (re.compile(r"(?i)\bin\s+the\s+modern\s+era\b"), '"in the modern era"'),
    (re.compile(r"(?i)\bnavigat(e|ing)\s+the\s+complexit(y|ies)\b"),
     '"navigate the complexities"'),
    (re.compile(r"(?i)\bnavigating\s+the\s+landscape\b"),
     '"navigating the landscape"'),
    (re.compile(r"(?i)\btapestry\b"), '"tapestry"'),
    (re.compile(r"(?i)\b(a\s+)?testament\s+to\b"), '"testament to"'),
    (re.compile(r"(?i)\bunderscor(es|ing)\s+the\s+importance\b"),
     '"underscores the importance"'),
    (re.compile(r"(?i)\b(a\s+)?game[- ]changer\b"), '"a game-changer"'),
    (re.compile(r"(?i)\bunlock\s+the\s+(full\s+)?potential\b"),
     '"unlock the (full) potential"'),
    (re.compile(r"(?i)\bunleash\s+the\s+power\b"), '"unleash the power"'),
    (re.compile(r"(?i)\bdive\s+deep\s+into\b"), '"dive deep into"'),
    (re.compile(r"(?i)\blet'?s\s+dive\s+in\b"), '"let\'s dive in"'),
    (re.compile(r"(?i)\bin\s+the\s+realm\s+of\b"), '"in the realm of"'),
    (re.compile(r"(?i)\bat\s+the\s+end\s+of\s+the\s+day\b"),
     '"at the end of the day"'),
    (re.compile(r"(?i)\bever[- ]evolving\b"), '"ever-evolving"'),
    (re.compile(r"(?i)\bever[- ]changing\s+landscape\b"),
     '"ever-changing landscape"'),
    (re.compile(r"(?i)\bseamless(ly)?\s+integrat\w*"),
     '"seamlessly integrate"'),
    (re.compile(r"(?i)\bseamless\s+experience\b"), '"seamless experience"'),
    (re.compile(r"(?i)\belevate\s+your\b"), '"elevate your"'),
    (re.compile(r"(?i)\brobust\s+and\s+scalable\b"), '"robust and scalable"'),
    (re.compile(r"(?i)\bembark\s+on\s+(a\s+journey|this)\b"),
     '"embark on a journey"'),
    (re.compile(r"(?i)\bneedless\s+to\s+say\b"), '"needless to say"'),
    (re.compile(r"(?i)\bfirst\s+and\s+foremost\b"), '"first and foremost"'),
    (re.compile(r"(?i)\bit\s+goes\s+without\s+saying\b"),
     '"it goes without saying"'),
    # "in conclusion," only as a paragraph opener (start of a line/block)
    (re.compile(r"(?im)^\s*in\s+conclusion\s*,"), '"in conclusion," opener'),
]

# Transition-word slop: only flag when BOTH "furthermore" AND "moreover" are
# present in the added prose (either alone is fine).
FURTHERMORE = re.compile(r"(?i)\bfurthermore\b")
MOREOVER = re.compile(r"(?i)\bmoreover\b")

# True em-dash only (U+2014). Hyphens and en-dashes are not counted.
EM_DASH = "—"
EM_DENSITY_MIN = 3      # 3+ em-dashes in one paragraph
EM_PARA_MAX_WORDS = 60  # ...but only if the paragraph is reasonably short


def _passthrough(msg=None):
    if msg:
        sys.stderr.write(msg + "\n")
    sys.exit(0)


def _kill_switch(cwd):
    if os.environ.get("NO_SLOP_GATE", "").lower() in ("off", "0", "false", "no"):
        return True
    home = os.path.expanduser("~")
    if os.path.exists(os.path.join(home, ".claude", ".no-slop-off")):
        return True
    if cwd and os.path.exists(os.path.join(cwd, ".no-slop-off")):
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


def _is_prose_path(path):
    ext = os.path.splitext(path)[1].lower()
    return ext in PROSE_EXT


def _added_text(name, inp):
    """Return the chunk of NEW prose an Edit/Write/MultiEdit introduces."""
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


def _em_dash_density(text):
    """True if any reasonably-short paragraph piles up >= 3 true em-dashes."""
    # Paragraphs split on blank lines.
    for para in re.split(r"\n\s*\n", text):
        if para.count(EM_DASH) >= EM_DENSITY_MIN:
            words = len(para.split())
            if 0 < words < EM_PARA_MAX_WORDS:
                return True
    return False


def _scan_for_slop(text):
    """Return a sorted list of distinct AI-tell reasons found in `text`."""
    found = set()
    for pat, label in TELL_PATTERNS:
        if pat.search(text):
            found.add(label)

    if FURTHERMORE.search(text) and MOREOVER.search(text):
        found.add('"furthermore" + "moreover"')

    if _em_dash_density(text):
        found.add("em-dash pile-up (3+ in a short paragraph)")

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

    prose_edited = False
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
                    if _is_prose_path(fp):
                        prose_edited = True
                        added = _added_text(name, inp)
                        if added:
                            for r in _scan_for_slop(added):
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

    # Threshold: need >= 2 DISTINCT tells. One stray cliché never blocks.
    if not prose_edited or len(reasons) < 2:
        _passthrough()

    if sentinel:
        _passthrough()

    if blocks_so_far >= 2:
        _passthrough()

    found = ", ".join(sorted(reasons))
    reason = (
        f"{BLOCK_TAG} The prose you wrote this turn reads like AI slop — distinct "
        f"AI tells found: {found}. Invoke the `no-slop` skill: cut each tell and say "
        "the thing plainly (one idea per sentence, no throat-clearing, no decorative "
        "transitions). Rewrite the offending passages, then end the turn. If the slop "
        "is there on purpose (quoting it as an example of what NOT to write), say so "
        f"explicitly with a line: {SENTINEL} — <reason>. "
        "(False positive? `touch .no-slop-off` in cwd.)"
    )
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        sys.stderr.write("no-slop gate skipped (%s)\n" % exc)
        sys.exit(0)
