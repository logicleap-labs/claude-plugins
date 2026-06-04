---
description: Automated visual QC sweep — capture the UI across states/viewports/themes, scan for console+network errors, then run an INDEPENDENT adversarial review via the visual-reviewer subagent and consolidate.
argument-hint: "[url | route | screen | 'current change'] (optional)"
---

Automated quality-control pass for the UI below. This is the heavier, automated cousin of `/visual-quality:visual-review`: it captures broadly, checks programmatically, and gets a **second pair of eyes** that didn't write the code.

Target: $ARGUMENTS  (default: the screen you changed most recently)

## 1. Capture the matrix (automated)
Render and screenshot the target across the full matrix — don't stop at the happy path:
- **States:** default, empty, loading, error, and the long-content / many-rows case.
- **Viewports:** narrowest supported width, a mid width, and full width (`preview_resize`).
- **Themes:** light AND dark.
- Xcode/iOS: capture the equivalent via the simulator (`xcrun simctl io booted screenshot`), plus Dynamic Type XXL if text-heavy.
Save each capture to a stable path (e.g. `/tmp/vqc-<state>-<viewport>-<theme>.png`) and note the paths.

## 2. Programmatic checks (automated)
- Web: `preview_console_logs` (errors/warnings) and `preview_network` (failed / slow / **duplicated** requests — repeated identical calls usually mean both a data bug and a perf bug). Exercise the primary interaction (`preview_click`, scroll) and confirm smoothness.
- Record every error/warning verbatim. Any console error is a finding.

## 3. Independent adversarial review (second pair of eyes)
Dispatch the **visual-reviewer** subagent (Agent tool, `subagent_type: "visual-reviewer"`) and pass it the saved screenshot paths + the original request. It re-derives defects from scratch using the visual-self-review taxonomy, with no knowledge of your intent — so it isn't anchored by "I meant it to look like that." Wait for its structured defect report.

## 4. Consolidate + fix
Merge your findings with the subagent's. De-duplicate. For every **blocker / obvious-to-user** defect: fix it, then re-capture that state and confirm it's resolved.

## 5. Report
Produce: the capture matrix (paths), the programmatic-check results, the consolidated defect table (found → fixed → re-verified), and the perf summary. End with `VISUAL-SELF-REVIEW: PASS — <n defects fixed>` only if every blocker is resolved and re-screenshotted; else enumerate what remains.
