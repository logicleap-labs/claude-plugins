# no-stub

**A scaffold is not a feature.**

Claude Code plugin that blocks turns ending after you've left half-written code — `TODO`/`FIXME`, `NotImplementedError`, empty `...` bodies, "your code here" — unless the code is real or you explicitly declare an intentional stub with `NO-STUB: INTENTIONAL`.

## Install

```bash
claude plugin marketplace add logicleap-labs/claude-plugins
claude plugin install no-stub
```

Restart Claude Code. Disable: `claude plugin disable no-stub`

## What's inside

| Piece | Role |
|---|---|
| **Skill `no-stub`** | Method: catch the placeholder reflex → finish the path → declare intentional stubs out loud |
| **Stop hook** | Blocks end-of-turn when code edited this turn still contains stub/placeholder markers |
| **`/no-stub:no-stub`** | On-demand scan-and-finish sweep of your own session's edits |

Only scans code edited *this segment* (reuses the `verify-before-done` segment/CODE_EXT logic), only flags markers in **added** code, ignores docs. Built to dodge false positives: JS spreads (`{...obj}`), type-hint ellipses (`Tuple[int, ...]`), and any `...` that isn't the sole statement of a function body.

## Kill switch

```bash
touch .no-stub-off   # in project root
# or
export NO_STUB_GATE=off
```

Fails open on errors and on any ambiguity; loop-capped at 2 blocks per turn. Intentional stub? End your message with `NO-STUB: INTENTIONAL — <reason>`.

## Pairs with

- **[`scope-guard`](../scope-guard/README.md)** — finish *the* job, not five other files
- **[`verify-before-done`](../verify-before-done/README.md)** — once the code is real, prove it runs

## License

MIT © Josh Matthews / LogicLeap Ltd.
