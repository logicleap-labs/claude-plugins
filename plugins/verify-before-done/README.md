# verify-before-done

**A clean compile is not verification.**

Claude Code plugin that blocks turns ending after code edits unless something was actually **run** to exercise the change — or you explicitly record proof with `VERIFY-BEFORE-DONE: PASS`.

## Install

```bash
claude plugin marketplace add logicleap-labs/claude-plugins
claude plugin install verify-before-done
```

Restart Claude Code. Disable: `claude plugin disable verify-before-done`

## What's inside

| Piece | Role |
|---|---|
| **Skill `verify-before-done`** | Method: pick proof → run → record evidence → sentinel line |
| **Stop hook** | Blocks end-of-turn when code edited but no test/build/run/sentinel |
| **`/verify-before-done:verify`** | On-demand checklist |

## Kill switch

```bash
touch .verify-before-done-off   # in project root
# or
export VERIFY_BEFORE_DONE_GATE=off
```

Fails open on errors; loop-capped at 2 blocks per turn.

## Pairs with

- **[`visual-quality`](../visual-quality/README.md)** — pixels after logic verifies
- Sequel narrative: *we forced looking at screens; now we force running the code*

## License

MIT © Josh Matthews / LogicLeap Ltd.