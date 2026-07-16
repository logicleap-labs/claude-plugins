# migration-safety

**Destroyed data has no kill switch.**

Claude Code plugin that blocks destructive SQL — `DROP TABLE`/`COLUMN`, `TRUNCATE`, `DELETE`/`UPDATE` without `WHERE`, irreversible `ALTER`s — run via Bash or written into migration files, until a migration plan is declared: target stated, blast radius dry-run, rollback written.

## Install

```bash
claude plugin marketplace add logicleap-labs/claude-plugins
claude plugin install migration-safety
```

Restart Claude Code. Disable: `claude plugin disable migration-safety`

## What it blocks

A Bash command, or a write to a `.sql`/migration-path file, is denied when it carries destructive SQL and no plan exists:

| Shape | Why |
|---|---|
| `DROP TABLE` / `DATABASE` / `SCHEMA` | gone is gone |
| `ALTER TABLE … DROP` | the column's data goes with it |
| `TRUNCATE` | a `DELETE` with no undo and no row count |
| `DELETE FROM …` with no `WHERE` | the classic |
| `UPDATE … SET …` with no `WHERE` | every row, silently |

## Declaring a plan

Either a **`.migration-plan` file** in the project root (delete it when the migration ships):

```
target: staging.sessions — rows older than 90 days (~14,203 per dry-run SELECT)
dry-run: count verified; matches retention policy
rollback: pg_dump to backups/sessions-20260611.sql
```

…or a one-off **sentinel** in the reply: `MIGRATION-SAFETY: ALLOW — <target, dry-run result, rollback>`.

## What it allows (no false positives)

- Any `DELETE`/`UPDATE` **with a `WHERE`** in the same statement
- Additive work: `CREATE`, `ALTER … ADD`, `INSERT`, `SELECT`
- SQL inside `--` comments
- Writes to files that aren't `.sql` and aren't on a migration-ish path — a `DROP TABLE` in a doc or test fixture never blocks

## What's inside

| Piece | Role |
|---|---|
| **Skill `migration-safety`** | Method: state the exact target → dry-run the blast radius → write the rollback → only then execute |
| **PreToolUse hook** | Blocks destructive SQL in Bash commands and migration-file writes until a plan is declared |
| **`/migration-safety:migrate`** | The four-step checklist, on demand |

## Kill switch

```bash
touch .migration-safety-off   # in project root
# or
export MIGRATION_SAFETY_GATE=off
```

Fails open on errors and on any ambiguity. Seeded test DB or scratch SQLite file? Kill switch, or declare the plan anyway — it's three lines.

## Pairs with

- **[`verify-before-done`](../verify-before-done/README.md)** — the dry-run is verification moved *before* the destructive step
- **[`no-silent-assumptions`](../no-silent-assumptions/README.md)** — "assuming this only touches staging" is exactly the guess the target step forces into the open
- **[`scope-guard`](../scope-guard/README.md)** — scope the files; this scopes the data

## License

MIT © Josh Matthews / LogicLeap Ltd.
