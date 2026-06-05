---
description: Scan the code you changed this session for leftover debug noise — console.log/debugger, pdb.set_trace/breakpoint, binding.pry, dd()/var_dump, dbg!(), debug-ish prints — and strip or promote each one.
---

Load and follow the `no-debug` skill, then sweep your own work this session.

1. List the code files you created or edited this session.
2. For each, scan for debug noise: `console.log`/`console.debug`/`console.trace`/`console.dir`/`debugger`, `pdb.set_trace()`/`breakpoint()`/`import pdb`, `binding.pry`/`binding.irb`/`byebug`, `var_dump()`/`print_r()`/`dd()`/`dump()`/`error_log()`, `dbg!()`, and debug-ish `print(...)` / `fmt.Println(...)` / `System.out.println(...)` lines (ones carrying `DEBUG`/`here`/`===`/an emoji).
3. Leave the legitimate stuff alone: `console.error`/`console.warn`, real loggers (`logger.info`, `log.warn`, `logging.getLogger`, winston/pino/slog), commented-out lines, and genuine CLI prints.
4. For each hit, **decide**: delete it (it was a one-off to watch a value), or promote it to a real log line at the right level if you actually want it in production.
5. If a print is genuinely intentional (a CLI tool or script that prints by design), keep it and record one line: `NO-DEBUG: INTENTIONAL — <reason>`.
6. Report what you stripped, what you promoted to a logger, and anything you deliberately kept as an intentional print.

Don't say "done" while a `console.log("here")` or a `pdb.set_trace()` is still in the diff.
