#!/usr/bin/env python3
"""
secret-guard :: PreToolUse gate
===============================
Refuses an Edit/Write/MultiEdit when the NEW content being written contains a
live-looking secret/credential — an AWS key, a GitHub/OpenAI/Stripe token, a
private key, a high-entropy `api_key = "..."` literal — landing in a source
file. Stops a credential from ever touching tracked code.

Fires on every Edit/Write/MultiEdit/NotebookEdit. NO-OP unless the ADDED text
contains a real-looking secret AND the target is a non-env source file.

Decision logic:
  - no secret in the added text       -> ALLOW
  - target is a .env / example file   -> ALLOW (that's where secrets belong)
  - value is a placeholder / env read  -> ALLOW
  - real-looking secret literal        -> DENY
  - sentinel present                   -> ALLOW

Sentinel (override): an assistant line containing
  SECRET-GUARD: ALLOW — <reason>
bypasses one block (e.g. a test fixture using a deliberately fake-but-shaped key).

Safety rails (fail-OPEN):
  * any exception                      -> allow (exit 0)
  * kill switch env/file               -> allow
  * .env / .env.* / *.env / example /  -> always allowed (correct home)
    sample / template files
  * secret-guard's own off-switch      -> always allowed
"""
import sys, os, json, re

BLOCK_TAG = "[secret-guard]"
SENTINEL_RE = re.compile(r"(?im)^\s*SECRET-GUARD:\s*ALLOW\b")
ALWAYS_ALLOW = (".secret-guard-off",)


def _allow(msg=None):
    if msg:
        sys.stderr.write(msg + "\n")
    sys.exit(0)


def _deny(reason):
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    print(json.dumps(out))
    sys.exit(0)


def _kill_switch(cwd):
    if os.environ.get("SECRET_GUARD_GATE", "").lower() in ("off", "0", "false", "no"):
        return True
    home = os.path.expanduser("~")
    if os.path.exists(os.path.join(home, ".claude", ".secret-guard-off")):
        return True
    if cwd and os.path.exists(os.path.join(cwd, ".secret-guard-off")):
        return True
    return False


def _norm(path, cwd):
    if not path:
        return None
    p = path
    if os.path.isabs(p) and cwd:
        try:
            p = os.path.relpath(p, cwd)
        except Exception:
            pass
    p = p.replace(os.sep, "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def _is_env_or_example(path):
    """True for files that are the CORRECT home for secrets / are placeholders.

    .env, .env.local, .env.production, foo.env, *.example, *.sample,
    *.template, *.tpl, and any path whose basename signals an example/template.
    These are typically gitignored or are deliberately fake — never block them.
    """
    base = os.path.basename(path).lower()
    # dotenv family: .env, .env.*, *.env
    if base == ".env" or base.startswith(".env.") or base.endswith(".env"):
        return True
    # example / sample / template files (incl. .env.example, config.sample.json)
    for token in ("example", "sample", "template", ".tpl", ".dist"):
        if token in base:
            return True
    return False


def _added_text(name, inp):
    """Return the chunk of NEW content an Edit/Write/MultiEdit introduces."""
    low = (name or "").lower()
    parts = []
    if low.endswith("write") or low == "write":
        c = inp.get("content")
        if isinstance(c, str):
            parts.append(c)
    elif "multiedit" in low:
        for ed in (inp.get("edits") or []):
            if isinstance(ed, dict) and isinstance(ed.get("new_string"), str):
                parts.append(ed["new_string"])
    elif low.endswith("edit") or low == "edit":
        ns = inp.get("new_string")
        if isinstance(ns, str):
            parts.append(ns)
        # NotebookEdit uses new_source
        nsrc = inp.get("new_source")
        if isinstance(nsrc, str):
            parts.append(nsrc)
    return "\n".join(parts)


# --- Secret patterns --------------------------------------------------------
# High-signal, low-false-positive credential shapes. Each is a real prefix +
# enough body length that random code is very unlikely to collide.
SECRET_PATTERNS = [
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key id"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"), "GitHub token"),
    (re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}"), "Anthropic API key"),
    (re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9]{20,}"), "OpenAI-style secret key"),
    (re.compile(r"\bsk_live_[A-Za-z0-9]{16,}"), "Stripe live secret key"),
    (re.compile(r"\b(?:pk|rk)_live_[A-Za-z0-9]{16,}"), "Stripe live key"),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"), "Google API key"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"), "Slack token"),
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP |DSA )?PRIVATE KEY-----"),
     "private key block"),
    # Generic: a secret-named var assigned a long literal.
    (re.compile(
        r"(?i)(api[_-]?key|secret|token|passwd|password|client[_-]?secret|"
        r"access[_-]?token)\s*[:=]\s*['\"]([A-Za-z0-9/+_\-!@#$%^&*.=~]{20,})['\"]"),
     "hardcoded secret literal"),
]

