# no-slop

**"Delve into" is not writing.**

Claude Code plugin that blocks turns ending after you've written AI-tell "slop" prose — `delve into`, `it's worth noting that`, `a testament to`, `navigate the complexities`, `rich tapestry`, em-dash pile-ups — unless the writing is plain or you explicitly declare it intentional with `NO-SLOP: INTENTIONAL`. The prose complement to [`no-stub`](../no-stub/README.md).

## Install

```bash
claude plugin marketplace add logicleap-labs/claude-plugins
claude plugin install no-slop
```

Restart Claude Code. Disable: `claude plugin disable no-slop`

## What's inside

| Piece | Role |
|---|---|
| **Skill `no-slop`** | Method: find the tell → cut it, keep the meaning → one idea per sentence, no throat-clearing |
| **Stop hook** | Blocks end-of-turn when prose edited this turn carries 2+ distinct AI tells |
| **`/no-slop:no-slop`** | On-demand scan-and-rewrite sweep of your own session's prose |

Only scans prose edited *this segment* (`.md`/`.mdx`/`.txt`/`.rst` — the inverse of no-stub's code set), only flags tells in **added** text, ignores code. Built tight to dodge false positives: only the multi-word clichés fire (never bare "leverage"/"robust"/"utilize"), one stray tell never blocks (threshold is 2 distinct), and the em-dash signal only counts true em-dashes (—) in short paragraphs.

## Kill switch

```bash
touch .no-slop-off   # in project root
# or
export NO_SLOP_GATE=off
```

Fails open on errors and on any ambiguity; loop-capped at 2 blocks per turn. Slop on purpose (quoting it as an example, reproducing source copy)? End your message with `NO-SLOP: INTENTIONAL — <reason>`.

## Pairs with

- **[`no-stub`](../no-stub/README.md)** — the same forcing function for code: don't ship half-written work
- **[`verify-before-done`](../verify-before-done/README.md)** — once the prose is clean, prove the code behind it runs

## License

MIT © Josh Matthews / LogicLeap Ltd.
