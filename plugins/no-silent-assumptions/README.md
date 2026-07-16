# no-silent-assumptions

**A guess you didn't say out loud is a bug report the human files next week.**

Claude Code plugin that blocks turns ending on unsurfaced guesses — an environment assumed rather than inspected, a data shape inferred rather than read, an API behavior never tested, an edge case waved away — unless they're surfaced in a short `Assumptions:` block or explicitly declared with `NO-SILENT-ASSUMPTIONS: INTENTIONAL`.

## Install

```bash
claude plugin marketplace add logicleap-labs/claude-plugins
claude plugin install no-silent-assumptions
```

Restart Claude Code. Disable: `claude plugin disable no-silent-assumptions`

## What's inside

| Piece | Role |
|---|---|
| **Skill `no-silent-assumptions`** | Method: track guesses as you make them → verify the cheap ones → surface the rest in an `Assumptions:` block with blast radius, before "done" |
| **Stop hook** | Blocks end-of-turn when code added this turn carries guess-shaped language and no `Assumptions:` block was surfaced |
| **`/no-silent-assumptions:assumptions`** | On-demand audit of your session's edits for unsurfaced guesses |

Only scans code edited *this segment* (reuses the `verify-before-done` segment/CODE_EXT logic), only flags **added** code, ignores docs. Built to dodge false positives: only multi-word guess-shaped phrases fire — "assuming the/that…", "guessing that…", "not sure if…", "probably works/fine", "might be null", "TODO: verify" — never bare words. A lone "assume" in an assert message, a variable named `assumed_role`, or the word "probably" by itself never blocks. One `Assumptions:` line anywhere in the reply satisfies the gate.

## Kill switch

```bash
touch .no-silent-assumptions-off   # in project root
# or
export NO_SILENT_ASSUMPTIONS_GATE=off
```

Fails open on errors and on any ambiguity; loop-capped at 2 blocks per turn. Flagged phrase is a documented invariant, not a guess? End your message with `NO-SILENT-ASSUMPTIONS: INTENTIONAL — <reason>`.

## Pairs with

- **[`verify-before-done`](../verify-before-done/README.md)** — the strongest move on an assumption is to verify it; this catches the ones you couldn't
- **[`no-stub`](../no-stub/README.md)** — a stub hides missing code; a silent assumption hides missing knowledge
- **[`migration-safety`](../migration-safety/README.md)** — "assuming this only touches staging" is the guess that one refuses to run on

## License

MIT © Josh Matthews / LogicLeap Ltd.
