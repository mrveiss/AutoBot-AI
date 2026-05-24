#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Pre-commit hook: block new local BaseModel subclasses in non-schema API endpoint files.

Schema migration work (#5799, #5996) moved 375+ classes from endpoint files into
domain schemas_*.py files. Without enforcement, local schemas will be re-introduced
over time. This hook prevents that regression.

Scan target:
  autobot-backend/api/*.py  — NOT schemas_*.py files

Allowlisted files (tightly-coupled domain logic, exempt by design):
  workflow_state.py  — WorkflowState tightly coupled with WorkflowStateMachine;
                       circular import risk if extracted (per #5996 audit)

Exit codes:
  0 — clean
  1 — violations found

Background: #5799 (schemas_common.py split), #5996 (terminal/analytics/knowledge model
merges), #6056 (this hook).
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _scan_helpers import iter_python_files  # noqa: E402

HOOK_ID = "no-local-schemas"

# Files in autobot-backend/api/ that are exempt from the check.
# Filename only (no directory prefix) — matched against path.name.
ALLOWLISTED_FILENAMES: frozenset[str] = frozenset(
    {
        "workflow_state.py",  # WorkflowState tightly coupled with WorkflowStateMachine (#5996)
    }
)

# Guidance shown with every violation to direct the developer to the right file.
_DOMAIN_GUIDE = """\
    schemas_analytics.py   – analytics, cost, usage
    schemas_agent.py       – agents, auth, chat, goals
    schemas_code.py        – code, integration, CI/CD, sandbox, MCP
    schemas_knowledge.py   – knowledge base, RAG, documents
    schemas_system.py      – system, config, permissions, terminal, vision
    schemas_terminal.py    – terminal session models (non-schema classes exempt)
    schemas_workflows.py   – workflows, marketplace, triggers"""


def _is_target_file(path: Path, repo_root: Path) -> bool:
    """Return True if *path* should be scanned by this hook.

    Conditions:
    - Resolves to within autobot-backend/api/
    - NOT named schemas_*.py
    - NOT in the allowlist
    """
    try:
        rel = path.resolve().relative_to(repo_root)
    except ValueError:
        return False

    parts = rel.parts
    # Must be inside autobot-backend/api/ (exactly — not a sub-package)
    if len(parts) < 3 or parts[0] != "autobot-backend" or parts[1] != "api":
        return False

    name = path.name
    if name.startswith("schemas_"):
        return False
    if name in ALLOWLISTED_FILENAMES:
        return False
    return True


def _basemodel_subclasses(tree: ast.Module) -> List[Tuple[int, str]]:
    """Return [(line_no, class_name)] for each BaseModel subclass in *tree*.

    Uses AST ClassDef nodes. A class is considered a BaseModel subclass when
    any of its bases is:
      - ast.Name with id == "BaseModel"
      - ast.Attribute with attr == "BaseModel"  (e.g. pydantic.BaseModel)
    """
    hits: List[Tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for base in node.bases:
            if isinstance(base, ast.Name) and base.id == "BaseModel":
                hits.append((node.lineno, node.name))
                break
            if isinstance(base, ast.Attribute) and base.attr == "BaseModel":
                hits.append((node.lineno, node.name))
                break
    return hits


def _check_file(path: Path, repo_root: Path) -> List[Tuple[int, str]]:
    """Return [(line_no, class_name)] for each BaseModel subclass violation in *path*.

    Returns an empty list when:
    - The file is not a scan target
    - The file cannot be parsed (syntax error, encoding error, missing file)
    - No BaseModel subclasses are found
    """
    if not _is_target_file(path, repo_root):
        return []

    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return []

    return _basemodel_subclasses(tree)


def main(argv: List[str]) -> int:
    repo_root = Path(__file__).resolve().parents[2]
    files = list(iter_python_files(argv[1:], repo_root))
    total = 0
    for path in files:
        hits = _check_file(path, repo_root)
        if not hits:
            continue
        try:
            rel = path.resolve().relative_to(repo_root)
        except ValueError:
            rel = path
        for line_no, class_name in hits:
            print(
                f"[{HOOK_ID}] {rel}:{line_no}: Local BaseModel subclass '{class_name}' found.\n"
                f"  Move it to the appropriate domain schema file:\n"
                f"{_DOMAIN_GUIDE}",
                file=sys.stderr,
            )
            total += 1
    if total:
        print(
            f"\n[{HOOK_ID}] {total} violation(s). "
            f"Move BaseModel subclasses to the matching domain schemas_*.py file (#6056).",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
