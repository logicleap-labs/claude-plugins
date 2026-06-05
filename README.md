<h1 align="center">LogicLeap Labs · Claude Code plugins</h1>

<p align="center">
  Open tooling for shipping AI output that's actually good.<br>
  By <a href="https://x.com/logicleaplabs">Josh Matthews</a> · <a href="https://logic-leap.co.uk">LogicLeap Ltd</a>
</p>

---

Most AI coding failures aren't capability failures — they're **looking** failures. The model can spot the blank sidebar item, the dead empty band, the same row rendered seven times… it just doesn't *check*. These plugins add the forcing functions that make it check.

## Install

```bash
# add this marketplace once
claude plugin marketplace add logicleap-labs/claude-plugins

# then install any plugin
claude plugin install visual-quality
```

Restart Claude Code so hooks load. Disable any time with `claude plugin disable <name>`.

## Plugins

### `visual-quality`
A hard quality gate for anything with pixels. Built because Claude kept doing `compile → screenshot → "looks good" → done` and shipping UI with defects a human catches in two seconds.

- **Skill `visual-self-review`** — the method. One rule does the work: *you don't get to judge a screen until you've transcribed it.* Read every element, account for every region, read every list in full → then sweep a 12-class defect taxonomy → performance pass → fix & re-screenshot → hard Definition of Done. Works in Xcode/SwiftUI, iOS/macOS, web, Electron, generated mockups.
- **Stop hook** — refuses to let a turn end if UI was edited/screenshotted but never reviewed. No-op on non-UI turns, fails open, loop-capped, kill switch (`touch .visual-quality-off`).
- **`/visual-quality:visual-review`** and **`/visual-quality:visual-qc`** — run the review / a full automated QC sweep on demand.
- **`visual-reviewer` subagent** — a second pair of eyes that didn't write the code.

→ [full docs](plugins/visual-quality/README.md)

### `verify-before-done`
Forces evidence before "done" on any code change. Built because "clean compile" and "updated the handler" kept shipping without a test, build, or smoke run.

- **Skill `verify-before-done`** — pick the smallest proof → run it → record output → sentinel line.
- **Stop hook** — blocks end-of-turn when code was edited but nothing verified. Fails open, kill switch (`touch .verify-before-done-off`).
- **`/verify-before-done:verify`** — on-demand verification checklist.

→ [full docs](plugins/verify-before-done/README.md)

### `scope-guard`
Keeps an agent in its lane. Built because the most expensive edits are the ones nobody asked for — the "while I'm here" refactor, the reformatted file two directories away, one agent clobbering another's work on a shared tree.

- **Skill `scope-guard`** — declare the narrowest set of files a task may touch, then decide deliberately (never widen silently) when you hit the edge.
- **PreToolUse hook** — blocks any `Edit`/`Write` outside the declared scope (`.scope-guard` file, `SCOPE_GUARD_PATHS` env, or a `SCOPE-GUARD:` sentinel). Silent no-op until you opt in, fails open, kill switch (`touch .scope-guard-off`).
- **`/scope-guard:scope`** — declare scope on demand.

→ [full docs](plugins/scope-guard/README.md)

### `no-stub`
Refuses to let a turn end with half-written code. Built because "scaffold the function → leave a `# TODO: implement` → done" quietly moves the work back to the human, who finds it at runtime instead of in the reply.

- **Skill `no-stub`** — catch the placeholder reflex, finish the path (the answer is usually already in the repo), and declare genuinely intentional stubs *out loud* instead of leaving leftovers.
- **Stop hook** — blocks end-of-turn when code edited this turn still contains stub markers: `TODO`/`FIXME`/`XXX`/`HACK`, `NotImplementedError`/`todo!()`/`throw new Error("not implemented")`, empty `...` bodies, "your code here". Only scans added code, ignores docs, dodges JS spreads and type-hint ellipses, fails open, kill switch (`touch .no-stub-off`). Override a true intentional stub with `NO-STUB: INTENTIONAL — <reason>`.
- **`/no-stub:no-stub`** — on-demand scan-and-finish sweep of your session's edits.

→ [full docs](plugins/no-stub/README.md)

## What this is

The start of a longer-term project: open-sourcing the tools and techniques behind how I actually use AI to build production software. More plugins, comparisons, and write-ups coming — follow along on [X](https://x.com/logicleaplabs) (and a YouTube channel soon).

## License

MIT © Josh Matthews / LogicLeap Ltd. See [LICENSE](LICENSE).
