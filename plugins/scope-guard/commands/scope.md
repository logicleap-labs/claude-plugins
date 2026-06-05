---
description: Declare the files this task is allowed to touch — Scope Guard blocks edits outside that set.
argument-hint: "[globs, e.g. src/checkout/**, src/lib/money.ts]"
---

Load and follow the `scope-guard` skill for this task.

Arguments (optional): `$ARGUMENTS`

1. If globs were given in the arguments, use them. Otherwise infer the
   **narrowest** set of paths that can satisfy the user's request from what
   they asked for — do not include speculative or "might need" files.
2. State the scope back to the user in one line, then emit the declaration on
   its own line so the hook picks it up:

   ```
   SCOPE-GUARD: <glob>, <glob>, !<exclusion>
   ```

3. Proceed with the work. If you later need a file outside scope, STOP, explain
   why, and re-emit a new `SCOPE-GUARD:` line that includes it — never widen
   silently.

If the user wants the scope to persist across the whole session (or the repo is
shared with other agents), write the globs to a `.scope-guard` file in the
project root instead, one per line.
