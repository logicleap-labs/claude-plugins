# scope-guard

**The most expensive edits are the ones nobody asked for.**

Claude Code plugin that keeps an agent in its lane. Declare the files a task is
allowed to touch, and a PreToolUse hook blocks any `Edit`/`Write`/`MultiEdit`
outside that set — before it happens. No more "while I'm here" refactors, no
clobbering another agent's files on a shared working tree.

## Install

```bash
claude plugin marketplace add logicleap-labs/claude-plugins
claude plugin install scope-guard
```

Restart Claude Code. Disable: `claude plugin disable scope-guard`

## Declare scope (any one of these)

```bash
# 1. a .scope-guard file in the repo root — one glob per line
printf 'src/checkout/**\nsrc/lib/money.ts\n!src/checkout/legacy/**\n' > .scope-guard

# 2. an env var
export SCOPE_GUARD_PATHS="src/**, !src/legacy/**"
```

```
# 3. an in-band sentinel, on its own line in the reply
SCOPE-GUARD: src/checkout/**, src/lib/money.ts
```

`**` spans directories · `*` stays in one segment · a bare `*.ts` matches that
basename anywhere · `src/` means `src/**` · leading `!` excludes.

**With no scope declared, the hook is a silent no-op** — it only acts once you opt in.

## What's inside

| Piece | Role |
|---|---|
| **Skill `scope-guard`** | Method: declare narrowest scope → work → decide (don't widen silently) |
| **PreToolUse hook** | Blocks edits to files outside the declared scope |
| **`/scope-guard:scope`** | Declare scope on demand: `/scope-guard:scope src/checkout/**` |

## Kill switch

```bash
touch .scope-guard-off   # in project root (or ~/.claude/.scope-guard-off)
# or
export SCOPE_GUARD_GATE=off
```

Fails open on any error — a broken guard never blocks your work.

## Pairs with

- **[`verify-before-done`](../verify-before-done/README.md)** — scope says *which*
  files; verify says *prove it works*. Narrow diff + real evidence = a reviewable change.
- **[`visual-quality`](../visual-quality/README.md)** — when the in-scope files render UI.

## License

MIT © Josh Matthews / LogicLeap Ltd.
