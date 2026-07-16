#!/usr/bin/env python3
"""
migration-safety :: PreToolUse gate
===================================
Refuses a Bash command or migration-file write that carries destructive SQL —
DROP TABLE/COLUMN, TRUNCATE, DELETE/UPDATE without WHERE, irreversible ALTERs —
unless a migration plan has been declared first. Destroyed data has no
kill switch; this gate makes the plan a precondition, not an afterthought.

Fires on every Bash / Edit / Write / MultiEdit. NO-OP unless:
  * Bash: the command text contains destructive SQL, or
  * Edit/Write: the target is a .sql file or lives on a migration-ish path
    (path contains "migration"/"migrate") and the ADDED text is destructive.

A plan is declared in priority order:
  1. .migration-plan file in cwd (any non-empty content = plan exists)
  2. MIGRATION-SAFETY: ALLOW — <reason> sentinel in the assistant transcript
     (must state target, that a dry-run was done, and the rollback)

Destructive patterns (SQL comments `--` are skipped):
  * DROP TABLE / DROP DATABASE / DROP SCHEMA
  * ALTER TABLE … DROP (COLUMN/CONSTRAINT/…)
  * TRUNCATE
  * DELETE FROM … with no WHERE in the same statement
  * UPDATE … SET … with no WHERE in the same statement

Decision:
  * nothing destructive            -> ALLOW (silent no-op)
  * destructive, plan declared     -> ALLOW
  * destructive, no plan           -> DENY

Safety rails (fail-OPEN):
  * any exception                  -> allow (exit 0)
  * kill switch env/file           -> allow
  * .migration-plan itself is always writable
  * DELETE/UPDATE with a WHERE, CREATE/ADD-only migrations, and SELECTs
    never flag — the gate only fires on the irreversible shapes
"""
import sys, os, json, re

BLOCK_TAG = "[migration-safety]"
SENTINEL = "MIGRATION-SAFETY: ALLOW"
PLAN_FILE = ".migration-plan"
ALWAYS_ALLOW = (PLAN_FILE, ".migration-safety-off")

MIGRATION_PATH_HINT = re.compile(r"(?i)(migrat|schema)")

# --- Destructive SQL shapes ---------------------------------------------------
DESTRUCTIVE = [
    (re.compile(r"(?i)\bDROP\s+TABLE\b"), "DROP TABLE"),
    (re.compile(r"(?i)\bDROP\s+DATABASE\b"), "DROP DATABASE"),
    (re.compile(r"(?i)\bDROP\s+SCHEMA\b"), "DROP SCHEMA"),
    (re.compile(r"(?i)\bALTER\s+TABLE\b[^;]{0,200}?\bDROP\b"), "ALTER TABLE … DROP"),
    (re.compile(r"(?i)\bTRUNCATE\b"), "TRUNCATE"),
]

DELETE_RE = re.compile(r"(?i)\bDELETE\s+FROM\b")
UPDATE_RE = re.compile(r"(?i)\bUPDATE\s+\S+\s+SET\b")
WHERE_RE = re.compile(r"(?i)\bWHERE\b")


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
    if os.environ.get("MIGRATION_SAFETY_GATE", "").lower() in ("off", "0", "false", "no"):
        return True
    home = os.path.expanduser("~")
    if os.path.exists(os.path.join(home, ".claude", ".migration-safety-off")):
        return True
    if cwd and os.path.exists(os.path.join(cwd, ".migration-safety-off")):
        return True
    return False


def _strip_sql_comments(text):
    out = []
    for line in text.splitlines():
        s = line.split("--", 1)[0] if "--" in line else line
        out.append(s)
    return "\n".join(out)


def _scan_destructive(text):
    """Return distinct destructive-SQL labels found in `text`."""
    body = _strip_sql_comments(text)
    found = set()
    for pat, label in DESTRUCTIVE:
        if pat.search(body):
            found.add(label)
    # statement-level WHERE check: split on ';' so a WHERE in a later
    # statement can't whitewash an earlier bare DELETE/UPDATE.
    for stmt in body.split(";"):
        if DELETE_RE.search(stmt) and not WHERE_RE.search(stmt):
            found.add("DELETE without WHERE")
        if UPDATE_RE.search(stmt) and not WHERE_RE.search(stmt):
            found.add("UPDATE without WHERE")
    return sorted(found)


def _plan_declared(cwd, transcript_path):
    # 1. .migration-plan file
    pf = os.path.join(cwd, PLAN_FILE) if cwd else PLAN_FILE
    if os.path.exists(pf):
        try:
            with open(pf, "r", encoding="utf-8", errors="ignore") as f:
                if f.read().strip():
                    return PLAN_FILE
        except Exception:
            return PLAN_FILE  # exists but unreadable: fail open on the plan
    # 2. sentinel in the assistant transcript
    if transcript_path and os.path.exists(transcript_path):
        try:
            with open(transcript_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()[-1200:]
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
                if SENTINEL.lower() in t.lower() and "<" not in t.split(SENTINEL)[-1][:40]:
                    return "sentinel"
    return None


def _added_text(name, inp):
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
    return "\n".join(parts)


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        _allow()

    cwd = payload.get("cwd") or os.getcwd()
    if _kill_switch(cwd):
        _allow()

    tool_name = (payload.get("tool_name") or "").lower()
    tool_input = payload.get("tool_input") or {}

    findings = []
    target = None

    if tool_name == "bash" or tool_name.endswith("bash"):
        cmd = tool_input.get("command")
        if not isinstance(cmd, str) or not cmd.strip():
            _allow()
        target = "this command"
        findings = _scan_destructive(cmd)
    else:
        fp = tool_input.get("file_path") or tool_input.get("path") or ""
        if not fp:
            _allow()
        base = os.path.basename(fp)
        if base in ALWAYS_ALLOW:
            _allow()
        ext = os.path.splitext(fp)[1].lower()
        if ext != ".sql" and not MIGRATION_PATH_HINT.search(fp):
            _allow()
        target = f"`{base}`"
        added = _added_text(payload.get("tool_name"), tool_input)
        if not added:
            _allow()
        findings = _scan_destructive(added)

    if not findings:
        _allow()

    source = _plan_declared(cwd, payload.get("transcript_path"))
    if source:
        _allow(f"migration-safety: destructive SQL allowed (plan via {source})")

    found = ", ".join(findings)
    _deny(
        f"{BLOCK_TAG} {target} contains destructive SQL ({found}) and no migration plan "
        "is declared. Destroyed data has no undo. Invoke the `migration-safety` skill and "
        "declare the plan FIRST: (1) state the exact target (database/table/rows affected, "
        "with a count from a dry-run SELECT), (2) show the dry-run, (3) state the rollback "
        "(backup taken, down-migration written, or why none is possible — say that out "
        "loud). Then either write it to a `.migration-plan` file in cwd, or emit a line "
        f"`{SENTINEL} — <target, dry-run result, rollback>` and retry. "
        "(False positive? `touch .migration-safety-off` in cwd.)"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        sys.stderr.write("migration-safety skipped (%s)\n" % exc)
        sys.exit(0)
