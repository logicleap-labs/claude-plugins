---
description: Scan the code you changed this session for silently-swallowed errors — `except: pass`, empty `catch (e) {}`, `.catch(() => {})`, empty `if err != nil {}` — and handle, log, re-raise, or return a real fallback for each.
---

Load and follow the `no-swallow` skill, then sweep your own work this session.

1. List the code files you created or edited this session.
2. For each, scan for swallowed errors: Python `except: pass` / `except X: pass` / multi-line `except` whose body is only `pass`/`...`/`continue`/`break`; JS/TS empty `catch (e) {}` / `catch {}` and `.catch(() => {})` / `.catch(() => null)` / `.catch(function(){})`; empty `catch (...) {}` in Java/Kotlin/C#/C++/Swift; empty `if err != nil {}` in Go.
3. Leave the legitimate stuff alone: any handler that logs (`logger.error`, `console.error`), re-raises (`raise`, `throw`), returns a value, sets an error state (`setError(e)`), calls a real handler (`.catch(handleError)`), does a fallback import (`except ImportError: <fallback>`), or uses Swift `try?`.
4. For each genuine swallow, **pick one**: handle it (real recovery), log it (project logger, right level), re-raise it (`raise`/`throw`), or return a sensible fallback — and usually log why.
5. If a swallow is genuinely intentional (best-effort optional cleanup), keep it and record one line: `NO-SWALLOW: INTENTIONAL — <reason>`.
6. Report what you fixed (and how — handled / logged / re-raised / fallback) and anything you deliberately kept as an intentional swallow.

Don't say "done" while an `except: pass` or an empty `catch (e) {}` is still in the diff.
