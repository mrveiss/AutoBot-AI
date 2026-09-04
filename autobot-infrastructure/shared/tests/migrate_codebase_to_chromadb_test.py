# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for migrate_codebase_to_chromadb's vectorized document text (#15585 sweep finding).

``migrate_functions``, ``migrate_classes``, ``migrate_problems`` and
``migrate_stats`` each built the ``doc_text`` fed to ChromaDB for semantic
search from a triple-quoted string containing ``{}`` placeholders with no
``f`` prefix, so every embedded document read e.g.
``"File: {function_data.get('file_path', 'unknown')}"`` literally -- the
codebase's semantic search index was populated with placeholder text instead
of real function/class/problem/statistic data, degrading every query against
it without ever raising an error. This asserts the documents actually added
to the collection contain real values from the fixture data and no leftover
``{identifier`` placeholder shape.
"""

import json
import re
import sys
from pathlib import Path

# Lives here, not beside the script it tests -- see enhance_workflow_ui_test.py in this same
# directory for the ci.yml path-list / `utilities` namespace-package reasoning (#14563, #14518).
_SCRIPTS_ROOT = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from utilities.migrate_codebase_to_chromadb import CodebaseChromaDBMigration  # noqa: E402

_LEFTOVER_PLACEHOLDER_RE = re.compile(r"\{[A-Za-z_]")


class _FakeRedis:
    """Just enough of the redis-py surface these methods call."""

    def __init__(self, hashes: dict | None = None, strings: dict | None = None):
        self._hashes = hashes or {}
        self._strings = strings or {}

    def scan_iter(self, match: str):
        prefix = match.rstrip("*")
        return iter(k for k in self._hashes if k.startswith(prefix))

    def hgetall(self, key: str) -> dict:
        return self._hashes.get(key, {})

    def get(self, key: str):
        return self._strings.get(key)


class _FakeCollection:
    """Records every .add() call instead of touching a real ChromaDB store."""

    def __init__(self):
        self.calls: list[dict] = []

    def add(self, ids, documents, metadatas):
        self.calls.append({"ids": ids, "documents": documents, "metadatas": metadatas})


def _migration_with(redis_client: _FakeRedis) -> tuple[CodebaseChromaDBMigration, _FakeCollection]:
    migration = CodebaseChromaDBMigration()
    migration.redis_client = redis_client
    collection = _FakeCollection()
    migration.code_collection = collection
    return migration, collection


def test_migrate_functions_renders_real_values_not_placeholders():
    redis_client = _FakeRedis(
        hashes={
            "codebase:functions:get_state_summary": {
                "file_path": "scripts/project_state_tracker.py",
                "start_line": "10",
                "end_line": "42",
                "complexity": "3",
                "parameters": "self",
                "docstring": "Return a summary of tracked phase state.",
            }
        }
    )
    migration, collection = _migration_with(redis_client)

    migration.migrate_functions()

    assert migration.migration_stats["errors"] == 0
    doc_text = collection.calls[0]["documents"][0]
    assert not _LEFTOVER_PLACEHOLDER_RE.search(doc_text), (
        "Function doc_text contains an un-substituted {identifier} placeholder -- "
        "a triple-quoted string is missing its f prefix"
    )
    assert "Function: get_state_summary" in doc_text
    assert "File: scripts/project_state_tracker.py" in doc_text
    assert "Lines: 10-42" in doc_text
    assert "Docstring: Return a summary of tracked phase state." in doc_text


def test_migrate_classes_renders_real_values_not_placeholders():
    redis_client = _FakeRedis(
        hashes={
            "codebase:classes:PhaseValidator": {
                "file_path": "scripts/phase_validation_system.py",
                "start_line": "1",
                "end_line": "300",
                "methods": "validate_all_phases",
                "bases": "object",
                "docstring": "Validates phase completion criteria.",
            }
        }
    )
    migration, collection = _migration_with(redis_client)

    migration.migrate_classes()

    assert migration.migration_stats["errors"] == 0
    doc_text = collection.calls[0]["documents"][0]
    assert not _LEFTOVER_PLACEHOLDER_RE.search(doc_text)
    assert "Class: PhaseValidator" in doc_text
    assert "Methods: validate_all_phases" in doc_text
    assert "Docstring: Validates phase completion criteria." in doc_text


def test_migrate_problems_renders_real_values_not_placeholders():
    problems = [
        {
            "type": "unused_import",
            "severity": "low",
            "file_path": "scripts/deploy_autobot.py",
            "line_number": 12,
            "description": "Imported module `json` is never used.",
            "suggestion": "Remove the unused import.",
        }
    ]
    redis_client = _FakeRedis(strings={"codebase:problems": json.dumps(problems)})
    migration, collection = _migration_with(redis_client)

    migration.migrate_problems()

    assert migration.migration_stats["errors"] == 0
    doc_text = collection.calls[0]["documents"][0]
    assert not _LEFTOVER_PLACEHOLDER_RE.search(doc_text)
    assert "Problem: unused_import" in doc_text
    assert "Description: Imported module `json` is never used." in doc_text
    assert "Suggestion: Remove the unused import." in doc_text


def test_migrate_stats_renders_real_values_not_placeholders():
    stats = {
        "total_files": 4321,
        "total_lines": 987654,
        "python_files": 3000,
        "javascript_files": 1000,
        "vue_files": 321,
        "total_functions": 15000,
        "total_classes": 2200,
        "last_indexed": "2026-01-01T00:00:00",
    }
    redis_client = _FakeRedis(strings={"codebase:stats": json.dumps(stats)})
    migration, collection = _migration_with(redis_client)

    migration.migrate_stats()

    assert migration.migration_stats["errors"] == 0
    doc_text = collection.calls[0]["documents"][0]
    assert not _LEFTOVER_PLACEHOLDER_RE.search(doc_text)
    assert "Total Files: 4321" in doc_text
    assert "Total Lines: 987654" in doc_text
    assert "Last Indexed: 2026-01-01T00:00:00" in doc_text
