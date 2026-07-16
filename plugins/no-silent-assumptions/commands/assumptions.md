---
description: Audit the work you did this session for unsurfaced guesses — env, data shape, API behavior, edge cases — and surface them in an "Assumptions:" block.
---

Load and follow the `no-silent-assumptions` skill, then audit your own work this session.

1. List the code files you created or edited this session.
2. For each, re-read what you wrote and ask of every non-trivial decision: *did I verify this, or did I guess?* Look for the four material categories: environment (tools/versions/services assumed present), data shape (schemas/fields/nullability inferred, not read), API behavior (returns/errors/ordering untested), and edge cases (inputs you decided can't happen).
3. The tells are in your own comments and replies: "assuming the…", "probably fine", "should work", "not sure if", "might be null", "TODO: verify".
4. For each guess found, **verify the cheap ones now** — read the schema, hit the endpoint, check the env. A verified fact beats a surfaced guess.
5. Surface everything that remains in one block — one line per assumption, each with what breaks if it's wrong:

   ```
   Assumptions:
   - <what you assumed> — <blast radius if wrong>
   ```

6. If a flagged phrase is a documented invariant rather than a guess, record one line: `NO-SILENT-ASSUMPTIONS: INTENTIONAL — <reason>`.

Don't say "done" while a guess that could break production lives only in a comment.
