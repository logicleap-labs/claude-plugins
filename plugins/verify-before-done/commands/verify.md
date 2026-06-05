---
description: Run the verify-before-done checklist — pick the right proof command, run it, record evidence, emit VERIFY-BEFORE-DONE: PASS.
---

Load and follow the `verify-before-done` skill for this project.

1. Identify what changed this session (files + behaviour claim).
2. Choose the **smallest** command that falsifies "it's fixed".
3. Run it via Bash; paste command + outcome.
4. If green, end with `VERIFY-BEFORE-DONE: PASS — <command> → <outcome>`.
5. If blocked by environment, state **unverified** and list exact manual steps.

Do not say "done" without evidence.