---
description: Scan the files you changed this session for live secrets — AWS/GitHub/OpenAI/Stripe/Slack tokens, Google keys, private keys, hardcoded api_key literals — and move each one out of source.
---

Load and follow the `secret-guard` skill, then sweep your own work this session.

1. List the files you created or edited this session.
2. For each, scan the content for live-looking credentials: `AKIA…` (AWS),
   `ghp_…`/`gho_…` (GitHub), `sk-…` / `sk-ant-…` (OpenAI/Anthropic),
   `sk_live_…` / `pk_live_…` (Stripe), `AIza…` (Google), `xox…-…` (Slack),
   `-----BEGIN … PRIVATE KEY-----` blocks, and any secret-named variable
   (`api_key`, `secret`, `token`, `password`, `client_secret`, `access_token`)
   assigned a long literal value.
3. Ignore the safe cases — `.env` / `.env.*` / `*.example` files, reads from
   the environment (`process.env.X`, `os.environ["X"]`), and obvious
   placeholders (`your-key-here`, `<TOKEN>`, `${VAR}`, `xxxxx`, `changeme`).
4. For each real hit: move the value into a `.env` file (gitignored), read it
   at runtime instead of hardcoding it, and leave a placeholder in
   `.env.example`. If the key was ever real, flag it for rotation — assume it's
   burned.
5. Report what you moved, anything you flagged for rotation, and any value you
   judged to be a deliberately fake test fixture (record it with one line:
   `SECRET-GUARD: ALLOW — <reason>`).

Don't say "done" while a live credential is still sitting in source.
