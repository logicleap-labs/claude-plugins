#!/usr/bin/env python3
"""accessibility-gate :: Stop hook.

Blocks a turn that edited UI source until the agent has explicitly completed an
accessibility pass. The hook is deliberately conservative and fails open: it
never blocks non-UI work, cannot read a transcript, or hits the loop cap.
"""
import json
import os
import sys

SENTINEL = "ACCESSIBILITY-GATE: PASS"
BLOCK_TAG = "[accessibility-gate]"
UI_EXTENSIONS = {
    ".astro", ".css", ".dart", ".html", ".htm", ".jsx", ".less", ".mdx",
    ".sass", ".scss", ".storyboard", ".svelte", ".swift", ".tsx", ".vue",
    ".xib",
}
AUDIT_WORDS = (
    "accessib", "a11y", "axe", "lighthouse", "pa11y", "voiceover",
    "keyboard", "focus order", "reduced motion",
)


def _pass():
    raise SystemExit(0)


def _kill_switch(cwd):
    if os.environ.get("ACCESSIBILITY_GATE", "").lower() in {"off", "0", "false", "no"}:
        return True
    home = os.path.expanduser("~")
    return any(
        os.path.exists(path)
        for path in (
            os.path.join(home, ".claude", ".accessibility-gate-off"),
            os.path.join(cwd, ".accessibility-gate-off"),
        )
    )


def _texts(content):
    if isinstance(content, str):
        yield content
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str):
                    yield text


def _tool_uses(content):
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                yield block.get("name", ""), block.get("input") or {}


def _ui_path(path):
    return os.path.splitext(path or "")[1].lower() in UI_EXTENSIONS


def _has_audit_evidence(name, tool_input):
    haystack = " ".join((name or "", str(tool_input))).lower()
    return any(word in haystack for word in AUDIT_WORDS)


def _load_entries(path):
    if not path or not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            return [json.loads(line) for line in handle if line.strip()]
    except Exception:
        return []


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        _pass()

    cwd = payload.get("cwd") or os.getcwd()
    if _kill_switch(cwd):
        _pass()

    entries = _load_entries(payload.get("transcript_path"))[-800:]
    segment_start = 0
    for index in range(len(entries) - 1, -1, -1):
        entry = entries[index]
        if entry.get("type") != "user":
            continue
        message = entry.get("message", entry)
        content = message.get("content") if isinstance(message, dict) else None
        if any(text.strip() for text in _texts(content)) and not (
            isinstance(content, list)
            and any(isinstance(block, dict) and block.get("type") == "tool_result" for block in content)
        ):
            segment_start = index
            break

    ui_edited = False
    audit_evidence = False
    passed = False
    blocks = 0
    for entry in entries[segment_start:]:
        message = entry.get("message", entry)
        content = message.get("content") if isinstance(message, dict) else None
        if entry.get("type") == "assistant":
            for name, tool_input in _tool_uses(content):
                low_name = (name or "").lower()
                if low_name.endswith(("edit", "write")) or "multiedit" in low_name or "notebookedit" in low_name:
                    path = tool_input.get("file_path") or tool_input.get("path") or tool_input.get("notebook_path")
                    ui_edited = ui_edited or _ui_path(path)
                audit_evidence = audit_evidence or _has_audit_evidence(name, tool_input)
            for text in _texts(content):
                upper = text.upper()
                if SENTINEL in upper:
                    passed = True
                blocks += text.count(BLOCK_TAG)
        elif entry.get("type") == "user" and isinstance(content, list):
            for block in content:
                block_content = block.get("content") if isinstance(block, dict) else None
                if isinstance(block_content, str):
                    blocks += block_content.count(BLOCK_TAG)

    if not ui_edited or passed or blocks >= 2:
        _pass()

    evidence_hint = (
        " Include the command or manual checks you actually ran in the sentinel."
        if not audit_evidence else ""
    )
    reason = (
        f"{BLOCK_TAG} UI source changed this turn but no accessibility pass is recorded. "
        "Run the smallest real check for this surface: keyboard-only tab order and focus "
        "visibility, accessible names/labels, contrast, and reduced-motion behavior; use "
        "axe/pa11y/Lighthouse or a UI test where available. Fix the failures, then end "
        f"with `{SENTINEL} — <checks run and result>`." + evidence_hint +
        " (False positive? touch .accessibility-gate-off.)"
    )
    print(json.dumps({"decision": "block", "reason": reason}))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        sys.stderr.write("accessibility-gate skipped (%s)\n" % exc)
        sys.exit(0)
