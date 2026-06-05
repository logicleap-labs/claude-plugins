# no-swallow

**A caught error you do nothing with is a bug that hides itself.**

Claude Code plugin that blocks turns ending with a silently-swallowed error — `except: pass`, an empty `catch (e) {}`, `.catch(() => {})`, an empty `if err != nil {}` — unless you handle it, log it, re-raise it, return a real fallback, or explicitly declare an intentional swallow with `NO-SWALLOW: INTENTIONAL`.

## Install

```bash
claude plugin marketplace add logicleap-labs/claude-plugins
claude plugin install no-swallow
```

Restart Claude Code. Disable: `claude plugin disable no-swallow`

## What's inside

| Piece | Role |
|---|---|
| **Skill `no-swallow`** | Method: find every handler you added → pick one of four real outcomes (handle / log / re-raise / return a fallback) → declare genuinely best-effort swallows out loud |
| **Stop hook** | Blocks end-of-turn when code edited this turn contains a caught error whose body does nothing |
| **`/no-swallow:no-swallow`** | On-demand scan-and-fix sweep of your own session's edits |

Only scans code edited *this segment* (reuses the `verify-before-done` segment/CODE_EXT logic), only flags swallows in **added** code, ignores docs. Detects: Python `except: pass` / `except X: pass` / multi-line `except` bodies that are only `pass`/`...`/`continue`/`break`; JS/TS empty `catch (e) {}` / `catch {}` and trivial `.catch(() => {})` / `.catch(() => null)` / `.catch(function(){})`; empty `catch (...) {}` in Java/Kotlin/C#/C++/Swift; and the clearly-empty Go `if err != nil {}`.

Built to dodge false positives: a handler that **logs** (`logger.error`, `console.error`, `print`), **re-raises** (`raise`/`throw`/`rethrow`), **returns** a value, **assigns / sets error state** (`setError(e)`), or **calls a real handler** (`.catch(handleError)`) is never flagged. Swift `try?` is a language idiom — never flagged. `except ImportError:` with a fallback import passes. A comment-only body still counts as a swallow (a comment isn't handling) — but the sentinel covers deliberate cases.

This one is **heuristic** — error swallowing is harder to detect than a stray `console.log` — so it is tuned to **fail open**: when a body is ambiguous or the braces don't balance cleanly, it passes rather than risk a false block.

## Kill switch

```bash
touch .no-swallow-off   # in project root
# or
export NO_SWALLOW_GATE=off
```

Fails open on errors and on any ambiguity; loop-capped at 2 blocks per turn. Intentional swallow? End your message with `NO-SWALLOW: INTENTIONAL — <reason>`.

## Pairs with

- **[`no-stub`](../no-stub/README.md)** — an empty handler is a stub of error handling; same bar for the failure path
- **[`no-debug`](../no-debug/README.md)** — strip the debug print, but keep and promote the real error log
- **[`verify-before-done`](../verify-before-done/README.md)** — once errors surface instead of hiding, prove the real path holds

## License

MIT © Josh Matthews / LogicLeap Ltd.
