import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "hooks" / "scripts" / "accessibility_gate.py"


def run_gate(entries, extra_env=None):
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
        for entry in entries:
            handle.write(json.dumps(entry) + "\n")
        transcript = handle.name
    try:
        env = os.environ.copy()
        env.pop("ACCESSIBILITY_GATE", None)
        env.update(extra_env or {})
        return subprocess.run(
            [sys.executable, str(SCRIPT)],
            input=json.dumps({"cwd": os.getcwd(), "transcript_path": transcript}),
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )
    finally:
        os.unlink(transcript)


def assistant_tool(name, tool_input):
    return {
        "type": "assistant",
        "message": {"content": [{"type": "tool_use", "name": name, "input": tool_input}]},
    }


class AccessibilityGateTests(unittest.TestCase):
    def test_non_ui_turn_passes(self):
        result = run_gate([{"type": "user", "message": {"content": "fix the API"}}])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_ui_edit_without_evidence_blocks(self):
        result = run_gate([
            {"type": "user", "message": {"content": "fix the button"}},
            assistant_tool("Edit", {"file_path": "src/Button.tsx"}),
        ])
        self.assertIn('"decision": "block"', result.stdout)
        self.assertIn("ACCESSIBILITY-GATE: PASS", result.stdout)

    def test_evidence_line_allows_ui_turn(self):
        result = run_gate([
            {"type": "user", "message": {"content": "fix the button"}},
            assistant_tool("Edit", {"file_path": "src/Button.tsx"}),
            {"type": "assistant", "message": {"content": "ACCESSIBILITY-GATE: PASS — keyboard + axe, 0 blockers"}},
        ])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_kill_switch_allows_ui_turn(self):
        result = run_gate(
            [
                {"type": "user", "message": {"content": "fix the button"}},
                assistant_tool("Edit", {"file_path": "src/Button.tsx"}),
            ],
            {"ACCESSIBILITY_GATE": "off"},
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
