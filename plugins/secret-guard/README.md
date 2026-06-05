# secret-guard

**A secret in source is a secret that's already leaked.**

Claude Code plugin that stops a live credential from ever landing in a tracked
file. A PreToolUse hook scans the new content of every `Edit`/`Write`/`MultiEdit`
and blocks the write — before it happens — when it carries a real-looking secret
into a non-env source file. `.env` files, placeholders, and env reads pass
straight through.

## Install

```bash
claude plugin marketplace add logicleap-labs/claude-plugins
claude plugin install secret-guard
```

Restart Claude Code. Disable: `claude plugin disable secret-guard`

## What it blocks

A write is denied when the added text contains a live-looking credential:

| Shape | Example prefix |
|---|---|
| AWS access key id | `AKIA…` |
| GitHub token | `ghp_…` / `gho_…` / `ghu_…` |
| OpenAI / Anthropic key | `sk-…` / `sk-ant-…` |
| Stripe live key | `sk_live_…` / `pk_live_…` / `rk_live_…` |
| Google API key | `AIza…` |
| Slack token | `xoxb-…` / `xoxp-…` |
| Private key block | `-----BEGIN … PRIVATE KEY-----` |
| Hardcoded secret literal | `apiKey = "…20+ chars…"` |

## What it allows (no false positives)

- **`.env` / `.env.*` / `*.env`** and **`*.example` / `*.sample` / `*.template`**
  files — the correct home for secrets and their placeholders.
- **Env reads** — `process.env.X`, `os.environ["X"]`, `getenv(...)`.
- **Placeholders** — `your-key-here`, `<TOKEN>`, `${VAR}`, `xxxxx`, `changeme`,
  `REDACTED`, `...`, all-same-char values.

## What's inside

| Piece | Role |
|---|---|
| **Skill `secret-guard`** | Method: secrets in `.env`, read at runtime, placeholder in `.env.example`, rotate if leaked |
| **PreToolUse hook** | Scans new content and blocks writes that carry a live secret into source |
| **`/secret-guard:secret-guard`** | Scan this session's edits for secrets on demand |

## Kill switch

```bash
touch .secret-guard-off   # in project root (or ~/.claude/.secret-guard-off)
# or
export SECRET_GUARD_GATE=off
```

Override one deliberate block (e.g. a fake-but-shaped test fixture) with a line:

```
SECRET-GUARD: ALLOW — <reason>
```

Fails open on any error — a broken guard never blocks your work.

## Pairs with

- **[`scope-guard`](../scope-guard/README.md)** — scope says *which* files;
  secret-guard says *what must never be in them*.
- **[`verify-before-done`](../verify-before-done/README.md)** — once the key is
  in `.env` and read at runtime, prove the integration actually connects.

## License

MIT © Josh Matthews / LogicLeap Ltd.
