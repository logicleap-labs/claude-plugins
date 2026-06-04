# visual-quality

A hard quality gate for anything with pixels. Built because Claude keeps doing
`compile → screenshot → "looks good" → done` and shipping UI with defects a human spots
in two seconds (blank sidebar items, dead empty bands, the same row rendered 7×, lag it
never measured). Claude *can* see these — it just pattern-matches instead of looking. This
plugin replaces the glance with a forced, structured, written review, and won't let a turn
end without one.

## What's in it

| Component | What it does |
|---|---|
| **Skill** `visual-self-review` | The method. Core rule: *you don't get to judge a screen until you've transcribed it.* Transcribe every element/region/list → sweep a 12-class defect taxonomy → performance pass → fix & re-screenshot → hard Definition of Done. Works for Xcode/SwiftUI, iOS/macOS, web, Electron, generated mockups. Auto-triggers on UI work and "done / looks good / screenshot / ship it". |
| **Stop hook** `visual_gate.py` | Enforcement. On every Stop it inspects the current turn: if UI source was edited but never rendered, or a screenshot was taken but never reviewed, it **blocks the turn from ending** with instructions to run the review. Passes when the review sentinel `VISUAL-SELF-REVIEW: PASS` appears. No-op for non-UI turns; fails open on any error; loop-capped at 2 nudges; kill switch below. |
| **PostToolUse hook** `screenshot_nudge.py` | The instant a screenshot is taken, injects a one-line "transcribe before you judge" reminder — right when the lazy reflex fires. |
| **Command** `/visual-quality:visual-review` | Run the full review now on the current change. |
| **Command** `/visual-quality:visual-qc` | Automated QC: capture across states/viewports/themes, scan console+network, dispatch the independent reviewer, consolidate & fix. |
| **Subagent** `visual-reviewer` | A second pair of eyes that didn't write the code — re-derives defects from screenshots with no anchoring on intent. |

## Kill switch (when the gate is a false positive)
Any one of:
- `touch .visual-quality-off` in the project dir (per-project), or
- `touch ~/.claude/.visual-quality-off` (global), or
- run with env `VISUAL_QUALITY_GATE=off`.

## Install
Registered in the `local` marketplace. `claude plugin install visual-quality@local`,
then restart. `claude plugin disable visual-quality` to turn the whole thing off.

## The sentinel
A passing review ends with `VISUAL-SELF-REVIEW: PASS — <n defects fixed>`. That line is both
how the Stop hook knows the review happened and a grep-able audit trail of what got caught.
