"""Shared violation record for the canonical-check workflow.

Every rule in every runner emits Diagnostic instances. Reporter formatters
consume the same shape regardless of whether the rule was Python AST,
frontend regex, or infra YAML.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

Severity = Literal["block", "warn", "audit"]
_VALID_SEVERITIES: frozenset[str] = frozenset({"block", "warn", "audit"})


@dataclass(frozen=True)
class Diagnostic:
    rule_id: str
    issue: str
    severity: Severity
    file: Path
    line: int
    col: int
    message: str
    snippet: str
    fix_hint: str = ""
    auto_fixable: bool = False

    def __post_init__(self) -> None:
        if self.severity not in _VALID_SEVERITIES:
            raise ValueError(f"severity must be one of {sorted(_VALID_SEVERITIES)}, got {self.severity!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "issue": self.issue,
            "severity": self.severity,
            "file": str(self.file),
            "line": self.line,
            "col": self.col,
            "message": self.message,
            "snippet": self.snippet,
            "fix_hint": self.fix_hint,
            "auto_fixable": self.auto_fixable,
        }
