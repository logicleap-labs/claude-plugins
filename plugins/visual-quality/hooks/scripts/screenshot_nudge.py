#!/usr/bin/env python3
"""
visual-quality :: screenshot nudge (PostToolUse)
================================================
The instant a screenshot is taken, inject a one-line reminder to TRANSCRIBE before
judging — the moment the 'looks good → done' reflex normally fires. Non-blocking;
fails open; stays silent unless the tool was actually a render/screenshot.
"""
import sys, os, json

NUDGE = (
    "[visual-quality] Screenshot captured. Do NOT judge it holistically yet — that reflex "
    "ships broken UI. First TRANSCRIBE: read every visible text string top-to-bottom (flag any "
    "interactive element with no label), account for every region (flag dead/empty space), read "
    "every list in full (flag duplicate/placeholder/garbage data). THEN sweep for defects. "
    "See the visual-self-review skill. End with `VISUAL-SELF-REVIEW: PASS` only when the "
    "Definition of Done is genuinely met."
)


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        sys.exit(0)

    name = (payload.get("tool_name") or "").lower()
    inp = payload.get("tool_input") or {}

    is_render = "screenshot" in name or "preview_snapshot" in name
    if (name.endswith("bash") or name == "bash"):
        cmd = (inp.get("command") or "")
        if ("simctl" in cmd and "screenshot" in cmd) or "screencapture" in cmd:
            is_render = True

    if not is_render:
        sys.exit(0)

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": NUDGE
        }
    }))
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)
