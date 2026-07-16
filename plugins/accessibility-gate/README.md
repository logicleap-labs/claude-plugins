# accessibility-gate

**A screen that looks right can still be unusable.**

Claude Code plugin that stops UI work being called done until the agent has
recorded a real accessibility pass: keyboard flow, visible focus, accessible
names, contrast, reduced motion, and error/loading states.

## Install

```bash
claude plugin marketplace add logicleap-labs/claude-plugins
claude plugin install accessibility-gate
```

Restart Claude Code so the Stop hook loads. Disable it with:

```bash
claude plugin disable accessibility-gate
```

## How it works

- The **Stop hook** wakes only after UI source changes (`.tsx`, `.jsx`, `.vue`,
  `.svelte`, `.css`, `.html`, `.swift`, `.xib`, and similar files).
- It blocks a turn without an `ACCESSIBILITY-GATE: PASS` evidence line.
- The **skill** tells the agent what to exercise instead of accepting a vague
  "looks accessible" claim.
- `/a11y` runs the checklist on demand.

Example completion line:

```text
ACCESSIBILITY-GATE: PASS — keyboard flow + axe scan, 0 blockers
```

The hook is silent on non-UI work, fails open on errors, caps its own nudges,
and can be disabled with `touch .accessibility-gate-off` in the project root.

## Pairs with

- [`visual-quality`](../visual-quality/README.md) — inspect the pixels and the semantics.
- [`verify-before-done`](../verify-before-done/README.md) — prove the behavior, then prove it is usable.

MIT © Josh Matthews / LogicLeap Ltd.
