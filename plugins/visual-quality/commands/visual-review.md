---
description: Run a full visual-self-review on the current UI work NOW — render the real screen, transcribe it, sweep the defect taxonomy, fix blockers, re-screenshot.
argument-hint: "[url | route | file | simulator | 'current change'] (optional — defaults to the change you just made)"
---

Invoke the **visual-self-review** skill and execute it end-to-end against the target below. Do not summarise the method — actually perform it.

Target: $ARGUMENTS
(If empty, review the UI you changed most recently in this session.)

Run every step, in order, and SHOW the work:

1. **Render the real thing.** Capture the actual current pixels — never review the source or your memory of intent.
   - Web/React/Next: `preview_start` if needed → `preview_screenshot` + `preview_snapshot`. Capture each state you touched and re-shoot at a narrow width and in dark mode (`preview_resize`).
   - Xcode/iOS/macOS: build + run, then `xcrun simctl io booted screenshot /tmp/vsr.png` and **Read the PNG back** so you actually see it.
   - Then **Read every screenshot** into context. A compile is not a render.

2. **Transcribe before you judge** (the core mechanic — write it out, do not skip):
   - Read every visible text string, top→bottom, left→right. Flag any interactive element with **no label**.
   - Account for **every region** of the frame. Flag dead/empty space with no purpose.
   - Read every list/repeated block **in full**. Flag duplicate / placeholder / garbage data.

3. **Sweep the 12-class defect taxonomy** from the skill (missing content, dead space, duplicate data, misalignment, inconsistent spacing, typography, truncation/overflow, contrast, broken states, overlap/z-index, alignment-to-request, performance). For each defect: location + what's wrong + severity (blocker / obvious-to-user / polish).

4. **Performance pass** if anything interactive changed: console + network errors, re-render storms, jank. Reported lag is a blocker, not a footnote.

5. **Fix every blocker and obvious-to-user defect, then re-render and re-review the new screenshot.** Loop until clean.

6. Check the result **against the original request** — nothing asked-for missing.

Output a tight report: the screenshots, the transcription, the defect table (with what you fixed), and the perf result. End with the line `VISUAL-SELF-REVIEW: PASS — <n defects fixed>` **only** if the skill's Definition of Done is genuinely met; otherwise list what still blocks it.
