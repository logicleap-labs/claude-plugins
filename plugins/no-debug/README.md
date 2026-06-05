# no-debug

**A `console.log("here")` is how you debugged it, not how it ships.**

Claude Code plugin that blocks turns ending with leftover debug noise — `console.log`/`debugger`, `pdb.set_trace()`/`breakpoint()`, `binding.pry`/`byebug`, `dd()`/`var_dump()`, `dbg!()`, debug-ish prints — unless you strip it, promote it to a real logger, or explicitly declare an intentional print with `NO-DEBUG: INTENTIONAL`.

## Install

```bash
claude plugin marketplace add logicleap-labs/claude-plugins
claude plugin install no-debug
```

Restart Claude Code. Disable: `claude plugin disable no-debug`

## What's inside

| Piece | Role |
|---|---|
| **Skill `no-debug`** | Method: sweep the prints you added → delete the one-offs, promote real logs to a logger → declare intentional CLI prints out loud |
| **Stop hook** | Blocks end-of-turn when code edited this turn still contains high-signal debug markers |
| **`/no-debug:no-debug`** | On-demand scan-and-strip sweep of your own session's edits |

Only scans code edited *this segment* (reuses the `verify-before-done` segment/CODE_EXT logic), only flags markers in **added** code, ignores docs. Built to dodge false positives: `console.error`/`console.warn` and real loggers (`logger.info`, `winston`, `pino`, `slog`, `logging.getLogger`) are never flagged, commented-out lines are skipped, and an ambiguous `print` / `fmt.Println` / `System.out.println` only flags when the line also carries debug-ish content (`DEBUG`, `here`, `===`, an emoji) — a bare CLI `print("Enter name:")` passes.

## Kill switch

```bash
touch .no-debug-off   # in project root
# or
export NO_DEBUG_GATE=off
```

Fails open on errors and on any ambiguity; loop-capped at 2 blocks per turn. Intentional print? End your message with `NO-DEBUG: INTENTIONAL — <reason>`.

## Pairs with

- **[`no-stub`](../no-stub/README.md)** — the same gate for half-written code; debug-free *and* stub-free is the bar
- **[`secret-guard`](../secret-guard/README.md)** — a `console.log(token)` is also how secrets leak
- **[`verify-before-done`](../verify-before-done/README.md)** — once the noise is gone, prove the real code still runs

## License

MIT © Josh Matthews / LogicLeap Ltd.
