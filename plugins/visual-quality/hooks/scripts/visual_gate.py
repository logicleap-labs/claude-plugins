#!/usr/bin/env python3
"""
visual-quality :: Stop gate
===========================
Refuses to let a turn END when the turn did UI work but never rendered + reviewed it.

Fires on every Stop. It is a NO-OP unless the current turn-segment edited UI source or
took a screenshot, so it never bothers non-UI work / other agents.

Decision logic (segment = everything since the last real user prompt):
  - no UI edit AND no render        -> PASS  (not visual work)
  - UI edited  AND no render        -> BLOCK "you edited UI but never rendered & looked at it"
  - rendered   AND no review pass   -> BLOCK "you rendered UI but never reviewed it"
  - rendered   AND review pass      -> PASS

A "review pass" is the sentinel line the visual-self-review skill emits when its
Definition of Done is met:   VISUAL-SELF-REVIEW: PASS
(case-insensitive, must appear in assistant text AFTER the render).

Safety rails (all fail-OPEN — this hook must never trap the user or break a turn):
  * any exception -> exit 0 (pass)
  * loop cap: if we've already blocked >=2 times this segment, pass
  * stop_hook_active from a prior non-block path is respected
  * kill switch: env VISUAL_QUALITY_GATE=off, or a file ~/.claude/.visual-quality-off,
    or a file .visual-quality-off in cwd -> pass
"""
import sys, os, json, re

SENTINEL = "VISUAL-SELF-REVIEW: PASS"
BLOCK_TAG = "[visual-quality gate]"   # appears in our own reason text; used to count prior blocks

UI_EXT = (".tsx", ".jsx", ".vue", ".svelte", ".css", ".scss", ".sass", ".less",
          ".html", ".htm", ".swift", ".storyboard", ".xib", ".kt", ".dart",
          ".astro", ".mdx")
# .ts/.js only count if they smell like UI (JSX/className/styled). Handled below.

RENDER_TOOLS = ("preview_screenshot", "preview_snapshot", "preview_start",
                "computer-use__screenshot", "screenshot")


def _passthrough(msg=None):
    if msg:
        sys.stderr.write(msg + "\n")
    sys.exit(0)


def _kill_switch(cwd):
    if os.environ.get("VISUAL_QUALITY_GATE", "").lower() in ("off", "0", "false", "no"):
        return True
    home = os.path.expanduser("~")
    if os.path.exists(os.path.join(home, ".claude", ".visual-quality-off")):
        return True
    if cwd and os.path.exists(os.path.join(cwd, ".visual-quality-off")):
        return True
    return False


def _iter_text(content):
    """Yield text from an assistant/user 'content' field (str or list of blocks)."""
    if isinstance(content, str):
        yield content
    elif isinstance(content, list):
        for b in content:
            if isinstance(b, dict):
                if b.get("type") == "text" and isinstance(b.get("text"), str):
                    yield b["text"]


def _tool_uses(content):
    """Yield (tool_name, tool_input_dict) for tool_use blocks in assistant content."""
    if isinstance(content, list):
        for b in content:
            if isinstance(b, dict) and b.get("type") == "tool_use":
                yield b.get("name", ""), (b.get("input") or {})


def _looks_like_ui_code(path, ext):
    if ext in UI_EXT:
        return True
    return False  # keep .ts/.js out unless extension is clearly UI; avoids false positives on API/server code


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

    # Read the tail of the transcript only (transcripts can be large).
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

    # Find the start of the current segment: the last genuine user prompt
    # (role user with text content that is NOT a tool_result echo).
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

    ui_edited = False
    rendered = False
    review_pass = False
    blocks_so_far = 0

    for e in segment:
        etype = e.get("type")
        msg = e.get("message", e)
        content = msg.get("content") if isinstance(msg, dict) else None

        if etype == "assistant":
            for name, inp in _tool_uses(content):
                low = (name or "").lower()
                if any(k in low for k in RENDER_TOOLS):
                    rendered = True
                if low.endswith("edit") or low.endswith("write") or "multiedit" in low \
                   or low in ("edit", "write", "multiedit"):
                    fp = inp.get("file_path") or inp.get("path") or ""
                    ext = os.path.splitext(fp)[1].lower()
                    if _looks_like_ui_code(fp, ext):
                        ui_edited = True
                if low.endswith("bash") or low == "bash":
                    cmd = (inp.get("command") or "")
                    if "simctl" in cmd and "screenshot" in cmd:
                        rendered = True
                    if "screencapture" in cmd:
                        rendered = True
                if low.endswith("read") or low == "read":
                    fp = (inp.get("file_path") or "").lower()
                    if fp.endswith((".png", ".jpg", ".jpeg", ".webp")):
                        rendered = True  # reading an image back == looking at a render
            for txt in _iter_text(content):
                if SENTINEL.lower() in txt.lower() and (rendered or ui_edited):
                    review_pass = True
                if BLOCK_TAG in txt:
                    blocks_so_far += 1

        # tool_result content can carry our injected block reason on the user side too
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

    # ---- decide --------------------------------------------------------------
    if not ui_edited and not rendered:
        _passthrough()                       # not visual work

    if blocks_so_far >= 2:
        _passthrough()                       # loop cap — already nudged twice, let it go

    if review_pass:
        _passthrough()                       # reviewed & passed

    if rendered and not review_pass:
        reason = (
            f"{BLOCK_TAG} You rendered UI this turn but have not run the visual-self-review. "
            "A screenshot is not a review. Invoke the `visual-self-review` skill and DO it: "
            "(1) transcribe every screenshot element-by-element (read every text string, account "
            "for every region, read every list in full), (2) sweep the 12-class defect taxonomy, "
            "(3) FIX every blocker / obvious-to-user defect and re-screenshot, (4) run the "
            "performance pass if anything interactive changed. When — and only when — the "
            f"Definition of Done is genuinely met, end your message with the line: {SENTINEL} "
            "— <n defects fixed>. "
            "(Kill switch if this is a false positive: `touch .visual-quality-off` in cwd.)"
        )
        print(json.dumps({"decision": "block", "reason": reason}))
        sys.exit(0)

    if ui_edited and not rendered:
        reason = (
            f"{BLOCK_TAG} You edited UI source this turn but never rendered it. A clean compile "
            "is not a render; types passing catches nothing visual. Render the actual screen "
            "(web: preview_screenshot; Xcode/iOS: build+run then `xcrun simctl io booted "
            "screenshot /tmp/vsr.png` and Read it back), then run the `visual-self-review` skill: "
            "transcribe → sweep the taxonomy → fix blockers → re-screenshot. End with "
            f"{SENTINEL} — <n defects fixed> once the Definition of Done is met. "
            "(False positive? `touch .visual-quality-off`.)"
        )
        print(json.dumps({"decision": "block", "reason": reason}))
        sys.exit(0)

    _passthrough()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # never break the user's turn
        sys.stderr.write("visual-quality gate skipped (%s)\n" % exc)
        sys.exit(0)