# Substrings that mark a value as a placeholder / example / env-read — never a
# live secret. If the matched value contains any of these, do NOT block.
PLACEHOLDER_TOKENS = (
    "xxx", "your-", "your_", "yourkey", "your.", "<", ">", "${", "...",
    "process.env", "os.environ", "getenv", "os.getenv", "example",
    "changeme", "change-me", "placeholder", "redacted", "dummy", "fake",
    "sample", "test-key", "testkey", "replace", "insert", "todo", "n/a",
    "abc123", "1234567890", "0000000000", "deadbeef",
)


def _looks_placeholder(value):
    if not value:
        return True
    v = value.strip()
    low = v.lower()
    for tok in PLACEHOLDER_TOKENS:
        if tok in low:
            return True
    # strip a known credential prefix, then judge the entropy of the body
    body = v
    for pre in ("sk-ant-", "sk-proj-", "sk-", "sk_live_", "pk_live_",
                "rk_live_", "AKIA", "AIza", "ghp_", "gho_", "ghu_", "ghs_",
                "ghr_", "xoxb-", "xoxa-", "xoxp-", "xoxr-", "xoxs-"):
        if v.startswith(pre):
            body = v[len(pre):]
            break
    # all-one-char (aaaa…, xxxx…, 0000…) -> placeholder
    stripped = re.sub(r"[-_/+]", "", body)
    if stripped and len(set(stripped)) <= 2:
        return True
    # too few distinct chars overall to be a real random secret
    if len(set(stripped)) < 6 and len(stripped) >= 8:
        return True
    return False


def _reads_from_env(text):
    """A line that READS a secret from the environment is the correct pattern."""
    return bool(re.search(
        r"process\.env|os\.environ|os\.getenv|getenv\(|System\.getenv|"
        r"ENV\[|Deno\.env|import\.meta\.env|config\(\)|dotenv",
        text))


def _scan(text):
    """Return a list of (label, snippet) for real-looking secrets in `text`."""
    found = []
    for pat, label in SECRET_PATTERNS:
        for m in pat.finditer(text):
            # the captured value (group 2 for generic, else whole match)
            value = None
            if pat.groups >= 2:
                value = m.group(2)
            if not value:
                value = m.group(0)
            # if this exact match is an env read, skip it
            line = text[max(0, m.start() - 80): m.end() + 1]
            if _reads_from_env(line):
                continue
            if _looks_placeholder(value):
                continue
            snippet = m.group(0)
            if len(snippet) > 24:
                snippet = snippet[:12] + "…" + snippet[-4:]
            found.append((label, snippet))
    return found


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        _allow()

    cwd = payload.get("cwd") or os.getcwd()
    if _kill_switch(cwd):
        _allow()

    tool_name = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input") or {}
    target = (tool_input.get("file_path") or tool_input.get("path")
              or tool_input.get("notebook_path"))
    path = _norm(target, cwd)
    if not path:
        _allow()

    if os.path.basename(path) in ALWAYS_ALLOW:
        _allow()

    # .env / example / template files are the correct home for secrets.
    if _is_env_or_example(path):
        _allow()

    added = _added_text(tool_name, tool_input)
    if not added:
        _allow()

    hits = _scan(added)
    if not hits:
        _allow()

    # sentinel override (one deliberate exception)
    transcript_path = payload.get("transcript_path")
    if transcript_path and os.path.exists(transcript_path):
        try:
            with open(transcript_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()[-400:]
        except Exception:
            lines = []
        for ln in lines:
            ln = ln.strip()
            if not ln:
                continue
            try:
                e = json.loads(ln)
            except Exception:
                continue
            if e.get("type") != "assistant":
                continue
            msg = e.get("message", e)
            content = msg.get("content") if isinstance(msg, dict) else None
            texts = []
            if isinstance(content, str):
                texts.append(content)
            elif isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "text":
                        texts.append(b.get("text", ""))
            for t in texts:
                if SENTINEL_RE.search(t):
                    _allow()

    kinds = ", ".join(sorted({label for label, _ in hits}))
    _deny(
        f"{BLOCK_TAG} This write puts a live-looking secret into `{path}`: {kinds}. "
        "A real credential must never land in a source file — it gets committed, "
        "pushed, and leaked. Instead: move the value into a `.env` (gitignored) "
        "and read it at runtime (`process.env.X` / `os.environ[\"X\"]`), or pull it "
        "from your secret manager. Put a placeholder in `.env.example`. If this key "
        "was ever real, ROTATE it now — assume it's burned. "
        "If this is a deliberately fake, shaped-like-a-key test fixture, say so on "
        "its own line: SECRET-GUARD: ALLOW — <reason>. "
        "(False positive? `touch .secret-guard-off` in cwd.)"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        sys.stderr.write("secret-guard skipped (%s)\n" % exc)
        sys.exit(0)
