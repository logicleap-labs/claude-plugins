---
description: Run the migration-safety checklist for destructive DB/schema work — state the target, dry-run the blast radius, write the rollback, then execute.
argument-hint: "[what you're migrating, e.g. drop legacy_users column from accounts]"
---

Load and follow the `migration-safety` skill for this migration.

Arguments (optional): `$ARGUMENTS`

Work the checklist in order — do not run any destructive statement until all four are done:

1. **Target.** Name the exact database (dev/staging/**prod**?), table(s), and rows affected. If the user's request is vague ("clean up the old data"), pin it down with them first.
2. **Dry-run.** Prove the blast radius: a `SELECT count(*)` with the same predicate as the DELETE/UPDATE, a check for non-null data before a DROP COLUMN, a run against a dev copy for a schema migration. Show the result. If it surprises you, stop and revise.
3. **Rollback.** State how this gets undone before it happens: backup/snapshot taken, down-migration written, or an explicit "irreversible — confirm?" to the user. Never discover irreversibility afterwards.
4. **Declare, then execute.** Write the plan to `.migration-plan` in the project root (target, dry-run result, rollback) — or emit `MIGRATION-SAFETY: ALLOW — <target, dry-run, rollback>` for a one-off — then run the migration. Delete `.migration-plan` once it ships.

Report the target, the dry-run numbers, the rollback path, and the outcome. Don't say "done" on a migration whose blast radius was never measured.
