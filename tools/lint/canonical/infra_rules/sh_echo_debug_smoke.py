"""sh-echo-debug-smoke — infra-runner smoke-test rule.

Detects `echo "DEBUG: ..."` in shell scripts. Exists only to prove the infra
runner can find rules, run them, and report violations. WARN severity.
"""

from __future__ import annotations

import re
from pathlib import Path

from tools.lint.canonical.diagnostic import Diagnostic

RULE_ID = "sh-echo-debug-smoke"
ISSUE = "#7458"
SEVERITY = "warn"
TARGETS = ["scripts", "repo_tests/lint/canonical/fixtures"]
DESCRIPTION = "echo DEBUG: in shell scripts — pipeline smoke-test rule"
FIX_HINT = "Use a structured logger or remove debug echoes before shipping."

_PATTERN = re.compile(r'echo\s+["\']?DEBUG:')


def check(file_path: Path) -> list[Diagnostic]:
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError:
        return []
    diagnostics: list[Diagnostic] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if _PATTERN.search(line):
            diagnostics.append(
                Diagnostic(
                    rule_id=RULE_ID,
                    issue=ISSUE,
                    severity=SEVERITY,
                    file=file_path,
                    line=lineno,
                    col=line.index("echo"),
                    message='echo "DEBUG: ..." in shell script',
                    snippet=line.strip()[:120],
                    fix_hint=FIX_HINT,
                )
            )
    return diagnostics
